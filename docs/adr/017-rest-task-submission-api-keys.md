# ADR-017: REST Task Submission and API Key Authentication

**Status:** Accepted
**Date:** 2026-02-21
**Deciders:** Engineering Team

---

## Context

The WebGUI REST API (ADR-014) exposed 18 endpoints but had no way for machine-to-machine (M2M) clients (e.g. YEOMAN MCP agents) to drive the full QA pipeline over plain HTTP. Every session was browser-initiated via the Chainlit chat interface. Two gaps had to be filled:

1. **Task submission** — a fire-and-forget POST that returns a `task_id`, plus a GET to poll status.
2. **M2M authentication** — Bearer JWT requires an interactive login flow; M2M clients need a long-lived credential.

---

## Decisions

### 1. Async fire-and-forget via `asyncio.create_task`

`POST /api/tasks` writes an initial `{status: "pending"}` record to Redis and immediately returns the `task_id`. The actual QA pipeline runs in the background via `asyncio.create_task(_run_task_async(...))`.

**Why:** QA sessions can take minutes. Blocking the HTTP response for the full duration would cause timeouts and poor UX for clients. The task-store pattern (`task:{task_id}` in Redis) lets any number of clients poll `GET /api/tasks/{task_id}` for status.

**Alternative considered:** Celery task. Rejected because it adds a broker round-trip for something already running inside the async FastAPI process; introduces a new dependency path just for task tracking.

### 2. Redis as task store (24-hour TTL)

Task records are stored at `task:{task_id}` with a `setex` TTL of 86 400 s (24 h). Status transitions: `pending → running → completed | failed`.

**Why:** Redis is already the shared state bus for the whole system. No new infrastructure needed. 24 h is long enough for clients to retrieve results after a slow QA run.

### 3. Dual-mode API key authentication

Two modes are supported, selectable per deployment:

| Mode | Env var / storage | Use case |
|------|-------------------|----------|
| Static | `AGNOSTIC_API_KEY` env var | Single-client, simple deployments |
| Redis-backed | `api_key:{sha256(key)}` Redis key | Multi-client, revocable keys |

`get_current_user` checks `X-API-Key` first, then falls back to `Authorization: Bearer <JWT>`. This keeps the JWT flow unchanged for browser clients.

**Why static key:** Zero operational overhead. One env var, one client, done.

**Why Redis-backed:** Revocable, auditable, per-client permissions. Key IDs (first 8 chars of sha256) allow management without exposing the raw secret. Raw keys are never stored — only their sha256 hash.

### 4. API key management endpoints

```
POST   /api/auth/api-keys        — create (returns raw key once)
GET    /api/auth/api-keys        — list key IDs + metadata
DELETE /api/auth/api-keys/{id}   — revoke
```

All three require `SYSTEM_CONFIGURE` permission, matching the existing permission model from ADR-005.

### 5. Agent-specific convenience endpoints

Four thin wrappers override the `agents` field and delegate to `submit_task`:

```
POST /api/tasks/security     → agents=["security-compliance"]
POST /api/tasks/performance  → agents=["performance"]
POST /api/tasks/regression   → agents=["junior-qa", "qa-analyst"]
POST /api/tasks/full         → agents=[] (all agents)
```

**Why:** Reduces boilerplate for the common case of single-concern scans. YEOMAN can call `/api/tasks/security` without knowing internal agent names.

---

## Consequences

**Positive:**
- YEOMAN MCP agents and CI/CD pipelines can drive the full QA pipeline over HTTP.
- No new infrastructure — Redis already running.
- API key auth is non-breaking; JWT flow unchanged.
- Convenience endpoints are zero-maintenance thin wrappers.

**Negative / trade-offs:**
- `asyncio.create_task` tasks are lost on process restart. Acceptable for a development-phase implementation; production deployments should consider persisting the task queue (see roadmap item: Test Result Persistence).
- Static `AGNOSTIC_API_KEY` provides no per-client audit trail. Teams needing audit logs should use Redis-backed keys.

## Amendment: Input validation & security hardening (2026-02-28)

`TaskSubmitRequest` now enforces:

| Field | Constraint |
|-------|-----------|
| `title` | `min_length=1`, `max_length=200` |
| `description` | `min_length=1`, `max_length=5000` |
| `priority` | `Literal["critical","high","medium","low"]` — invalid values → HTTP 422 |
| `business_goals` | `max_length=500` |
| `constraints` | `max_length=500` |

Static `AGNOSTIC_API_KEY` comparison changed from `==` to `hmac.compare_digest()` (constant-time) to prevent timing side-channel attacks.
