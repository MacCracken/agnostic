"""Fleet coordination for distributed Agnostic instances.

Provides node registration, heartbeat, group management, and unified
crew state so that multiple Agnostic instances can operate as a single
distributed crew execution fabric.
"""

from config.fleet.node import FleetNode, NodeCapabilities
from config.fleet.registry import FleetRegistry, fleet_registry
from config.fleet.state import CrewState, crew_state_manager

__all__ = [
    "CrewState",
    "FleetNode",
    "FleetRegistry",
    "NodeCapabilities",
    "crew_state_manager",
    "fleet_registry",
]
