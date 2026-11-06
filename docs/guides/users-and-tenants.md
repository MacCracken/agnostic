# Users and tenants

How to go from the bootstrap account to a deployment with people, tenants and machine credentials.
Every example needs `AGNOSTIC_AUTH=required`. [ADR 0023](../adr/0023-provisioning-is-routes-and-one-recovery-command.md)
says why it works this way.

## Roles

| Role | Can |
|---|---|
| `viewer` | Read crews, presets and definitions in their tenant, and manage their own password and API keys |
| `operator` | Also submit and cancel crews, and write definitions |
| `admin` | Also manage the users of their own tenant |
| `super_admin` | Also manage tenants and any tenant's users, read the audit trail, and switch plugins |

Nobody can grant a role above their own, or change a user above their own. To a tenant's administrator,
another tenant's user answers 404.

## First steps

Start the server with a bootstrap account and a signing secret:

```bash
export AGNOSTIC_AUTH=required
export AGNOSTIC_BOOTSTRAP_EMAIL=you@example.com
export AGNOSTIC_BOOTSTRAP_PASSWORD='at least twelve characters'
export AGNOSTIC_JWT_SECRET="$(head -c 32 /dev/urandom | base64)"
./build/agnostic
```

Keep `AGNOSTIC_JWT_SECRET` somewhere safe and set it again on every start. Without it, each restart ends
every session.

Log in and replace the bootstrap password:

```bash
TOKEN=$(curl -sS -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"at least twelve characters"}' | jq -r .token)
```

```bash
curl -sS -X PUT localhost:8000/api/v1/auth/password -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"current_password":"at least twelve characters","new_password":"a better password"}'
```

The answer holds a new token, because changing a password ends the older ones. Then unset
`AGNOSTIC_BOOTSTRAP_PASSWORD`. It has no effect once a user exists.

## Add a tenant and a user

```bash
curl -sS -X POST localhost:8000/api/v1/tenants -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"key":"acme","name":"Acme Corp"}'
```

```bash
curl -sS -X POST localhost:8000/api/v1/users -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"email":"ops@acme.example","password":"twelve or more","role":"admin","tenant":"acme"}'
```

A tenant key is lower-case letters, digits and hyphens. A user with no `tenant` is in the default scope,
`_`. An administrator creates users in their own tenant and need not name it.

Crews, agent definitions and plugin documents belong to a tenant.

## Give a script a key

Log in as the user the script should act as, then:

```bash
curl -sS -X POST localhost:8000/api/v1/auth/api-keys -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"label":"ci"}'
```

The `api_key` in the answer is shown once. Send it as `Authorization: ApiKey <key>`. A key takes its user's
current role and lasts until it is revoked. A key cannot mint another, so a stolen one cannot outlive
being revoked. Revoke one with `DELETE /api/v1/auth/api-keys/{id}`, and an
administrator can use `DELETE /api/v1/users/{id}/api-keys/{key}`.

A password change does not revoke keys. If an account is compromised, revoke them too.

## If everyone is locked out

Stop the server, then set a password from the machine that holds the database:

```bash
read -rs PW && printf '%s\n' "$PW" | ./build/agnostic admin reset-password you@example.com
```

It reads the same `AGNOSTIC_DB_PATH` and `AGNOSTIC_AUDIT_PATH` as the server, refuses while a server is
running, and records the reset in the audit trail. The password comes from stdin because a command-line
argument is visible to every user of the machine.
