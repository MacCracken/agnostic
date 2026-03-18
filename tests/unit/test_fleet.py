"""Tests for fleet node, registry, and crew state modules."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.fleet.node import FleetNode, NodeCapabilities
from config.fleet.state import AgentPlacement, CrewState, CrewStateManager


# ---------------------------------------------------------------------------
# NodeCapabilities tests
# ---------------------------------------------------------------------------


class TestNodeCapabilities:
    def test_to_dict(self):
        caps = NodeCapabilities(cpu_cores=8, ram_total_mb=16384, gpu_count=1)
        d = caps.to_dict()
        assert d["cpu_cores"] == 8
        assert d["gpu_count"] == 1

    def test_from_dict(self):
        caps = NodeCapabilities.from_dict(
            {"cpu_cores": 4, "ram_total_mb": 8192, "gpu_count": 0}
        )
        assert caps.cpu_cores == 4
        assert caps.gpu_count == 0

    def test_from_dict_ignores_unknown_fields(self):
        caps = NodeCapabilities.from_dict({"cpu_cores": 2, "unknown_field": "ignore"})
        assert caps.cpu_cores == 2

    def test_probe_local(self):
        caps = NodeCapabilities.probe_local()
        assert caps.cpu_cores > 0
        assert caps.python_version != ""


# ---------------------------------------------------------------------------
# FleetNode tests
# ---------------------------------------------------------------------------


class TestFleetNode:
    def test_to_dict_round_trip(self):
        node = FleetNode(
            node_id="test-1",
            group="gpu-rack",
            external_url="http://test:8000",
            capabilities=NodeCapabilities(cpu_cores=4, gpu_count=1),
            last_heartbeat=time.time(),
            registered_at=time.time(),
        )
        d = node.to_dict()
        assert d["node_id"] == "test-1"
        assert d["group"] == "gpu-rack"
        assert d["has_gpu"] is True

        restored = FleetNode.from_dict(d)
        assert restored.node_id == "test-1"
        assert restored.capabilities.gpu_count == 1

    def test_is_alive(self):
        node = FleetNode(
            node_id="alive",
            last_heartbeat=time.time(),
        )
        assert node.is_alive

        dead_node = FleetNode(
            node_id="dead",
            last_heartbeat=time.time() - 60,
        )
        assert not dead_node.is_alive

    def test_has_gpu(self):
        gpu_node = FleetNode(
            node_id="gpu",
            capabilities=NodeCapabilities(gpu_count=2),
        )
        assert gpu_node.has_gpu

        cpu_node = FleetNode(
            node_id="cpu",
            capabilities=NodeCapabilities(gpu_count=0),
        )
        assert not cpu_node.has_gpu

    def test_local(self):
        node = FleetNode.local()
        assert node.node_id != ""
        assert node.capabilities.cpu_cores > 0
        assert node.is_alive


# ---------------------------------------------------------------------------
# AgentPlacement tests
# ---------------------------------------------------------------------------


class TestAgentPlacement:
    def test_to_dict_round_trip(self):
        p = AgentPlacement(
            agent_key="test-agent",
            node_id="node-1",
            device_index=0,
            status="running",
        )
        d = p.to_dict()
        restored = AgentPlacement.from_dict(d)
        assert restored.agent_key == "test-agent"
        assert restored.node_id == "node-1"
        assert restored.device_index == 0


# ---------------------------------------------------------------------------
# CrewState tests
# ---------------------------------------------------------------------------


class TestCrewState:
    def test_to_dict_round_trip(self):
        state = CrewState(
            crew_id="crew-1",
            coordinator_node_id="node-1",
            status="running",
            barrier_seq=3,
            placements=[
                AgentPlacement(agent_key="a1", node_id="node-1"),
                AgentPlacement(agent_key="a2", node_id="node-2", device_index=0),
            ],
            created_at=time.time(),
        )
        d = state.to_dict()
        assert d["crew_id"] == "crew-1"
        assert len(d["placements"]) == 2

        restored = CrewState.from_dict(d)
        assert restored.crew_id == "crew-1"
        assert len(restored.placements) == 2
        assert restored.placements[1].device_index == 0

    def test_get_placement(self):
        state = CrewState(
            crew_id="crew-1",
            placements=[
                AgentPlacement(agent_key="a1", node_id="n1"),
                AgentPlacement(agent_key="a2", node_id="n2"),
            ],
        )
        assert state.get_placement("a1").node_id == "n1"
        assert state.get_placement("a2").node_id == "n2"
        assert state.get_placement("missing") is None


# ---------------------------------------------------------------------------
# CrewStateManager tests
# ---------------------------------------------------------------------------


class TestCrewStateManager:
    def _mock_redis(self):
        """Create a mock async Redis client with dict-backed storage."""
        storage = {}
        hash_storage = {}

        client = AsyncMock()

        async def _setex(key, ttl, value):
            storage[key] = value

        async def _get(key):
            return storage.get(key)

        async def _delete(*keys):
            for k in keys:
                storage.pop(k, None)
                hash_storage.pop(k, None)

        async def _hset(key, field, value):
            hash_storage.setdefault(key, {})[field] = value

        async def _hget(key, field):
            return hash_storage.get(key, {}).get(field)

        async def _incr(key):
            val = int(storage.get(key, "0")) + 1
            storage[key] = str(val)
            return val

        async def _expire(key, ttl):
            pass

        client.setex = _setex
        client.get = _get
        client.delete = _delete
        client.hset = _hset
        client.hget = _hget
        client.incr = _incr
        client.expire = _expire

        return client

    @pytest.mark.asyncio
    async def test_create_and_get(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        placements = [
            AgentPlacement(agent_key="a1", node_id="node-1"),
            AgentPlacement(agent_key="a2", node_id="node-2"),
        ]

        state = await mgr.create("crew-1", "node-1", placements, redis_client=client)
        assert state.crew_id == "crew-1"
        assert state.coordinator_node_id == "node-1"
        assert len(state.placements) == 2

        fetched = await mgr.get("crew-1", redis_client=client)
        assert fetched is not None
        assert fetched.crew_id == "crew-1"

    @pytest.mark.asyncio
    async def test_update_agent_status(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        placements = [AgentPlacement(agent_key="a1", node_id="node-1")]
        await mgr.create("crew-1", "node-1", placements, redis_client=client)

        ok = await mgr.update_agent_status(
            "crew-1",
            "a1",
            "completed",
            result={"output": "done"},
            redis_client=client,
        )
        assert ok

        state = await mgr.get("crew-1", redis_client=client)
        assert state.placements[0].status == "completed"

    @pytest.mark.asyncio
    async def test_barrier(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        placements = [AgentPlacement(agent_key="a1", node_id="n1")]
        await mgr.create("crew-1", "n1", placements, redis_client=client)

        seq = await mgr.get_barrier("crew-1", redis_client=client)
        assert seq == 0

        new_seq = await mgr.advance_barrier("crew-1", redis_client=client)
        assert new_seq == 1

        new_seq = await mgr.advance_barrier("crew-1", redis_client=client)
        assert new_seq == 2

    @pytest.mark.asyncio
    async def test_checkpoint(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        placements = [AgentPlacement(agent_key="a1", node_id="n1")]
        await mgr.create("crew-1", "n1", placements, redis_client=client)

        await mgr.checkpoint_agent(
            "crew-1", "a1", {"step": 3, "partial": "data"}, redis_client=client
        )

        cp = await mgr.get_checkpoint("crew-1", "a1", redis_client=client)
        assert cp is not None
        assert cp["step"] == 3

    @pytest.mark.asyncio
    async def test_coordinator_transfer(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        placements = [AgentPlacement(agent_key="a1", node_id="n1")]
        await mgr.create("crew-1", "n1", placements, redis_client=client)

        await mgr.set_coordinator("crew-1", "n2", redis_client=client)

        state = await mgr.get("crew-1", redis_client=client)
        assert state.coordinator_node_id == "n2"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        result = await mgr.get("does-not-exist", redis_client=client)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self):
        mgr = CrewStateManager()
        client = self._mock_redis()

        placements = [AgentPlacement(agent_key="a1", node_id="n1")]
        await mgr.create("crew-1", "n1", placements, redis_client=client)

        await mgr.delete("crew-1", redis_client=client)

        result = await mgr.get("crew-1", redis_client=client)
        assert result is None


# ---------------------------------------------------------------------------
# Fleet endpoint tests
# ---------------------------------------------------------------------------


class TestFleetEndpoints:
    @pytest.fixture()
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from webgui.routes.dependencies import get_current_user
        from webgui.routes.fleet import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_current_user] = lambda: {
            "user_id": "test",
            "role": "admin",
        }
        return TestClient(app)

    def test_fleet_disabled(self, client):
        """Endpoints return 503 when fleet is disabled."""
        resp = client.get("/api/v1/fleet/status")
        assert resp.status_code == 503
        assert "not enabled" in resp.json()["detail"]

    @patch("config.fleet.node.FLEET_ENABLED", True)
    @patch("config.fleet.registry.fleet_registry")
    def test_fleet_status(self, mock_registry, client):
        mock_registry.local_node = None

        async def _get_all(redis_client=None):
            return [
                FleetNode(
                    node_id="n1",
                    capabilities=NodeCapabilities(
                        cpu_cores=4,
                        gpu_count=1,
                        gpu_vram_total_mb=8000,
                        gpu_vram_free_mb=6000,
                    ),
                    last_heartbeat=time.time(),
                )
            ]

        mock_registry.get_all_nodes = _get_all
        resp = client.get("/api/v1/fleet/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["total_nodes"] == 1
        assert data["total_gpus"] == 1


# ---------------------------------------------------------------------------
# Placement engine tests
# ---------------------------------------------------------------------------


class TestPlacementEngine:
    def _make_nodes(self) -> list[FleetNode]:
        return [
            FleetNode(
                node_id="gpu-1",
                group="gpu-rack",
                capabilities=NodeCapabilities(
                    cpu_cores=8,
                    gpu_count=2,
                    gpu_vram_total_mb=48000,
                    gpu_vram_free_mb=40000,
                ),
                last_heartbeat=time.time(),
            ),
            FleetNode(
                node_id="cpu-1",
                group="cpu-rack",
                capabilities=NodeCapabilities(cpu_cores=16),
                last_heartbeat=time.time(),
            ),
            FleetNode(
                node_id="cpu-2",
                group="cpu-rack",
                capabilities=NodeCapabilities(cpu_cores=8),
                last_heartbeat=time.time(),
            ),
        ]

    def _make_defs(self) -> list[dict]:
        return [
            {"agent_key": "gpu-agent", "gpu_required": True, "gpu_memory_min_mb": 8000},
            {"agent_key": "cpu-agent-1"},
            {"agent_key": "cpu-agent-2"},
        ]

    def test_gpu_affinity(self):
        from config.fleet.placement import place_agents

        plan = place_agents(
            self._make_defs(), self._make_nodes(), policy="gpu-affinity"
        )
        assert not plan.has_errors
        assert len(plan.placements) == 3
        gpu_placement = next(p for p in plan.placements if p.agent_key == "gpu-agent")
        assert gpu_placement.node_id == "gpu-1"

    def test_balanced(self):
        from config.fleet.placement import place_agents

        plan = place_agents(self._make_defs(), self._make_nodes(), policy="balanced")
        assert not plan.has_errors
        node_ids = {p.node_id for p in plan.placements}
        assert len(node_ids) == 3  # spread across all 3 nodes

    def test_lockstep_strict(self):
        from config.fleet.placement import place_agents

        plan = place_agents(
            self._make_defs(), self._make_nodes(), policy="lockstep-strict"
        )
        assert not plan.has_errors
        gpu_p = next(p for p in plan.placements if p.agent_key == "gpu-agent")
        assert gpu_p.node_id == "gpu-1"
        # CPU agents co-located on most capable node
        cpu_nodes = {
            p.node_id for p in plan.placements if not p.agent_key.startswith("gpu")
        }
        assert len(cpu_nodes) == 1

    def test_cost_aware(self):
        from config.fleet.placement import place_agents

        plan = place_agents(self._make_defs(), self._make_nodes(), policy="cost-aware")
        assert not plan.has_errors
        gpu_p = next(p for p in plan.placements if p.agent_key == "gpu-agent")
        assert gpu_p.node_id == "gpu-1"
        # CPU agents should prefer non-GPU nodes
        cpu_placements = [
            p for p in plan.placements if not p.agent_key.startswith("gpu")
        ]
        assert all(p.node_id != "gpu-1" for p in cpu_placements)

    def test_group_filter(self):
        from config.fleet.placement import place_agents

        defs = [{"agent_key": "a1"}, {"agent_key": "a2"}]
        plan = place_agents(defs, self._make_nodes(), group="cpu-rack")
        assert not plan.has_errors
        assert all(p.node_id in ("cpu-1", "cpu-2") for p in plan.placements)

    def test_no_nodes(self):
        from config.fleet.placement import place_agents

        plan = place_agents([{"agent_key": "a1"}], [])
        assert plan.has_errors

    def test_no_gpu_nodes_fallback(self):
        from config.fleet.placement import place_agents

        cpu_only = [
            FleetNode(
                node_id="cpu-1",
                capabilities=NodeCapabilities(cpu_cores=4),
                last_heartbeat=time.time(),
            )
        ]
        defs = [{"agent_key": "gpu-agent", "gpu_required": True}]
        plan = place_agents(defs, cpu_only, policy="gpu-affinity")
        assert not plan.has_errors
        assert len(plan.warnings) == 1
        assert plan.placements[0].node_id == "cpu-1"


# ---------------------------------------------------------------------------
# Relay message tests
# ---------------------------------------------------------------------------


class TestTaskRelay:
    def test_relay_message_round_trip(self):
        from config.fleet.relay import RelayMessage

        msg = RelayMessage(
            crew_id="crew-1",
            agent_key="a1",
            source_node="n1",
            target_node="n2",
            seq=1,
            msg_type="task_handoff",
            payload={"task": "do stuff"},
        )
        json_str = msg.to_json()
        restored = RelayMessage.from_json(json_str)
        assert restored.crew_id == "crew-1"
        assert restored.seq == 1
        assert restored.payload["task"] == "do stuff"

    def test_dedup(self):
        from config.fleet.relay import TaskRelay

        relay = TaskRelay()
        assert not relay._is_duplicate("crew-1", 1)
        assert relay._is_duplicate("crew-1", 1)  # second time = duplicate
        assert not relay._is_duplicate("crew-1", 2)

    def test_seq_counter(self):
        from config.fleet.relay import TaskRelay

        relay = TaskRelay()
        assert relay._next_seq("crew-1") == 1
        assert relay._next_seq("crew-1") == 2
        assert relay._next_seq("crew-2") == 1  # independent per crew

    def test_cleanup(self):
        from config.fleet.relay import TaskRelay

        relay = TaskRelay()
        relay._next_seq("crew-1")
        relay._is_duplicate("crew-1", 1)
        relay.cleanup("crew-1")
        assert "crew-1" not in relay._seen_seqs
        assert "crew-1" not in relay._seq_counter


# ---------------------------------------------------------------------------
# Coordinator tests
# ---------------------------------------------------------------------------


class TestFleetCoordinator:
    def test_submit_result(self):
        from config.fleet.coordinator import FleetCoordinator

        coord = FleetCoordinator("crew-1", node_id="n1")
        coord._expected_agents = {"a1", "a2"}
        coord.submit_result("a1", {"status": "completed", "output": "done"})
        assert "a1" in coord._results
        assert coord._results["a1"]["status"] == "completed"
