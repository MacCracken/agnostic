#!/usr/bin/env python3
"""check-skill.py — an agent skill says only what the server's API schema says.

Added at 0.1.13 (H6). `skills/agnostic/SKILL.md` teaches a coding agent agnostic's HTTP
API. Nothing compiles it, and the server IGNORES a query parameter no handler reads
(`src/http/codec.cyr`, "Query strings"). A skill that spells the event cursor `?since=`
for `?after=` therefore fails nowhere: the agent silently re-reads the whole window on
every poll. The H3 and H6 plans of 0.1.13 made exactly that mistake.

The reference is `docs/api/generated/schema.json`, the output of `agnostic api schema`
(ADR 0015). `tests/api_schema.tcyr` keeps it equal to the server's own tables, so checking
against it is checking against the router, the decoders and the vocabularies, without
parsing Cyrius. For every skills/*/SKILL.md this checks:

  * the frontmatter is Agent Skills frontmatter: only name, description, license,
    compatibility, metadata and allowed-tools; `name` lowercase-hyphenated, at most 64
    characters, and the skill directory's name; `description` 1 to 1024 characters with
    no angle brackets; `compatibility` at most 500;
  * the body stays under 500 lines;
  * every /api/v1/..., /health, /ready and /ui path is a route of the schema, with a
    path parameter written {name}, :name, $VAR or …;
  * every `METHOD /path` pair, and every curl command's method (-X, else POST with
    -d/--data, else GET), is one that route answers;
  * every query parameter on a path is one that route reads (its `query`);
  * every header a curl command sends is one the server reads: a global header, or one
    the route declares;
  * after a `<!-- schema: response METHOD /path -->` line, the ```json example parses, has
    only keys that route answers with, and has every key it always answers with;
  * after a `<!-- schema: a.b ... -->` line, the block (up to the next blank line) names
    every value of each schema list in backticks. A field, refused field, role or status
    the server gains fails here until the skill says what it is.

What it cannot see: prose. A status code, a limit or a sentence about behaviour can still
drift; the schema leaves out per-handler 4xx codes and nested shapes (`docs/api/README.md`).

Usage: check-skill.py [--schema PATH] [SKILL.md ...]. Exits non-zero on any finding.
Run from anywhere; paths default to this repository's.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA_REL = 'docs/api/generated/schema.json'
ALLOWED_KEYS = {'name', 'description', 'license', 'compatibility', 'metadata', 'allowed-tools'}
NAME_RE = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
STOP = r'[^\s"\'`?#)\]|,;.]'
ROUTE = rf'/api/v1/{STOP}+|/health\b|/ready\b|/ui\b(?:/{STOP}*)?'
PATH_RE = re.compile(rf'({ROUTE})(\?[^\s"\'`)#]*)?')
PAIR_RE = re.compile(rf'\b(GET|POST|PUT|PATCH|DELETE|HEAD)\s+`?({ROUTE})')
PARAM_SEG = re.compile(r'^(\{[a-z_]+\}|:[a-z_]+|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|<[^>]*>|…)$')
MARKER = re.compile(r'^\s*<!--\s*schema:\s*(.*?)\s*-->\s*$')


def resolve(path, table):
    """The schema pattern `path` names, and its {method: route}; (None, {}) for none."""
    want = path.strip('/').split('/')
    for pat, methods in table.items():
        ps = pat.strip('/').split('/')
        if len(ps) == len(want) and all(
                (p.startswith(':') and PARAM_SEG.match(w)) or p == w for p, w in zip(ps, want)):
            return pat, methods
    return None, {}


def frontmatter(text):
    """({key: value}, body, body's first line number), or (None, None, 0)."""
    if not text.startswith('---\n'):
        return None, None, 0
    end = text.find('\n---\n', 4)
    if end < 0:
        return None, None, 0
    fm = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line[0] in ' \t#':
            continue
        key, _, val = line.partition(':')
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in '"\'':
            val = val[1:-1]
        fm[key.strip()] = val
    return fm, text[end + 5:], text[:end + 5].count('\n') + 1


def schema_list(doc, dotted):
    """The list of strings at `dotted` in the schema document, or None."""
    v = doc
    for part in dotted.split('.'):
        if not isinstance(v, dict) or part not in v:
            return None
        v = v[part]
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return v
    return None


def check_markers(rel, lines, first, doc, table):
    """Findings for the `<!-- schema: ... -->` lines, and how many examples and lists."""
    errs, examples, lists = [], 0, 0
    for i, line in enumerate(lines):
        m = MARKER.match(line)
        if not m:
            continue
        at = f'{rel}:{first + i}'
        args = m.group(1).split()
        if args and args[0] == 'response':
            examples += 1
            if len(args) != 3:
                errs.append(f'{at}: write a response marker as `schema: response METHOD /path`')
                continue
            pat, methods = resolve(args[2], table)
            route = methods.get(args[1])
            if route is None:
                errs.append(f'{at}: {args[1]} {args[2]} is not a route in the schema')
                continue
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines) or lines[j].strip() != '```json':
                errs.append(f'{at}: a response marker must be followed by a ```json block')
                continue
            k = j + 1
            while k < len(lines) and lines[k].strip() != '```':
                k += 1
            try:
                ex = json.loads('\n'.join(lines[j + 1:k]))
            except ValueError as e:
                errs.append(f'{at}: the example for {args[1]} {pat} is not JSON: {e}')
                continue
            keys = route['response']['keys']
            allowed = {key.rstrip('?') for key in keys}
            if route['response']['kind'] != 'json' or not isinstance(ex, dict):
                errs.append(f'{at}: {args[1]} {pat} does not answer a JSON object')
                continue
            for key in ex:
                if key not in allowed:
                    errs.append(f'{at}: {args[1]} {pat} never answers with {key!r} '
                                f'(it answers {", ".join(keys)})')
            for key in keys:
                if not key.endswith('?') and key not in ex:
                    errs.append(f'{at}: {args[1]} {pat} always answers with {key!r}; '
                                f'the example leaves it out')
            continue
        if not args:
            errs.append(f'{at}: an empty schema marker')
            continue
        block = []
        for nxt in lines[i + 1:]:
            if not nxt.strip() or MARKER.match(nxt):
                break
            block.append(nxt)
        named = set(re.findall(r'`([^`\n]+)`', '\n'.join(block)))
        for dotted in args:
            lists += 1
            values = schema_list(doc, dotted)
            if values is None:
                errs.append(f'{at}: {dotted} is not a list in the schema')
                continue
            missing = [v for v in values if v not in named]
            if missing:
                errs.append(f'{at}: the block below says nothing of {dotted} '
                            f'{", ".join(missing)}; name each in backticks')
    return errs, examples, lists


def check(path, doc, table):
    """Every finding for one SKILL.md, and (paths, examples, lists) checked."""
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        rel = path
    fm, body, first = frontmatter(path.read_text())
    if fm is None:
        return [f'{rel}: no YAML frontmatter between --- lines'], (0, 0, 0)
    errs = []
    for k in sorted(set(fm) - ALLOWED_KEYS):
        errs.append(f'{rel}: frontmatter key {k!r} is not an Agent Skills field')
    name = fm.get('name', '')
    if not NAME_RE.match(name) or len(name) > 64:
        errs.append(f'{rel}: name {name!r} must be lowercase letters, digits and single hyphens, 1-64')
    if name != path.parent.name:
        errs.append(f'{rel}: name {name!r} must be the directory name {path.parent.name!r}')
    desc = fm.get('description', '')
    if not 1 <= len(desc) <= 1024:
        errs.append(f'{rel}: description is {len(desc)} characters, must be 1-1024')
    if '<' in desc or '>' in desc:
        errs.append(f'{rel}: description must not contain < or >')
    if len(fm.get('compatibility', '')) > 500:
        errs.append(f'{rel}: compatibility is over 500 characters')
    if body.count('\n') >= 500:
        errs.append(f'{rel}: body is {body.count(chr(10))} lines; keep it under 500')

    globals_ = set(doc['headers'])
    joined = re.sub(r'\\\n\s*', ' ', body)   # a curl command continued with a backslash
    paths = 0
    for m in PATH_RE.finditer(joined):
        paths += 1
        pat, methods = resolve(m.group(1), table)
        if pat is None:
            errs.append(f'{rel}: {m.group(1)} is not a route in {SCHEMA_REL}')
            continue
        reads = set()
        for route in methods.values():
            reads |= set(route['query'])
        for q in re.findall(r'[?&]([A-Za-z_]+)=', m.group(2) or ''):
            if q not in reads:
                errs.append(f'{rel}: ?{q}= on {m.group(1)}: {pat} reads '
                            f'{", ".join(sorted(reads)) or "no query parameter"}; '
                            f'the server ignores any other')
    for m in PAIR_RE.finditer(joined):
        pat, methods = resolve(m.group(2), table)
        if pat and m.group(1) not in methods:
            errs.append(f'{rel}: {m.group(1)} {m.group(2)}: {pat} answers {", ".join(sorted(methods))}')
    for line in joined.splitlines():
        if not re.search(r'\bcurl\s', line):
            continue
        x = re.search(r'-X\s+([A-Z]+)', line)
        meth = x.group(1) if x else ('POST' if re.search(r'\s(-d|--data[\w-]*)\s', line) else 'GET')
        sent = [h.lower() for h in re.findall(r'-H\s+[\'"]([A-Za-z0-9-]+)\s*:', line)]
        for m in PATH_RE.finditer(line):
            pat, methods = resolve(m.group(1), table)
            if pat is None:
                continue
            route = methods.get(meth)
            if route is None:
                errs.append(f'{rel}: curl {meth} {m.group(1)}: {pat} answers {", ".join(sorted(methods))}')
                continue
            for h in sent:
                if h not in globals_ and h not in route['headers']:
                    errs.append(f'{rel}: curl {meth} {pat} sends {h!r}, a header the server does not read')

    e, examples, lists = check_markers(rel, body.split('\n'), first, doc, table)
    return errs + e, (paths, examples, lists)



def main(argv):
    schema = ROOT / SCHEMA_REL
    if len(argv) >= 2 and argv[0] == '--schema':
        schema, argv = pathlib.Path(argv[1]), argv[2:]
    doc = json.loads(schema.read_text())
    table = {}
    for r in doc['routes']:
        table.setdefault(r['path'], {})[r['method']] = r
    skills = [pathlib.Path(a) for a in argv] or sorted((ROOT / 'skills').glob('*/SKILL.md'))
    if not skills:
        print('skill: no skills/*/SKILL.md to check')
        return 1
    errs, totals = [], [0, 0, 0]
    for s in skills:
        e, counts = check(s, doc, table)
        errs += e
        totals = [a + b for a, b in zip(totals, counts)]
    for e in errs:
        print(e)
    if errs:
        return 1
    print(f'skill OK — {len(skills)} file(s): {totals[0]} path mentions, {totals[1]} response '
          f'examples and {totals[2]} marked lists, against {len(doc["routes"])} routes of the '
          f'API schema')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
