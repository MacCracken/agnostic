# WebGUI REST API Reference

## Overview

The WebGUI exposes a Chainlit-based chat interface **and** a full REST API for machine-to-machine access. All REST routes are mounted under `/api/v1`.

- **Base URL (local):** `http://localhost:8000`
- **Framework:** Chainlit 2.x + FastAPI
- **Authentication:** `Authorization: Bearer <JWT>` or `X-API-Key: <key>`
- **Interactive docs:** `http://localhost:8000/docs` (Swagger UI), `/redoc`
- **OpenAPI schema:** `http://localhost:8000/openapi.json`

---

## Authentication

### JWT (browser / interactive)

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email": "user@example.com", "password": "secret"}
```

Response:
```json
{
  "access_token": "<jwt>",
  "refresh_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 900
}
```

Use the access token in subsequent requests:
```http
Authorization: Bearer <access_token>
```

### API Key (M2M / CI/CD)

Pass the API key in the `X-API-Key` header:

```http
X-API-Key: <your-key>
```

Two modes:

| Mode | Configuration |
|------|---------------|
| Static (single key) | Set `AGNOSTIC_API_KEY` env var |
| Per-client Redis-backed | Create via `POST /api/v1/auth/api-keys` |

---

## Endpoints

### Auth

| Method | Path | Description | Auth required |
|--------|------|-------------|---------------|
| `POST` | `/api/v1/auth/login` | Authenticate; get JWT tokens | No |
| `POST` | `/api/v1/auth/refresh` | Refresh access token | No |
| `POST` | `/api/v1/auth/logout` | Invalidate tokens | Yes |
| `GET`  | `/api/v1/auth/me` | Current user info | Yes |
| `POST` | `/api/v1/auth/api-keys` | Create API key | Yes + `system:configure` |
| `GET`  | `/api/v1/auth/api-keys` | List API key IDs | Yes + `system:configure` |
| `DELETE` | `/api/v1/auth/api-keys/{key_id}` | Revoke API key | Yes + `system:configure` |

#### `POST /api/v1/auth/api-keys`

Request:
```json
{"description": "YEOMAN CI key", "role": "api_user"}
```

Response (raw key shown **once**):
```json
{
  "key_id": "a1b2c3d4",
  "api_key": "<raw-key-store-safely>",
  "description": "YEOMAN CI key",
  "role": "api_user",
  "created_at": "2026-02-21T10:00:00",
  "note": "Store this key safely — it will not be shown again."
}
```

---

### Task Submission

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/tasks` | Submit a QA task |
| `GET`  | `/api/v1/tasks/{task_id}` | Poll task status |
| `POST` | `/api/v1/tasks/security` | Security-focused task |
| `POST` | `/api/v1/tasks/performance` | Performance-focused task |
| `POST` | `/api/v1/tasks/regression` | Regression task (junior + analyst) |
| `POST` | `/api/v1/tasks/full` | Full 6-agent task |

#### `POST /api/v1/tasks`

Request:
```json
{
  "title": "Sprint 42 QA",
  "description": "Test the new checkout flow including OWASP checks",
  "target_url": "https://staging.example.com",
  "priority": "high",
  "standards": ["OWASP", "GDPR"],
  "agents": [],
  "business_goals": "Zero P0 bugs before release",
  "constraints": "Staging environment, no PII",
  "callback_url": "https://ci.example.com/hooks/qa",
  "callback_secret": "optional-hmac-secret"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | **required** | Short task title |
| `description` | string | **required** | Detailed requirements |
| `target_url` | string\|null | `null` | URL under test |
| `priority` | string | `"high"` | `critical \| high \| medium \| low` |
| `standards` | string[] | `[]` | e.g. `["OWASP", "GDPR"]` |
| `agents` | string[] | `[]` | `[]` = all 6 agents; or e.g. `["security-compliance"]` |
| `business_goals` | string | `"Ensure quality..."` | Goals for fuzzy verification |
| `constraints` | string | `"Standard testing..."` | Environment constraints |
| `callback_url` | string\|null | `null` | Webhook URL for completion notification |
| `callback_secret` | string\|null | `null` | HMAC-SHA256 signing secret for webhook |

Response (immediate, status = `pending`):
```json
{
  "task_id": "3f4a1b2c-...",
  "session_id": "session_20260221_100000_3f4a1b2c",
  "status": "pending",
  "created_at": "2026-02-21T10:00:00+00:00",
  "updated_at": "2026-02-21T10:00:00+00:00",
  "result": null
}
```

#### `GET /api/v1/tasks/{task_id}`

Response:
```json
{
  "task_id": "3f4a1b2c-...",
  "session_id": "session_20260221_100000_3f4a1b2c",
  "status": "completed",
  "created_at": "2026-02-21T10:00:00+00:00",
  "updated_at": "2026-02-21T10:05:32+00:00",
  "result": {
    "test_plan": {...},
    "verification": {...}
  }
}
```

`status` values: `pending | running | completed | failed`

#### Convenience endpoints

All accept the same `TaskSubmitRequest` body. The `agents` field is **overridden** by the endpoint:

| Endpoint | `agents` override |
|----------|-------------------|
| `/api/v1/tasks/security` | `["security-compliance"]` |
| `/api/v1/tasks/performance` | `["performance"]` |
| `/api/v1/tasks/regression` | `["junior-qa", "qa-analyst"]` |
| `/api/v1/tasks/full` | `[]` (all 6 agents) |

#### Webhook Callback

When `callback_url` is provided, on task completion the API posts:

```http
POST <callback_url>
Content-Type: application/json
X-Signature: sha256=<hmac-sha256-hex>

{"task_id": "...", "status": "completed", ...}
```

Verify the signature on the receiving end:
```python
import hmac, hashlib
body = request.body()
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
assert request.headers["X-Signature"] == f"sha256={expected}"
```

---

### Dashboard

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/dashboard` | Aggregate dashboard data |
| `GET` | `/api/v1/dashboard/sessions` | Active sessions |
| `GET` | `/api/v1/dashboard/agents` | Agent status |
| `GET` | `/api/v1/dashboard/metrics` | Resource metrics |

---

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/sessions` | Session history (pagination: `limit`, `offset`, `user_id`) |
| `GET` | `/api/v1/sessions/search?q=<query>` | Search sessions |
| `GET` | `/api/v1/sessions/{session_id}` | Session details |
| `POST` | `/api/v1/sessions/compare` | Compare two sessions |

---

### Reports

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/reports` | List user's reports |
| `POST` | `/api/v1/reports/generate` | Generate a report |
| `GET` | `/api/v1/reports/{report_id}/download` | Download report file |

---

### Agents

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/agents` | Yes | All agent statuses |
| `GET` | `/api/v1/agents/queues` | Yes | Queue depths |
| `GET` | `/api/v1/agents/{agent_name}` | Yes | Agent metrics |

---

### A2A Protocol (Agent-to-Agent)

These endpoints implement the YEOMAN A2A wire protocol so Agnostic can appear as a first-class peer in a YEOMAN delegation tree (ADR-019).

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/api/v1/a2a/receive` | Yes | Receive an A2A protocol message |
| `GET`  | `/api/v1/a2a/capabilities` | No | Advertise supported capabilities |

#### `GET /api/v1/a2a/capabilities`

No authentication required.

```json
{
  "capabilities": [
    {"name": "qa",             "description": "6-agent QA pipeline (security, performance, regression, compliance)", "version": "1.0"},
    {"name": "security-audit", "description": "OWASP, GDPR, PCI DSS, SOC 2 compliance scanning", "version": "1.0"},
    {"name": "performance-test","description": "Load testing and P95/P99 latency profiling", "version": "1.0"}
  ]
}
```

#### `POST /api/v1/a2a/receive`

Accepts any A2A envelope. Routing is performed on the `type` field:

```json
{
  "id": "msg-abc-123",
  "type": "a2a:delegate",
  "fromPeerId": "yeoman-agent",
  "toPeerId": "agnostic",
  "payload": {
    "title": "Security scan",
    "description": "Run OWASP checks on staging",
    "target_url": "https://staging.example.com",
    "priority": "high",
    "agents": ["security-compliance"],
    "standards": ["OWASP", "GDPR"]
  },
  "timestamp": 1708516800000
}
```

| `type` | Behaviour |
|--------|-----------|
| `a2a:delegate` | Extracts task fields from `payload`, submits via `POST /api/v1/tasks`, returns `task_id` |
| `a2a:heartbeat` | Echoes `message_id` + `timestamp` |
| *(anything else)* | Returns `accepted: true` with a `warning` field (forward-compatible) |

**Delegate response:**
```json
{"accepted": true, "task_id": "3f4a1b2c-...", "message_id": "msg-abc-123"}
```

**Heartbeat response:**
```json
{"accepted": true, "message_id": "hb-001", "timestamp": 1708516800000}
```

**Payload fields for `a2a:delegate`** (all optional except `title` + `description`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | `"A2A QA Task"` | Task title |
| `description` | string | `""` | Task requirements |
| `target_url` | string\|null | `null` | URL under test |
| `priority` | string | `"high"` | `critical \| high \| medium \| low` |
| `agents` | string[] | `[]` | Agent subset; `[]` = all 6 |
| `standards` | string[] | `[]` | e.g. `["OWASP", "GDPR"]` |

---

### Observability

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/metrics` | None | Prometheus metrics (scrape endpoint) |
| `GET` | `/health` | None | Infrastructure + agent liveness |

#### `GET /health`

```json
{
  "status": "healthy",
  "timestamp": "2026-02-21T10:00:00+00:00",
  "redis": "ok",
  "rabbitmq": "ok",
  "agents": {
    "qa-manager": "alive",
    "senior-qa": "stale",
    "junior-qa": "alive",
    "qa-analyst": "alive",
    "security-compliance": "offline",
    "performance": "alive"
  }
}
```

| `status` | Meaning |
|----------|---------|
| `healthy` | Redis ok + RabbitMQ ok + ≥1 agent alive |
| `degraded` | Infrastructure ok but all agents stale/offline |
| `unhealthy` | Redis or database unreachable |

Agent heartbeat staleness threshold: `AGENT_STALE_THRESHOLD_SECONDS` (default: `300`).

---

## TypeScript Client Generation

After any API change, regenerate the TypeScript client used by YEOMAN:

```bash
# Export the schema
python scripts/export-openapi.py

# Generate TypeScript types
npx openapi-typescript http://localhost:8000/openapi.json \
  --output packages/mcp/src/tools/agnostic-client.ts
```

The `scripts/export-openapi.py` script writes `docs/api/openapi.json` from the live FastAPI schema.

---

## CORS

Allowed origins are controlled via the `CORS_ALLOWED_ORIGINS` env var (comma-separated):

```bash
CORS_ALLOWED_ORIGINS=http://localhost:18789,http://localhost:3001
```

Default: `http://localhost:18789,http://localhost:3001`.
