# TODO — Agnostic QA Platform

## YEOMAN MCP Integration (REST API) — All Implemented ✅

All 8 original priorities for the YEOMAN MCP bridge are complete.
See `docs/project/changelog.md` for details. Reference below preserved for history.

---

## Upcoming Work (see roadmap for full detail)

### Near-term
- [ ] WebSocket real-time updates (`/ws/realtime`) — infrastructure exists (`webgui/realtime.py`), not yet wired to API
- [ ] Scheduled report generation — APScheduler or Celery Beat integration
- [ ] CrewAI 1.x + litellm migration (drop langchain 0.1.x dependency)
- [ ] Grafana dashboard JSON + Prometheus `ServiceMonitor` CRD

### Medium-term
- [ ] PostgreSQL/SQLite test result persistence (replace Redis-only storage)
- [ ] Multi-tenant WebGUI (team-scoped keyspaces, per-team RabbitMQ vhosts)
- [ ] GitOps/ArgoCD integration + Sealed Secrets

---

## REST API YEOMAN Integration History

### Priority 1 — Task Submission Endpoint ✅ Implemented

The most critical missing piece. Currently, QA task submission only happens via
the Chainlit `@cl.on_message` handler inside `webgui/app.py`. There is no REST
equivalent.

**Add to `webgui/api.py`:**

```python
class TaskSubmitRequest(BaseModel):
    title: str
    description: str
    target_url: str | None = None
    priority: str = "high"                     # critical | high | medium | low
    standards: list[str] = []                  # ["OWASP", "GDPR", "PCI DSS", ...]
    agents: list[str] = []                     # [] = all agents; or ["security_compliance", "performance"]
    business_goals: str = "Ensure quality and functionality"
    constraints: str = "Standard testing environment"

class TaskStatusResponse(BaseModel):
    task_id: str
    session_id: str
    status: str        # pending | running | completed | failed
    created_at: str
    updated_at: str
    result: dict | None = None

@api_router.post("/tasks", response_model=TaskStatusResponse)
async def submit_task(
    req: TaskSubmitRequest,
    user: dict = Depends(get_current_user),
):
    """Submit a QA task to the agent team."""
    from agents.manager.qa_manager_optimized import OptimizedQAManager
    import uuid

    task_id = str(uuid.uuid4())
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}"

    requirements = {
        "title": req.title,
        "description": req.description,
        "target_url": req.target_url,
        "business_goals": req.business_goals,
        "constraints": req.constraints,
        "priority": req.priority,
        "standards": req.standards,
        "agents": req.agents,
        "submitted_by": user.get("user_id", "api"),
        "submitted_at": datetime.now().isoformat(),
    }

    # Store pending task in Redis so GET /api/tasks/{task_id} can poll it
    redis_client = config.get_redis_client()
    redis_client.set(
        f"task:{task_id}",
        json.dumps({
            "task_id": task_id,
            "session_id": session_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "result": None,
        }),
        ex=86400,  # 24h TTL
    )

    # Kick off async QA session (fire-and-forget, stores result in Redis on completion)
    import asyncio
    manager = OptimizedQAManager()
    asyncio.create_task(
        _run_task_async(manager, task_id, session_id, requirements, redis_client)
    )

    return TaskStatusResponse(
        task_id=task_id,
        session_id=session_id,
        status="pending",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        result=None,
    )


async def _run_task_async(manager, task_id, session_id, requirements, redis_client):
    """Background coroutine: run QA session and write result back to Redis."""
    try:
        redis_client.set(
            f"task:{task_id}",
            json.dumps({"task_id": task_id, "session_id": session_id, "status": "running",
                        "created_at": redis_client.get(f"task:{task_id}") and
                        json.loads(redis_client.get(f"task:{task_id}")).get("created_at"),
                        "updated_at": datetime.now().isoformat(), "result": None}),
            ex=86400,
        )
        result = await manager.orchestrate_qa_session({"session_id": session_id, **requirements})
        redis_client.set(
            f"task:{task_id}",
            json.dumps({"task_id": task_id, "session_id": session_id, "status": "completed",
                        "updated_at": datetime.now().isoformat(), "result": result}),
            ex=86400,
        )
    except Exception as e:
        redis_client.set(
            f"task:{task_id}",
            json.dumps({"task_id": task_id, "session_id": session_id, "status": "failed",
                        "updated_at": datetime.now().isoformat(), "result": {"error": str(e)}}),
            ex=86400,
        )


@api_router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, user: dict = Depends(get_current_user)):
    """Poll a task for completion."""
    redis_client = config.get_redis_client()
    data = redis_client.get(f"task:{task_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(data)
```

---

## Priority 2 — API Key Authentication ✅ Implemented

The current auth requires email + password login to get a JWT. For service-to-service
integration (YEOMAN → Agnostic), API key auth is simpler and more appropriate.

**Add to `webgui/auth.py`:**
- Support `X-API-Key: <key>` header as an alternative to `Authorization: Bearer <token>`
- Store API keys in a `api_keys` table (or Redis set) keyed by `sha256(key)`
- Add management endpoints: `POST /api/auth/api-keys`, `DELETE /api/auth/api-keys/{key_id}`
- `get_current_user` dependency should check API key header first, fall back to JWT

**Env var:** `AGNOSTIC_API_KEY` (single static key for simple deployments)

---

## Priority 3 — Webhook / Callback on Task Completion ✅ Implemented

Instead of polling `GET /api/tasks/{task_id}`, callers can register a webhook URL
that Agnostic POSTs to when a task completes.

**Add to `TaskSubmitRequest`:**
```python
callback_url: str | None = None   # POST here with TaskStatusResponse when done
callback_secret: str | None = None  # HMAC-SHA256 signing secret for webhook payload
```

Implement in `_run_task_async`: after writing the result, if `callback_url` is set,
POST the final `TaskStatusResponse` JSON with `X-Signature: sha256(<secret>, <body>)`.

---

## Priority 4 — Agent-Specific Task Endpoints ✅ Implemented

Add convenience endpoints that pre-select the relevant agent(s) so callers don't
need to know internal agent names:

```
POST /api/tasks/security   → runs security_compliance agent only
POST /api/tasks/performance → runs performance agent only
POST /api/tasks/regression  → runs junior_qa + qa_analyst
POST /api/tasks/full        → runs full 6-agent team (same as POST /api/tasks with agents=[])
```

---

## Priority 5 — OpenAPI Schema & Client SDK ✅ Implemented

- Ensure all request/response models are typed Pydantic models (not raw dicts)
  so FastAPI auto-generates complete OpenAPI docs at `/docs`
- Publish the OpenAPI schema to `docs/api/openapi.json` on each release
- Generate a TypeScript client from the schema for use in YEOMAN:
  `npx openapi-typescript http://localhost:8000/openapi.json --output packages/mcp/src/tools/agnostic-client.ts`

---

## Priority 6 — Health Endpoint Enhancements ✅ Implemented

`GET /health` exists but only returns `{ status, timestamp }`. Extend it:

```python
@app.get("/health")
async def health_check():
    # Check Redis connectivity
    # Check RabbitMQ connectivity
    # Report agent heartbeat ages from Redis
    return {
        "status": "healthy" | "degraded" | "unhealthy",
        "timestamp": ...,
        "redis": "ok" | "error",
        "rabbitmq": "ok" | "error",
        "agents": {
            "qa_manager": "alive" | "stale" | "offline",
            "senior_qa": ...,
            ...
        }
    }
```

---

## Priority 7 — CORS Configuration ✅ Implemented

Add explicit CORS headers so YEOMAN dashboard (running on a different port) can
call the Agnostic API from the browser if needed:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:18789", "http://localhost:3001"],  # YEOMAN ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Priority 8 — A2A Protocol Receive Endpoint ✅ Implemented

Implement `POST /api/v1/a2a/receive` so YEOMAN can delegate QA tasks via the A2A
(Agent-to-Agent) protocol instead of REST. This enables Agnostic agents to appear
as first-class peers in YEOMAN's delegation tree.

**Add to `webgui/api.py`:**

```python
from pydantic import BaseModel

class A2AMessage(BaseModel):
    id: str
    type: str          # "a2a:delegate", "a2a:heartbeat", etc.
    fromPeerId: str
    toPeerId: str
    payload: dict
    timestamp: int     # Unix milliseconds

@api_router.post("/api/v1/a2a/receive")
async def receive_a2a_message(
    msg: A2AMessage,
    user: dict = Depends(get_current_user),
):
    """Receive an A2A protocol message from a YEOMAN peer."""
    if msg.type == "a2a:delegate":
        # Extract QA task from payload and route to the task queue
        # Payload shape from YEOMAN:
        # {
        #   "task_type": "qa",
        #   "title": str,
        #   "description": str,
        #   "target_url": str | None,
        #   "priority": "critical" | "high" | "medium" | "low",
        #   "agents": list[str],   # [] = all agents
        #   "standards": list[str]
        # }
        payload = msg.payload
        task_req = TaskSubmitRequest(
            title=payload.get("title", "A2A QA Task"),
            description=payload.get("description", ""),
            target_url=payload.get("target_url"),
            priority=payload.get("priority", "high"),
            agents=payload.get("agents", []),
            standards=payload.get("standards", []),
        )
        result = await submit_task(task_req, user)
        return {"accepted": True, "task_id": result.task_id, "message_id": msg.id}

    if msg.type == "a2a:heartbeat":
        return {"accepted": True, "message_id": msg.id, "timestamp": msg.timestamp}

    # Unknown message type — acknowledge receipt but take no action
    return {"accepted": True, "message_id": msg.id, "warning": f"Unhandled type: {msg.type}"}
```

**Also add** `GET /api/v1/a2a/capabilities` to advertise what Agnostic can do:

```python
@api_router.get("/api/v1/a2a/capabilities")
async def a2a_capabilities():
    return {
        "capabilities": [
            {"name": "qa", "description": "6-agent QA pipeline (security, performance, regression, compliance)", "version": "1.0"},
            {"name": "security-audit", "description": "OWASP, GDPR, PCI DSS, SOC 2 compliance scanning", "version": "1.0"},
            {"name": "performance-test", "description": "Load testing and P95/P99 latency profiling", "version": "1.0"},
        ]
    }
```

**YEOMAN MCP tool:** `agnostic_delegate_a2a` (shipped in `packages/mcp/src/tools/agnostic-tools.ts`).
**YEOMAN peer registration:** `POST /api/v1/a2a/peers/local` with `{ "url": "http://127.0.0.1:8000", "name": "agnostic" }`.

---

## Integration Reference

The YEOMAN MCP bridge (`packages/mcp/src/tools/agnostic-tools.ts`) calls:

| MCP Tool | Agnostic Endpoint | Status |
|----------|-------------------|--------|
| `agnostic_health` | `GET /health` | ✅ Exists |
| `agnostic_agents_status` | `GET /api/agents` | ✅ Exists |
| `agnostic_agents_queues` | `GET /api/agents/queues` | ✅ Exists |
| `agnostic_session_list` | `GET /api/sessions` | ✅ Exists |
| `agnostic_session_detail` | `GET /api/sessions/{id}` | ✅ Exists |
| `agnostic_dashboard` | `GET /api/dashboard` | ✅ Exists |
| `agnostic_generate_report` | `POST /api/reports/generate` | ✅ Exists |
| `agnostic_submit_qa` | `POST /api/tasks` | ✅ Functional (P1 + P3 implemented) |
| `agnostic_task_status` | `GET /api/tasks/{id}` | ✅ Functional (P1 implemented) |
| `agnostic_delegate_a2a` | `POST /api/v1/a2a/receive` | ✅ Implemented (P8) |

Configure in YEOMAN `.env`:
```env
MCP_EXPOSE_AGNOSTIC_TOOLS=true
AGNOSTIC_URL=http://127.0.0.1:8000
AGNOSTIC_API_KEY=your-api-key       # preferred (P2 implemented)
# AGNOSTIC_EMAIL=admin@example.com  # fallback JWT auth
# AGNOSTIC_PASSWORD=your-password   # fallback JWT auth
```
