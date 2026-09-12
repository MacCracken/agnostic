# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.1] - 2026-09-11

### Changed

- **Toolchain `6.5.35` → `6.6.2`.** No source change; the value form needed none.
  Build, tests, and any bench/fuzz/distlib target the repo ships re-verified at the new pin.

- **agnosai `2.0.8` → `2.0.9` — fixes the aarch64 cross-build.** agnosai's
  `sandbox/spawn.cyr` wired the child's stdio with raw `syscall(SYS_DUP2, fd, n)`.
  aarch64 Linux has **no `dup2` syscall at all** (only `dup3`), so the constant is
  undefined there and `Cross-build aarch64` failed on the vendored bundle with
  `undefined variable 'SYS_DUP2'`. The x86_64 build never touches that path, which is
  why it shipped green. 2.0.9 uses the stdlib's `sys_dup2()`, which exists on both
  targets. Verified here: aarch64 cross-build OK (6,086,136 bytes).

- **`scripts/lock-check.sh` replaces the inline `git diff --quiet -- cyrius.lock`.**
  `cyrius deps` does NOT emit the lock's entries in a stable ORDER across machines, so
  the byte-exact gate failed for every lock committed from another machine — it
  reported `98 insertions(+), 98 deletions(-)` while an order-insensitive compare of
  the same two files was EMPTY (identical hashes for all 117 entries, different
  sequence). The script — adopted verbatim from commandress, which hit this on its
  first CI run — compares the `commit` pins and the file set as sorted sets, so it
  still catches a changed hash, an added entry or a dropped pin. Upstream:
  cyrius `docs/development/issues/2026-09-12-cyrius-lock-unstable-order.md`.

- **`bote`, `majra`, `ai-hwaccel` and `tyche` are now pinned explicitly, ahead of
  `[deps.agnosai]`.** agnosai's own published manifest declares them with
  `path = "../<sibling>"` beside their tags; a path override makes the tag inert, so a
  machine with those siblings checked out resolves the working tree while CI resolves
  the tag. Declaring them here without a path removes the override from this repo's
  resolution.


### Changed — agnosai 2.0.4 → 2.0.5, Cyrius pin 6.5.32 → 6.5.34, and `[deps.agnosai]` loses its `path`

**These are one change, not three.** agnosai 2.0.5 carries bote 3.3.3 → libro 2.8.10,
which declares `[deps.patra] = 1.13.10`, and `cyrius deps` overlays a declared dep's
copy on top of the `lib sync --full` snapshot on every resolve. Only a Cyrius that
folds 1.13.10 — **6.5.34** — leaves `lib/` matching the pin, and
`scripts/check-clean.sh`'s lib-snapshot rule allows **no** file to differ.

⚠ Bumping either half alone leaves this repo red, in opposite directions: 2.0.4 pulls
libro 2.8.8 (patra 1.13.9), which would **downgrade** `lib/patra.cyr` against a 6.5.34
snapshot exactly as surely as 2.0.5 **upgraded** it against a 6.5.32 one. agnosai's
`main` was red for precisely this reason before 2.0.5.

**`path = "../agnosai"` is deleted, and that is the durable fix.** `path` beats `tag`
when a checkout is present, so every previous resolve here vendored whatever the
sibling working tree happened to hold — content corresponding to no tag, which CI
cannot fetch. The effect is measurable: **the lock went from 1 commit pin to 9.**
Every dependency now resolves from `git` + `tag` and carries a commit pin —
`agnosai` 2.0.5, `sigil` 3.12.9, `bote` 3.3.3, `majra` 2.6.7, `kavach` 3.12.2,
`ai-hwaccel` 2.3.18, `tyche` 1.0.1, `libro` 2.8.10, `patra` 1.13.10. Verified:
`lib/agnosai.cyr` is byte-identical to `git show 2.0.5:dist/agnosai.cyr`.

**What the chain actually delivers here.** libro 2.8.9 fixes `PatraStore` faulting when
read off the opening thread — **the defect this repo reported**, and the reason its audit
verification currently runs only once at open. patra 1.13.10 stops `patra_init` clobbering
the host's log level — the other work-around, in `src/engine/store.cyr`. ⚠ **Both
work-arounds are still in place and are now removable**; they are left for a separate
change rather than folded into a dependency bump.

Also arrives: kavach 3.12.2 (`config_env`, `config_workdir`, and a command-blocklist fix
that let a rootfs'd sandbox run a shell). Nothing here calls that surface yet.

### Added — a `lib/`↔`lib/` symbol gate, because nothing in the ecosystem had one

`scripts/check-lib-symbols.py`, wired in as **Rule 4** of `check-symbols.sh`.

Rules 1–3 all take `src/` as one side of the comparison, so none of them can see a
collision **between two dependencies** — and neither can the compiler, which warns on a
duplicate `fn` and is **silent** for `var` and for enum members. That blind spot is how
kavach's `var BACKEND_COUNT = 10` and ai-hwaccel's `= 18` both reached a binary through
agnosai, with the 18 winning: it admitted ids 0–17 into a 10-slot function-pointer table
and called whatever sat 224 bytes past its end. It was found by hand.

`lib/` here is ~1.6 MB of vendored dependency, most of it arriving **transitively**
through agnosai — kavach, ai-hwaccel, libro, bote-core, majra, tyche — so this repo
carries the exposure without declaring most of the deps that create it.

The check resolves the real compile set from `cyrius.cyml` (`[deps].stdlib`, each dist's
`.deps` sidecar, every dep dist in `lib/`), skips the per-platform stdlib variants that
define the same names on purpose, **fails** on any constant defined twice with differing
values, and reports the rest. **Validated against the historical defect**: with kavach
3.11.14 and ai-hwaccel 2.3.17 restored it reports `BACKEND_COUNT` 18-vs-10 and fails.

⚠ **One live divergence is allow-listed, not fixed:** `STDIN` is `var STDIN = 0` in
`lib/io.cyr` and `InjectionMethod.STDIN = 2` in `lib/kavach.cyr`. Under this repo's
ordering io.cyr wins, so kavach's member collapses onto `ENV_VAR` (both 0) and its two
credential guards alias — a secret requested on stdin would be injected into the
environment instead. **Unreachable here**: across the whole 52-module compile set `STDIN`
occurs exactly four times — io.cyr's definition and kavach's own three — and nothing reads
it as a file descriptor. Filed upstream with a repro; a consumer-side rename cannot fix it
because both definitions live in `lib/`.

### Changed — agnosai 2.0.5 → 2.0.6, Cyrius pin 6.5.34 → 6.5.35

**24 suites, 1,175 assertions, 0 failed — identical to before the bump**, which is
the expected result: agnosai 2.0.6 is a dependency-and-toolchain release whose only
`src/` change is a version-drift fix, and `git diff --stat 6.5.34 6.5.35 -- lib/`
is empty, so the folded stdlib does not move either. This bump changes the code
generator and the dependency chain, not behaviour.

Arriving through agnosai: **bote 3.3.3 → 3.3.7**, **majra 2.6.7 → 2.7.0**, and
**libro 2.8.10 → 2.8.12** transitively through bote. `sigil` 3.12.9, `kavach`
3.12.2, `ai-hwaccel` 2.3.18 and `tyche` 1.0.1 were already newest and did not move.

✅ **No `[deps.patra]` hold is needed at this pin.** 6.5.35 folds patra 1.13.10,
which is what libro 2.8.12 declares, so `lib/` matches the snapshot with **zero**
files differing — verified file by file, not inferred from a green gate. The hold
that 2.0.5 needed is not reintroduced here and must not be added back.

⚠ **Verified against the tags, not the install directory.** `lib/agnosai.cyr` is
byte-identical to `git show 2.0.6:dist/agnosai.cyr`, and every dep dist in `lib/`
was matched back to a tag by hash. That discipline exists because reading
`~/.cyrius/versions/<V>/lib/` produced a wrong diagnosis earlier in this port —
a concurrent session rewrites those files in place.

⚠ **The lock carries 8 commit pins, not 9: `agnosai` has none yet.** At the time
of this change `refs/tags/2.0.6` was **not on the remote** — the commit was pushed,
the tag was not — so `cyrius deps` could not fetch it and the dep was resolved from
a locally seeded cache of the tagged tree. The bytes are identical to the tag by
construction and were hash-checked against it. **A fresh `cyrius deps` after the
tag is pushed will add the missing commit pin**, and CI cannot resolve this
dependency until then. That is the one outstanding item on this change.

### Added — M6 (part 1), the tool viability gate: 2 of 38 resolve

**31 assertions** in `tests/tools.tcyr`; 1,175 total across 24 suites, 0 failed.
`src/engine/tools.cyr` turns the preset tool vocabulary from a comment into a
**checkable contract**, which is the thing the roadmap assigns M6 to own.

**The measured position, not an estimate.** The 18 presets name **38 distinct
tools**; the engine registers **14 builtins**; **zero of the 38 resolve by name**,
because the two vocabularies are in different forms — `LoadTestingTool` versus
`load_testing`. After this change **2 resolve and 36 do not**, and both numbers
are pinned by the suite so they can only move deliberately.

⚠ **A case transform was rejected, not overlooked.** `LoadTestingTool` →
`load_testing` happens to work; `RiskScoringTool` → `risk_scoring` resolves to
nothing at all. A transform makes those two indistinguishable — it reports
coverage for 38 names and fails at call time for 36 of them. An explicit alias
table is the only shape where an entry means something can actually run.

⚠ **`ComprehensiveSecurityAssessmentTool` is deliberately NOT aliased to
`security_audit`**, even though the backend is sitting right there and the names
are close. "Comprehensive" is a stronger claim than the backend makes, and
mapping it would book coverage this tree does not have. The suite asserts the
absence, so a later contributor has to argue for it rather than add it quietly.

⚠ **A miss returns 0, and callers must refuse.** That is the direct answer to
`ORACLE-AUDIT.md` §3.15 — the oracle's registry was never populated, so
`_resolve_tools` warned and built every agent with `tools=[]`. The defect was not
the empty registry; it was that a miss degraded silently. There is no
best-effort path in this module and none should be added.

⚠ **Resolution returns the ENGINE's tool object rather than wrapping it.** A
wrapper per QA name would record two GenAI spans per call — `agnosai_tool_execute`
instruments the vtable chokepoint — and would have to reproduce the backend's
schema callback, whose allocator convention is AgnosAI's to change.

**`ArtifactManagementTool` and `CIPipelineIntegrationTool`** are still named by
`quality-large.json` and still have no implementation anywhere — unlike the other
36, which at least had a class in the oracle. The roadmap requires them written
or struck; `tools/nonexistent` exists so that decision cannot be forgotten.

⚠ **What M6 part 2 has to decide first: who owns the tool registry.**
`agnostic_engine_init` exposes no registry handle — the orchestrator owns one
internally — so nothing here is wired into mount yet, and coverage is a library
question rather than a served one. Registering agnostic's QA tools somewhere the
orchestrator's agents actually read is the next decision, and guessing at it
would be the kind of narrow fix that has to be redone. The gate is deliberately
useful without it: the number is real, and it is the number that has to reach 0.

### Added — M5 (part 3), the login route and the first-administrator bootstrap

**35 assertions** in `tests/loginroute.tcyr`; 1,144 total across 23 suites, 0 failed.
Together these close the loop M5 part 2 left open: there was an auth rung and no
way to obtain a credential, and no way to create the account that would.

**`POST /api/v1/auth/login`** — `{email, password}` on the allow-list codec, so an
unknown field is a 422 rather than the oracle's silent discard. Answers a Bearer
token, its type, its TTL and the role.

⚠ **It is the only anonymous route on the authenticated surface**, exempted in
`agnostic_route_needs_auth` — a route that issues credentials cannot require one.
That exemption is the single hole in this API's fail-closed default, and what
stands in it is `agnostic_login_a`: the per-IP bucket and the Argon2 pool cap,
both already mutation-verified to run *before* any hashing.

⚠ **A wrong password and an unknown address are byte-identical responses.** Same
status, same rendered body — asserted by comparing the two, not by inspection.
`agnostic_users_verify_a` already spends a full Argon2 on the unknown path, so
the timing does not separate them either. The 429s are likewise
indistinguishable: bucket exhaustion and a saturated pool both answer "come back
later" without saying which limit was hit.

**`agnostic_auth_bootstrap_a`** creates the first administrator as a SUPER_ADMIN
— it has to be able to provision everything else. ⚠ **It refuses if ANY user
already exists**, which is what keeps a credential left in the environment from
being a standing backdoor. Not "no admin exists": a deployment holding a lone
viewer has already been bootstrapped. *Mutant: removing that guard mints a second
super-admin from the same environment variables.*

⚠ **`AGNOSTIC_AUTH=required` with no users and no bootstrap credential REFUSES TO
START.** The alternative is a server that is up, enforcing, and impossible to
authenticate against — locked shut with no message saying why.
`AGNOSTIC_BOOTSTRAP_PASSWORD` is read like `AGNOSTIC_LLM_API_KEY`: stored, never
logged, never in a response. The mount logs the email and uid, and WARNs to
rotate the credential.

### Changed — the dispatch ladder takes a request context, not a bare header

`agnostic_route_dispatch_a`'s sixth parameter is now an `agnostic_reqctx_new_a`
block carrying the credential *and* the peer address, which the login route needs
for its rate bucket. Threading each transport fact separately is how a dispatch
signature reaches nine parameters.

⚠ **`peer_ip` is the socket peer, deliberately not `X-Forwarded-For`.** Behind a
proxy every request shares one address and the bucket becomes a global limit —
a real deployment problem, but the alternative is worse: a caller-supplied
address lets an attacker mint a fresh bucket per request and removes the control
entirely. Trusted-proxy configuration is not carried yet.

⚠ **Two Cyrius hazards this change walked into, both worth knowing:**

- `ctx == 0` still means "nothing known", so the existing call sites kept
  compiling — but `tests/authn.tcyr` passed a **`Str` header** where a struct was
  now expected, and everything is `i64`, so nothing caught it. The suite
  **crashed** rather than failing an assertion, producing no output at all: it
  showed up only as `22 passed, 1 failed` with 23 suites present. Changing what a
  parameter *means* is not visible to the compiler here.
- `agnostic_serve_handler`'s first parameter is already named `ctx` (sandhi's
  server context). Shadowing it is a compile error whose diagnostic points at an
  **unrelated file** — `src/routes/crews.cyr`, at a column that line does not
  have.

⚠ **And one real bug the tests initially hid.** The login route first passed
`agnostic_encode_a(...)` to `agnostic_response_json_a`, but that helper takes the
bayan **object** — `_agnostic_serve_send` serialises it. Handing it a `Str` makes
it encode the encoding, so the client receives a JSON string containing escaped
JSON. The test missed it by reading the body directly instead of through the send
path; it now asserts the rendered body begins with `{`.

### Removed — both sibling-library work-arounds, now that their fixes have landed

Two guards in this tree existed only because upstream defects were live. Both
fixes arrived with agnosai 2.0.5 / Cyrius 6.5.34, so both guards are gone —
and each is replaced by an assertion, because both failures were **silent**.

**`patra_init` no longer clobbers the host's log level.** It used to end with an
unconditional `sakshi_set_level(SK_WARN)`, process-global, so opening the
database threw away whatever `AGNOSTIC_LOG_LEVEL` had set — including the
`listening` line. `src/engine/store.cyr` saved and restored the level around the
call. Fixed in **patra 1.13.10**; the save/restore is deleted from `store.cyr`
and from six test helpers that had copied it. `tests/crewstore.tcyr`'s
`store/log-level` group now asserts the level survives `patra_init` at INFO and
DEBUG — the downstream symptom is *missing log lines*, not an error, so it needs
a test rather than a reader's attention.

**A `PatraStore` read from another thread no longer kills the process.**
`patrastore_open` cached its `SELECT` and `COUNT` handles while patra's SQL parse
scratch is per-thread, so a statement parsed on the opening thread and executed
on a sandhi pool worker dereferenced absent TLS — no diagnostic, no unwind. This
tree found it as *"the first HTTP request to one endpoint takes the whole server
down while every other route keeps working"*, filed it, and worked around it by
reading **nothing** off the main thread: `agnostic_audit_count` was
`at_open + appended` arithmetic rather than a query, and verification could only
run at open.

Fixed in **libro 2.8.9**, so:

- `agnostic_audit_count` now **queries live**. The counter version was also wrong
  whenever this process was not the only writer — it under-reported silently.
- **`agnostic_audit_reverify` is new** and runs on any thread, which is the live
  re-verify endpoint the module header said would become possible. ⚠ It re-reads
  and re-hashes the whole chain, so it is an operator action, not a health check.
- The open-time verdict is still what `/api/v1/audit` reports by default — that
  part was a design preference, not the constraint, and it stays.

`tests/audit.tcyr`'s `audit/off-thread` group spawns a worker and has it both
count and re-verify. ⚠ **If that test ever dumps core instead of failing an
assertion, the upstream fix has been undone.** Worth knowing while reading it:
patra's own comment records that threads spawned via `lib/thread.cyr` inherit
their TLS block through `CLONE_SETTLS` and must **not** re-init — which is why a
pool worker can touch the store without any per-worker setup.

### Added — M5 (part 2), identity end to end: the auth rung is no longer a comment

**478 assertions across five new suites**; 1,103 total across 22 suites, 0 failed.
Every security claim below is backed by a **killed mutant**, not by a passing
assertion — the mutation is named with each one.

**`src/auth/store.cyr` — users and API keys.** patra auto-indexes column 0 when
it is `COL_INT`, so both tables put a 63-bit truncated SHA-256 there and issue
**zero `CREATE INDEX`**. ⚠ That makes a hit a *bucket*, not an identity: patra
re-checks its own STR index hits and gives no such re-check for an app-computed
INT key. Every lookup re-verifies the full value, the API-key path in constant
time. *Mutants: dropping either re-check returns an attacker's row — the user one
resolved a forged collision to somebody else's uid.* An over-long email is
**refused**, because a `COL_STR` is 256 fixed bytes and truncation would merge two
addresses into one row. An unknown address still costs a full Argon2 against a
decoy record, so login is not a user-enumeration oracle.

**`src/auth/jwt.cyr` — HS256 bearer tokens**, adapted from the SecureYeoman
probe the roadmap names. ⚠ **The token's own `alg` header is never read.**
Verification recomputes HS256 and compares; there is no branch that could select
an algorithm the caller named, so `{"alg":"none"}` and an RS256 swap both die at
the MAC. The signature is compared **encoded**, so attacker-controlled base64 is
never decoded before authentication. A missing `exp` is a reject, not "no
expiry". *Mutants: removing the compare breaks six assertions; treating an absent
`exp` as unlimited breaks one.*

⚠ **Correction to the reference:** its note that bayan's `base64url_decode` "did
not round-trip" does **not** reproduce against the folded bayan in `lib/`. Ours
exists for a different reason — bayan's encode/decode allocate on the
process-global no-free bump, and issue/verify run per request. The encoder is
cross-checked byte-for-byte against bayan's on every remainder class.

**`src/auth/perm.cyr` — a static role→permission table**, not `role >= N`. ⚠ An
ordering comparison makes the enum's numeric order load-bearing and grants
everything below an out-of-range value. *Mutant: the `>=` form grants READ to role
**-1** — which is exactly what `agnostic_users_role` and `agnostic_jwt_claim_role`
return for "no such identity".* A route nobody classified requires ADMIN.

**`src/auth/tenant.cyr` — tenancy.** Scoping is `"<tenant>:<key>"`, which is a
cross-tenant collision primitive unless the tenant key cannot contain the
separator: `acme` + `x:y` and `acme:x` + `y` would both produce `acme:x:y`.
Tenant keys are `[a-z0-9][a-z0-9-]*`, so the ambiguous tenant cannot be named —
asserted directly. *Mutant: letting `unscope` trust the first colon lets one
tenant read another's object.*

**`src/auth/authn.cyr` + the dispatch ladder — the rung itself.** Two schemes,
named explicitly (`Bearer`, `ApiKey`) and never sniffed from the credential's
shape. ⚠ **A verified JWT proves *who*, not *what*: the role and tenant are
re-read from the user row on every request.** That costs one indexed lookup and
buys instant revocation. *Mutant: trusting the role claim leaves a demoted user a
SUPER_ADMIN and lets a deleted account keep authenticating.*

⚠ **401 and 403 are kept distinct.** 401 is "I do not know who you are"; 403 is
"I know, and you may not". Collapsing them — a common hardening reflex — tells a
valid user with the wrong role to re-authenticate, which cannot help them.
*Mutant: disabling the rung turns a 401 into a 200 and a 403 into a 422, the
latter proving the handler had parsed a body it should never have seen.*

**Auth is off by default, and that is bounded rather than fail-open.** Nothing can
authenticate before an operator has provisioned a user and there is no bootstrap
route yet. What stops it being a hole: `agnostic_serve_mount` **refuses to start**
with `AGNOSTIC_AUTH` off on any bind but loopback, and says so on loopback.
`state.md` recorded loopback as the only thing standing in front of the crew
routes; that is now structural rather than incidental.

**`src/auth/ratelimit.cyr` — login-abuse controls.** Argon2id at ~244 ms makes
login a request-amplification lever. Two independent controls: the pool slot count
caps *concurrent* hashes, and a per-IP token bucket caps the *rate*. ⚠ **The
bucket is checked before any Argon2 work** — a limiter that sheds after hashing
has already paid the cost it exists to avoid. *Mutant: moving the check after the
verify is caught by asserting the Argon2 shed counter does not move, which a test
on the returned 429 alone would have missed.* The table is fixed-size, so memory
is bounded; the honest cost — an attacker rotating addresses evicts legitimate
entries — is stated in the module rather than glossed.

**`src/auth/webhook.cyr` — HMAC-SHA256 callbacks.** The signature covers
`"<ts>.<body>"`, not the body alone, because a bare body signature is replayable
forever. The timestamp is **inside** the MAC, so an old signature cannot be
re-stamped with a fresh one. *Mutant: signing the body alone lets exactly that
forgery through.* Freshness is checked before the MAC is computed.

**External IdP verification is additive, and enforced to be.** The validator runs
**only after local verification fails**, returns a **uid rather than a principal**
(so it cannot grant a role this deployment did not assign), and a uid with no
local row authenticates nobody. All three are asserted.

⚠ **A Cyrius note worth keeping:** `secret` is a **reserved keyword** and cannot
be a parameter name. The diagnostic attributes it to the previously-included
file, which sent the first search to the wrong module.

### Added — M5 (part 1), credential primitives on sigil

**54 assertions** in `tests/crypto.tcyr` across six groups (hex, digest, password,
malformed-record, pool, api-key); 825 total across 17 suites, 0 failed.

`src/auth/crypto.cyr` — Argon2id password hashing at the roadmap's parameters
(m=19456 KiB, t=2, p=1), API-key digests, and the cost budget.

- **The Argon2 buffer pool IS the concurrency cap.** sigil's convenience form allocates
  its own scratch and rules itself out (`fl_alloc` is not thread-safe), so
  `argon2id_into` with a caller-supplied buffer is the only correct entry point here —
  handlers run on sandhi pool workers. At 19.0 MiB per concurrent hash, one buffer per
  worker would be 304 MiB resident. A small fixed pool bounds the memory *and* sheds
  excess logins with 429 having done no Argon2 work — the amplification SecureYeoman
  measured was 8 concurrent attempts pushing `GET /health` from 6 ms to 942 ms.
- **The stored form carries its parameters** — `v1$<t>$<m>$<p>$<salt-hex>$<hash-hex>` —
  so raising `m_cost` later does not silently invalidate every existing password.
- Malformed records are **refused, not partially decoded**; the API-key path parses
  attacker-supplied hex.

### Added — M4 (part 2), a durable tamper-evident audit chain on libro

**35 assertions** in `tests/audit.tcyr`; 746 total across 15 suites, 0 failed.
Proven live: three events recorded, the process restarted, one byte of a recorded
detail edited on disk, and the restart reported `"intact": false, "bad_index": 1`
with an ERROR naming the entry.

`GET /api/v1/audit` reports the trail's state. Crew submit/cancel and definition
create/replace/delete each record an entry.

- **A streaming chain, not a retaining one.** libro's own comment is the reason:
  for a write-through consumer the retaining chain's entry vec "is pure
  accumulation ... A long-lived writer grew forever." Linkage is byte-identical,
  so the durable chain verifies the same.
- **Hash-linked, and not signature-backed — stated rather than implied.** libro's
  `audit_entries` table is `(id, ts, sev, src, act, det, aid, phash, hash, halg)`:
  there is **no signature column**, so `sign_entry` would compute a signature and
  `patrastore_append` would discard it. Computing security theatre is worse than
  not computing it. What that leaves undetected is named in the module header: an
  attacker who can write the file *and* recompute every hash forward.
- Still strictly better than the engine's own trail, which mints its key with
  `random_bytes` per start and keeps entries in memory — unverifiable across a
  restart, and gone when the process is.
- **Gaps are counted, because verification cannot see them.** A failed append
  leaves no hole to find, so `dropped` is on the endpoint beside `intact`. A
  chain reporting `intact: true` with a non-zero drop count has not told you
  everything.
- **A broken chain is loud, not fatal.** Refusing to start would let an attacker
  deny service by corrupting one byte and would take the evidence offline with it.

### Fixed — `patra_init` was silently resetting the log level

`patra_init`'s last line is an unconditional `sakshi_set_level(SK_WARN)`
(`lib/patra.cyr:4472`), so opening the database threw away whatever
`AGNOSTIC_LOG_LEVEL` had set — every INFO line in the process, including
`listening`. agnosai hit this, avoided patra entirely, and left a note for
"whoever does reach for patra later" (`lib/agnosai.cyr:29933`).

Saved and restored around the call in `agnostic_definitions_open`, so the wart
stays in the one module that triggers it. ⚠ **Worth fixing upstream** — a library
has no business setting its host's log level.

### Changed — audit verification runs at open, not per request

⚠ **A libro thread-safety limitation, found by it crashing the server.**
`patrastore_open` prepares its `SELECT` and `COUNT` statements once and caches
them in the store struct, and patra's SQL parse scratch is **per-thread**
(`patra_init`: "Install this (main/foreign) thread's TLS block so the per-thread
SQL parse scratch resolves"). Using those cached statements from a sandhi pool
worker kills the process — reproduced directly: `agnostic_audit_count()` succeeds
on the main thread and takes the worker down.

`src/engine/definitions.cyr` is unaffected because it calls `patra_prepare` on
the calling thread every time; libro's store does not.

So verification happens once, at open, on the main thread — which is also simply
the right moment, since the question a tamper-evident chain answers is "was this
altered while I was not running". Entry counts are maintained in-process rather
than queried. `GET /api/v1/audit` reports `"verified": "open"` so a client reading
`intact` knows *when* it was true. A live re-verify needs libro to stop sharing
prepared statements across threads.

### Added — M4 (part 1), agent definitions are durable in patra

**106 assertions** in `tests/agentdef.tcyr`; 711 total across 14 suites, 0 failed.
Verified live: a definition created in one process is served by a *different*
process after a restart, with its retained fields intact.

`patra` joins `[deps].stdlib` — it is folded into the toolchain stdlib rather
than being a `[deps.*]` block. New config: **`AGNOSTIC_DB_PATH`**, defaulting to
`agnostic.patra` relative to the working directory, with the resolved path logged
at mount.

- **The nine store functions kept their signatures**, so
  `src/routes/definitions.cyr` was not touched. That rule existed for exactly
  this moment. The one thing that moved on the wire is the `storage` literal:
  `"memory"` → `"patra"`.
- **The stored document is the wire form.** A definition is persisted as the JSON
  `agnostic_agent_def_to_value_a` renders and read back through
  `agnostic_agent_def_decode_a` — the same decoder that validates a client
  request. So there is no second serialiser to drift, a row that no longer
  decodes is caught rather than half-read, and `focus` / `allow_delegation`
  persist for free because they are in the wire form. The restart test asserts
  exactly that: `focus`, which the engine has no slot for, survives.
- **A decode cache, because there is still no `free()`.** Decoding per `GET`
  would leak from the global bump on every read. patra is authoritative for
  existence, `count` and `keys`; the cache only avoids re-decoding a document
  already read. ⚠ It assumes this process is the only writer — patra is
  flock-arbitrated and genuinely multi-process, so if that stops being true the
  cache has to go rather than be patched.
- **`AGNOSTIC_DEFINITIONS_MAX` changed meaning** from a store ceiling to a cache
  bound. M3 refused a create past it because memory had no `free()`; patra has no
  such limit, so creates now succeed past it and only caching stops. The suite
  asserts the new behaviour rather than the old.
- **A store that cannot open is a startup failure.** Accepting a definition
  against a database that is not there would lose it, which is worse than
  refusing to start.

⚠ **Two patra constraints confirmed by reading it, both real.** Exactly **one
index per table** — `SCH_IDX_COL` is a single slot in the schema page, and a
second `CREATE INDEX` replaces the first. And `COL_STR` is a fixed 256-byte slot,
so long values need `COL_TEXT`, which is chain-paged and **cannot be indexed or
used in `WHERE`**. Neither binds M4: definitions index on `dkey` and carry the
document as TEXT. The single-index limit will bind **M5**, where users need
lookup by both id and email.

Durability is configurable, contrary to the roadmap's shorthand:
`PATRA_SYNC_FULL` (fdatasync per mutating exec) is the default, but
`PATRA_SYNC_BATCH`, `patra_flush` and explicit `patra_begin`/`patra_commit`
transactions all exist.

### Added — M3 (part 2), agent definitions: one model, three dispositions

**97 assertions** in `tests/agentdef.tcyr`; 702 total across 14 suites, 0 failed.

A crew's `agents` array and a stored agent definition are the **same model**,
decoded by `agnostic_agent_def_decode_a` and by nothing else. `request.cyr` had a
second copy; two decoders for one concept is how the two ends drift, which is
`ORACLE-AUDIT.md` §3.3 restated at the level of a field.

`ORACLE-AUDIT.md` §2.2 lists fourteen fields the oracle dropped in translation.
Nothing here is dropped — every key a client can send has exactly one of three
fates, and the client can tell which:

- **FORWARDED** (12) — the engine has a slot that acts on it.
- **RETAINED** (2) — `focus` and `allow_delegation`, kept and round-tripped
  verbatim and **named in an `unforwarded` array** on every response carrying the
  definition. Membership was decided by one test: does the canonical preset
  library carry it? All 76 preset agents carry `focus`, 18 carry
  `allow_delegation`, and neither reaches the engine.
- **REFUSED** (12) — a 422 naming the missing capability, checked *before* the
  generic unknown-field arm so a real capability request never reads as a typo.
  `agent_key` is refused with a message pointing at `key`, because the oracle and
  the engine both spell it the other way. `hardware` is the one field refused
  despite the engine having a slot — the record is `ai-hwaccel`-shaped and
  Agnostic has no decoder for it.

Five CRUD routes, **201** for a definition against M2's 202 for a crew: a crew is
accepted work that is not finished, a definition is complete when the call
returns. **No upsert** in either direction — `POST` to an existing key is 409,
`PUT` to an absent one is 404 — because an upsert turns a typo'd key into a
second silently-created definition. **507**, not 503, when the store is full: 503
means the engine cannot act, and one of those faults is retriable after a delete.

The store is memory-resident, capped at 256, and **never evicts** — evicting a
definition the user named would 404 something they created. Disclosed by
`"storage": "memory"` on all five responses and a WARN at mount.

### Fixed — an unset GPU memory floor became a concrete 0

Found by live testing, not by the suite. The three GPU fields share one engine
setter, so `gpu_required` alone still writes all three — and passing 0 for the
unspecified floor overwrote the engine's `AGNOSAI_NO_LIMIT` sentinel, putting
`"gpu_memory_min_mb": 0` on the wire for a field the caller never sent. An
unspecified value acquiring a concrete one is the same class of defect as a
dropped field, in the opposite direction. Pinned by a regression assertion.

### Added — M3 (part 1), the canonical preset library

**71 assertions** in `tests/presets.tcyr`; 581 total across 13 suites, 0 failed.

18 documents, 76 agents, 38 distinct tool names. Checked in at `src/presets/*.json`
and embedded into `src/presets_data.cyr` by `scripts/gen-presets.sh` — Cyrius has
no `include_str!`, so a data file must be turned into source first. The generated
file is committed so a clone builds without the generator, and `check-clean.sh`
runs `--check` so that copy cannot go stale.

- **Parsed once at mount.** `agnosai_builtin_presets()` re-parses all eighteen on
  every call, `agnosai_preset_from_value` allocates from the no-`free()` global
  bump, and the engine has no name lookup at all — no `agnosai_preset_find`,
  `_get` or `_by_name` exists. A parse shortfall **refuses to start**.
- **`GET /api/v1/presets` returns summaries**, and `GET /api/v1/presets/{name}` the
  whole document, served as parsed rather than copied. The library is 61,412 bytes
  against a 65,536-byte arena that spills into the global bump, so a full-document
  listing would leak on every call. Measured live: listing 4,416 B, largest
  document 7,064 B — the default arena was left unchanged on that evidence.
- **Read-only.** A write earns a 405 naming the mismatch, not a 404 claiming the
  collection does not exist. Durable presets are M4's.

### Added — `src/app.cyr`, so adding a route stops breaking every suite

The include order lived in `src/main.cyr` and every suite reaching the router
reproduced it — so a new route module failed them all with "undefined function"
rather than "missing include", three times across M2 and M3. `main.cyr` cannot
serve that role itself: its two trailing top-level statements run at include time
and would start a server inside a suite.

### Changed — `check-clean.sh` skips lint for files marked `GENERATED FILE`

Exactly one file qualifies. `src/presets_data.cyr` has lines over 120 characters
that cannot be avoided: a single JSON atom — a `backstory` — runs to 442
characters, and the wrapper must not split inside one because a Cyrius line
continuation **keeps the newline** (verified: `"abc\<newline>def"` is 7 bytes, not
6) and a raw newline inside a JSON string is illegal JSON. Cyrius has no C-style
adjacent-literal concatenation to split it with, and `#skip-lint` is scoped to a
line, so it cannot be placed on an offending line that sits inside a literal.

The length is a property of the documents, not of anyone's style. The file is
still covered by `fmt`, `doc`, the compiler, `gen-presets.sh --check`, and
`tests/presets.tcyr` — 17 human-authored files are still linted.

### Fixed — `gpu_strict` is refused by name, and it is not `gpu_required`

A correction to M2's own comments, found while opening M3. `gpu_strict` and `gpu_required` are
**different fields**: the oracle declares both (`agents/base.py:61-62`) and hard-fails only on
`gpu_required AND gpu_strict` (`config/gpu_scheduler.py:196`). `required` asks for a GPU; `strict`
says fail rather than fall back to CPU. M2's comments claimed `gpu_required` was `gpu_strict`'s
counterpart — it is not, and believing that would leave a reader thinking hard-fail was covered.

⚠ **The Cyrius engine cannot express strictness at all** — `gpu_strict` appears zero times in
`lib/agnosai.cyr`, `agnosai_agent_with_gpu` takes only (required, preferred, memory_min_mb), and
`agnosai_agent_hardware_requirement` builds accelerators plus a memory floor with no fallback flag.

So it is refused, and now refused **with its own message** naming the missing capability rather than
falling to the generic "unknown field", which reads like a typo. A caller who needs hard-fail learns
the platform cannot do it. The alternative — mapping it onto `gpu_required` — would reinstate exactly
the silent CPU fallback `ORACLE-AUDIT.md` §3.11 records.

### Added — M2, the crew surface: submit, poll, cancel, progress

**267 new assertions across 4 suites** (496 total across 12), 0 failed. All three gates green.
Verified live over a socket, not only under test.

AgnosAI is linked **in-process**, so there is no transport here — no client, no URL, no retry
policy. That removes a whole class of the oracle's defects by construction and leaves the ones that
were never about transport.

- **`src/engine/outcome.cyr`** — the result type the milestone turns on. Carries status **and**
  error **and** the engine-assigned crew id **and** the result set. The oracle's `BackendResult`
  had a `.status` that **no caller anywhere in the codebase read**.
- **`src/engine/ledger.cyr`** — what Agnostic remembers about the crews it submitted, and where a
  terminal status is latched.
- **`src/engine/request.cyr`** — one task model, allow-list decoded, dependency graph validated.
- **`src/engine/crew.cyr`** — the orchestrator bridge: submit, poll, cancel.
- **`src/routes/crews.cyr`** — `POST /api/v1/crews` (**202**), `GET /api/v1/crews/{id}`,
  `POST /api/v1/crews/{id}/cancel`, `GET /api/v1/crews/{id}/events`.

**202-then-poll**, not the engine's inline shape. `agnosai_route_create_crew_a` calls the blocking
`agnosai_orchestrator_run_crew` to keep parity with its Rust oracle, so a `POST` holds a worker for
the whole run. Agnostic submits and returns the id.

### Fixed — the four `ORACLE-AUDIT.md` §3 defects, designed out rather than avoided

- **§3.1 — a failed crew reported as completed.** `_agnostic_outcome_normalise` demotes a
  COMPLETED-with-no-results to FAILED *before* the record exists, so the vacuous success is never
  observable. ⚠ **This is not a Python-ism.** `agnosai_crew_runner_run` sets `COMPLETED` and only
  downgrades inside a loop over `results` — over an empty set the loop body never runs and the
  status stands. `all([])` in Cyrius, one dependency away.
- **§3.2 — cancel addressing an id the engine never saw.** Every id originates in
  `agnosai_crew_new`. Agnostic mints none, so there is no local UUID to substitute. A refusal from
  the engine is **returned, not discarded**, and the ledger is not relabelled.
- **§3.3 — two structurally different task models.** `tasks` is required and non-empty, there is no
  fallback path, and an unlisted key is a 422 naming it. The oracle's fallback fired on every
  request because its model declared no `tasks` field at all.
- **§3.4 — a terminal state overwritten by a later, wronger one.** `agnostic_ledger_latch` refuses
  to write over a terminal status — in one guard, at the only place a status is stored.

### Fixed — two engine behaviours that only bite the async path

Neither is in the 86 audited oracle defects; both were found building M2.

- **A cyclic DAG submitted asynchronously reports `pending` forever.**
  `agnosai_crew_runner_run` returns 0 on exactly one arm, and `_agnosai_orch_finish_err` then
  returns **without touching the crew map** — which `_agnosai_orch_register` has already seeded with
  PENDING. The blocking caller sees the 0; `_agnosai_orch_submit_thread` discards it. Closed at the
  front door: `agnostic_crew_req_has_cycle` rejects the graph before submission, so the arm is
  unreachable through Agnostic.
- **A finished crew can be evicted and then 404.** `_agnosai_orch_evict_locked` drops **every**
  finished crew once the registry holds 1000, so a successful run becomes indistinguishable from a
  typo'd id. The ledger answers from its own latched outcome; `AGNOSTIC_LEDGER_MAX` is deliberately
  above the engine's cap, and a suite asserts that ordering.

### Added — placeholder mode is disclosed, because nothing else can distinguish it

With no `AGNOSTIC_LLM_URL`, `agnosai_execute_task` takes its `client == 0` arm and
`_agnosai_crew_placeholder_result` echoes the task description back as output with status
`COMPLETED`. A crew of echoes therefore normalises to `completed`, every task complete — and **no
property of the result type can tell it from real model output**.

Closed by disclosure rather than by type: `engine_mode` is on every submit and poll response, and
mount logs a WARN.

### Removed — `AGNOSTIC_CREW_MAX_CONCURRENT_TASKS`, a knob that did nothing

Verified against the bundle: `agnosai_resource_budget_max_concurrent_tasks` has no reader outside
its own accessor and the budget serialiser, and `agnosai_orchestrator_budget` has **zero** call
sites. The field is stored, serialised, and enforced by nothing. Shipping it would have sold an
operator a concurrency ceiling that does not exist. `AGNOSTIC_CREW_TIMEOUT_SECS` is kept because
`max_duration_secs` genuinely *is* read, by `agnosai_orchestrator_timeout_secs`.

The ceiling that does work is per-request `max_concurrency` on process `parallel` — which is
accepted only alongside `parallel`, because a field that is accepted and then has no effect is the
same defect in miniature.

### Added — `scripts/check-log-lengths.py`, after two silent miscounts shipped

sakshi takes `(pointer, length)` pairs, so every log message's byte count is hand-written and
nothing checked it. Both failure modes are silent, and both were in one commit: one call declared
76 for a 75-byte message and shipped the **NUL terminator inside a JSON string**; another declared
45 for 46 and **truncated** the message by a character. Not a compile error, not a lint warning, and
invisible to suites that assert on handler behaviour rather than log text.

Wired into `check-clean.sh`. Mutation-verified: changing any declared length by one fails it.

### Changed — `check-symbols.sh` rule 3 now scans enum members on both sides

It compared only `^(fn|var)` against `lib/`. Cyrius enum qualifiers are **cosmetic** — `Backend.WASM`
and `KavachBackend.WASM` both resolve to the bare member `WASM` — so a `src/` enum member colliding
with a `lib/` one silently replaced it for the whole program, with no diagnostic from compiler or
linter. That is the same mechanism as the `BACKEND_COUNT` memory-safety defect below, in the one
declaration kind the gate did not cover. M2 adds ~50 enum members; all verified collision-free.

Mutation-verified: injecting a member named `AGN_CREW_ID` fails the gate, naming both sites.

### Added — a mount-time warning where the two size ceilings interact

A request body is parsed into the per-request arena, whose exhaustion policy is `ARENA_FULL_SPILL` —
overflow is satisfied from the global bump, which has **no `free()`**. The defaults make this
reachable (64 KiB arena, 1 MiB body limit), and the engine's own caps admit several megabytes of
entirely legal crew request. Not a startup failure, since the safe configuration depends on the
deployment; an operator gets a warning naming the arena size.


### Changed — agnosai 2.0.3 → 2.0.4, closing a memory-safety defect in this binary

Agnostic is the binary where the defect actually lived, because Agnostic is what links kavach and
ai-hwaccel together — transitively, through agnosai.

Both libraries defined `var BACKEND_COUNT`, 10 and 18. Cyrius has one flat symbol namespace with
last-definition-wins and is **silent** on a duplicate `var`, so the constant resolved to **18** while
kavach used it as the bounds check in `_backend_fp` over a **10-slot** table (`_backend_table[320]`
at `BACKEND_SLOT_SIZE = 32`). The guard admitted ids 0–17; `_backend_slot(17)` sits at byte 544, 224
bytes past the end, and `backend_dispatch_exec` then calls the result as a function pointer.
Renamed upstream to `KAVACH_BACKEND_COUNT` / `AIHW_BACKEND_COUNT` in kavach 3.11.15 and
ai-hwaccel 2.3.18, which agnosai 2.0.4 folds.

### Added — `tests/deps_symbols.tcyr`, a guard for the class rather than the instance

**14 assertions.** The instance is fixed upstream; this suite exists because *nothing caught it*.
The compiler warns on a duplicate `fn` and is silent for `var`, and every `check-symbols.sh` in the
ecosystem — including this repo's — scans `src/` only. A collision between two dependencies inside
`lib/` is therefore invisible to the compiler and the linter simultaneously, and Agnostic is the
repo where such a collision lands.

The suite pins both counts as distinct values, ties kavach's guard to its table's real slot count,
and records the out-of-bounds arithmetic the old value produced. Mutation-tested: three mutants —
restoring 18, resizing the table to 18 slots, and drifting an enum member — each killed.

⚠ It also pins the enum *members* (`PROCESS`, `WASM`, `OCI`, `NOOP`), because in Cyrius an enum
qualifier is **cosmetic** — `Backend.WASM` and `KavachBackend.WASM` both resolve to the member
`WASM`, asserted here directly. The upstream type rename therefore protected nothing on its own;
those members remain generic and unprefixed, and a future library defining `WASM` would collide the
same silent way.

### Fixed — `lib/vani.cyr` did not match the pinned toolchain snapshot

Pre-existing and unrelated to the dep bump: the vendored copy matched **no** installed toolchain, so
`scripts/check-clean.sh` failed at HEAD. `vani` is not in `[deps].stdlib` and `src/` has zero
references to it, but the snapshot check requires every file in the pinned snapshot to be present
*and* byte-identical, so removing it would fail too. Re-synced from the 6.5.32 snapshot.

⚠ Provisioning was done with the **pinned** toolchain binary rather than the PATH wrapper, which had
drifted to 6.5.33. `lib sync` and `deps` provision from the *installed* toolchain, not the manifest
pin, so syncing under drift is how a lock that CI cannot reproduce gets written.

### Added — M1, the HTTP foundation

The first milestone where untrusted bytes reach a buffer. **215 assertions across 7 suites**, 0
failed; all CI gates green. Verified live over a socket, not only under test.

- **`src/config.cyr`** — environment config, strictly parsed. A malformed value **refuses to start**
  rather than silently defaulting, because an operator discovering in production that
  `AGNOSTIC_PORT` never applied is worse than a startup failure that names the problem.
- **`src/strcase.cyr`** — ASCII case folding. The stdlib has no case-insensitive compare and
  `str_lower_cstr` allocates; comparing an env value to a literal should not.
- **`src/trace.cyr`** — thread-local W3C trace ids. sakshi's is a process global, so under a worker
  pool concurrent requests would overwrite each other's id and misattribute every log line.
- **`src/log.cyr`** — sakshi emit hook rendering one JSON object per event, formatter split out as a
  pure function so tests assert bytes without a pipe.
- **`src/http/{status,response,codec,router}.cyr`** — status vocabulary, handler return type,
  allow-list decoding, route table with a `:name` matcher.
- **`src/routes/health.cyr`** — `/health` liveness and `/ready` readiness with a check registry.
- **`src/server/serve.cyr`** — the sandhi adapter: arena/SPILL wiring, cstring→`Str` boundary,
  `signalfd` graceful shutdown.

### Decisions

- **ADR 0001** — health and readiness are separate probes. The oracle's `/health` pings Redis and
  RabbitMQ and 503s when they are down; under an orchestrator that manufactures an outage, since one
  Redis blip fails liveness on every replica and restarting cannot fix a dependency.
- **ADR 0002** — Daimon Tier 1 deferred. It cannot be implemented as written: daimon serves no agent
  heartbeat route, and registration for an externally-started process keys supervisor maps to pid 0.
  Zero first-party projects perform it at runtime, including the one the standard names as canonical.
- All six open port decisions closed — identity (own it thin, adapted from SecureYeoman's Cyrius
  probe), preset canon (Agnostic's is canonical), PDF (wait for `bayan_pdf_*`), release shape (one
  total release), Daimon (deferred), MCP transports (both shapes stand, on merit).

### Fixed — three oracle defect classes designed out, each locked by a mutation-tested assertion

- **Silent config fallback.** The oracle reused its u16 port parser for a rate limit, so any value
  above 65535 fell back to the default with no error. `parse_bounded` is deliberately a separate
  function; aliasing it back to `parse_port` fails two named assertions.
- **`extra='ignore'` field dropping.** Pydantic silently discarded 14 fields including `gpu_strict`,
  turning a hard-fail GPU requirement into a silent CPU fallback, and elsewhere ate an entire
  `tasks` array. Replacing the allow-list check with `return 1` fails
  *"an unlisted field is rejected, not silently dropped"*.
- **Liveness conflated with readiness.** See ADR 0001. The suite asserts `/health` stays 200 with a
  failing dependency registered.

### Fixed — two upstream defects avoided that the reference implementation still has

- `GET /health?probe=1` returns 200. AgnosAI never strips the query string, so its own health
  endpoint 404s for any caller appending a cache-buster.
- `/ready` reports a version **derived** from `${file:VERSION}`. AgnosAI hardcodes its equivalent and
  has reported 1.1.0 since shipping 2.0.x.

### Filed upstream

- `cyrius 2026-08-20-pkgver-not-visible-in-included-files` — `CYRIUS_PKG_VERSION` resolves only in
  the entry file's own text; any `include`d file referencing it fails to compile. That is where the
  symbol is least useful, since `/version` and `/ready` handlers live in modules. Worked around by
  threading it from `main.cyr` at mount, so the version stays derived rather than hardcoded.

## [0.1.0]

### Hardening — P(-1) pass complete

`first-party-standards.md:817` requires the audit-and-tighten pass before any feature work: *"Build
features on an unaudited foundation and every feature inherits the foundation's shortcuts."*
Exit criteria per `:869` all met — audit-clean, fmt/lint/vet/deny clean, security clean, baseline
benchmarks captured.

- `docs/audit/2026-08-20-audit.md` — the eight-point security process worked against the code that
  exists rather than the code that is planned. **0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW**, both LOW
  closed in the pass. Six of the eight points are N/A on a 34-line scaffold with no external input,
  no buffers, no file handling and no subprocess execution — so each N/A row records **which
  milestone re-opens it**, making the document a checklist for M1–M9 rather than a one-time
  clearance.
- `scripts/bench-history.sh` — written to the full four-clause contract at
  `first-party-standards.md:443-447`. The sibling implementation drops two of them: it records no
  commit hash (so a row cannot be attributed to code, defeating the point of a history trail) and
  emits no Markdown table. This one writes `date,version,commit,branch,benchmark,time_ns` and
  regenerates `BENCHMARKS.md` with human-readable units.
- Baseline captured — `noop` at 2 ns. This is the starting line for the 3-point
  baseline → optimized → current trend.

### Fixed — LOW-1, unprefixed globals in the generated harnesses

`cyrius init` emitted `var r = main();` into the bench and fuzz harnesses and `var exit_code` into
the test suite. Cyrius has one flat symbol table with last-definition-wins, and a test binary links
all of `lib/`, which exports ~180 unprefixed names.

Verified *not* currently exploitable — `lib/` declares no single-letter or `exit_code` globals — so
this was latent, not live. But the dependency set is about to grow by six packages, and the same
class caused a real upstream incident (four duplicated enum constants, three with different values,
three of them struct sizes passed straight to `alloc()`). Renamed to `_agnostic_{bench,fuzz,test}_exit_code`.

LOW-2 (exit-code masking in `.bcyr`/`.fcyr`, which do not clamp `& 0xFF` the way the `.tcyr` does)
was assessed and **accepted without a code change**: neither harness returns a failure count, so no
path to a value ≥256 exists. Recorded so the first harness returning a count adds the clamp.

### Added — roadmap through v1.0

`docs/development/roadmap.md` replaced its placeholder milestones with M0–M9 in dependency order,
each carrying its gates, its prerequisite repos, and the audit points it re-opens. Three decisions
are marked open and one milestone (M5, identity) is explicitly **blocked** on the user answering
it — per `cyrius/CLAUDE.md:66`, that is settled before the milestone opens rather than discovered
inside it.

### Added
- Initial project scaffold, generated by `cyrius init --language=none .` against
  the Cyrius 6.5.32 toolchain. The Python implementation is retained at
  `python-port/` as a behavioural oracle and is never built or shipped —
  see `ORACLE-AUDIT.md` for the 86 verified defects in it.
- Root docs the scaffolder does not emit: `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`. `SECURITY.md` is written for Agnostic's
  own surface (inbound API, delegated execution, targets under test, stored
  artefacts, credentials) rather than adapted from a sibling.
- `scripts/check-symbols.sh` and `scripts/check-clean.sh`, adapted from AgnosAI.
  Two inherited assumptions had to be removed: a `gen-presets.sh` generated-source
  check for a file this repo does not have, and a `deps --verify` step that
  assumed a lockfile — Agnostic declares no git deps yet, and
  `first-party-standards.md:135` makes "no lockfile" the documented default. The
  lock check re-arms automatically once a `[deps.NAME]` block appears.
- `[release]` manifest section declaring `bins` and `cross_bins`.

### Changed — CI raised to the first-party standard

The scaffolded `ci.yml` had a single 4-step job. It now carries the three jobs
`first-party-standards.md:364-386` requires — `build`, `security`, `docs` — with
fmt/lint/vet/deny via `check-clean.sh`, the symbol gate, a DCE build, ELF
verification, an aarch64 cross-build, and `cyrius bench` behind
`continue-on-error`.

`release.yml` gained the aarch64 build, made fatal rather than skipped: the
standard's DON'T list (`:963`) names "release without aarch64 builds" explicitly,
and a tagged release that silently ships one architecture is the failure that
guards against. Both binaries are now checksummed and attached, along with
benchmark results per `:419`.

⭐ **New gate: toolchain drift is fatal.** `cyrius lib sync --full` and
`cyrius deps` provision from the *installed* toolchain, not the manifest pin, so
a developer whose wrapper has drifted ahead writes a `lib/` and `cyrius.lock`
describing a version CI will never install — and every local build stays green
because the polluted lib agrees with the polluted lock. This is exactly how
AgnosAI 2.0.2 reached main with a 6.5.30-shaped lock under a 6.5.27 pin and lost
the entire stdlib in CI. The CLI already prints
`manifest-pin: X (drift — wrapper is Y)`; this treats that line as fatal in both
workflows. Mutation-verified in both directions: injecting a pin mismatch fails
the gate, restoring it passes.

Relatedly, the lockfile step **fails** on a mismatch rather than emitting a
`::notice` and continuing, which is what let the bad lock through upstream.

### Fixed
- The scaffolder's generated entry point declared `var r = main();` — a bare
  unprefixed top-level global in Cyrius's single flat symbol table.
  `check-symbols.sh` failed on it immediately; renamed `_agnostic_exit_code`.
  Filed against the toolchain rather than patched, together with the missing
  scaffold files and the absent `--language=python` port mode:
  `cyrius/docs/development/issues/2026-08-20-cyrius-port-language-python.md`.
