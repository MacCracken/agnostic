#!/usr/bin/env python3
"""check-embedded.py — what `[embed]` puts in the binary is what should be there.

`cyrius.cyml`'s `[embed]` table compiles each file in as it stands, so nothing is generated and nothing
can fall behind. That leaves what a compiler cannot know, which used to be the generators' job and is
this gate's:

  * the table names every file that should be embedded and no other, and each name is used, so a new
    preset or plugin cannot be left out, or carried for nothing;
  * each plugin's page and manifest stand in the same place in `src/webgui/assets.cyr`;
  * every manifest, and the permission vocabulary, says what the loader and the shell rely on;
  * each page would run under the policy `src/webgui/plugins.cyr` gives it. A page that loads an external
    resource or carries an inline handler fails HERE, not blank in a browser;
  * each plugin page carries the bridge client byte for byte.

    scripts/check-embedded.py             check, and exit 1 with every fault
    scripts/check-embedded.py --sync-kit  rewrite each page's copy of the bridge client first

A plugin page is one self-contained file (ADR 0004), so the client side of the host bridge cannot be
shared by reference. The canonical source is `src/webgui/kit/host.js`, and each page carries it between
its `agnostic-kit:host begin` / `end` markers.
"""
import json
import os
import re
import sys

MANIFEST = "cyrius.cyml"
ASSETS = "src/webgui/assets.cyr"
PLUGINS_DIR = "src/webgui/plugins"
PRESETS_DIR = "src/presets"
PERMISSIONS_FILE = "src/webgui/permissions.json"

KIT_FILE = "src/webgui/kit/host.js"
KIT_BEGIN = "/* agnostic-kit:host begin"
KIT_END = "/* agnostic-kit:host end */"

# A manifest carries exactly these keys — the allow-list rule the API's request decoders follow
# (src/http/codec.cyr): an unknown key is an error, never ignored.
MANIFEST_KEYS = ["id", "name", "description", "version", "data", "entry", "permissions"]
STRING_KEYS = ["id", "name", "description", "version", "data", "entry"]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
# `mixed`: the view shows both, and labels each mission itself (0.1.8).
DATA_KINDS = ("simulated", "live", "mixed")

PERM_NAME_RE = re.compile(r"^[a-z]+(:[a-z]+)?$")
ROUTE_RE = re.compile(r"^(GET|POST|PUT|DELETE) (/(?:[a-z0-9._-]+|:[a-z]+))+$")

# What `agnostic_webgui_csp` reads as a script.
SCRIPT_OPEN_RE = re.compile(r"<script[\s/>][^>]*>|<script>", re.I)
SCRIPT_CLOSE_RE = re.compile(r"</script[\s/>][^>]*>|</script>", re.I)

faults = []


def fault(msg):
    faults.append(msg)


def embed_table():
    """`{name: path}` from the manifest's `[embed]` table."""
    table, inside = {}, False
    for n, line in enumerate(open(MANIFEST, encoding="utf-8"), 1):
        line = line.strip()
        if line.startswith("["):
            inside = line == "[embed]"
            continue
        if not inside or not line or line.startswith("#"):
            continue
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*) = "([^"]+)"$', line)
        if not m:
            fault("%s:%d: not `NAME = \"path\"`: %s" % (MANIFEST, n, line))
            continue
        if m.group(1) in table:
            fault("%s: %s is declared twice" % (MANIFEST, m.group(1)))
        table[m.group(1)] = m.group(2)
    return table


def expected_files():
    """Every file that belongs in the binary, from the tree."""
    out = {PERMISSIONS_FILE, "src/webgui/index.html"}
    for f in sorted(os.listdir(PRESETS_DIR)):
        if f.endswith(".json"):
            out.add("%s/%s" % (PRESETS_DIR, f))
    for d in sorted(os.listdir(PLUGINS_DIR)):
        if os.path.isdir(os.path.join(PLUGINS_DIR, d)):
            out.add("%s/%s/index.html" % (PLUGINS_DIR, d))
            out.add("%s/%s/plugin.json" % (PLUGINS_DIR, d))
    return out


def check_table(table):
    paths = list(table.values())
    for p in sorted(set(p for p in paths if paths.count(p) > 1)):
        fault("%s: %s is embedded twice" % (MANIFEST, p))
    want, have = expected_files(), set(paths)
    for p in sorted(want - have):
        fault("%s: `[embed]` does not name %s, so the binary would be without it" % (MANIFEST, p))
    for p in sorted(have - want):
        fault("%s: `[embed]` names %s, which is not a preset or a WebGUI file" % (MANIFEST, p))
    source = ""
    for base, _, files in os.walk("src"):
        for f in files:
            if f.endswith(".cyr"):
                source += open(os.path.join(base, f), encoding="utf-8").read()
    for name in sorted(table):
        if not re.search(r"\b%s\(\)" % re.escape(name), source):
            fault("%s: %s is embedded and nothing under src/ reads it" % (MANIFEST, name))


def chain(text, fn):
    """The embed names function `fn` answers, by arm, as `[(index, NAME), …]`."""
    m = re.search(r"^fn %s\(i\): i64 \{\n(.*?)^\}" % re.escape(fn), text, re.S | re.M)
    if not m:
        fault("%s: no %s" % (ASSETS, fn))
        return []
    return [(int(i), n) for i, n in re.findall(r"if \(i == (\d+)\) \{ return ([A-Z0-9_a-z]+)\(\); \}", m.group(1))]


def check_assets(table):
    """Each plugin's page stands one past its manifest, and each page's length is its own."""
    text = open(ASSETS, encoding="utf-8").read()
    pages = chain(text, "agnostic_webgui_asset_bytes")
    lens = chain(text, "agnostic_webgui_asset_len")
    manifests = chain(text, "agnostic_webgui_plugin_manifest")
    if [(i, n + "_len") for i, n in pages] != lens:
        fault("%s: a page's length is not the same page's: the two chains differ" % ASSETS)
    if [i for i, _ in pages] != list(range(len(pages))):
        fault("%s: agnostic_webgui_asset_bytes skips an index" % ASSETS)
    if [i for i, _ in manifests] != list(range(len(manifests))):
        fault("%s: agnostic_webgui_plugin_manifest skips an index" % ASSETS)
    for var, value in (("AGNOSTIC_WEBGUI_ASSET_COUNT", len(pages)), ("AGNOSTIC_WEBGUI_PLUGIN_COUNT", len(manifests))):
        m = re.search(r"^var %s = (\d+);" % var, text, re.M)
        if not m or int(m.group(1)) != value:
            fault("%s: %s is not %d" % (ASSETS, var, value))
    if pages and table.get(pages[0][1]) != "src/webgui/index.html":
        fault("%s: page 0 must be the shell" % ASSETS)
    for i, name in manifests:
        path = table.get(name, "")
        page = table.get(pages[i + 1][1], "") if i + 1 < len(pages) else ""
        if os.path.dirname(path) != os.path.dirname(page) or not path:
            fault("%s: manifest %d is %s and page %d is %s: a plugin's page is the one past its own place"
                  % (ASSETS, i, path or name, i + 1, page or "missing"))


def load_permissions():
    try:
        raw = json.load(open(PERMISSIONS_FILE, encoding="utf-8"))
    except (OSError, ValueError) as e:
        fault("%s: %s" % (PERMISSIONS_FILE, e))
        return {}
    if not isinstance(raw, dict) or not raw:
        fault("%s: the vocabulary is a non-empty JSON object" % PERMISSIONS_FILE)
        return {}
    for name, p in raw.items():
        if not PERM_NAME_RE.match(name):
            fault("%s: permission %r must match %s" % (PERMISSIONS_FILE, name, PERM_NAME_RE.pattern))
        if not isinstance(p, dict) or sorted(p) != ["grants", "routes"]:
            fault("%s: %s must hold exactly `grants` and `routes`" % (PERMISSIONS_FILE, name))
            continue
        if not isinstance(p["grants"], str) or not p["grants"] or len(p["grants"]) > 120:
            fault("%s: %s.grants must be a sentence of 1-120 characters" % (PERMISSIONS_FILE, name))
        routes = p["routes"]
        if not isinstance(routes, list) or not routes or len(set(routes)) != len(routes):
            fault("%s: %s.routes must be a non-empty list without repeats" % (PERMISSIONS_FILE, name))
            continue
        for r in routes:
            if not isinstance(r, str) or not ROUTE_RE.match(r):
                fault("%s: %s: route %r is not `METHOD /path` with literal or :name segments"
                      % (PERMISSIONS_FILE, name, r))
                continue
            path = r.split(" ", 1)[1]
            segs = path.split("/")[1:]
            if not path.startswith("/api/v1/"):
                fault("%s: %s: route %r is not under /api/v1/ — a plugin reaches the API and nothing else"
                      % (PERMISSIONS_FILE, name, r))
            for i, seg in enumerate(segs):
                if seg == ":self" and segs[:i] != ["api", "v1", "plugins"]:
                    fault("%s: %s: `:self` may only follow /api/v1/plugins/ — it names the asking "
                          "plugin's own id" % (PERMISSIONS_FILE, name))
    return raw


def kit_span(text, path):
    """(start, end) of the kit block in `text`, or None when it carries none."""
    b = text.find(KIT_BEGIN)
    if b < 0:
        return None
    e = text.find(KIT_END, b)
    if e < 0:
        fault("%s: opens the bridge client block and never closes it" % path)
        return None
    return (b, e + len(KIT_END))


def load_kit():
    text = open(KIT_FILE, encoding="utf-8").read()
    span = kit_span(text, KIT_FILE)
    if span is None or span != (0, len(text.rstrip("\n"))):
        fault("%s: must be exactly one bridge client block, from %r to %r" % (KIT_FILE, KIT_BEGIN, KIT_END))
        return ""
    return text[span[0]:span[1]]


def check_kit(path, text, permissions, kit):
    span = kit_span(text, path)
    if span is None:
        if permissions:
            fault("%s: asks the server for something (permissions %s) but carries no bridge client — paste "
                  "%s between the agnostic-kit:host markers, or run --sync-kit"
                  % (path, ", ".join(permissions), KIT_FILE))
        return
    if text[span[0]:span[1]] != kit:
        fault("%s: its copy of the bridge client differs from %s — run scripts/check-embedded.py --sync-kit"
              % (path, KIT_FILE))


def check_page(path):
    """Refuse what the page's CSP would block."""
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        fault("%s: not UTF-8 (%s)" % (path, e))
        return
    if "\0" in text:
        fault("%s: contains a NUL byte" % path)
    if "\r" in text:
        fault("%s: contains a carriage return; save it with LF line endings — a browser normalises CR "
              "before hashing a script, so the CSP hash would not match" % path)
    if re.search(r"<script\b[^>]*\bsrc\s*=", text, re.I):
        fault("%s: loads an external script; inline it — the CSP admits only the page's own inline "
              "scripts, by hash" % path)
    m = re.search(r"<[a-zA-Z][^<>]*\son[a-z]+\s*=", text)
    if m:
        fault("%s: has an inline event handler (%s…); use addEventListener — the CSP does not run inline "
              "handlers" % (path, m.group(0)[:40]))
    if re.search(r"javascript:", text, re.I):
        fault("%s: uses a javascript: URL, which the CSP does not run" % path)
    at = 0
    while True:
        tag = SCRIPT_OPEN_RE.search(text, at)
        if not tag:
            break
        end = SCRIPT_CLOSE_RE.search(text, tag.end())
        if not end:
            fault("%s: a script opens and never closes, and such a page has no policy, so the server would "
                  "refuse to start" % path)
            break
        at = end.end()
    ext = (re.search(r"<link\b[^>]*\bhref\s*=\s*[\"']?(https?:|//)", text, re.I)
           or re.search(r"<(img|iframe|source|video|audio|embed|object)\b[^>]*\bsrc\s*=\s*[\"']?(https?:|//)", text, re.I)
           or re.search(r"@import\b", text)
           or re.search(r"url\(\s*[\"']?(https?:|//)", text, re.I))
    if ext:
        fault("%s: loads an external resource (%s…); a page is served with default-src 'none' and must be "
              "self-contained" % (path, ext.group(0)[:40]))


def check_manifest(pid, vocabulary):
    """The manifest of plugin `pid`, or None."""
    path = "%s/%s/plugin.json" % (PLUGINS_DIR, pid)
    try:
        m = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        fault("%s: %s" % (path, e))
        return None
    if not isinstance(m, dict):
        fault("%s: a manifest is a JSON object" % path)
        return None
    unknown = sorted(set(m) - set(MANIFEST_KEYS))
    missing = [k for k in MANIFEST_KEYS if k not in m]
    if unknown or missing:
        fault("%s: unknown key(s) %s, missing key(s) %s"
              % (path, ", ".join(unknown) or "none", ", ".join(missing) or "none"))
        return None
    for k in STRING_KEYS:
        if not isinstance(m[k], str) or not m[k]:
            fault("%s: `%s` must be a non-empty string" % (path, k))
            return None
    perms = m["permissions"]
    if not isinstance(perms, list) or not all(isinstance(x, str) for x in perms):
        fault("%s: `permissions` must be a list of strings (it may be empty)" % path)
        return None
    bad = [x for x in perms if x not in vocabulary]
    if bad or len(set(perms)) != len(perms):
        fault("%s: `permissions` may hold each of %s once; got %s"
              % (path, ", ".join(vocabulary), ", ".join(perms) or "none"))
    if m["id"] != pid or not ID_RE.match(pid):
        fault("%s: `id` must equal its directory name and match [a-z0-9][a-z0-9-]{0,31}" % path)
    if len(m["name"]) > 64:
        fault("%s: `name` is longer than 64 characters" % path)
    if len(m["description"]) > 512:
        fault("%s: `description` is longer than 512 characters" % path)
    if not VERSION_RE.match(m["version"]):
        fault("%s: `version` must be MAJOR.MINOR.PATCH" % path)
    if m["data"] not in DATA_KINDS:
        fault("%s: `data` must be one of %s — say whether the view shows simulated or live data (or "
              "`mixed`, when it labels each mission itself), because a simulation reads exactly like real "
              "work" % (path, ", ".join(DATA_KINDS)))
    if m["entry"] != "index.html":
        fault("%s: `entry` must be index.html — a plugin is one self-contained page" % path)
    return m


def check_presets():
    """Each preset parses, and is what its file is called: the library is looked up by that name."""
    count = 0
    for f in sorted(os.listdir(PRESETS_DIR)):
        if not f.endswith(".json"):
            continue
        count += 1
        path = "%s/%s" % (PRESETS_DIR, f)
        raw = open(path, "rb").read()
        if b"\0" in raw:
            fault("%s: contains a NUL byte, and a preset is read as a C string" % path)
        try:
            doc = json.loads(raw)
        except ValueError as e:
            fault("%s: %s" % (path, e))
            continue
        if not isinstance(doc, dict) or doc.get("name") != f[:-5]:
            fault("%s: its `name` must be %s" % (path, f[:-5]))
        if not isinstance(doc.get("agents") if isinstance(doc, dict) else None, list):
            fault("%s: `agents` must be a list" % path)
    m = re.search(r"^var AGNOSTIC_PRESET_JSON_COUNT = (\d+);", open("src/engine/presets.cyr", encoding="utf-8").read(), re.M)
    if not m or int(m.group(1)) != count:
        fault("src/engine/presets.cyr: AGNOSTIC_PRESET_JSON_COUNT is not %d" % count)
    return count


def main():
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    sync = sys.argv[1:] == ["--sync-kit"]
    if sys.argv[1:] and not sync:
        sys.stderr.write(__doc__)
        return 2
    table = embed_table()
    check_table(table)
    check_assets(table)
    vocabulary = load_permissions()
    kit = load_kit()
    presets = check_presets()
    check_page("src/webgui/index.html")
    plugins = sorted(d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d)))
    for pid in plugins:
        m = check_manifest(pid, vocabulary)
        page = "%s/%s/index.html" % (PLUGINS_DIR, pid)
        if not os.path.exists(page):
            fault("%s: a plugin is one page, and this one is missing" % page)
            continue
        if sync and kit:
            text = open(page, encoding="utf-8").read()
            span = kit_span(text, page)
            if span is not None and text[span[0]:span[1]] != kit:
                open(page, "w", encoding="utf-8").write(text[:span[0]] + kit + text[span[1]:])
                print("check-embedded: synced the bridge client into " + page)
        check_page(page)
        check_kit(page, open(page, encoding="utf-8").read(), m["permissions"] if m else [], kit)
    for f in faults:
        sys.stderr.write("check-embedded: " + f + "\n")
    if faults:
        return 1
    print("check-embedded: %d files in [embed]: %d presets, %d pages, %d manifests, the vocabulary"
          % (len(table), presets, len(plugins) + 1, len(plugins)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
