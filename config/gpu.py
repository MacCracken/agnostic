"""GPU detection and status reporting.

Detects available NVIDIA GPUs via ``nvidia-smi`` (or falls back to an
agnosys probe when running on an AGNOS fleet node).  Provides a cached
snapshot of GPU state that the crew scheduler can query before placing
agents.

Environment variables
---------------------
AGNOS_GPU_ENABLED
    Master switch. Set to ``false`` to disable GPU detection entirely
    (e.g. on headless CI nodes). Default ``true``.
AGNOS_GPU_PROBE_INTERVAL
    Seconds between hardware re-probes. Default ``30``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_GPU_ENABLED = os.getenv("AGNOS_GPU_ENABLED", "true").lower() not in (
    "false",
    "0",
    "no",
)
_PROBE_INTERVAL = int(os.getenv("AGNOS_GPU_PROBE_INTERVAL", "30"))


@dataclass(frozen=True)
class GPUDevice:
    """Snapshot of a single GPU."""

    index: int
    name: str
    uuid: str
    memory_total_mb: int
    memory_used_mb: int
    memory_free_mb: int
    utilization_pct: int  # 0-100
    temperature_c: int
    cuda_version: str = ""

    @property
    def memory_available_mb(self) -> int:
        return self.memory_free_mb

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "uuid": self.uuid,
            "memory_total_mb": self.memory_total_mb,
            "memory_used_mb": self.memory_used_mb,
            "memory_free_mb": self.memory_free_mb,
            "utilization_pct": self.utilization_pct,
            "temperature_c": self.temperature_c,
            "cuda_version": self.cuda_version,
        }


@dataclass
class GPUStatus:
    """Aggregated GPU status for the host."""

    available: bool = False
    device_count: int = 0
    devices: list[GPUDevice] = field(default_factory=list)
    driver_version: str = ""
    cuda_version: str = ""
    probed_at: float = 0.0
    error: str = ""

    @property
    def total_memory_mb(self) -> int:
        return sum(d.memory_total_mb for d in self.devices)

    @property
    def free_memory_mb(self) -> int:
        return sum(d.memory_free_mb for d in self.devices)

    def devices_with_free_memory(self, min_mb: int) -> list[GPUDevice]:
        """Return devices with at least *min_mb* free VRAM."""
        return [d for d in self.devices if d.memory_free_mb >= min_mb]

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "device_count": self.device_count,
            "devices": [d.to_dict() for d in self.devices],
            "driver_version": self.driver_version,
            "cuda_version": self.cuda_version,
            "total_memory_mb": self.total_memory_mb,
            "free_memory_mb": self.free_memory_mb,
            "probed_at": self.probed_at,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Probe implementation
# ---------------------------------------------------------------------------

_NVIDIA_SMI_QUERY = (
    "index,name,uuid,memory.total,memory.used,memory.free,"
    "utilization.gpu,temperature.gpu"
)


def _probe_nvidia_smi() -> GPUStatus:
    """Probe GPUs via ``nvidia-smi --query-gpu``."""
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return GPUStatus(error="nvidia-smi not found")

    try:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=" + _NVIDIA_SMI_QUERY,
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return GPUStatus(error="nvidia-smi timed out")
    except Exception as exc:
        return GPUStatus(error=f"nvidia-smi failed: {exc}")

    if result.returncode != 0:
        return GPUStatus(
            error=f"nvidia-smi exited {result.returncode}: {result.stderr.strip()}"
        )

    # Parse driver/cuda version from a separate call
    driver_version = ""
    cuda_version = ""
    try:
        ver_result = subprocess.run(
            [nvidia_smi, "--query-gpu=driver_version", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if ver_result.returncode == 0:
            driver_version = ver_result.stdout.strip().split("\n")[0].strip()

        # CUDA version from nvidia-smi header
        header_result = subprocess.run(
            [nvidia_smi],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if header_result.returncode == 0:
            for line in header_result.stdout.split("\n"):
                if "CUDA Version" in line:
                    parts = line.split("CUDA Version:")
                    if len(parts) > 1:
                        cuda_version = parts[1].strip().rstrip("|").strip()
                    break
    except Exception:
        pass

    devices: list[GPUDevice] = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 8:
            continue
        try:
            devices.append(
                GPUDevice(
                    index=int(parts[0]),
                    name=parts[1],
                    uuid=parts[2],
                    memory_total_mb=int(parts[3]),
                    memory_used_mb=int(parts[4]),
                    memory_free_mb=int(parts[5]),
                    utilization_pct=int(parts[6]),
                    temperature_c=int(parts[7]),
                    cuda_version=cuda_version,
                )
            )
        except (ValueError, IndexError) as exc:
            logger.warning("Skipping malformed nvidia-smi line %r: %s", line, exc)

    return GPUStatus(
        available=len(devices) > 0,
        device_count=len(devices),
        devices=devices,
        driver_version=driver_version,
        cuda_version=cuda_version,
        probed_at=time.time(),
    )


def _probe_agnosys() -> GPUStatus | None:
    """Try to read GPU info from an agnosys probe file (AGNOS fleet nodes).

    Returns None if agnosys data is not available.
    """
    probe_path = os.getenv("AGNOS_GPU_PROBE_PATH", "/var/lib/agnosys/gpu.json")
    try:
        with open(probe_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    devices = []
    for gpu in data.get("devices", []):
        try:
            devices.append(
                GPUDevice(
                    index=gpu.get("index", len(devices)),
                    name=gpu.get("name", "Unknown"),
                    uuid=gpu.get("uuid", ""),
                    memory_total_mb=gpu.get("memory_total_mb", 0),
                    memory_used_mb=gpu.get("memory_used_mb", 0),
                    memory_free_mb=gpu.get("memory_free_mb", 0),
                    utilization_pct=gpu.get("utilization_pct", 0),
                    temperature_c=gpu.get("temperature_c", 0),
                    cuda_version=data.get("cuda_version", ""),
                )
            )
        except Exception as exc:
            logger.warning("Skipping malformed agnosys GPU entry: %s", exc)

    return GPUStatus(
        available=len(devices) > 0,
        device_count=len(devices),
        devices=devices,
        driver_version=data.get("driver_version", ""),
        cuda_version=data.get("cuda_version", ""),
        probed_at=time.time(),
    )


# ---------------------------------------------------------------------------
# Cached probe
# ---------------------------------------------------------------------------

_cached_status: GPUStatus | None = None


def detect_gpus(force: bool = False) -> GPUStatus:
    """Return current GPU status, using a cached probe within the interval.

    Set *force=True* to bypass the cache and re-probe immediately.
    """
    global _cached_status

    if not _GPU_ENABLED:
        return GPUStatus(error="GPU detection disabled (AGNOS_GPU_ENABLED=false)")

    now = time.time()
    if (
        not force
        and _cached_status is not None
        and (now - _cached_status.probed_at) < _PROBE_INTERVAL
    ):
        return _cached_status

    # Try agnosys first (fleet node), fall back to nvidia-smi
    status = _probe_agnosys()
    if status is None:
        status = _probe_nvidia_smi()

    _cached_status = status

    if status.available:
        logger.info(
            "GPU probe: %d device(s), %d MB total, %d MB free",
            status.device_count,
            status.total_memory_mb,
            status.free_memory_mb,
        )
    elif status.error:
        logger.debug("GPU probe: %s", status.error)

    return status


def get_gpu_status() -> GPUStatus:
    """Convenience alias for ``detect_gpus()`` (non-forced)."""
    return detect_gpus()


def reset_cache() -> None:
    """Clear the cached GPU status (useful in tests)."""
    global _cached_status
    _cached_status = None
