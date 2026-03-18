"""E2E test: fleet scaling — add/remove nodes while crews execute.

Requires Docker services (Redis + multiple Agnostic containers).
Run: .venv/bin/python -m pytest tests/e2e/test_fleet_scaling.py -v

Skipped automatically if Docker services are not available.
"""

from __future__ import annotations

import os

import pytest

FLEET_TESTS_ENABLED = os.getenv("FLEET_E2E_TESTS", "false").lower() in ("true", "1")

pytestmark = pytest.mark.skipif(
    not FLEET_TESTS_ENABLED,
    reason="Fleet E2E tests require Docker (set FLEET_E2E_TESTS=true)",
)


@pytest.fixture()
def fleet_nodes():
    """Fixture that spins up multiple Agnostic containers as fleet nodes.

    TODO: Implement with docker-compose or testcontainers.
    Needs: shared Redis, 3+ Agnostic containers with AGNOS_FLEET_ENABLED=true,
    unique AGNOS_FLEET_NODE_ID per container.
    """
    pytest.skip("Fleet node fixture not yet implemented — needs Docker compose")


class TestFleetScaling:
    """Test that nodes can join/leave a fleet during crew execution."""

    def test_add_node_during_crew(self, fleet_nodes):
        """Start a crew on 2 nodes, add a 3rd mid-execution, verify completion."""

    def test_remove_node_during_crew(self, fleet_nodes):
        """Start a crew on 3 nodes, kill one mid-execution, verify re-placement."""

    def test_graceful_drain(self, fleet_nodes):
        """Deregister a node gracefully, verify its agents are re-placed."""

    def test_node_rejoin_after_failure(self, fleet_nodes):
        """Kill a node, wait for eviction, bring it back, verify it rejoins."""
