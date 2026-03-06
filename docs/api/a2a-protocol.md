# A2A (Agent-to-Agent) Protocol

AGNOSTIC implements the A2A protocol for bidirectional communication with SecureYeoman and other AGNOS peers.

**Requires:** `YEOMAN_A2A_ENABLED=true`

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/a2a/receive` | Yes | Receive an A2A message from a peer |
| GET | `/api/v1/a2a/capabilities` | Yes | Advertise capabilities to peers |

Both endpoints return HTTP 503 when `YEOMAN_A2A_ENABLED=false`.

## Message Envelope

All A2A messages use this envelope format:

```json
{
  "id": "unique-message-id",
  "type": "a2a:<message_type>",
  "fromPeerId": "sender-id",
  "toPeerId": "receiver-id",
  "payload": {},
  "timestamp": 1708516800000
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique message identifier |
| `type` | string | Message type (see below) |
| `fromPeerId` | string | Sender's peer ID |
| `toPeerId` | string | Receiver's peer ID |
| `payload` | object | Type-specific data |
| `timestamp` | integer | Unix milliseconds |

## Message Types

### `a2a:delegate`

Delegate a QA task to AGNOSTIC. Creates a task via the standard task pipeline.

**Payload:**

```json
{
  "title": "Security scan via A2A",
  "description": "Run OWASP checks on staging",
  "target_url": "https://staging.example.com",
  "priority": "high",
  "agents": ["security-compliance"],
  "standards": ["OWASP"]
}
```

**Response:**

```json
{
  "accepted": true,
  "task_id": "uuid",
  "message_id": "msg-001"
}
```

### `a2a:heartbeat`

Health check ping between peers.

**Payload:** `{}` or `{"status": "healthy"}`

**Response:**

```json
{
  "accepted": true,
  "message_id": "hb-001",
  "timestamp": 1708516800000
}
```

### `a2a:result`

YEOMAN sending completed task results back to AGNOSTIC. Results are cached in an LRU cache (max 500 entries) for retrieval via `/dashboard/yeoman`.

**Payload:**

```json
{
  "task_id": "original-task-id",
  "status": "completed",
  "result": { ... }
}
```

**Response:**

```json
{
  "accepted": true,
  "message_id": "msg-id",
  "type": "result_cached"
}
```

### `a2a:status_query`

YEOMAN querying AGNOSTIC's current status. Returns a dashboard snapshot including agent statuses, active sessions, and metrics.

**Payload:** `{}`

**Response:**

```json
{
  "accepted": true,
  "message_id": "msg-id",
  "type": "status_response",
  "data": {
    "agents": [...],
    "sessions": [...],
    "metrics": {...}
  }
}
```

### Unknown types

Unrecognized message types are acknowledged with a warning for forward compatibility:

```json
{
  "accepted": true,
  "message_id": "msg-id",
  "warning": "Unhandled type: a2a:future_type"
}
```

## Capabilities

`GET /api/v1/a2a/capabilities` advertises:

| Capability | Description |
|------------|-------------|
| `qa` | 6-agent QA pipeline (security, performance, regression, compliance) |
| `security-audit` | OWASP, GDPR, PCI DSS, SOC 2 compliance scanning |
| `performance-test` | Load testing and P95/P99 latency profiling |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `YEOMAN_A2A_ENABLED` | `false` | Enable A2A endpoints and client |
| `YEOMAN_A2A_URL` | `http://localhost:3001` | YEOMAN's A2A endpoint base URL |
| `YEOMAN_A2A_API_KEY` | (empty) | API key for authenticating with YEOMAN |
| `YEOMAN_PEER_ID` | `secureyeoman` | YEOMAN's peer identifier |

## Client Usage

AGNOSTIC can also initiate A2A messages to YEOMAN via `shared/yeoman_a2a_client.py`:

```python
from shared.yeoman_a2a_client import yeoman_a2a_client

# Delegate a task
task_id = await yeoman_a2a_client.delegate_task("Run integration tests")

# Query status
status = await yeoman_a2a_client.query_task_status(task_id)

# Batch delegate (single round-trip)
task_ids = await yeoman_a2a_client.delegate_batch([
    {"description": "Security scan", "task_type": "security"},
    {"description": "Performance test", "task_type": "performance"},
])

# Batch status query (single round-trip)
statuses = await yeoman_a2a_client.query_batch_status(task_ids)

# Send heartbeat
await yeoman_a2a_client.send_heartbeat()
```
