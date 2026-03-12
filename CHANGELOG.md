# Changelog

## [2026.3.12-1] - 2026-03-12

### Bug Fixes
- **Health check degraded status** — `/health` now returns HTTP 200 for "degraded" state (no agent heartbeats, RabbitMQ down). Only "unhealthy" (Redis/DB down) returns 503. Fixes false-negative liveness failures in fresh containers and e2e tests.
- **K8s manifest test expectations** — Fixed HPA, PDB, and NetworkPolicy test expectations to match actual manifest names (`agnostic` not `webgui`).
- **Integration test patches** — Rewrote `test_agent_communication.py` to patch `config.get_redis_client` instead of non-existent `module.redis.Redis` attributes. Tests now exercise real agent methods (`get_session_status`, `_get_redis_json`).

### Features
- **Session comparison report** — Implemented `_generate_comparison_report()` in exports module. Compares current session metrics (score, duration, errors, coverage) against up to 10 historical sessions with trend analysis and per-agent benchmarking.

### Documentation
- **API path versioning** — Updated `docs/api/webgui.md` to use `/api/v1/` prefixes throughout, matching the actual router implementation.

## [2026.3.12] - 2026-03-12

### Performance
- **Async Redis in agent_monitor** — Migrated all Redis calls from sync `redis.Redis` to `redis.asyncio.Redis`, eliminating event loop blocking on dashboard loads.
- **MGET batching** — Replaced N+1 per-key GET loops with SCAN + MGET batch queries; reduces ~1800 Redis round-trips per dashboard refresh to ~6.
- **Bounded LRU cache** — Agent status cache now uses `_BoundedCache(OrderedDict)` with configurable max entries, preventing unbounded memory growth.
- **Single-pass error rate** — Eliminated 3 separate SCAN passes for error rate calculation; now uses a single `_count_tasks_by_status()` call.
- **DB pool defaults** — Increased PostgreSQL connection pool from 5/10 to 20/40 (`pool_size`/`max_overflow`), configurable via `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` env vars.

### Features
- **Health check HTTP status codes** — `/health` now returns 200 for healthy, 503 for degraded/unhealthy. Monitoring systems (Kubernetes, Prometheus) can now detect failures without parsing JSON.
- **Readiness probe** — Added `/ready` endpoint for Kubernetes readiness checks (Redis + optional DB connectivity).
- **Task cancellation** — `DELETE /tasks/{task_id}` cancels pending/running tasks with state validation (409 for terminal states).
- **Task retry** — `POST /tasks/{task_id}/retry` retries failed/cancelled tasks by cloning the original requirements.
- **LLM streaming timeout** — `_streaming_call()` now enforces `LLM_STREAM_TOTAL_TIMEOUT` (default 300s) via `asyncio.wait_for()`, preventing indefinite hangs.
- **MCP subscribe_webhook** — Implemented `agnostic_subscribe_webhook` MCP tool dispatcher with SSRF validation and Redis subscription storage.
- **MCP event_stream** — Implemented `agnostic_event_stream` MCP tool dispatcher returning SSE connection info.
- **Session filtering/sorting** — `GET /sessions` now supports `status`, `created_after`, `created_before`, `sort_by`, and `sort_order` query parameters.

### Bug Fixes
- **Webhook signature verification** — Fixed inverted logic: when no `YEOMAN_WEBHOOK_SECRET` is configured, webhooks are now accepted (dev/test mode) instead of silently rejected.
- **Report type/format validation** — `ReportGenerateRequest` now uses Pydantic `Literal` types, rejecting invalid report types and formats at the model layer instead of at generation time.

### Configuration
- `MAX_ACTIVE_SESSIONS` — Configurable via env var (default 1000).
- `REPORTS_DIR` — Configurable report output directory (default `/app/reports`).
- `EVENT_BUFFER_MAX` — Configurable SSE event buffer size (default 1000).
- `LLM_STREAM_CHUNK_TIMEOUT` / `LLM_STREAM_TOTAL_TIMEOUT` — Configurable streaming timeouts.
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` — Configurable database connection pool sizing.

### Audit
- Added `TASK_CANCELLED` audit action for task cancellation tracking.

### Tests
- Rewrote `test_agent_monitor.py` for async Redis (17 tests with `AsyncMock` and async generators).
- Added `test_code_review_changes.py` (23 tests covering webhook signatures, report validation, task cancel/retry models, health check status codes, MCP dispatch, LLM streaming timeout, configurable constants).
- Updated health check tests across `test_webgui_app.py`, `test_webgui_api.py`, and `test_yeoman_phase_b.py` for new HTTP status code behavior.
- **833 unit tests passing**, 0 failures.

## [2026.3.9] - 2026-03-09

- Initial versioned release.
