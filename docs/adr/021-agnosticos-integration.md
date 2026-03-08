# ADR-021: AGNOS OS Integration

**Status**: Accepted
**Date**: 2026-02-22
**Authors**: AGNOS / Agnostic teams

---

## Context

Agnostic is designed to run as a QA platform on top of the **AGNOS OS** (`agnosticos` repository) — an AI-native Linux-based operating system that provides:

- **LLM Gateway** (`agnosticos/userland/llm-gateway`): A Rust daemon that brokers LLM inference across Ollama, llama.cpp, OpenAI, and Anthropic with per-agent token accounting, rate limiting, caching, and model sharing.
- **Agent Runtime** (`agnosticos/userland/agent-runtime`): An agent lifecycle daemon (akd) that manages agent processes, sandboxing (Landlock, seccomp-bpf, namespaces), and IPC.
- **AI Shell** (`agnosticos/userland/ai-shell`): Natural language shell with human oversight.
- **Security Layer**: Mandatory Landlock filesystem sandboxing and seccomp-bpf syscall filtering applied to all processes including Docker containers.

Without integration, Agnostic bypasses these services and calls LLM providers directly. This misses out on OS-level token accounting, shared model caching across agents, rate limiting, and the unified security audit trail that agnosticos provides.

---

## Decision

Agnostic will support routing all LLM inference calls through the AGNOS LLM Gateway when running on agnosticos, controlled by environment flags. The integration is **opt-in and non-breaking** — existing deployments on standard Linux/Docker continue to work unchanged.

### Integration Points

#### 1. LLM Gateway (Primary)

The AGNOS LLM Gateway exposes an **OpenAI-compatible REST API** at port `8088`:

```
POST http://localhost:8088/v1/chat/completions
GET  http://localhost:8088/v1/models
```

Agnostic's existing `model_manager.py` (`OpenAIProvider`) can target this endpoint without any code changes — it is configured via the `agnos_gateway` entry in `config/models.json`:

```json
"agnos_gateway": {
  "type": "openai",
  "base_url": "${AGNOS_LLM_GATEWAY_URL:-http://localhost:8088}/v1",
  "api_key": "${AGNOS_LLM_GATEWAY_API_KEY:-agnos-local}",
  "model": "${AGNOS_LLM_GATEWAY_MODEL:-default}",
  "enabled": false
}
```

Enable by setting in `.env`:

```env
AGNOS_LLM_GATEWAY_ENABLED=true
AGNOS_LLM_GATEWAY_URL=http://localhost:8088
PRIMARY_MODEL_PROVIDER=agnos_gateway
FALLBACK_MODEL_PROVIDERS=ollama,openai
```

#### 2. Security Sandboxing (Passive)

When agnosticos is the host OS, its kernel-level Landlock + seccomp-bpf policies automatically apply to all Docker container processes. Agnostic does not need to configure this — it is enforced by the OS. Operators can review agent sandbox policies via the agnosticos security UI or `agnos-cli security`.

#### 3. Shared Ollama Instance (Implicit)

Both systems currently use Ollama at `http://localhost:11434` by default. On agnosticos, the LLM Gateway manages Ollama as a supervised provider — Agnostic should point to the gateway (port 8088) rather than Ollama directly (port 11434) to benefit from caching and token accounting.

#### 4. Agent Runtime (Future)

In a future phase, Agnostic's CrewAI agents may be registerable as agnosticos agents via the `agnos-sys` SDK. This would allow:
- Agnostic agents to appear in the agnosticos Agent HUD
- agnosticos orchestrator to manage agent lifecycle and resource limits
- Unified audit trail across all agents OS-wide

This is tracked in the agnosticos roadmap (see ADR-007 in agnosticos).

---

## Port Allocation

| Service | Port | Notes |
|---------|------|-------|
| AGNOS LLM Gateway | 8088 | OpenAI-compatible `/v1` API |
| Ollama (managed by agnosticos) | 11434 | Native Ollama API |
| llama.cpp | 8080 | Used by agnosticos `custom_local` provider |
| Agnostic WebGUI | 8000 | Chainlit + FastAPI |
| Agnostic Redis | 6379 | Internal messaging |
| Agnostic RabbitMQ | 5672 / 15672 | Internal task broker |

No port conflicts exist in the default configuration.

---

## Consequences

### Positive
- Agnostic agents gain OS-level token accounting and per-agent usage reporting
- Shared model cache across all 6 agents — fewer duplicate inference calls
- OS-enforced security sandbox with no changes to Agnostic code
- Single audit log combining Agnostic QA events with agnosticos OS security events

### Negative / Risks
- Dependency on agnosticos LLM Gateway being available (mitigated by `fallback_providers`)
- Port 8088 must not be in use by another service (document in deployment guide)
- agnosticos LLM Gateway OpenAI-compatible HTTP server is not yet fully implemented (tracked in agnosticos TODO)

### Neutral
- No changes to Agnostic's Python code, agent logic, or Docker containers
- Existing deployments not on agnosticos are entirely unaffected

---

## Implementation Checklist

- [x] Add `agnos_gateway` provider to `config/models.json` (disabled by default)
- [x] Add `AGNOS_LLM_GATEWAY_*` env vars to `.env.example`
- [ ] agnosticos: implement OpenAI-compatible HTTP server in `llm-gateway` on port 8088
- [ ] agnosticos: expose `/v1/chat/completions` and `/v1/models` endpoints
- [ ] Write `docs/deployment/agnosticos.md` deployment guide
- [ ] Integration test: agnostic → agnos gateway → Ollama round-trip

---

## Related

- [ADR-007 in agnosticos](../../../agnosticos/docs/adr/adr-007-agnostic-integration.md): agnosticos side of this integration
- [ADR-007: LLM Integration](007-llm-integration.md): Existing Agnostic LLM provider architecture
- agnosticos repository: `userland/llm-gateway/src/main.rs`
