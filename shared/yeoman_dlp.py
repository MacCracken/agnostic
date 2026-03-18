"""DLP (Data Loss Prevention) integration with SecureYeoman.

Before crew results are returned to the caller, they can optionally be
routed through SecureYeoman's DLP pipeline to scan for sensitive data
(PII, credentials, secrets, regulated data).

If DLP flags content, the crew result is sanitized and the finding is
logged to the audit trail.

Environment variables
---------------------
YEOMAN_DLP_ENABLED
    Enable DLP scanning of crew output. Default ``false``.
YEOMAN_DLP_URL
    SecureYeoman DLP endpoint. Default ``http://localhost:18789/api/v1/dlp/scan``.
YEOMAN_DLP_API_KEY
    API key for the DLP endpoint.
YEOMAN_DLP_BLOCK_ON_FINDING
    If ``true``, block (redact) crew output when DLP finds sensitive data.
    If ``false`` (default), warn but still return the output.
YEOMAN_DLP_TIMEOUT
    Timeout for DLP requests in seconds. Default ``10``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DLP_ENABLED = os.getenv("YEOMAN_DLP_ENABLED", "false").lower() in ("true", "1", "yes")
_DLP_URL = os.getenv("YEOMAN_DLP_URL", "http://localhost:18789/api/v1/dlp/scan")
_DLP_API_KEY = os.getenv("YEOMAN_DLP_API_KEY", "")
_DLP_BLOCK = os.getenv("YEOMAN_DLP_BLOCK_ON_FINDING", "false").lower() in (
    "true",
    "1",
    "yes",
)
_DLP_TIMEOUT = int(os.getenv("YEOMAN_DLP_TIMEOUT", "10"))


async def scan_crew_output(
    crew_id: str,
    results: dict[str, Any],
) -> dict[str, Any]:
    """Scan crew output through SY's DLP pipeline.

    Returns the (possibly sanitized) results dict. If DLP is disabled
    or unavailable, returns the results unchanged.
    """
    if not _DLP_ENABLED:
        return results

    try:
        import httpx
    except ImportError:
        logger.debug("httpx not available — DLP scan skipped")
        return results

    payload = {
        "source": "agnostic_crew",
        "source_id": crew_id,
        "content": json.dumps(results, default=str),
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _DLP_API_KEY:
        headers["X-API-Key"] = _DLP_API_KEY

    try:
        async with httpx.AsyncClient(timeout=_DLP_TIMEOUT) as client:
            resp = await client.post(_DLP_URL, json=payload, headers=headers)

        if resp.status_code != 200:
            logger.warning(
                "DLP scan returned %d for crew %s — passing through",
                resp.status_code,
                crew_id,
            )
            return results

        dlp_result = resp.json()
        findings = dlp_result.get("findings", [])

        if not findings:
            logger.debug("DLP scan clean for crew %s", crew_id)
            return results

        logger.warning(
            "DLP found %d issue(s) in crew %s output: %s",
            len(findings),
            crew_id,
            ", ".join(f.get("category", "unknown") for f in findings),
        )

        # Attach findings metadata to results
        results["_dlp"] = {
            "scanned": True,
            "findings_count": len(findings),
            "categories": list({f.get("category", "unknown") for f in findings}),
        }

        if _DLP_BLOCK:
            # Redact the agent results — replace with DLP notice
            sanitized = dlp_result.get("sanitized_content")
            if sanitized:
                try:
                    results["agent_results"] = json.loads(sanitized).get(
                        "agent_results", results.get("agent_results")
                    )
                except (json.JSONDecodeError, AttributeError):
                    pass
            results["_dlp"]["blocked"] = True
            logger.info("DLP blocked/redacted crew %s output", crew_id)

        return results

    except Exception as exc:
        logger.warning(
            "DLP scan failed for crew %s: %s — passing through", crew_id, exc
        )
        return results


def is_enabled() -> bool:
    """Whether DLP scanning is enabled."""
    return _DLP_ENABLED
