# Port parity review: what must happen before `python-port/` can be deleted

Reviewed 2026-11-05, at agnostic 0.2.1 with agnosai 2.2.3. Deletion is not done here.

Status words: **PORTED** (a `src/` file and a test), **DELEGATED** (an agnosai or sibling file owns it), **DELEGATED\*** (the owner exists and nothing in Agnostic calls it), **DROPPED** (on purpose, with a record), **OWED** (scheduled), **GAP** (none of those). NOISE marks `.pyc` files and empty package markers.

## 1. Verdict

**Not yet, by the rule. Yes, mechanically.**

Nothing in the repo reads `python-port/`. No script, suite or CI step touches it, and `gen-presets.sh` reads `src/presets/`. So deleting it breaks no build and no test (§9). The first-party rule asks for something else: equal or better coverage. That is not met, because three of the things Agnostic exists to do are unbuilt.

Blockers, shortest honest list:

1. **M6.** 36 of 38 preset tool names resolve to nothing, and agnosai F1 means no tool would be called if they did. The registry seam is undecided (handoff §8).
2. **M7.** MCP and A2A are not started.
3. **M8.** Reports are not started, and what they report over is undecided (G5).
4. **G1 and G2, in code.** A deployment has one user, no issuable API key, and tokens that die on restart. Python's static `AGNOSTIC_API_KEY` worked, so machine access regresses.
5. **Fifteen missing records** (G3–G17). Each needs a decision. Most recommend a one-line drop; G3, G7 and G12 may turn into small code, and G14 and G15 into guides.
6. **Two extractions and one pinned rev** (§10), done in the commit before deletion.

M9's streaming is owed, but it is not a parity blocker: the event cursor already gives everything `/ws/realtime` gave except push.

If you would rather delete earlier: the only cost is that M6–M8 read the oracle through `git show`. That is a convenience loss, not a data loss, but it does set aside the roadmap's v1.0 criterion, so it is your call.

## 2. What was and was not checked

- **Files.** The snapshot holds **397 files**, not 405. The live tree's other 8 are `benchmarks/__pycache__/*.pyc`, and they are the only difference between the two lists. Every one of the 397 is assigned to exactly one row in §4, asserted by script.
- **Mechanical parts.** Routes, environment variables, tool classes and test counts came from the Python AST, not grep. The table scripts fail if a route or variable is unassigned. The Python test count comes to 1,207, matching ORACLE-AUDIT §1.
- **Removal check.** In a copy of the snapshot without `python-port/`, these all passed: `gen-presets.sh --check`, `gen-webgui.sh --check`, `check-skill.py`, `check-store-lock.py`, `check-log-lengths.py`, `check-webgui-js.sh` (80 tests).
- **Not run.** `cyrius build` and `cyrius test`, because a build re-resolves dependencies and may go to the network. That no suite needs the tree rests on grep: no `include` or file read names it. No Python ran either, and I did not run git, so I cannot confirm the 397 are all tracked. Check `git ls-files python-port | wc -l` before deleting.
- **"Did it ever work".** ORACLE-AUDIT's six audits covered `agents/backend`, `config/fleet`, `routes/crews.py`, `benchmarks/`, `tests/` and `docs/`, and §3.15 added the registry. Everything else here is my reading of the code, so "never ran" means I found no path to it, not that I watched it fail.
- **The record is thinner than it reads.** The roadmap and `CONTRIBUTING.md` point at the brief for "the three-way split of ported / delegated / dropped". The brief has no such list: only §0's headline and the tables in §2 and §5. So most of what the port silently left behind has no record, which is why the GAP list is long. Very few GAPs are lost function.
- **"By rule".** Two routes are DROPPED because a settled rule plainly covers them without naming them. Both say so.

## 3. Counts and gaps

| Status | Area rows (§4) | Files | Routes (§5) | Variables (§6) |
|---|---:|---:|---:|---:|
| PORTED | 30 | 78 | 9 ported, 10 renamed | 22 renamed |
| DELEGATED | 13 (5 unwired) | 29 (12 unwired) | | |
| DROPPED | 25 | 104 | 13 | 88 |
| OWED | 15 | 37 | 12 | 10 |
| GAP | 31 | 121 | 62 | 72 |
| NOISE | 6 | 28 | | |
| Total | 120 | 397 | 106 | 192 |

File counts are not a measure of work: 43 of the DROPPED files are Kubernetes manifests, and one OWED row of 12 files holds all 36 tools. The 31 GAP rows and 72 GAP variables merge into the 17 gaps below.

### G1. Identity provisioning

- **What it does.** Adding anyone or anything after the bootstrap admin: `/auth/api-keys*`, `/tenants*` (CRUD and tenant users), `/auth/me`, the static `AGNOSTIC_API_KEY`. In Cyrius the store functions exist (`agnostic_apikey_issue_a`, `agnostic_users_create_a`, `agnostic_tenant_create_a`) and only suites call them; `src/cli.cyr` has no such command. `Authorization: ApiKey` is implemented and no key can be issued. A deployment has exactly one user, and M5 is marked complete.
- **Did it work.** Partly. The static `AGNOSTIC_API_KEY` path ran: it is what `tests/e2e/test_smoke.py::auth_accepts_api_key` drives. Redis keys, tenant keys and local login never ran (roadmap Settled 2026-08-20; brief §7.2). Tenant create needs `super_admin`, a role nothing grants. Not one of the 86 audited defects.
- **Recommendation.** **Port.** Admin routes or a `agnostic admin` CLI, plus an ADR. Machine clients regress without it: Python had a working key, Cyrius has none. The v1.0 criterion "at least one consumer green" needs a credential a consumer can hold.

### G2. JWT signing secret

- **What it does.** `WEBGUI_SECRET_KEY` has no successor. `agnostic_jwt_init_random` generates one per start, so every restart logs everyone out, and the comment at `src/auth/jwt.cyr:73` says an operator "installs their own", but `agnostic_jwt_set_secret` has no production caller and no variable reads it. In Python, `ENVIRONMENT=production` is what demanded this key.
- **Did it work.** Yes for the variable; tokens themselves were minted only in tests (see G1).
- **Recommendation.** **Port.** One `AGNOSTIC_JWT_SECRET`, length-checked, refused at mount when short.

### G3. Crew-completion webhook

- **What it does.** `callback_url` / `callback_secret` on a crew or task: a signed POST on finish, three retries with backoff, SSRF re-check at fire time. In Cyrius `src/auth/webhook.cyr` signs and verifies and has no caller; the crew body has no such field (a 422). The roadmap lists "webhook HMAC-SHA256" as settled identity work, built, and nothing drives it.
- **Did it work.** On the success path, unit-tested (`TestFireWebhook`, `TestSSRFProtection`). ORACLE-AUDIT §5 (Call sites) records early returns skipping it. Never verified end to end.
- **Recommendation.** **Port or drop, and record it.** It is how a CI job learns a QA run finished without polling, so port at M7 on agnosai's `src/guarded_fetch.cyr`. If dropped, delete `src/auth/webhook.cyr` too.

### G4. Crew request conveniences

- **What it does.** `target_url`, `agent_keys` (run stored definitions), `QA_TEAM_SIZE`, `/tasks/{id}/retry`, and the shortcuts `/tasks/security`, `/performance`, `/regression`, `/full`. Preset expansion alone has a record (`src/engine/presets.cyr`, "No preset-to-crew expansion"). A Cyrius crew body is `{name, process, max_concurrency, agents, tasks}`, so `target_url` is a 422 and a stored definition must be read and re-sent by the client.
- **Did it work.** The wrappers ran, and every agent had `tools=[]` (§3.15). `target_url` never reached AgnosAI (§2.2).
- **Recommendation.** **Decide at M6.** A QA tool needs a target. Record `target_url` as a task field or as prose in `description`. Drop the shortcuts and retry with a recorded reason; a preset plus one task replaces them.

### G5. QA result persistence

- **What it does.** `test_sessions`, `test_results`, `test_metrics`, `test_reports` and six routes (`/test-sessions*`, `/test-results*`). Cyrius stores crew outcomes only; there is no test-level result. M8 owes "quality trends and comparison reports" and does not say what they are computed over.
- **Did it work.** A passive store. No production code writes these tables except the POST routes themselves; `create_report` and `add_metric` have no caller outside tests.
- **Recommendation.** **Decide before M8 starts.** Either reports read crew outcomes (record it, drop the routes), or M8 grows a result model. The patra limits at roadmap M8 apply.

### G6. Scheduled reports and delivery

- **What it does.** APScheduler jobs, cron triggers, a job store, delivery by webhook, Slack and SMTP; `/reports/scheduled*`; 19 environment variables. M8 lists export, trends and comparison only. Brief §5.2 prices SMTP and names alternatives but decides nothing.
- **Did it work.** **Never.** The daily and weekly jobs call `ReportType("comprehensive")` and `ReportType("compliance")`; neither is a member, so both raise before any report exists. Default off. Not in ORACLE-AUDIT.
- **Recommendation.** **Drop with a recorded reason** in Out of scope. A cron job calling the M8 route replaces it.

### G7. Prometheus metrics and the monitoring stack

- **What it does.** `GET /api/v1/metrics` with `METRICS_AUTH_TOKEN`, `shared/metrics.py`, `/dashboard/agent-metrics`, `/dashboard/llm`, plus compose overlays, Prometheus, Grafana, Alertmanager and Logstash configs. The roadmap says AgnosAI owns Prometheus, but `agnosai_metrics_gather` is in `lib/agnosai.cyr` and Agnostic never calls it. Cyrius exports OTLP traces only (ADRs 0018, 0020).
- **Did it work.** The route was wired, with an e2e test (`test_smoke::prometheus_metrics`). The stack was not: `monitoring/prometheus.yml` scrapes `webgui:8000/metrics`, the route is `/api/v1/metrics`, and its six agent targets on `:8080` are services the default compose does not have. There are no dashboards and no alert rules in the tree.
- **Recommendation.** **Port one route** over `agnosai_metrics_gather`, or record that OTLP is the only telemetry. Drop the stack either way.

### G8. Alerts

- **What it does.** `shared/alerts.py`: a background health monitor that fires on failures and breaker trips, by webhook, Slack and email; `GET /alerts`; `ALERT_*`.
- **Did it work.** Default off, unit-tested with mocks. Not audited.
- **Recommendation.** **Drop with a recorded reason.** Operators alert from their telemetry backend.

### G9. Dashboards and the agent monitor

- **What it does.** `/dashboard`, `/dashboard/sessions`, `/agents`, `/agents/queues`, `/sessions/search`, `webgui/dashboard.py`, `webgui/agent_monitor.py`. Partly superseded by the Crews view and `GET /api/v1/crews`. There are no long-lived agents to monitor any more, and no queue (roadmap Settled 2026-08-21).
- **Did it work.** **Not usefully.** They read `session:*:info` and `agent:*:status`, and I found no writer for either key in the tree. So sessions were always empty, agents always offline, and `/health` could never answer `healthy` (see §11). Not in ORACLE-AUDIT.
- **Recommendation.** **Drop with a recorded reason.** Keep `/sessions/search` only if the Crews view needs text search.

### G10. Engine capabilities with no Agnostic surface

- **What it does.** Definition versions and rollback, package export and import, `GET /tools`, `POST /tools/upload`, `/gpu/*`, `/fleet/*`, the `team` crew spec, `recommend_preset`. The roadmap says "Agnostic calls it"; Agnostic does not. The code exists in agnosai (`src/definitions/`, `src/fleet/`) and nothing here reaches it. `recommend_preset` has no owner anywhere.
- **Did it work.** GPU and definition routes were wired. Fleet was default off. Custom upload was the only production writer of `_REGISTRY` (§3.15).
- **Recommendation.** **Record per item.** Nothing is lost on deletion, since the logic is in agnosai. Recommend: surface `GET /tools` with M6 (the gate wants it); drop the rest for 1.0. Custom upload needs a sandbox answer before it could come back.

### G11. Tenant limits

- **What it does.** `TENANT_DEFAULT_RATE_LIMIT`, per-tenant 429 on `/tasks`, `A2A_RATE_LIMIT`, plan and quota fields on tenants. Cyrius rate-limits login only.
- **Did it work.** The Redis rate limit was wired under `MULTI_TENANT_ENABLED`. `check_quota` and `is_within_trial` have no caller.
- **Recommendation.** **Defer to agnosai F5 and record it.** Drop quotas, which never ran.

### G12. Audit vocabulary

- **What it does.** Python audited login failure, API-key use and rate-limit hits. Cyrius audits `auth.login` on success and ten other actions, and no refusal: a failed login, a 401 and a 403 leave no entry.
- **Did it work.** Login failure and key use were emitted. `PERMISSION_DENIED` and `PATH_TRAVERSAL_BLOCKED` are enum members nothing emits.
- **Recommendation.** **Port failed login**, bounded so the trail is not a write amplifier (each entry is an fsync). Take this to the v1.0 security audit.

### G13. AGNOS client integrations

- **What it does.** `shared/agnos_{audit,dashboard_bridge,memory,rag_client,reasoning,recording_client,rpc_client,screen_client,vector_client}.py`, `config/agnos_environment.py`, `/rpc/*`, `/dashboard/recordings`. ADR 0002 covers process registration only.
- **Did it work.** `agnos_memory`, `agnos_rag_client`, `agnos_reasoning`, `agnos_screen_client` and `agnos_vector_client` were never used: their only reference is a shutdown `close()`. The rest were default off in code.
- **Recommendation.** **Drop with one recorded line.** ADR 0002's tool registrar is the daimon path that survives.

### G14. Deployment path and TLS

- **What it does.** Dockerfile, single-node compose, supervisord, and Caddy TLS with provided certs or ACME. Brief §2 and the roadmap drop the multi-container topology and Kubernetes. Nothing says how the single binary is deployed, and nothing says who terminates TLS: the server speaks plain HTTP (`run_pooled_tls` allocates no request arena, handoff §5), and `AGNOSTIC_AUTH=required` on `AGNOSTIC_ADDR=any` sends bearer tokens in the clear unless proxied.
- **Did it work.** Unverified. ORACLE-AUDIT §3.10, §3.12 and §5 record a broken quick start, overrides for services that no longer exist, and `Dockerfile.agnos` on a local-only tag.
- **Recommendation.** **Port as a guide**: binary, reverse proxy, unit file. A small image is optional. Record that TLS is the proxy's job. Zugot's recipe is owed separately.

### G15. Operator documentation and the Python docs

- **What it does.** No Cyrius document lists the 22 variables `src/config.cyr` reads, and there is no `.env.example` or deployment guide. `docs/guides/getting-started.md` is near its scaffold form and `docs/examples/` is empty though CLAUDE.md lists it. The 57 Python doc files, 29 ADRs among them, have no recorded fate.
- **Did it work.** Python's docs were unreliable (ORACLE-AUDIT §1.1).
- **Recommendation.** **Write a configuration reference** before 1.0 and record that the Python docs live in git only.

### G16. Preset writes

- **What it does.** `POST` and `DELETE /presets`. `src/routes/presets.cyr` says a user-created preset "belongs with M4". M4 closed without it and no roadmap item carries it.
- **Did it work.** Create ran, and running a created preset 404s (same comment).
- **Recommendation.** **Drop with a recorded reason.** Agnostic's library is canonical and compiled in; saved definitions and Swarm Command's saved swarms cover the need.

### G17. Small leftovers

- **What it does.** `config/testing_targets.json` (no reader), `examples/*.json` (the dead chat format), `.github` issue and PR templates plus the dependency-update workflow, `scripts/run-e2e.sh`, `scripts/smoke_tests.py`, `tests/load/locustfile.py`. No CI step boots the server and probes it: `help` and `api schema` exit without serving.
- **Did it work.** Examples and targets never fed anything.
- **Recommendation.** **Drop by one line**, except add a boot-and-probe step to CI, which is cheap and catches what socketpair suites cannot.

## 4. Area by area

### agents (50 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `agents/analyst/__init__.py`, `agents/analyst/__pycache__/__init__.cpython-314.pyc`, `agents/analyst/__pycache__/qa_analyst.cpython-314.pyc`, `agents/junior/__pycache__/junior_qa.cpython-314.pyc`, `agents/performance/__init__.py`, `agents/senior/__pycache__/senior_qa.cpython-314.pyc` | 6 | NOISE |  | `.pyc` and empty package markers |
| `agents/base.py` | 1 | PORTED | `src/engine/agentdef.cyr`; `tests/agentdef.tcyr`, `tests/crew_request.tcyr` | `AgentDefinition` only. `BaseAgent`'s run loop is DELEGATED to agnosai `src/core/agent.cyr`, `src/orchestrator/crew_runner.cyr`; `delegate_to` to `src/tools/builtin/delegate.cyr` |
| `agents/constants.py` | 1 | PORTED | `agnostic_key_is_valid` in `src/engine/agentdef.cyr`, domains in `src/engine/presets.cyr`; `tests/agentdef.tcyr` (`agentdef/valid`), `tests/presets.tcyr` (`presets/domain`) |  |
| `agents/status.py` | 1 | PORTED | `src/engine/outcome.cyr`; `tests/outcome.tcyr` | Plus `interrupted` (ADR 0013) |
| `agents/factory.py` | 1 | PORTED | `src/engine/definitions.cyr`, `src/engine/presets.cyr`; `tests/agentdef.tcyr`, `tests/presets.tcyr` | YAML and file loading is DELEGATED* to agnosai `src/definitions/loader.cyr` |
| `agents/crew_assembler.py` | 1 | DELEGATED\* | agnosai `src/definitions/assembler.cyr`, `tests/definitions_assembler.tcyr` | Nothing here calls it. `recommend_preset` has no owner. G10 |
| `agents/packaging.py` | 1 | DELEGATED\* | agnosai `src/definitions/packaging.cyr`, `tests/definitions_packaging.tcyr` | Nothing here calls it. G10 |
| `agents/versioning.py` | 1 | DELEGATED\* | agnosai `src/definitions/versioning.cyr`, `tests/definitions_versioning.tcyr` | In-memory there. Cyrius has a revision and ETag (`router/definition-revisions`), no history. G10 |
| `agents/tool_registry.py` | 1 | DELEGATED | agnosai `src/tools/registry.cyr`, `src/tools/remote_registry.cyr` | Who registers QA tools is undecided (handoff §8). Upload half: G10 |
| `agents/tool_sandbox.py` | 1 | DELEGATED | kavach, through agnosai `src/sandbox/kavach_bridge.cyr` | Roadmap M6; `first-party-standards.md:76` |
| `agents/backend/__init__.py`, `agents/backend/base.py` | 2 | PORTED | `src/engine/outcome.cyr`; `tests/outcome.tcyr` | Design lesson 1 |
| `agents/backend/agnosai_backend.py` | 1 | PORTED | `src/engine/crew.cyr`, `src/engine/request.cyr`; `tests/crews_route.tcyr`, `tests/crew_request.tcyr` | In-process, so no client. ORACLE-AUDIT §3.1–3.3, §3.6 and §3.11 designed out |
| `agents/backend/crewai_backend.py`, `agents/backend/router.py` | 2 | DROPPED | Brief §2 (agnosai replaces CrewAI), §7 D1 | One backend |
| `agents/definitions/presets/` | 18 | PORTED | `src/presets/*.json`; `tests/presets.tcyr` | 18 of 18 byte-identical (§7) |
| `agents/` | 12 | OWED | M6 | The 36 tool classes, role wrappers, Celery tasks. Every tool is a fresh implementation (roadmap M6) |

### config (23 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `config/__init__.py`, `config/__pycache__/environment.cpython-314.pyc`, `config/__pycache__/llm_integration.cpython-314.pyc` | 3 | NOISE |  |  |
| `config/agent_registry.py` | 1 | PORTED | `src/engine/presets.cyr`; `tests/presets.tcyr` | `route_task` is DELEGATED to agnosai `src/orchestrator/scoring.cyr` |
| `config/agnos_agent_registration.py` | 1 | DROPPED | ADR 0002 | Deferred. The tool registrar is owed at M7 |
| `config/agnos_environment.py` | 1 | GAP | G13 |  |
| `config/agnos_token_budget.py` | 1 | DELEGATED | hoosh (brief §2); agnosai `src/orchestrator/budget.cyr` | Enforced budgets wait on agnosai F5 |
| `config/environment.py` | 1 | PORTED | `src/config.cyr`; `tests/config.tcyr` | Redis, RabbitMQ and Celery half dropped: brief §5.2, roadmap Settled 2026-08-21 |
| `config/fleet/shim.py` | 1 | DROPPED | ORACLE-AUDIT §2.3; brief §4 | Dead branch against routes that never existed |
| `config/fleet/__init__.py`, `config/fleet/coordinator.py`, `config/fleet/node.py`, `config/fleet/placement.py`, `config/fleet/registry.py`, `config/fleet/relay.py`, `config/fleet/state.py` | 7 | DELEGATED\* | agnosai `src/fleet/` (`coordinator`, `placement`, `registry`, `relay`, `state`), `tests/fleet_*.tcyr` | Nothing here calls it. G10 |
| `config/gpu.py`, `config/gpu_scheduler.py` | 2 | DELEGATED\* | ai-hwaccel (brief §2); agnosai `src/fleet/gpu.cyr`, `tests/fleet_gpu.tcyr` | Agnostic forwards `gpu_required`, `gpu_preferred`, `gpu_memory_min_mb` only. G10 |
| `config/llm_integration.py`, `config/local_inference.py` | 2 | DELEGATED | agnosai `src/llm/hoosh.cyr`, `src/llm/router.cyr`, `src/llm/retry.cyr` | Brief §2 |
| `config/model_manager.py`, `config/models.json` | 2 | DELEGATED | hoosh (brief §2) | No agnosai file: hoosh is a service |
| `config/testing_targets.json` | 1 | GAP | G17 | No reader in the tree |

### shared (34 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `shared/__init__.py`, `shared/database/__init__.py` | 2 | NOISE |  |  |
| `shared/audit.py` | 1 | PORTED | `src/engine/audit.cyr`; `tests/audit.tcyr` | A tamper-evident chain where Python logged JSON. Narrower vocabulary: G12 |
| `shared/context.py` | 1 | PORTED | `src/trace.cyr`; `tests/trace.tcyr` |  |
| `shared/crewai_compat.py` | 1 | DROPPED | Brief §2 |  |
| `shared/data_generation_service.py` | 1 | OWED | M6 | No importer in Python; intent for the two data-generator tools |
| `shared/database/models.py`, `shared/database/repository.py` | 2 | GAP | G5 | Reports half owed at M8 |
| `shared/database/tenant_repository.py`, `shared/database/tenants.py` | 2 | PORTED | `src/auth/tenant.cyr`; `tests/authz.tcyr` (`tenant/*`) | Library only, no route: G1. Limits: G11 |
| `shared/logging_config.py` | 1 | PORTED | `src/log.cyr`; `tests/log.tcyr` | No importer in Python |
| `shared/agent_metrics.py`, `shared/metrics.py` | 2 | GAP | G7 |  |
| `shared/alerts.py` | 1 | GAP | G8 |  |
| `shared/resilience.py` | 1 | DELEGATED | agnosai `src/llm/retry.cyr`; hoosh failover (brief §2) | `GracefulShutdown` is in `src/server/serve.cyr`, untested (§8) |
| `shared/ssrf.py` | 1 | DELEGATED | agnosai `src/server/ssrf.cyr`, `src/guarded_fetch.cyr` | No importer in Python |
| `shared/telemetry.py` | 1 | PORTED | `src/trace.cyr`, agnosai `src/telemetry/otlp.cyr`; `tests/trace.tcyr`, `tests/server_span.tcyr` | ADRs 0018, 0020 |
| `shared/version.py` | 1 | PORTED | `GET /ready`; `tests/health.tcyr` (`routes/version`) |  |
| `shared/agnos_audit.py`, `shared/agnos_dashboard_bridge.py`, `shared/agnos_memory.py`, `shared/agnos_rag_client.py`, `shared/agnos_reasoning.py`, `shared/agnos_recording_client.py`, `shared/agnos_rpc_client.py`, `shared/agnos_screen_client.py`, `shared/agnos_vector_client.py` | 9 | GAP | G13 |  |
| `shared/yeoman_mcp_server.py` | 1 | OWED | M7 | Daimon tool registrar (ADR 0002). The SecureYeoman half is dropped by brief §7.3 |
| `shared/yeoman_a2a_client.py`, `shared/yeoman_audit.py`, `shared/yeoman_dlp.py`, `shared/yeoman_event_stream.py`, `shared/yeoman_jwt.py`, `shared/yeoman_schemas.py` | 6 | DROPPED | Brief §7.3; roadmap Out of scope (SY shim) | DLP to hoosh (brief §2). JWT to the IdP seam, `agnostic_authn_set_external`, `tests/loginguard.tcyr`. Schemas: see §10 |

### webgui (40 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `webgui/__init__.py`, `webgui/routes/__init__.py` | 2 | NOISE |  |  |
| `webgui/app.py` | 1 | DROPPED | Brief §7 D3 | The Chainlit chat. `/health`, `/ready` PORTED (`src/routes/health.cyr`, `tests/health.tcyr`, ADR 0001). CORS dropped by ADRs 0005, 0006. `/ws/realtime` owed at M9 |
| `webgui/api.py` | 1 | PORTED | `src/http/router.cyr`; `tests/router.tcyr` |  |
| `webgui/auth/__init__.py`, `webgui/auth/models.py`, `webgui/auth/permission_validator.py`, `webgui/auth/token_manager.py` | 4 | PORTED | `src/auth/authn.cyr`, `jwt.cyr`, `perm.cyr`, `crypto.cyr`; `tests/authn.tcyr`, `jwt.tcyr`, `authz.tcyr`, `crypto.tcyr` | Refresh and blacklist dropped by rule (roadmap Settled 2026-08-20) |
| `webgui/auth/api_keys.py` | 1 | PORTED | `src/auth/store.cyr`; `tests/authstore.tcyr` | Library only, no route: G1 |
| `webgui/auth/oauth_provider.py` | 1 | DROPPED | Roadmap Settled 2026-08-20 | Three unreachable providers |
| `webgui/routes/auth.py` | 1 | PORTED | `src/routes/auth.cyr`, `src/auth/ratelimit.cyr`; `tests/loginroute.tcyr`, `tests/loginguard.tcyr` | Login only. Rest: G1 |
| `webgui/routes/crews.py` | 1 | PORTED | `src/routes/crews.cyr`, `src/engine/ledger.cyr`, `crewstore.cyr`; `tests/crews_route.tcyr`, `crew_tenancy.tcyr`, `ledger.tcyr`, `crewstore.tcyr` | ORACLE-AUDIT §3.1–3.5 designed out. Fields: G4 |
| `webgui/routes/definitions.py` | 1 | PORTED | `src/routes/definitions.cyr`, `presets.cyr`; `tests/agentdef.tcyr`, `tests/router.tcyr` | CRUD and reads. Rest: G10, G16 |
| `webgui/routes/dependencies.py` | 1 | PORTED | `src/auth/authn.cyr`, `src/http/guard.cyr`; `tests/authn.tcyr`, `tests/plugindata.tcyr` | SSRF half goes with G3 |
| `webgui/routes/tasks.py` | 1 | OWED | M7 | A2A half. Task routes renamed onto crews. Webhook G3, shortcuts G4 |
| `webgui/routes/mcp.py` | 1 | OWED | M7 | 34 tools: see §7, §10 |
| `webgui/routes/reports.py` | 1 | OWED | M8 | Scheduled half: G6 |
| `webgui/exports.py`, `webgui/history.py` | 2 | OWED | M8 | HTML, CSV, JSON; PDF undecided (roadmap M8) |
| `webgui/routes/sessions.py` | 1 | OWED | M8 | Compare. Lists renamed onto crews. Search: G9 |
| `webgui/routes/persistence.py` | 1 | GAP | G5 | Trends and diff owed at M8 |
| `webgui/routes/tenants.py` | 1 | GAP | G1 |  |
| `webgui/routes/fleet.py`, `webgui/routes/gpu.py` | 2 | GAP | G10 |  |
| `webgui/agent_monitor.py`, `webgui/dashboard.py`, `webgui/routes/agents.py`, `webgui/routes/dashboard.py` | 4 | GAP | G9 | Registration half: ADR 0002. Metrics half: G7 |
| `webgui/routes/rpc.py` | 1 | GAP | G13 |  |
| `webgui/routes/integration.py`, `webgui/routes/yeoman_webhooks.py` | 2 | DROPPED | Brief §7.3; roadmap Out of scope (SY shim) |  |
| `webgui/realtime.py` | 1 | OWED | M9 | Streaming. The cursor already covers replay (ADR 0009) |
| `webgui/scheduled_reports.py` | 1 | GAP | G6 |  |
| `webgui/static/css/dashboard.css`, `webgui/static/css/realtime.css`, `webgui/static/css/reports.css`, `webgui/static/js/dashboard.js`, `webgui/static/templates/dashboard.html`, `webgui/static/templates/reports/executive_summary.html` | 6 | DROPPED | Brief §7 D3 | Never served: no static mount exists |
| `webgui/Dockerfile` | 1 | GAP | G14 |  |

### tests (81 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `tests/__init__.py`, `tests/benchmarks/__init__.py`, `tests/e2e/__init__.py`, `tests/e2e/conftest.py`, `tests/fixtures/__init__.py`, `tests/fixtures/common.py`, `tests/integration/__init__.py`, `tests/k8s/__init__.py`, `tests/load/__init__.py`, `tests/unit/__init__.py`, `tests/unit/conftest.py`, `tests/unit/integration/__init__.py`, `tests/unit/tools/__init__.py`, `tests/unit/webgui/__init__.py` | 14 | NOISE |  |  |
| `tests/k8s/test_k8s_manifests.py` | 1 | DROPPED | Roadmap Out of scope |  |
| `tests/benchmarks/bench_definitions.py`, `tests/benchmarks/bench_packaging.py` | 2 | DROPPED | Roadmap Out of scope; ORACLE-AUDIT §4 |  |
| `tests/load/locustfile.py` | 1 | GAP | G17 |  |
| `tests/unit/test_data_generation.py`, `tests/unit/tools/test_junior_qa_tools.py`, `tests/unit/tools/test_performance_tools.py`, `tests/unit/tools/test_qa_analyst_tools.py`, `tests/unit/tools/test_qa_manager_tools.py`, `tests/unit/tools/test_security_compliance_tools.py`, `tests/unit/tools/test_senior_qa_tools.py` | 7 | OWED | M6 |  |
| `tests/unit/test_history.py`, `tests/unit/test_session_diff.py`, `tests/unit/webgui/test_report_generator.py` | 3 | OWED | M8 |  |
| `tests/unit/integration/test_yeoman_websocket.py`, `tests/unit/test_message_buffer.py`, `tests/unit/webgui/test_realtime.py` | 3 | OWED | M9 |  |
| `tests/e2e/test_a2a_roundtrip.py` | 1 | OWED | M7 |  |
| `tests/e2e/test_fleet_lockstep.py`, `tests/e2e/test_fleet_scaling.py`, `tests/unit/test_crew_assembler.py`, `tests/unit/test_fleet.py`, `tests/unit/test_gpu.py`, `tests/unit/test_model_manager.py`, `tests/unit/test_packaging_versioning.py`, `tests/unit/test_resilience.py` | 8 | DELEGATED | agnosai `tests/fleet_*.tcyr`, `llm_*.tcyr`, `definitions_*.tcyr` | See §8 |
| `tests/unit/test_crewai_compat.py` | 1 | DROPPED | Brief §2 |  |
| `tests/integration/test_agent_communication.py`, `tests/unit/integration/test_yeoman_integration.py`, `tests/unit/integration/test_yeoman_schemas.py` | 3 | DROPPED | Brief §7.3; §2 (Redis, Celery) |  |
| `tests/unit/integration/test_agnos_agent_registration.py` | 1 | DROPPED | ADR 0002 |  |
| `tests/e2e/test_agnos_gateway.py`, `tests/unit/integration/test_agnos_clients.py`, `tests/unit/integration/test_agnos_rpc.py`, `tests/unit/integration/test_agnos_vector_client.py` | 4 | GAP | G13 | The gateway round trip still matters: §8 |
| `tests/unit/test_agent_metrics.py`, `tests/unit/test_metrics.py` | 2 | GAP | G7 |  |
| `tests/unit/test_alerts.py` | 1 | GAP | G8 |  |
| `tests/unit/test_agent_monitor.py`, `tests/unit/webgui/test_dashboard.py` | 2 | GAP | G9 |  |
| `tests/unit/webgui/test_report_delivery.py`, `tests/unit/webgui/test_scheduled_reports.py` | 2 | GAP | G6 |  |
| `tests/unit/test_database_models.py` | 1 | GAP | G5 |  |
| `tests/unit/test_observability.py` | 1 | GAP | G12 | Mixed: see §8 |
| `tests/e2e/test_crew_dual_backend.py`, `tests/e2e/test_smoke.py`, `tests/e2e/test_task_lifecycle.py`, `tests/unit/test_agent_registry.py`, `tests/unit/test_agnosai_backend.py`, `tests/unit/test_api_validation.py`, `tests/unit/test_audit.py`, `tests/unit/test_backend_router.py`, `tests/unit/test_base_agent.py`, `tests/unit/test_config_environment.py`, `tests/unit/test_constants.py`, `tests/unit/test_logging_config.py`, `tests/unit/test_permission_validator.py`, `tests/unit/test_team_config.py`, `tests/unit/test_tenant.py`, `tests/unit/test_tenant_isolation.py`, `tests/unit/test_token_manager.py`, `tests/unit/webgui/test_api_routes.py`, `tests/unit/webgui/test_app.py`, `tests/unit/webgui/test_auth.py`, `tests/unit/webgui/test_crews_api.py`, `tests/unit/webgui/test_definitions_api.py`, `tests/unit/webgui/test_task_routes.py` | 23 | PORTED | See §8 | Crews, definitions, presets, auth, tenancy, health, config, logging, audit |

### docs (57 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docs/deployment/kubernetes.md` | 1 | DROPPED | Roadmap Out of scope |  |
| `docs/development/benchmarks.md` | 1 | DROPPED | ORACLE-AUDIT §4 |  |
| `docs/agents/index.md` | 1 | OWED | M6 | Role and tool intent |
| `docs/` | 54 | GAP | G15 | No recorded fate. All Python-stack prose; recoverable from git |

### scripts (7 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `scripts/bump-version.sh` | 1 | PORTED | `scripts/version-bump.sh` |  |
| `scripts/build-release.sh` | 1 | PORTED | `.github/workflows/release.yml` |  |
| `scripts/export-openapi.py` | 1 | PORTED | `scripts/gen-api-schema.sh`, `agnostic api schema`; `tests/api_schema.tcyr` | ADR 0015 |
| `scripts/generate-sdk.sh` | 1 | DROPPED | ADR 0015 (OpenAPI rejected until field types exist) |  |
| `scripts/build-docker.sh` | 1 | GAP | G14 |  |
| `scripts/run-e2e.sh`, `scripts/smoke_tests.py` | 2 | GAP | G17 |  |

### benchmarks (8 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `benchmarks/__init__.py`, `benchmarks/__main__.py`, `benchmarks/conftest.py`, `benchmarks/report.py`, `benchmarks/run.py`, `benchmarks/runner.py`, `benchmarks/scenarios.py`, `benchmarks/test_crewai_vs_agnosai.py` | 8 | DROPPED | Roadmap Out of scope; ORACLE-AUDIT §4 | Cyrius baseline: `tests/agnostic.bcyr`, `BENCHMARKS.md` |

### docker (16 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docker-compose.dev.yml`, `docker-compose.old-style.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`, `docker/Dockerfile.agent`, `docker/Dockerfile.agnos`, `docker/Dockerfile.base`, `docker/pg-init.sh` | 8 | DROPPED | Brief §2 (patra row); roadmap Out of scope | Multi-container topology |
| `.dockerignore`, `Dockerfile`, `docker-compose.tls.yml`, `docker-compose.yml`, `docker/README.md`, `docker/agent-entrypoint.sh`, `docker/entrypoint.sh`, `docker/supervisord.conf` | 8 | GAP | G14 | Single-node path and TLS |

### k8s (43 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `k8s/` | 43 | DROPPED | Roadmap Out of scope (Kubernetes topology parity) |  |

### monitoring (5 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docker-compose.monitoring.yml`, `monitoring/alertmanager.yml`, `monitoring/grafana/dashboards/dashboard.yml`, `monitoring/grafana/datasources/prometheus.yml`, `monitoring/prometheus.yml` | 5 | GAP | G7 | No dashboards, no rules |

### logging (2 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docker-compose.logging.yml`, `logging/logstash.conf` | 2 | GAP | G7 | Logs are JSON on stdout (`src/log.cyr`) |

### alembic (6 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `alembic.ini`, `alembic/README`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/a1b2c3d4e5f6_apscheduler_jobs_table.py`, `alembic/versions/db8d3fe1686e_initial_schema.py` | 6 | DROPPED | Brief §2 (patra replaces PostgreSQL and SQLAlchemy) | No data exists to migrate (`state.md`, Consumers: none). A patra migration story is unrecorded: it needs one before 1.0 freezes the file format |

### tls/certs (2 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `certs/generate-certs.sh`, `tls/rabbitmq/rabbitmq.conf` | 2 | DROPPED | Brief §5.2 (AMQP), §2 (Redis) | Internal Redis and RabbitMQ TLS. Server TLS: G14 |

### examples (2 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `examples/api_testing_example.json`, `examples/ecommerce_checkout_testing.json` | 2 | GAP | G17 |  |

### public (1 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `public/favicon.svg` | 1 | DROPPED | Brief §7 D3 | The shell has its own inline icon |

### top-level (20 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `.github/actions/setup-python-env/action.yml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml` | 3 | PORTED | `.github/workflows/ci.yml`, `release.yml` | Rewritten for Cyrius |
| `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`, `.github/pull_request_template.md`, `.github/workflows/dependency-update.yml` | 4 | GAP | G17 |  |
| `.pre-commit-config.yaml` | 1 | PORTED | `scripts/check-clean.sh` |  |
| `.env.example` | 1 | GAP | G15 |  |
| `.gitignore` | 1 | NOISE |  |  |
| `CHANGELOG.md` | 1 | GAP | G15 |  |
| `LICENSE`, `README.md`, `VERSION` | 3 | PORTED | Root `LICENSE`, `VERSION`, `README.md` | CalVer to SemVer (`state.md`) |
| `agnostic.agpkg.toml` | 1 | OWED | v1.0 criterion (Zugot recipe), not a milestone |  |
| `chainlit.md` | 1 | DROPPED | Brief §7 D3 |  |
| `pyproject.toml`, `requirements-docker.txt`, `requirements.txt` | 3 | DROPPED | `CONTRIBUTING.md:5-8`; ORACLE-AUDIT §3.13 |  |
| `run_tests.py` | 1 | PORTED | `cyrius test` |  |

## 5. Comparison 1: routes

Python exposes **106** routes: 103 under `/api/v1`, plus `/health`, `/ready` and `/ws/realtime`. The Chainlit chat handlers in `webgui/app.py` are not HTTP routes; D3 replaces them. `schema.json` lists **27** method-and-path pairs.

Result: 9 ported, 10 renamed, 13 dropped, 12 owed, 62 gap. Line numbers are from `webgui/`.

Routes only Cyrius has: `GET /api/v1/crews/:id/events`, `GET /api/v1/crews/:id/plan`, `GET /api/v1/audit`, `GET /api/v1/audit/entries`, `GET /api/v1/plugins`, `PUT /api/v1/plugins/:id`, `GET /api/v1/plugins/:id/data`, `GET /api/v1/plugins/:id/data/:key`, `PUT /api/v1/plugins/:id/data/:key`, `DELETE /api/v1/plugins/:id/data/:key`, `GET /ui`, `GET /ui/`, `GET /ui/plugins/:id`.

| Source | Method | Python path | Status | Target or record | Note |
|---|---|---|---|---|---|
| `routes/agents.py:47` | GET | `/api/v1/agents/registration-status` | dropped | ADR 0002 |  |
| `routes/agents.py:62` | POST | `/api/v1/agents/register-agnostic` | dropped | ADR 0002 |  |
| `routes/agents.py:81` | POST | `/api/v1/agents/deregister-agnostic` | dropped | ADR 0002 |  |
| `routes/agents.py:98` | GET | `/api/v1/agents/queues` | gap | G9 | No queue survives (roadmap Settled 2026-08-21), but the route's fate is unrecorded |
| `routes/agents.py:107` | GET | `/api/v1/agents/{agent_name}` | gap | G9 |  |
| `routes/agents.py:120` | GET | `/api/v1/agents` | gap | G9 |  |
| `routes/auth.py:88` | POST | `/api/v1/auth/login` | ported | `POST /api/v1/auth/login` | Answers `token`, not `access_token`; no refresh token |
| `routes/auth.py:126` | POST | `/api/v1/auth/refresh` | dropped | Roadmap Settled 2026-08-20, by rule | Not named. No refresh token ever existed. Cyrius tokens last 3600 s |
| `routes/auth.py:139` | POST | `/api/v1/auth/logout` | dropped | Roadmap Settled 2026-08-20, by rule | Not named. The shell drops its token; revocation is the role re-read |
| `routes/auth.py:156` | GET | `/api/v1/auth/me` | gap | G1 |  |
| `routes/auth.py:171` | POST | `/api/v1/auth/api-keys` | gap | G1 |  |
| `routes/auth.py:197` | GET | `/api/v1/auth/api-keys` | gap | G1 |  |
| `routes/auth.py:218` | DELETE | `/api/v1/auth/api-keys/{key_id}` | gap | G1 |  |
| `routes/crews.py:681` | POST | `/api/v1/crews` | ported | `POST /api/v1/crews` | 201 to 202. Body is agents and tasks. Fields: G4. Webhook: G3 |
| `routes/crews.py:856` | GET | `/api/v1/crews/{crew_id}` | ported | `GET /api/v1/crews/:id` |  |
| `routes/crews.py:877` | GET | `/api/v1/crews` | ported | `GET /api/v1/crews` | `offset` to a cursor (ADR 0008) |
| `routes/crews.py:930` | POST | `/api/v1/crews/{crew_id}/cancel` | ported | `POST /api/v1/crews/:id/cancel` | Stops work (design lesson 4) |
| `routes/dashboard.py:105` | GET | `/api/v1/dashboard` | gap | G9 |  |
| `routes/dashboard.py:115` | GET | `/api/v1/dashboard/sessions` | gap | G9 | Read a key nothing writes |
| `routes/dashboard.py:126` | GET | `/api/v1/dashboard/agents` | gap | G9 |  |
| `routes/dashboard.py:137` | GET | `/api/v1/dashboard/metrics` | gap | G9 |  |
| `routes/dashboard.py:147` | GET | `/api/v1/dashboard/agent-metrics` | gap | G7 |  |
| `routes/dashboard.py:157` | GET | `/api/v1/dashboard/llm` | gap | G7 |  |
| `routes/dashboard.py:167` | GET | `/api/v1/dashboard/llm-gateway` | gap | G9 | hoosh serves its own health |
| `routes/dashboard.py:178` | GET | `/api/v1/dashboard/yeoman` | dropped | Brief §7.3; roadmap Out of scope |  |
| `routes/dashboard.py:197` | GET | `/api/v1/dashboard/unified` | dropped | Brief §7.3; roadmap Out of scope | AGNOSTIC plus YEOMAN view |
| `routes/dashboard.py:245` | GET | `/api/v1/dashboard/widget` | dropped | Brief §7.3; roadmap Out of scope | Embeddable for YEOMAN |
| `routes/dashboard.py:339` | GET | `/api/v1/dashboard/token-budget` | dropped | Brief §2 (hoosh owns budgets) |  |
| `routes/dashboard.py:383` | GET | `/api/v1/dashboard/recordings` | gap | G13 |  |
| `routes/dashboard.py:407` | GET | `/api/v1/alerts` | gap | G8 |  |
| `routes/dashboard.py:443` | GET | `/api/v1/metrics` | gap | G7 |  |
| `routes/definitions.py:151` | GET | `/api/v1/definitions` | renamed | `GET /api/v1/agents/definitions` | No `domain`, `limit`, `offset` |
| `routes/definitions.py:213` | GET | `/api/v1/definitions/{agent_key}` | renamed | `GET /api/v1/agents/definitions/:key` |  |
| `routes/definitions.py:231` | POST | `/api/v1/definitions` | renamed | `POST /api/v1/agents/definitions` | `agent_key` to `key` |
| `routes/definitions.py:265` | PUT | `/api/v1/definitions/{agent_key}` | renamed | `PUT /api/v1/agents/definitions/:key` | With `If-Match` |
| `routes/definitions.py:303` | DELETE | `/api/v1/definitions/{agent_key}` | renamed | `DELETE /api/v1/agents/definitions/:key` | With `If-Match` |
| `routes/definitions.py:336` | GET | `/api/v1/presets` | ported | `GET /api/v1/presets` | No `domain`, `size` filters |
| `routes/definitions.py:400` | GET | `/api/v1/presets/{preset_name}` | ported | `GET /api/v1/presets/:name` |  |
| `routes/definitions.py:432` | POST | `/api/v1/presets` | gap | G16 |  |
| `routes/definitions.py:479` | DELETE | `/api/v1/presets/{preset_name}` | gap | G16 |  |
| `routes/definitions.py:529` | GET | `/api/v1/definitions/{agent_key}/versions` | gap | G10 |  |
| `routes/definitions.py:543` | POST | `/api/v1/definitions/{agent_key}/versions` | gap | G10 |  |
| `routes/definitions.py:561` | POST | `/api/v1/definitions/{agent_key}/rollback` | gap | G10 |  |
| `routes/definitions.py:595` | POST | `/api/v1/packages/export` | gap | G10 |  |
| `routes/definitions.py:627` | POST | `/api/v1/packages/import` | gap | G10 |  |
| `routes/definitions.py:682` | POST | `/api/v1/tools/upload` | gap | G10 |  |
| `routes/definitions.py:716` | GET | `/api/v1/tools` | gap | G10 |  |
| `routes/fleet.py:28` | GET | `/api/v1/fleet/nodes` | gap | G10 |  |
| `routes/fleet.py:51` | GET | `/api/v1/fleet/nodes/{node_id}` | gap | G10 |  |
| `routes/fleet.py:66` | GET | `/api/v1/fleet/groups` | gap | G10 |  |
| `routes/fleet.py:78` | GET | `/api/v1/fleet/status` | gap | G10 |  |
| `routes/fleet.py:106` | GET | `/api/v1/fleet/gpu` | gap | G10 |  |
| `routes/fleet.py:139` | POST | `/api/v1/fleet/evict` | gap | G10 |  |
| `routes/gpu.py:18` | GET | `/api/v1/gpu/status` | gap | G10 |  |
| `routes/gpu.py:33` | GET | `/api/v1/gpu/devices/{device_index}` | gap | G10 |  |
| `routes/gpu.py:48` | GET | `/api/v1/gpu/memory` | gap | G10 |  |
| `routes/gpu.py:84` | GET | `/api/v1/gpu/slots` | gap | G10 |  |
| `routes/gpu.py:104` | GET | `/api/v1/gpu/inference` | gap | G10 |  |
| `routes/integration.py:31` | GET | `/api/v1/results/structured/{session_id}` | dropped | Brief §7.3; roadmap Out of scope | The result model is worth keeping: §10 |
| `routes/mcp.py:626` | GET | `/api/v1/mcp/tools` | owed | M7 | `tools/list` at `/mcp` |
| `routes/mcp.py:650` | GET | `/api/v1/mcp/server-info` | owed | M7 | MCP 2026-07-28 has no handshake |
| `routes/mcp.py:670` | POST | `/api/v1/mcp/invoke` | owed | M7 | Same path by name |
| `routes/persistence.py:120` | GET | `/api/v1/test-sessions` | gap | G5 |  |
| `routes/persistence.py:151` | POST | `/api/v1/test-sessions` | gap | G5 |  |
| `routes/persistence.py:176` | PUT | `/api/v1/test-sessions/{session_id}/status` | gap | G5 |  |
| `routes/persistence.py:199` | GET | `/api/v1/test-results` | gap | G5 |  |
| `routes/persistence.py:236` | POST | `/api/v1/test-results` | gap | G5 |  |
| `routes/persistence.py:253` | GET | `/api/v1/test-results/{session_id}/summary` | gap | G5 |  |
| `routes/persistence.py:273` | GET | `/api/v1/test-metrics/trends` | owed | M8 | Quality trends |
| `routes/persistence.py:288` | GET | `/api/v1/test-sessions/diff` | owed | M8 | Comparison reports |
| `routes/reports.py:75` | GET | `/api/v1/reports` | owed | M8 |  |
| `routes/reports.py:106` | POST | `/api/v1/reports/generate` | owed | M8 |  |
| `routes/reports.py:156` | GET | `/api/v1/reports/{report_id}/download` | owed | M8 | Path traversal re-opens here (roadmap M8) |
| `routes/reports.py:208` | GET | `/api/v1/reports/scheduled` | gap | G6 |  |
| `routes/reports.py:226` | POST | `/api/v1/reports/scheduled` | gap | G6 |  |
| `routes/reports.py:264` | DELETE | `/api/v1/reports/scheduled/{job_id}` | gap | G6 |  |
| `routes/rpc.py:67` | POST | `/api/v1/rpc/handle` | gap | G13 |  |
| `routes/rpc.py:125` | GET | `/api/v1/rpc/methods` | gap | G13 |  |
| `routes/sessions.py:36` | GET | `/api/v1/sessions` | renamed | `GET /api/v1/crews` | Read a key nothing writes |
| `routes/sessions.py:84` | GET | `/api/v1/sessions/search` | gap | G9 | Only `?status=` exists |
| `routes/sessions.py:97` | GET | `/api/v1/sessions/{session_id}` | renamed | `GET /api/v1/crews/:id` |  |
| `routes/sessions.py:109` | POST | `/api/v1/sessions/compare` | owed | M8 | Comparison reports |
| `routes/tasks.py:197` | POST | `/api/v1/tasks` | renamed | `POST /api/v1/crews` | A wrapper over `run_crew`; shape differs |
| `routes/tasks.py:257` | GET | `/api/v1/tasks/{task_id}` | renamed | `GET /api/v1/crews/:id` |  |
| `routes/tasks.py:297` | DELETE | `/api/v1/tasks/{task_id}` | renamed | `POST /api/v1/crews/:id/cancel` |  |
| `routes/tasks.py:344` | POST | `/api/v1/tasks/{task_id}/retry` | gap | G4 |  |
| `routes/tasks.py:419` | POST | `/api/v1/tasks/security` | gap | G4 |  |
| `routes/tasks.py:440` | POST | `/api/v1/tasks/performance` | gap | G4 |  |
| `routes/tasks.py:460` | POST | `/api/v1/tasks/regression` | gap | G4 |  |
| `routes/tasks.py:480` | POST | `/api/v1/tasks/full` | gap | G4 |  |
| `routes/tasks.py:523` | POST | `/api/v1/a2a/receive` | owed | M7 | A2A callback endpoint |
| `routes/tasks.py:690` | GET | `/api/v1/a2a/capabilities` | owed | M7 | Signed Agent Card |
| `routes/tenants.py:88` | GET | `/api/v1/tenants` | gap | G1 |  |
| `routes/tenants.py:127` | POST | `/api/v1/tenants` | gap | G1 |  |
| `routes/tenants.py:158` | GET | `/api/v1/tenants/{tenant_id}` | gap | G1 |  |
| `routes/tenants.py:189` | PUT | `/api/v1/tenants/{tenant_id}` | gap | G1 |  |
| `routes/tenants.py:219` | DELETE | `/api/v1/tenants/{tenant_id}` | gap | G1 |  |
| `routes/tenants.py:246` | GET | `/api/v1/tenants/{tenant_id}/users` | gap | G1 |  |
| `routes/tenants.py:282` | POST | `/api/v1/tenants/{tenant_id}/users` | gap | G1 |  |
| `routes/tenants.py:314` | DELETE | `/api/v1/tenants/{tenant_id}/users/{user_id}` | gap | G1 |  |
| `routes/yeoman_webhooks.py:276` | POST | `/api/v1/yeoman/webhooks` | dropped | Brief §7.3; roadmap Out of scope |  |
| `routes/yeoman_webhooks.py:399` | GET | `/api/v1/yeoman/events/stream` | dropped | Brief §7.3; roadmap Out of scope | M9 owes crew streaming |
| `routes/yeoman_webhooks.py:458` | GET | `/api/v1/yeoman/events` | dropped | Brief §7.3; roadmap Out of scope |  |
| `app.py` | GET | `/health` | ported | `GET /health` | Liveness only (ADR 0001); `tests/health.tcyr` |
| `app.py` | GET | `/ready` | ported | `GET /ready` | `tests/health.tcyr` |
| `app.py` | WS | `/ws/realtime` | owed | M9 | Streaming crew events; the cursor polls today |

Parameters that disappeared with a route that stayed: `domain`, `limit`, `offset` on definitions; `domain`, `size` on presets; `offset` on crews (replaced by a cursor). Also, `X-API-Key` became `Authorization: ApiKey`, and `{"detail": ...}` errors became `{"error": ...}`.

## 6. Comparison 2: configuration

Python's non-test code reads **192** names (AST over every `getenv`, `environ.get`, `environ[...]`). `src/config.cyr` reads **22**, and no other file in `src/` calls `getenv`.

Result: 22 renamed, 88 dropped, 10 owed, 72 gap. Nothing keeps its Python name, so an old `.env` applies nothing; the default port, 8000, is the only setting that carries over. Two reads are dynamic: `config/agnos_environment.py:112` (profile keys) and `webgui/routes/crews.py:210-258` (GPU variables, set per agent).

| Python names | Status | Cyrius or owner | Record |
|---|---|---|---|
| `LOG_LEVEL` | renamed | `AGNOSTIC_LOG_LEVEL` |  |
| `LOG_FORMAT` | renamed | `AGNOSTIC_LOG_FORMAT` |  |
| `AGNOS_LLM_GATEWAY_URL` | renamed | `AGNOSTIC_LLM_URL` | Brief §2 |
| `AGNOS_LLM_GATEWAY_API_KEY` | renamed | `AGNOSTIC_LLM_API_KEY` |  |
| `AGNOS_LLM_GATEWAY_ENABLED` | renamed | Implied by `AGNOSTIC_LLM_URL` | Unset is placeholder mode, disclosed |
| `AGNOSAI_EXECUTE_TIMEOUT`, `LLM_STREAM_TOTAL_TIMEOUT` | renamed | `AGNOSTIC_LLM_TIMEOUT_SECS` |  |
| `AGNOS_OTEL_ENABLED`, `AGNOS_OTEL_ENDPOINT` | renamed | `OTEL_EXPORTER_OTLP_ENDPOINT` (and `_TRACES_ENDPOINT`) | ADR 0018 |
| `AGNOS_OTEL_SERVICE_NAME` | renamed | `OTEL_SERVICE_NAME` | ADR 0018 |
| `DATABASE_ENABLED`, `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_USER` | renamed | `AGNOSTIC_DB_PATH` | Brief §2 (patra) |
| `AUDIT_LOG_ENABLED`, `AUDIT_LOG_LEVEL` | renamed | `AGNOSTIC_AUDIT_PATH`; always on |  |
| `AGNOSTIC_VERSION` | renamed | Compiled in; `GET /ready` |  |
| `LOGIN_RATE_LIMIT_MAX`, `LOGIN_RATE_LIMIT_WINDOW` | renamed | Constants in `src/auth/ratelimit.cyr` | Per IP, not per email |
| `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_SIZE`, `DB_POOL_TIMEOUT` | dropped | No pool | Brief §2 (patra) |
| `REDIS_DB`, `REDIS_HOST`, `REDIS_MAX_CONNECTIONS`, `REDIS_PASSWORD`, `REDIS_PORT`, `REDIS_URL` | dropped | No Redis | Brief §2; roadmap Settled 2026-08-21 |
| `RABBITMQ_HOST`, `RABBITMQ_PASSWORD`, `RABBITMQ_PORT`, `RABBITMQ_URL`, `RABBITMQ_USER`, `RABBITMQ_VHOST` | dropped | No AMQP | Brief §5.2 |
| `AGNOSAI_API_KEY`, `AGNOSAI_URL`, `AGNOSTIC_BACKEND` | dropped | agnosai is linked in-process | Brief §7 D1 |
| `AGNOS_LLM_GATEWAY_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL` | dropped | hoosh holds provider keys; a model is per agent (`llm_model`) | Brief §2 |
| `LLM_STREAM_CHUNK_TIMEOUT` | dropped | agnosai's own timeouts | Brief §2 |
| `AGNOS_LOCAL_INFERENCE_API_KEY`, `AGNOS_LOCAL_INFERENCE_ENABLED`, `AGNOS_LOCAL_INFERENCE_GPU_MIN_FREE_MB`, `AGNOS_LOCAL_INFERENCE_MAX_PARAMS_B`, `AGNOS_LOCAL_INFERENCE_MODELS`, `AGNOS_LOCAL_INFERENCE_PROVIDER`, `AGNOS_LOCAL_INFERENCE_URL` | dropped | hoosh routes local models | Brief §2 |
| `AGNOS_TOKEN_BUDGET_API_KEY`, `AGNOS_TOKEN_BUDGET_ENABLED`, `AGNOS_TOKEN_BUDGET_POOL`, `AGNOS_TOKEN_BUDGET_URL` | dropped | hoosh owns budgets | Brief §2; roadmap F5 |
| `AGNOS_TOOL_SANDBOX_ENABLED`, `AGNOS_TOOL_SANDBOX_MAX_MEM_MB`, `AGNOS_TOOL_SANDBOX_TIMEOUT` | dropped | kavach owns the sandbox | Roadmap M6 |
| `AGNOS_GPU_ENABLED`, `AGNOS_GPU_PROBE_INTERVAL`, `AGNOS_GPU_PROBE_PATH` | dropped | ai-hwaccel | Brief §2 |
| `AGNOS_AGENT_REGISTRATION_ENABLED`, `AGNOS_CAPABILITY_ADVERTISE_ENABLED`, `AGNOS_HEARTBEAT_INTERVAL_SECONDS` | dropped | No process registration | ADR 0002 |
| `CORS_ALLOWED_ORIGINS` | dropped | The server grants no CORS | ADRs 0005, 0006 |
| `MAX_ACTIVE_SESSIONS` | dropped | Chainlit session cap | Brief §7 D3 |
| `OAUTH2_AZURE_CLIENT_ID`, `OAUTH2_AZURE_TENANT_ID`, `OAUTH2_GITHUB_CLIENT_ID`, `OAUTH2_GITHUB_CLIENT_SECRET`, `OAUTH2_GOOGLE_CLIENT_ID` | dropped | Three unreachable providers | Roadmap Settled 2026-08-20 |
| `AGNOSTIC_EXTERNAL_URL`, `EVENT_BUFFER_MAX`, `SSE_KEEPALIVE_INTERVAL`, `WEBHOOK_MAX_BODY_SIZE`, `YEOMAN_A2A_API_KEY`, `YEOMAN_A2A_ENABLED`, `YEOMAN_A2A_URL`, `YEOMAN_AUDIT_API_KEY`, `YEOMAN_AUDIT_ENABLED`, `YEOMAN_AUDIT_URL`, `YEOMAN_COVERAGE_THRESHOLD`, `YEOMAN_DLP_API_KEY`, `YEOMAN_DLP_BLOCK_ON_FINDING`, `YEOMAN_DLP_ENABLED`, `YEOMAN_DLP_TIMEOUT`, `YEOMAN_DLP_URL`, `YEOMAN_ERROR_RATE_THRESHOLD`, `YEOMAN_EVENT_PUSH_ENABLED`, `YEOMAN_EVENT_PUSH_SECRET`, `YEOMAN_EVENT_PUSH_URL`, `YEOMAN_JWT_AUDIENCE`, `YEOMAN_JWT_ENABLED`, `YEOMAN_JWT_ISSUER`, `YEOMAN_JWT_PUBLIC_KEY`, `YEOMAN_JWT_SECRET`, `YEOMAN_MCP_API_KEY`, `YEOMAN_MCP_AUTO_REGISTER`, `YEOMAN_MCP_URL`, `YEOMAN_OIDC_DISCOVERY_URL`, `YEOMAN_PEER_ID`, `YEOMAN_PERF_DEGRADATION_FACTOR`, `YEOMAN_WEBHOOKS_ENABLED`, `YEOMAN_WEBHOOK_SECRET` | dropped | SecureYeoman surface | Brief §7.3; roadmap Out of scope |
| `AGNOSAI_BENCH_URL`, `BENCH_ROUNDS`, `CREWAI_BENCH_URL`, `OLLAMA_MODEL`, `OLLAMA_URL` | dropped | `benchmarks/` only | Roadmap Out of scope; ORACLE-AUDIT §4 |
| `AGNOS_AGENT_API_KEY`, `AGNOS_AGENT_REGISTRY_URL`, `DAIMON_MCP_AUTO_REGISTER` | owed | M7: the env-gated, default-off tool registrar | ADR 0002 |
| `MCP_SERVER_ENABLED` | owed | M7 |  |
| `A2A_RATE_LIMIT` | owed | M7, with the A2A endpoint | Limit itself: G11 |
| `REPORTS_DIR` | owed | M8 |  |
| `REALTIME_IDLE_TIMEOUT_SECONDS`, `REALTIME_MAX_MESSAGE_SIZE`, `REALTIME_STREAM_MAX_LEN`, `REALTIME_STREAM_REPLAY_LIMIT` | owed | M9 |  |
| `AGNOSTIC_API_KEY`, `DEFAULT_TENANT_ID`, `MULTI_TENANT_ENABLED` | gap | G1 |  |
| `ENVIRONMENT`, `HOME`, `WEBGUI_SECRET_KEY` | gap | G2 |  |
| `WEBHOOK_MAX_RETRIES` | gap | G3 |  |
| `QA_TEAM_SIZE` | gap | G4 |  |
| `REDIS_SCHEDULER_DB`, `REPORT_DELIVERY_MAX_RETRIES`, `REPORT_EMAIL_ENABLED`, `REPORT_EMAIL_RECIPIENTS`, `REPORT_SLACK_WEBHOOK_URL`, `REPORT_WEBHOOK_SECRET`, `REPORT_WEBHOOK_URL`, `SCHEDULED_REPORTS_ENABLED`, `SCHEDULED_REPORT_DAILY_TIME`, `SCHEDULED_REPORT_WEEKLY_DAY`, `SCHEDULED_REPORT_WEEKLY_TIME`, `SCHEDULER_JOBSTORE`, `SMTP_FROM`, `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_USE_TLS`, `TZ` | gap | G6 |  |
| `METRICS_AUTH_TOKEN` | gap | G7 |  |
| `ALERTS_ENABLED`, `ALERT_COOLDOWN_SECONDS`, `ALERT_DELIVERY_MAX_RETRIES`, `ALERT_EMAIL_RECIPIENTS`, `ALERT_POLL_INTERVAL_SECONDS`, `ALERT_SLACK_WEBHOOK_URL`, `ALERT_WEBHOOK_SECRET`, `ALERT_WEBHOOK_URL` | gap | G8 |  |
| `AGENT_MONITOR_CACHE_MAX_ENTRIES`, `AGENT_STALE_THRESHOLD_SECONDS` | gap | G9 |  |
| `AGNOSTIC_MAX_VERSIONS`, `AGNOS_FLEET_ENABLED`, `AGNOS_FLEET_EXTERNAL_URL`, `AGNOS_FLEET_GROUP`, `AGNOS_FLEET_HEARTBEAT_INTERVAL`, `AGNOS_FLEET_HEARTBEAT_TTL`, `AGNOS_FLEET_NODE_ID` | gap | G10 |  |
| `TENANT_DEFAULT_RATE_LIMIT` | gap | G11 |  |
| `AGNOS_AUDIT_API_KEY`, `AGNOS_AUDIT_BATCH_SIZE`, `AGNOS_AUDIT_ENABLED`, `AGNOS_AUDIT_FLUSH_INTERVAL`, `AGNOS_AUDIT_URL`, `AGNOS_DASHBOARD_API_KEY`, `AGNOS_DASHBOARD_BRIDGE_ENABLED`, `AGNOS_DASHBOARD_PUSH_INTERVAL`, `AGNOS_DASHBOARD_URL`, `AGNOS_MEMORY_API_KEY`, `AGNOS_MEMORY_ENABLED`, `AGNOS_MEMORY_URL`, `AGNOS_PATH_PREFIX`, `AGNOS_PROFILE`, `AGNOS_PROFILE_API_KEY`, `AGNOS_PROFILE_URL`, `AGNOS_RAG_ENABLED`, `AGNOS_REASONING_API_KEY`, `AGNOS_REASONING_ENABLED`, `AGNOS_REASONING_URL`, `AGNOS_RPC_ENABLED`, `AGNOS_SCREEN_ENABLED`, `AGNOS_VECTOR_API_KEY`, `AGNOS_VECTOR_COLLECTION`, `AGNOS_VECTOR_ENABLED`, `AGNOS_VECTOR_URL` | gap | G13 |  |

`src/config.cyr` side:

| Cyrius names | Origin |
|---|---|
| `AGNOSTIC_PORT`, `PORT` | `AGNOSTIC_PORT` wins; default 8000 matches the oracle |
| `AGNOSTIC_ADDR` | `any` or loopback |
| `AGNOSTIC_WORKERS` | New |
| `AGNOSTIC_REQUEST_ARENA_BYTES` | New |
| `AGNOSTIC_MAX_BODY_BYTES` | New |
| `AGNOSTIC_IDLE_MS` | New |
| `AGNOSTIC_BACKLOG` | New |
| `AGNOSTIC_LOG_LEVEL`, `AGNOSTIC_LOG_FORMAT` | Renamed |
| `AGNOSTIC_CREW_TIMEOUT_SECS` | New |
| `AGNOSTIC_LLM_URL`, `AGNOSTIC_LLM_API_KEY`, `AGNOSTIC_LLM_TIMEOUT_SECS` | Renamed |
| `AGNOSTIC_DB_PATH`, `AGNOSTIC_AUDIT_PATH` | Replace Postgres and the audit logger |
| `AGNOSTIC_AUTH` | New; off refuses a non-loopback bind |
| `AGNOSTIC_BOOTSTRAP_EMAIL`, `AGNOSTIC_BOOTSTRAP_PASSWORD` | New; first admin |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME` | ADR 0018. `OTEL_EXPORTER_OTLP_HEADERS` is read inside agnosai |

Named in `.env.example` and read by no Python code (25, dead on arrival): `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `CUSTOM_LLM_API_KEY`, `CUSTOM_LLM_BASE_URL`, `CUSTOM_LLM_MODEL`, `ENABLE_CONTEXT_AWARE_TESTING`, `ENABLE_FUZZY_VERIFICATION`, `ENABLE_RISK_BASED_PRIORITIZATION`, `ENABLE_SELF_HEALING`, `FALLBACK_MODEL_PROVIDERS`, `GOOGLE_API_KEY`, `GOOGLE_MODEL`, `LM_STUDIO_BASE_URL`, `LM_STUDIO_MODEL`, `OAUTH2_GOOGLE_CLIENT_SECRET`, `OLLAMA_BASE_URL`, `PDF_GENERATOR_ENGINE`, `PRIMARY_MODEL_PROVIDER`, `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`, `REDIS_PUBSUB_CHANNEL`, `REPORT_EXPORT_PATH`, `WEBGUI_HOST`, `WEBGUI_PORT`, `WEBSOCKET_ENABLED`. The compose and entrypoint scripts add `TLS_*`, `WEBGUI_*` and `*_EMBEDDED`, which go with G14, and service-container variables, which go with the topology.

## 7. Comparison 3: tools and presets

### Presets

**Confirmed: 18 of 18 are byte-identical** between `python-port/agents/definitions/presets/` and `src/presets/`, by direct comparison of the bytes. That is 76 agents, 45 distinct keys, 38 distinct tool names, matching `state.md`.

`src/presets_data.cyr` is generated by `scripts/gen-presets.sh`, from `src/presets/*.json`. It does **not** read `python-port/`. The script embeds each document whitespace-collapsed as a Cyrius literal, in a fixed order that `tests/presets.tcyr` asserts. `check-clean.sh` runs `--check`, and that check passed with `python-port/` absent. No extraction is needed.

### The 36 tool classes

None was ever registered (§3.15). Two names resolve in Cyrius, and 34 do not. Behaviour by reading each class: 21 local computation, 5 does i/o, 4 local, uses `random`, 3 local, calls an llm, 3 hard-coded stub. "Hard-coded stub" means `_run` returns a literal; `LoadTestingTool` is one, so the alias to agnosai's real `load_testing` is an upgrade, not a port.

| Class | Module | Python `name` | Lines | Behaviour | Python test | Presets | Cyrius state |
|---|---|---|---:|---|---|---:|---|
| `DataOrganizationReportingTool` | analyst | Data Organization & Reporting | 298 | Local computation | Yes | 5 | Unresolved |
| `DefectPredictionTool` | analyst | Defect Prediction | 247 | Local computation | No | 3 | Unresolved |
| `PerformanceProfilingTool` | analyst | Performance Profiler | 264 | Does I/O | No | 3 | Unresolved |
| `QualityTrendAnalysisTool` | analyst | Quality Trend Analysis | 189 | Local, uses `random` | No | 3 | Unresolved |
| `ReleaseReadinessTool` | analyst | Release Readiness Assessment | 211 | Local computation | No | 5 | Unresolved |
| `RiskScoringTool` | analyst | Risk Scoring | 262 | Local computation | No | 4 | Unresolved |
| `SecurityAssessmentTool` | analyst | Security Assessment | 310 | Does I/O | No | 3 | Aliased to `security_audit` |
| `TestTraceabilityTool` | analyst | Test Traceability & Coverage | 298 | Local computation | No | 3 | Unresolved |
| `CrossPlatformTestingTool` | junior | Cross-Platform Testing Orchestrator | 95 | Local computation | No | 1 | Unresolved |
| `DesktopAppTestingTool` | junior | Desktop App Testing | 264 | Local computation | No | 1 | Unresolved |
| `FlakyTestDetectionTool` | junior | Flaky Test Detection & Management | 478 | Local computation | No | 3 | Unresolved |
| `LocalizationTestingTool` | junior | i18n & Localization Testing | 341 | Local computation | No | 3 | Unresolved |
| `MobileAppTestingTool` | junior | Mobile App Testing | 264 | Local, uses `random` | No | 1 | Unresolved |
| `RegressionTestingTool` | junior | Regression Testing Suite | 534 | Does I/O | Yes | 3 | Unresolved |
| `SyntheticDataGeneratorTool` | junior | Synthetic Data Generator | 245 | Local, uses `random` | Yes | 2 | Unresolved |
| `TestExecutionOptimizerTool` | junior | Test Execution Optimizer | 128 | Local computation | Yes | 3 | Unresolved |
| `UXUsabilityTestingTool` | junior | UX & Usability Testing | 337 | Local computation | No | 3 | Unresolved |
| `VisualRegressionTool` | junior | Visual Regression Testing | 145 | Local computation | No | 2 | Unresolved |
| `FuzzyVerificationTool` | manager | Fuzzy Verification | 57 | Local, calls an LLM | No | 3 | Unresolved |
| `TestPlanDecompositionTool` | manager | Test Plan Decomposition | 106 | Local, calls an LLM | Yes | 3 | Unresolved |
| `AdvancedProfilingTool` | performance | Advanced Performance Profiling | 279 | Local computation | No | 3 | Unresolved |
| `LoadTestingTool` | performance | load_testing | 15 | Hard-coded stub | Yes | 3 | Aliased to `load_testing` |
| `PerformanceMonitoringTool` | performance | performance_monitoring | 17 | Hard-coded stub | Yes | 3 | Unresolved |
| `ResilienceValidationTool` | performance | resilience_validation | 16 | Hard-coded stub | Yes | 3 | Unresolved |
| `ComprehensiveSecurityAssessmentTool` | security_compliance | Comprehensive Security Assessment | 300 | Does I/O | Yes | 3 | Unresolved |
| `GDPRComplianceTool` | security_compliance | GDPR Compliance Checker | 223 | Local computation | Yes | 3 | Unresolved |
| `HIPAAComplianceTool` | security_compliance | HIPAA Compliance Checker | 276 | Local computation | No | 3 | Unresolved |
| `ISO27001ComplianceTool` | security_compliance | ISO 27001 Compliance Checker | 256 | Local computation | No | 3 | Unresolved |
| `PCIDSSComplianceTool` | security_compliance | PCI DSS Compliance Checker | 172 | Local computation | No | 3 | Unresolved |
| `SOC2ComplianceTool` | security_compliance | SOC 2 Compliance Checker | 267 | Local computation | Yes | 3 | Unresolved |
| `AITestGenerationTool` | senior | AI Test Generation | 378 | Local, calls an LLM | No | 2 | Unresolved |
| `AutonomousTestDataGeneratorTool` | senior | Autonomous Test Data Generator | 129 | Local, uses `random` | No | 2 | Unresolved |
| `CodeAnalysisTestGeneratorTool` | senior | Code Analysis Test Generator | 209 | Local computation | No | 2 | Unresolved |
| `EdgeCaseAnalysisTool` | senior | Edge Case Analysis | 111 | Local computation | No | 2 | Unresolved |
| `ModelBasedTestingTool` | senior | Model-Based Testing (MBT) | 86 | Local computation | No | 2 | Unresolved |
| `SelfHealingTool` | senior | Self-Healing UI Testing | 470 | Does I/O | Yes | 2 | Unresolved |
| `ArtifactManagementTool` | none | | | No implementation anywhere | No | 1 | Roadmap: write or strike |
| `CIPipelineIntegrationTool` | none | | | No implementation anywhere | No | 1 | Roadmap: write or strike; agnosai `delta_*` is plausible backing (handoff §8) |

`RiskAssessmentTool`, documented in `agents/manager/README.md`, has no class. `agents/tool_registry.py` holds `load_tool_from_source`, whose upload path is G10.

### MCP tools are a different list

`webgui/routes/mcp.py` declares **34** MCP tools, and **none of them is one of the 38**. They are operations, such as `agnostic_submit_task` and `agnostic_gpu_status`. M7 says the "full QA tool surface" of 38 is settled, so M7 needs to say whether `/mcp` exposes those 38, these 34, or both. Most of the 34 route to surfaces in G1, G5, G7, G9 and G10, so the answer shapes those gaps too.

| Category | Tools |
|---|---|
| quality | `agnostic_submit_task`, `agnostic_task_status`, `agnostic_list_sessions`, `agnostic_agent_status`, `agnostic_dashboard`, `agnostic_structured_results`, `agnostic_session_diff`, `agnostic_quality_trends`, `agnostic_quality_dashboard`, `agnostic_qa_orchestrate` |
| security | `agnostic_security_scan`, `agnostic_security_findings` |
| performance | `agnostic_performance_test`, `agnostic_performance_results` |
| reports | `agnostic_generate_report`, `agnostic_list_reports` |
| system | `agnostic_health`, `agnostic_metrics`, `agnostic_agent_metrics`, `agnostic_llm_usage` |
| a2a | `agnostic_a2a_delegate`, `agnostic_a2a_status`, `agnostic_a2a_heartbeat` |
| gpu | `agnostic_gpu_status`, `agnostic_gpu_memory`, `agnostic_gpu_slots` |
| webhooks | `agnostic_subscribe_webhook` |
| streaming | `agnostic_event_stream` |
| crews | `agnostic_run_crew`, `agnostic_crew_status`, `agnostic_list_presets`, `agnostic_list_definitions`, `agnostic_create_agent`, `agnostic_preset_recommend` |

## 8. Comparison 4: test coverage intent

By behaviour, not by count. Bold marks behaviours with a Python test, no Cyrius test, and a reason to care.

| Python suites | Cyrius suites | Verdict |
|---|---|---|
| Crew API: `unit/webgui/test_crews_api`, `e2e/test_crew_dual_backend`, `e2e/test_task_lifecycle`, `unit/webgui/test_task_routes` (submit, poll, cancel) | `crews_route`, `crew_request`, `crew_tenancy`, `ledger`, `outcome`, `crewstore`, `restart` | Better. Cyrius asserts the wire (lessons 1–4, 6); Python mocked it (§3.7, §3.8). |
| Definitions and presets: `unit/webgui/test_definitions_api`, `test_base_agent`, `test_agent_registry`, `test_team_config`, `test_constants` | `agentdef`, `presets`, `router`, `tools` | Equal for CRUD and key rules. Preset writes: G16. Team-size filters are gone. |
| Auth: `unit/webgui/test_auth`, `test_token_manager`, `test_permission_validator` | `authn`, `authstore`, `authz`, `jwt`, `crypto`, `loginguard`, `loginroute` | Better on the security properties (mutation-checked). No route-level test of key or user management, because the routes do not exist: G1. |
| Tenancy: `test_tenant`, `test_tenant_isolation` | `authz` (`tenant/*`), `crew_tenancy`, `plugindata` | Isolation better. Tenant CRUD over HTTP, per-tenant rate limits and API-key isolation have no Cyrius test: G1, G11. |
| HTTP plumbing: `unit/webgui/test_api_routes`, `test_app`, `test_api_validation` | `router`, `health`, `codec`, `serve_mount`, `plugindata`, `api_schema` | Better; the schema snapshot has no Python equivalent. Report download security and SSRF (11 cases) have no Cyrius test: M8 and G3. |
| Config and logging: `test_config_environment`, `test_logging_config` | `config`, `log`, `trace` | Better. Strict parsing is pure-function tested. `agnostic_config_from_env` itself cannot be (no `setenv`). |
| Audit: `test_audit` | `audit`, `store_concurrency` | Better on integrity. Failed-login and rate-limit events: G12. |
| Observability: `test_observability` | `trace`, `server_span`, `log` | Traces better. A2A audit, rate-limit and payload-validation cases move to M7. Correlation id is replaced by W3C trace context. |
| Metrics: `test_metrics`, `test_agent_metrics`, `e2e/test_smoke::prometheus_metrics` | None | **No Cyrius test, still matters if G7 is ported.** |
| Resilience: `test_resilience` | agnosai `llm_retry`, `server_rate_limit` | Delegated, except `TestGracefulShutdown`: **no suite sends a signal to Agnostic's server.** `restart` covers what survives, not a clean stop with crews running. |
| Fleet and GPU: `test_fleet`, `test_gpu`, `e2e/test_fleet_*` | agnosai `fleet_*` | Delegated. Route cases in `TestFleetEndpoints` and `TestGPUEndpoints` follow G10. |
| Crew assembly: `test_crew_assembler` | agnosai `definitions_assembler` | `assemble_team` delegated. `TestRecommendPreset` (9) has no counterpart anywhere: G10. |
| Packaging and versioning: `test_packaging_versioning` | agnosai `definitions_packaging`, `definitions_versioning`, `tools_builtin_delegate` | Delegated. Custom-tool upload safety has no counterpart: G10. |
| LLM: `test_model_manager`, `e2e/test_agnos_gateway` | agnosai `llm_hoosh`, `llm_router`; Agnostic `crews_route` (`crews/llm-timeout`) | **Agnostic has no suite that takes a crew through a gateway.** Suites run placeholder mode; the priced runs in `state.md` were manual, against a scratch stand-in (0.1.9, 0.1.10). A stub-gateway suite would meet audit lesson 7 properly and also check the consumer path M7 needs. |
| QA tools: `unit/tools/*` (45 tests, 12 of 36 tools) | `tools` (the gate only) | **M6.** These test Python output shapes, some over hard-coded data, so they are weak as a spec. Their value is the input shape. |
| Data generation: `test_data_generation` | None | M6, if a data-generator tool is built. |
| Reports: `test_report_generator`, `test_history`, `test_session_diff` | None | **M8.** Sanitised output, metric calculation, trend direction and diff semantics all still matter, and M8 owes them. |
| Scheduled reports and delivery: `test_scheduled_reports`, `test_report_delivery` | None | Mocks around code that could not run (G6). Do not carry over. |
| Realtime: `test_realtime`, `test_message_buffer`, `test_yeoman_websocket` | `ledger` (`ledger/ring-cursor`), `crews_route` (`crews/events-*`) | Replay intent covered by the cursor and `missed`. Transport tests owed at M9. |
| MCP and A2A: `test_api_validation::TestMCPDispatch`, `test_task_routes::TestA2AEndpoints`, `e2e/test_a2a_roundtrip` | None | **M7.** |
| Webhook delivery: `test_task_routes::TestFireWebhook`, `test_api_validation::TestWebhookSignatureVerification` | `loginguard` (`webhook/sign`) | Signature covered and stronger (timestamp inside the MAC). Delivery, retry and SSRF-at-fire have no test: G3. |
| Dashboards and monitor: `test_dashboard`, `test_agent_monitor` | `tests/webgui/*.test.mjs` for the replacement views | Do not carry over: they mock keys nothing writes (G9). |
| Black-box smoke: `e2e/test_smoke`, `scripts/smoke_tests.py` | `serve_mount` (socketpair), `api_schema` (`api/responses`, real mount) | Good in-process. **No CI step binds a port and probes it**: G17. |
| Load: `tests/load/locustfile.py` | `tests/agnostic.bcyr` (micro only) | No concurrent-load test. `store_concurrency` is the closest. Worth one soak run before the v1.0 security audit: `sandhi` closes every connection (brief §5.2) and only a load test shows that. |
| Kubernetes manifests: `tests/k8s` | None | Dropped with the manifests. |
| SecureYeoman and AGNOS clients: `unit/integration/*`, `integration/test_agent_communication` | None | Dropped or G13. `test_yeoman_schemas` is worth reading again for M8. |
| Benchmarks: `tests/benchmarks/*` | `tests/agnostic.bcyr` | Not comparable (roadmap v1.0 criteria). |

## 9. Dependencies on `python-port/` from the rest of the repo

`grep -rIn python-port` over everything outside it, `lib/` included: **nothing breaks if it is deleted.** Every hit is prose. There are no hits in `.github/`, `cyrius.cyml`, `cyrius.lock`, `tests/` or `skills/`, and none in a script other than the one `echo` below.

| Reference | Kind | Action |
|---|---|---|
| `CONTRIBUTING.md:6,8,10,53,58` | Stale prose | Rewrite. Line 53 tells readers to check a module against `python-port/`. Line 10 already says 85, not 86 |
| `ORACLE-AUDIT.md:14,16` | Stale prose | Keep the document; add the pinned rev. Its ~40 line citations need one (§10) |
| `CYRIUS-PORT-BRIEF.md:8,94` | Stale prose | Dated snapshot, says so. Leave, or add the rev |
| `BENCHMARKS.md:37` | Stale prose | Generated: fix the generator below |
| `scripts/bench-history.sh:119` | Stale prose, in a generator | An `echo`. Edit it, or the next bench run writes the line back |
| `docs/adr/0001-health-and-readiness-are-separate.md:15,34` | Stale prose | ADRs are history. Leave |
| `docs/audit/2026-08-20-audit.md:90,158` | Stale prose | Dated audit. Leave |
| `docs/audit/2026-08-20-audit-m1.md:138` | Stale prose | Dated audit. Leave |
| `SECURITY.md:23` | Stale prose | Delete the scope clause |
| `docs/development/state.md:454` | Stale prose | Delete at the release that retires it |
| `docs/development/handoff.md:489` | Stale prose | Rewrite |
| `docs/development/roadmap.md:23,38` | Stale prose | Line 38 is the criterion: tick it. Line 23 goes |
| `src/routes/health.cyr:12` | Stale prose, already wrong | Names `webgui/routes/health.py`, which has never existed; `/health` is in `webgui/app.py` |
| `CHANGELOG.md:3643` | Stale prose | History. Leave |

Indirect references, which do not say `python-port` and go stale the same way:

- `src/engine/request.cyr:54-55` and `tests/crew_request.tcyr:138-139` cite `agents/base.py:61-62` and `config/gpu_scheduler.py:196`.
- `ORACLE-AUDIT.md` cites Python paths and lines throughout, and 43 files say "oracle".
- `scripts/version-bump.sh:13` says `rust-old/`, copied from agnosai. It is unrelated, and already wrong.
- `CONTRIBUTING.md:52` says `src/` mirrors the oracle.

Outside the repo: your memory note `agnostic-cyrius-port.md` says the tree "stays there". I found no `agnostic.toml` recipe under `~/Repos` within five levels, so nothing there builds from this tree's Dockerfile.

The standard itself is loose here. `agnosticos/docs/development/first-party/first-party-standards.md:53` sets the rule and points to a "retirement-via-git-tag pattern" in `first-party-documentation.md`, and that file has no such section. So tag it yourself: a git tag before the deletion commit is what makes the citations above resolvable.

## 10. What exists only in `python-port/`

Everything committed stays reachable through `git show <rev>:python-port/...`, so nothing is lost by deleting it. "Extract first" below means: open work is written against this content, so it should be in the tree before the tree goes.

| Content | Only copy? | Where it goes |
|---|---|---|
| Preset documents (18) | No. `src/presets/*.json` is byte-identical | Nothing to do |
| **Tool intent** for the 36 classes: `name`, `description`, inputs, outputs | **Yes.** Roadmap M6 says to build against "preset-declared intent", but a preset declares a class name and an agent `focus`. The rest is only in the classes and `agents/*/README.md` | **Extract first.** One table in `docs/development/research/`, the M6 spec. Tool bodies and compliance checklists can stay in git |
| **MCP manifest**: 34 tools with `inputSchema` (`webgui/routes/mcp.py`) | **Yes** | **Extract first** into M7's ADR notes, and settle which surface M7 means: Python's 34 are operations, the 38 are QA classes, and they overlap in no name (§7) |
| Result model: `shared/yeoman_schemas.py` (`Finding`, severity and category enums, `SecurityResult`, `PerformanceResult`, `TestExecutionResult`, `QAReport`) | Yes, and the only typed result model in the tree | Recommended: note it in M8's plan. It feeds M8's report shape and the reviewer preset's `output_schema`. Recoverable from git |
| Report logic: `webgui/exports.py`, `webgui/history.py`, `shared/database/repository.py` (`diff_sessions`, `get_quality_trends`) | Yes | Recoverable from git. Read §11 first: most of it was unreachable |
| Schema: `alembic/versions/*`, `shared/database/models.py` | Yes | Recoverable. No production data exists. The migration and the models disagree (§11) |
| A2A message types: `webgui/routes/tasks.py`, `docs/api/a2a-protocol.md`, `docs/adr/019-a2a-protocol.md` | Yes | Recoverable. M7 targets A2A v1.0.x, so this is background, not a contract |
| Operator docs: `docs/deployment/*`, `docs/api/*`, `docs/guides/*`, `docs/development/manual-testing.md` | Yes, all Python-stack | Recoverable. G15 writes new ones |
| Python ADRs 001–029, `docs/project/changelog.md`, `CHANGELOG.md`, `README.md` | Yes | Recoverable. History |
| Grafana dashboards, Prometheus rules | **They do not exist.** `monitoring/grafana/dashboards/dashboard.yml` is a provisioning stub, and `rules/` is absent | Nothing to do |
| Fixtures | `tests/fixtures/common.py` is 265 bytes; no data fixtures exist | Nothing to do |
| Benchmark workloads: `benchmarks/scenarios.py` | Yes | Recoverable. Useful only if an end-to-end crew benchmark is added |
| `config/models.json`, `config/testing_targets.json`, `examples/*.json`, `tests/load/locustfile.py` | Yes | Recoverable |
| `.github` issue and PR templates | Yes | Recoverable, or re-add (G17) |

Before the deletion commit: tag the parent, then put that rev in `ORACLE-AUDIT.md`'s header so its citations resolve.

## 11. Found on the way, not in ORACLE-AUDIT

In the oracle. These matter because they change what M8 owes, and several gaps above rest on them:

- **Session and agent keys have no writer.** I found no literal `set` of `session:*:info`, `manager:*:test_plan`, `manager:*:verification` or `agent:*:status`. `/sessions`, `/dashboard/sessions`, `/agents` and the report's info and plan sections read them. In `/health`, `any_alive` can never be true, so the best possible answer was `degraded`.
- **Only one report type could be requested.** `ReportGenerateRequest.report_type` allows `executive_summary`, `detailed`, `compliance`, `security`, `performance`. `ReportType` is `executive_summary`, `technical_report`, `compliance_report`, `comparison_report`, `agent_performance`. Only the first is in both, so the others answer 400. The route also refuses `csv`, which `ReportFormat` has.
- **Report content.** `_collect_session_data` reads agent reports that only the legacy Celery workers write, and the default compose does not start them. On the crew path, a report had almost nothing in it.
- **Scheduled jobs raise on construction** (G6).
- **`monitoring/prometheus.yml` scrapes `/metrics`**; the route is `/api/v1/metrics`.
- **The migration and the models disagree.** `shared/database/models.py` has `domain` and `crew_preset`; `alembic/versions/db8d3fe1686e` does not.
- **`webgui/static/**` is never served**: there is no static mount.
- **No importer at all:** `shared/agnos_memory`, `agnos_rag_client`, `agnos_reasoning`, `agnos_screen_client`, `data_generation_service`, `logging_config`, `ssrf`. The four AGNOS clients appear only in a shutdown `close()` loop. `agnos_vector_client` has the same shape with a direct import.
- **`check_quota`, `is_within_trial`, `PERMISSION_DENIED`, `PATH_TRAVERSAL_BLOCKED`** are defined and unused.

In the Cyrius record, worth fixing whatever is decided:

- `src/auth/jwt.cyr:72` says an operator can install a secret; nothing lets them (G2).
- `state.md:193` and `src/server/serve.cyr:410` say there is no bootstrap route; the environment bootstrap has existed since M5 part 3.
- The roadmap's M5 entry says "tenant CRUD"; it is library-only (G1).
- The roadmap says Agnostic calls what the engine owns; it does not, for versioning, packaging, the assembler, fleet, GPU or Prometheus (G7, G10).
- `handoff.md:18` says nineteen ADRs; there are twenty. `handoff.md:466` still says a `bayan_pdf_*` request should be filed; roadmap M8 says that is moot. `CONTRIBUTING.md:10` says 85 defects.
- M6 says "preset-declared intent", and presets do not declare it (§10).
- `docs/guides/getting-started.md` still has scaffold text, and `docs/examples/` is empty.
