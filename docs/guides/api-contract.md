# Cross-Project API Contract

API surface shared between Agnostic, SecureYeoman, and AGNOS. This document is the source of truth for cross-project integration.

## Crew Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/crews` | Create and run a crew. Accepts `preset`, `agent_keys`, `agent_definitions`, or `team` |
| GET | `/api/v1/crews/{crew_id}` | Get crew status and results |
| GET | `/api/v1/crews` | List crews (filterable by `status`, paginated) |
| POST | `/api/v1/crews/{crew_id}/cancel` | Cancel a running or pending crew |

### CrewRunRequest

```json
{
  "preset": "quality-standard",
  "title": "Code review",
  "description": "Review the authentication module",
  "target_url": "https://github.com/org/repo/pull/42",
  "priority": "high",
  "process": "sequential",
  "gpu_memory_budget_mb": 8000,
  "scheduling_policy": "gpu-affinity",
  "group": "gpu-rack-1",
  "callback_url": "https://example.com/webhook",
  "callback_secret": "hmac-secret"
}
```

**Source options** (provide exactly one):
- `preset` — named preset (e.g. `"quality-standard"`, `"design-lean"`)
- `agent_keys` — list of definition keys from disk
- `agent_definitions` — inline agent definition dicts
- `team` — `{"members": [{"role": "UX Researcher", "context": "..."}], "project_context": "..."}`

### CrewRunResponse

```json
{
  "crew_id": "uuid",
  "task_id": "uuid",
  "session_id": "crew_20260317_...",
  "status": "pending",
  "agent_count": 3,
  "agents": ["senior-qa", "security-compliance", "qa-analyst"],
  "created_at": "2026-03-17T..."
}
```

## Preset Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/presets` | List presets (filterable by `domain`, `size`) |
| GET | `/api/v1/presets/{name}` | Get preset details with agent list |
| POST | `/api/v1/presets` | Create a custom preset (admin) |
| DELETE | `/api/v1/presets/{name}` | Delete a preset (admin) |

### Domains and sizes

- **Domains**: `quality`, `software-engineering`, `design`, `data-engineering`, `devops`
- **Sizes**: `lean` (2-3 agents), `standard` (3-6), `large` (6-9)
- **Naming**: `{domain}-{size}` (e.g. `design-large`)

## Definition Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/definitions` | List agent definitions (filterable by `domain`) |
| GET | `/api/v1/definitions/{key}` | Get single definition |
| POST | `/api/v1/definitions` | Create definition (admin) |
| PUT | `/api/v1/definitions/{key}` | Update definition (admin) |
| DELETE | `/api/v1/definitions/{key}` | Delete definition (admin) |

## A2A Protocol

Endpoint: `POST /api/v1/a2a/receive`

### Message types

| Type | Direction | Description |
|------|-----------|-------------|
| `a2a:delegate` | SY → Agnostic | Delegate a task/crew to Agnostic |
| `a2a:create_agent` | SY → Agnostic | Create an agent definition |
| `a2a:heartbeat` | Either → Either | Liveness check |
| `a2a:result` | SY → Agnostic | Return task results |
| `a2a:status_query` | SY → Agnostic | Query dashboard status |

### A2A delegate payload

```json
{
  "id": "msg-uuid",
  "type": "a2a:delegate",
  "fromPeerId": "secureyeoman",
  "toPeerId": "agnostic",
  "payload": {
    "title": "Security audit",
    "description": "Audit the payment module",
    "preset": "quality-security",
    "priority": "high",
    "target_url": "https://..."
  },
  "timestamp": 1710700000000
}
```

### A2A delegate response

```json
{
  "accepted": true,
  "crew_id": "uuid",
  "task_id": "uuid",
  "message_id": "msg-uuid"
}
```

## GPU Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/gpu/status` | GPU devices, VRAM, utilization |
| GET | `/api/v1/gpu/memory` | Aggregated VRAM per device |
| GET | `/api/v1/gpu/devices/{index}` | Single device detail |
| GET | `/api/v1/gpu/slots` | Cross-crew GPU reservations |
| GET | `/api/v1/gpu/inference` | Local inference offload status |

## Fleet Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/fleet/nodes` | List fleet nodes |
| GET | `/api/v1/fleet/nodes/{id}` | Single node detail |
| GET | `/api/v1/fleet/groups` | List node groups |
| GET | `/api/v1/fleet/status` | Fleet-wide summary |
| GET | `/api/v1/fleet/gpu` | Fleet-wide GPU aggregation |
| POST | `/api/v1/fleet/evict` | Remove dead nodes (admin) |

## Authentication

All endpoints accept one of:
- `X-API-Key` header — static key (`AGNOSTIC_API_KEY`) or Redis-backed
- `Authorization: Bearer <jwt>` — Agnostic JWT or SecureYeoman JWT (if `YEOMAN_JWT_ENABLED=true`)

## Webhook callbacks

When `callback_url` is provided on crew/task creation:
- POST to the URL on completion/failure
- Body: JSON crew/task record
- `X-Signature: sha256=<hmac>` header if `callback_secret` provided
- Retries: up to 3 with exponential backoff
- SSRF validation at submission and at fire time

## MCP Tools

35 tools across 8 categories. Discovery: `GET /api/v1/mcp/tools`. Invocation: `POST /api/v1/mcp/invoke`.

Key tools for cross-project use:
- `agnostic_run_crew` — submit crew with domain/size/preset/team
- `agnostic_crew_status` — poll crew by ID
- `agnostic_preset_recommend` — get best preset for a description
- `agnostic_list_presets` — browse available presets
- `agnostic_gpu_status` — check GPU availability
- `agnostic_a2a_delegate` — delegate via A2A protocol
