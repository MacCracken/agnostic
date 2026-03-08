# ADR-028: Runtime LLM Credential Provisioning

**Status**: Accepted
**Date**: 2026-03-08
**Authors**: Agnostic team

## Context

Agnostic supports 7 LLM providers (OpenAI, Anthropic, Google, Ollama, LM Studio, Custom, AGNOS Gateway). In standalone mode, API keys are configured via environment variables in `.env`. When orchestrated by SecureYeoman or AGNOS, requiring every Agnostic instance to store LLM keys locally creates operational burden: key rotation requires redeployment, keys are duplicated across systems, and there is no centralized audit trail for key usage.

## Decision

Introduce a **dual-mode credential system**:

1. **Standalone mode** (default): Keys come from environment variables. No behavior change.
2. **Orchestrated mode** (`CREDENTIAL_PROVISIONING_ENABLED=true`): The orchestrator (SecureYeoman/AGNOS) pushes LLM credentials at runtime via MCP tool (`agnostic_provision_credentials`) or A2A message (`a2a:provision_credentials`). Agnostic holds them in memory and LLM consumers check the in-memory store before falling back to env vars.

### Key design decisions

- **In-memory only**: Credentials are never written to disk, Redis, or the database. On process restart, the orchestrator must re-provision. This prevents credential leakage through persistence layers.
- **Call-time resolution**: `LLMIntegrationService._llm_call()` and `BaseModelProvider.chat_completion()` resolve the API key on every call, not at init time. This supports live rotation without restart.
- **Authorization gate**: Only callers authenticated via YEOMAN JWT or with admin role can provision/revoke credentials. All operations are audit-logged.
- **TTL support**: Credentials can have an optional `expires_in_seconds`. Expired credentials are lazily evicted on next access.
- **Transport security**: TLS on MCP/A2A channels handles encryption in flight. Source identity is validated via YEOMAN JWT or API key auth.

## Implementation

| Component | File | Change |
|-----------|------|--------|
| Credential store | `config/credential_store.py` | New — thread-safe in-memory store with put/get/revoke/expiry |
| Audit actions | `shared/audit.py` | Added `CREDENTIAL_PROVISIONED`, `CREDENTIAL_ROTATED`, `CREDENTIAL_REVOKED`, `CREDENTIAL_EXPIRED` |
| LLM integration | `config/llm_integration.py` | `_resolve_api_key()` checks store before env var |
| Model manager | `config/model_manager.py` | `BaseModelProvider._resolve_api_key()` + call-time resolution in OpenAI/Anthropic providers |
| MCP tools | `webgui/routes/mcp.py` | `agnostic_provision_credentials` + `agnostic_revoke_credentials` tools |
| A2A protocol | `webgui/routes/tasks.py` | `a2a:provision_credentials` + `a2a:revoke_credentials` message types |

## Consequences

### Positive
- Zero-config LLM access when orchestrated — no keys in Agnostic's `.env`
- Centralized key rotation via orchestrator (no redeployment)
- Full audit trail for credential lifecycle
- Backward compatible — disabled by default, standalone mode unchanged

### Negative
- Credentials lost on process restart (by design — orchestrator re-provisions)
- Adds a code path that must be tested alongside env-var path
- Requires trusted transport (TLS) between orchestrator and Agnostic

## AGNOS LLM Gateway Integration

When `AGNOS_LLM_GATEWAY_ENABLED=true`, the gateway becomes the **sole LLM path**:

- `ModelManager` promotes `agnos_gateway` to primary provider; agent-specific `preferred_provider` overrides are bypassed — all calls route through the gateway.
- `LLMIntegrationService` rewrites its model string to `openai/<gateway_model>` with `base_url` pointing at the gateway, and injects an `x-agent-id` header for per-agent token accounting.
- Agnostic never holds or needs any provider API key (OpenAI, Anthropic, etc.) — only `AGNOS_LLM_GATEWAY_API_KEY`.

This is the recommended end-state for AGNOS deployments. Credential provisioning (above) covers the transitional case where SecureYeoman orchestrates without full AGNOS infrastructure.

## Alternatives Considered

1. **AGNOS LLM Gateway only**: Route all LLM calls through the gateway, never hold keys. Implemented as the preferred path when AGNOS is available, but credential provisioning covers the SecureYeoman-only case.
2. **Redis-backed credential store**: Would survive restarts but introduces a persistence vector for secrets. Rejected for security reasons — credentials are intentionally ephemeral.
3. **Kubernetes Secrets injection**: Works for K8s deployments but not for Docker Compose or standalone. Credential provisioning is transport-agnostic.
