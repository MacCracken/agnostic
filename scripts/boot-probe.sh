#!/usr/bin/env bash
# boot-probe.sh — start the real binary, talk to it over a real socket, stop it, start it again.
#
# WHAT IT GUARDS. The suites drive handlers through socketpairs, so nothing in them listens,
# binds, takes a signal or restarts. That is where the bind failure 0.2.2 fixed lived: every suite
# passed while a server that could not bind said nothing and exited 0. CI's `help` and `api schema`
# steps exit without serving, so before this no step ever served a request.
#
# Usage: scripts/boot-probe.sh [binary]      default build/agnostic
#        AGNOSTIC_PROBE_PORT=18731           the port to use
set -uo pipefail

BIN="${1:-build/agnostic}"
PORT="${AGNOSTIC_PROBE_PORT:-18731}"
WORK="$(mktemp -d)"
BASE="http://127.0.0.1:${PORT}"
PID=""

cleanup() {
  [ -n "$PID" ] && kill -KILL "$PID" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() {
  echo "boot-probe: FAIL: $1" >&2
  for log in "$WORK"/*.log; do
    [ -f "$log" ] && { echo "--- $log" >&2; tail -20 "$log" >&2; }
  done
  exit 1
}

[ -x "$BIN" ] || fail "$BIN is not an executable"

# start <log name> <db name>: AGNOSTIC_ADDR is loopback, so a CI runner exposes nothing.
start() {
  AGNOSTIC_ADDR=127.0.0.1 AGNOSTIC_PORT="$PORT" AGNOSTIC_AUTH=off \
    AGNOSTIC_DB_PATH="$WORK/$2.patra" AGNOSTIC_AUDIT_PATH="$WORK/$2-audit.patra" \
    "$BIN" > "$WORK/$1.log" 2>&1 &
  PID=$!
}

status_of() { curl -s -m 10 -o "$WORK/body" -w '%{http_code}' "$@" || true; }

wait_up() {
  local i=0
  while [ "$i" -lt 100 ]; do
    [ "$(status_of "$BASE/health")" = "200" ] && return 0
    kill -0 "$PID" 2>/dev/null || fail "the server exited before it answered"
    sleep 0.1
    i=$((i + 1))
  done
  fail "/health did not answer 200 within 10 s"
}

expect() {
  local want="$1" what="$2"
  shift 2
  local got
  got="$(status_of "$@")"
  [ "$got" = "$want" ] || fail "$what: got $got, wanted $want: $(head -c 200 "$WORK/body")"
  echo "  ok: $what ($got)"
}

# stop: SIGTERM, then the exit status the stop gave. A stop that hangs fails the probe.
stop() {
  kill -TERM "$PID" || fail "the server was gone before SIGTERM"
  local i=0
  while kill -0 "$PID" 2>/dev/null; do
    [ "$i" -lt 300 ] || fail "SIGTERM did not stop the server within 30 s"
    sleep 0.1
    i=$((i + 1))
  done
  local rc=0
  wait "$PID" || rc=$?
  PID=""
  [ "$rc" -eq 0 ] || fail "a graceful stop exited $rc, not 0"
  echo "  ok: SIGTERM stopped it, exit 0"
}

echo "boot-probe: $BIN on port $PORT"
start first store
wait_up
expect 200 "GET /health" "$BASE/health"
expect 200 "GET /ready" "$BASE/ready"
expect 200 "GET /api/v1/presets" "$BASE/api/v1/presets"
expect 200 "GET /ui/" "$BASE/ui/"
grep -q '<html' "$WORK/body" || fail "/ui/ did not serve the page"
expect 404 "an unknown route" "$BASE/no/such/route"

# A second server on the same port must say so and exit non-zero. It has its own store, so the
# store's lock is not what stops it.
SECOND=0
AGNOSTIC_ADDR=127.0.0.1 AGNOSTIC_PORT="$PORT" AGNOSTIC_AUTH=off \
  AGNOSTIC_DB_PATH="$WORK/other.patra" AGNOSTIC_AUDIT_PATH="$WORK/other-audit.patra" \
  timeout -k 5 30 "$BIN" > "$WORK/second.log" 2>&1 || SECOND=$?
[ "$SECOND" -ne 0 ] || fail "a server that could not bind exited 0"
[ "$SECOND" -ne 124 ] || fail "a server that could not bind kept running"
grep -q 'server failed' "$WORK/second.log" || fail "a server that could not bind did not say so"
echo "  ok: a port in use is refused, exit $SECOND"

BODY='{"name":"probe","agents":[{"key":"a","role":"r","goal":"g"}],"tasks":[{"description":"one"}]}'
expect 202 "POST /api/v1/crews" -X POST -H 'Content-Type: application/json' -d "$BODY" "$BASE/api/v1/crews"
CREW="$(sed -E 's/.*"crew_id":"([0-9a-f-]+)".*/\1/' "$WORK/body")"
[ "${#CREW}" -eq 36 ] || fail "no crew_id in the reply: $(head -c 200 "$WORK/body")"
expect 422 "a crew with an unknown field" -X POST -H 'Content-Type: application/json' \
  -d '{"name":"probe","no_such_field":1}' "$BASE/api/v1/crews"
i=0
while :; do
  expect 200 "GET the crew" "$BASE/api/v1/crews/$CREW" > /dev/null
  grep -q '"status":"completed"' "$WORK/body" && break
  [ "$i" -lt 100 ] || fail "the crew did not complete within 10 s: $(head -c 200 "$WORK/body")"
  sleep 0.1
  i=$((i + 1))
done
echo "  ok: the crew completed"
stop

# The same store, from a new process: what the first one wrote, and its audit chain.
start second-run store
wait_up
expect 200 "the crew, from the store" "$BASE/api/v1/crews/$CREW"
grep -q '"status":"completed"' "$WORK/body" || fail "the stored crew reads $(head -c 200 "$WORK/body")"
expect 200 "GET /api/v1/crews" "$BASE/api/v1/crews"
grep -q "$CREW" "$WORK/body" || fail "the listing does not hold the stored crew"
expect 200 "GET /api/v1/audit" "$BASE/api/v1/audit"
grep -q '"intact"' "$WORK/body" || fail "the audit chain is not intact: $(head -c 200 "$WORK/body")"
stop

# Authentication on: what a signing secret does across a restart, which no suite can see.
SECRET_A=0123456789abcdef0123456789abcdef
SECRET_B=fedcba9876543210fedcba9876543210

# start_auth <log name> <jwt secret>
start_auth() {
  AGNOSTIC_ADDR=127.0.0.1 AGNOSTIC_PORT="$PORT" AGNOSTIC_AUTH=required \
    AGNOSTIC_BOOTSTRAP_EMAIL=probe@example.com AGNOSTIC_BOOTSTRAP_PASSWORD=probe-password-12 \
    AGNOSTIC_JWT_SECRET="$2" \
    AGNOSTIC_DB_PATH="$WORK/auth.patra" AGNOSTIC_AUDIT_PATH="$WORK/auth-audit.patra" \
    "$BIN" > "$WORK/$1.log" 2>&1 &
  PID=$!
}

SHORT=0
AGNOSTIC_ADDR=127.0.0.1 AGNOSTIC_PORT="$PORT" AGNOSTIC_AUTH=required \
  AGNOSTIC_JWT_SECRET=too-short \
  AGNOSTIC_DB_PATH="$WORK/short.patra" AGNOSTIC_AUDIT_PATH="$WORK/short-audit.patra" \
  timeout -k 5 30 "$BIN" > "$WORK/short.log" 2>&1 || SHORT=$?
[ "$SHORT" -ne 0 ] || fail "a short AGNOSTIC_JWT_SECRET exited 0"
[ "$SHORT" -ne 124 ] || fail "a short AGNOSTIC_JWT_SECRET started a server"
grep -q 'invalid configuration' "$WORK/short.log" || fail "a short secret was not named as configuration"
grep -q 'too-short' "$WORK/short.log" && fail "the refused secret reached the log"
echo "  ok: a short secret is refused, exit $SHORT"

start_auth auth-first "$SECRET_A"
wait_up
expect 401 "a route without a token" "$BASE/api/v1/presets"
expect 200 "login" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"
[ "${#TOKEN}" -gt 40 ] || fail "no token in the reply: $(head -c 200 "$WORK/body")"
expect 200 "a route with it" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/presets"
stop
grep -q "$SECRET_A" "$WORK"/auth-first.log && fail "the signing secret reached the log"

start_auth auth-second "$SECRET_A"
wait_up
expect 200 "the token, after a restart on the same secret" -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/v1/presets"
stop

start_auth auth-third "$SECRET_B"
wait_up
expect 401 "the token, after a restart on another secret" -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/v1/presets"
expect 200 "login, for the recovery below" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"

# Recovery: it needs the server stopped, reads the password from stdin, and what it sets is what
# login then takes. Only a real second process can meet the first's claim on the database.
recover() {
  printf '%s\n' "$1" | AGNOSTIC_DB_PATH="$WORK/auth.patra" AGNOSTIC_AUDIT_PATH="$WORK/auth-audit.patra" \
    "$BIN" admin reset-password "$2" > "$WORK/recover.log" 2>&1
}
NEW_PW=recovered-password-34
HELD=0
recover "$NEW_PW" probe@example.com || HELD=$?
[ "$HELD" -eq 1 ] || fail "a reset beside a running server exited $HELD, not 1"
grep -q 'a server is running' "$WORK/recover.log" || fail "the reset did not say a server is running"
echo "  ok: a reset refuses beside a running server"
stop

# A token's `iat` is in seconds, so the reset has to land in a later one to end it.
sleep 1
UNKNOWN=0
recover "$NEW_PW" nobody@example.com || UNKNOWN=$?
[ "$UNKNOWN" -eq 1 ] || fail "a reset for an unknown email exited $UNKNOWN, not 1"
recover "$NEW_PW" probe@example.com || fail "the reset failed: $(cat "$WORK/recover.log")"
grep -q "$NEW_PW" "$WORK/recover.log" && fail "the password reached the command's output"
echo "  ok: the reset set a password, stopped server"

start_auth auth-fourth "$SECRET_B"
wait_up
expect 401 "the old password" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
expect 401 "a token from before the reset" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/presets"
expect 200 "the new password" -X POST -H 'Content-Type: application/json' \
  -d "{\"email\":\"probe@example.com\",\"password\":\"$NEW_PW\"}" "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"
expect 200 "the trail" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/audit/entries"
grep -q 'auth.password.reset' "$WORK/body" || fail "the trail does not hold the reset"
grep -q "$NEW_PW" "$WORK/body" && fail "the trail holds the password"
stop

echo "boot-probe: OK"
