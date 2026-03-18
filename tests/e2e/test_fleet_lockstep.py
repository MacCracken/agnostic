"""E2E test: multi-node lockstep crew execution.

Spins up 3+ fleet nodes (Docker containers), runs a crew that spans all,
and verifies lockstep ordering, fault recovery, and output correctness.

Requires Docker services.
Run: .venv/bin/python -m pytest tests/e2e/test_fleet_lockstep.py -v
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
def fleet_cluster():
    """Fixture that creates a 3-node fleet cluster.

    TODO: Implement with docker-compose or testcontainers.
    Needs: shared Redis, 3 Agnostic containers, each with unique node ID
    and AGNOS_FLEET_ENABLED=true.
    """
    pytest.skip("Fleet cluster fixture not yet implemented — needs Docker compose")


class TestFleetLockstepCrew:
    """Verify distributed crew execution across multiple fleet nodes."""

    def test_crew_spans_all_nodes(self, fleet_cluster):
        """Submit a 6-agent crew to a 3-node fleet.

        Verify that agents are distributed across nodes (not all local).
        """

    def test_lockstep_ordering(self, fleet_cluster):
        """Verify barrier synchronization — Agent B doesn't start until
        Agent A commits its output.
        """

    def test_coordinator_failover(self, fleet_cluster):
        """Kill the coordinator node mid-crew. Verify another node promotes
        itself and the crew completes from checkpointed state.
        """

    def test_result_aggregation(self, fleet_cluster):
        """Submit a crew, wait for completion. Verify the aggregated result
        contains output from all agents regardless of which node ran them.
        """

    def test_group_pinning(self, fleet_cluster):
        """Submit a crew with group='test-group'. Verify all agents run
        on nodes in that group only.
        """

    def test_gpu_affinity_across_fleet(self, fleet_cluster):
        """Submit a crew with GPU-requiring agents. Verify they are placed
        on GPU-capable nodes.
        """
