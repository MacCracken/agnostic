"""
Locust load test for the Agnostic QA Platform.

Run with:
    locust -f tests/load/locustfile.py --host http://localhost:8000

Environment variables:
    AGNOSTIC_API_KEY: API key for authentication
    LOAD_TEST_DURATION: Test duration hint (default: 60s)
"""

import json
import os

from locust import HttpUser, between, task


class AgnosticUser(HttpUser):
    """Simulates a SecureYeoman or API client interacting with Agnostic."""

    wait_time = between(1, 3)

    def on_start(self):
        self.api_key = os.getenv("AGNOSTIC_API_KEY", "test-key")
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    @task(5)
    def health_check(self):
        """High-frequency health polling (typical for orchestrators)."""
        self.client.get("/health")

    @task(3)
    def dashboard(self):
        """Dashboard data fetch."""
        self.client.get("/api/dashboard", headers=self.headers)

    @task(2)
    def agent_metrics(self):
        """Per-agent metrics."""
        self.client.get("/api/dashboard/agent-metrics", headers=self.headers)

    @task(2)
    def llm_metrics(self):
        """LLM usage metrics."""
        self.client.get("/api/dashboard/llm", headers=self.headers)

    @task(1)
    def prometheus_metrics(self):
        """Prometheus scrape endpoint."""
        self.client.get("/api/metrics", headers=self.headers)

    @task(1)
    def submit_task(self):
        """Submit a QA task (the primary write path)."""
        payload = {
            "title": "Load test QA task",
            "description": "Automated load test — verify system handles concurrent submissions",
            "priority": "medium",
            "agents": ["junior-qa"],
        }
        self.client.post(
            "/api/tasks",
            data=json.dumps(payload),
            headers=self.headers,
        )

    @task(2)
    def list_sessions(self):
        """List active sessions."""
        self.client.get("/api/dashboard/sessions", headers=self.headers)

    @task(1)
    def mcp_tools(self):
        """MCP tool discovery (SecureYeoman auto-discovery pattern)."""
        self.client.get("/api/v1/mcp/tools", headers=self.headers)

    @task(1)
    def a2a_capabilities(self):
        """A2A capability advertisement."""
        self.client.get("/api/v1/a2a/capabilities", headers=self.headers)

    @task(1)
    def a2a_heartbeat(self):
        """A2A heartbeat message."""
        payload = {
            "id": "loadtest-hb-001",
            "type": "a2a:heartbeat",
            "fromPeerId": "loadtest",
            "toPeerId": "agnostic-qa",
            "payload": {"status": "healthy"},
            "timestamp": 1700000000000,
        }
        self.client.post(
            "/api/v1/a2a/receive",
            data=json.dumps(payload),
            headers=self.headers,
        )
