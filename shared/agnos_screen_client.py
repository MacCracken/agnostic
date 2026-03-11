"""
AGNOS Screen Capture Client.

Captures screenshots and manages screen recordings via the AGNOS daimon
screen capture API. Used by the Senior QA agent for visual regression
testing and CV-based element detection.

Configure via:
- AGNOS_SCREEN_ENABLED: Enable screen capture (default: false)
- AGNOS_AGENT_REGISTRY_URL: Daimon base URL
- AGNOS_AGENT_API_KEY: API key for daimon
"""

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

AGNOS_PATH_PREFIX = os.getenv("AGNOS_PATH_PREFIX", "/v1")

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class AgnosScreenClient:
    """Client for AGNOS screen capture and recording APIs."""

    def __init__(self) -> None:
        self.enabled = (
            os.getenv("AGNOS_SCREEN_ENABLED", "false").lower() == "true"
            and _HTTPX_AVAILABLE
        )
        self.base_url = os.getenv(
            "AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090"
        )
        self.api_key = os.getenv("AGNOS_AGENT_API_KEY", "")
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

        try:
            from shared.resilience import CircuitBreaker

            self._circuit = CircuitBreaker(
                name="agnos_screen", failure_threshold=5, recovery_timeout=60.0
            )
        except ImportError:
            self._circuit = None

    async def _get_client(self) -> "httpx.AsyncClient":
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers={"X-API-Key": self.api_key} if self.api_key else {},
                    timeout=15.0,
                )
        return self._client

    def _can_execute(self) -> bool:
        if not self.enabled:
            return False
        if self._circuit and not self._circuit.can_execute():
            return False
        return True

    def _record_success(self) -> None:
        if self._circuit:
            self._circuit.record_success()

    def _record_failure(self) -> None:
        if self._circuit:
            self._circuit.record_failure()

    # ------------------------------------------------------------------
    # Screenshot capture
    # ------------------------------------------------------------------

    async def capture(
        self,
        *,
        target_type: str = "full_screen",
        format: str = "png",
        agent_id: str | None = None,
        region: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Capture a screenshot via AGNOS screen capture API.

        Args:
            target_type: "full_screen", "window", or "region".
            format: Image format — "png", "bmp", or "raw_argb".
            agent_id: Optional agent UUID for permission tracking.
            region: For "region" target: {"x", "y", "width", "height"}.

        Returns:
            Dict with id, width, height, format, data_base64, etc.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        target: dict[str, Any] = {"type": target_type}
        if region and target_type == "region":
            target.update(region)

        payload: dict[str, Any] = {"target": target, "format": format}
        if agent_id:
            payload["agent_id"] = agent_id

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/screen/capture",
                json=payload,
            )
            response.raise_for_status()
            self._record_success()
            return response.json()
        except Exception as exc:
            self._record_failure()
            logger.warning("Screen capture failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    # ------------------------------------------------------------------
    # Recording management
    # ------------------------------------------------------------------

    async def start_recording(
        self,
        *,
        target_type: str = "full_screen",
        format: str = "png",
        agent_id: str | None = None,
        frame_interval_ms: int = 100,
        max_duration_secs: int = 60,
    ) -> dict[str, Any]:
        """Start a screen recording session.

        Returns:
            Dict with status and recording_id.
        """
        if not self._can_execute():
            return {"status": "disabled"}

        payload: dict[str, Any] = {
            "target": {"type": target_type},
            "format": format,
            "frame_interval_ms": frame_interval_ms,
            "max_duration_secs": max_duration_secs,
        }
        if agent_id:
            payload["agent_id"] = agent_id

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/screen/recording/start",
                json=payload,
            )
            response.raise_for_status()
            self._record_success()
            result = response.json()
            logger.info("Started recording: %s", result.get("recording_id"))
            return result
        except Exception as exc:
            self._record_failure()
            logger.warning("Start recording failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def stop_recording(self, recording_id: str) -> dict[str, Any]:
        """Stop a screen recording session."""
        if not self._can_execute():
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/screen/recording/{recording_id}/stop",
            )
            response.raise_for_status()
            self._record_success()
            return response.json()
        except Exception as exc:
            self._record_failure()
            logger.warning("Stop recording failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_latest_frame(self, recording_id: str) -> dict[str, Any]:
        """Get the most recent frame from an active recording."""
        if not self._can_execute():
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            response = await client.get(
                f"{AGNOS_PATH_PREFIX}/screen/recording/{recording_id}/latest",
            )
            response.raise_for_status()
            self._record_success()
            return response.json()
        except Exception as exc:
            self._record_failure()
            logger.debug("Get latest frame failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_frames(
        self, recording_id: str, *, since: int = 0
    ) -> list[dict[str, Any]]:
        """Get frames from a recording since a sequence number."""
        if not self._can_execute():
            return []

        try:
            client = await self._get_client()
            response = await client.get(
                f"{AGNOS_PATH_PREFIX}/screen/recording/{recording_id}/frames",
                params={"since": since},
            )
            response.raise_for_status()
            self._record_success()
            return response.json().get("frames", [])
        except Exception as exc:
            self._record_failure()
            logger.debug("Get frames failed: %s", exc)
            return []

    async def get_recording_info(self, recording_id: str) -> dict[str, Any]:
        """Get metadata for a recording session."""
        if not self._can_execute():
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            response = await client.get(
                f"{AGNOS_PATH_PREFIX}/screen/recording/{recording_id}",
            )
            response.raise_for_status()
            self._record_success()
            return response.json()
        except Exception as exc:
            self._record_failure()
            logger.debug("Get recording info failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def list_recordings(self) -> list[dict[str, Any]]:
        """List all recording sessions."""
        if not self._can_execute():
            return []

        try:
            client = await self._get_client()
            response = await client.get(
                f"{AGNOS_PATH_PREFIX}/screen/recordings",
            )
            response.raise_for_status()
            self._record_success()
            return response.json().get("recordings", [])
        except Exception as exc:
            self._record_failure()
            logger.debug("List recordings failed: %s", exc)
            return []

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


agnos_screen = AgnosScreenClient()
