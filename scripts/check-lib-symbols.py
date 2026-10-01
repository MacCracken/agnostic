#!/usr/bin/env python3
"""Rule 4 — no two lib/ modules in the COMPILE SET define one constant with two values.

Cyrius has one flat symbol table with last-definition-wins, and the compiler is SILENT
for `var` and for enum members (only a duplicate `fn` warns). A lib/<->lib/ collision
between two dependencies is therefore invisible to the compiler, to Rules 1-3 (which
scan src/), and to every other gate. That is exactly how kavach's BACKEND_COUNT (10)
was silently resolved to ai-hwaccel's 18, defeating a bounds check on a function-pointer
table -- see CHANGELOG 2.0.4.

This fails the build on a duplicate whose VALUES DIVERGE, and reports the rest.
Known-and-filed divergences live in scripts/lib-symbol-allow.txt, one per line, each
required to carry a `#` comment naming the upstream issue.

Each shipped target is checked on its own, with `#ifdef`-style conditionals evaluated
for it: a name declared once per platform arm is one definition on every target, not
two. See TARGETS below.
"""
import re, sys, os, glob, collections

# Platform-exclusive stdlib variants: these define the same names ON PURPOSE and are
# never co-compiled. Excluding them is correct for a duplicate-detection gate.
PLAT = re.compile(r'_(macos|win|windows|agnos|linux_common|aarch64|aarch64_linux|x86_64|x86_64_linux|x86_64_agnos)\.cyr$')

def strip_comments(s):
    r"""Drop `#` comments, respecting quotes.

    ⚠ Required, not cosmetic. A naive non-greedy `\[(.*?)\]` over the raw manifest
    stops at the first `]` -- and these manifests carry comments that mention other
    blocks by name, e.g. "agnosai declares `[deps.sigil]` at 3.12.9" INSIDE the
    stdlib array. That truncated the parsed stdlib list and silently dropped
    modules from the compile set, which is the precise failure mode this gate
    exists to prevent it having.
    """
    out, q = [], None
    for line in s.split("\n"):
        buf = []
        for ch in line:
            if q:
                buf.append(ch)
                if ch == q:
                    q = None
            elif ch in '"\'':
                q = ch; buf.append(ch)
            elif ch == '#':
                break
            else:
                buf.append(ch)
        out.append("".join(buf))
        q = None          # cyml has no multi-line strings here
    return "\n".join(out)

def _array_after(s, key):
    """Text of the bracket-balanced array following `key =`, or None."""
    m = re.search(r'^\s*' + re.escape(key) + r'\s*=\s*\[', s, re.M)
    if not m:
        return None
    i = s.index('[', m.start()); depth = 0
    for j in range(i, len(s)):
        if s[j] == '[': depth += 1
        elif s[j] == ']':
            depth -= 1
            if depth == 0:
                return s[i + 1:j]
    return None

def parse_manifest(path="cyrius.cyml"):
    s = strip_comments(open(path).read())
    arr = _array_after(s, "stdlib")
    stdlib = set(re.findall(r'"([^"]+)"', arr)) if arr else set()
    deps = {}
    for name in re.findall(r'^\[deps\.([A-Za-z0-9_-]+)\]', s, re.M):
        blk = re.search(r'^\[deps\.' + re.escape(name) + r'\](.*?)(?=^\[|\Z)', s, re.S | re.M).group(1)
        tag = (re.search(r'^tag\s*=\s*"([^"]+)"', blk, re.M) or [None, None])[1]
        pth = (re.search(r'^path\s*=\s*"([^"]+)"', blk, re.M) or [None, None])[1]
        marr = _array_after(blk, "modules")
        mods = re.findall(r'"([^"]+)"', marr) if marr else []
        deps[name] = {"tag": tag, "path": pth, "modules": mods}
    return stdlib, deps

def sidecar_leaves(name, info):
    """Stdlib leaves a dep's fold needs, from its dist/<mod>.deps sidecar.
    Looked up in the cyrius dep cache first (present on a CI runner) then the
    sibling checkout (present locally).

    ⚠ The cache is `$CYRIUS_HOME/deps` when CYRIUS_HOME is set -- the empty-cache
    replica that certifies a dep bump runs under exactly that. Reading only
    `~/.cyrius/deps` there found no sidecar, silently shrank the compile set (53 -> 49
    modules at 0.1.7) and checked less than it reported."""
    out = set()
    home = os.environ.get("CYRIUS_HOME", os.path.expanduser("~/.cyrius"))
    for mod in info["modules"]:
        base = mod[:-4] + ".deps" if mod.endswith(".cyr") else mod + ".deps"
        cands = []
        if info["tag"]:
            cands.append(os.path.join(home, "deps", name, info["tag"], base))
            cands.append(os.path.expanduser(f"~/.cyrius/deps/{name}/{info['tag']}/{base}"))
        if info["path"]:
            cands.append(os.path.join(info["path"], base))
        cands.append(os.path.join("..", name, base))
        for c in cands:
            if os.path.exists(c):
                for L in open(c):
                    L = L.strip()
                    if L and not L.startswith("#"):
                        out.add(L)
                break
    return out

def compile_set(stdlib, deps):
    """Every lib/ module that actually reaches the compile unit."""
    names = set(stdlib)
    dist_basenames = set()
    for n, info in deps.items():
        names |= sidecar_leaves(n, info)
        for mod in info["modules"]:
            dist_basenames.add(os.path.basename(mod))

    files = set()
    for n in names:
        p = f"lib/{n}.cyr"
        if os.path.exists(p):
            files.add(p)
    # Every non-stdlib file in lib/ is a dep dist that `cyrius deps` provisioned --
    # including transitive ones no [deps.*] block names directly (libro arrives via
    # bote). They all compile, so they all count.
    # Locate the pinned stdlib snapshot, so "not in the snapshot" identifies a dep
    # dist. CI's installer lays out $HOME/.cyrius/{bin,lib} and does NOT necessarily
    # create versions/<pin>/lib, so try the layouts in order of specificity. If none
    # is found we must NOT quietly fall through to a dist_basenames-only scan: that
    # would silently drop the TRANSITIVE dists (libro arrives via bote), making this
    # gate weaker in CI than on a developer machine -- the exact shape of blind spot
    # it exists to close.
    snap = None
    mp = re.search(r'^cyrius\s*=\s*"([^"]+)"', open("cyrius.cyml").read(), re.M)
    home = os.environ.get("CYRIUS_HOME", os.path.expanduser("~/.cyrius"))
    cands = []
    if mp:
        cands.append(os.path.join(home, "versions", mp.group(1), "lib"))
        cands.append(os.path.expanduser(f"~/.cyrius/versions/{mp.group(1)}/lib"))
    cands.append(os.path.join(home, "lib"))
    cands.append(os.path.expanduser("~/.cyrius/lib"))
    for cand in cands:
        if os.path.isdir(cand) and glob.glob(os.path.join(cand, "*.cyr")):
            snap = {os.path.basename(f) for f in glob.glob(os.path.join(cand, "*.cyr"))}
            break
    if snap is None:
        print("error: cannot locate the pinned Cyrius stdlib snapshot; tried:", file=sys.stderr)
        for c in cands:
            print(f"         {c}", file=sys.stderr)
        print("       Without it, transitive dep dists cannot be told from stdlib modules",
              file=sys.stderr)
        print("       and this check would silently cover less than it appears to.",
              file=sys.stderr)
        return 1
    for p in glob.glob("lib/*.cyr"):
        b = os.path.basename(p)
        if b in dist_basenames or (snap is not None and b not in snap):
            files.add(p)
    return {f for f in sorted(files) if not PLAT.search(f)}

# --- Preprocessor conditionals, evaluated per shipped target ----------------------
# ⚠ A file is not one set of definitions; it is one set PER TARGET. sigil 3.13.5 (the
# cyrius 6.6.12 fold) declares eight errno names twice -- the BSD values under
# `#ifdef CYRIUS_TARGET_MACOS`, the Linux ones under `#ifndef CYRIUS_TARGET_MACOS` --
# and exactly one arm is ever compiled. Reading every line as live reported both arms
# as a divergence from kavach, which declares the Linux values: a false positive on
# every target this repo builds. Allow-listing the eight names would also have hidden
# a REAL future divergence of any of them, so the conditionals are evaluated instead,
# once per target, and a divergence on ANY shipped target fails.
#
# The targets are what CI builds: the native x86_64 build and the aarch64 cross-build.
# (aarch64 is withheld from releases since 0.1.7 — see `[release]` in cyrius.cyml — but
# CI still compiles it so it can come back; it is checked here for the same reason.)
# The compiler defines exactly one CYRIUS_TARGET_* per build, plus CYRIUS_ARCH_X86 or
# CYRIUS_ARCH_AARCH64 (cyrius-guide, "Preprocessor").
TARGETS = {
    "x86_64-linux":  ({"CYRIUS_TARGET_LINUX", "CYRIUS_ARCH_X86"}, {"x86_64", "linux"}),
    "aarch64-linux": ({"CYRIUS_TARGET_LINUX", "CYRIUS_ARCH_AARCH64"}, {"aarch64", "linux"}),
}

_DIRECTIVE = re.compile(
    r'^\s*#(ifdef|ifndef|ifplat|if|elif|else|endif|endplat|define|undef)\b\s*([A-Za-z_0-9]*)')

def active_lines(path, target):
    """The file's lines for `target`, with every inactive arm and every directive line
    blanked -- blanked rather than dropped, so reported line numbers stay true.

    Follows the compiler's own reading: a line inside a multi-line string is string
    DATA even when it begins `#ifdef` (cyrius 6.6.6, `PP_LEXST`), so string state is
    carried across lines here too. An `#if` with an expression this does not evaluate
    keeps BOTH arms live, which is how every line was read before conditionals were
    understood -- an unknown form can make the gate stricter, never blind.
    """
    defs, plats = set(TARGETS[target][0]), TARGETS[target][1]
    out, stack, active, in_str = [], [], True, False
    for L in open(path, errors="replace").read().split("\n"):
        m = None if in_str else _DIRECTIVE.match(L)
        if m:
            d, arg = m.group(1), m.group(2)
            if d in ("ifdef", "ifndef", "ifplat", "if"):
                cond = {"ifdef": arg in defs, "ifndef": arg not in defs,
                        "ifplat": arg in plats, "if": True}[d]
                arm = active and cond
                # frame: [parent active, an arm already taken, condition unknown]
                stack.append([active, arm, d == "if"])
                active = arm
            elif d in ("elif", "else") and stack:
                parent, taken, unknown = stack[-1]
                if unknown:
                    arm = parent
                else:
                    arm = parent and not taken and (d == "else" or arg in defs)
                stack[-1][1] = taken or arm
                active = arm
            elif d in ("endif", "endplat") and stack:
                active = stack.pop()[0]
            elif d == "define" and active and arg:
                defs.add(arg)
            elif d == "undef" and active and arg:
                defs.discard(arg)
            out.append("")
            continue
        out.append(L if active else "")
        i, n = 0, len(L)
        while i < n:
            ch = L[i]
            if in_str:
                if ch == "\\":
                    i += 2
                    continue
                if ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "'":
                j = i + 1
                while j < n and L[j] != "'":
                    j += 2 if L[j] == "\\" else 1
                i = j
            elif ch == "#":
                break
            i += 1
    return out

def constants(path, target):
    """(name, value, kind) for every top-level `var` and every enum member live on `target`."""
    out, lines, i = [], active_lines(path, target), 0
    while i < len(lines):
        L = lines[i]
        m = re.match(r'^var\s+([A-Za-z_]\w*)\s*=\s*([^;]+);', L)
        if m:
            out.append((m.group(1), m.group(2).strip(), "var"))
        if re.match(r'^enum\s+[A-Za-z_]\w*', L):
            j, auto = i + 1, 0
            while j < len(lines) and not re.match(r'^\}', lines[j]):
                mm = re.match(r'^\s*([A-Za-z_]\w*)\s*(?:=\s*([^,;\n#]+))?\s*[,;]?\s*(?:#.*)?$', lines[j])
                if mm and mm.group(1):
                    raw = (mm.group(2) or "").strip()
                    if raw:
                        val = raw
                        try:
                            auto = int(raw, 0) + 1
                        except ValueError:
                            auto += 1
                    else:
                        val = str(auto); auto += 1
                    out.append((mm.group(1), val, "enum-member"))
                j += 1
            i = j
        i += 1
    return out

def main():
    if not os.path.exists("cyrius.cyml"):
        print("lib-symbol check: no cyrius.cyml", file=sys.stderr); return 1
    stdlib, deps = parse_manifest()
    files = compile_set(stdlib, deps)
    if not files:
        print("lib-symbol check: empty compile set — is lib/ provisioned?", file=sys.stderr); return 1

    allow = {}
    ap = "scripts/lib-symbol-allow.txt"
    if os.path.exists(ap):
        for L in open(ap):
            L = L.strip()
            if not L or L.startswith("#"):
                continue
            nm, _, why = L.partition("#")
            allow[nm.strip()] = why.strip()

    rc = 0
    for target in TARGETS:
        seen = collections.defaultdict(list)
        for f in sorted(files):
            for nm, val, kind in constants(f, target):
                seen[nm].append((val, os.path.basename(f), kind))

        diverge, same = [], 0
        for nm, e in seen.items():
            if len({f for _, f, _ in e}) > 1:
                if len({v for v, _, _ in e}) > 1:
                    diverge.append((nm, e))
                else:
                    same += 1

        unflagged = [(n, e) for n, e in sorted(diverge) if n not in allow]
        flagged   = [(n, e) for n, e in sorted(diverge) if n in allow]

        print(f"lib-symbol check [{target}]: {len(files)} modules in the compile set, "
              f"{len(seen)} constants, {same} benign duplicate(s)")
        for nm, e in flagged:
            print(f"  ALLOWED  {nm} — {allow[nm]}")
            for v, f, k in e:
                print(f"             {v:<24} {f} ({k})")
        if unflagged:
            print()
            print(f"error: on {target}, a constant is defined more than once in the compile set")
            print("       WITH DIFFERENT VALUES. Cyrius resolves this silently (last definition")
            print("       wins) — no warning is emitted for `var` or for enum members, so nothing")
            print("       else in the build will catch it.")
            for nm, e in unflagged:
                print(f"  {nm}")
                for v, f, k in e:
                    print(f"      {v:<24} {f} ({k})")
            print()
            print("       Fix it upstream in the owning library (prefix the name), then add it to")
            print("       scripts/lib-symbol-allow.txt with the issue reference while the fix lands.")
            rc = 1
    return rc

sys.exit(main())
