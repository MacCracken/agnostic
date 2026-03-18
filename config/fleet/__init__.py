"""Fleet coordination for distributed Agnostic instances.

Provides node registration, heartbeat, group management, placement,
inter-node relay, coordinator election, and unified crew state so that
multiple Agnostic instances can operate as a single distributed crew
execution fabric.
"""

from config.fleet.node import FleetNode, NodeCapabilities
from config.fleet.placement import PlacementPlan, place_agents
from config.fleet.registry import FleetRegistry, fleet_registry
from config.fleet.relay import RelayMessage, TaskRelay, task_relay
from config.fleet.state import (
    AgentPlacement,
    CrewState,
    CrewStateManager,
    crew_state_manager,
)

__all__ = [
    "AgentPlacement",
    "CrewState",
    "CrewStateManager",
    "FleetNode",
    "FleetRegistry",
    "NodeCapabilities",
    "PlacementPlan",
    "RelayMessage",
    "TaskRelay",
    "crew_state_manager",
    "fleet_registry",
    "place_agents",
    "task_relay",
]
