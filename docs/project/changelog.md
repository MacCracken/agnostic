# Changelog

All notable changes to AAS (Agnostic Agent System) are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions use **YYYY.M.D** (calendar versioning) for git tags and releases.
Same-day patches use **YYYY.M.D-N** suffix (e.g. `2026.3.8-1`, `2026.3.8-2`).
Build artifacts use **agnostic-VERSION** (e.g. `agnostic-2026.3.8-1`).
See `scripts/build-release.sh` for the build-and-rename workflow.

---

## [2026.3.17]

### Added

- **GPU-aware crew scheduling** — `config/gpu.py` detects NVIDIA GPUs via `nvidia-smi` or agnosys probe (`/var/lib/agnosys/gpu.json`). `config/gpu_scheduler.py` assigns agents to devices based on requirements. Per-agent `CUDA_VISIBLE_DEVICES` isolation. Cached probe with 30s TTL
- **GPU memory monitoring & limits** — `CrewRunRequest.gpu_memory_budget_mb` enforces per-crew GPU memory caps. Scheduler pre-checks declared minimums against budget. VRAM snapshots captured before/after each GPU agent execution (stored in crew results as `gpu_vram`)
- **Local LLM inference offload** — `config/local_inference.py` routes eligible models (small, embeddings, reranking) to local vLLM/Ollama/OpenAI-compatible servers. Integrated transparently into `LLMIntegrationService._llm_call`. GPU headroom check, model size heuristic (<14B default), 6 `AGNOS_LOCAL_INFERENCE_*` env vars
- **GPU-accelerated tool execution** — `@register_gpu_tool(gpu_memory_min_mb=N)` decorator in tool registry. `tool_requires_gpu()`/`tool_gpu_memory_min()` queries. `BaseAgent._infer_gpu_from_tools()` auto-promotes agents with GPU tools. `list_registered_tools()` includes GPU info
- **Multi-GPU scheduling across crews** — `GPUSlotTracker` tracks cross-crew GPU reservations process-wide. Crews reserve on start, release on finish (and on failure). Scheduler spreads agents across devices by free memory
- **GPU API endpoints** — `GET /api/v1/gpu/status`, `/gpu/memory`, `/gpu/devices/{index}`, `/gpu/slots`, `/gpu/inference`
- **AgentDefinition GPU fields** — `gpu_required`, `gpu_strict`, `gpu_preferred`, `gpu_memory_min_mb` (only serialized when non-default)
- **67 GPU tests** — detection, scheduling, memory budgets, slot tracker, tool registration, local inference routing, all endpoints. Total: 1055 unit tests
- **`TaskStatus` enum** (`agents/status.py`) — `StrEnum` with `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `PARTIAL`, `CANCELLED`. Single source of truth for status strings
- **`require_admin` dependency** (`webgui/routes/dependencies.py`) — reusable `Depends()` for admin role checks, replacing 7+ inline duplications
- **Version pruning** — `save_version()` now auto-prunes oldest versions when count exceeds `AGNOSTIC_MAX_VERSIONS` (default 50)
- **Symlink traversal fix** — `AgentFactory.from_file()` blocks symlinks that resolve outside `DEFINITIONS_DIR`
- **Webhook SSRF re-validation** — `_fire_webhook()` re-validates callback URL at fire time to guard against stored SSRF / DNS rebinding
- **Background task tracking** — `_background_tasks` set in crews.py prevents GC of fire-and-forget `asyncio.Task` references
- **Module-scope `asyncio.Lock` fix** — `_webhook_client_lock` in tasks.py lazily created via `_get_webhook_lock()` to avoid binding to wrong event loop
- **Async file I/O** — `list_definitions` and `export_package` endpoints now use `run_in_executor` to avoid blocking the event loop
- **`import_package()` dedup** — definition and preset install loops consolidated into shared loop
- **Prometheus crew metrics** — `agnostic_crew_runs_total`, `agnostic_crew_run_duration_seconds`, `agnostic_crew_agent_count`, `agnostic_active_crew_tasks`, `agnostic_tool_registry_size`, `agnostic_definition_cache_hits/misses_total`, `agnostic_gpu_agents_scheduled_total`, `agnostic_gpu_memory_reserved_mb`
- **Definition cache metrics** — `AgentFactory._load_definition_file` records cache hit/miss counters
- **TTL cache for `list_definitions`** — 5-second in-memory cache, invalidated on create/update/delete
- **`.agpkg` multipart file upload** — `POST /api/v1/packages/import` accepts `multipart/form-data` with 10 MB limit
- **`require_rate_limit` dependency** — Redis-backed per-user rate limiter factory in `dependencies.py`
- **Benchmark scripts** — `tests/benchmarks/bench_definitions.py` (10/50/200/500 files) and `tests/benchmarks/bench_packaging.py` (50 defs + 10 presets export/import)
- **18 crew presets** — 5 domains (quality, software-engineering, design, data-engineering, devops) x 3 sizes (lean, standard, large) + `complete-lean` + `quality-security` + `quality-performance`
- **Crew assembler** (`agents/crew_assembler.py`) — `assemble_team()` builds agent definitions from natural-language team specs; `recommend_preset()` suggests best preset from task description
- **Custom team composition** — `CrewRunRequest.team` (TeamSpec) enables "I need a 4-person team: UX, game engineer, game designer, project lead" style requests
- **`agnostic_preset_recommend` MCP tool** — given a description, returns the best preset + size + alternatives
- **`domain` + `size` params on `agnostic_run_crew`** — auto-selects preset (e.g. `domain="design", size="large"`)
- **Shared constants** — `agents/constants.py` now exports `DOMAINS`, `SIZES`, `DomainType`, `SizeType`, `make_agent_key()`
- **`TeamSpec.from_payload()`** classmethod for dict→TeamSpec conversion
- **`_crew_to_task_response()`** helper eliminates response wrapping duplication
- **40 new unit tests** — `test_crew_assembler.py` (26), `test_constants.py` (14). Total: 992 unit tests

### Changed

- **Domain rename** — `qa` → `quality` across all presets, registry, MCP tools, API endpoints, and A2A protocol
- **All task submission routes through crew builder** — `POST /api/v1/tasks`, `/tasks/security`, `/tasks/performance`, `/tasks/regression`, `/tasks/full`, all 4 legacy MCP tools (`agnostic_submit_task`, `agnostic_security_scan`, `agnostic_performance_test`, `agnostic_qa_orchestrate`), A2A `a2a:delegate`, and Chainlit chat — all now use `run_crew()`
- **`agnostic_list_presets`** — now returns agent details (key, name, role, focus) per preset; supports `size` filter
- **Convenience endpoints use targeted presets** — `/tasks/security` → `quality-security`, `/tasks/performance` → `quality-performance`, `/tasks/full` → `quality-large`
- **Preset loading consolidated** — `definitions.list_presets`, `factory.list_presets` read from `AgentRegistry` cache (no per-request file I/O)
- **Agent registry refactored** — loads from preset JSON files; `list_presets(domain, size)`, `list_domains()`, `get_preset_name(domain, size)`
- **A2A delegate** — supports `domain`+`size`, `preset`, `team`, `agent_definitions`; defaults to `quality-standard`

### Removed

- **Legacy QA pipeline** — `QAManagerAgent`, `OptimizedQAManager`, `_run_task_async()`, `_task_done_callback()`, legacy `submit_task()` Celery path
- **`config/team_config.json`** and **`config/team_config_loader.py`** — replaced by preset JSON files + `AgentRegistry`
- **`agents/manager/qa_manager_optimized.py`** — deleted entirely
- **`QAManagerAgent` class** — removed from `qa_manager.py` (tools `TestPlanDecompositionTool` and `FuzzyVerificationTool` retained)

---

## [2026.3.14]

### Added

- **General-purpose agent platform** — expanded from QA-only to support any domain. See ADR-029
- **`BaseAgent` class** (`agents/base.py`) — generic agent foundation with shared Redis/Celery/LLM/CrewAI init, task lifecycle, inter-crew delegation via `delegate_to()`
- **`AgentDefinition` schema** — runtime-loadable agent definitions from JSON, YAML, or API dicts
- **`AgentFactory`** (`agents/factory.py`) — create agents from files, dicts, presets, or definitions with caching
- **Tool registry** (`agents/tool_registry.py`) — global `@register_tool` decorator, name-based lookup, `load_tool_from_source()` for dynamic tool upload with sandboxed exec
- **Agent definition CRUD API** — POST/GET/PUT/DELETE `/api/v1/definitions/{key}` with admin auth, domain filtering, pagination
- **Preset management API** — GET/POST/DELETE `/api/v1/presets/{name}` with built-in preset protection
- **Crew builder API** — POST `/api/v1/crews` assembles and runs crews from presets, agent keys, or inline definitions; GET `/api/v1/crews/{id}` for status polling
- **Agent versioning** (`agents/versioning.py`) — save/list/get/rollback versions via API at `/api/v1/definitions/{key}/versions`
- **Agent packaging** (`agents/packaging.py`) — `.agpkg` ZIP bundles with manifest for export (POST `/api/v1/packages/export`) and import
- **Custom tool upload** — POST `/api/v1/tools/upload` with sandboxed compilation; GET `/api/v1/tools` lists all registered tools
- **MCP crew tools** — `agnostic_run_crew`, `agnostic_crew_status`, `agnostic_list_presets`, `agnostic_list_definitions`, `agnostic_create_agent`
- **A2A crew delegation** — `a2a:delegate` routes to crew builder; `a2a:create_agent` for dynamic agent creation
- **Dynamic A2A capabilities** — `/a2a/capabilities` returns loaded presets

### Changed

- **Branding** — "Agentic QA Team System" → "AAS — Agnostic Agent System". Container/artifact names remain `agnostic`
- **Database models** — added `domain` and `crew_preset` columns (no migration needed)
- **AGNOS registration** — merges static + dynamic preset agents
- **Dashboard timeline** — discovers dynamic agent prefixes via Redis SCAN
- **MCP server name** — `agnostic-qa` → `agnostic`

---

## [2026.3.12]

### Changed

- **API versioning** — all REST endpoints now under `/api/v1/` prefix (was `/api/`). Protocol-specific routes (RPC, A2A, MCP, Yeoman) unified under the same prefix — no more mixed `/api/` and `/api/v1/` paths
- **`response_model` coverage** — added Pydantic response models to all 57 API routes (was 36/57). Every JSON endpoint now has explicit schema for OpenAPI docs and response validation. Streaming/file endpoints excluded
- **`Depends()` session lifecycle** — database sessions in persistence and tenant routes now use FastAPI `Depends()` async generators (`_db_repo_dependency`, `_tenant_repo_dependency`) with guaranteed `session.close()` on exit. Legacy `get_db_repo()`/`get_tenant_repo()` retained for non-route callers
- **Async Redis in HistoryManager** — `webgui/history.py` migrated from sync `redis.Redis` to `redis.asyncio.Redis`, eliminating event-loop blocking in session history, search, and metrics queries

---

## [2026.3.11]

### Added

- **SSRF protection for agent tools** — `shared/ssrf.py` with `validate_url()` and `validate_hostname()` blocking private/internal networks; applied to `SecurityAssessmentTool` and `ComprehensiveSecurityAssessmentTool`
- **Webhook idempotency** — deterministic `event_id` via SHA-256 hash + dedup check in `_EventBuffer.push()` prevents duplicate webhook processing
- **Task status state machine** — forward-only `_VALID_TRANSITIONS` dict with atomic Redis WATCH/MULTI/EXEC optimistic locking (3 retries) for task status updates
- **A2A rate limiting** — `_check_a2a_rate_limit()` with configurable per-peer rate limit (`A2A_RATE_LIMIT` env var, default 60/min)
- **A2A audit logging** — `AuditAction.A2A_DELEGATE_RECEIVED`, `A2A_RESULT_RECEIVED`, `A2A_STATUS_QUERY`, `A2A_DELEGATE_SENT` enum members + audit_log calls in A2A endpoint
- **Session lifecycle audit actions** — `AuditAction.SESSION_CREATED`, `SESSION_COMPLETED`, `SESSION_FAILED`
- **A2A payload validation** — delegate messages now require a `description` field (returns 400 if missing)
- **Circuit breaker metrics** — `_on_llm_breaker_change()` callback exports state to Prometheus `CIRCUIT_BREAKER_STATE` gauge
- **Async Redis client** — `config.environment.Config.get_async_redis_client()` returning `redis.asyncio.Redis`; auth, alerts, dashboard, reports, and tasks modules migrated to async Redis
- **Bounded thread pool** — `ThreadPoolExecutor(max_workers=20)` as default event loop executor in `webgui/app.py`
- **Dashboard performance** — TTL caching (5s), `mget()` batch fetching, `asyncio.gather()` parallelism, dynamic `SCAN` count based on `dbsize()`
- **Database composite indexes** — `(created_at, status)` on TestSession/TestResult, `(session_id, status)` on TestResult
- **`PaginatedResponse` model** — shared Pydantic envelope for consistent pagination across list endpoints
- **`response_model` on endpoints** — OpenAPI schema validation on auth, dashboard, sessions, agents, reports, persistence, and tenants endpoints
- **JSON schema validation** — `isinstance(dict)` checks on all `json.loads()` results from Redis in integration and dashboard routes
- **Report download size limit** — 100 MB cap on report file downloads

### Fixed

- **Fire-and-forget task crash logging** — `add_done_callback` on all `asyncio.create_task()` calls across 6 agent modules
- **Bare exception anti-pattern** — replaced `except Exception: pass` with `logger.debug()` in agent modules
- **Timezone consistency** — `datetime.now(UTC)` across all agent and dashboard modules (was `datetime.now()`)

### Changed

- **Test count** — 810 unit tests passing (was 790), 0 failed, 2 skipped

---

## [2026.3.9]

### Added

- **Embedded Redis** — `redis-server` installed in production image, managed by supervisord. Skipped when `REDIS_URL` points to an external host
- **Embedded PostgreSQL 17** — auto-`initdb` on first run, skipped when `DATABASE_URL` points to an external host. `/data/postgres` persisted via Docker volume
- **Caddy TLS reverse proxy** — production-grade TLS termination. Two modes: provided certs (`TLS_CERT_PATH`/`TLS_KEY_PATH`) or auto-HTTPS via ACME (`TLS_DOMAIN`). HTTP→HTTPS redirect, HSTS, security headers. Skipped when `TLS_ENABLED!=true`
- **Supervisord process management** — `docker/supervisord.conf` manages Redis, PostgreSQL, Caddy, and Chainlit app with conditional autostart based on environment
- **`DATABASE_URL` env var support** — `get_database_url()` in `shared/database/models.py` now checks `DATABASE_URL` first before building from individual `POSTGRES_*` components
- **Certs volume mount** — `./certs:/app/certs:ro` in docker-compose, matching SecureYeoman's cert pattern

### Fixed

- **Auth `PermissionError` under supervisord** — `webgui/auth/__init__.py` now catches `PermissionError` when `appuser` cannot read `/root/.agnostic_dev_secret_key`; generates ephemeral key instead
- **Flaky `test_qa_analyst_tools.py`** — tests were patching `qa_analyst.redis.Redis` but the tool uses `config.get_redis_client()` (cached singleton). Fixed by patching `config.environment.config.get_redis_client`
- **Test warnings** — added `filterwarnings` to `pyproject.toml` to suppress third-party noise (crewai DeprecationWarning, aiohttp/asyncio ResourceWarning, importlib ImportWarning)

### Changed

- **`Dockerfile` rebuilt** — now installs `redis-server`, `postgresql-17`, `supervisor`, and `caddy`. Entrypoint changed from `CMD chainlit` to `ENTRYPOINT ["/app/docker/entrypoint.sh"]` (supervisord)
- **`docker-compose.yml` updated** — `DATABASE_ENABLED` defaults to `true`, added `agnostic_data` volume for persistence, added TLS env vars (`TLS_ENABLED`, `TLS_CERT_PATH`, `TLS_KEY_PATH`, `TLS_DOMAIN`), exposed ports 80/443
- **Test count** — 816 unit tests passing (was 725), 0 warnings (was 8)

### Dependency Updates

- **chromadb 1.1.1** — no longer blocked on Python 3.13; dropped pydantic v1 dependency, `requires-python: >=3.9` (no upper bound). Removed from Active Blockers in dependency-watch
- **Python 3.14 blocker** — sole remaining blocker is crewai 1.10.1 `requires-python: <3.14`

---

## [2026.3.8-1]

### Changed

- **AGNOS compose is now the primary `docker-compose.yml`** — renamed `docker-compose.agnos.yml` to `docker-compose.yml`; old standalone compose moved to `docker-compose.old-style.yml`
- **AGNOS deployment guide updated** — reflects profile-based structure (production: webgui only, `--profile dev` for infra, `--profile workers` for distributed agents)
- **README updated** — AGNOS listed as primary deployment option, standalone moved to secondary
- **Removed CLAUDE.md** — all content already covered by `docs/development/setup.md` and `README.md`

### Fixed

- **Health check treats unconfigured RabbitMQ as acceptable** — `not_configured` no longer triggers `degraded` status; RabbitMQ is optional (only needed with `--profile workers`)
- **Credential provisioning tests** — added `litellm` module stub for test venvs without litellm installed
- **Health check tests** — set `RABBITMQ_HOST` env var in tests that expect rabbitmq connectivity checks
- **Ruff formatting** — auto-formatted 13 files across agents/, config/, shared/, webgui/
- **CI workflow split** — replaced monolithic `ci-cd.yml` with separate `ci.yml` (test/lint/build) and `release.yml` (tag-triggered publish)
- **E2E test task submit endpoint** — fixed URL (`/api/v1/tasks/submit` → `/api/tasks`) and payload fields (`type`/`requirements` → `title`/`description`) in `test_agnos_gateway.py`
- **E2E teardown missing env var** — added `POSTGRES_PASSWORD` to CI teardown step; Docker Compose requires it even for `logs`/`down` commands
- **E2E smoke test fixes** — corrected assertions and endpoint paths in `test_smoke.py`
- **Helm chart fixes** — corrected label selectors, HPA/PDB apiVersions, network policy ports, ingress annotations, and container image references across templates and manifests
- **K8s manifest alignment** — updated kustomization overlays, webgui deployment probes, and agent resource definitions to match Helm chart changes

### Added

- **Same-day patch versioning** — version format now supports `YYYY.M.D-N` suffix for same-day patches (e.g. `2026.3.8-1`); `build-release.sh` handles patch suffix in artifact naming
- **AGNOS gateway E2E tests** — new `tests/e2e/test_agnos_gateway.py` covering hoosh/daimon health, LLM gateway round-trip, agent registration, and credential-free operation

---

## [2026.3.8]

### Fixed

- **GHCR push "installation not allowed to Create organization package"** — added `org.opencontainers.image.source` OCI labels to all Dockerfiles (`docker/Dockerfile.base`, `docker/Dockerfile.agent`, `webgui/Dockerfile`); GHCR requires this label to link packages to the repository so `GITHUB_TOKEN` can create them
- **CI workflow permissions** — added workflow-level `permissions: packages: write` to `ci-cd.yml` (matching agnosticos pattern); ensures all jobs inherit GHCR push capability
- **E2E API routes returning HTML** — API routes were only registered on the standalone FastAPI app, not on Chainlit's app; created `_configure_app()` helper in `webgui/app.py` that registers middleware + routes on both apps; `/health`, `/ws/realtime`, and all API routes now work under `chainlit run`

### Changed

- **OCI metadata on all container images** — `org.opencontainers.image.source`, `description`, and `licenses` labels added to base, agent, and webgui Dockerfiles for GHCR discoverability and repo linking

---

## [2026.3.7]

### Changed

- **Docker base image upgraded to Python 3.13** — `docker/Dockerfile.base` now uses `python:3.13-slim` (was `python:3.11-slim`), enabling crewai 1.10.1 and modern package versions
- **crewai upgraded to 1.10.1** — drops langchain dependency entirely; uses direct openai/litellm; resolves tiktoken version conflict; all 6 agents now start successfully
- **Separate Docker requirements file** — created `requirements-docker.txt` with runtime-only minimum version pins; eliminates dev tool conflicts (safety/typer, bandit, pytest pinning) that blocked the Docker build
- **GHCR container registry support** — CI workflow now logs in to `ghcr.io`, tags images as `ghcr.io/maccracken/agnostic-<service>`, and pushes on main/tag push; owner name forced lowercase via `tr` to prevent GHCR rejection
- **K8s manifests updated for GHCR** — all static manifests (`k8s/manifests/`) and Helm values (`k8s/helm/agentic-qa/values.yaml`) now reference `ghcr.io/maccracken/agnostic-*` images
- **Git remote and URLs normalized** — remote, README badge, and `pyproject.toml` URLs updated to `MacCracken/agnostic` (lowercase)
- **Docker postgres port remapped** — `docker-compose.yml` postgres host port changed from 5432 to 5433 to avoid conflict with local postgres
- **Unified `VERSION` file as single source of truth** — project version read from a single `VERSION` file; `pyproject.toml` uses `dynamic = ["version"]`; `shared/version.py` module provides `VERSION` constant for all Python code; `scripts/bump-version.sh` updates all static references in one command
- **Unified agent Docker image** — replaced 6 per-agent Dockerfiles with single `docker/Dockerfile.agent` + `docker/agent-entrypoint.sh`; `AGENT_ROLE` env var selects which agent module to run; reduces image count from 7 to 2 (agent + webgui)
- **Docker Compose lean defaults** — `docker compose up -d` now starts 3 containers (redis, postgres, webgui) with agents running in-process; 6 agent workers + rabbitmq available via `--profile workers`; YAML anchors (`x-worker-common`) eliminate config duplication
- **Docker Compose file consolidation** — rewrote `docker-compose.dev.yml`, `docker-compose.prod.yml`, `docker-compose.tls.yml` as thin overrides; deleted stale `agentic/docker-compose.prod.yml` duplicate; fixed YAML errors in prod and dev compose files
- **CI/CD shared composite action** — `.github/actions/setup-python-env/action.yml` extracts repeated Python setup (version read, Python install, pip extras) into reusable composite action; all CI jobs use it
- **CI Python version upgraded to 3.13** — composite action default changed from `3.11` to `3.13`
- **CI tag format support** — CI/CD pipeline now triggers on both `v*` and `YYYY.M.D` bare calver tags
- **CI GitHub Release job** — new `release` job creates GitHub Release with artifacts on tag push; generates release notes with GHCR pull commands
- **GHCR image reduction** — CI pushes 2 images (agent, webgui) instead of 7 separate per-agent images
- **Docker BuildKit compatibility** — `scripts/build-docker.sh` uses `--load` flag to ensure images are in local daemon store; CI uses `driver: docker` for BuildKit to avoid image store isolation issues
- **RabbitMQ credentials use safe defaults** — `docker-compose.yml` and `docker-compose.test.yml` use `${VAR:-default}` instead of `${VAR:?required}` for rabbitmq vars; prevents parse failure when workers profile is not active

### Fixed

- **Missing `shared/` module in Docker containers** — added `COPY shared/ ./shared/` to all 7 Dockerfiles (webgui + 6 agents); agents and webgui were crashing with `ModuleNotFoundError: No module named 'shared'`
- **Missing `llm_service` singleton** — added module-level `llm_service = LLMIntegrationService()` to `config/llm_integration.py`; 3 agents (manager, analyst, performance) were failing to import it
- **Pydantic v2 ClassVar annotations** — added `ClassVar` type annotations to un-annotated class attributes in BaseTool subclasses (`PLATFORM_CONFIGS`, `DEVICE_PROFILES`, `DESKTOP_PROFILES`, `EXPECTED_HEADERS`, `flaky_threshold`, `min_executions`, `quarantine_duration`); pydantic v2 (via crewai 1.10.1) rejects unannotated attributes
- **Pydantic v2 Faker instance attribute** — converted `SyntheticDataGeneratorTool.faker` from `__init__` instance attribute to lazy `ClassVar` + property to avoid pydantic's `__setattr__` validation
- **Chainlit `CHAINLIT_ROOT_PATH=/` crash** — changed to empty string; FastAPI rejects prefix ending with `/`
- **pytest missing in Docker runtime** — added `pytest` and `Faker` to `requirements-docker.txt`; junior QA agent uses pytest programmatically at runtime to execute tests
- **CI workflow Python version** — updated `PYTHON_VERSION` env var reference for consistency
- **Alert cooldown false suppression on fresh VMs** — `AlertManager._last_fired` default changed from `0.0` to `None`; `time.monotonic()` returns small values on freshly booted systems, causing `now - 0.0 < cooldown_seconds` to suppress every first alert (`shared/alerts.py`)
- **AlertManager enabled flag** — `enabled` parameter added to `AlertManager.__init__()` as instance attribute; `fire()` checks `self.enabled` instead of module-level `ALERTS_ENABLED` constant
- **Bandit B104/B108 false positives** — `nosec` comments on intentional `host="0.0.0.0"` and `/tmp` fallback (`webgui/app.py`, `webgui/auth/__init__.py`)
- **Ruff I001 import sort** — `shared.version` import moved to first-party block (`webgui/routes/dashboard.py`)
- **CI Trivy SARIF output** — corrected Trivy action parameters; upgraded CodeQL to v4 with `security-events: write` permission
- **CI Helm lint nil pointer** — added missing `metrics` section with defaults to `k8s/helm/agentic-qa/values.yaml`
- **CI unit test optional deps** — added `database` extra to CI install; `importorskip` for `sqlalchemy`, `faker`, `prometheus_client` in test files
- **CI test_crewai_compat.py** — fixed pydantic v2 field override annotations
- **CI pytest asyncio mode** — added `asyncio_mode = "auto"` to `pyproject.toml`
- **CI integration test env vars** — added correct ports and credentials for test compose (6380, 5673)
- **CI build-release BuildKit image isolation** — `driver: docker` + `--load` flag ensures base image visibility
- **CI `docker-compose` v1 → `docker compose` v2** — `run_tests.py` updated to use `docker compose` (plugin syntax); v1 standalone binary not available on CI runners
- **build-docker.sh version parsing** — reads from `VERSION` file instead of `pyproject.toml`

### Tests

- **725 unit tests passing** (7 skipped) + 24 E2E tests
- Tests skip gracefully when optional deps (faker, prometheus_client, sqlalchemy) not installed

---

## [2026.3.6]

### Security

- **Optional `/metrics` authentication** — `METRICS_AUTH_TOKEN` env var enables Bearer token auth on the Prometheus scrape endpoint; open by default for backward compatibility (`webgui/routes/dashboard.py`)
- **WebSocket message size validation** — `receive_json()` replaced with `receive_text()` + 64 KB size check before `json.loads()`; oversized messages are dropped with a warning (`webgui/realtime.py`)
- **SSRF DNS rebinding prevention** — `_validate_callback_url()` now resolves domain names via `socket.getaddrinfo()` and validates all resolved IPs against blocked networks, preventing DNS rebinding attacks that bypass hostname-based checks (`webgui/routes/dependencies.py`)
- **Timing-safe refresh token comparison** — replaced `!=` with `hmac.compare_digest()` in `TokenManager.refresh_tokens()` to prevent timing side-channel attacks (`webgui/auth/token_manager.py`)
- **Azure AD issuer verification** — replaced `verify_iss: False` with tenant-specific issuer URL and JWKS endpoint using `OAUTH2_AZURE_TENANT_ID`; prevents token forgery from other Azure tenants (`webgui/auth/oauth_provider.py`)
- **SHA-256 user ID generation** — replaced `hashlib.md5` with `hashlib.sha256` for OAuth user ID generation (`webgui/auth/oauth_provider.py`)
- **Dev JWT secret persistence** — auto-generated dev secret key now persisted to `~/.agnostic_dev_secret_key` (mode 0600) so tokens survive app restarts (`webgui/auth/__init__.py`)
- **Task ID input validation** — `GET /api/tasks/{task_id}` validates task_id against `^[a-zA-Z0-9\-]{1,100}$` regex; returns 400 on invalid format (`webgui/routes/tasks.py`)
- **Login rate limiting** — `POST /auth/login` rate-limited per email via Redis INCR with sliding window; configurable via `LOGIN_RATE_LIMIT_MAX` (default 10) and `LOGIN_RATE_LIMIT_WINDOW` (default 300s); returns 429 on excess; open-by-default if Redis unavailable (`webgui/routes/auth.py`)
- **Refresh token rotation** — used refresh tokens are deleted from Redis before issuing new ones, preventing replay of old refresh tokens (`webgui/auth/token_manager.py`)

### Fixed

- **Unbounded YEOMAN result cache** — `_results_cache` changed from plain dict to `OrderedDict` with LRU eviction (max 500 entries) (`shared/yeoman_a2a_client.py`)
- **Unbounded audit buffer** — `queue_event()` enforces 10K hard cap, dropping oldest events with warning log when exceeded (`shared/agnos_audit.py`)
- **Missing shutdown cleanup** — app lifespan now closes `agnos_dashboard_bridge`, `yeoman_a2a_client`, `agnos_audit_forwarder`, `alert_manager`, `model_manager`, and `agnos_token_budget` on shutdown (`webgui/app.py`)
- **Alert cooldown memory growth** — proactive eviction every 100 entries + hard cap enforcement in `AlertManager` (`shared/alerts.py`)
- **Stale WebSocket connections** — idle connection pruning via `time.monotonic()` tracking with configurable `_CONNECTION_IDLE_TIMEOUT` (default 5 min) (`webgui/realtime.py`)
- **Background task accumulation** — Redis listener `_redis_listener()` rewritten with internal retry loop instead of spawning new tasks on error (`webgui/realtime.py`)
- **Synchronous Redis blocking event loop** — `_run_task_async()` wraps sync Redis calls in `loop.run_in_executor()` (`webgui/routes/tasks.py`)
- **`redis.keys()` replaced with `scan_iter()`** — dashboard `get_sessions()` and `get_agents()` use non-blocking `scan_iter()` instead of `keys()` (`webgui/dashboard.py`)
- **Redundant double-fetch in dashboard** — `get_resource_metrics()` fetches sessions and agents once each instead of twice (`webgui/dashboard.py`)
- **Webhook client race condition** — `_get_webhook_client()` protected with `asyncio.Lock` to prevent duplicate client creation under concurrent requests (`webgui/routes/tasks.py`)
- **Webhook thundering herd** — retry backoff now includes jitter: `(2^attempt) * (0.8 + 0.4 * random())` (`webgui/routes/tasks.py`)
- **Per-call httpx client in token budget** — `AgnosTokenBudgetClient` now uses a shared `httpx.AsyncClient` with lazy init and `close()` method (`config/agnos_token_budget.py`)
- **Silent exception swallowing** — bare `except Exception: pass` blocks in dashboard alerts and A2A status_query replaced with `logger.warning()` calls (`webgui/routes/dashboard.py`, `webgui/routes/tasks.py`)
- **Per-request Redis client creation** — `Config.get_redis_client()` now returns a cached singleton instead of creating a new `Redis` instance and `ConnectionPool` on every call (`config/environment.py`)
- **Unbounded active_sessions** — `AgenticQAGUI.active_sessions` capped at 1000 entries with oldest-session eviction (`webgui/app.py`)
- **N+1 HTTP in AGNOS memory client** — added `retrieve_batch()` method with fallback to sequential retrieval; `get_patterns()` and `get_risk_models()` use batch retrieval (`shared/agnos_memory.py`)
- **Circuit breaker recovery notifications** — YEOMAN A2A and AGNOS dashboard bridge circuit breakers now log state transitions via `on_state_change` callbacks (`shared/yeoman_a2a_client.py`, `shared/agnos_dashboard_bridge.py`)

### Changed

- **POST endpoints return 201** — `POST /api/tasks`, `POST /api/test-sessions`, `POST /api/test-results`, `POST /api/auth/api-keys` now return HTTP 201 Created instead of 200 (`webgui/routes/tasks.py`, `webgui/routes/persistence.py`, `webgui/routes/auth.py`)
- **A2A endpoints gated by feature flag** — `POST /api/v1/a2a/receive` and `GET /api/v1/a2a/capabilities` return 503 when `YEOMAN_A2A_ENABLED=false` (default); prevents accidental exposure of A2A protocol (`webgui/routes/tasks.py`)
- **aiohttp connection pooling** — `BaseModelProvider._get_session()` now creates `TCPConnector(limit=20, limit_per_host=10, ttl_dns_cache=300)` instead of default unlimited connector (`config/model_manager.py`)
- **PostgreSQL in docker-compose** — added `postgres:16-alpine` service with health check, `postgres_data` volume, and `DATABASE_URL` env var wired to webgui service (`docker-compose.yml`)
- **Duplicate .env.example cleanup** — removed duplicate AGNOS LLM Gateway block (lines 200–207); added `OAUTH2_AZURE_TENANT_ID`, `LOGIN_RATE_LIMIT_MAX`, `LOGIN_RATE_LIMIT_WINDOW` (`.env.example`)
- **Auth route cleanup** — removed inline `from fastapi import HTTPException` in favour of top-level import (`webgui/routes/auth.py`)
- **Consistent API response wrappers** — list endpoints in sessions, dashboard, and persistence routes now return `{items, total, limit, offset}` instead of raw lists (`webgui/routes/sessions.py`, `webgui/routes/dashboard.py`, `webgui/routes/persistence.py`)
- **YEOMAN/AGNOS health in `/health`** — health endpoint now reports YEOMAN A2A and AGNOS dashboard bridge circuit breaker state (`webgui/app.py`)
- **A2A protocol documentation** — full reference for all 5 message types, envelope format, capabilities, configuration, and client usage (`docs/api/a2a-protocol.md`)
- **aiohttp TCPConnector pool config** — `enable_cleanup_closed` removed (deprecated in Python 3.14); kept `limit`, `limit_per_host`, `ttl_dns_cache` (`config/model_manager.py`)
- **Dashboard `response_model` declarations** — added `ItemListResponse` and `AlertListResponse` Pydantic models to `/dashboard/sessions`, `/dashboard/agents`, and `/alerts` endpoints (`webgui/routes/dashboard.py`)
- **Consistent pagination in persistence routes** — `GET /test-sessions` and `GET /test-results` now use `Query(50, ge=1, le=200)` for limit validation, matching other routes (`webgui/routes/persistence.py`)
- **Batch A2A operations** — added `delegate_batch()` and `query_batch_status()` to `YeomanA2AClient` for single-round-trip multi-task delegation and status queries (`shared/yeoman_a2a_client.py`)
- **Bidirectional dashboard bridge** — added `pull_fleet_status()` and `pull_peer_metrics()` pull methods to `AgnosDashboardBridge`, enabling bidirectional data flow with AGNOS dashboard (`shared/agnos_dashboard_bridge.py`)
- **`a2a:status_query` response schema** — added `A2AStatusResponse` Pydantic model formalizing the response shape for status query messages (`webgui/routes/tasks.py`)

### Tests

- 2 new SSRF tests: `test_blocks_dns_rebinding_to_private`, `test_blocks_unresolvable_hostname` (`tests/unit/test_webgui_api.py`)
- A2A tests patched with `@patch("webgui.routes.tasks.YEOMAN_A2A_ENABLED", True)` for feature gate compatibility (`tests/unit/test_webgui_tasks.py`)
- Task submission tests updated for 201 status codes (`tests/unit/test_webgui_tasks.py`, `tests/unit/test_tenant_isolation.py`)
- Dashboard tests updated for `scan_iter()` mocking (`tests/unit/test_dashboard.py`)
- **674 unit tests passing** (7 skipped) + 19 E2E tests

---

## [2026.3.5]

### Added

- **Route module decomposition** — `webgui/api.py` split from 1868-line monolith into 10 focused route modules under `webgui/routes/` (auth, tasks, reports, tenants, agents, dashboard, sessions, persistence, integration, dependencies); backward-compatible re-exports preserve all existing test patch targets
- **Auth package decomposition** — `AuthManager` split into composed sub-managers: `TokenManager` (JWT create/verify/refresh/logout), `OAuthProviderFactory` (local/Google/GitHub/Azure AD), `PermissionValidator` (RBAC + resource access), `api_keys` module, `models` module; `webgui/auth/` package with `__init__.py` re-exporting identical public API
- **YEOMAN MCP tools (6 new)** — `agnostic_session_diff`, `agnostic_structured_results`, `agnostic_quality_trends`, `agnostic_security_findings`, `agnostic_qa_orchestrate`, `agnostic_quality_dashboard` registered in `agnostic-tools.ts` + `manifest.ts` (16 total)
- **LLM Gateway consolidation** — `ModelManager.load_config()` auto-enables `agnos_gateway` provider when `AGNOS_LLM_GATEWAY_ENABLED=true`; `OpenAIProvider` propagates `x-agent-id` header for per-agent token accounting via AGNOS gateway; `ModelManager.gateway_health()` checks gateway `/health` endpoint; `GET /api/dashboard/llm-gateway` endpoint exposes gateway status (`config/model_manager.py`, `webgui/routes/dashboard.py`)
- **REST API Proxy tools (9 new)** — `AgnosticApiClient` adapter implements `CoreApiClient` interface wrapping `agnosticGet`/`agnosticPost`; 9 high-value endpoints registered via `registerApiProxyTool()` factory: `agnostic_proxy_sessions`, `agnostic_proxy_session_search`, `agnostic_proxy_task_list`, `agnostic_proxy_agent_detail`, `agnostic_proxy_agent_registration`, `agnostic_proxy_dashboard_overview`, `agnostic_proxy_llm_gateway`, `agnostic_proxy_reports`, `agnostic_proxy_alerts` (`agnostic-tools.ts`, `manifest.ts`; 25 total agnostic tools)

- **WebSocket Real-Time Dashboard** — `/ws/realtime` endpoint fully wired in `webgui/app.py`; initializes Redis pub/sub on startup, subscribes to agent task channels (`manager:tasks`, `senior:tasks`, etc.) for real-time task progress; dashboard.js auto-subscribes to active sessions on connect (`webgui/realtime.py`, `webgui/static/js/dashboard.js`)
- **Prometheus ServiceMonitor** — `ServiceMonitor` and `PodMonitor` CRDs for Prometheus scraping of `/api/metrics` endpoint; configurable via `metrics.enabled` in Helm values (`k8s/helm/agentic-qa/templates/service-monitor.yaml`)
- **Scheduled Report Generation** — APScheduler integration for automated daily/weekly reports; `POST /api/reports/scheduled`, `GET /api/reports/scheduled`, `DELETE /api/reports/scheduled/{job_id}` endpoints; configurable via `SCHEDULED_REPORTS_ENABLED`, `SCHEDULED_REPORT_DAILY_TIME`, `SCHEDULED_REPORT_WEEKLY_DAY`, `SCHEDULED_REPORT_WEEKLY_TIME` env vars (`webgui/scheduled_reports.py`, `webgui/api.py`, `pyproject.toml`)
- **GitOps/ArgoCD Integration** — ArgoCD `ApplicationSet` for multi-environment promotion; External Secrets Operator for Vault-backed secret rotation; Kustomize overlays for dev/staging/prod (`k8s/argocd/applicationset.yaml`, `k8s/argocd/external-secrets.yaml`, `k8s/overlays/`)
- **Test Result Persistence (PostgreSQL)** — SQLAlchemy async models for test sessions, results, metrics, and reports; REST endpoints for CRUD operations; quality trends API; configurable via `DATABASE_ENABLED`, `POSTGRES_*` env vars (`shared/database/models.py`, `shared/database/repository.py`, `webgui/api.py`, `pyproject.toml`)
- **Multi-Tenant WebGUI** — Tenant models (`Tenant`, `TenantUser`, `TenantAPIKey`) with `TenantRepository` for database CRUD; admin endpoints for tenant provisioning (create, update, soft-delete, user management); tenant-scoped Redis keyspaces; configurable via `MULTI_TENANT_ENABLED` env var (`shared/database/tenants.py`, `shared/database/tenant_repository.py`, `webgui/api.py`)
- **AGNOS OS Phase 2 - Agent HUD Registration** — AgentRegistryClient for registering Agnostic QA agents with agnosticos Agent HUD; registration on startup, deregistration on shutdown; REST endpoints for status and manual registration; configurable via `AGNOS_AGENT_REGISTRATION_ENABLED`, `AGNOS_AGENT_REGISTRY_URL` env vars (`config/agnos_agent_registration.py`, `webgui/api.py`, `docs/adr/022-agnosticos-agent-hud.md`)
- **YEOMAN MCP Bridge WebSocket Support** — WebSocket task subscription via `subscribe_task` message; task status updates published to Redis `task:{id}` channel on status changes; enables MCP bridge to receive push notifications instead of polling (`webgui/realtime.py`, `webgui/api.py`)
- **Structured Result Schemas for YEOMAN** — Typed dataclasses for security, performance, and test execution results with `to_yeoman_action()` method for programmatic actions (auto-create issues, block PRs); `GET /results/structured/{session_id}` endpoint (`shared/yeoman_schemas.py`, `webgui/api.py`)
- **Alembic database migrations** — async PostgreSQL migration support; initial migration covering all 7 tables (test_sessions, test_results, test_metrics, test_reports, tenants, tenant_users, tenant_api_keys); `alembic/env.py` configured for `asyncpg` (`alembic/`)
- **Scheduled reports unit tests** (`tests/unit/test_scheduled_reports.py`) — 27 tests covering init, enabled/disabled behavior, job scheduling, triggers, day mapping, error handling
- **Multi-tenant unit tests** (`tests/unit/test_tenant.py`) — 39 tests covering TenantManager, TenantRepository CRUD, endpoint guards, auth, 404 handling
- **Unit tests for WebSocket realtime** (`tests/unit/test_webgui_realtime.py`) — 15 tests covering EventType, WebSocketMessage, RealtimeManager, WebSocketHandler, and channel configuration
- **Webhook callback retry with exponential backoff** — `_fire_webhook` retries up to 3 times with 1s/2s/4s delays on failure; configurable via `WEBHOOK_MAX_RETRIES` env var; failed deliveries logged with attempt count (`webgui/api.py`)
- **Configurable YEOMAN action thresholds** — coverage, error rate, and performance degradation thresholds extracted from hardcoded values to env vars: `YEOMAN_COVERAGE_THRESHOLD`, `YEOMAN_ERROR_RATE_THRESHOLD`, `YEOMAN_PERF_DEGRADATION_FACTOR` (`shared/yeoman_schemas.py`)
- **Tenant-scoped Redis key isolation** — `submit_task`, `get_task`, and `_run_task_async` use `tenant_manager.task_key()` for tenant-prefixed Redis keys when `MULTI_TENANT_ENABLED=true`; backward-compatible (plain keys when disabled) (`webgui/api.py`, `shared/database/tenants.py`)
- **Tenant-scoped API key validation** — `get_current_user` checks tenant API keys via `tenant_manager.validate_tenant_api_key()` with SHA-256 hash lookup and last-used tracking (`webgui/api.py`)
- **Per-tenant rate limiting** — sliding-window rate limiter in `submit_task` returns HTTP 429 when tenant exceeds `TENANT_DEFAULT_RATE_LIMIT` per minute; uses Redis INCR with 60s TTL (`webgui/api.py`, `shared/database/tenants.py`)
- **Tenant manager unit tests** — 13 new tests for `task_key`, `session_key`, `check_rate_limit`, and `validate_tenant_api_key` (52 total tenant tests) (`tests/unit/test_tenant.py`)
- **Tenant data isolation tests** — 12 tests verifying cross-tenant leakage prevention: key isolation, endpoint-level task visibility, rate limit independence, API key scoping, quota boundaries (`tests/unit/test_tenant_isolation.py`)
- **Tenant provisioning documentation** — provisioning workflow, API key issuance, isolation model, rate limiting, lifecycle states, backward compatibility (`docs/api/tenant-provisioning.md`)
- **Scheduled report delivery channels** — `ReportDeliveryService` with webhook (HMAC-SHA256 signed POST, exponential backoff retry) and Slack (incoming webhook with status emoji) delivery; configurable via `REPORT_WEBHOOK_URL`, `REPORT_WEBHOOK_SECRET`, `REPORT_SLACK_WEBHOOK_URL`, `REPORT_DELIVERY_MAX_RETRIES`; integrated into `_generate_and_deliver()` for both built-in and custom reports; failure notifications also delivered (`webgui/scheduled_reports.py`)
- **Tenant-scoped scheduled reports** — `schedule_custom_report()` accepts optional `tenant_id`; job IDs include tenant prefix for namespace isolation (`webgui/scheduled_reports.py`, `webgui/api.py`)
- **WebSocket missed-message recovery** — `MessageBuffer` class buffers all pub/sub messages to Redis Streams (`XADD` with configurable `REALTIME_STREAM_MAX_LEN`); `replay_missed_messages()` replays buffered messages via `XRANGE` on reconnection; live messages include `stream_id` for position tracking; replayed messages tagged with `"replayed": true` (`webgui/realtime.py`)
- **Client reconnection with last_message_id** — `subscribe_session` and `subscribe_task` messages accept optional `last_message_id` field; server replays missed messages (up to `REALTIME_STREAM_REPLAY_LIMIT`) before resuming live updates; backward-compatible with clients that don't send it (`webgui/realtime.py`)
- **Report delivery unit tests** — 13 tests covering webhook delivery, HMAC signatures, retry logic, Slack formatting, multi-channel dispatch, tenant-scoped job IDs (`tests/unit/test_report_delivery.py`)
- **Message buffer unit tests** — 15 tests covering Redis Streams XADD/XRANGE, replay mechanics, reconnection protocol, publish buffering (`tests/unit/test_message_buffer.py`)
- **Email delivery channel for scheduled reports** — `ReportDeliveryService._deliver_email()` sends HTML reports via SMTP using `aiosmtplib`; supports TLS/STARTTLS, authentication, multiple recipients; exponential backoff retry matching webhook/Slack pattern; configurable via `REPORT_EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `SMTP_FROM`, `REPORT_EMAIL_RECIPIENTS` env vars (`webgui/scheduled_reports.py`)
- **Persistent database job store for APScheduler** — `ScheduledReportManager._create_jobstore()` selects between Redis (default) and SQLAlchemy job store; database store uses APScheduler's built-in `SQLAlchemyJobStore` with sync `psycopg2` driver; selected via `SCHEDULER_JOBSTORE=database` when `DATABASE_ENABLED=true`; falls back to Redis when database unavailable (`webgui/scheduled_reports.py`)
- **Alembic migration for APScheduler jobs table** — `apscheduler_jobs` table (id, next_run_time, job_state) matching APScheduler's expected schema (`alembic/versions/a1b2c3d4e5f6_apscheduler_jobs_table.py`)
- **Email delivery unit tests** — 7 tests covering enable/disable, SMTP send, retry logic, HTML body content, multi-channel dispatch (`tests/unit/test_report_delivery.py`)
- **Job store selection unit tests** — 5 tests covering Redis default, explicit Redis, database fallback when DB disabled, SQLAlchemy selection, sync URL conversion (`tests/unit/test_scheduled_reports.py`)
- **ADR-026** — Scheduled report enhancements: email delivery and persistent job store (`docs/adr/026-scheduled-report-enhancements.md`)
- **Structured audit logging** — `shared/audit.py` with `AuditAction` enum (22 actions covering auth, task, report, tenant, system events) and `audit_log()` function; emits JSON to dedicated `audit` logger; wired into `webgui/api.py` (task submit, rate limit, report generate/download/schedule) and `webgui/auth.py` (login success/failure); configurable via `AUDIT_LOG_ENABLED`, `AUDIT_LOG_LEVEL` env vars (`shared/audit.py`, `webgui/api.py`, `webgui/auth.py`)
- **Agent metrics dashboard** — `shared/agent_metrics.py` with `get_agent_metrics()` (per-agent task counts, success rates, LLM token usage) and `get_llm_metrics()` (call counts, error rates, by-method breakdown); reads in-process Prometheus metrics; `GET /api/dashboard/agent-metrics` and `GET /api/dashboard/llm` endpoints (`shared/agent_metrics.py`, `webgui/api.py`)
- **LLM token usage metrics** — `LLM_TOKENS_PROMPT` and `LLM_TOKENS_COMPLETION` Prometheus counters with `(agent, method)` labels; instrumented in all 6 `LLMIntegrationService` methods via `response.usage`; `agent_name` parameter added to constructor (`shared/metrics.py`, `config/llm_integration.py`)
- **E2E test suite** — `tests/e2e/test_smoke.py` (14 tests: health, A2A, Prometheus, auth, task submit/poll, sessions, reports, agents, security headers, path traversal) and `tests/e2e/test_task_lifecycle.py` (5 tests: full lifecycle, 404, validation, A2A delegate); `scripts/run-e2e.sh` harness with auto-start; `pytest.mark.e2e` marker registered (`tests/e2e/`, `scripts/run-e2e.sh`, `pyproject.toml`)
- **E2E CI job** — `e2e-tests` job in GitHub Actions; builds full Docker stack, waits for health, runs `pytest tests/e2e/ -v -m e2e` (`.github/workflows/ci.yml`)
- **Audit logging unit tests** — 10 tests covering JSON emission, enable/disable, field completeness, failure outcomes, enum validation, handler setup idempotency (`tests/unit/test_audit.py`)
- **Agent metrics unit tests** — 10 tests covering agent list, structure, success rate calculation, zero defaults, LLM metrics structure, Prometheus fallback (`tests/unit/test_agent_metrics.py`)
- **ADR-027** — Audit logging and agent metrics dashboard (`docs/adr/027-audit-logging-agent-metrics.md`)
- **Rate limiting middleware** — `RateLimitMiddleware` on all `/api/*` paths with per-IP sliding window; configurable via `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`; returns 429 with `Retry-After` and `X-RateLimit-*` headers (`webgui/app.py`, `shared/rate_limit.py`)
- **Correlation ID request tracing** — `CorrelationIdMiddleware` generates/propagates `X-Correlation-ID` on every request; bound to structlog contextvars and audit log events (`webgui/app.py`, `shared/audit.py`)
- **Database connection pooling tuning** — `DB_POOL_TIMEOUT` env var; pool config logging on startup; `close_db()` in shutdown handler to prevent connection leaks (`shared/database/models.py`, `webgui/app.py`, `.env.example`)
- **Alert & notification system** — `AlertManager` with webhook/Slack/email delivery, cooldown throttling; `HealthMonitor` background task polls health state and fires alerts on transitions (degraded, unhealthy, agent offline/stale); circuit breaker `on_state_change` callback; configurable via `ALERTS_ENABLED`, `ALERT_POLL_INTERVAL_SECONDS`, `ALERT_COOLDOWN_SECONDS` (`shared/alerts.py`, `shared/resilience.py`, `webgui/app.py`)
- **API pagination** — all list endpoints return `{items, total, limit, offset}` with `limit`/`offset` query params; paginated: reports, scheduled reports, agents, tenants, tenant users, API keys (`webgui/api.py`)
- **OpenAPI client SDK generation** — `scripts/generate-sdk.sh` fetches OpenAPI schema (live or offline) and generates Python (`openapi-python-client`) and TypeScript (`openapi-generator-cli`) client SDKs (`scripts/generate-sdk.sh`)
- **Test result diffing** — `TestResultRepository.diff_sessions()` compares two sessions by `test_id`; categorises regressions, fixes, new tests, removed tests; computes pass rate delta and average execution time; `GET /test-sessions/diff?base=&compare=` endpoint (`shared/database/repository.py`, `webgui/api.py`)
- **Middleware unit tests** — 12 tests covering CorrelationIdMiddleware, RateLimitMiddleware, correlation ID in audit log, DB pool config (`tests/unit/test_middleware.py`)
- **Alert system unit tests** — 14 tests covering AlertManager, HealthMonitor, circuit breaker callback (`tests/unit/test_alerts.py`)
- **Session diff unit tests** — 9 tests covering identical sessions, regressions, fixes, new/removed tests, pass rate delta, avg time (`tests/unit/test_session_diff.py`)

### Security

- **SSRF protection for webhooks** — `_validate_callback_url()` blocks callbacks to private networks (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, IPv6 link-local/ULA); validates URL scheme (http/https only) (`webgui/api.py`)
- **CORS hardened** — restricted `allow_methods` from `["*"]` to `["GET", "POST", "PUT", "DELETE", "OPTIONS"]`; restricted `allow_headers` to `["Content-Type", "Authorization", "X-API-Key", "X-Correlation-ID"]` (`webgui/app.py`)
- **Static API key permissions restricted** — static `AGNOSTIC_API_KEY` no longer grants `SYSTEM_CONFIGURE` permission; operational permissions only (`webgui/api.py`)
- **Tenant isolation enforcement** — `_check_tenant_access()` guard added to `GET /tenants/{id}`, `PUT /tenants/{id}`, `DELETE /tenants/{id}`, `GET /tenants/{id}/users`; users can only access their own tenant; super_admin bypasses (`webgui/api.py`)
- **Agent name normalization** — `_normalize_agent_name()` converts underscores to hyphens, fixing YEOMAN snake_case→kebab-case mismatch that caused silent agent filtering failures (`webgui/api.py`)

- **Unit tests for 7 previously untested modules** — 136 new tests: `shared/rate_limit.py` (18 tests), `shared/crewai_compat.py` (4 tests), `shared/data_generation_service.py` (30 tests), `webgui/app.py` (12 tests), `webgui/agent_monitor.py` (15 tests), `webgui/dashboard.py` (15 tests), `webgui/history.py` (20 tests) (`tests/unit/test_rate_limit.py`, `tests/unit/test_crewai_compat.py`, `tests/unit/test_data_generation.py`, `tests/unit/test_webgui_app.py`, `tests/unit/test_agent_monitor.py`, `tests/unit/test_dashboard.py`, `tests/unit/test_history.py`)
- **Auth token manager unit tests** — 21 tests covering JWT creation/verification/refresh, token blacklisting, logout, bcrypt password hashing (`tests/unit/test_token_manager.py`)
- **Permission validator unit tests** — 16 tests covering RBAC role permissions, resource access (session owner/team/org/super admin), user management access (`tests/unit/test_permission_validator.py`)
- **Team config loader unit tests** — 22 tests covering config loading (valid/invalid/missing JSON), team presets, agent routing, workflow config, dynamic scaling (`tests/unit/test_team_config.py`)
- **Agent metrics helper tests** — 8 new tests covering `_get_counter_value`, `_get_gauge_value`, `_iter_samples`, LLM metrics with data (`tests/unit/test_agent_metrics.py`)
- **Report exports unit tests** — 16 tests covering enums, dataclasses, `_collect_session_data` (info/plan/verification/agents/timeline), `_calculate_session_metrics` (scores/duration/agents) (`tests/unit/test_exports.py`); total unit tests: 672

### Fixed

- **`UnifiedDataGenerator._generate_data_item()` crash on non-dict preset keys** — `_generate_data_item()` and `_get_data_schema()` now skip `_`-prefixed and non-dict entries in preset dicts, fixing `AttributeError: 'str' object has no attribute 'get'` when presets contain metadata keys like `_name` or scalar overrides from `optimize_for_agent()` (`shared/data_generation_service.py`)
- **`test_redis_url_format` / `test_rabbitmq_url_format` failures** — tests now clear `REDIS_URL`/`RABBITMQ_URL` env vars before asserting component-based URL construction, fixing the `os.getenv("REDIS_URL")` precedence issue (`tests/unit/test_config_environment.py`)
- **WebSocket realtime test hang** — `test_handle_websocket_accepts_connection` blocked forever due to missing `receive_json` side_effect; handler's `while True` receive loop now properly terminated in test
- **pytest collection warnings** — `TestStatus` and `TestExecutionResult` in `shared/yeoman_schemas.py` suppressed via `__test__ = False`
- **SQLAlchemy reserved name conflict** — `TestResult.metadata` renamed to `extra_metadata` with explicit column name `"metadata"` to avoid collision with SQLAlchemy's `Base.metadata`
- **Rate limiter memory leak** — added `_last_seen` tracking and TTL-based eviction (1 hour) to prevent unbounded growth of per-IP entries (`shared/rate_limit.py`)
- **Alert cooldown memory leak** — added `_evict_stale_cooldowns()` with 2-hour TTL to prevent `_last_fired` dict from growing unbounded (`shared/alerts.py`)
- **Redis pub/sub blocking event loop** — replaced synchronous `get_message(timeout=1.0)` with `run_in_executor()` to avoid blocking the async event loop for up to 1 second (`webgui/realtime.py`)
- **Redis `KEYS` command replaced with `SCAN`** — report listing endpoint now uses non-blocking `SCAN` + `MGET` instead of `KEYS` + individual `GET` calls (`webgui/api.py`)
- **httpx client reuse** — `AlertManager` and webhook delivery now use shared `httpx.AsyncClient` singletons instead of creating new clients per request (`shared/alerts.py`, `webgui/api.py`)
- **LLM integration deduplicated** — extracted `_llm_call()` common wrapper replacing 6 identical 70-line methods with circuit breaker, metrics, and fallback logic (`config/llm_integration.py`)
- **Alert query endpoint** — `GET /api/alerts?limit=&severity=` reads from Redis stream for recent alert history; alerts persisted via `XADD` with 1000-entry cap (`webgui/api.py`, `shared/alerts.py`)
- **SSRF protection unit tests** — 9 tests covering private IP blocking, public URL allowance, scheme validation (`tests/unit/test_webgui_api.py`)
- **Agent name normalization tests** — 4 tests covering snake_case/kebab-case conversion (`tests/unit/test_webgui_api.py`)
- **Static API key permission test** — verifies SYSTEM_CONFIGURE excluded from static key (`tests/unit/test_webgui_api.py`)

### Changed

- **TODO.md consolidated** — deleted `TODO.md` (was a redirect); all tracking moved to `docs/development/roadmap.md`; references in `README.md` and `docs/README.md` updated

---

## [2026.2.28]

### Security

- **Path traversal prevention** — `GET /reports/{id}/download` resolves `file_path` with `Path.resolve()` and asserts `is_relative_to(_REPORTS_DIR)` before serving; paths outside `/app/reports` return HTTP 403 (`webgui/api.py`)
- **Session ID sanitization** — session IDs stripped of non-alphanumeric characters via `re.sub` before use in generated filenames, preventing directory traversal in report generation (`webgui/exports.py`)
- **Constant-time API key comparison** — static `AGNOSTIC_API_KEY` comparison changed from `==` to `hmac.compare_digest()` to prevent timing side-channel attacks (`webgui/api.py`)
- **Required RabbitMQ credentials** — `guest:guest` fallback removed; `RABBITMQ_USER` and `RABBITMQ_PASSWORD` must be explicitly set; Docker Compose uses `:?` syntax to fail clearly if unset (`docker-compose.yml`, `.env.example`)
- **Security headers middleware** — `SecurityHeadersMiddleware` sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: strict-origin-when-cross-origin` on every response (`webgui/app.py`)
- **Input validation hardening** — `TaskSubmitRequest` enforces `min_length`/`max_length` on all text fields (title: 200, description: 5000, goals/constraints: 500) and `Literal["critical","high","medium","low"]` for priority; invalid values return HTTP 422 (`webgui/api.py`)

### Added

- **Manual testing guide** (`docs/development/manual-testing.md`) — ~45 test steps covering smoke, integration, and E2E sweeps with exact `curl` commands, expected outputs, and pass/fail criteria; includes YEOMAN MCP bridge verification
- **AGNOS OS integration** ([ADR-021](../adr/021-agnosticos-integration.md)) — route LLM calls through the AGNOS OS LLM Gateway (port 8088, OpenAI-compatible); config-only change, no agent code modified
  - `config/models.json`: new `agnos_gateway` provider entry (disabled by default)
  - `.env.example`: `AGNOS_LLM_GATEWAY_ENABLED`, `AGNOS_LLM_GATEWAY_URL`, `AGNOS_LLM_GATEWAY_API_KEY`, `AGNOS_LLM_GATEWAY_MODEL`
  - `docs/adr/021-agnosticos-integration.md`, `docs/deployment/agnosticos.md`
  - `tests/unit/test_model_manager.py`: 41 unit tests covering provider schema, gateway routing, env-var guards
- **Kubernetes production readiness** ([ADR-020](../adr/020-kubernetes-production-readiness.md)) — full production controls for manifests and Helm chart
  - `HorizontalPodAutoscalers` (`autoscaling/v2`) for all 6 agents + WebGUI; CPU/memory-based, 300 s scale-down stabilisation
  - `PodDisruptionBudgets` (`policy/v1`, `minAvailable: 1`) for all 7 deployments
  - `NetworkPolicies` — least-privilege ingress/egress; agents may reach public internet (LLM APIs) but not private CIDRs
  - `ResourceQuota` — namespace cap (32 CPU, 64 Gi RAM, 20 pods/services/secrets/ConfigMaps, 10 PVCs)
  - Helm templates: `hpa.yaml`, `pdb.yaml`, `resource-quota.yaml`; `values-dev.yaml` and `values-prod.yaml`
  - K8s YAML validation test suite (`tests/k8s/`)
- **A2A Protocol integration** ([ADR-019](../adr/019-a2a-protocol.md)) — Agnostic as a first-class peer in YEOMAN's agent delegation tree
  - `POST /api/v1/a2a/receive` — handles `a2a:delegate` (routes to task submission), `a2a:heartbeat`, unknown types (forward-compatible)
  - `GET /api/v1/a2a/capabilities` — advertises QA, security-audit, and performance-test capabilities (unauthenticated)
  - 8 unit tests covering delegate, heartbeat, unknown type, auth enforcement, validation
- **REST task submission + API key auth** ([ADR-017](../adr/017-rest-task-submission-api-keys.md))
  - `POST /api/tasks`, `GET /api/tasks/{id}` — fire-and-forget with Redis-backed status polling; 24 h TTL; `pending → running → completed | failed`
  - `POST /api/tasks/security`, `/performance`, `/regression`, `/full` — convenience endpoints for agent-specific runs
  - `X-API-Key` header auth — dual mode: static `AGNOSTIC_API_KEY` env var + Redis-backed per-client keys (sha256-hashed, never stored raw)
  - `POST/GET /api/auth/api-keys`, `DELETE /api/auth/api-keys/{key_id}` — key management endpoints
- **Webhook callbacks + CORS** ([ADR-018](../adr/018-webhook-callbacks-cors.md))
  - Optional `callback_url` + `callback_secret` on task submission; HMAC-SHA256 `X-Signature` header on callback POST
  - `CORSMiddleware` with `CORS_ALLOWED_ORIGINS` env var; defaults allow YEOMAN dashboard ports
- **Observability stack** ([ADR-015](../adr/015-observability-stack.md))
  - `shared/metrics.py` — Prometheus counters, histograms, gauges with no-op fallback; `get_metrics_text()`
  - `shared/logging_config.py` — structured JSON logging via structlog or stdlib text fallback
  - `GET /api/metrics` — Prometheus scrape endpoint (unauthenticated)
  - LLM call instrumentation (counter + histogram on all 6 `LLMIntegrationService` methods)
- **Agent communication hardening** ([ADR-016](../adr/016-communication-hardening.md))
  - `shared/resilience.py` — `CircuitBreaker` (CLOSED/OPEN/HALF_OPEN), `retry_async` decorator with exponential backoff, `GracefulShutdown` async context manager
  - Celery reliability: `task_acks_late`, `task_reject_on_worker_lost`, retry config
  - `GracefulShutdown` wired into all 6 agent `main()` functions
- **Plugin architecture** ([ADR-013](../adr/013-plugin-architecture.md)) — config-driven `AgentRegistry` + `AgentDefinition` in `config/agent_registry.py`; replaces hardcoded if/elif routing; new agents require 5 steps instead of 7 with no code changes to manager or WebGUI
- **WebGUI REST API** ([ADR-014](../adr/014-webgui-rest-api.md)) — 18+ FastAPI endpoints (dashboard, sessions, reports, agents, auth) with JWT authentication; OpenAPI schema at `/docs`
- **Enhanced health endpoint** — `GET /health` returns `healthy | degraded | unhealthy` with per-component detail (Redis ping, RabbitMQ TCP connect, per-agent heartbeat freshness); configurable via `AGENT_STALE_THRESHOLD_SECONDS`
- **Dependency Watch** (`docs/development/dependency-watch.md`) — tracks upstream blockers (chromadb/Python 3.14, chainlit FastAPI conflict) with exact error context, fix conditions, and monitoring links

### Changed

- **crewAI 1.x migration — LangChain removed** — all application code now targets `crewai>=1.0.0,<2.0.0` with litellm for LLM routing
  - `pyproject.toml`: `crewai>=1.0.0,<2.0.0`; removed `langchain`, `langchain-openai`, `langchain-community`; `numpy <2.0` cap lifted; `requires-python` narrowed to `>=3.11,<3.14`
  - `config/llm_integration.py`: `ChatOpenAI` + LangChain schema messages replaced with `litellm.acompletion()`
  - `config/universal_llm_adapter.py`: rewritten — `langchain.llms.base.LLM` subclass replaced with `crewai.LLM` factory (`create_llm()` / `get_crewai_llm()`)
  - All 6 agent files: `from langchain_openai import ChatOpenAI` → `from crewai import LLM`; `ChatOpenAI(...)` → `LLM(...)`
  - `agents/performance/qa_performance.py`: `from langchain.tools import BaseTool` → `from shared.crewai_compat import BaseTool`
  - Python 3.14 still blocked by chromadb — see `docs/development/dependency-watch.md`; production Docker (Python 3.11) unaffected
- **OAuth2 JWT signature verification** — replaced `verify_signature: False` with proper JWKS verification for Google, GitHub, and Azure AD providers (`webgui/auth.py`)
- **Docker health checks** — agent health checks now perform an actual Redis ping instead of `print('healthy')` (`docker-compose.yml`)
- **PDF export** — implemented real PDF generation with ReportLab (`SimpleDocTemplate`, `Paragraph`, `Table`) with HTML fallback (`webgui/exports.py`)
- **Documentation consolidation** — CLAUDE.md slimmed to commands + pointers; full project documentation now lives in `docs/`; roadmap moved to `docs/development/roadmap.md`; `docs/development/setup.md` updated with current tech stack and plugin-architecture agent-adding steps

### Fixed

- `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` across codebase
- `RABBITMQ_URL` missing from WebGUI service in `docker-compose.yml`
- `.env.example`: removed duplicate keys, added 11 missing variables (OAuth, WebSocket, reporting, team config)
- `pyproject.toml`: added missing dependencies (`PyJWT[crypto]`, `faker`, `reportlab`, `requests`)

### Removed

- `langchain>=0.1.0,<0.2.0`, `langchain-openai>=0.0.5,<0.1.0`, `langchain-community>=0.0.38,<0.1.0` — replaced by litellm (via crewai 1.x)
- `numpy <2.0` upper bound — was required only by langchain 0.1.x
- `guest:guest` RabbitMQ default credentials — credentials now required at startup

### Tests

- `tests/unit/test_webgui_api.py`: `TestReportDownloadSecurity` (4 tests — valid path, path traversal blocked 403, dotdot blocked 403, missing file 404); `TestSecurityHeaders`
- `tests/unit/test_webgui_tasks.py`: 10 new validation tests (empty title, oversized fields, invalid priority enum, 422 responses)
- `tests/unit/test_webgui_exports.py`: `TestGenerateFileSanitization` (path traversal in session ID neutralised, normal IDs preserved)
- `tests/unit/test_model_manager.py`: 41 tests for AGNOS OS provider, gateway routing, env-var guards
- `tests/k8s/`: YAML structural validation for all Kubernetes manifests and Helm values
- **451 unit tests + 19 E2E tests passing**

---

## [2026.2.16]

### Added

- Complete 6-agent QA platform (QA Manager, Senior QA, Junior QA, QA Analyst, Security & Compliance, Performance & Resilience)
- CrewAI-based multi-agent orchestration via Redis + RabbitMQ Celery bus
- Chainlit WebGUI (`http://localhost:8000`) with real-time dashboard, session history, report generation
- Docker Compose deployment (9 containers) with optimised base image (99% faster rebuilds)
- Kubernetes deployment — Kustomize manifests + Helm chart with hardened security contexts (`readOnlyRootFilesystem`, drop ALL capabilities, seccomp RuntimeDefault)
- CI/CD pipeline (GitHub Actions) — test, lint, security scan (Bandit), Helm lint
- Multi-provider LLM integration (OpenAI primary; Anthropic, Google Gemini, Ollama, LM Studio fallbacks) via `config/model_manager.py`
- Advanced testing — self-healing UI selectors (CV + semantic analysis), fuzzy verification (LLM-based 0–1 quality scoring), risk-based test prioritisation (ML-driven)
- JWT authentication + RBAC (Super Admin, Org Admin, Team Lead, QA Engineer, Viewer, API User)
- Multi-format report export (PDF via ReportLab, JSON, CSV)
- Cross-platform testing support — web (Playwright), mobile (Appium), desktop (cross-platform)
- Compliance automation — OWASP, GDPR, PCI DSS, SOC 2, ISO 27001, HIPAA
- Predictive quality analytics — defect prediction, quality trends, risk scoring, release readiness
- AI-enhanced test generation — requirements-driven, code analysis, autonomous data generation
- Team size presets — Lean / Standard / Large via `QA_TEAM_SIZE` env var (`config/team_config.json`)
- 21 Architecture Decision Records (ADR-001 through ADR-016 + 021)
- YEOMAN MCP integration — 10 `agnostic_*` tools in SecureYeoman bridge

---

[2026.3.7]: https://github.com/MacCracken/agnostic/compare/2026.3.6...2026.3.7
[2026.3.6]: https://github.com/MacCracken/agnostic/compare/2026.3.5...2026.3.6
[2026.3.5]: https://github.com/MacCracken/agnostic/compare/2026.2.28...2026.3.5
[2026.2.28]: https://github.com/MacCracken/agnostic/compare/2026.2.16...2026.2.28
[2026.2.16]: https://github.com/MacCracken/agnostic/releases/tag/2026.2.16
