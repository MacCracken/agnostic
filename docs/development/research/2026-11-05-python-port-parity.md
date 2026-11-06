# Port parity review: what has not been ported

Reviewed 2026-11-05. The tables in §4–§11 were taken at agnostic 0.2.1 with agnosai 2.2.3; §1 and §3 were re-checked against the agnostic source at 0.2.2.

**agnostic is the project, and it is written in Cyrius. `python-port/` is its former code.** This review lists what has not come across, and that is all. It does not treat the former code as correct: [`ORACLE-AUDIT.md`](../../../ORACLE-AUDIT.md) records 86 verified defects in it, and agnostic has already fixed or replaced much of what it did. Each thing not in agnostic ends one of three ways: agnostic already answers it, it is missing function on the roadmap, or it is a question for the user. Nothing here recommends removing anything.

Status words: **PORTED** (a `src/` file and a test), **DELEGATED** (an agnosai or sibling file owns it), **DELEGATED\*** (the owner exists and nothing in Agnostic calls it), **REPLACED** (agnostic answers it differently, with a record), **SCHEDULED** (on the roadmap), **NOT PORTED** (none of those; §3 says what happens to each). NOISE marks `.pyc` files and empty package markers.

## 1. Verdict

**`python-port/` is removed once the release plan is finished and tagged.** Nothing in the repo reads it (§9), and all of it stays in git. The first-party rule asks for equal or better coverage (`first-party-standards.md:53`), and the largest function agnostic does not have yet is:

| Missing from agnostic | What agnostic has today | Release |
|---|---|---|
| QA tools (M6) | `src/engine/tools.cyr` resolves the preset vocabulary. 36 of 38 names have no tool behind them, and agnosai F1 means a tool would not be called | 0.4.x |
| MCP and A2A (M7) | Nothing | 0.5.x |
| Reports (M8) | Crew outcomes, stored and listed | 0.5.x |
| Issuing users, API keys and tenants (G1) | Done at 0.3.0 ([ADR 0023](../../adr/0023-provisioning-is-routes-and-one-recovery-command.md)) | 0.3.0 |
| An operator-set JWT secret (G2) | Done at 0.3.0: `AGNOSTIC_JWT_SECRET` | 0.3.0 |

§3 lists everything else, and the [release plan](../roadmap.md#release-plan) carries all of it.

## 2. What was and was not checked

- **Files.** The snapshot holds **397 files**, not 405, and `git ls-files python-port | wc -l` agrees. The live tree's other 8 are `benchmarks/__pycache__/*.pyc`. Every one of the 397 is assigned to exactly one row in §4, asserted by script.
- **Mechanical parts.** Routes, environment variables, tool classes and test counts came from the Python AST, not grep. The table scripts fail if a route or variable is unassigned. The Python test count comes to 1,207, matching ORACLE-AUDIT §1.
- **Removal check.** In a copy of the snapshot without `python-port/`, these all passed: `gen-presets.sh --check`, `gen-webgui.sh --check`, `check-skill.py`, `check-store-lock.py`, `check-log-lengths.py`, `check-webgui-js.sh` (80 tests).
- **Not run.** `cyrius build` and `cyrius test` in that copy. That no suite needs the tree rests on grep: no `include` or file read names it.
- **"Did it ever work".** ORACLE-AUDIT's six audits covered `agents/backend`, `config/fleet`, `routes/crews.py`, `benchmarks/`, `tests/` and `docs/`, and §3.15 added the registry. Everything else here is my reading of the code, so "never ran" means I found no path to it, not that I watched it fail.
- **"By rule".** No record names the routes `/auth/refresh` and `/auth/logout`. They are REPLACED by agnostic's token design (§3), and both rows say "by rule".

## 3. Everything not in agnostic

| Status | Area rows (§4) | Files | Routes (§5) | Variables (§6) |
|---|---:|---:|---:|---:|
| PORTED | 30 | 78 | 9 ported, 10 renamed | 22 renamed |
| DELEGATED | 13 (5 unwired) | 29 (12 unwired) | | |
| REPLACED | 25 | 104 | 13 | 88 |
| SCHEDULED | 15 | 37 | 12 | 10 |
| NOT PORTED | 31 | 121 | 62 | 72 |
| NOISE | 6 | 28 | | |
| Total | 120 | 397 | 106 | 192 |

Counted at 0.2.1. File counts are not a measure of work: 43 of the REPLACED files are Kubernetes manifests, and one SCHEDULED row of 12 files holds all 36 tools. The NOT PORTED rows and variables merge into the items G1–G17 below.

### agnostic already answers it

Nothing to port.

| Item | agnostic's answer |
|---|---|
| Everything REPLACED in §4–§6: Redis, RabbitMQ, Celery, PostgreSQL, Kubernetes, the multi-container topology, CrewAI, Chainlit, the SecureYeoman shim | patra, the in-process engine, the single binary and the WebGUI, each with its record in the row |
| Crew shortcuts and retry (G4): `/tasks/security`, `/performance`, `/regression`, `/full`, `/tasks/{id}/retry` | `POST /api/v1/crews` with a preset's agents and a task |
| Dashboards and the agent monitor (G9) | The Crews view, `GET /api/v1/crews` and `GET /api/v1/crews/:id/events`. Agents are not long-lived and there is no queue to watch |
| Failed-login audit (G12) | `auth.login.failed`, since 0.2.2 |
| Configuration reference (G15) | `docs/guides/configuration.md`, since 0.2.2 |
| Preset writes (G16) | A canonical library compiled in, and saved definitions for custom agents. In the former code, running a created preset was a 404 |
| Token refresh and logout routes | Tokens last 3600 s, roles are re-read on each request, and the shell clears its own token |

### Missing, on the roadmap

| Item | agnostic today | Release |
|---|---|---|
| Identity provisioning (G1) and the JWT secret (G2) | Done at 0.3.0, see §1 | 0.3.0 |
| The rest of the audit vocabulary (G12) | A 401, a 403 and a rate-limit hit leave no entry | 0.3.x |
| Deployment guide (G14) | `SECURITY.md` and the configuration guide say TLS belongs to a proxy. Nothing covers the binary, the proxy and a unit file together | 0.3.x |
| A crew's target (G4) | A QA tool needs one, and the crew body is `name`, `process`, `max_concurrency`, `agents`, `tasks` | 0.4.x |
| `GET /tools` (G10) | `src/engine/tools.cyr` resolves names, and no route shows them | 0.4.x |
| Completion webhook (G3) | `src/auth/webhook.cyr` signs and verifies with a signed timestamp, tested in `tests/loginguard.tcyr`. Nothing sends one, and the crew body has no callback field | 0.5.x |
| A boot-and-probe CI step (G17) | Suites run on socketpairs, and CI never boots the binary and probes it | 0.2.x |
| Issue and PR templates (G17) | `.github` holds workflows only | 0.2.x |
| Tenant limits (G11) | Login is the only limit | 0.3.x |
| A metrics route (G7) | OTLP traces. `agnosai_metrics_gather` exists, and nothing calls it | 0.3.x |
| Stored definitions in a crew body (G4) | A client reads a definition and re-sends it | 0.4.x |
| Engine features with no route (G10) | Definition versions and rollback, package export and import, tool upload, GPU, fleet, the `team` crew spec and `recommend_preset`, which has no owner | 0.4.x |
| The AGNOS clients (G13) | Memory, RAG, reasoning, recording, RPC, screen and vector: none here | 0.5.x |
| Scheduled reports and delivery (G6) | None. The former default jobs raised on construction, so there is nothing to copy | 0.5.x |
| Health alerts (G8) | None | 0.5.x |
| Text search across crews (G9) | `GET /api/v1/crews` lists and does not search | 0.5.x |

### Questions for the user

All four were on the release plan and needed a form only you could pick. All four were answered on 2026-11-05.

1. **Provisioning (G1):** answered 2026-11-05: routes, plus one recovery command. See the roadmap's *Settled decisions*.
2. **A crew's target (G4):** answered 2026-11-05: a checked field on the crew, which a task may override. See the roadmap's *Settled decisions*.
3. **Reports (G5):** answered 2026-11-05: crew outcomes, with no result model of their own. See the roadmap's *Settled decisions*.
4. **MCP surface (M7):** answered 2026-11-05: agnostic's own API, beside the 38 QA tools, which were already settled. The former 34 are not the list (§7). See the roadmap's *Settled decisions*.

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
| `agents/versioning.py` | 1 | DELEGATED\* | agnosai `src/definitions/versioning.cyr`, `tests/definitions_versioning.tcyr` | In-memory there. agnostic has a revision and ETag (`router/definition-revisions`), no history. G10 |
| `agents/tool_registry.py` | 1 | DELEGATED | agnosai `src/tools/registry.cyr`, `src/tools/remote_registry.cyr` | Who registers QA tools is undecided (handoff §8). Upload half: G10 |
| `agents/tool_sandbox.py` | 1 | DELEGATED | kavach, through agnosai `src/sandbox/kavach_bridge.cyr` | Roadmap M6; `first-party-standards.md:76` |
| `agents/backend/__init__.py`, `agents/backend/base.py` | 2 | PORTED | `src/engine/outcome.cyr`; `tests/outcome.tcyr` | Design lesson 1 |
| `agents/backend/agnosai_backend.py` | 1 | PORTED | `src/engine/crew.cyr`, `src/engine/request.cyr`; `tests/crews_route.tcyr`, `tests/crew_request.tcyr` | In-process, so no client. ORACLE-AUDIT §3.1–3.3, §3.6 and §3.11 designed out |
| `agents/backend/crewai_backend.py`, `agents/backend/router.py` | 2 | REPLACED | Brief §2 (agnosai replaces CrewAI), §7 D1 | One backend |
| `agents/definitions/presets/` | 18 | PORTED | `src/presets/*.json`; `tests/presets.tcyr` | 18 of 18 byte-identical (§7) |
| `agents/` | 12 | SCHEDULED | M6 | The 36 tool classes, role wrappers, Celery tasks. Every tool is a fresh implementation (roadmap M6) |

### config (23 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `config/__init__.py`, `config/__pycache__/environment.cpython-314.pyc`, `config/__pycache__/llm_integration.cpython-314.pyc` | 3 | NOISE |  |  |
| `config/agent_registry.py` | 1 | PORTED | `src/engine/presets.cyr`; `tests/presets.tcyr` | `route_task` is DELEGATED to agnosai `src/orchestrator/scoring.cyr` |
| `config/agnos_agent_registration.py` | 1 | REPLACED | ADR 0002 | The tool registrar is on M7 |
| `config/agnos_environment.py` | 1 | NOT PORTED | G13 |  |
| `config/agnos_token_budget.py` | 1 | DELEGATED | hoosh (brief §2); agnosai `src/orchestrator/budget.cyr` | Enforced budgets wait on agnosai F5 |
| `config/environment.py` | 1 | PORTED | `src/config.cyr`; `tests/config.tcyr` | Redis, RabbitMQ and Celery half replaced: brief §5.2, roadmap Settled 2026-08-21 |
| `config/fleet/shim.py` | 1 | REPLACED | ORACLE-AUDIT §2.3; brief §4 | Dead branch against routes that never existed |
| `config/fleet/__init__.py`, `config/fleet/coordinator.py`, `config/fleet/node.py`, `config/fleet/placement.py`, `config/fleet/registry.py`, `config/fleet/relay.py`, `config/fleet/state.py` | 7 | DELEGATED\* | agnosai `src/fleet/` (`coordinator`, `placement`, `registry`, `relay`, `state`), `tests/fleet_*.tcyr` | Nothing here calls it. G10 |
| `config/gpu.py`, `config/gpu_scheduler.py` | 2 | DELEGATED\* | ai-hwaccel (brief §2); agnosai `src/fleet/gpu.cyr`, `tests/fleet_gpu.tcyr` | Agnostic forwards `gpu_required`, `gpu_preferred`, `gpu_memory_min_mb` only. G10 |
| `config/llm_integration.py`, `config/local_inference.py` | 2 | DELEGATED | agnosai `src/llm/hoosh.cyr`, `src/llm/router.cyr`, `src/llm/retry.cyr` | Brief §2 |
| `config/model_manager.py`, `config/models.json` | 2 | DELEGATED | hoosh (brief §2) | No agnosai file: hoosh is a service |
| `config/testing_targets.json` | 1 | NOT PORTED | G17 | No reader in the tree |

### shared (34 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `shared/__init__.py`, `shared/database/__init__.py` | 2 | NOISE |  |  |
| `shared/audit.py` | 1 | PORTED | `src/engine/audit.cyr`; `tests/audit.tcyr` | A tamper-evident chain where Python logged JSON. Narrower vocabulary: G12 |
| `shared/context.py` | 1 | PORTED | `src/trace.cyr`; `tests/trace.tcyr` |  |
| `shared/crewai_compat.py` | 1 | REPLACED | Brief §2 |  |
| `shared/data_generation_service.py` | 1 | SCHEDULED | M6 | No importer in Python; intent for the two data-generator tools |
| `shared/database/models.py`, `shared/database/repository.py` | 2 | NOT PORTED | G5 | Reports half on M8 |
| `shared/database/tenant_repository.py`, `shared/database/tenants.py` | 2 | PORTED | `src/auth/tenant.cyr`; `tests/authz.tcyr` (`tenant/*`) | Library only, no route: G1. Limits: G11 |
| `shared/logging_config.py` | 1 | PORTED | `src/log.cyr`; `tests/log.tcyr` | No importer in Python |
| `shared/agent_metrics.py`, `shared/metrics.py` | 2 | NOT PORTED | G7 |  |
| `shared/alerts.py` | 1 | NOT PORTED | G8 |  |
| `shared/resilience.py` | 1 | DELEGATED | agnosai `src/llm/retry.cyr`; hoosh failover (brief §2) | `GracefulShutdown` is in `src/server/serve.cyr`, untested (§8) |
| `shared/ssrf.py` | 1 | DELEGATED | agnosai `src/server/ssrf.cyr`, `src/guarded_fetch.cyr` | No importer in Python |
| `shared/telemetry.py` | 1 | PORTED | `src/trace.cyr`, agnosai `src/telemetry/otlp.cyr`; `tests/trace.tcyr`, `tests/server_span.tcyr` | ADRs 0018, 0020 |
| `shared/version.py` | 1 | PORTED | `GET /ready`; `tests/health.tcyr` (`routes/version`) |  |
| `shared/agnos_audit.py`, `shared/agnos_dashboard_bridge.py`, `shared/agnos_memory.py`, `shared/agnos_rag_client.py`, `shared/agnos_reasoning.py`, `shared/agnos_recording_client.py`, `shared/agnos_rpc_client.py`, `shared/agnos_screen_client.py`, `shared/agnos_vector_client.py` | 9 | NOT PORTED | G13 |  |
| `shared/yeoman_mcp_server.py` | 1 | SCHEDULED | M7 | Daimon tool registrar (ADR 0002). The SecureYeoman half is out of scope by brief §7.3 |
| `shared/yeoman_a2a_client.py`, `shared/yeoman_audit.py`, `shared/yeoman_dlp.py`, `shared/yeoman_event_stream.py`, `shared/yeoman_jwt.py`, `shared/yeoman_schemas.py` | 6 | REPLACED | Brief §7.3; roadmap Out of scope (SY shim) | DLP to hoosh (brief §2). JWT to the IdP seam, `agnostic_authn_set_external`, `tests/loginguard.tcyr`. Schemas: see §10 |

### webgui (40 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `webgui/__init__.py`, `webgui/routes/__init__.py` | 2 | NOISE |  |  |
| `webgui/app.py` | 1 | REPLACED | Brief §7 D3 | The Chainlit chat. `/health`, `/ready` PORTED (`src/routes/health.cyr`, `tests/health.tcyr`, ADR 0001). CORS replaced by ADRs 0005, 0006. `/ws/realtime` on M9 |
| `webgui/api.py` | 1 | PORTED | `src/http/router.cyr`; `tests/router.tcyr` |  |
| `webgui/auth/__init__.py`, `webgui/auth/models.py`, `webgui/auth/permission_validator.py`, `webgui/auth/token_manager.py` | 4 | PORTED | `src/auth/authn.cyr`, `jwt.cyr`, `perm.cyr`, `crypto.cyr`; `tests/authn.tcyr`, `jwt.tcyr`, `authz.tcyr`, `crypto.tcyr` | Refresh and blacklist replaced by rule (roadmap Settled 2026-08-20) |
| `webgui/auth/api_keys.py` | 1 | PORTED | `src/auth/store.cyr`; `tests/authstore.tcyr` | Library only, no route: G1 |
| `webgui/auth/oauth_provider.py` | 1 | REPLACED | Roadmap Settled 2026-08-20 | Three unreachable providers |
| `webgui/routes/auth.py` | 1 | PORTED | `src/routes/auth.cyr`, `src/auth/ratelimit.cyr`; `tests/loginroute.tcyr`, `tests/loginguard.tcyr` | Login only. Rest: G1 |
| `webgui/routes/crews.py` | 1 | PORTED | `src/routes/crews.cyr`, `src/engine/ledger.cyr`, `crewstore.cyr`; `tests/crews_route.tcyr`, `crew_tenancy.tcyr`, `ledger.tcyr`, `crewstore.tcyr` | ORACLE-AUDIT §3.1–3.5 designed out. Fields: G4 |
| `webgui/routes/definitions.py` | 1 | PORTED | `src/routes/definitions.cyr`, `presets.cyr`; `tests/agentdef.tcyr`, `tests/router.tcyr` | CRUD and reads. Rest: G10, G16 |
| `webgui/routes/dependencies.py` | 1 | PORTED | `src/auth/authn.cyr`, `src/http/guard.cyr`; `tests/authn.tcyr`, `tests/plugindata.tcyr` | SSRF half goes with G3 |
| `webgui/routes/tasks.py` | 1 | SCHEDULED | M7 | A2A half. Task routes renamed onto crews. Webhook G3, shortcuts G4 |
| `webgui/routes/mcp.py` | 1 | SCHEDULED | M7 | 34 tools: see §7, §10 |
| `webgui/routes/reports.py` | 1 | SCHEDULED | M8 | Scheduled half: G6 |
| `webgui/exports.py`, `webgui/history.py` | 2 | SCHEDULED | M8 | HTML, CSV, JSON; PDF undecided (roadmap M8) |
| `webgui/routes/sessions.py` | 1 | SCHEDULED | M8 | Compare. Lists renamed onto crews. Search: G9 |
| `webgui/routes/persistence.py` | 1 | NOT PORTED | G5 | Trends and diff on M8 |
| `webgui/routes/tenants.py` | 1 | NOT PORTED | G1 |  |
| `webgui/routes/fleet.py`, `webgui/routes/gpu.py` | 2 | NOT PORTED | G10 |  |
| `webgui/agent_monitor.py`, `webgui/dashboard.py`, `webgui/routes/agents.py`, `webgui/routes/dashboard.py` | 4 | NOT PORTED | G9 | Registration half: ADR 0002. Metrics half: G7 |
| `webgui/routes/rpc.py` | 1 | NOT PORTED | G13 |  |
| `webgui/routes/integration.py`, `webgui/routes/yeoman_webhooks.py` | 2 | REPLACED | Brief §7.3; roadmap Out of scope (SY shim) |  |
| `webgui/realtime.py` | 1 | SCHEDULED | M9 | Streaming. The cursor already covers replay (ADR 0009) |
| `webgui/scheduled_reports.py` | 1 | NOT PORTED | G6 |  |
| `webgui/static/css/dashboard.css`, `webgui/static/css/realtime.css`, `webgui/static/css/reports.css`, `webgui/static/js/dashboard.js`, `webgui/static/templates/dashboard.html`, `webgui/static/templates/reports/executive_summary.html` | 6 | REPLACED | Brief §7 D3 | Never served: no static mount exists |
| `webgui/Dockerfile` | 1 | NOT PORTED | G14 |  |

### tests (81 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `tests/__init__.py`, `tests/benchmarks/__init__.py`, `tests/e2e/__init__.py`, `tests/e2e/conftest.py`, `tests/fixtures/__init__.py`, `tests/fixtures/common.py`, `tests/integration/__init__.py`, `tests/k8s/__init__.py`, `tests/load/__init__.py`, `tests/unit/__init__.py`, `tests/unit/conftest.py`, `tests/unit/integration/__init__.py`, `tests/unit/tools/__init__.py`, `tests/unit/webgui/__init__.py` | 14 | NOISE |  |  |
| `tests/k8s/test_k8s_manifests.py` | 1 | REPLACED | Roadmap Out of scope |  |
| `tests/benchmarks/bench_definitions.py`, `tests/benchmarks/bench_packaging.py` | 2 | REPLACED | Roadmap Out of scope; ORACLE-AUDIT §4 |  |
| `tests/load/locustfile.py` | 1 | NOT PORTED | G17 |  |
| `tests/unit/test_data_generation.py`, `tests/unit/tools/test_junior_qa_tools.py`, `tests/unit/tools/test_performance_tools.py`, `tests/unit/tools/test_qa_analyst_tools.py`, `tests/unit/tools/test_qa_manager_tools.py`, `tests/unit/tools/test_security_compliance_tools.py`, `tests/unit/tools/test_senior_qa_tools.py` | 7 | SCHEDULED | M6 |  |
| `tests/unit/test_history.py`, `tests/unit/test_session_diff.py`, `tests/unit/webgui/test_report_generator.py` | 3 | SCHEDULED | M8 |  |
| `tests/unit/integration/test_yeoman_websocket.py`, `tests/unit/test_message_buffer.py`, `tests/unit/webgui/test_realtime.py` | 3 | SCHEDULED | M9 |  |
| `tests/e2e/test_a2a_roundtrip.py` | 1 | SCHEDULED | M7 |  |
| `tests/e2e/test_fleet_lockstep.py`, `tests/e2e/test_fleet_scaling.py`, `tests/unit/test_crew_assembler.py`, `tests/unit/test_fleet.py`, `tests/unit/test_gpu.py`, `tests/unit/test_model_manager.py`, `tests/unit/test_packaging_versioning.py`, `tests/unit/test_resilience.py` | 8 | DELEGATED | agnosai `tests/fleet_*.tcyr`, `llm_*.tcyr`, `definitions_*.tcyr` | See §8 |
| `tests/unit/test_crewai_compat.py` | 1 | REPLACED | Brief §2 |  |
| `tests/integration/test_agent_communication.py`, `tests/unit/integration/test_yeoman_integration.py`, `tests/unit/integration/test_yeoman_schemas.py` | 3 | REPLACED | Brief §7.3; §2 (Redis, Celery) |  |
| `tests/unit/integration/test_agnos_agent_registration.py` | 1 | REPLACED | ADR 0002 |  |
| `tests/e2e/test_agnos_gateway.py`, `tests/unit/integration/test_agnos_clients.py`, `tests/unit/integration/test_agnos_rpc.py`, `tests/unit/integration/test_agnos_vector_client.py` | 4 | NOT PORTED | G13 | The gateway round trip still matters: §8 |
| `tests/unit/test_agent_metrics.py`, `tests/unit/test_metrics.py` | 2 | NOT PORTED | G7 |  |
| `tests/unit/test_alerts.py` | 1 | NOT PORTED | G8 |  |
| `tests/unit/test_agent_monitor.py`, `tests/unit/webgui/test_dashboard.py` | 2 | NOT PORTED | G9 |  |
| `tests/unit/webgui/test_report_delivery.py`, `tests/unit/webgui/test_scheduled_reports.py` | 2 | NOT PORTED | G6 |  |
| `tests/unit/test_database_models.py` | 1 | NOT PORTED | G5 |  |
| `tests/unit/test_observability.py` | 1 | NOT PORTED | G12 | Mixed: see §8 |
| `tests/e2e/test_crew_dual_backend.py`, `tests/e2e/test_smoke.py`, `tests/e2e/test_task_lifecycle.py`, `tests/unit/test_agent_registry.py`, `tests/unit/test_agnosai_backend.py`, `tests/unit/test_api_validation.py`, `tests/unit/test_audit.py`, `tests/unit/test_backend_router.py`, `tests/unit/test_base_agent.py`, `tests/unit/test_config_environment.py`, `tests/unit/test_constants.py`, `tests/unit/test_logging_config.py`, `tests/unit/test_permission_validator.py`, `tests/unit/test_team_config.py`, `tests/unit/test_tenant.py`, `tests/unit/test_tenant_isolation.py`, `tests/unit/test_token_manager.py`, `tests/unit/webgui/test_api_routes.py`, `tests/unit/webgui/test_app.py`, `tests/unit/webgui/test_auth.py`, `tests/unit/webgui/test_crews_api.py`, `tests/unit/webgui/test_definitions_api.py`, `tests/unit/webgui/test_task_routes.py` | 23 | PORTED | See §8 | Crews, definitions, presets, auth, tenancy, health, config, logging, audit |

### docs (57 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docs/deployment/kubernetes.md` | 1 | REPLACED | Roadmap Out of scope |  |
| `docs/development/benchmarks.md` | 1 | REPLACED | ORACLE-AUDIT §4 |  |
| `docs/agents/index.md` | 1 | SCHEDULED | M6 | Role and tool intent |
| `docs/` | 54 | NOT PORTED | G15 | No recorded fate. All Python-stack prose; recoverable from git |

### scripts (7 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `scripts/bump-version.sh` | 1 | PORTED | `scripts/version-bump.sh` |  |
| `scripts/build-release.sh` | 1 | PORTED | `.github/workflows/release.yml` |  |
| `scripts/export-openapi.py` | 1 | PORTED | `scripts/gen-api-schema.sh`, `agnostic api schema`; `tests/api_schema.tcyr` | ADR 0015 |
| `scripts/generate-sdk.sh` | 1 | REPLACED | ADR 0015 (OpenAPI rejected until field types exist) |  |
| `scripts/build-docker.sh` | 1 | NOT PORTED | G14 |  |
| `scripts/run-e2e.sh`, `scripts/smoke_tests.py` | 2 | NOT PORTED | G17 |  |

### benchmarks (8 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `benchmarks/__init__.py`, `benchmarks/__main__.py`, `benchmarks/conftest.py`, `benchmarks/report.py`, `benchmarks/run.py`, `benchmarks/runner.py`, `benchmarks/scenarios.py`, `benchmarks/test_crewai_vs_agnosai.py` | 8 | REPLACED | Roadmap Out of scope; ORACLE-AUDIT §4 | agnostic baseline: `tests/agnostic.bcyr`, `BENCHMARKS.md` |

### docker (16 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docker-compose.dev.yml`, `docker-compose.old-style.yml`, `docker-compose.prod.yml`, `docker-compose.test.yml`, `docker/Dockerfile.agent`, `docker/Dockerfile.agnos`, `docker/Dockerfile.base`, `docker/pg-init.sh` | 8 | REPLACED | Brief §2 (patra row); roadmap Out of scope | Multi-container topology |
| `.dockerignore`, `Dockerfile`, `docker-compose.tls.yml`, `docker-compose.yml`, `docker/README.md`, `docker/agent-entrypoint.sh`, `docker/entrypoint.sh`, `docker/supervisord.conf` | 8 | NOT PORTED | G14 | Single-node path and TLS |

### k8s (43 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `k8s/` | 43 | REPLACED | Roadmap Out of scope (Kubernetes topology parity) |  |

### monitoring (5 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docker-compose.monitoring.yml`, `monitoring/alertmanager.yml`, `monitoring/grafana/dashboards/dashboard.yml`, `monitoring/grafana/datasources/prometheus.yml`, `monitoring/prometheus.yml` | 5 | NOT PORTED | G7 | No dashboards, no rules |

### logging (2 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `docker-compose.logging.yml`, `logging/logstash.conf` | 2 | NOT PORTED | G7 | Logs are JSON on stdout (`src/log.cyr`) |

### alembic (6 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `alembic.ini`, `alembic/README`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/a1b2c3d4e5f6_apscheduler_jobs_table.py`, `alembic/versions/db8d3fe1686e_initial_schema.py` | 6 | REPLACED | Brief §2 (patra replaces PostgreSQL and SQLAlchemy) | No data exists to migrate (`state.md`, Consumers: none). A patra migration story is unrecorded: it needs one before 1.0 freezes the file format |

### tls/certs (2 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `certs/generate-certs.sh`, `tls/rabbitmq/rabbitmq.conf` | 2 | REPLACED | Brief §5.2 (AMQP), §2 (Redis) | Internal Redis and RabbitMQ TLS. Server TLS: G14 |

### examples (2 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `examples/api_testing_example.json`, `examples/ecommerce_checkout_testing.json` | 2 | NOT PORTED | G17 |  |

### public (1 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `public/favicon.svg` | 1 | REPLACED | Brief §7 D3 | The shell has its own inline icon |

### top-level (20 files)

| Path | Files | Status | Where | Note |
|---|---:|---|---|---|
| `.github/actions/setup-python-env/action.yml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml` | 3 | PORTED | `.github/workflows/ci.yml`, `release.yml` | Rewritten for agnostic |
| `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`, `.github/pull_request_template.md`, `.github/workflows/dependency-update.yml` | 4 | NOT PORTED | G17 |  |
| `.pre-commit-config.yaml` | 1 | PORTED | `scripts/check-clean.sh` |  |
| `.env.example` | 1 | NOT PORTED | G15 |  |
| `.gitignore` | 1 | NOISE |  |  |
| `CHANGELOG.md` | 1 | NOT PORTED | G15 |  |
| `LICENSE`, `README.md`, `VERSION` | 3 | PORTED | Root `LICENSE`, `VERSION`, `README.md` | CalVer to SemVer (`state.md`) |
| `agnostic.agpkg.toml` | 1 | SCHEDULED | v1.0 criterion (Zugot recipe), not a milestone |  |
| `chainlit.md` | 1 | REPLACED | Brief §7 D3 |  |
| `pyproject.toml`, `requirements-docker.txt`, `requirements.txt` | 3 | REPLACED | `CONTRIBUTING.md:5-8`; ORACLE-AUDIT §3.13 |  |
| `run_tests.py` | 1 | PORTED | `cyrius test` |  |

## 5. Comparison 1: routes

Python exposes **106** routes: 103 under `/api/v1`, plus `/health`, `/ready` and `/ws/realtime`. The Chainlit chat handlers in `webgui/app.py` are not HTTP routes; D3 replaces them. `schema.json` lists **27** method-and-path pairs.

Result: 9 ported, 10 renamed, 13 replaced, 12 scheduled, 62 not ported. Line numbers are from `webgui/`.

Routes only agnostic has: `GET /api/v1/crews/:id/events`, `GET /api/v1/crews/:id/plan`, `GET /api/v1/audit`, `GET /api/v1/audit/entries`, `GET /api/v1/plugins`, `PUT /api/v1/plugins/:id`, `GET /api/v1/plugins/:id/data`, `GET /api/v1/plugins/:id/data/:key`, `PUT /api/v1/plugins/:id/data/:key`, `DELETE /api/v1/plugins/:id/data/:key`, `GET /ui`, `GET /ui/`, `GET /ui/plugins/:id`.

| Source | Method | Python path | Status | Target or record | Note |
|---|---|---|---|---|---|
| `routes/agents.py:47` | GET | `/api/v1/agents/registration-status` | replaced | ADR 0002 |  |
| `routes/agents.py:62` | POST | `/api/v1/agents/register-agnostic` | replaced | ADR 0002 |  |
| `routes/agents.py:81` | POST | `/api/v1/agents/deregister-agnostic` | replaced | ADR 0002 |  |
| `routes/agents.py:98` | GET | `/api/v1/agents/queues` | not ported | G9 | No queue survives (roadmap Settled 2026-08-21), but the route's fate is unrecorded |
| `routes/agents.py:107` | GET | `/api/v1/agents/{agent_name}` | not ported | G9 |  |
| `routes/agents.py:120` | GET | `/api/v1/agents` | not ported | G9 |  |
| `routes/auth.py:88` | POST | `/api/v1/auth/login` | ported | `POST /api/v1/auth/login` | Answers `token`, not `access_token`; no refresh token |
| `routes/auth.py:126` | POST | `/api/v1/auth/refresh` | replaced | Roadmap Settled 2026-08-20, by rule | Not named. No refresh token ever existed. agnostic tokens last 3600 s |
| `routes/auth.py:139` | POST | `/api/v1/auth/logout` | replaced | Roadmap Settled 2026-08-20, by rule | Not named. The shell clears its token; revocation is the role re-read |
| `routes/auth.py:156` | GET | `/api/v1/auth/me` | not ported | G1 |  |
| `routes/auth.py:171` | POST | `/api/v1/auth/api-keys` | not ported | G1 |  |
| `routes/auth.py:197` | GET | `/api/v1/auth/api-keys` | not ported | G1 |  |
| `routes/auth.py:218` | DELETE | `/api/v1/auth/api-keys/{key_id}` | not ported | G1 |  |
| `routes/crews.py:681` | POST | `/api/v1/crews` | ported | `POST /api/v1/crews` | 201 to 202. Body is agents and tasks. Fields: G4. Webhook: G3 |
| `routes/crews.py:856` | GET | `/api/v1/crews/{crew_id}` | ported | `GET /api/v1/crews/:id` |  |
| `routes/crews.py:877` | GET | `/api/v1/crews` | ported | `GET /api/v1/crews` | `offset` to a cursor (ADR 0008) |
| `routes/crews.py:930` | POST | `/api/v1/crews/{crew_id}/cancel` | ported | `POST /api/v1/crews/:id/cancel` | Stops work (design lesson 4) |
| `routes/dashboard.py:105` | GET | `/api/v1/dashboard` | not ported | G9 |  |
| `routes/dashboard.py:115` | GET | `/api/v1/dashboard/sessions` | not ported | G9 | Read a key nothing writes |
| `routes/dashboard.py:126` | GET | `/api/v1/dashboard/agents` | not ported | G9 |  |
| `routes/dashboard.py:137` | GET | `/api/v1/dashboard/metrics` | not ported | G9 |  |
| `routes/dashboard.py:147` | GET | `/api/v1/dashboard/agent-metrics` | not ported | G7 |  |
| `routes/dashboard.py:157` | GET | `/api/v1/dashboard/llm` | not ported | G7 |  |
| `routes/dashboard.py:167` | GET | `/api/v1/dashboard/llm-gateway` | not ported | G9 | hoosh serves its own health |
| `routes/dashboard.py:178` | GET | `/api/v1/dashboard/yeoman` | replaced | Brief §7.3; roadmap Out of scope |  |
| `routes/dashboard.py:197` | GET | `/api/v1/dashboard/unified` | replaced | Brief §7.3; roadmap Out of scope | AGNOSTIC plus YEOMAN view |
| `routes/dashboard.py:245` | GET | `/api/v1/dashboard/widget` | replaced | Brief §7.3; roadmap Out of scope | Embeddable for YEOMAN |
| `routes/dashboard.py:339` | GET | `/api/v1/dashboard/token-budget` | replaced | Brief §2 (hoosh owns budgets) |  |
| `routes/dashboard.py:383` | GET | `/api/v1/dashboard/recordings` | not ported | G13 |  |
| `routes/dashboard.py:407` | GET | `/api/v1/alerts` | not ported | G8 |  |
| `routes/dashboard.py:443` | GET | `/api/v1/metrics` | not ported | G7 |  |
| `routes/definitions.py:151` | GET | `/api/v1/definitions` | renamed | `GET /api/v1/agents/definitions` | No `domain`, `limit`, `offset` |
| `routes/definitions.py:213` | GET | `/api/v1/definitions/{agent_key}` | renamed | `GET /api/v1/agents/definitions/:key` |  |
| `routes/definitions.py:231` | POST | `/api/v1/definitions` | renamed | `POST /api/v1/agents/definitions` | `agent_key` to `key` |
| `routes/definitions.py:265` | PUT | `/api/v1/definitions/{agent_key}` | renamed | `PUT /api/v1/agents/definitions/:key` | With `If-Match` |
| `routes/definitions.py:303` | DELETE | `/api/v1/definitions/{agent_key}` | renamed | `DELETE /api/v1/agents/definitions/:key` | With `If-Match` |
| `routes/definitions.py:336` | GET | `/api/v1/presets` | ported | `GET /api/v1/presets` | No `domain`, `size` filters |
| `routes/definitions.py:400` | GET | `/api/v1/presets/{preset_name}` | ported | `GET /api/v1/presets/:name` |  |
| `routes/definitions.py:432` | POST | `/api/v1/presets` | not ported | G16 |  |
| `routes/definitions.py:479` | DELETE | `/api/v1/presets/{preset_name}` | not ported | G16 |  |
| `routes/definitions.py:529` | GET | `/api/v1/definitions/{agent_key}/versions` | not ported | G10 |  |
| `routes/definitions.py:543` | POST | `/api/v1/definitions/{agent_key}/versions` | not ported | G10 |  |
| `routes/definitions.py:561` | POST | `/api/v1/definitions/{agent_key}/rollback` | not ported | G10 |  |
| `routes/definitions.py:595` | POST | `/api/v1/packages/export` | not ported | G10 |  |
| `routes/definitions.py:627` | POST | `/api/v1/packages/import` | not ported | G10 |  |
| `routes/definitions.py:682` | POST | `/api/v1/tools/upload` | not ported | G10 |  |
| `routes/definitions.py:716` | GET | `/api/v1/tools` | not ported | G10 |  |
| `routes/fleet.py:28` | GET | `/api/v1/fleet/nodes` | not ported | G10 |  |
| `routes/fleet.py:51` | GET | `/api/v1/fleet/nodes/{node_id}` | not ported | G10 |  |
| `routes/fleet.py:66` | GET | `/api/v1/fleet/groups` | not ported | G10 |  |
| `routes/fleet.py:78` | GET | `/api/v1/fleet/status` | not ported | G10 |  |
| `routes/fleet.py:106` | GET | `/api/v1/fleet/gpu` | not ported | G10 |  |
| `routes/fleet.py:139` | POST | `/api/v1/fleet/evict` | not ported | G10 |  |
| `routes/gpu.py:18` | GET | `/api/v1/gpu/status` | not ported | G10 |  |
| `routes/gpu.py:33` | GET | `/api/v1/gpu/devices/{device_index}` | not ported | G10 |  |
| `routes/gpu.py:48` | GET | `/api/v1/gpu/memory` | not ported | G10 |  |
| `routes/gpu.py:84` | GET | `/api/v1/gpu/slots` | not ported | G10 |  |
| `routes/gpu.py:104` | GET | `/api/v1/gpu/inference` | not ported | G10 |  |
| `routes/integration.py:31` | GET | `/api/v1/results/structured/{session_id}` | replaced | Brief §7.3; roadmap Out of scope | The result model is worth keeping: §10 |
| `routes/mcp.py:626` | GET | `/api/v1/mcp/tools` | scheduled | M7 | `tools/list` at `/mcp` |
| `routes/mcp.py:650` | GET | `/api/v1/mcp/server-info` | scheduled | M7 | MCP 2026-07-28 has no handshake |
| `routes/mcp.py:670` | POST | `/api/v1/mcp/invoke` | scheduled | M7 | Same path by name |
| `routes/persistence.py:120` | GET | `/api/v1/test-sessions` | not ported | G5 |  |
| `routes/persistence.py:151` | POST | `/api/v1/test-sessions` | not ported | G5 |  |
| `routes/persistence.py:176` | PUT | `/api/v1/test-sessions/{session_id}/status` | not ported | G5 |  |
| `routes/persistence.py:199` | GET | `/api/v1/test-results` | not ported | G5 |  |
| `routes/persistence.py:236` | POST | `/api/v1/test-results` | not ported | G5 |  |
| `routes/persistence.py:253` | GET | `/api/v1/test-results/{session_id}/summary` | not ported | G5 |  |
| `routes/persistence.py:273` | GET | `/api/v1/test-metrics/trends` | scheduled | M8 | Quality trends |
| `routes/persistence.py:288` | GET | `/api/v1/test-sessions/diff` | scheduled | M8 | Comparison reports |
| `routes/reports.py:75` | GET | `/api/v1/reports` | scheduled | M8 |  |
| `routes/reports.py:106` | POST | `/api/v1/reports/generate` | scheduled | M8 |  |
| `routes/reports.py:156` | GET | `/api/v1/reports/{report_id}/download` | scheduled | M8 | Path traversal re-opens here (roadmap M8) |
| `routes/reports.py:208` | GET | `/api/v1/reports/scheduled` | not ported | G6 |  |
| `routes/reports.py:226` | POST | `/api/v1/reports/scheduled` | not ported | G6 |  |
| `routes/reports.py:264` | DELETE | `/api/v1/reports/scheduled/{job_id}` | not ported | G6 |  |
| `routes/rpc.py:67` | POST | `/api/v1/rpc/handle` | not ported | G13 |  |
| `routes/rpc.py:125` | GET | `/api/v1/rpc/methods` | not ported | G13 |  |
| `routes/sessions.py:36` | GET | `/api/v1/sessions` | renamed | `GET /api/v1/crews` | Read a key nothing writes |
| `routes/sessions.py:84` | GET | `/api/v1/sessions/search` | not ported | G9 | Only `?status=` exists |
| `routes/sessions.py:97` | GET | `/api/v1/sessions/{session_id}` | renamed | `GET /api/v1/crews/:id` |  |
| `routes/sessions.py:109` | POST | `/api/v1/sessions/compare` | scheduled | M8 | Comparison reports |
| `routes/tasks.py:197` | POST | `/api/v1/tasks` | renamed | `POST /api/v1/crews` | A wrapper over `run_crew`; shape differs |
| `routes/tasks.py:257` | GET | `/api/v1/tasks/{task_id}` | renamed | `GET /api/v1/crews/:id` |  |
| `routes/tasks.py:297` | DELETE | `/api/v1/tasks/{task_id}` | renamed | `POST /api/v1/crews/:id/cancel` |  |
| `routes/tasks.py:344` | POST | `/api/v1/tasks/{task_id}/retry` | not ported | G4 |  |
| `routes/tasks.py:419` | POST | `/api/v1/tasks/security` | not ported | G4 |  |
| `routes/tasks.py:440` | POST | `/api/v1/tasks/performance` | not ported | G4 |  |
| `routes/tasks.py:460` | POST | `/api/v1/tasks/regression` | not ported | G4 |  |
| `routes/tasks.py:480` | POST | `/api/v1/tasks/full` | not ported | G4 |  |
| `routes/tasks.py:523` | POST | `/api/v1/a2a/receive` | scheduled | M7 | A2A callback endpoint |
| `routes/tasks.py:690` | GET | `/api/v1/a2a/capabilities` | scheduled | M7 | Signed Agent Card |
| `routes/tenants.py:88` | GET | `/api/v1/tenants` | not ported | G1 |  |
| `routes/tenants.py:127` | POST | `/api/v1/tenants` | not ported | G1 |  |
| `routes/tenants.py:158` | GET | `/api/v1/tenants/{tenant_id}` | not ported | G1 |  |
| `routes/tenants.py:189` | PUT | `/api/v1/tenants/{tenant_id}` | not ported | G1 |  |
| `routes/tenants.py:219` | DELETE | `/api/v1/tenants/{tenant_id}` | not ported | G1 |  |
| `routes/tenants.py:246` | GET | `/api/v1/tenants/{tenant_id}/users` | not ported | G1 |  |
| `routes/tenants.py:282` | POST | `/api/v1/tenants/{tenant_id}/users` | not ported | G1 |  |
| `routes/tenants.py:314` | DELETE | `/api/v1/tenants/{tenant_id}/users/{user_id}` | not ported | G1 |  |
| `routes/yeoman_webhooks.py:276` | POST | `/api/v1/yeoman/webhooks` | replaced | Brief §7.3; roadmap Out of scope |  |
| `routes/yeoman_webhooks.py:399` | GET | `/api/v1/yeoman/events/stream` | replaced | Brief §7.3; roadmap Out of scope | Crew streaming is on M9 |
| `routes/yeoman_webhooks.py:458` | GET | `/api/v1/yeoman/events` | replaced | Brief §7.3; roadmap Out of scope |  |
| `app.py` | GET | `/health` | ported | `GET /health` | Liveness only (ADR 0001); `tests/health.tcyr` |
| `app.py` | GET | `/ready` | ported | `GET /ready` | `tests/health.tcyr` |
| `app.py` | WS | `/ws/realtime` | scheduled | M9 | Streaming crew events; the cursor polls today |

Parameters that disappeared with a route that stayed: `domain`, `limit`, `offset` on definitions; `domain`, `size` on presets; `offset` on crews (replaced by a cursor). Also, `X-API-Key` became `Authorization: ApiKey`, and `{"detail": ...}` errors became `{"error": ...}`.

## 6. Comparison 2: configuration

Python's non-test code reads **192** names (AST over every `getenv`, `environ.get`, `environ[...]`). `src/config.cyr` reads **22**, and no other file in `src/` calls `getenv`.

Result: 22 renamed, 88 replaced, 10 scheduled, 72 not ported. Nothing keeps its Python name, so an old `.env` applies nothing; the default port, 8000, is the only setting that carries over. Two reads are dynamic: `config/agnos_environment.py:112` (profile keys) and `webgui/routes/crews.py:210-258` (GPU variables, set per agent).

| Python names | Status | agnostic or owner | Record |
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
| `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`, `DB_POOL_SIZE`, `DB_POOL_TIMEOUT` | replaced | No pool | Brief §2 (patra) |
| `REDIS_DB`, `REDIS_HOST`, `REDIS_MAX_CONNECTIONS`, `REDIS_PASSWORD`, `REDIS_PORT`, `REDIS_URL` | replaced | No Redis | Brief §2; roadmap Settled 2026-08-21 |
| `RABBITMQ_HOST`, `RABBITMQ_PASSWORD`, `RABBITMQ_PORT`, `RABBITMQ_URL`, `RABBITMQ_USER`, `RABBITMQ_VHOST` | replaced | No AMQP | Brief §5.2 |
| `AGNOSAI_API_KEY`, `AGNOSAI_URL`, `AGNOSTIC_BACKEND` | replaced | agnosai is linked in-process | Brief §7 D1 |
| `AGNOS_LLM_GATEWAY_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL` | replaced | hoosh holds provider keys; a model is per agent (`llm_model`) | Brief §2 |
| `LLM_STREAM_CHUNK_TIMEOUT` | replaced | agnosai's own timeouts | Brief §2 |
| `AGNOS_LOCAL_INFERENCE_API_KEY`, `AGNOS_LOCAL_INFERENCE_ENABLED`, `AGNOS_LOCAL_INFERENCE_GPU_MIN_FREE_MB`, `AGNOS_LOCAL_INFERENCE_MAX_PARAMS_B`, `AGNOS_LOCAL_INFERENCE_MODELS`, `AGNOS_LOCAL_INFERENCE_PROVIDER`, `AGNOS_LOCAL_INFERENCE_URL` | replaced | hoosh routes local models | Brief §2 |
| `AGNOS_TOKEN_BUDGET_API_KEY`, `AGNOS_TOKEN_BUDGET_ENABLED`, `AGNOS_TOKEN_BUDGET_POOL`, `AGNOS_TOKEN_BUDGET_URL` | replaced | hoosh owns budgets | Brief §2; roadmap F5 |
| `AGNOS_TOOL_SANDBOX_ENABLED`, `AGNOS_TOOL_SANDBOX_MAX_MEM_MB`, `AGNOS_TOOL_SANDBOX_TIMEOUT` | replaced | kavach owns the sandbox | Roadmap M6 |
| `AGNOS_GPU_ENABLED`, `AGNOS_GPU_PROBE_INTERVAL`, `AGNOS_GPU_PROBE_PATH` | replaced | ai-hwaccel | Brief §2 |
| `AGNOS_AGENT_REGISTRATION_ENABLED`, `AGNOS_CAPABILITY_ADVERTISE_ENABLED`, `AGNOS_HEARTBEAT_INTERVAL_SECONDS` | replaced | No process registration | ADR 0002 |
| `CORS_ALLOWED_ORIGINS` | replaced | The server grants no CORS | ADRs 0005, 0006 |
| `MAX_ACTIVE_SESSIONS` | replaced | Chainlit session cap | Brief §7 D3 |
| `OAUTH2_AZURE_CLIENT_ID`, `OAUTH2_AZURE_TENANT_ID`, `OAUTH2_GITHUB_CLIENT_ID`, `OAUTH2_GITHUB_CLIENT_SECRET`, `OAUTH2_GOOGLE_CLIENT_ID` | replaced | Three unreachable providers | Roadmap Settled 2026-08-20 |
| `AGNOSTIC_EXTERNAL_URL`, `EVENT_BUFFER_MAX`, `SSE_KEEPALIVE_INTERVAL`, `WEBHOOK_MAX_BODY_SIZE`, `YEOMAN_A2A_API_KEY`, `YEOMAN_A2A_ENABLED`, `YEOMAN_A2A_URL`, `YEOMAN_AUDIT_API_KEY`, `YEOMAN_AUDIT_ENABLED`, `YEOMAN_AUDIT_URL`, `YEOMAN_COVERAGE_THRESHOLD`, `YEOMAN_DLP_API_KEY`, `YEOMAN_DLP_BLOCK_ON_FINDING`, `YEOMAN_DLP_ENABLED`, `YEOMAN_DLP_TIMEOUT`, `YEOMAN_DLP_URL`, `YEOMAN_ERROR_RATE_THRESHOLD`, `YEOMAN_EVENT_PUSH_ENABLED`, `YEOMAN_EVENT_PUSH_SECRET`, `YEOMAN_EVENT_PUSH_URL`, `YEOMAN_JWT_AUDIENCE`, `YEOMAN_JWT_ENABLED`, `YEOMAN_JWT_ISSUER`, `YEOMAN_JWT_PUBLIC_KEY`, `YEOMAN_JWT_SECRET`, `YEOMAN_MCP_API_KEY`, `YEOMAN_MCP_AUTO_REGISTER`, `YEOMAN_MCP_URL`, `YEOMAN_OIDC_DISCOVERY_URL`, `YEOMAN_PEER_ID`, `YEOMAN_PERF_DEGRADATION_FACTOR`, `YEOMAN_WEBHOOKS_ENABLED`, `YEOMAN_WEBHOOK_SECRET` | replaced | SecureYeoman surface | Brief §7.3; roadmap Out of scope |
| `AGNOSAI_BENCH_URL`, `BENCH_ROUNDS`, `CREWAI_BENCH_URL`, `OLLAMA_MODEL`, `OLLAMA_URL` | replaced | `benchmarks/` only | Roadmap Out of scope; ORACLE-AUDIT §4 |
| `AGNOS_AGENT_API_KEY`, `AGNOS_AGENT_REGISTRY_URL`, `DAIMON_MCP_AUTO_REGISTER` | scheduled | M7: the env-gated, default-off tool registrar | ADR 0002 |
| `MCP_SERVER_ENABLED` | scheduled | M7 |  |
| `A2A_RATE_LIMIT` | scheduled | M7, with the A2A endpoint | Limit itself: G11 |
| `REPORTS_DIR` | scheduled | M8 |  |
| `REALTIME_IDLE_TIMEOUT_SECONDS`, `REALTIME_MAX_MESSAGE_SIZE`, `REALTIME_STREAM_MAX_LEN`, `REALTIME_STREAM_REPLAY_LIMIT` | scheduled | M9 |  |
| `AGNOSTIC_API_KEY`, `DEFAULT_TENANT_ID`, `MULTI_TENANT_ENABLED` | not ported | G1 |  |
| `ENVIRONMENT`, `HOME`, `WEBGUI_SECRET_KEY` | not ported | G2 |  |
| `WEBHOOK_MAX_RETRIES` | not ported | G3 |  |
| `QA_TEAM_SIZE` | not ported | G4 |  |
| `REDIS_SCHEDULER_DB`, `REPORT_DELIVERY_MAX_RETRIES`, `REPORT_EMAIL_ENABLED`, `REPORT_EMAIL_RECIPIENTS`, `REPORT_SLACK_WEBHOOK_URL`, `REPORT_WEBHOOK_SECRET`, `REPORT_WEBHOOK_URL`, `SCHEDULED_REPORTS_ENABLED`, `SCHEDULED_REPORT_DAILY_TIME`, `SCHEDULED_REPORT_WEEKLY_DAY`, `SCHEDULED_REPORT_WEEKLY_TIME`, `SCHEDULER_JOBSTORE`, `SMTP_FROM`, `SMTP_HOST`, `SMTP_PASSWORD`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_USE_TLS`, `TZ` | not ported | G6 |  |
| `METRICS_AUTH_TOKEN` | not ported | G7 |  |
| `ALERTS_ENABLED`, `ALERT_COOLDOWN_SECONDS`, `ALERT_DELIVERY_MAX_RETRIES`, `ALERT_EMAIL_RECIPIENTS`, `ALERT_POLL_INTERVAL_SECONDS`, `ALERT_SLACK_WEBHOOK_URL`, `ALERT_WEBHOOK_SECRET`, `ALERT_WEBHOOK_URL` | not ported | G8 |  |
| `AGENT_MONITOR_CACHE_MAX_ENTRIES`, `AGENT_STALE_THRESHOLD_SECONDS` | not ported | G9 |  |
| `AGNOSTIC_MAX_VERSIONS`, `AGNOS_FLEET_ENABLED`, `AGNOS_FLEET_EXTERNAL_URL`, `AGNOS_FLEET_GROUP`, `AGNOS_FLEET_HEARTBEAT_INTERVAL`, `AGNOS_FLEET_HEARTBEAT_TTL`, `AGNOS_FLEET_NODE_ID` | not ported | G10 |  |
| `TENANT_DEFAULT_RATE_LIMIT` | not ported | G11 |  |
| `AGNOS_AUDIT_API_KEY`, `AGNOS_AUDIT_BATCH_SIZE`, `AGNOS_AUDIT_ENABLED`, `AGNOS_AUDIT_FLUSH_INTERVAL`, `AGNOS_AUDIT_URL`, `AGNOS_DASHBOARD_API_KEY`, `AGNOS_DASHBOARD_BRIDGE_ENABLED`, `AGNOS_DASHBOARD_PUSH_INTERVAL`, `AGNOS_DASHBOARD_URL`, `AGNOS_MEMORY_API_KEY`, `AGNOS_MEMORY_ENABLED`, `AGNOS_MEMORY_URL`, `AGNOS_PATH_PREFIX`, `AGNOS_PROFILE`, `AGNOS_PROFILE_API_KEY`, `AGNOS_PROFILE_URL`, `AGNOS_RAG_ENABLED`, `AGNOS_REASONING_API_KEY`, `AGNOS_REASONING_ENABLED`, `AGNOS_REASONING_URL`, `AGNOS_RPC_ENABLED`, `AGNOS_SCREEN_ENABLED`, `AGNOS_VECTOR_API_KEY`, `AGNOS_VECTOR_COLLECTION`, `AGNOS_VECTOR_ENABLED`, `AGNOS_VECTOR_URL` | not ported | G13 |  |

`src/config.cyr` side:

| agnostic names | Origin |
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

`src/presets_data.cyr` is generated by `scripts/gen-presets.sh`, from `src/presets/*.json`. It does **not** read `python-port/`. The script embeds each document whitespace-collapsed as a agnostic literal, in a fixed order that `tests/presets.tcyr` asserts. `check-clean.sh` runs `--check`, and that check passed with `python-port/` absent. No extraction is needed.

### The 36 tool classes

None was ever registered (§3.15). Two names resolve in agnostic, and 34 do not. Behaviour by reading each class: 21 local computation, 5 does i/o, 4 local, uses `random`, 3 local, calls an llm, 3 hard-coded stub. "Hard-coded stub" means `_run` returns a literal; `LoadTestingTool` is one, so the alias to agnosai's real `load_testing` is an upgrade, not a port.

| Class | Module | Python `name` | Lines | Behaviour | Python test | Presets | agnostic state |
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

`webgui/routes/mcp.py` declares **34** MCP tools, and **none of them is one of the 38**. They are operations, such as `agnostic_submit_task` and `agnostic_gpu_status`. M7 says the "full QA tool surface" of 38 is settled. Answered 2026-11-05: `/mcp` carries those 38 beside tools that mirror agnostic's own routes, and these 34 are not the list. Most of them route to surfaces in G1, G5, G7, G9 and G10.

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

By behaviour, not by count. Bold marks behaviours with a Python test, no agnostic test, and a reason to care.

| Python suites | agnostic suites | Verdict |
|---|---|---|
| Crew API: `unit/webgui/test_crews_api`, `e2e/test_crew_dual_backend`, `e2e/test_task_lifecycle`, `unit/webgui/test_task_routes` (submit, poll, cancel) | `crews_route`, `crew_request`, `crew_tenancy`, `ledger`, `outcome`, `crewstore`, `restart` | Better. agnostic asserts the wire (lessons 1–4, 6); Python mocked it (§3.7, §3.8). |
| Definitions and presets: `unit/webgui/test_definitions_api`, `test_base_agent`, `test_agent_registry`, `test_team_config`, `test_constants` | `agentdef`, `presets`, `router`, `tools` | Equal for CRUD and key rules. Preset writes: G16. Team-size filters are gone. |
| Auth: `unit/webgui/test_auth`, `test_token_manager`, `test_permission_validator` | `authn`, `authstore`, `authz`, `jwt`, `crypto`, `loginguard`, `loginroute` | Better on the security properties (mutation-checked). No route-level test of key or user management, because the routes do not exist: G1. |
| Tenancy: `test_tenant`, `test_tenant_isolation` | `authz` (`tenant/*`), `crew_tenancy`, `plugindata` | Isolation better. Tenant CRUD over HTTP, per-tenant rate limits and API-key isolation have no agnostic test: G1, G11. |
| HTTP plumbing: `unit/webgui/test_api_routes`, `test_app`, `test_api_validation` | `router`, `health`, `codec`, `serve_mount`, `plugindata`, `api_schema` | Better; the schema snapshot has no Python equivalent. Report download security and SSRF (11 cases) have no agnostic test: M8 and G3. |
| Config and logging: `test_config_environment`, `test_logging_config` | `config`, `log`, `trace` | Better. Strict parsing is pure-function tested. `agnostic_config_from_env` itself cannot be (no `setenv`). |
| Audit: `test_audit` | `audit`, `store_concurrency` | Better on integrity. Failed-login and rate-limit events: G12. |
| Observability: `test_observability` | `trace`, `server_span`, `log` | Traces better. A2A audit, rate-limit and payload-validation cases move to M7. Correlation id is replaced by W3C trace context. |
| Metrics: `test_metrics`, `test_agent_metrics`, `e2e/test_smoke::prometheus_metrics` | None | **No agnostic test, still matters if G7 is ported.** |
| Resilience: `test_resilience` | agnosai `llm_retry`, `server_rate_limit` | Delegated, except `TestGracefulShutdown`: **no suite sends a signal to Agnostic's server.** `restart` covers what survives, not a clean stop with crews running. |
| Fleet and GPU: `test_fleet`, `test_gpu`, `e2e/test_fleet_*` | agnosai `fleet_*` | Delegated. Route cases in `TestFleetEndpoints` and `TestGPUEndpoints` follow G10. |
| Crew assembly: `test_crew_assembler` | agnosai `definitions_assembler` | `assemble_team` delegated. `TestRecommendPreset` (9) has no counterpart anywhere: G10. |
| Packaging and versioning: `test_packaging_versioning` | agnosai `definitions_packaging`, `definitions_versioning`, `tools_builtin_delegate` | Delegated. Custom-tool upload safety has no counterpart: G10. |
| LLM: `test_model_manager`, `e2e/test_agnos_gateway` | agnosai `llm_hoosh`, `llm_router`; Agnostic `crews_route` (`crews/llm-timeout`) | **Agnostic has no suite that takes a crew through a gateway.** Suites run placeholder mode; the priced runs in `state.md` were manual, against a scratch stand-in (0.1.9, 0.1.10). A stub-gateway suite would meet audit lesson 7 properly and also check the consumer path M7 needs. |
| QA tools: `unit/tools/*` (45 tests, 12 of 36 tools) | `tools` (the gate only) | **M6.** These test Python output shapes, some over hard-coded data, so they are weak as a spec. Their value is the input shape. |
| Data generation: `test_data_generation` | None | M6, if a data-generator tool is built. |
| Reports: `test_report_generator`, `test_history`, `test_session_diff` | None | **M8.** Sanitised output, metric calculation, trend direction and diff semantics all still matter, and M8 needs them. |
| Scheduled reports and delivery: `test_scheduled_reports`, `test_report_delivery` | None | Mocks around code that could not run (G6). Do not carry over. |
| Realtime: `test_realtime`, `test_message_buffer`, `test_yeoman_websocket` | `ledger` (`ledger/ring-cursor`), `crews_route` (`crews/events-*`) | Replay intent covered by the cursor and `missed`. Transport tests on M9. |
| MCP and A2A: `test_api_validation::TestMCPDispatch`, `test_task_routes::TestA2AEndpoints`, `e2e/test_a2a_roundtrip` | None | **M7.** |
| Webhook delivery: `test_task_routes::TestFireWebhook`, `test_api_validation::TestWebhookSignatureVerification` | `loginguard` (`webhook/sign`) | Signature covered and stronger (timestamp inside the MAC). Delivery, retry and SSRF-at-fire have no test: G3. |
| Dashboards and monitor: `test_dashboard`, `test_agent_monitor` | `tests/webgui/*.test.mjs` for the replacement views | Do not carry over: they mock keys nothing writes (G9). |
| Black-box smoke: `e2e/test_smoke`, `scripts/smoke_tests.py` | `serve_mount` (socketpair), `api_schema` (`api/responses`, real mount) | Good in-process. **No CI step binds a port and probes it**: G17. |
| Load: `tests/load/locustfile.py` | `tests/agnostic.bcyr` (micro only) | No concurrent-load test. `store_concurrency` is the closest. Worth one soak run before the v1.0 security audit: `sandhi` closes every connection (brief §5.2) and only a load test shows that. |
| Kubernetes manifests: `tests/k8s` | None | Replaced with the manifests. |
| SecureYeoman and AGNOS clients: `unit/integration/*`, `integration/test_agent_communication` | None | Replaced, or G13. `test_yeoman_schemas` is worth reading again for M8. |
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

Everything committed stays reachable through `git show <rev>:python-port/...`, so nothing is lost by deleting it. This is a list of where things are, not a list of things to carry over.

| Content | Only copy? | Where it goes |
|---|---|---|
| Preset documents (18) | No. `src/presets/*.json` is byte-identical | Nothing to do |
| **Tool intent** for the 36 classes: `name`, `description`, inputs, outputs | **Yes.** Roadmap M6 says to build against "preset-declared intent", but a preset declares a class name and an agent `focus`. The rest is only in the classes and `agents/*/README.md` | Reference while M6 designs each tool for agnostic. Recoverable from git |
| **MCP manifest**: 34 tools with `inputSchema` (`webgui/routes/mcp.py`) | **Yes** | Reference for question 4 (§3). Recoverable from git |
| Result model: `shared/yeoman_schemas.py` (`Finding`, severity and category enums, `SecurityResult`, `PerformanceResult`, `TestExecutionResult`, `QAReport`) | Yes, and the only typed result model in the tree | Reference for question 3 (§3). Recoverable from git |
| Report logic: `webgui/exports.py`, `webgui/history.py`, `shared/database/repository.py` (`diff_sessions`, `get_quality_trends`) | Yes | Recoverable from git. Read §11 first: most of it was unreachable |
| Schema: `alembic/versions/*`, `shared/database/models.py` | Yes | Recoverable. No production data exists. The migration and the models disagree (§11) |
| A2A message types: `webgui/routes/tasks.py`, `docs/api/a2a-protocol.md`, `docs/adr/019-a2a-protocol.md` | Yes | Recoverable. M7 targets A2A v1.0.x, so this is background, not a contract |
| Operator docs: `docs/deployment/*`, `docs/api/*`, `docs/guides/*`, `docs/development/manual-testing.md` | Yes, all Python-stack | Recoverable. agnostic has its own (`docs/guides/`) |
| Python ADRs 001–029, `docs/project/changelog.md`, `CHANGELOG.md`, `README.md` | Yes | Recoverable. History |
| Grafana dashboards, Prometheus rules | **They do not exist.** `monitoring/grafana/dashboards/dashboard.yml` is a provisioning stub, and `rules/` is absent | Nothing to do |
| Fixtures | `tests/fixtures/common.py` is 265 bytes; no data fixtures exist | Nothing to do |
| Benchmark workloads: `benchmarks/scenarios.py` | Yes | Recoverable. Useful only if an end-to-end crew benchmark is added |
| `config/models.json`, `config/testing_targets.json`, `examples/*.json`, `tests/load/locustfile.py` | Yes | Recoverable |
| `.github` issue and PR templates | Yes | Recoverable (G17) |

Before the deletion commit: tag the parent, then put that rev in `ORACLE-AUDIT.md`'s header so its citations resolve.

## 11. Found on the way, not in ORACLE-AUDIT

In the former code. Read these before treating any of it as a guide:

- **Session and agent keys have no writer.** I found no literal `set` of `session:*:info`, `manager:*:test_plan`, `manager:*:verification` or `agent:*:status`. `/sessions`, `/dashboard/sessions`, `/agents` and the report's info and plan sections read them. In `/health`, `any_alive` can never be true, so the best possible answer was `degraded`.
- **Only one report type could be requested.** `ReportGenerateRequest.report_type` allows `executive_summary`, `detailed`, `compliance`, `security`, `performance`. `ReportType` is `executive_summary`, `technical_report`, `compliance_report`, `comparison_report`, `agent_performance`. Only the first is in both, so the others answer 400. The route also refuses `csv`, which `ReportFormat` has.
- **Report content.** `_collect_session_data` reads agent reports that only the legacy Celery workers write, and the default compose does not start them. On the crew path, a report had almost nothing in it.
- **Scheduled jobs raise on construction** (G6).
- **`monitoring/prometheus.yml` scrapes `/metrics`**; the route is `/api/v1/metrics`.
- **The migration and the models disagree.** `shared/database/models.py` has `domain` and `crew_preset`; `alembic/versions/db8d3fe1686e` does not.
- **`webgui/static/**` is never served**: there is no static mount.
- **No importer at all:** `shared/agnos_memory`, `agnos_rag_client`, `agnos_reasoning`, `agnos_screen_client`, `data_generation_service`, `logging_config`, `ssrf`. The four AGNOS clients appear only in a shutdown `close()` loop. `agnos_vector_client` has the same shape with a direct import.
- **`check_quota`, `is_within_trial`, `PERMISSION_DENIED`, `PATH_TRAVERSAL_BLOCKED`** are defined and unused.

In the agnostic record:

- `src/auth/jwt.cyr:72` says an operator can install a secret; nothing lets them (G2).
- `state.md:193` and `src/server/serve.cyr:410` say there is no bootstrap route; the environment bootstrap has existed since M5 part 3.
- The roadmap's M5 entry says "tenant CRUD"; it is library-only (G1).
- The roadmap says Agnostic calls what the engine owns; it does not, for versioning, packaging, the assembler, fleet, GPU or Prometheus (G7, G10).
- `handoff.md:18` says nineteen ADRs; there are twenty. `handoff.md:466` still says a `bayan_pdf_*` request should be filed; roadmap M8 says that is moot. `CONTRIBUTING.md:10` says 85 defects.
- M6 says "preset-declared intent", and presets do not declare it (§10).
- `docs/guides/getting-started.md` still has scaffold text, and `docs/examples/` is empty.
