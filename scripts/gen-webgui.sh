#!/usr/bin/env bash
# gen-webgui.sh — embed src/webgui/ (the shell and every plugin) into a Cyrius source file.
#
# Same reason `gen-presets.sh` exists: Cyrius has no `include_str!`, so a page has to be
# turned into source before `include` can reach it.
#
#   ./scripts/gen-webgui.sh            regenerate src/webgui_data.cyr
#   ./scripts/gen-webgui.sh --check    fail if the checked-in file has drifted
#   ./scripts/gen-webgui.sh --sync-kit rewrite every plugin page's copy of the bridge client
#                                      from src/webgui/kit/host.js, then regenerate
#
# ## One bridge client, carried verbatim by every plugin (0.1.10)
#
# A plugin page is one self-contained file (ADR 0004), so the client side of the host bridge —
# `class Host` — cannot be shared by reference: each page carries a copy. Copies drift. So the
# canonical source is `src/webgui/kit/host.js`, each page carries it between its
# `agnostic-kit:host begin` / `end` markers, and this script refuses a page whose copy differs
# from the canonical one by a single byte — and a page that asks the server for anything
# (non-empty `permissions`) without carrying it. `--sync-kit` rewrites the copies.
#
# The generated file IS committed, so a clone builds without running this, and
# `scripts/check-clean.sh` runs `--check` so an edited page cannot ship stale.
#
# ## Each page is embedded VERBATIM, as one multi-line string literal
#
# `gen-presets.sh` breaks its literals with `\`-continuations, which is safe only because
# it breaks between JSON tokens: a continuation keeps the newline AND `cyrius fmt`
# indents the next line, so the indentation lands inside the string. That would rewrite
# a page. So here every newline is a RAW newline inside the literal (legal; and since
# cyrius 6.6.6 a line inside a string that starts `#ifdef` is string data, not a
# directive), and only `\`, `"`, tabs and other control bytes are escaped. The literal's
# bytes are the file's bytes — `tests/webgui.tcyr` re-hashes them against the SHA-256
# recorded here, so an escaping slip fails a suite rather than serving a damaged page.
#
# ## Each page's Content-Security-Policy is computed here
#
# Only this script sees the exact bytes of a page's inline `<script>` blocks, so it is
# what admits them, by hash, and nothing else: no external script, no inline event
# handler, no `javascript:` URL, no external resource. A page that needs one is refused
# here, with the reason, instead of rendering blank in a browser under a CSP that
# blocked it.
#
# ⚠ THE PLUGIN ORDER IS DELIBERATE: it is the order `GET /api/v1/plugins` lists them and
# the shell shows their tabs. PLUGINS below is that order, and every directory under
# src/webgui/plugins/ must appear in it — a plugin cannot be added by accident.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

OUT="src/webgui_data.cyr"
MODE="${1:-generate}"

tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/gen-webgui.XXXXXX") || exit 2
trap 'rm -rf "$tmpdir"' EXIT
gen="$tmpdir/webgui_data.cyr"

python3 - "$gen" "$MODE" <<'PY' || { echo "gen-webgui: generation failed" >&2; exit 1; }
import base64
import hashlib
import json
import os
import re
import sys

OUT = sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else "generate"

# The bridge client every plugin carries (0.1.10) — see the header.
KIT_FILE = "src/webgui/kit/host.js"
KIT_BEGIN = "/* agnostic-kit:host begin"
KIT_END = "/* agnostic-kit:host end */"

# The plugins, in listing order. Each is src/webgui/plugins/<id>/ holding a
# `plugin.json` manifest and the page it names.
PLUGINS = ["swarm", "crews", "library", "audit"]

# A manifest carries exactly these keys — the allow-list rule the API's request
# decoders follow (src/http/codec.cyr): an unknown key is an error, never ignored.
MANIFEST_KEYS = ["id", "name", "description", "version", "data", "entry", "permissions"]
STRING_KEYS = ["id", "name", "description", "version", "data", "entry"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
# `mixed`: the view shows both, and labels each mission itself (0.1.8).
DATA_KINDS = ("simulated", "live", "mixed")

# What a plugin may ask the server for (ADR 0005, ADR 0007). ONE file defines the
# vocabulary — each permission's name, the words Settings shows for it, and the exact
# routes it grants — and everything else reads it: this generator validates manifests
# against it and embeds it, the server enforces it on every request a plugin makes
# (`X-Agnostic-Plugin`), and the shell shows its words. Adding a permission is an edit
# to that file (and the docs), never to code in three places.
PERMISSIONS_FILE = "src/webgui/permissions.json"
PERM_NAME_RE = re.compile(r"^[a-z]+(:[a-z]+)?$")
ROUTE_RE = re.compile(r"^(GET|POST|PUT|DELETE) (/(?:[a-z0-9._-]+|:[a-z]+))+$")

def fail(msg):
    sys.stderr.write("gen-webgui: " + msg + "\n")
    sys.exit(2)

def load_permissions():
    try:
        raw = json.load(open(PERMISSIONS_FILE))
    except (OSError, ValueError) as e:
        fail("%s: %s" % (PERMISSIONS_FILE, e))
    if not isinstance(raw, dict) or not raw:
        fail("%s: the vocabulary is a non-empty JSON object" % PERMISSIONS_FILE)
    for name, p in raw.items():
        if not PERM_NAME_RE.match(name):
            fail("%s: permission %r must match %s" % (PERMISSIONS_FILE, name, PERM_NAME_RE.pattern))
        if not isinstance(p, dict) or sorted(p) != ["grants", "routes"]:
            fail("%s: %s must hold exactly `grants` and `routes`" % (PERMISSIONS_FILE, name))
        if not isinstance(p["grants"], str) or not p["grants"] or len(p["grants"]) > 120:
            fail("%s: %s.grants must be a sentence of 1-120 characters" % (PERMISSIONS_FILE, name))
        routes = p["routes"]
        if not isinstance(routes, list) or not routes or len(set(routes)) != len(routes):
            fail("%s: %s.routes must be a non-empty list without repeats" % (PERMISSIONS_FILE, name))
        for r in routes:
            if not isinstance(r, str) or not ROUTE_RE.match(r):
                fail("%s: %s: route %r is not `METHOD /path` with literal or :name segments"
                     % (PERMISSIONS_FILE, name, r))
            segs = r.split(" ", 1)[1].split("/")[1:]
            if not r.split(" ", 1)[1].startswith("/api/v1/"):
                fail("%s: %s: route %r is not under /api/v1/ — a plugin reaches the API and "
                     "nothing else" % (PERMISSIONS_FILE, name, r))
            for i, seg in enumerate(segs):
                if seg == ":self" and segs[:i] != ["api", "v1", "plugins"]:
                    fail("%s: %s: `:self` may only follow /api/v1/plugins/ — it names the "
                         "asking plugin's own id" % (PERMISSIONS_FILE, name))
    return raw

PERMISSION_TABLE = load_permissions()
PERMISSIONS = tuple(PERMISSION_TABLE)

root = "src/webgui/plugins"
on_disk = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
if on_disk != sorted(PLUGINS):
    fail("src/webgui/plugins/ does not match PLUGINS in scripts/gen-webgui.sh, so a\n"
         "plugin's place in the listing would be accidental. List it deliberately.\n"
         "  on disk but not listed: %s\n  listed but not on disk: %s"
         % (", ".join(sorted(set(on_disk) - set(PLUGINS))) or "none",
            ", ".join(sorted(set(PLUGINS) - set(on_disk))) or "none"))

def kit_span(text):
    """(start, end) of the kit block in `text`, or None when it carries none."""
    b = text.find(KIT_BEGIN)
    if b < 0:
        return None
    e = text.find(KIT_END, b)
    if e < 0:
        fail("a page opens the bridge client block (%r) and never closes it (%r)" % (KIT_BEGIN, KIT_END))
    return (b, e + len(KIT_END))

try:
    KIT = open(KIT_FILE, encoding="utf-8").read()
except OSError as e:
    fail("%s: %s" % (KIT_FILE, e))
_ks = kit_span(KIT)
if _ks is None or _ks != (0, len(KIT.rstrip("\n"))):
    fail("%s: must be exactly one bridge client block, from %r to %r" % (KIT_FILE, KIT_BEGIN, KIT_END))
KIT = KIT[_ks[0]:_ks[1]]

def check_kit(path, text, permissions):
    span = kit_span(text)
    if span is None:
        if permissions:
            fail("%s: asks the server for something (permissions %s) but carries no bridge client — "
                 "paste %s between the agnostic-kit:host markers, or run --sync-kit"
                 % (path, ", ".join(permissions), KIT_FILE))
        return
    if text[span[0]:span[1]] != KIT:
        fail("%s: its copy of the bridge client differs from %s — run "
             "./scripts/gen-webgui.sh --sync-kit" % (path, KIT_FILE))

def check_page(path, text):
    """Refuse what the page's CSP would block, and what the src/ gates would misread."""
    if "\0" in text:
        fail("%s: contains a NUL byte; an embedded page is a NUL-terminated string" % path)
    if "\r" in text:
        fail("%s: contains a carriage return; save it with LF line endings — a browser "
             "normalises CR before hashing a script, so the CSP hash would not match" % path)
    for n, line in enumerate(text.split("\n"), 1):
        m = re.match(r"(fn|var|enum|struct|include)\b", line)
        if m:
            fail("%s:%d: a line starting `%s` at column 0 reads as a Cyrius definition to "
                 "the gates that scan src/ line by line; indent it" % (path, n, m.group(1)))
    if re.search(r"<script\b[^>]*\bsrc\s*=", text, re.I):
        fail("%s: loads an external script; inline it — the CSP admits only the page's "
             "own inline scripts, by hash" % path)
    m = re.search(r"<[a-zA-Z][^<>]*\son[a-z]+\s*=", text)
    if m:
        fail("%s: has an inline event handler (%s…); use addEventListener — the CSP "
             "does not run inline handlers" % (path, m.group(0)[:40]))
    if re.search(r"javascript:", text, re.I):
        fail("%s: uses a javascript: URL, which the CSP does not run" % path)
    ext = (re.search(r"<link\b[^>]*\bhref\s*=\s*[\"']?(https?:|//)", text, re.I)
           or re.search(r"<(img|iframe|source|video|audio|embed|object)\b[^>]*\bsrc\s*=\s*[\"']?(https?:|//)", text, re.I)
           or re.search(r"@import\b", text)
           or re.search(r"url\(\s*[\"']?(https?:|//)", text, re.I))
    if ext:
        fail("%s: loads an external resource (%s…); a page is served with "
             "default-src 'none' and must be self-contained" % (path, ext.group(0)[:40]))

def script_hashes(text):
    out = []
    for m in re.finditer(r"<script(\s[^>]*)?>(.*?)</script\s*>", text, re.S | re.I):
        digest = hashlib.sha256(m.group(2).encode("utf-8")).digest()
        out.append("'sha256-%s'" % base64.b64encode(digest).decode("ascii"))
    return out

def csp(hashes, shell):
    parts = ["default-src 'none'",
             "script-src " + (" ".join(hashes) if hashes else "'none'"),
             "style-src 'unsafe-inline'"]
    if shell:
        # The shell frames plugin pages from its own origin and nothing frames it.
        parts += ["img-src data:", "connect-src 'self'", "frame-src 'self'",
                  "frame-ancestors 'none'"]
    else:
        # A plugin page may be framed by the shell (same origin) and nothing else, and
        # it connects to NOTHING: every request goes through the shell's host bridge,
        # which checks it against the plugin's `permissions` (ADR 0005).
        parts += ["connect-src 'none'", "frame-ancestors 'self'"]
    parts += ["base-uri 'none'", "form-action 'none'"]
    return "; ".join(parts)

def cyr_escape(text):
    """Text -> the inside of a Cyrius string literal. Newlines stay raw."""
    out = []
    for ch in text:
        o = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\n")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or o == 0x7F:
            out.append("\\x%02x" % o)
        else:
            out.append(ch)
    return "".join(out)

pages = []   # (relative path, raw bytes, text, csp)

def add_page(rel, shell):
    path = "src/webgui/" + rel
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        fail("%s: not UTF-8 (%s)" % (path, e))
    check_page(path, text)
    pages.append((rel, raw, text, csp(script_hashes(text), shell)))
    return len(pages) - 1

add_page("index.html", True)          # page 0 is always the shell

manifests = []
for pid in PLUGINS:
    mpath = "%s/%s/plugin.json" % (root, pid)
    try:
        m = json.load(open(mpath))
    except (OSError, ValueError) as e:
        fail("%s: %s" % (mpath, e))
    if not isinstance(m, dict):
        fail("%s: a manifest is a JSON object" % mpath)
    unknown = sorted(set(m) - set(MANIFEST_KEYS))
    missing = [k for k in MANIFEST_KEYS if k not in m]
    if unknown or missing:
        fail("%s: unknown key(s) %s, missing key(s) %s"
             % (mpath, ", ".join(unknown) or "none", ", ".join(missing) or "none"))
    for k in STRING_KEYS:
        if not isinstance(m[k], str) or not m[k]:
            fail("%s: `%s` must be a non-empty string" % (mpath, k))
    perms = m["permissions"]
    if not isinstance(perms, list) or not all(isinstance(x, str) for x in perms):
        fail("%s: `permissions` must be a list of strings (it may be empty)" % mpath)
    unknown_perms = [x for x in perms if x not in PERMISSIONS]
    if unknown_perms or len(set(perms)) != len(perms):
        fail("%s: `permissions` may hold each of %s once; got %s"
             % (mpath, ", ".join(PERMISSIONS), ", ".join(perms) or "none"))
    if m["id"] != pid or not ID_RE.match(pid):
        fail("%s: `id` must equal its directory name and match [a-z0-9][a-z0-9-]{0,31}" % mpath)
    if len(m["name"]) > 64:
        fail("%s: `name` is longer than 64 characters" % mpath)
    if len(m["description"]) > 512:
        fail("%s: `description` is longer than 512 characters" % mpath)
    if not VERSION_RE.match(m["version"]):
        fail("%s: `version` must be MAJOR.MINOR.PATCH" % mpath)
    if m["data"] not in DATA_KINDS:
        fail("%s: `data` must be one of %s — say whether the view shows simulated or live "
             "data (or `mixed`, when it labels each mission itself), because a simulation "
             "reads exactly like real work" % (mpath, ", ".join(DATA_KINDS)))
    if m["entry"] != "index.html":
        fail("%s: `entry` must be index.html — a plugin is one self-contained page" % mpath)
    doc = {k: m[k] for k in MANIFEST_KEYS}
    page = "%s/%s/index.html" % (root, pid)
    if MODE == "--sync-kit":
        text = open(page, encoding="utf-8").read()
        span = kit_span(text)
        if span is not None and text[span[0]:span[1]] != KIT:
            open(page, "w", encoding="utf-8").write(text[:span[0]] + KIT + text[span[1]:])
            sys.stderr.write("gen-webgui: synced the bridge client into %s\n" % page)
    check_kit(page, open(page, encoding="utf-8").read(), perms)
    doc["asset"] = add_page("plugins/%s/index.html" % pid, False)
    manifests.append(doc)

L = []
L.append("# " + "=" * 78)
L.append("# agnostic/webgui_data — GENERATED FILE. Do not edit by hand.")
L.append("#")
L.append("# Regenerate with `./scripts/gen-webgui.sh`; its `--check` mode fails when this file")
L.append("# has drifted from `src/webgui/`, and `scripts/check-clean.sh` runs it.")
L.append("#")
L.append("# Each page is ONE multi-line string literal holding the source file's bytes")
L.append("# verbatim: newlines are raw, and only `\\`, `\"`, tabs and control bytes are")
L.append("# escaped. The byte count and SHA-256 below are the source file's, and")
L.append("# `tests/webgui.tcyr` re-hashes the embedded bytes against them.")
L.append("#")
L.append("# Each page's Content-Security-Policy admits its own inline scripts by hash and")
L.append("# nothing else; only the generator sees those bytes, so it computes the policy.")
L.append("# " + "=" * 78)
L.append("")
L.append("# How many pages are embedded. Page 0 is the shell.")
L.append("var AGNOSTIC_WEBGUI_ASSET_COUNT = %d;" % len(pages))
L.append("")
L.append("# How many plugin manifests are embedded.")
L.append("var AGNOSTIC_WEBGUI_PLUGIN_COUNT = %d;" % len(manifests))
for i, (rel, raw, text, policy) in enumerate(pages):
    L.append("")
    L.append("# --- src/webgui/%s — %d bytes " % (rel, len(raw)) + "-" * max(0, 52 - len(rel) - len(str(len(raw)))))
    L.append('var _AGNOSTIC_WEBGUI_ASSET_%02d = "%s";' % (i, cyr_escape(text)))
L.append("")

def chain(fn, doc, values):
    for line in doc:
        L.append("# " + line if line else "#")
    L.append("fn %s(i): i64 {" % fn)
    for n, v in enumerate(values):
        L.append("    if (i == %d) { return %s; }" % (n, v))
    L.append("    return 0;")
    L.append("}")
    L.append("")

q = lambda s: '"' + cyr_escape(s) + '"'
chain("agnostic_webgui_asset_bytes",
      ["The `i`th page's bytes as a NUL-terminated C string, or 0 when `i` is out of range.",
       "",
       "A chain rather than a table because a `var` array of string literals has no",
       "spelling in Cyrius."],
      ["_AGNOSTIC_WEBGUI_ASSET_%02d" % n for n in range(len(pages))])
chain("agnostic_webgui_asset_len",
      ["The `i`th page's length in bytes, as the generator counted it, or 0."],
      [str(len(raw)) for _, raw, _, _ in pages])
chain("agnostic_webgui_asset_sha256",
      ["The SHA-256 of the `i`th page's source file, lowercase hex, or 0."],
      [q(hashlib.sha256(raw).hexdigest()) for _, raw, _, _ in pages])
chain("agnostic_webgui_asset_path",
      ["The `i`th page's source path, relative to `src/webgui/`, or 0."],
      [q(rel) for rel, _, _, _ in pages])
chain("agnostic_webgui_asset_csp",
      ["The Content-Security-Policy the `i`th page is served with, or 0."],
      [q(policy) for _, _, _, policy in pages])
L.append("# The plugin permission vocabulary, `src/webgui/permissions.json`, as compact JSON:")
L.append("# `{name: {grants, routes[]}}`. Parsed once at mount (`src/webgui/plugins.cyr`), which")
L.append("# enforces it on every request a plugin makes (ADR 0007).")
L.append("fn agnostic_webgui_permissions_json(): i64 {")
L.append("    return %s;" % q(json.dumps(PERMISSION_TABLE, separators=(",", ":"), ensure_ascii=False)))
L.append("}")
L.append("")
chain("agnostic_webgui_plugin_manifest",
      ["The `i`th plugin's manifest as compact JSON, or 0. `asset` is the page the",
       "generator resolved its `entry` to."],
      [q(json.dumps(m, separators=(",", ":"), ensure_ascii=False)) for m in manifests])

with open(OUT, "w") as f:
    f.write("\n".join(L).rstrip("\n") + "\n")
PY

# `cyrius fmt` formats IN PLACE and prints nothing on stdout — read the file back, never
# its stdout (agnosai once shipped a `--check` that compared against an empty capture).
# Running it here is what keeps this generator and `check-clean.sh`'s fmt gate agreeing.
if ! cyrius fmt "$gen" >/dev/null 2>&1; then
    echo "gen-webgui: cyrius fmt failed on the generated source" >&2
    exit 1
fi

if [ "$MODE" = "--check" ]; then
    if [ ! -f "$OUT" ]; then
        echo "gen-webgui: $OUT is missing — run ./scripts/gen-webgui.sh" >&2
        exit 1
    fi
    if ! cmp -s "$OUT" "$gen"; then
        echo "gen-webgui: $OUT is stale — run ./scripts/gen-webgui.sh" >&2
        diff -u "$OUT" "$gen" | head -40 >&2
        exit 1
    fi
    echo "gen-webgui: $OUT is up to date"
    exit 0
fi

cp "$gen" "$OUT"
echo "gen-webgui: wrote $OUT"
