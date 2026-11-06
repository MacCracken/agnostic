# 0023 — Provisioning is routes and one recovery command, and ADMIN runs a tenant

**Status**: Accepted
**Date**: 2026-11-05

## Context

Until 0.3.0 a deployment had one user. `agnostic_users_create_a` was called only by the bootstrap, and
`agnostic_tenant_create_a` and `agnostic_apikey_issue_a` had no callers, so nothing could add anyone,
issue a key or rotate the bootstrap password. Tokens were signed with a secret drawn at start, so a
restart logged everyone out. The v1.0 criterion "a consumer green against the published API" could not
be met.

A second user makes two latent findings of the 2026-11-05 audit real. Any ADMIN could read every
tenant's audit entries and switch a plugin for everyone (S4), and a tenant-b OPERATOR could list, read,
replace and delete tenant-a's agent definitions (S3).

The server claims its database for its whole life (`src/engine/store.cyr`), so a second process cannot
write beside it. That rules out a command for ordinary provisioning, because each user added would mean
stopping the server. Routes alone leave one hole: `agnostic_auth_bootstrap_a` acts only on an empty
store, so a lost password on the last super administrator has no way back.

## Decision

**Provisioning is 17 routes on a running server, plus `agnostic admin reset-password`, which needs the
server stopped and does nothing else.** The user chose this form on 2026-11-05.

**Three tiers, in the permission table.** Everyone manages their own password and API keys (READ, which
every role holds). An ADMIN manages the users of their own tenant. A SUPER manages tenants, and the users
of any of them. The audit trail and the plugin switch move from ADMIN to SUPER, because they span tenants
and audit entries carry no scope to filter by. A route nobody classified now falls through to SUPER.

**What the ladder cannot see, the handlers check** (`src/routes/identity.cyr`):

- Another tenant's user does not exist: 404, not 403, as ADR 0008 has it for crews.
- Nobody grants a role above their own, or touches a user above their own: 403.
  `agnostic_role_within` compares permission masks, never role numbers (`src/auth/perm.cyr`).
- The last super administrator cannot be deleted or demoted: 409, decided under the store lock with the
  write, so two requests cannot both pass.
- `PUT /api/v1/users/{id}/password` refuses the caller's own account. It takes no current password, so a
  stolen token would keep the account. `PUT /api/v1/auth/password` is the way.

**A password change ends older tokens.** `agnostic_users` gains `tokens_from`, and a bearer token issued
before it is refused. The role is already read from that row on every request, so this adds one column
to one statement. `ADD COLUMN` runs on every start, so a store from before 0.3.0 gains it with every
token still good, and a store that has it is untouched. `PUT /api/v1/auth/password` answers a new token,
or changing a password would log the client out.

**An API key belongs to a user** and takes that user's current role. It is not revoked by a password
change: it is a separate credential, and a script should not break because someone rotated a password.
A user holds at most 32. Only the digest is stored, so the 201 that mints a key is the only time it exists.
A key cannot mint a key, or a stolen one could outlive being revoked.

**Ids on the wire are 16 hex digits, not numbers.** A uid is a 63-bit integer, and as a JSON number a
browser rounds it to 53 bits and silently names somebody else.

**`AGNOSTIC_JWT_SECRET`** is at least 32 bytes, or the server refuses to start. Unset, each process draws
a secret, as before.

**Agent definitions belong to a tenant** (S3). The row key is `<tenant>:<key>`, and in the default scope
`_` it is the bare key. A row from before 0.3.0 has no colon, so it is `_`'s with no migration, as a crew
stored before 0.1.9 is (ADR 0008).

**`agnostic admin reset-password <email>`** takes the database claim, so it refuses while a server runs. It
reads the password from stdin, because arguments are visible in `/proc/<pid>/cmdline`, and it refuses to
run if it cannot write the audit trail.

## Consequences

- **Positive**
  - A deployment can have users, tenants and machine credentials, and tokens survive a restart.
  - S3, S4 and S12b are closed, and an unclassified route now fails closed at the top.
  - Role changes and deletions land on the next request, as the design always promised.
- **Negative**
  - ⚠ **Breaking:** an ADMIN can no longer read the audit trail or switch a plugin. Only the bootstrap
    account is SUPER on an existing deployment, and it was the only account there could be.
  - ⚠ **Breaking for tenants:** definitions are per tenant now. In practice none existed outside `_`,
    because nothing could create a second user.
  - A 409 on `POST /api/v1/users` tells an ADMIN that an address is taken, perhaps in another tenant.
    Login needs one address to mean one user.
  - `iat` is in seconds, so a token issued in the very second of a password change survives it.
  - Deleting a tenant keeps what is stored under it, as `agnostic_tenant_delete_a` always said, and a
    tenant created later with that key reads it.
- **Neutral**
  - The WebGUI has no users view yet (roadmap, 0.3.x).
  - The routes are listed under the skill's "Routes this skill does not teach", except minting a key.

## Alternatives considered

- **A command only.** Rejected: each user added would mean stopping the server, and the WebGUI could not
  use it.
- **Routes only.** Rejected: a lost password on the last super administrator would have no way back.
- **`/api/v1/users/me/...` in place of `/api/v1/auth/...`.** Rejected: one handler would decide both tiers,
  so the schema's permission for those routes would say `read` for what is an administrator's action.
- **A permission of its own for your own credentials.** Rejected: READ is already what every role holds,
  and no plugin is granted these routes, so a new vocabulary word would change nothing.
- **A revocation list for tokens.** Rejected: `tokens_from` does the same with state that is already read
  on every request.
- **Filtering audit entries by scope, in place of SUPER.** Rejected: entries carry no scope, and giving
  them one means changing libro's store. A tenant's own trail can be added later without taking this back.
- **Refusing a tenant delete until its data is gone.** Rejected: a cascade across every scoped table is a
  data-loss primitive behind one call.
