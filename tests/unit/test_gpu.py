"""Tests for GPU detection and scheduling."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from config.gpu import (
    GPUDevice,
    GPUStatus,
    _probe_nvidia_smi,
    detect_gpus,
    reset_cache,
)
from config.gpu_scheduler import (
    AgentGPURequirements,
    GPUAssignment,
    GPUPlacementPlan,
    GPUSlotTracker,
    apply_gpu_assignment,
    schedule_crew_gpus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_gpu(
    index: int = 0,
    name: str = "NVIDIA RTX 4090",
    memory_total_mb: int = 24576,
    memory_used_mb: int = 2048,
    memory_free_mb: int = 22528,
    utilization_pct: int = 15,
) -> GPUDevice:
    return GPUDevice(
        index=index,
        name=name,
        uuid=f"GPU-fake-uuid-{index}",
        memory_total_mb=memory_total_mb,
        memory_used_mb=memory_used_mb,
        memory_free_mb=memory_free_mb,
        utilization_pct=utilization_pct,
        temperature_c=45,
        cuda_version="12.4",
    )


def _make_gpu_status(device_count: int = 1) -> GPUStatus:
    devices = [_make_gpu(index=i) for i in range(device_count)]
    return GPUStatus(
        available=True,
        device_count=device_count,
        devices=devices,
        driver_version="550.54.14",
        cuda_version="12.4",
        probed_at=1000.0,
    )


def _make_agent_def(
    key: str = "test-agent",
    gpu_required: bool = False,
    gpu_strict: bool = False,
    gpu_preferred: bool = False,
    gpu_memory_min_mb: int = 0,
) -> dict:
    return {
        "agent_key": key,
        "name": f"Test Agent {key}",
        "role": "tester",
        "goal": "test",
        "backstory": "test",
        "gpu_required": gpu_required,
        "gpu_strict": gpu_strict,
        "gpu_preferred": gpu_preferred,
        "gpu_memory_min_mb": gpu_memory_min_mb,
    }


# ---------------------------------------------------------------------------
# GPUDevice tests
# ---------------------------------------------------------------------------


class TestGPUDevice:
    def test_to_dict(self):
        dev = _make_gpu()
        d = dev.to_dict()
        assert d["name"] == "NVIDIA RTX 4090"
        assert d["memory_free_mb"] == 22528

    def test_memory_available(self):
        dev = _make_gpu(memory_free_mb=8000)
        assert dev.memory_available_mb == 8000


# ---------------------------------------------------------------------------
# GPUStatus tests
# ---------------------------------------------------------------------------


class TestGPUStatus:
    def test_empty_status(self):
        s = GPUStatus()
        assert not s.available
        assert s.total_memory_mb == 0
        assert s.free_memory_mb == 0

    def test_status_with_devices(self):
        s = _make_gpu_status(device_count=2)
        assert s.available
        assert s.device_count == 2
        assert s.total_memory_mb == 24576 * 2

    def test_devices_with_free_memory(self):
        s = _make_gpu_status(device_count=2)
        assert len(s.devices_with_free_memory(20000)) == 2
        assert len(s.devices_with_free_memory(30000)) == 0

    def test_to_dict(self):
        s = _make_gpu_status()
        d = s.to_dict()
        assert d["available"] is True
        assert d["device_count"] == 1
        assert len(d["devices"]) == 1


# ---------------------------------------------------------------------------
# detect_gpus tests
# ---------------------------------------------------------------------------


class TestDetectGpus:
    def setup_method(self):
        reset_cache()

    def test_disabled_via_env(self):
        with patch.dict(os.environ, {"AGNOS_GPU_ENABLED": "false"}):
            # Need to reimport to pick up env change
            import config.gpu as gpu_mod

            old = gpu_mod._GPU_ENABLED
            gpu_mod._GPU_ENABLED = False
            try:
                status = detect_gpus()
                assert not status.available
                assert "disabled" in status.error
            finally:
                gpu_mod._GPU_ENABLED = old

    def test_cache_hit(self):
        import config.gpu as gpu_mod

        fake = _make_gpu_status()
        gpu_mod._cached_status = fake
        import time

        gpu_mod._cached_status = GPUStatus(
            available=True,
            device_count=1,
            devices=[_make_gpu()],
            probed_at=time.time(),
        )
        status = detect_gpus()
        assert status.available

    @patch("config.gpu._probe_agnosys", return_value=None)
    @patch("config.gpu._probe_nvidia_smi")
    def test_falls_back_to_nvidia_smi(self, mock_smi, mock_agnosys):
        mock_smi.return_value = _make_gpu_status()
        status = detect_gpus(force=True)
        assert status.available
        mock_smi.assert_called_once()

    @patch("config.gpu._probe_agnosys")
    def test_prefers_agnosys(self, mock_agnosys):
        mock_agnosys.return_value = _make_gpu_status()
        status = detect_gpus(force=True)
        assert status.available
        mock_agnosys.assert_called_once()


# ---------------------------------------------------------------------------
# nvidia-smi probe tests
# ---------------------------------------------------------------------------


class TestProbeNvidiaSmi:
    @patch("shutil.which", return_value=None)
    def test_no_nvidia_smi(self, mock_which):
        status = _probe_nvidia_smi()
        assert not status.available
        assert "not found" in status.error

    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("subprocess.run")
    def test_parse_output(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="0, NVIDIA RTX 4090, GPU-abc-123, 24576, 2048, 22528, 15, 45\n",
            stderr="",
        )
        status = _probe_nvidia_smi()
        assert status.available
        assert status.device_count == 1
        assert status.devices[0].name == "NVIDIA RTX 4090"
        assert status.devices[0].memory_total_mb == 24576

    @patch("shutil.which", return_value="/usr/bin/nvidia-smi")
    @patch("subprocess.run")
    def test_multi_gpu(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "0, NVIDIA RTX 4090, GPU-abc-1, 24576, 2048, 22528, 15, 45\n"
                "1, NVIDIA RTX 4090, GPU-abc-2, 24576, 4096, 20480, 30, 50\n"
            ),
            stderr="",
        )
        status = _probe_nvidia_smi()
        assert status.device_count == 2


# ---------------------------------------------------------------------------
# AgentGPURequirements tests
# ---------------------------------------------------------------------------


class TestAgentGPURequirements:
    def test_from_dict_defaults(self):
        req = AgentGPURequirements.from_definition({"agent_key": "foo"})
        assert not req.gpu_required
        assert not req.gpu_strict
        assert req.gpu_memory_min_mb == 0

    def test_from_dict_explicit(self):
        req = AgentGPURequirements.from_definition(
            {
                "agent_key": "ml-agent",
                "gpu_required": True,
                "gpu_strict": True,
                "gpu_memory_min_mb": 8000,
            }
        )
        assert req.gpu_required
        assert req.gpu_strict
        assert req.gpu_memory_min_mb == 8000

    def test_from_dict_via_metadata(self):
        req = AgentGPURequirements.from_definition(
            {
                "agent_key": "ml-agent",
                "metadata": {"gpu_required": True, "gpu_memory_min_mb": 4000},
            }
        )
        assert req.gpu_required
        assert req.gpu_memory_min_mb == 4000

    def test_from_agent_definition_object(self):
        from agents.base import AgentDefinition

        defn = AgentDefinition(
            agent_key="gpu-agent",
            name="GPU Agent",
            role="compute",
            goal="crunch",
            backstory="fast",
            gpu_required=True,
            gpu_memory_min_mb=16000,
        )
        req = AgentGPURequirements.from_definition(defn)
        assert req.gpu_required
        assert req.gpu_memory_min_mb == 16000


# ---------------------------------------------------------------------------
# GPU scheduling tests
# ---------------------------------------------------------------------------


class TestScheduleCrewGpus:
    def test_no_gpu_agents(self):
        agents = [_make_agent_def("a1"), _make_agent_def("a2")]
        plan = schedule_crew_gpus(agents, gpu_status=_make_gpu_status())
        assert not plan.has_errors
        assert len(plan.gpu_agents) == 0
        assert len(plan.cpu_agents) == 2

    def test_gpu_required_with_gpu_available(self):
        agents = [
            _make_agent_def("cpu-agent"),
            _make_agent_def("gpu-agent", gpu_required=True),
        ]
        plan = schedule_crew_gpus(agents, gpu_status=_make_gpu_status())
        assert not plan.has_errors
        assert len(plan.gpu_agents) == 1
        gpu_a = plan.get_assignment("gpu-agent")
        assert gpu_a is not None
        assert gpu_a.is_gpu
        assert gpu_a.device_index == 0

    def test_gpu_required_no_gpu_available(self):
        agents = [_make_agent_def("gpu-agent", gpu_required=True)]
        no_gpu = GPUStatus()
        plan = schedule_crew_gpus(agents, gpu_status=no_gpu)
        assert not plan.has_errors  # non-strict falls back
        assert len(plan.warnings) == 1
        assert plan.assignments[0].device_index == -1

    def test_gpu_strict_no_gpu_errors(self):
        agents = [_make_agent_def("gpu-agent", gpu_required=True, gpu_strict=True)]
        no_gpu = GPUStatus()
        plan = schedule_crew_gpus(agents, gpu_status=no_gpu)
        assert plan.has_errors
        assert "strict" in plan.errors[0]

    def test_memory_constraint(self):
        agents = [
            _make_agent_def("big-agent", gpu_required=True, gpu_memory_min_mb=30000)
        ]
        plan = schedule_crew_gpus(agents, gpu_status=_make_gpu_status())  # 22528 free
        assert not plan.has_errors
        assert len(plan.warnings) == 1  # falls back to CPU
        assert plan.assignments[0].device_index == -1

    def test_multi_gpu_spread(self):
        agents = [
            _make_agent_def("a1", gpu_required=True),
            _make_agent_def("a2", gpu_required=True),
        ]
        status = _make_gpu_status(device_count=2)
        plan = schedule_crew_gpus(agents, gpu_status=status)
        assert len(plan.gpu_agents) == 2
        # Both should get assigned (same free memory, either order is fine)
        indices = {a.device_index for a in plan.gpu_agents}
        assert len(indices) == 2  # spread across both GPUs

    def test_gpu_preferred_with_gpu(self):
        agents = [_make_agent_def("pref", gpu_preferred=True)]
        plan = schedule_crew_gpus(agents, gpu_status=_make_gpu_status())
        assert plan.get_assignment("pref").is_gpu

    def test_gpu_preferred_without_gpu(self):
        agents = [_make_agent_def("pref", gpu_preferred=True)]
        plan = schedule_crew_gpus(agents, gpu_status=GPUStatus())
        assert not plan.get_assignment("pref").is_gpu
        assert len(plan.warnings) == 1

    def test_plan_to_dict(self):
        agents = [_make_agent_def("a1", gpu_required=True)]
        plan = schedule_crew_gpus(agents, gpu_status=_make_gpu_status())
        d = plan.to_dict()
        assert d["gpu_available"] is True
        assert d["gpu_agents_count"] == 1

    def test_preserves_original_order(self):
        agents = [
            _make_agent_def("cpu-first"),
            _make_agent_def("gpu-mid", gpu_required=True, gpu_strict=True),
            _make_agent_def("cpu-last"),
        ]
        plan = schedule_crew_gpus(agents, gpu_status=_make_gpu_status())
        keys = [a.agent_key for a in plan.assignments]
        assert keys == ["cpu-first", "gpu-mid", "cpu-last"]


# ---------------------------------------------------------------------------
# apply_gpu_assignment tests
# ---------------------------------------------------------------------------


class TestApplyGPUAssignment:
    def test_gpu_assignment(self):
        a = GPUAssignment(agent_key="a", device_index=1, cuda_visible_devices="1")
        env = apply_gpu_assignment(a)
        assert env["CUDA_VISIBLE_DEVICES"] == "1"

    def test_cpu_assignment(self):
        a = GPUAssignment(agent_key="a", device_index=-1)
        env = apply_gpu_assignment(a)
        assert env["CUDA_VISIBLE_DEVICES"] == ""


# ---------------------------------------------------------------------------
# AgentDefinition GPU fields tests
# ---------------------------------------------------------------------------


class TestAgentDefinitionGPU:
    def test_gpu_fields_in_to_dict(self):
        from agents.base import AgentDefinition

        defn = AgentDefinition(
            agent_key="gpu-agent",
            name="GPU Agent",
            role="compute",
            goal="crunch",
            backstory="fast",
            gpu_required=True,
            gpu_memory_min_mb=8000,
        )
        d = defn.to_dict()
        assert d["gpu_required"] is True
        assert d["gpu_memory_min_mb"] == 8000
        assert "gpu_strict" not in d  # default False excluded

    def test_gpu_fields_not_in_dict_when_default(self):
        from agents.base import AgentDefinition

        defn = AgentDefinition(
            agent_key="cpu-agent",
            name="CPU Agent",
            role="worker",
            goal="work",
            backstory="diligent",
        )
        d = defn.to_dict()
        assert "gpu_required" not in d
        assert "gpu_memory_min_mb" not in d

    def test_from_dict_round_trip(self):
        from agents.base import AgentDefinition

        original = AgentDefinition(
            agent_key="rt-agent",
            name="RT",
            role="r",
            goal="g",
            backstory="b",
            gpu_required=True,
            gpu_preferred=True,
            gpu_memory_min_mb=4000,
        )
        d = original.to_dict()
        restored = AgentDefinition.from_dict(d)
        assert restored.gpu_required is True
        assert restored.gpu_preferred is True
        assert restored.gpu_memory_min_mb == 4000


# ---------------------------------------------------------------------------
# agnosys probe tests
# ---------------------------------------------------------------------------


class TestAgnosysProbe:
    def test_agnosys_probe_reads_json(self, tmp_path):
        probe_file = tmp_path / "gpu.json"
        probe_file.write_text(
            json.dumps(
                {
                    "driver_version": "550.54",
                    "cuda_version": "12.4",
                    "devices": [
                        {
                            "index": 0,
                            "name": "RTX 4090",
                            "uuid": "GPU-test",
                            "memory_total_mb": 24576,
                            "memory_used_mb": 1024,
                            "memory_free_mb": 23552,
                            "utilization_pct": 10,
                            "temperature_c": 40,
                        }
                    ],
                }
            )
        )

        with patch.dict(os.environ, {"AGNOS_GPU_PROBE_PATH": str(probe_file)}):
            from config.gpu import _probe_agnosys

            status = _probe_agnosys()
            assert status is not None
            assert status.available
            assert status.devices[0].name == "RTX 4090"

    def test_agnosys_probe_missing_file(self):
        with patch.dict(os.environ, {"AGNOS_GPU_PROBE_PATH": "/nonexistent/gpu.json"}):
            from config.gpu import _probe_agnosys

            assert _probe_agnosys() is None


# ---------------------------------------------------------------------------
# Memory budget tests
# ---------------------------------------------------------------------------


class TestMemoryBudget:
    def test_budget_exceeded_by_declared_minimums(self):
        agents = [
            _make_agent_def("a1", gpu_required=True, gpu_memory_min_mb=8000),
            _make_agent_def("a2", gpu_required=True, gpu_memory_min_mb=8000),
        ]
        plan = schedule_crew_gpus(
            agents, gpu_status=_make_gpu_status(), memory_budget_mb=10000
        )
        assert plan.has_errors
        assert "budget exceeded" in plan.errors[0]

    def test_budget_within_limit(self):
        agents = [
            _make_agent_def("a1", gpu_required=True, gpu_memory_min_mb=4000),
            _make_agent_def("a2", gpu_required=True, gpu_memory_min_mb=4000),
        ]
        plan = schedule_crew_gpus(
            agents, gpu_status=_make_gpu_status(), memory_budget_mb=10000
        )
        assert not plan.has_errors
        assert len(plan.gpu_agents) == 2

    def test_budget_none_means_unlimited(self):
        agents = [
            _make_agent_def("a1", gpu_required=True, gpu_memory_min_mb=20000),
        ]
        plan = schedule_crew_gpus(
            agents, gpu_status=_make_gpu_status(), memory_budget_mb=None
        )
        assert not plan.has_errors
        assert len(plan.gpu_agents) == 1

    def test_budget_zero_means_unlimited(self):
        agents = [
            _make_agent_def("a1", gpu_required=True, gpu_memory_min_mb=20000),
        ]
        plan = schedule_crew_gpus(
            agents, gpu_status=_make_gpu_status(), memory_budget_mb=0
        )
        assert not plan.has_errors

    def test_runtime_budget_caps_later_agents(self):
        """When budget runs low during scheduling, later agents fall back to CPU."""
        agents = [
            _make_agent_def("a1", gpu_required=True, gpu_memory_min_mb=8000),
            _make_agent_def("a2", gpu_required=True, gpu_memory_min_mb=8000),
        ]
        # Budget allows first agent but not second
        plan = schedule_crew_gpus(
            agents, gpu_status=_make_gpu_status(), memory_budget_mb=9000
        )
        # Pre-check: 8000+8000=16000 > 9000 → errors
        assert plan.has_errors

    def test_budget_with_mixed_agents(self):
        agents = [
            _make_agent_def("cpu", gpu_required=False),
            _make_agent_def("gpu", gpu_required=True, gpu_memory_min_mb=4000),
        ]
        plan = schedule_crew_gpus(
            agents, gpu_status=_make_gpu_status(), memory_budget_mb=5000
        )
        assert not plan.has_errors
        assert not plan.get_assignment("cpu").is_gpu
        assert plan.get_assignment("gpu").is_gpu


# ---------------------------------------------------------------------------
# check_memory_usage tests
# ---------------------------------------------------------------------------


class TestCheckMemoryUsage:
    @patch("config.gpu.detect_gpus")
    def test_returns_usage_for_valid_device(self, mock_detect):
        mock_detect.return_value = _make_gpu_status()
        from config.gpu import check_memory_usage

        usage = check_memory_usage(0)
        assert usage is not None
        assert usage["total_mb"] == 24576
        assert usage["free_mb"] == 22528

    @patch("config.gpu.detect_gpus")
    def test_returns_none_for_missing_device(self, mock_detect):
        mock_detect.return_value = _make_gpu_status()
        from config.gpu import check_memory_usage

        assert check_memory_usage(99) is None


# ---------------------------------------------------------------------------
# GPU endpoint tests
# ---------------------------------------------------------------------------


class TestGPUEndpoints:
    @pytest.fixture()
    def client(self):
        from unittest.mock import AsyncMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from webgui.routes.gpu import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        # Override auth
        from webgui.routes.dependencies import get_current_user

        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "test",
            "role": "admin",
        }

        return TestClient(app)

    @patch("config.gpu.detect_gpus")
    def test_gpu_status_endpoint(self, mock_detect, client):
        mock_detect.return_value = _make_gpu_status()
        resp = client.get("/api/v1/gpu/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["device_count"] == 1

    @patch("config.gpu.detect_gpus")
    def test_gpu_memory_endpoint(self, mock_detect, client):
        mock_detect.return_value = _make_gpu_status()
        resp = client.get("/api/v1/gpu/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_count"] == 1
        assert data["total_mb"] == 24576
        assert len(data["devices"]) == 1

    @patch("config.gpu.detect_gpus")
    def test_gpu_device_detail_endpoint(self, mock_detect, client):
        mock_detect.return_value = _make_gpu_status()
        resp = client.get("/api/v1/gpu/devices/0")
        assert resp.status_code == 200
        assert resp.json()["name"] == "NVIDIA RTX 4090"

    @patch("config.gpu.detect_gpus")
    def test_gpu_device_not_found(self, mock_detect, client):
        mock_detect.return_value = _make_gpu_status()
        resp = client.get("/api/v1/gpu/devices/99")
        assert resp.status_code == 404

    @patch("config.gpu.detect_gpus")
    def test_gpu_slots_endpoint(self, mock_detect, client):
        mock_detect.return_value = _make_gpu_status()
        resp = client.get("/api/v1/gpu/slots")
        assert resp.status_code == 200
        data = resp.json()
        assert "tracker" in data
        assert "adjusted_free_mb" in data

    def test_gpu_inference_endpoint(self, client):
        resp = client.get("/api/v1/gpu/inference")
        assert resp.status_code == 200
        data = resp.json()
        assert "enabled" in data
        assert "models" in data


# ---------------------------------------------------------------------------
# GPU slot tracker tests
# ---------------------------------------------------------------------------


class TestGPUSlotTracker:
    def test_reserve_and_release(self):
        tracker = GPUSlotTracker()
        tracker.reserve("crew-1", 0, 4000)
        tracker.reserve("crew-1", 1, 8000)
        assert tracker.total_reserved(0) == 4000
        assert tracker.total_reserved(1) == 8000
        assert len(tracker.active_crews()) == 1

        tracker.release("crew-1")
        assert tracker.total_reserved(0) == 0
        assert tracker.total_reserved(1) == 0
        assert len(tracker.active_crews()) == 0

    def test_multiple_crews(self):
        tracker = GPUSlotTracker()
        tracker.reserve("crew-1", 0, 4000)
        tracker.reserve("crew-2", 0, 2000)
        assert tracker.total_reserved(0) == 6000
        assert len(tracker.active_crews()) == 2

        tracker.release("crew-1")
        assert tracker.total_reserved(0) == 2000

    def test_adjusted_free(self):
        tracker = GPUSlotTracker()
        tracker.reserve("crew-1", 0, 4000)
        status = _make_gpu_status()  # 22528 free on device 0
        adjusted = tracker.adjusted_free(status)
        assert adjusted[0] == 22528 - 4000

    def test_to_dict(self):
        tracker = GPUSlotTracker()
        tracker.reserve("crew-1", 0, 4000)
        d = tracker.to_dict()
        assert d["active_crews"] == 1
        assert "crew-1" in d["reservations"]

    def test_release_nonexistent_crew(self):
        tracker = GPUSlotTracker()
        tracker.release("nope")  # should not raise


# ---------------------------------------------------------------------------
# Tool GPU registration tests
# ---------------------------------------------------------------------------


class TestToolGPURegistration:
    def test_register_gpu_tool(self):
        from shared.crewai_compat import BaseTool

        from agents.tool_registry import (
            _REGISTRY,
            register_gpu_tool,
            tool_gpu_memory_min,
            tool_requires_gpu,
        )

        @register_gpu_tool(gpu_memory_min_mb=4000)
        class _TestGPUTool(BaseTool):
            name: str = "TestGPUTool"
            description: str = "A test GPU tool"

            def _run(self, **kwargs):
                return "ok"

        assert tool_requires_gpu("_TestGPUTool")
        assert tool_gpu_memory_min("_TestGPUTool") == 4000

        # Cleanup
        _REGISTRY.pop("_TestGPUTool", None)

    def test_non_gpu_tool(self):
        from agents.tool_registry import tool_gpu_memory_min, tool_requires_gpu

        assert not tool_requires_gpu("NonExistentTool")
        assert tool_gpu_memory_min("NonExistentTool") == 0

    def test_infer_gpu_from_tools(self):
        from shared.crewai_compat import BaseTool

        from agents.base import AgentDefinition, BaseAgent
        from agents.tool_registry import _REGISTRY, register_gpu_tool

        @register_gpu_tool(gpu_memory_min_mb=6000)
        class _InferTestTool(BaseTool):
            name: str = "InferTestTool"
            description: str = "GPU inference test"

            def _run(self, **kwargs):
                return "ok"

        defn = AgentDefinition(
            agent_key="infer-test",
            name="Infer Test",
            role="tester",
            goal="test",
            backstory="test",
            tools=["_InferTestTool"],
        )

        # Simulate what BaseAgent.__init__ does
        BaseAgent._infer_gpu_from_tools(defn)
        assert defn.gpu_required is True
        assert defn.gpu_memory_min_mb == 6000

        # Cleanup
        _REGISTRY.pop("_InferTestTool", None)

    def test_explicit_gpu_not_overridden(self):
        from agents.base import AgentDefinition, BaseAgent

        defn = AgentDefinition(
            agent_key="explicit-gpu",
            name="Explicit",
            role="r",
            goal="g",
            backstory="b",
            gpu_preferred=True,
            gpu_memory_min_mb=2000,
        )

        BaseAgent._infer_gpu_from_tools(defn)
        # Should not be changed since gpu_preferred is already set
        assert defn.gpu_memory_min_mb == 2000


# ---------------------------------------------------------------------------
# Local inference routing tests
# ---------------------------------------------------------------------------


class TestLocalInference:
    def test_disabled_by_default(self):
        from config.local_inference import route_inference

        route = route_inference("gpt-4o")
        assert not route.local
        assert "disabled" in route.reason

    def test_force_cloud(self):
        from config.local_inference import route_inference

        route = route_inference("gpt-4o", force_cloud=True)
        assert not route.local
        assert route.reason == "force_cloud"

    def test_model_not_in_local_list(self):
        import config.local_inference as li

        old_enabled = li._ENABLED
        li._ENABLED = True
        try:
            route = li.route_inference("gpt-4o")
            assert not route.local
            assert "not in local model list" in route.reason
        finally:
            li._ENABLED = old_enabled

    @patch("config.local_inference._gpu_has_headroom", return_value=True)
    def test_routes_to_ollama(self, mock_headroom):
        import config.local_inference as li

        old_enabled, old_models, old_provider = (
            li._ENABLED,
            li._LOCAL_MODELS,
            li._PROVIDER,
        )
        li._ENABLED = True
        li._LOCAL_MODELS = {"llama3.1:8b"}
        li._PROVIDER = "ollama"
        try:
            route = li.route_inference("llama3.1:8b")
            assert route.local
            assert route.model_name == "ollama/llama3.1:8b"
            assert route.reason == "routed_to_local"
        finally:
            li._ENABLED, li._LOCAL_MODELS, li._PROVIDER = (
                old_enabled,
                old_models,
                old_provider,
            )

    @patch("config.local_inference._gpu_has_headroom", return_value=True)
    def test_routes_to_vllm(self, mock_headroom):
        import config.local_inference as li

        old_enabled, old_models, old_provider = (
            li._ENABLED,
            li._LOCAL_MODELS,
            li._PROVIDER,
        )
        li._ENABLED = True
        li._LOCAL_MODELS = {"llama3.1:8b"}
        li._PROVIDER = "vllm"
        try:
            route = li.route_inference("llama3.1:8b")
            assert route.local
            assert route.model_name == "openai/llama3.1:8b"
        finally:
            li._ENABLED, li._LOCAL_MODELS, li._PROVIDER = (
                old_enabled,
                old_models,
                old_provider,
            )

    def test_model_too_large(self):
        import config.local_inference as li

        old_enabled, old_models = li._ENABLED, li._LOCAL_MODELS
        li._ENABLED = True
        li._LOCAL_MODELS = {"llama3:70b"}
        try:
            route = li.route_inference("llama3:70b")
            assert not route.local
            assert "too large" in route.reason
        finally:
            li._ENABLED, li._LOCAL_MODELS = old_enabled, old_models

    @patch("config.local_inference._gpu_has_headroom", return_value=False)
    def test_insufficient_vram(self, mock_headroom):
        import config.local_inference as li

        old_enabled, old_models = li._ENABLED, li._LOCAL_MODELS
        li._ENABLED = True
        li._LOCAL_MODELS = {"llama3.1:8b"}
        try:
            route = li.route_inference("llama3.1:8b")
            assert not route.local
            assert "VRAM" in route.reason
        finally:
            li._ENABLED, li._LOCAL_MODELS = old_enabled, old_models

    def test_strips_provider_prefix(self):
        import config.local_inference as li

        old_enabled, old_models = li._ENABLED, li._LOCAL_MODELS
        li._ENABLED = True
        li._LOCAL_MODELS = {"llama3.1:8b"}
        try:
            with patch("config.local_inference._gpu_has_headroom", return_value=True):
                route = li.route_inference("ollama/llama3.1:8b")
                assert route.local
        finally:
            li._ENABLED, li._LOCAL_MODELS = old_enabled, old_models

    def test_get_local_models(self):
        import config.local_inference as li

        old_models = li._LOCAL_MODELS
        li._LOCAL_MODELS = {"llama3.1:8b", "nomic-embed-text"}
        try:
            models = li.get_local_models()
            assert len(models) == 2
            names = {m["name"] for m in models}
            assert "llama3.1:8b" in names
            assert "nomic-embed-text" in names
        finally:
            li._LOCAL_MODELS = old_models

    def test_embedding_model_estimated_small(self):
        from config.local_inference import _estimate_params_b

        assert _estimate_params_b("nomic-embed-text") < 1.0
        assert _estimate_params_b("bge-reranker-v2-m3") < 1.0
