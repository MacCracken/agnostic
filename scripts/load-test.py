#!/usr/bin/env python3
"""load-test.py — many clients against the real binary; every crew must end up `completed`.

WHAT IT GUARDS. A suite runs one thread with no store contention, so it cannot show what a sweep
does at 200 crews a second. The first version of ADR 0022's fix passed every suite and lost most of
its crews under this load, and only a real server with concurrent clients showed it.

Four steps, each of which has lost crews before:

  1. a burst from `--clients` clients, past the engine's registry of 1,000, none of it polled;
  2. every crew read back, while the outcome writes are still behind;
  3. a second burst and SIGTERM as soon as it is accepted, so the stop finds writes outstanding;
  4. a restart, where every crew must read `completed` from the store.

The second burst is there because reading the first takes long enough for the writes to catch up,
and a stop with nothing outstanding proves nothing. A crew that reads `interrupted` after the
restart finished before the stop and was not written. Exits 1 on any crew that is not `completed`.

Usage: scripts/load-test.py [binary] [--crews 6000] [--clients 16] [--port 18732]
"""
import argparse
import collections
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

CREW = json.dumps({
    "name": "load",
    "agents": [{"key": "a", "role": "r", "goal": "g"}],
    "tasks": [{"description": "one"}],
})
HEADERS = {"Content-Type": "application/json", "Host": "localhost"}


def request(port, method, path, body=None):
    """One request on its own connection: sixteen idle sockets would hold every worker."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        conn.request(method, path, body=body, headers=HEADERS)
        reply = conn.getresponse()
        return reply.status, reply.read()
    finally:
        conn.close()


def start(binary, work, port, log_name):
    env = dict(
        os.environ,
        AGNOSTIC_ADDR="127.0.0.1",
        AGNOSTIC_PORT=str(port),
        AGNOSTIC_AUTH="off",
        AGNOSTIC_DB_PATH=os.path.join(work, "load.patra"),
        AGNOSTIC_AUDIT_PATH=os.path.join(work, "load-audit.patra"),
    )
    log = open(os.path.join(work, log_name), "wb")
    server = subprocess.Popen([binary], env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(600):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return server
        except OSError:
            if server.poll() is not None:
                sys.exit(f"load-test: the server exited {server.returncode} before it listened")
            time.sleep(0.05)
    sys.exit("load-test: the server did not listen within 30 s")


def burst(port, total, clients):
    """Submit `total` crews from `clients` threads. The ids accepted, and anything refused."""
    ids, refused, lock, taken = [], collections.Counter(), threading.Lock(), [0]

    def client():
        while True:
            with lock:
                if taken[0] >= total:
                    return
                taken[0] += 1
            status, text = request(port, "POST", "/api/v1/crews", CREW)
            with lock:
                if status == 202:
                    ids.append(json.loads(text)["crew_id"])
                else:
                    refused[status] += 1

    threads = [threading.Thread(target=client) for _ in range(clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return ids, refused


def read_all(port, ids, settle_s):
    """Each crew's status, read until none is in flight or `settle_s` runs out."""
    seen, waiting = collections.Counter(), list(ids)
    deadline = time.time() + settle_s
    while waiting:
        still = []
        for crew in waiting:
            status, text = request(port, "GET", f"/api/v1/crews/{crew}")
            word = json.loads(text).get("status") if status == 200 else str(status)
            if word in ("pending", "running") and time.time() < deadline:
                still.append(crew)
            else:
                seen[word] += 1
        waiting = still
    return dict(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("binary", nargs="?", default="build/agnostic")
    parser.add_argument("--crews", type=int, default=6000)
    parser.add_argument("--clients", type=int, default=16)
    parser.add_argument("--port", type=int, default=18732)
    args = parser.parse_args()

    work = tempfile.mkdtemp(prefix="agnostic-load-")
    server = None
    bad = []
    try:
        server = start(args.binary, work, args.port, "first.log")
        began = time.time()
        ids, refused = burst(args.port, args.crews, args.clients)
        took = time.time() - began
        rate = len(ids) / took if took > 0 else 0
        print(f"accepted {len(ids)} of {args.crews} at {rate:.0f}/s from {args.clients} clients")
        if refused:
            bad.append(f"refused: {dict(refused)}")

        seen = read_all(args.port, ids, 60)
        print(f"while running: {seen}")
        if seen != {"completed": len(ids)}:
            bad.append(f"while running: {seen}")

        more, refused = burst(args.port, max(args.crews // 4, 300), args.clients)
        print(f"accepted {len(more)} more")
        if refused:
            bad.append(f"refused: {dict(refused)}")
        ids.extend(more)
        stopping = time.time()
        server.terminate()
        code = server.wait(300)
        print(f"SIGTERM: exit {code} after {time.time() - stopping:.1f} s")
        if code != 0:
            bad.append(f"exit {code} on SIGTERM")

        server = start(args.binary, work, args.port, "second.log")
        seen = read_all(args.port, ids, 0)
        print(f"after the restart: {seen}")
        if seen != {"completed": len(ids)}:
            bad.append(f"after the restart: {seen}")
        status, text = request(args.port, "GET", "/api/v1/audit")
        if status != 200 or b'"intact"' not in text:
            bad.append(f"audit chain: {status} {text[:120]!r}")
        server.terminate()
        server.wait(60)
        server = None
    finally:
        if server is not None and server.poll() is None:
            server.kill()
        shutil.rmtree(work, ignore_errors=True)

    if bad:
        print("load-test: FAIL: " + "; ".join(bad), file=sys.stderr)
        return 1
    print("load-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
