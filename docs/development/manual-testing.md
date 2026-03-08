# Manual Testing Guide

This document describes the complete manual test sweep for the Agnostic QA platform — covering smoke, integration, and end-to-end tests. Run these in order when validating a new deployment, release candidate, or after significant code changes.

**Estimated time:** Smoke ~5 min · Integration ~40 min · End-to-end ~90 min

---

## Prerequisites

### Environment setup

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

```bash
# LLM — required
OPENAI_API_KEY=sk-...

# RabbitMQ — required (no guest default)
RABBITMQ_USER=qa_user
RABBITMQ_PASSWORD=your_strong_password

# Static API key for M2M tests
AGNOSTIC_API_KEY=test-api-key-manual-sweep

# Environment label
ENVIRONMENT=development
```

### Services running

```bash
docker compose -f docker-compose.old-style.yml --profile workers up -d
docker compose -f docker-compose.old-style.yml ps   # all services should show "Up"
```

### Test tools

```bash
# curl (any version) + jq for JSON formatting
curl --version
jq --version
```

Export a base URL shorthand for all commands below:

```bash
export BASE=http://localhost:8000
```

---

## 1. Smoke Tests

**Goal:** confirm the stack starts cleanly and the minimum viable surface is reachable in under 5 minutes.

### 1.1 All containers up

```bash
docker compose ps
```

**Pass:** every service shows `Up` (no `Exit` or `Restarting`). Expected services:

| Service | Port(s) |
|---------|---------|
| agnostic (webgui) | 8000 |
| redis | 6379 |
| postgres | 5433 |
| rabbitmq (workers profile) | 5672, 15672 |
| qa-manager (workers profile) | — |
| senior-qa (workers profile) | — |
| junior-qa (workers profile) | — |
| qa-analyst (workers profile) | — |
| security-compliance-agent (workers profile) | — |
| performance-agent (workers profile) | — |

### 1.2 Health endpoint

```bash
curl -s $BASE/health | jq .
```

**Pass:** HTTP 200, `status` is `"healthy"` or `"degraded"` (not `"unhealthy"`), `redis` and `rabbitmq` show `"ok"`.

Example passing response:

```json
{
  "status": "healthy",
  "redis": "ok",
  "rabbitmq": "ok",
  "agents": {
    "QA Manager": "alive",
    "Senior QA Engineer": "alive"
  },
  "timestamp": "2026-02-28T12:00:00+00:00"
}
```

**Fail indicators:**
- `"redis": "error"` — check `docker compose logs redis`
- `"rabbitmq": "error"` — check `RABBITMQ_USER`/`RABBITMQ_PASSWORD` in `.env`
- HTTP 502 — webgui container not yet started; wait 10 s and retry

### 1.3 WebGUI loads

```bash
curl -s -o /dev/null -w "%{http_code}" $BASE/
```

**Pass:** `200`

### 1.4 A2A capabilities (unauthenticated)

```bash
curl -s $BASE/api/v1/a2a/capabilities | jq .capabilities[].name
```

**Pass:** HTTP 200, response lists `"qa"`, `"security-audit"`, `"performance-test"`.

### 1.5 RabbitMQ management reachable

```bash
curl -s -o /dev/null -w "%{http_code}" \
  http://localhost:15672/api/overview \
  -u "${RABBITMQ_USER}:${RABBITMQ_PASSWORD}"
```

**Pass:** `200`

**Note:** `guest:guest` will no longer work — credentials are now required from `.env`.

---

## 2. Integration Tests

**Goal:** verify each API surface, authentication path, and cross-service integration point independently.

### 2.1 Authentication — JWT login

```bash
curl -s -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@agnostic.local","password":"changeme"}' | jq .
```

**Pass:** HTTP 200 with `access_token` and `refresh_token` in the response.

Export the token for subsequent calls:

```bash
export TOKEN=$(curl -s -X POST $BASE/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@agnostic.local","password":"changeme"}' \
  | jq -r .access_token)
```

**Fail:** HTTP 401 means the default admin account is not seeded — check `webgui/auth.py` setup.

### 2.2 Authentication — Static API key

```bash
curl -s $BASE/api/auth/me \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq .
```

**Pass:** HTTP 200, `user_id` is `"api-key-user"`, role is `"api_user"`.

### 2.3 Authentication — Invalid API key rejected

```bash
curl -s -o /dev/null -w "%{http_code}" $BASE/api/auth/me \
  -H "X-API-Key: wrong-key"
```

**Pass:** `401`

### 2.4 Authentication — Unauthenticated request rejected

```bash
curl -s -o /dev/null -w "%{http_code}" $BASE/api/tasks
```

**Pass:** `401`

### 2.5 Input validation — Invalid priority rejected

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -X POST $BASE/api/tasks \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"title":"T","description":"D","priority":"urgent"}'
```

**Pass:** `422` (Unprocessable Entity — `"urgent"` is not a valid priority)

### 2.6 Input validation — Oversized title rejected

```bash
LONG=$(python3 -c "print('x'*201)")
curl -s -o /dev/null -w "%{http_code}" \
  -X POST $BASE/api/tasks \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"${LONG}\",\"description\":\"D\"}"
```

**Pass:** `422`

### 2.7 Task submission and polling

```bash
# Submit
TASK=$(curl -s -X POST $BASE/api/tasks \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Smoke QA task",
    "description": "Verify the login flow and basic navigation",
    "priority": "medium",
    "target_url": "http://example.com"
  }')

echo $TASK | jq .
TASK_ID=$(echo $TASK | jq -r .task_id)
```

**Pass:** HTTP 200, `status` is `"pending"`, `task_id` is a UUID.

```bash
# Poll for status
curl -s $BASE/api/tasks/$TASK_ID \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq '{status,task_id}'
```

**Pass:** HTTP 200. Status will move from `"pending"` → `"running"` → `"completed"` (or `"failed"` if LLM is not available). Either `"completed"` or `"failed"` confirms the task lifecycle is wired up.

### 2.8 Agent-specific endpoints

```bash
for endpoint in security performance regression full; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST $BASE/api/tasks/$endpoint \
    -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"title":"T","description":"D"}')
  echo "POST /api/tasks/$endpoint → $CODE"
done
```

**Pass:** all four return `200`.

### 2.9 Agent status endpoints

```bash
# All agents
curl -s $BASE/api/agents \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq 'length'

# Queue depths
curl -s $BASE/api/agents/queues \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq .
```

**Pass:** `/api/agents` returns a JSON array (length ≥ 0), `/api/agents/queues` returns a JSON object with agent-name keys.

### 2.10 Dashboard

```bash
curl -s $BASE/api/dashboard \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq 'keys'
```

**Pass:** HTTP 200, response has keys including `sessions`, `agents`, `metrics`.

### 2.11 Sessions list

```bash
curl -s "$BASE/api/sessions?limit=10" \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq .
```

**Pass:** HTTP 200, response is a JSON array (may be empty on a fresh deployment).

### 2.12 Report generation and download

```bash
# Generate a report for the session created in 2.7
SESSION_ID=$(curl -s $BASE/api/tasks/$TASK_ID \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq -r .session_id)

REPORT=$(curl -s -X POST $BASE/api/reports/generate \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"${SESSION_ID}\",\"report_type\":\"executive_summary\",\"format\":\"json\"}")

echo $REPORT | jq .
REPORT_ID=$(echo $REPORT | jq -r .report_id)
```

**Pass:** HTTP 200, `report_id` is returned.

```bash
# Download
curl -s -o /dev/null -w "%{http_code}" \
  "$BASE/api/reports/$REPORT_ID/download" \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}"
```

**Pass:** `200` (file served) or `404` if no data was written for the session (valid for a fresh empty session).

### 2.13 Security: path traversal blocked on download

```bash
# Attempt a traversal via the report_id parameter
curl -s -o /dev/null -w "%{http_code}" \
  "$BASE/api/reports/../../../etc/passwd/download" \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}"
```

**Pass:** `404` (FastAPI route doesn't match) — the `/../../` is rejected at routing before it reaches the handler.

To test the in-handler protection, you would need to inject a crafted `file_path` into Redis. This is covered by the automated tests in `tests/unit/test_webgui_api.py::TestReportDownloadSecurity`.

### 2.14 Security: response headers present

```bash
curl -sI $BASE/health | grep -iE "x-content-type|x-frame|x-xss|referrer"
```

**Pass:** all four headers present:

```
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin
```

### 2.15 Prometheus metrics (unauthenticated)

```bash
curl -s $BASE/api/metrics | head -20
```

**Pass:** HTTP 200, plain text in Prometheus exposition format (lines starting with `#` or metric names).

### 2.16 A2A protocol — delegate message

```bash
curl -s -X POST $BASE/api/v1/a2a/receive \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-msg-001",
    "type": "a2a:delegate",
    "fromPeerId": "manual-test",
    "toPeerId": "agnostic",
    "payload": {
      "title": "A2A security scan",
      "description": "Run OWASP checks on staging",
      "priority": "high",
      "agents": ["security-compliance"],
      "standards": ["OWASP"]
    },
    "timestamp": 1708516800000
  }' | jq .
```

**Pass:** `accepted: true`, `task_id` present, `message_id` matches `"test-msg-001"`.

### 2.17 A2A protocol — heartbeat

```bash
curl -s -X POST $BASE/api/v1/a2a/receive \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "hb-001",
    "type": "a2a:heartbeat",
    "fromPeerId": "manual-test",
    "toPeerId": "agnostic",
    "payload": {},
    "timestamp": 1708516800000
  }' | jq .
```

**Pass:** `accepted: true`, `timestamp: 1708516800000`.

### 2.18 Redis connectivity — direct verification

```bash
docker compose exec redis redis-cli ping
```

**Pass:** `PONG`

```bash
# Verify task record was written
docker compose exec redis redis-cli get "task:${TASK_ID}" | jq .status
```

**Pass:** `"completed"` or `"failed"` (confirms the task lifecycle wrote to Redis).

### 2.19 RabbitMQ queues — management API

```bash
curl -s "http://localhost:15672/api/queues" \
  -u "${RABBITMQ_USER}:${RABBITMQ_PASSWORD}" | jq '[.[] | {name,messages}]'
```

**Pass:** HTTP 200, response lists the agent queues (`qa_manager`, `senior_qa`, etc.).

### 2.20 Webhook callback — manual setup (optional)

Requires a local HTTP listener. Use `nc` or `python3 -m http.server` in a separate terminal:

```bash
# Terminal A — start listener
python3 -m http.server 9999

# Terminal B — submit task with callback
curl -s -X POST $BASE/api/tasks \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Webhook test",
    "description": "Short task to trigger callback",
    "priority": "low",
    "callback_url": "http://host.docker.internal:9999/webhook",
    "callback_secret": "test-secret-123"
  }' | jq .task_id
```

**Pass:** Terminal A receives a POST to `/webhook` with `Content-Type: application/json` and an `X-Signature: sha256=...` header once the task completes.

---

## 3. End-to-End Tests

**Goal:** validate full user journeys from start to finish — covering the WebGUI chat interface, the REST API pipeline, and the YEOMAN MCP bridge (if available).

### 3.1 WebGUI chat — submit a QA requirement

1. Open `http://localhost:8000` in a browser.
2. You should see the welcome message listing all 6 agents.
3. Type and submit:
   ```
   Test the checkout flow for SQL injection, measure response times under 100 concurrent users, and validate GDPR compliance for user data handling
   ```
4. Observe the response — the QA Manager should parse and reflect back a structured test plan.

**Pass criteria:**
- Welcome message names all 6 agents
- Submission returns a test plan with named scenarios
- Each scenario shows an assigned agent and priority label
- Session ID is visible in the response
- No stack trace or `❌ Error:` message appears

### 3.2 WebGUI chat — status and report commands

After completing 3.1, in the same chat session:

```
status
```

**Pass:** shows session ID, status, and total scenarios count.

```
report
```

**Pass:** shows executive summary section, metrics (pass rate, coverage), or `"No analyst report available yet"` for a fresh run.

```
security
```

**Pass:** shows security score and risk level, or `"No security assessment available yet"`.

```
release
```

**Pass:** shows release readiness verdict (`GO` / `GO_WITH_WARNINGS` / `NO_GO`) or `"No release readiness data available yet"`.

### 3.3 REST API — full pipeline via `POST /api/tasks/full`

```bash
FULL_TASK=$(curl -s -X POST $BASE/api/tasks/full \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Full pipeline E2E test",
    "description": "Test a sample e-commerce checkout: functional correctness, OWASP Top-10 security scan, P95 latency under 500ms, GDPR compliance for PII fields",
    "target_url": "http://example.com/checkout",
    "priority": "high",
    "standards": ["OWASP", "GDPR", "PCI-DSS"],
    "business_goals": "Zero critical vulnerabilities, P95 < 500ms, GDPR pass",
    "constraints": "Read-only access, no live data modification"
  }')

echo $FULL_TASK | jq '{task_id, session_id, status}'
FULL_TASK_ID=$(echo $FULL_TASK | jq -r .task_id)
```

**Pass:** HTTP 200, `status: "pending"`.

Poll until complete (up to 10 minutes for a full LLM-backed run):

```bash
watch -n 10 "curl -s $BASE/api/tasks/$FULL_TASK_ID \
  -H 'X-API-Key: ${AGNOSTIC_API_KEY}' | jq '{status,updated_at}'"
```

**Pass:** status reaches `"completed"` (or `"failed"` with a non-empty `result.error` if LLM quota is exhausted — this is expected in CI without a live key).

Verify result structure:

```bash
curl -s $BASE/api/tasks/$FULL_TASK_ID \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq '.result | keys'
```

**Pass:** result keys include at minimum `status`, `session_id`, and agent-specific result objects.

### 3.4 REST API — security-focused scan

```bash
SEC_TASK=$(curl -s -X POST $BASE/api/tasks/security \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "OWASP Top-10 scan",
    "description": "Scan login, registration, and admin endpoints for injection, XSS, broken auth, and IDOR",
    "target_url": "http://example.com",
    "priority": "critical",
    "standards": ["OWASP"]
  }')

SEC_TASK_ID=$(echo $SEC_TASK | jq -r .task_id)
echo "Security task: $SEC_TASK_ID"
```

**Pass:** `status: "pending"`, correct `session_id` format.

Check that only the security agent is used:

```bash
# After completion, verify session data in Redis
docker compose exec redis redis-cli keys "security_compliance:*" | head -5
```

**Pass:** keys exist in the `security_compliance:*` namespace (confirms the security agent wrote results).

### 3.5 REST API — performance test

```bash
PERF_TASK=$(curl -s -X POST $BASE/api/tasks/performance \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Load and P99 latency test",
    "description": "Simulate 50 concurrent users for 60 seconds, assert P99 < 1000ms and error rate < 1%",
    "target_url": "http://example.com/api/products",
    "priority": "high"
  }')

echo $PERF_TASK | jq .task_id
```

**Pass:** HTTP 200, `status: "pending"`.

### 3.6 REST API — report generation after full pipeline

After 3.3 completes:

```bash
FULL_SESSION=$(curl -s $BASE/api/tasks/$FULL_TASK_ID \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq -r .session_id)

# Executive summary in JSON
EXEC_REPORT=$(curl -s -X POST $BASE/api/reports/generate \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"session_id\": \"${FULL_SESSION}\",
    \"report_type\": \"executive_summary\",
    \"format\": \"json\"
  }")

echo $EXEC_REPORT | jq '{report_id,report_type,format,file_size}'
EXEC_REPORT_ID=$(echo $EXEC_REPORT | jq -r .report_id)

# Download and spot-check
curl -s "$BASE/api/reports/$EXEC_REPORT_ID/download" \
  -H "X-API-Key: ${AGNOSTIC_API_KEY}" | jq 'keys'
```

**Pass:** report downloads and contains expected top-level keys (`session_id`, `generated_at`, at least one content section).

### 3.7 YEOMAN MCP bridge end-to-end

> Requires SecureYeoman running (`secureyeoman start` or its local dev equivalent) with `MCP_EXPOSE_AGNOSTIC_TOOLS=true` and `AGNOSTIC_URL=http://127.0.0.1:8000`.

#### 3.7.1 Health check via MCP

Ask the YEOMAN agent:
```
Use the agnostic_health tool to check if the Agnostic QA platform is reachable
```

**Pass:** Agent reports `"reachable": true`, version information returned.

#### 3.7.2 Agent status via MCP

```
Use agnostic_agents_status to list all QA agents and their current status
```

**Pass:** Response lists all 6 agents with name, role, and status fields.

#### 3.7.3 Submit a task via MCP

```
Use agnostic_submit_qa to submit a security scan task:
  title: "MCP-submitted OWASP scan"
  description: "Automated scan submitted from YEOMAN via MCP bridge"
  priority: high
  agents: ["security-compliance"]
  standards: ["OWASP"]
```

**Pass:** Tool returns a `task_id`. Note it.

#### 3.7.4 Poll the task via MCP

```
Use agnostic_task_status to check the status of task <task_id from above>
```

**Pass:** Returns status `running` or `completed`, consistent with `GET /api/tasks/{id}` via direct curl.

#### 3.7.5 A2A delegation via MCP

```
Use agnostic_delegate_a2a to delegate a compliance check:
  title: "GDPR compliance via A2A"
  description: "Validate PII handling on the registration form"
  priority: medium
  agents: ["security-compliance"]
  standards: ["GDPR"]
```

**Pass:** Tool returns `accepted: true` with a `task_id`.

#### 3.7.6 Dashboard via MCP

```
Use agnostic_dashboard to retrieve the current aggregate metrics
```

**Pass:** Response includes session counts, agent statuses, and metrics — consistent with `GET /api/dashboard`.

#### 3.7.7 Generate and retrieve a report via MCP

```
Use agnostic_generate_report for session <session_id from 3.7.3> with type executive_summary and format json
```

**Pass:** `report_id` returned. Can be verified with direct curl download.

---

## 4. Pass / Fail Criteria Summary

| Test area | Pass condition | Common failure cause |
|-----------|----------------|----------------------|
| All containers up | All services `Up` | Credential missing, port conflict |
| Health endpoint | `status: healthy` or `degraded` | Redis/RabbitMQ not ready |
| JWT login | `200` + `access_token` | Admin user not seeded |
| Static API key | `200` + correct user | `AGNOSTIC_API_KEY` not set in `.env` |
| Invalid priority | `422` | Pydantic validation regression |
| Oversized fields | `422` | Field length constraint removed |
| Task submission | `200` + `status: pending` | Redis unavailable |
| Task lifecycle | `completed` or `failed` | LLM not available (expected in offline CI) |
| Security headers | All 4 headers present | Middleware removed or not registered |
| Path traversal | `404`/`403` | Path validation logic removed |
| A2A delegate | `accepted: true` + `task_id` | Auth or routing regression |
| A2A heartbeat | `accepted: true` + `timestamp` | Handler not matching type |
| RabbitMQ queues | Queue list returned | Wrong credentials in `.env` |
| MCP health | `reachable: true` | `AGNOSTIC_URL` misconfigured in YEOMAN |
| MCP submit + poll | Task progresses | Token cache failure; retry with API key auth |

---

## 5. What to Check in Logs When Tests Fail

```bash
# Agnostic / API layer
docker compose logs --tail=100 agnostic | grep -iE "error|exception|traceback"

# QA Manager (task orchestration)
docker compose logs --tail=100 qa-manager | grep -iE "error|failed"

# Security agent
docker compose logs --tail=100 security-compliance-agent | grep -iE "error"

# Performance agent
docker compose logs --tail=100 performance-agent | grep -iE "error"

# Redis (connectivity issues)
docker compose logs --tail=50 redis

# RabbitMQ (auth issues show up here)
docker compose logs --tail=50 rabbitmq | grep -iE "error|refused|denied"
```

Redis key inspection:

```bash
# List all tasks
docker compose exec redis redis-cli keys "task:*"

# Inspect a specific task
docker compose exec redis redis-cli get "task:<task_id>" | python3 -m json.tool

# List session keys
docker compose exec redis redis-cli keys "session:*"

# List all agent result keys for a session
docker compose exec redis redis-cli keys "*:<session_id>:*"
```

---

## 6. Resetting Test State

```bash
# Flush all Redis test data (non-destructive to config)
docker compose exec redis redis-cli flushdb

# Full restart with clean state
docker compose down
docker compose up -d

# Reset to a known good build
docker compose down -v
./scripts/build-docker.sh
docker compose up -d
```

---

## Related Documents

- [Quick Start Guide](../getting-started/quick-start.md) — initial setup
- [Development Setup](setup.md) — local dev without Docker
- [ADR-010 Security Strategy](../adr/010-security-strategy.md) — security controls tested in section 2.13–2.14
- [ADR-017 Task Submission & API Keys](../adr/017-rest-task-submission-api-keys.md) — task API design
- [ADR-018 Webhooks & CORS](../adr/018-webhook-callbacks-cors.md) — webhook test in section 2.20
- [ADR-019 A2A Protocol](../adr/019-a2a-protocol.md) — A2A tests in sections 2.16–2.17 and 3.7.5
