"""
YEOMAN MCP Server Auto-Registration.

On startup, registers AGNOSTIC as an MCP server with SecureYeoman so that
AGNOSTIC's QA tools appear automatically in the SecureYeoman MCP tab.

Configure via:
- YEOMAN_MCP_AUTO_REGISTER: Enable auto-registration (default: false)
- YEOMAN_MCP_URL: SecureYeoman core API base URL (default: http://localhost:18789)
- YEOMAN_MCP_API_KEY: API key for SecureYeoman core
- AGNOSTIC_EXTERNAL_URL: How SecureYeoman reaches AGNOSTIC (default: http://localhost:8000)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_YEOMAN_CORE_URL = "http://localhost:18789"
_DEFAULT_AGNOSTIC_URL = "http://localhost:8000"
_REQUEST_TIMEOUT = 15.0
_SERVER_NAME = "agnostic-qa"
_SERVER_DESCRIPTION = (
    "AGNOSTIC 6-Agent QA Platform — security audits, performance testing, "
    "regression testing, compliance scanning, and comprehensive QA reports."
)

# Tool manifest: import from the canonical source (webgui/routes/mcp.py).
# Falls back to a minimal manifest when FastAPI route module is unavailable
# (e.g. agent containers that don't ship webgui).
def _load_tool_manifest() -> list[dict[str, Any]]:
    try:
        from webgui.routes.mcp import MCP_TOOLS

        return MCP_TOOLS
    except Exception:
        # Minimal fallback — enough for registration handshake
        return [
            {
                "name": "agnostic_submit_task",
                "description": "Submit a QA task to the 6-agent pipeline",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["title", "description"],
                },
            },
            {
                "name": "agnostic_dashboard",
                "description": "Get aggregated QA dashboard metrics",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "agnostic_health",
                "description": "Check if AGNOSTIC QA platform is reachable and healthy",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]


TOOL_MANIFEST: list[dict[str, Any]] = _load_tool_manifest()


class YeomanMcpRegistration:
    """Handles auto-registration of AGNOSTIC as an MCP server with SecureYeoman."""

    def __init__(self) -> None:
        self.enabled: bool = os.getenv(
            "YEOMAN_MCP_AUTO_REGISTER", "false"
        ).lower() in ("true", "1", "yes")
        self.yeoman_url: str = os.getenv(
            "YEOMAN_MCP_URL", _DEFAULT_YEOMAN_CORE_URL
        ).rstrip("/")
        self.api_key: str | None = os.getenv("YEOMAN_MCP_API_KEY")
        self.agnostic_url: str = os.getenv(
            "AGNOSTIC_EXTERNAL_URL", _DEFAULT_AGNOSTIC_URL
        ).rstrip("/")
        self._server_id: str | None = None
        self._client: httpx.AsyncClient | None = None  # type: ignore[name-defined]

    def _get_client(self) -> httpx.AsyncClient:  # type: ignore[name-defined]
        if not _HTTPX_AVAILABLE:
            raise RuntimeError("httpx is not installed")
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            self._client = httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT, headers=headers
            )
        return self._client

    async def register(self) -> bool:
        """Register AGNOSTIC as an MCP server with SecureYeoman.

        POSTs to ``/api/v1/mcp/servers`` with the tool manifest.
        Returns True on success.
        """
        if not self.enabled:
            logger.debug("YEOMAN MCP auto-registration disabled")
            return False

        url = f"{self.yeoman_url}/api/v1/mcp/servers"
        payload = {
            "name": _SERVER_NAME,
            "description": _SERVER_DESCRIPTION,
            "transport": "http",
            "url": self.agnostic_url,
            "tools": TOOL_MANIFEST,
            "enabled": True,
            "metadata": {
                "provider": "agnostic-qa",
                "version": os.getenv("AGNOSTIC_VERSION", "2026.3.5"),
                "capabilities": [
                    "security-audit",
                    "performance-test",
                    "regression-test",
                    "compliance-scan",
                    "qa-report",
                ],
            },
        }

        try:
            client = self._get_client()
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            self._server_id = data.get("id") or data.get("server_id")
            logger.info(
                "Registered AGNOSTIC as MCP server with SecureYeoman (id=%s)",
                self._server_id,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Failed to register AGNOSTIC as MCP server with SecureYeoman: %s",
                exc,
            )
            return False

    async def deregister(self) -> bool:
        """Remove AGNOSTIC from SecureYeoman's MCP server list."""
        if not self.enabled or not self._server_id:
            return False

        url = f"{self.yeoman_url}/api/v1/mcp/servers/{self._server_id}"
        try:
            client = self._get_client()
            resp = await client.delete(url)
            resp.raise_for_status()
            logger.info("Deregistered AGNOSTIC MCP server (id=%s)", self._server_id)
            self._server_id = None
            return True
        except Exception as exc:
            logger.warning("Failed to deregister AGNOSTIC MCP server: %s", exc)
            return False

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Module-level singleton
yeoman_mcp_registration = YeomanMcpRegistration()
