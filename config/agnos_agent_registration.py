"""
AGNOS OS Agent Registration Module

Registers Agnostic QA agents with agnosticos Agent HUD.
Phase 2 of AGNOS OS integration (ADR-022).

Phase 3 Item 7: Capability advertisement — advertises structured capability
definitions so native AGNOS agents can discover and request QA services
without direct AGNOSTIC knowledge.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from shared.version import VERSION

logger = logging.getLogger(__name__)

AGNOS_PATH_PREFIX = os.getenv("AGNOS_PATH_PREFIX", "/v1")


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
        "capabilities": [
            "test_execution",
            "test_data_generation",
            "regression_testing",
        ],
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
        "capabilities": [
            "security_audit",
            "compliance_check",
            "vulnerability_scanning",
        ],
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


# ---------------------------------------------------------------------------
# Phase 3 Item 7: Structured capability definitions
# ---------------------------------------------------------------------------
# Each entry describes a capability that AGNOSTIC can fulfill via its agents.
# AGNOS capability negotiation uses these schemas so native agents can request
# QA services without knowing AGNOSTIC internals.
# ---------------------------------------------------------------------------

CAPABILITY_DEFINITIONS: dict[str, dict] = {
    "security_audit": {
        "name": "security_audit",
        "description": "OWASP Top 10, dependency CVE scanning, auth flow analysis",
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "scope": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "findings": {"type": "array"},
                "risk_level": {"type": "string"},
            },
        },
        "agents": ["agnostic-security-compliance"],
        "estimated_duration_seconds": 300,
        "requires_auth": True,
    },
    "load_testing": {
        "name": "load_testing",
        "description": "HTTP load testing with configurable concurrency and duration",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_url": {"type": "string"},
                "concurrency": {"type": "integer"},
                "duration_seconds": {"type": "integer"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "rps": {"type": "number"},
                "p50_ms": {"type": "number"},
                "p99_ms": {"type": "number"},
                "error_rate": {"type": "number"},
            },
        },
        "agents": ["agnostic-performance"],
        "estimated_duration_seconds": 600,
        "requires_auth": True,
    },
    "compliance_check": {
        "name": "compliance_check",
        "description": "GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA compliance validation",
        "input_schema": {
            "type": "object",
            "properties": {
                "frameworks": {"type": "array", "items": {"type": "string"}},
                "scope": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "compliant": {"type": "boolean"},
                "gaps": {"type": "array"},
                "score": {"type": "number"},
            },
        },
        "agents": ["agnostic-security-compliance"],
        "estimated_duration_seconds": 180,
        "requires_auth": True,
    },
    "test_planning": {
        "name": "test_planning",
        "description": "AI-driven test plan generation from requirements",
        "input_schema": {
            "type": "object",
            "properties": {
                "requirements": {"type": "string"},
                "priority": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "test_plan": {"type": "object"},
                "scenarios": {"type": "array"},
                "estimated_effort": {"type": "string"},
            },
        },
        "agents": ["agnostic-qa-manager", "agnostic-senior-qa"],
        "estimated_duration_seconds": 120,
        "requires_auth": True,
    },
    "test_execution": {
        "name": "test_execution",
        "description": "Execute test cases and report results",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_plan_id": {"type": "string"},
                "scope": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "passed": {"type": "integer"},
                "failed": {"type": "integer"},
                "skipped": {"type": "integer"},
                "report": {"type": "object"},
            },
        },
        "agents": ["agnostic-junior-qa"],
        "estimated_duration_seconds": 300,
        "requires_auth": True,
    },
    "quality_analysis": {
        "name": "quality_analysis",
        "description": "Comprehensive quality metrics analysis and reporting",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "quality_score": {"type": "number"},
                "trends": {"type": "array"},
                "recommendations": {"type": "array"},
            },
        },
        "agents": ["agnostic-qa-analyst"],
        "estimated_duration_seconds": 120,
        "requires_auth": True,
    },
    "regression_testing": {
        "name": "regression_testing",
        "description": "Automated regression test suite execution",
        "input_schema": {
            "type": "object",
            "properties": {
                "baseline_session": {"type": "string"},
                "target_session": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "regressions": {"type": "array"},
                "new_passes": {"type": "array"},
                "diff_summary": {"type": "object"},
            },
        },
        "agents": ["agnostic-junior-qa"],
        "estimated_duration_seconds": 240,
        "requires_auth": True,
    },
    "fuzzy_verification": {
        "name": "fuzzy_verification",
        "description": "LLM-based fuzzy verification of test results against business goals",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_results": {"type": "object"},
                "business_goals": {"type": "string"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "confidence": {"type": "string"},
                "alignment": {"type": "string"},
            },
        },
        "agents": ["agnostic-qa-manager"],
        "estimated_duration_seconds": 60,
        "requires_auth": True,
    },
}


class AgentRegistryClient:
    """Client for agnosticos Agent Registry REST API."""

    def __init__(self):
        self.enabled = (
            os.getenv("AGNOS_AGENT_REGISTRATION_ENABLED", "false").lower() == "true"
        )
        self.capability_advertise_enabled = (
            os.getenv("AGNOS_CAPABILITY_ADVERTISE_ENABLED", "false").lower() == "true"
        )
        self.base_url = os.getenv("AGNOS_AGENT_REGISTRY_URL", "http://localhost:8090")
        self.api_key = os.getenv("AGNOS_AGENT_API_KEY", "")
        self.version = os.getenv("AGNOSTIC_VERSION", VERSION)
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()
        self._registered_agents: dict[str, bool] = {}
        self._capabilities_advertised: bool = False

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers={"X-API-Key": self.api_key} if self.api_key else {},
                    timeout=10.0,
                )
        return self._client

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
        # daimon expects "name", not "agent_name"
        if "agent_name" in agent_config and "name" not in agent_config:
            agent_config["name"] = agent_config.pop("agent_name")

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/agents/register",
                json=agent_config,
            )
            response.raise_for_status()
            result = response.json()
            # daimon returns a UUID; store it for heartbeats
            daimon_id = result.get("id", agent_config["agent_id"])
            self._registered_agents[agent_key] = daimon_id
            logger.info(
                "Registered agent with agnosticos: %s (daimon_id=%s)",
                agent_key,
                daimon_id,
            )
            return {
                "status": "registered",
                "agent_id": agent_config["agent_id"],
                "daimon_id": daimon_id,
            }
        except httpx.HTTPError as e:
            logger.warning(f"Failed to register agent {agent_key}: {e}")
            return {"status": "error", "message": str(e)}

    async def deregister_agent(self, agent_key: str) -> dict[str, Any]:
        """Deregister an agent from agnosticos."""
        if not self.enabled:
            return {"status": "disabled"}

        if agent_key not in AGNOSTIC_AGENTS:
            return {"status": "error", "message": "Unknown agent"}

        try:
            daimon_id = self._registered_agents.get(agent_key)
            if not daimon_id:
                return {"status": "skipped", "message": "Not registered"}
            client = await self._get_client()
            response = await client.delete(
                f"{AGNOS_PATH_PREFIX}/agents/{daimon_id}",
            )
            response.raise_for_status()
            self._registered_agents[agent_key] = None
            logger.info(f"Deregistered agent from agnosticos: {agent_key}")
            return {"status": "deregistered", "daimon_id": daimon_id}
        except httpx.HTTPError as e:
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
            daimon_id = self._registered_agents[agent_key]
            payload = {
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "metadata": metadata or {},
            }
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/agents/{daimon_id}/heartbeat",
                json=payload,
            )
            response.raise_for_status()
            return {"status": "ok"}
        except httpx.HTTPError as e:
            logger.debug(f"Heartbeat failed for {agent_key}: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Phase 3 Item 7: Capability advertisement
    # ------------------------------------------------------------------

    async def advertise_capabilities(self) -> dict[str, Any]:
        """Advertise all AGNOSTIC capability definitions to the AGNOS registry.

        Posts the full CAPABILITY_DEFINITIONS batch to the AGNOS capability
        negotiation endpoint so native AGNOS agents can discover QA services.
        """
        if not self.enabled or not self.capability_advertise_enabled:
            logger.debug("Capability advertisement disabled, skipping")
            return {"status": "disabled"}

        payload = {
            "provider": "agnostic-qa",
            "version": self.version,
            "timestamp": datetime.now(UTC).isoformat(),
            "capabilities": list(CAPABILITY_DEFINITIONS.values()),
        }

        try:
            client = await self._get_client()
            response = await client.post(
                f"{AGNOS_PATH_PREFIX}/capabilities/advertise",
                json=payload,
            )
            response.raise_for_status()
            self._capabilities_advertised = True
            logger.info(
                "Advertised %d capabilities to AGNOS",
                len(CAPABILITY_DEFINITIONS),
            )
            return {
                "status": "advertised",
                "capabilities": list(CAPABILITY_DEFINITIONS.keys()),
                "count": len(CAPABILITY_DEFINITIONS),
            }
        except httpx.HTTPError as e:
            logger.warning(f"Failed to advertise capabilities: {e}")
            return {"status": "error", "message": str(e)}

    async def withdraw_capabilities(self) -> dict[str, Any]:
        """Withdraw all AGNOSTIC capabilities from the AGNOS registry."""
        if not self.enabled or not self.capability_advertise_enabled:
            return {"status": "disabled"}

        try:
            client = await self._get_client()
            response = await client.delete(
                f"{AGNOS_PATH_PREFIX}/capabilities/agnostic-qa",
            )
            response.raise_for_status()
            self._capabilities_advertised = False
            logger.info("Withdrew capabilities from AGNOS")
            return {"status": "withdrawn"}
        except httpx.HTTPError as e:
            logger.warning(f"Failed to withdraw capabilities: {e}")
            return {"status": "error", "message": str(e)}

    async def handle_capability_request(
        self, capability_name: str, params: dict
    ) -> dict[str, Any]:
        """Handle an inbound capability request routed by AGNOS.

        Validates the requested capability exists and returns a task
        submission acknowledgment that AGNOS can use to track execution.

        Args:
            capability_name: The capability being requested (must be a key
                in CAPABILITY_DEFINITIONS).
            params: Parameters for the capability, validated against the
                capability's input_schema at the caller's discretion.

        Returns:
            Acknowledgment dict with task_id placeholder and capability
            metadata, or an error dict if the capability is unknown.
        """
        if capability_name not in CAPABILITY_DEFINITIONS:
            logger.warning(f"Unknown capability requested: {capability_name}")
            return {
                "status": "error",
                "message": f"Unknown capability: {capability_name}",
                "available_capabilities": list(CAPABILITY_DEFINITIONS.keys()),
            }

        capability = CAPABILITY_DEFINITIONS[capability_name]
        task_id = (
            f"agnostic-{capability_name}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
        )

        logger.info(
            "Accepted capability request: %s (task_id=%s)",
            capability_name,
            task_id,
        )

        return {
            "status": "accepted",
            "task_id": task_id,
            "capability": capability_name,
            "assigned_agents": capability["agents"],
            "estimated_duration_seconds": capability["estimated_duration_seconds"],
            "params": params,
        }

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    async def register_all_agents(self) -> dict[str, dict[str, Any]]:
        """Register all Agnostic agents, advertise capabilities, and register RPC methods."""
        agent_keys = list(AGNOSTIC_AGENTS.keys())
        agent_results = await asyncio.gather(
            *[self.register_agent(k) for k in agent_keys]
        )
        results: dict[str, dict[str, Any]] = dict(zip(agent_keys, agent_results, strict=False))

        # After all agents are registered, advertise capabilities
        results["capabilities"] = await self.advertise_capabilities()

        # Register RPC methods with daimon for cross-agent invocation
        try:
            from shared.agnos_rpc_client import agnos_rpc

            rpc_results = await agnos_rpc.register_all_agent_methods(
                self._registered_agents
            )
            results["rpc_methods"] = rpc_results
        except Exception as e:
            logger.warning("RPC method registration failed: %s", e)
            results["rpc_methods"] = {"status": "error", "message": str(e)}

        return results

    async def deregister_all_agents(self) -> dict[str, dict[str, Any]]:
        """Deregister all Agnostic agents, withdraw capabilities, and clear RPC methods."""
        results: dict[str, dict[str, Any]] = {}

        # Clear RPC method registrations (daimon auto-deregisters on agent removal)
        try:
            from shared.agnos_rpc_client import agnos_rpc

            await agnos_rpc.deregister_all_methods()
        except Exception as e:
            logger.debug("RPC method deregistration: %s", e)

        # Withdraw capabilities before deregistering agents
        if self._capabilities_advertised:
            results["capabilities"] = await self.withdraw_capabilities()

        keys_to_deregister = [
            k for k in AGNOSTIC_AGENTS if self._registered_agents.get(k)
        ]
        deregister_results = await asyncio.gather(
            *[self.deregister_agent(k) for k in keys_to_deregister]
        )
        results.update(dict(zip(keys_to_deregister, deregister_results, strict=False)))
        return results

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def get_registration_status(self) -> dict[str, Any]:
        """Get registration status for all agents."""
        rpc_registered: dict[str, list[str]] = {}
        try:
            from shared.agnos_rpc_client import agnos_rpc

            rpc_registered = agnos_rpc._registered_methods
        except ImportError:
            pass

        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "registered_agents": self._registered_agents,
            "total_agents": len(AGNOSTIC_AGENTS),
            "capability_advertise_enabled": self.capability_advertise_enabled,
            "capabilities_advertised": self._capabilities_advertised,
            "total_capabilities": len(CAPABILITY_DEFINITIONS),
            "rpc_methods_registered": rpc_registered,
        }


agent_registry_client = AgentRegistryClient()
