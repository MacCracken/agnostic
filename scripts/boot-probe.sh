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

GATEWAY=""

cleanup() {
  [ -n "$PID" ] && kill -KILL "$PID" 2>/dev/null
  [ -n "$GATEWAY" ] && kill -KILL "$GATEWAY" 2>/dev/null
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

# Each page's policy names the scripts of the page as a browser receives it, and no others (0.4.4,
# ADR 0039): the server takes those hashes from its own bytes at mount, so this takes them again from
# outside, over the socket, with another reader. A wrong one would be a view that opens blank.
for page in swarm crews library users audit; do
  expect 200 "switch on $page" -X PUT -H 'Content-Type: application/json' -d '{"enabled":true}' \
    "$BASE/api/v1/plugins/$page" > /dev/null
done
python3 - "$BASE" <<'PY' || fail "a page's policy does not name its scripts"
import base64, hashlib, re, sys, urllib.request

for path in ["/ui/"] + ["/ui/plugins/" + p for p in ("swarm", "crews", "library", "users", "audit")]:
    with urllib.request.urlopen(sys.argv[1] + path, timeout=10) as r:
        csp, body = r.headers["Content-Security-Policy"], r.read()
    scripts = re.findall(rb"<script(?:\s[^>]*)?>(.*?)</script\s*>", body, re.S | re.I)
    want = ["'sha256-%s'" % base64.b64encode(hashlib.sha256(s).digest()).decode() for s in scripts]
    got = re.search(r"script-src ([^;]*);", csp).group(1).split(" ")
    if not want or got != want:
        sys.exit("%s: its %d script(s) are not what script-src names: %s" % (path, len(want), got))
print("  ok: all six policies name their pages' scripts")
PY

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

# ⭐ A live crew. Nothing else here runs one: with no gateway the engine takes its placeholder path,
# and checks nothing (ADR 0033).
GATEWAY_PORT=$((PORT + 1))
python3 "$(dirname "$0")/fake-gateway.py" "$GATEWAY_PORT" & GATEWAY=$!
AGNOSTIC_TARGET_HOSTS=127.0.0.1 AGNOSTIC_LLM_URL="http://127.0.0.1:$GATEWAY_PORT" start live live
wait_up

# live_crew <what the task says> <rest of the crew>: its document, in $WORK/body, once it has ended.
live_crew() {
  local shape='"output_schema":{"type":"object","required":["verdict"]}'
  local body="{\"name\":\"live\",${LIVE_TARGET:-}\"agents\":[{\"key\":\"a\",\"role\":\"r\",\"goal\":\"g\"${LIVE_TOOLS:-}}],$2}"
  body="${body//SHAPE/$shape}"
  body="${body//SAY/$1}"
  expect 202 "a live crew: $1" -X POST -H 'Content-Type: application/json' -d "$body" "$BASE/api/v1/crews" > /dev/null
  local id
  id="$(sed -E 's/.*"crew_id":"([0-9a-f-]+)".*/\1/' "$WORK/body")"
  local i=0
  while :; do
    expect 200 "the live crew" "$BASE/api/v1/crews/$id" > /dev/null
    grep -qE '"status":"(pending|running)","task_count"' "$WORK/body" || break
    [ "$i" -lt 100 ] || fail "a live crew did not end within 10 s"
    sleep 0.1
    i=$((i + 1))
  done
}

ONE='"tasks":[{"description":"SAY",SHAPE}]'
live_crew say-prose "$ONE"
grep -q '"status":"failed","task_count"' "$WORK/body" || fail "a task that never met its shape did not fail: $(head -c 300 "$WORK/body")"
grep -q '"output_valid":false' "$WORK/body" || fail "and does not say so: $(head -c 300 "$WORK/body")"
grep -q 'output failed validation' "$WORK/body" || fail "and does not say why: $(head -c 300 "$WORK/body")"
grep -q '"total_tokens":45' "$WORK/body" || fail "all three calls were not billed: $(head -c 400 "$WORK/body")"
echo "  ok: a task that never met its shape failed, says so, and billed all three calls"

live_crew say-fenced "$ONE"
grep -q '"status":"completed","task_count"' "$WORK/body" || fail "a fenced answer did not pass: $(head -c 300 "$WORK/body")"
grep -q '"output_valid":true' "$WORK/body" || fail "and does not say so: $(head -c 300 "$WORK/body")"
grep -q '```' "$WORK/body" && fail "the fence reached the output: $(head -c 300 "$WORK/body")"
echo "  ok: a fenced answer passed, and its output is the block alone"

live_crew say-late "$ONE"
grep -q '"output_valid":true' "$WORK/body" || fail "an answer that came right was not taken: $(head -c 300 "$WORK/body")"
grep -q '"total_tokens":30' "$WORK/body" || fail "the retry was not billed: $(head -c 400 "$WORK/body")"
echo "  ok: an answer that came right on the retry passed, and billed both calls"

live_crew say-prose '"process":"dag","tasks":[{"description":"SAY",SHAPE},{"description":"after","dependencies":[0]}]'
grep -q '"status":"failed","task_count"' "$WORK/body" || fail "a DAG went on past a shape: $(head -c 300 "$WORK/body")"
grep -q '"output":"after"' "$WORK/body" && fail "a dependent task ran on an answer that failed"
echo "  ok: a task that depends on one that failed its shape does not run"

# ⭐ A tool, through the loop, held to its target and on the record (0.4.5, ADR 0040). A model is what
# chooses the URL, so the gateway here asks for the one the task description names.
LIVE_TOOLS=',"tools":["LoadTestingTool"]'
LIVE_TARGET="\"target\":{\"url\":\"$BASE/health\"},"
TOOLED='"tasks":[{"description":"SAY"}]'
live_crew "use-tool load_testing $BASE/health" "$TOOLED"
grep -q '"tool":"load_testing"' "$WORK/body" || fail "no tool call on the task: $(head -c 400 "$WORK/body")"
grep -q '"effect":"committed","success":true' "$WORK/body" || fail "the tool did not run: $(head -c 600 "$WORK/body")"
grep -q '"total_requests"' "$WORK/body" || fail "what the tool measured is not on the task: $(head -c 600 "$WORK/body")"
echo "  ok: a model called a tool at the crew's target, and what it measured is on the task"

live_crew "use-tool load_testing http://localhost:$PORT/health" "$TOOLED"
grep -q '"effect":"none","success":false' "$WORK/body" || fail "a call off the target ran: $(head -c 600 "$WORK/body")"
grep -q 'this call may not reach it' "$WORK/body" || fail "a call off the target does not say why: $(head -c 600 "$WORK/body")"
echo "  ok: a call to another host never started"

LIVE_TARGET=""
live_crew "use-tool load_testing $BASE/health" "$TOOLED"
grep -q '"effect":"none","success":false' "$WORK/body" || fail "a crew with no target pointed a tool: $(head -c 600 "$WORK/body")"
echo "  ok: a crew with no target points a tool at nothing"

expect 400 "a tool with nothing behind it" -X POST -H 'Content-Type: application/json' \
  -d '{"name":"m","agents":[{"key":"a","role":"r","goal":"g","tools":["RiskScoringTool"]}],"tasks":[{"description":"d"}]}' \
  "$BASE/api/v1/crews"
grep -q "tool 'RiskScoringTool' has nothing behind it" "$WORK/body" || fail "the refusal does not name it: $(head -c 300 "$WORK/body")"
expect 200 "the trail" "$BASE/api/v1/audit/entries"
grep -q '"tool.call"' "$WORK/body" || fail "a tool call is not on the trail: $(head -c 300 "$WORK/body")"
grep -q '"tool.result"' "$WORK/body" || fail "a tool result is not on the trail: $(head -c 300 "$WORK/body")"
grep -q 'effect=committed' "$WORK/body" || fail "the trail does not say what it did: $(head -c 300 "$WORK/body")"
echo "  ok: every call is on the audit trail, before and after"
LIVE_TOOLS=""
stop
kill "$GATEWAY" 2>/dev/null
wait "$GATEWAY" 2>/dev/null

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

# --- behind a proxy, and what a scraper and a tenant meet (0.3.1) --------------------------------

# refused <what> VAR=value...: a setting that must stop the server before it listens.
refused() {
  local what="$1"
  shift
  local rc=0
  env AGNOSTIC_ADDR=127.0.0.1 AGNOSTIC_PORT="$PORT" AGNOSTIC_AUTH=off \
    AGNOSTIC_DB_PATH="$WORK/refused.patra" AGNOSTIC_AUDIT_PATH="$WORK/refused-audit.patra" \
    "$@" timeout 5 "$BIN" > "$WORK/refused.log" 2>&1 || rc=$?
  [ "$rc" -eq 1 ] || fail "$what: exited $rc, not 1"
  echo "  ok: $what is refused"
}
refused "a proxy list of /0" AGNOSTIC_TRUSTED_PROXIES=0.0.0.0/0
refused "a proxy list with a typo" AGNOSTIC_TRUSTED_PROXIES=10.1.2.3/8
refused "a short metrics token" AGNOSTIC_METRICS_TOKEN=short
refused "a target host with a port" AGNOSTIC_TARGET_HOSTS=staging.example.com:8080
refused "a wildcard target host" 'AGNOSTIC_TARGET_HOSTS=*.example.com'
refused "a GPU tools switch that is neither word" AGNOSTIC_GPU_TOOLS=yes
refused "a tenant limit that is not a number" AGNOSTIC_TENANT_MAX_CREWS=many

SCRAPE=scrape-0123456789abcdef0123456789abcdef

# start_proxied <log> <db> [VAR=value...]: auth required, one bootstrap user, and whatever is named.
start_proxied() {
  local log="$1" db="$2"
  shift 2
  env AGNOSTIC_ADDR=127.0.0.1 AGNOSTIC_PORT="$PORT" AGNOSTIC_AUTH=required \
    AGNOSTIC_BOOTSTRAP_EMAIL=probe@example.com AGNOSTIC_BOOTSTRAP_PASSWORD=probe-password-12 \
    AGNOSTIC_DB_PATH="$WORK/$db.patra" AGNOSTIC_AUDIT_PATH="$WORK/$db-audit.patra" \
    "$@" "$BIN" > "$WORK/$log.log" 2>&1 &
  PID=$!
}

# bad_login <expected status> <what> [curl args...]: a wrong password, with the headers named.
bad_login() {
  local want="$1" what="$2"
  shift 2
  expect "$want" "$what" -X POST -H 'Content-Type: application/json' "$@" \
    -d '{"email":"probe@example.com","password":"wrong-password-1"}' "$BASE/api/v1/auth/login"
}

# drain <what> [curl args...]: wrong passwords until the bucket refuses, with @N@ in an argument
# replaced by the attempt's number. The burst is 5, and a token comes back every 12 s, so on a machine
# where a hash takes 2 s the sixth attempt is honestly let in. What matters is that a refusal comes:
# a caller who got a fresh bucket per request would never see one.
drain() {
  local what="$1" n=0 got
  shift
  while [ "$n" -lt 10 ]; do
    n=$((n + 1))
    got="$(status_of -X POST -H 'Content-Type: application/json' "${@//@N@/$n}" \
      -d '{"email":"probe@example.com","password":"wrong-password-1"}' "$BASE/api/v1/auth/login")"
    if [ "$got" = "429" ]; then
      echo "  ok: $what: refused on attempt $n"
      return 0
    fi
    [ "$got" = "401" ] || fail "$what: attempt $n got $got"
  done
  fail "$what: ten attempts and no refusal"
}

# refused_soon <what> [curl args...]: the bucket is already drained, so a refusal comes within two
# attempts, one token at most having come back. A fresh bucket would answer 401 twice.
refused_soon() {
  local what="$1" n=0 got
  shift
  while [ "$n" -lt 2 ]; do
    n=$((n + 1))
    got="$(status_of -X POST -H 'Content-Type: application/json' "$@" \
      -d '{"email":"probe@example.com","password":"wrong-password-1"}' "$BASE/api/v1/auth/login")"
    if [ "$got" = "429" ]; then
      echo "  ok: $what"
      return 0
    fi
  done
  fail "$what: two attempts and no refusal"
}

# With no list the header is noise: rotating it buys no new bucket.
start_proxied noproxy noproxy
wait_up
drain "a new claimed address each time, with no proxy named" -H 'X-Forwarded-For: 198.51.100.@N@'
stop

start_proxied proxied proxied AGNOSTIC_TRUSTED_PROXIES=127.0.0.1 AGNOSTIC_METRICS_TOKEN="$SCRAPE" \
  AGNOSTIC_TENANT_RATE_LIMIT=2
wait_up
drain "client A" -H 'X-Forwarded-For: 203.0.113.1'
bad_login 401 "client B, behind the same proxy, is not locked out" -H 'X-Forwarded-For: 203.0.113.2'
refused_soon "client A cannot escape by writing to the left of what the proxy adds" \
  -H 'X-Forwarded-For: 192.0.2.77, 203.0.113.1'
refused_soon "nor with a line of its own ahead of the proxy's" \
  -H 'X-Forwarded-For: 192.0.2.78' -H 'X-Forwarded-For: 203.0.113.1'
bad_login 401 "an IPv6 client has a bucket" -H 'X-Forwarded-For: 2001:db8:1:2::9'

expect 401 "the metrics, with nothing" "$BASE/api/v1/metrics"
expect 401 "the metrics, with a wrong token" -H 'Authorization: Bearer scrape-wrong' "$BASE/api/v1/metrics"
expect 200 "the metrics, as a scraper" -H "Authorization: Bearer $SCRAPE" "$BASE/api/v1/metrics"
grep -q '^agnostic_build_info{version="' "$WORK/body" || fail "the metrics name no version"
grep -q '^agnostic_refusals_total{reason="login_throttled"} [1-9]' "$WORK/body" \
  || fail "the metrics do not count the throttled logins"
expect 401 "and that token opens nothing else" -H "Authorization: Bearer $SCRAPE" "$BASE/api/v1/presets"
CTYPE="$(curl -s -m 10 -o /dev/null -w '%{content_type}' -H "Authorization: Bearer $SCRAPE" "$BASE/api/v1/metrics")"
case "$CTYPE" in
  text/plain*version=0.0.4*) echo "  ok: the metrics say their format" ;;
  *) fail "the metrics are served as '$CTYPE'" ;;
esac

expect 200 "a sign-in" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"
CREW='{"name":"probe","agents":[{"key":"a1","role":"r","goal":"g"}],"tasks":[{"description":"d"}]}'
for n in 1 2; do
  expect 202 "crew $n of 2 a minute" -X POST -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d "$CREW" "$BASE/api/v1/crews"
done
LIMITED="$(curl -s -m 10 -D - -o /dev/null -X POST -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d "$CREW" "$BASE/api/v1/crews")"
printf '%s' "$LIMITED" | grep -q '^HTTP/1.1 429' || fail "the third crew was not refused: $LIMITED"
printf '%s' "$LIMITED" | grep -qi '^retry-after: [1-9]' || fail "the 429 has no Retry-After: $LIMITED"
echo "  ok: a tenant over its rate is told when to come back"

expect 404 "the Users view, switched off" "$BASE/ui/plugins/users"
expect 200 "switching it on" -X PUT -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"enabled":true}' "$BASE/api/v1/plugins/users"
expect 200 "the Users view" "$BASE/ui/plugins/users"
grep -q 'Users · agnostic' "$WORK/body" || fail "/ui/plugins/users is not the Users view"

# More refusals than the budget, so the stop has a count to write.
for n in $(seq 1 30); do
  [ "$(status_of "$BASE/api/v1/presets")" = "401" ] || fail "refusal $n was not a 401"
done
expect 200 "the trail" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/audit/entries?limit=100"
grep -q '"auth.denied"' "$WORK/body" || fail "a 401 left nothing in the trail"
grep -q '"auth.throttled"' "$WORK/body" || fail "a throttled login left nothing in the trail"
grep -q 'peer=203.0.113.1' "$WORK/body" || fail "the trail does not name the client behind the proxy"
grep -q '"tenant.throttled"' "$WORK/body" || fail "a tenant's refusal left nothing in the trail"
grep -q 'wrong-password' "$WORK/body" && fail "the trail holds a password"
echo "  ok: refusals are in the trail, by the client's address"
stop

start_proxied proxied-again proxied
wait_up
expect 200 "a sign-in after the stop" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"
expect 200 "the trail again" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/audit/entries?limit=100"
grep -q '"audit.refusals_held"' "$WORK/body" || fail "the stop did not write what was held"
echo "  ok: a stop writes what the budget held back"
stop

# --- what a crew's body can say (0.4.0) ------------------------------------------------------------

start_proxied crewbody crewbody AGNOSTIC_TARGET_HOSTS=sut.example
wait_up
expect 200 "a sign-in" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"
# The crew body (0.4.0): a target, a stored definition, a declared shape, and the tools route.
CREW_TASK='{"description":"check it","output_schema":{"type":"object","required":["verdict"]}}'
submit() { status_of -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d "$1" "$BASE/api/v1/crews"; }
expect 201 "a definition to name" -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"key":"probe-agent","role":"tester","goal":"find bugs"}' "$BASE/api/v1/agents/definitions"
[ "$(submit '{"name":"aimed","target":{"url":"https://sut.example/app"},"agents":[{"definition":"probe-agent"}],"tasks":['"$CREW_TASK"']}')" = "202" ] \
  || { cat "$WORK/body"; fail "a crew with a listed target, a named agent and a shape was not accepted"; }
AIMED="$(sed -E 's/.*"crew_id":"([^"]+)".*/\1/' "$WORK/body")"
echo "  ok: a crew names a listed target, a stored agent and a shape"
[ "$(submit '{"name":"away","target":{"url":"https://elsewhere.example/"},"agents":[{"definition":"probe-agent"}],"tasks":[{"description":"t"}]}')" = "403" ] \
  || fail "a target off the list was not refused"
grep -q 'elsewhere' "$WORK/body" && fail "the refusal echoes the host"
[ "$(submit '{"name":"sly","target":{"url":"https://sut.example\\@elsewhere.example/"},"agents":[{"definition":"probe-agent"}],"tasks":[{"description":"t"}]}')" = "400" ] \
  || fail "a URL two parsers read differently was not refused"
[ "$(submit '{"name":"lost","agents":[{"definition":"nobody"}],"tasks":[{"description":"t"}]}')" = "422" ] \
  || fail "a definition nothing is stored under was not refused"
echo "  ok: off the list, a confusing URL and an absent definition are refused"
tries=0
until [ "$(status_of -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/crews/$AIMED")" = "200" ] && grep -q '"finished_at"' "$WORK/body"; do
  tries=$((tries + 1))
  [ "$tries" -lt 100 ] || fail "the aimed crew did not finish"
  read -r -t 0.1 _ < <(tail -f /dev/null) || true
done
grep -q '"target":{"url":"https://sut.example/app"}' "$WORK/body" || fail "the outcome does not say what the crew ran against"
grep -q '"output_valid"' "$WORK/body" && fail "a placeholder answer was judged: no model gave it"
echo "  ok: the outcome says what it ran against, and judges no placeholder"
expect 200 "the tools" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/tools"
grep -q '"unresolved":36' "$WORK/body" || fail "the gate's number is not on the wire"
grep -q '"crews_call_tools":true' "$WORK/body" || fail "the tools route does not say a crew calls them"

# 0.4.1: the host's own accelerators, whatever they are here. Bytes a JSON string may not hold raw are
# what a row overrunning its allocation looks like, as it did on the first real GPU this ran on.
expect 200 "the accelerators" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/gpu"
grep -q '"gpu_required_enforced":false' "$WORK/body" || fail "the GPU route does not say a crew is not held to it"
grep -q '"vendor_tools":false' "$WORK/body" || fail "a tool ran that nobody allowed"
grep -q 'u0000' "$WORK/body" && fail "a device's words are damaged: $(cat "$WORK/body")"
grep -qE '"detected_at":[1-9]' "$WORK/body" || fail "the mount did not read the host"
echo "  ok: this host: $(sed -E 's/"detected_at".*//' "$WORK/body")"

expect 200 "the trail" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/audit/entries?limit=100"
grep -q '"crew.target_refused"' "$WORK/body" || fail "a refused target left nothing in the trail"
echo "  ok: a refused target is in the trail"
stop

# --- what may run at start (0.4.1) -----------------------------------------------------------------

# ⭐ From outside, because `vendor_tools` is the server's own word for it: a tool on the PATH that
# leaves a mark when it runs, and fails.
FAKE="$WORK/tools"
mkdir -p "$FAKE"
printf '#!/bin/sh\ntouch "%s/spawned"\nexit 3\n' "$WORK" > "$FAKE/nvidia-smi"
chmod +x "$FAKE/nvidia-smi"

start_proxied tools-off tools PATH="$FAKE:$PATH"
wait_up
[ ! -e "$WORK/spawned" ] || fail "a vendor tool ran with AGNOSTIC_GPU_TOOLS unset"
echo "  ok: with tools off, nothing is spawned"
stop

start_proxied tools-on tools PATH="$FAKE:$PATH" AGNOSTIC_GPU_TOOLS=on
wait_up
[ -e "$WORK/spawned" ] || fail "AGNOSTIC_GPU_TOOLS=on ran no tool"
expect 200 "a sign-in" -X POST -H 'Content-Type: application/json' \
  -d '{"email":"probe@example.com","password":"probe-password-12"}' "$BASE/api/v1/auth/login"
TOKEN="$(sed -E 's/.*"token":"([^"]+)".*/\1/' "$WORK/body")"
expect 200 "the accelerators" -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/gpu"
grep -q '"vendor_tools":true' "$WORK/body" || fail "tools ran and the answer does not say so"
grep -qE '"warnings":[1-9]' "$WORK/body" || fail "a tool that failed is not counted"
grep -q 'nvidia' "$WORK/body" && fail "a tool's words reached the answer"
echo "  ok: with tools on, they run, and a failure is counted and not quoted"
stop

# ⭐ A tool that hangs delays the start by its deadline, and is killed, and the server comes up.
printf '#!/bin/sh\nexec sleep 8642\n' > "$FAKE/nvidia-smi"
began=$(date +%s)
start_proxied tools-hung tools PATH="$FAKE:$PATH" AGNOSTIC_GPU_TOOLS=on
tries=0
until [ "$(status_of "$BASE/health")" = "200" ]; do
  tries=$((tries + 1))
  [ "$tries" -lt 600 ] || fail "a hung tool held the start past 60 s"
  kill -0 "$PID" 2>/dev/null || fail "the server exited behind a hung tool"
  sleep 0.1
done
echo "  ok: a hung tool held the start for $(($(date +%s) - began)) s"
ps -eo args | grep -q '^sleep 8642' && fail "a hung tool was left running"
stop

echo "boot-probe: OK"
