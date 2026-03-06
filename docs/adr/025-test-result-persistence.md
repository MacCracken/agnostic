# ADR-025: Test Result Persistence (PostgreSQL)

**Status**: Accepted
**Date**: 2026-03-05
**Authors**: Agnostic team

---

## Context

Test results were stored only in Redis with a 24-hour TTL. This made historical analysis, quality trends, and compliance auditing impossible beyond a single day. For production QA workflows, results must persist across sessions and be queryable over time.

---

## Decision

Add PostgreSQL as an optional persistence layer for test results, metrics, and reports. The feature is **opt-in** via the `DATABASE_ENABLED` environment variable and does not affect existing Redis-based workflows.

### Data Model

Four SQLAlchemy async models:

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `test_sessions` | QA session tracking | session_id, title, status, priority, created_by |
| `test_results` | Individual test outcomes | test_id, test_name, status, severity, category, execution_time_ms |
| `test_metrics` | Numeric metrics per session | metric_name, metric_value, metric_unit |
| `test_reports` | Generated reports | report_type, summary (JSON), pass_count/fail_count/pass_rate |

All tables are indexed on `session_id` and `created_at` for efficient querying.

### Repository Pattern

`TestResultRepository` provides async CRUD operations:
- `create_session()`, `update_session_status()`, `get_sessions()`
- `add_test_result()`, `get_test_results()`, `get_session_results_summary()`
- `add_metric()`, `get_metrics()`
- `create_report()`, `get_reports()`
- `get_quality_trends(days)` — aggregated pass/fail counts by date

### REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/test-sessions` | List sessions with optional status filter |
| POST | `/api/test-sessions` | Create a new test session |
| PUT | `/api/test-sessions/{id}/status` | Update session status |
| GET | `/api/test-results` | Query results by session/status |
| POST | `/api/test-results` | Add a test result |
| GET | `/api/test-results/{session_id}/summary` | Session results summary |
| GET | `/api/test-metrics/trends` | Quality trends over N days |

All endpoints return HTTP 503 with a clear message when `DATABASE_ENABLED=false`.

### Configuration

```env
DATABASE_ENABLED=true
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=secret
POSTGRES_DB=agnostic
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
```

---

## Files Modified

- `shared/database/models.py` — SQLAlchemy models, engine initialization, `get_session()`
- `shared/database/repository.py` — `TestResultRepository` with async CRUD
- `shared/database/__init__.py` — Package init
- `webgui/api.py` — 7 REST endpoints with `DATABASE_ENABLED` guard
- `pyproject.toml` — `sqlalchemy[asyncio]`, `asyncpg` dependencies
- `.env.example` — `DATABASE_ENABLED`, `POSTGRES_*`, `DB_*` variables
- `tests/unit/test_database_models.py` — Unit tests for models and repository

---

## Consequences

### Positive
- Historical quality trend analysis across days/weeks/months
- Compliance audit trail persists beyond Redis TTL
- Repository pattern isolates database logic from API layer
- Connection pooling with configurable limits

### Negative
- PostgreSQL is an additional infrastructure dependency
- Schema migrations will be needed as models evolve (not yet automated)

### Neutral
- Fully opt-in — existing Redis-only deployments are unaffected
- Redis remains the primary real-time data store; PostgreSQL is for persistence
