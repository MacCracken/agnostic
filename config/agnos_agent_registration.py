"""
AGNOS OS Agent Registration Module

Registers Agnostic QA agents with agnosticos Agent HUD.
Phase 2 of AGNOS OS integration (ADR-022).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

logger = logging.getLogger(__name__)


AGNOSTIC_AGENTS = {
    "qa-manager": {
        "agent_id": "agnostic-qa-manager",
        "agent_name": "QA Manager",
        "agent_type": "qa",
        "description": "Coordinates multi-agent QA workflows and task distribution",
        "capabilities": ["test_planning", "task_coordination", "fuzzy_verification"],
        "resource_limits": {"cpu": "2", "memory": "2Gi"},
    },
    "senior-qa": {
        "agent_id": "agnostic-senior-qa",
        "agent_name": "Senior QA Engineer",
        "agent_type": "qa",
        "description": "Creates comprehensive test plans and edge case analysis",
        "capabilities": ["test_planning", "edge_case_analysis", "risk_assessment"],
        "resource_limits": {"cpu": "2", "memory": "3Gi"},
    },
    "junior-qa": {
        "agent_id": "agnostic-junior-qa",
        "agent_name": "Junior QA Engineer",
        "agent_type": "qa",
        "description": "Executes test cases and generates test data",
        "capabilities": ["test_execution", "test_data_generation", "regression_testing"],
        "resource_limits": {"cpu": "1.5", "memory": "2Gi"},
    },
    "qa-analyst": {
        "agent_id": "agnostic-qa-analyst",
        "agent_name": "QA Analyst",
        "agent_type": "qa",
        "description": "Analyzes test results and generates comprehensive reports",
        "capabilities": ["result_analysis", "reporting", "quality_metrics"],
        "resource_limits": {"cpu": "1.5", "memory": "2Gi"},
    },
    "security-compliance": {
        "agent_id": "agnostic-security-compliance",
        "agent_name": "Security & Compliance Officer",
        "agent_type": "security",
        "description": "Performs security audits and compliance checks",
        "capabilities": ["security_audit", "compliance_check", "vulnerability_scanning"],
        "resource_limits": {"cpu": "1.5", "memory": "2Gi"},
    },
    "performance": {
        "agent_id": "agnostic-performance",
        "agent_name": "Performance & Resilience Engineer",
        "agent_type": "performance",
        "description": "Runs load tests and validates system resilience",
        "capabilities": ["load_testing", "performance_profiling", "chaos_testing"],
        "resource_limits": {"cpu": "2", "memory": "3Gi"},
    },
}


class AgentRegistryClient:
    """Client for agnosticos Agent Registry REST API."""

    def __init__(self):
        self.enabled = os.getenv(
            "AGNOS_AGENT_REGISTRATION_ENABLED", "false"
        ).lower() == "true"
        self.base_url = os.getenv("AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090")
        self.api_key = os.getenv("AGNOS_AGENT_API_KEY", "")
        self.version = os.getenv("AGNOSTIC_VERSION", "2026.2.28")
        self._session = None
        self._registered_agents: dict[str, bool] = {}

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"X-API-Key": self.api_key})
        return self._session

    async def register_agent(self, agent_key: str) -> dict[str, Any]:
        """Register an agent with agnosticos."""
        if not self.enabled:
            logger.debug(f"Agent registration disabled, skipping {agent_key}")
            return {"status": "disabled"}

        if agent_key not in AGNOSTIC_AGENTS:
            logger.warning(f"Unknown agent key: {agent_key}")
            return {"status": "error", "message": "Unknown agent"}

        agent_config = AGNOSTIC_AGENTS[agent_key].copy()
        agent_config["version"] = self.version

        try:
            response = self.session.post(
                f"{self.base_url}/api/v1/agents/register",
                json=agent_config,
                timeout=5,
            )
            response.raise_for_status()
            self._registered_agents[agent_key] = True
            logger.info(f"Registered agent with agnosticos: {agent_key}")
            return {"status": "registered", "agent_id": agent_config["agent_id"]}
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to register agent {agent_key}: {e}")
            return {"status": "error", "message": str(e)}

    async def deregister_agent(self, agent_key: str) -> dict[str, Any]:
        """Deregister an agent from agnosticos."""
        if not self.enabled:
            return {"status": "disabled"}

        if agent_key not in AGNOSTIC_AGENTS:
            return {"status": "error", "message": "Unknown agent"}

        try:
            agent_id = AGNOSTIC_AGENTS[agent_key]["agent_id"]
            response = self.session.delete(
                f"{self.base_url}/api/v1/agents/{agent_id}", timeout=5
            )
            response.raise_for_status()
            self._registered_agents[agent_key] = False
            logger.info(f"Deregistered agent from agnosticos: {agent_key}")
            return {"status": "deregistered", "agent_id": agent_id}
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to deregister agent {agent_key}: {e}")
            return {"status": "error", "message": str(e)}

    async def send_heartbeat(
        self, agent_key: str, status: str = "idle", metadata: dict | None = None
    ) -> dict[str, Any]:
        """Send heartbeat for an agent."""
        if not self.enabled or not self._registered_agents.get(agent_key):
            return {"status": "skipped"}

        if agent_key not in AGNOSTIC_AGENTS:
            return {"status": "error", "message": "Unknown agent"}

        try:
            agent_id = AGNOSTIC_AGENTS[agent_key]["agent_id"]
            payload = {
                "agent_id": agent_id,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
            response = self.session.post(
                f"{self.base_url}/api/v1/agents/{agent_id}/heartbeat",
                json=payload,
                timeout=5,
            )
            response.raise_for_status()
            return {"status": "ok"}
        except requests.exceptions.RequestException as e:
            logger.debug(f"Heartbeat failed for {agent_key}: {e}")
            return {"status": "error", "message": str(e)}

    async def register_all_agents(self) -> dict[str, dict[str, Any]]:
        """Register all Agnostic agents."""
        results = {}
        for agent_key in AGNOSTIC_AGENTS:
            results[agent_key] = await self.register_agent(agent_key)
        return results

    async def deregister_all_agents(self) -> dict[str, dict[str, Any]]:
        """Deregister all Agnostic agents."""
        results = {}
        for agent_key in AGNOSTIC_AGENTS:
            if self._registered_agents.get(agent_key):
                results[agent_key] = await self.deregister_agent(agent_key)
        return results

    def get_registration_status(self) -> dict[str, Any]:
        """Get registration status for all agents."""
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "registered_agents": self._registered_agents,
            "total_agents": len(AGNOSTIC_AGENTS),
        }


agent_registry_client = AgentRegistryClient()
