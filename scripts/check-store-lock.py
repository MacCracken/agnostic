#!/usr/bin/env python3
"""check-store-lock.py — every use of the shared patra handle is under the store lock.

Added at 0.1.4. The server's pool workers all share ONE patra handle, and patra
does not make that safe: its read path takes no lock (since 1.12.0), so two
concurrent statements on one handle race its header buffer and file offset.
`tests/store_concurrency.tcyr` measured it on the 0.1.3 code — eight threads doing
only the per-request user lookup killed the process with SIGBUS on every run.

The fix has two halves and this is the second:

  * At RUN time, `agnostic_store_db()` hands the handle only to a thread holding
    `agnostic_store_lock()`. That catches a forgotten lock on every path a suite
    exercises.
  * This gate checks the same rule STATICALLY, so a path no suite reaches cannot
    carry the bug either.

The rules, over `src/`:

  0. The raw global `_agnostic_store_db` is referenced only in
     `src/engine/store.cyr`. Everything else goes through the accessor.
  1. A function that calls `agnostic_store_db()` either is named `*_locked` /
     `*_locked_a` — its contract is "my caller holds the store lock" — or calls
     `agnostic_store_lock()` before its first `agnostic_store_db()`.
  2. A call to a store-locked function (rule 1's `*_locked` kind, or one that
     calls another) comes from a function that is itself `*_locked`, or that
     called `agnostic_store_lock()` earlier in its body.
  3. Nothing BORROWS a result string (added at 0.1.5). `patra_result_get_str`
     points into the result set, which `patra_result_free` releases, and
     `str_new` / `str_new_a` / `str_from` / `str_from_a` keep the pointer they are
     given rather than copying it. So neither that call nor a variable assigned
     from it may be handed to one of them — copy it (`str_from_buf`, or
     `alloc_via` + `memcpy`). Both 0.1.4 cases were exactly this: the definitions
     listing segfaulted on ~300 rows, and a principal's tenant read back another
     user's once the next query recycled the freed block.

"Earlier" is textual order within the function, which is what the store's
wrappers look like: `agnostic_store_lock(); var r = _x_locked(...);
agnostic_store_unlock(); return r;`. A lock taken on some branch and not another
would pass this gate — the runtime check is what catches that.

Exits non-zero on any violation. Run from the repo root.
"""
import glob
import re
import sys

STORE = "src/engine/store.cyr"
GETSTR = "patra_result_get_str("
BORROWER = r"\b(str_new|str_new_a|str_from|str_from_a)\s*\("
LOCK = "agnostic_store_lock()"
ACCESSOR = "agnostic_store_db()"


def strip_comment(line):
    """Drop a `#` comment, ignoring `#` inside a string literal."""
    out, in_str, esc = [], False, False
    for ch in line:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out)


def functions(path):
    """Yield (name, first_line, [(lineno, code)]) for every top-level fn."""
    name, start, body = None, 0, []
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        m = re.match(r"^fn\s+(\w+)\s*\(", raw)
        if m:
            if name:
                yield name, start, body
            name, start, body = m.group(1), n, []
        code = strip_comment(raw)
        if name:
            body.append((n, code))
    if name:
        yield name, start, body


def is_locked_name(name):
    return name.endswith("_locked") or name.endswith("_locked_a")


def main():
    files = sorted(glob.glob("src/**/*.cyr", recursive=True))
    fns = {}
    problems = []

    for path in files:
        for n, raw in enumerate(open(path, encoding="utf-8"), 1):
            code = strip_comment(raw)
            if path != STORE and re.search(r"\b_agnostic_store_db\b", code):
                problems.append(f"{path}:{n}: rule 0 — the raw handle global is used outside {STORE}")
        for name, start, body in functions(path):
            fns[name] = (path, start, body)

    # The store-locked set: *_locked functions that fetch the handle, closed over
    # *_locked functions that call one.
    store_locked = {
        nm for nm, (p, s, b) in fns.items()
        if is_locked_name(nm) and any(ACCESSOR in c for _, c in b)
    }
    grew = True
    while grew:
        grew = False
        for nm, (p, s, b) in fns.items():
            if nm in store_locked or not is_locked_name(nm):
                continue
            if any(re.search(r"\b%s\s*\(" % re.escape(t), c) for _, c in b for t in store_locked):
                store_locked.add(nm)
                grew = True

    reads = 0
    for nm, (path, start, body) in sorted(fns.items(), key=lambda kv: (kv[1][0], kv[1][1])):
        # Rule 3 — every file, store.cyr included.
        borrowed = set()
        for n, code in body:
            if GETSTR in code:
                reads += 1
                m = re.match(r"\s*(?:var\s+)?(\w+)\s*=[^=].*\bpatra_result_get_str\s*\(", code)
                if m:
                    borrowed.add(m.group(1))
            if re.search(BORROWER, code):
                src = GETSTR in code or any(re.search(r"\b%s\b" % re.escape(v), code) for v in borrowed)
                if src:
                    problems.append(
                        f"{path}:{n}: rule 3 — `{nm}` wraps a patra result string in a "
                        f"BORROWING Str; it dangles once the result set is freed — copy it")
        if path == STORE:
            continue
        locked_by_name = is_locked_name(nm)
        holds = False
        for n, code in body:
            if LOCK in code:
                holds = True
            if ACCESSOR in code and not (locked_by_name or holds):
                problems.append(
                    f"{path}:{n}: rule 1 — `{nm}` fetches the store handle without "
                    f"taking {LOCK} first, and is not named *_locked")
            for callee in re.findall(r"\b(\w+)\s*\(", code):
                if callee == nm or callee not in store_locked:
                    continue
                if not (locked_by_name or holds):
                    problems.append(
                        f"{path}:{n}: rule 2 — `{nm}` calls store-locked `{callee}` "
                        f"without holding {LOCK}")

    if problems:
        print("store-lock check FAILED — the shared patra handle is reachable without the store lock,")
        print("or a result string outlives its result set:")
        for p in problems:
            print("  " + p)
        print("  See the header of src/engine/store.cyr.")
        return 1
    print(f"store lock OK — {len(store_locked)} store-locked functions, "
          f"every handle fetch and every call to one is under {LOCK}; "
          f"{reads} result-string reads, none borrowed")
    return 0


sys.exit(main())
