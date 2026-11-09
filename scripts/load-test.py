#!/usr/bin/env python3
"""load-test.py — many clients against the real binary; every crew must end up `completed`.

WHAT IT GUARDS. A suite runs one thread with no store contention, so it cannot show what a sweep
does at 200 crews a second. The first version of ADR 0022's fix passed every suite and lost most of
its crews under this load, and only a real server with concurrent clients showed it.

Eight steps, the first four of which have lost crews before:

  1. a burst from `--clients` clients, past the engine's registry of 1,000, none of it polled;
  2. every crew read back, while the outcome writes are still behind;
  3. a second burst and SIGTERM as soon as it is accepted, so the stop finds writes outstanding;
  4. a restart, where every crew must read `completed` from the store;
  5. readers of `/events` against a burst past the ledger's cap, whose eviction recycles event rings:
     a crew must never show another crew's events. A smoke test: the moment a request holds an entry
     across its eviction is too short to hit on demand, so `ledger/ring-recycled` holds that rule;
  6. the same clients against a tenant cap, where a crew can end before its submit returns. A place
     not given back shows up as a tenant refused for crews it no longer has.
  7. crews with a target of their own, a stored agent and a shape, polled as they end and read back
     after a restart: each must say its own target and that a placeholder has no `output_valid`, and a
     placeholder crew ending under a millisecond must not lose its target;
  8. readers aimed at the crews about to be evicted, while writers push through the ledger's cap, so
     that crews are given back and their arenas reused under the reads (ADR 0034). A crew must say
     only its own words: a read of a released arena is another crew's output, or a crash. The memory
     the process holds must stop growing, which is audit P2's measurement from outside.
  9. crews calling a tool through a gateway, from every client at once (ADR 0040): each call must come
     back on its own crew, and every one goes through the journal's one writer, so a lost wake is a
     crew that never ends and two entries written at once is a trail that does not verify.

The second burst is there because reading the first takes long enough for the writes to catch up,
and a stop with nothing outstanding proves nothing. A crew that reads `interrupted` after the
restart finished before the stop and was not written. Exits 1 on any crew that is not `completed`.

Usage: scripts/load-test.py [binary] [--crews 6000] [--clients 16] [--port 18732]
       --steps 1-4,5,6      run only some of it (a mutant's check needs only its own step)
"""
import argparse
import collections
import http.client
import json
import os
import random
import re
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


def start(binary, work, port, log_name, db="load", **extra):
    env = dict(
        os.environ,
        AGNOSTIC_ADDR="127.0.0.1",
        AGNOSTIC_PORT=str(port),
        AGNOSTIC_AUTH="off",
        AGNOSTIC_DB_PATH=os.path.join(work, db + ".patra"),
        AGNOSTIC_AUDIT_PATH=os.path.join(work, db + "-audit.patra"),
        **extra,
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


def burst(port, total, clients, follow=False):
    """Submit `total` crews from `clients` threads. The ids accepted, and anything refused.

    `follow` reads each accepted crew until it ends, which is what frees its place at a tenant's cap,
    so places turn over as fast as crews finish and not at the collector's 200 ms.
    """
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
            if follow and status != 202:
                time.sleep(0.01)  # as a client told to come back would, or it only spins on refusals
            if follow and status == 202:
                crew = json.loads(text)["crew_id"]
                while True:
                    got, reply = request(port, "GET", f"/api/v1/crews/{crew}")
                    if got != 200 or json.loads(reply).get("status") not in ("pending", "running"):
                        break

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


def named_crew(name):
    return json.dumps({
        "name": name,
        "agents": [{"key": "a", "role": "r", "goal": "g"}],
        "tasks": [{"description": "one"}],
    })


def events_race(port, total, clients):
    """Step 5. How many reads found their crew's events, and how many found another's."""
    known, lock, taken, done = [], threading.Lock(), [0], threading.Event()
    reads, wrong = [0], []

    def writer():
        while True:
            with lock:
                if taken[0] >= total:
                    return
                taken[0] += 1
                name = f"crew-{taken[0]}"
            status, text = request(port, "POST", "/api/v1/crews", named_crew(name))
            if status == 202:
                with lock:
                    known.append((json.loads(text)["crew_id"], name))

    def reader():
        rng = random.Random()
        while not done.is_set():
            with lock:
                if not known:
                    continue
                crew, name = known[rng.randrange(len(known))]
            status, text = request(port, "GET", f"/api/v1/crews/{crew}/events")
            if status != 200:
                continue
            for event in json.loads(text)["events"]:
                if event["type"] == "crew_started":
                    with lock:
                        reads[0] += 1
                        if event["data"]["name"] != name:
                            wrong.append((crew, name, event["data"]["name"]))

    writers = [threading.Thread(target=writer) for _ in range(clients)]
    readers = [threading.Thread(target=reader) for _ in range(clients // 2)]
    for t in writers + readers:
        t.start()
    for t in writers:
        t.join()
    done.set()
    for t in readers:
        t.join()
    return reads[0], wrong


def metric(port, name):
    status, text = request(port, "GET", "/api/v1/metrics")
    if status != 200:
        return None
    found = re.search(r"^" + re.escape(name) + r" (\d+)$", text.decode(), re.M)
    return int(found.group(1)) if found else None


def settle_count(port, ids, settle_s):
    """Wait for `ids` to end, and report how many did not."""
    seen = read_all(port, ids, settle_s)
    return sum(n for word, n in seen.items() if word != "completed")


def wanted(spec):
    """The step numbers `--steps 1-4,6` names."""
    out = set()
    for part in spec.split(","):
        first, _, last = part.partition("-")
        out.update(range(int(first), int(last or first) + 1))
    return out


def steps_one_to_four(args, work, bad):
    server = start(args.binary, work, args.port, "first.log")
    try:
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
    finally:
        if server.poll() is None:
            server.kill()


def step_five(args, work, bad):
    server = start(args.binary, work, args.port, "events.log", db="events")
    try:
        total = max(args.crews // 2, 2000)
        reads, wrong = events_race(args.port, total, args.clients)
        print(f"{reads} reads of a crew's events beside {total} crews and eviction: {len(wrong)} of another's")
        if wrong:
            bad.append(f"a crew showed another's events: {wrong[:3]}")
        if reads == 0:
            bad.append("no read reached a crew's events")
        server.terminate()
        code = server.wait(300)
        if code != 0:
            bad.append(f"exit {code} after the event readers")
    finally:
        if server.poll() is None:
            server.kill()


def step_six(args, work, bad):
    cap = 8
    server = start(args.binary, work, args.port, "cap.log", db="cap", AGNOSTIC_TENANT_MAX_CREWS=str(cap))
    try:
        total = max(args.crews // 2, 2000)
        ids, refused = burst(args.port, total, args.clients, follow=True)
        print(f"at a cap of {cap}: accepted {len(ids)}, refused {dict(refused)} of {total}")
        if set(refused) - {429}:
            bad.append(f"a capped burst was answered {dict(refused)}")
        if len(ids) < cap * 10:
            bad.append(f"only {len(ids)} crews got through, too few to turn the places over")
        if settle_count(args.port, ids, 60) != 0:
            bad.append("a capped burst did not finish")
        counted = metric(args.port, 'agnostic_refusals_total{reason="tenant_crews"}')
        if counted != refused[429]:
            bad.append(f"the metrics count {counted} refusals of {refused[429]}")

        # Every crew has ended, so every place is free. One leaked place would fail this: `cap`
        # crews at once, each held by nothing but the collector's 200 ms.
        time.sleep(0.5)
        status = [request(args.port, "POST", "/api/v1/crews", CREW)[0] for _ in range(cap)]
        print(f"then {cap} more, with nothing running: {collections.Counter(status)}")
        if status != [202] * cap:
            bad.append(f"places were lost: {collections.Counter(status)}")
        server.terminate()
        code = server.wait(300)
        if code != 0:
            bad.append(f"exit {code} after the capped burst")
    finally:
        if server.poll() is None:
            server.kill()


def aimed_crew(n):
    """Step 7's crew: a target only it has, a stored agent, and a shape a placeholder is not held to."""
    return json.dumps({
        "name": f"aimed-{n}",
        "target": {"url": f"https://sut.example/crew-{n}"},
        "agents": [{"definition": "load-agent"}],
        "tasks": [{"description": "one", "output_schema": {"type": "object", "required": ["verdict"]}}],
    })


def aimed_fault(crew, n, text):
    """What is wrong with crew `crew`'s document `text`, for its number `n`, or None."""
    doc = json.loads(text)
    if doc.get("status") != "completed":
        return f"{crew} ended {doc.get('status')}"
    if doc.get("target", {}).get("url") != f"https://sut.example/crew-{n}":
        return f"{crew} says it ran against {doc.get('target')}"
    results = doc.get("results", [])
    if len(results) != 1 or "output_valid" in results[0]:
        return f"{crew} judged a placeholder: {[r.get('output_valid') for r in results]}"
    return None


def aimed_race(port, total, clients):
    """Step 7's burst, with half as many pollers. Crew id to number, the reads, and every fault."""
    known, lock, taken, done = {}, threading.Lock(), [0], threading.Event()
    reads, faults = [0], []

    def writer():
        while True:
            with lock:
                if taken[0] >= total:
                    return
                taken[0] += 1
                n = taken[0]
            status, text = request(port, "POST", "/api/v1/crews", aimed_crew(n))
            if status == 202:
                with lock:
                    known[json.loads(text)["crew_id"]] = n
            else:
                with lock:
                    faults.append(f"submit {n} answered {status}")

    def reader():
        rng = random.Random()
        while not done.is_set():
            with lock:
                if not known:
                    continue
                crew = rng.choice(list(known.keys())[-64:])
                n = known[crew]
            status, text = request(port, "GET", f"/api/v1/crews/{crew}")
            if status != 200 or json.loads(text).get("status") in ("pending", "running"):
                continue
            fault = aimed_fault(crew, n, text)
            with lock:
                reads[0] += 1
                if fault:
                    faults.append(fault)

    writers = [threading.Thread(target=writer) for _ in range(clients)]
    readers = [threading.Thread(target=reader) for _ in range(clients // 2)]
    for t in writers + readers:
        t.start()
    for t in writers:
        t.join()
    done.set()
    for t in readers:
        t.join()
    return known, reads[0], faults


def read_aimed(port, known, settle_s):
    """Every crew of step 7, read until it ends. Its faults."""
    faults = []
    deadline = time.monotonic() + settle_s
    for crew, n in known.items():
        while True:
            status, text = request(port, "GET", f"/api/v1/crews/{crew}")
            ended = status == 200 and json.loads(text).get("status") not in ("pending", "running")
            if ended or time.monotonic() > deadline:
                break
            time.sleep(0.02)
        fault = aimed_fault(crew, n, text) if status == 200 else f"{crew} answered {status}"
        if fault:
            faults.append(fault)
    return faults


def wordy_crew(n, tasks=12):
    """Step 8's crew. Its words are its own, so a read of anything else's memory cannot pass."""
    return json.dumps({
        "name": f"wordy-{n}",
        "agents": [{"key": "a", "role": "r", "goal": "g"}],
        "tasks": [{"description": f"wordy-{n}-task-{i}"} for i in range(tasks)],
    })


def wordy_fault(n, path, text):
    """What is wrong with the answer `text` to reading crew `n` at `path`, or None."""
    doc = json.loads(text)
    mine = f"wordy-{n}"
    if path == "plan":
        said = [t.get("description") for t in doc.get("tasks", [])]
        if said and said != [f"{mine}-task-{i}" for i in range(len(said))]:
            return f"{mine}'s plan says {said[:2]}"
    elif path == "events":
        for event in doc.get("events", []):
            if event["type"] == "crew_started" and event["data"]["name"] != mine:
                return f"{mine}'s events name {event['data']['name']}"
    else:
        if doc.get("name") != mine:
            return f"{mine} is called {doc.get('name')}"
        for result in doc.get("results", []):
            if not result.get("output", "").startswith(mine + "-"):
                return f"{mine} answered {result.get('output')!r}"
    return None


def resident_kb(pid):
    with open(f"/proc/{pid}/status", encoding="ascii") as status:
        return int(re.search(r"VmRSS:\s+(\d+)", status.read()).group(1))


def release_race(port, total, clients, pid):
    """Step 8. The reads, every fault, and the resident memory as the burst went on: (crews, KiB)."""
    known, lock, taken, done = [], threading.Lock(), [0], threading.Event()
    reads, faults, resident, pause = [0], [], [], [0.0]

    def pacer():
        """Hold the writers to the store. A backlog of outcomes keeps crews in the ledger, whose
        arenas are in use and not a leak, and would hide the one thing this step measures. Writers
        slow and never stop, because only a submit evicts."""
        while not done.is_set():
            held = metric(port, "agnostic_ledger_crews") or 0
            pause[0] = max(0, held - 1200) * 0.002
            time.sleep(0.1)

    def writer():
        while True:
            with lock:
                if taken[0] >= total:
                    return
                taken[0] += 1
                n = taken[0]
            time.sleep(pause[0])
            status, text = request(port, "POST", "/api/v1/crews", wordy_crew(n))
            if status == 202:
                with lock:
                    known.append((json.loads(text)["crew_id"], n))
                    if len(known) % 500 == 0:
                        resident.append((len(known), resident_kb(pid)))
            elif status != 429:
                with lock:
                    faults.append(f"a submit answered {status}")

    def reader():
        rng = random.Random()
        while not done.is_set():
            with lock:
                held = len(known)
                if held < 1024:
                    continue
                # The ledger keeps 768 to 1,024 crews, so these are the ones about to go.
                crew, n = known[held - rng.randrange(700, 1100)]
            path = rng.choice(["", "events", "plan"])
            status, text = request(port, "GET", f"/api/v1/crews/{crew}" + (f"/{path}" if path else ""))
            if status not in (200, 404):
                with lock:
                    faults.append(f"reading {crew}/{path} answered {status}")
                continue
            fault = wordy_fault(n, path, text) if status == 200 else None
            with lock:
                reads[0] += 1 if status == 200 else 0
                if fault:
                    faults.append(fault)

    writers = [threading.Thread(target=writer) for _ in range(clients)]
    others = [threading.Thread(target=reader) for _ in range(clients)] + [threading.Thread(target=pacer)]
    for t in writers + others:
        t.start()
    for t in writers:
        t.join()
    done.set()
    for t in others:
        t.join()
    return reads[0], faults, resident


def step_eight(args, work, bad):
    server = start(args.binary, work, args.port, "release.log", db="release")
    try:
        # Long enough for the pool to settle: a Raspberry Pi 4 still reads 2.8 KB a crew at 5,000.
        total = max(args.crews, 9000)
        reads, faults, resident = release_race(args.port, total, args.clients, server.pid)
        print(f"{reads} reads of crews about to go, beside {total} crews and their arenas: {len(faults)} faults")
        if faults:
            bad.append(f"crews being given back: {faults[:3]}")
        if reads == 0:
            bad.append("no read reached a crew about to go")
        # Past the ledger, its limbo and the first arenas. What is left grows only with the audit
        # trail and the store's cache, so a crew kept for life shows at once: it was 11 KB and more.
        settled = [r for r in resident if r[0] >= max(3000, total // 2)]
        if len(settled) >= 2:
            crews = settled[-1][0] - settled[0][0]
            per = (settled[-1][1] - settled[0][1]) * 1024 // crews
            print(f"resident {settled[0][1]} KiB at {settled[0][0]} crews, {settled[-1][1]} KiB at "
                  f"{settled[-1][0]}: {per} B a crew")
            print("  by crews: " + " ".join(f"{n}:{kib // 1024}M" for n, kib in resident[::2]))
            if per > 2048:
                bad.append(f"{per} B a crew stays resident")
        server.terminate()
        code = server.wait(300)
        if code != 0:
            bad.append(f"exit {code} after the release race")
    finally:
        if server.poll() is None:
            server.kill()


def tooled_crew(n):
    """Step 9's crew: its tool answers with its own number, so a crossed result cannot pass."""
    return json.dumps({
        "name": f"tooled-{n}",
        "agents": [{"key": "a", "role": "r", "goal": "g", "tools": ["echo"]}],
        "tasks": [{"description": f"use-tool echo tooled-{n}"}],
    })


def tool_fault(n, text):
    """What is wrong with crew `n`'s document, or None."""
    doc = json.loads(text)
    if doc.get("status") != "completed":
        return f"tooled-{n} ended {doc.get('status')}"
    calls = doc["results"][0].get("tool_calls", [])
    if len(calls) != 1 or calls[0].get("tool") != "echo" or calls[0].get("effect") != "committed":
        return f"tooled-{n} called {calls}"
    if calls[0].get("result") != f"tooled-{n}":
        return f"tooled-{n} was answered {calls[0].get('result')}"
    return None


def step_nine(args, work, bad):
    gateway_port = args.port + 7
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake-gateway.py")
    gateway = subprocess.Popen([sys.executable, script, str(gateway_port)])
    server = start(args.binary, work, args.port, "tools.log", db="tools",
                   AGNOSTIC_LLM_URL=f"http://127.0.0.1:{gateway_port}")
    try:
        # Under the ledger's 1024, as this many are in flight at once: a crew past it while still
        # running reads `unknown` by design.
        total = min(args.crews, 900)
        known, lock, taken = {}, threading.Lock(), [0]

        def client():
            while True:
                with lock:
                    if taken[0] >= total:
                        return
                    taken[0] += 1
                    n = taken[0]
                status, text = request(args.port, "POST", "/api/v1/crews", tooled_crew(n))
                if status == 202:
                    with lock:
                        known[json.loads(text)["crew_id"]] = n
                else:
                    with lock:
                        bad.append(f"a tooled crew answered {status}: {text[:120]}")

        threads = [threading.Thread(target=client) for _ in range(args.clients)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        faults, deadline = [], time.monotonic() + 120
        for crew, n in known.items():
            while True:
                status, text = request(args.port, "GET", f"/api/v1/crews/{crew}")
                ended = status == 200 and json.loads(text).get("status") not in ("pending", "running")
                if ended or time.monotonic() > deadline:
                    break
                time.sleep(0.02)
            fault = tool_fault(n, text) if status == 200 else f"tooled-{n} answered {status}"
            if fault:
                faults.append(fault)
        print(f"{len(known)} crews called a tool at once: {len(faults)} faults")
        if faults:
            bad.append(f"tooled crews: {faults[:3]}")
        status, text = request(args.port, "GET", "/api/v1/audit")
        verdict = json.loads(text)
        if status != 200 or not verdict.get("intact"):
            bad.append(f"the trail after {len(known)} journaled calls: {text[:160]}")
        server.terminate()
        code = server.wait(300)
        if code != 0:
            bad.append(f"exit {code} after the tooled crews")
    finally:
        if server.poll() is None:
            server.kill()
        gateway.kill()
        gateway.wait()


def step_seven(args, work, bad):
    hosts = {"AGNOSTIC_TARGET_HOSTS": "sut.example"}
    server = start(args.binary, work, args.port, "aimed.log", db="aimed", **hosts)
    try:
        status, _ = request(args.port, "POST", "/api/v1/agents/definitions",
                            json.dumps({"key": "load-agent", "role": "r", "goal": "g", "focus": "f"}))
        if status != 201:
            bad.append(f"the stored agent answered {status}")
            return
        total = max(args.crews // 3, 1500)
        known, reads, faults = aimed_race(args.port, total, args.clients)
        faults += read_aimed(args.port, known, 120)
        print(f"{len(known)} aimed crews, {reads} reads of a finished one beside them: {len(faults)} faults")
        if faults:
            bad.append(f"aimed crews: {faults[:3]}")
        if reads == 0:
            bad.append("no read reached a finished crew")
        server.terminate()
        code = server.wait(300)
        if code != 0:
            bad.append(f"exit {code} after the aimed crews")
    finally:
        if server.poll() is None:
            server.kill()

    server = start(args.binary, work, args.port, "aimed-again.log", db="aimed", **hosts)
    try:
        faults = read_aimed(args.port, known, 30)
        print(f"after a restart: {len(known) - len(faults)} of {len(known)} say what they ran against and how it read")
        if faults:
            bad.append(f"aimed crews after a restart: {faults[:3]}")
        server.terminate()
        server.wait(300)
    finally:
        if server.poll() is None:
            server.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("binary", nargs="?", default="build/agnostic")
    parser.add_argument("--crews", type=int, default=6000)
    parser.add_argument("--clients", type=int, default=16)
    parser.add_argument("--port", type=int, default=18732)
    parser.add_argument("--steps", default="1-9")
    args = parser.parse_args()
    steps = wanted(args.steps)

    work = tempfile.mkdtemp(prefix="agnostic-load-")
    bad = []
    try:
        if steps & {1, 2, 3, 4}:
            steps_one_to_four(args, work, bad)
        if 5 in steps:
            step_five(args, work, bad)
        if 6 in steps:
            step_six(args, work, bad)
        if 7 in steps:
            step_seven(args, work, bad)
        if 8 in steps:
            step_eight(args, work, bad)
        if 9 in steps:
            step_nine(args, work, bad)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if bad:
        print("load-test: FAIL: " + "; ".join(bad), file=sys.stderr)
        return 1
    print("load-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
