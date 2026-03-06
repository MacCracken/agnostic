# Tenant Provisioning

Guide for provisioning and managing tenants in the Agentic QA System.

> **Prerequisite:** Multi-tenancy requires `MULTI_TENANT_ENABLED=true` and `DATABASE_ENABLED=true` with a running PostgreSQL instance. See [Development Setup](../development/setup.md#database-migrations-alembic) for database configuration.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MULTI_TENANT_ENABLED` | `false` | Enable tenant isolation |
| `DATABASE_ENABLED` | `false` | Enable PostgreSQL persistence |
| `DEFAULT_TENANT_ID` | `default` | Fallback tenant for non-tenant requests |
| `TENANT_DEFAULT_RATE_LIMIT` | `100` | Requests per minute per tenant |

---

## Provisioning a Tenant

### 1. Create the tenant

```bash
curl -X POST http://localhost:8000/api/tenants \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "acme",
    "name": "Acme Corp",
    "slug": "acme-corp",
    "owner_email": "admin@acme.com",
    "plan": "pro"
  }'
```

Response:

```json
{
  "tenant_id": "acme",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "status": "trial",
  "plan": "pro"
}
```

Requires `super_admin` or `admin` role.

### 2. Invite users

```bash
curl -X POST http://localhost:8000/api/tenants/acme/users \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-1",
    "email": "dev@acme.com",
    "role": "member"
  }'
```

### 3. Issue a tenant API key

Store a SHA-256 hashed key in Redis for M2M authentication:

```bash
# Generate a key
API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
KEY_HASH=$(echo -n "$API_KEY" | sha256sum | cut -d' ' -f1)

# Store in Redis with tenant metadata
redis-cli SET "tenant_api_key:$KEY_HASH" '{"tenant_id":"acme","role":"api_user","permissions":["read","write"]}'

echo "Tenant API Key: $API_KEY"
```

Clients authenticate with `X-API-Key: <key>`. The system looks up the hash, finds the tenant, and scopes all operations to that tenant.

---

## Tenant Isolation

When `MULTI_TENANT_ENABLED=true`, the system isolates tenant data at the Redis key level:

| Resource | Key format (disabled) | Key format (enabled) |
|----------|-----------------------|----------------------|
| Task | `task:<task_id>` | `tenant:<tenant_id>:task:<task_id>` |
| Session | `session:<session_id>` | `tenant:<tenant_id>:session:<session_id>` |
| Generic | `<key>` | `tenant:<tenant_id>:<key>` |

Task submission (`POST /api/tasks`) and retrieval (`GET /api/tasks/{id}`) automatically use tenant-scoped keys based on the authenticated user's `tenant_id`.

### Rate Limiting

Each tenant has a per-minute sliding window rate limit (default: 100 requests/minute). When exceeded, `POST /api/tasks` returns HTTP 429.

The rate limit counter uses Redis keys of the form `tenant:<id>:rate:<YYYYMMDDHHmm>` with a 60-second TTL.

---

## Managing Tenants

### List tenants

```bash
curl http://localhost:8000/api/tenants \
  -H "Authorization: Bearer <admin-token>"
```

### Update tenant

```bash
curl -X PUT http://localhost:8000/api/tenants/acme \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"plan": "enterprise", "max_sessions": 50, "max_agents": 20}'
```

Updatable fields: `name`, `status`, `plan`, `max_sessions`, `max_agents`, `max_storage_mb`, `webhook_url`, `custom_domain`.

### Deactivate tenant

```bash
curl -X DELETE http://localhost:8000/api/tenants/acme \
  -H "Authorization: Bearer <admin-token>"
```

This is a **soft delete** — sets `is_active=false` and `status=disabled`. Data is retained.

### List / remove users

```bash
# List
curl http://localhost:8000/api/tenants/acme/users \
  -H "Authorization: Bearer <admin-token>"

# Remove
curl -X DELETE http://localhost:8000/api/tenants/acme/users/user-1 \
  -H "Authorization: Bearer <admin-token>"
```

---

## Tenant Lifecycle

```
Created (trial) ──► Active ──► Suspended ──► Disabled (soft-deleted)
       │                                          ▲
       └──────────────────────────────────────────┘
                    (direct deactivation)
```

| Status | Behavior |
|--------|----------|
| `trial` | Full access, checked against `trial_ends_at` |
| `active` | Full access, production use |
| `suspended` | Read-only, no new task submission |
| `disabled` | No access, data retained for reactivation |

---

## Backward Compatibility

When `MULTI_TENANT_ENABLED=false` (default):

- All requests use `DEFAULT_TENANT_ID` (`default`)
- Redis keys use plain format (`task:<id>`, not `tenant:default:task:<id>`)
- Rate limiting is not enforced
- Tenant API endpoints return HTTP 503

No code changes are needed for single-tenant deployments.

---

*Related: [API Reference](webgui.md) · [Development Setup](../development/setup.md) · [ADR-017 — API Keys](../adr/017-task-submission-api-keys.md)*
