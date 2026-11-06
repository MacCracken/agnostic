#!/usr/bin/env python3
"""check-log-lengths.py — a log literal's declared length must be its real length.

sakshi's logging API takes (pointer, length) pairs rather than NUL-terminated
strings, so the byte count is hand-written at every call site and nothing checks
it. Both ways of getting it wrong fail SILENTLY, and both shipped in this repo
before this gate existed (M2, src/engine/crew.cyr):

  * **One too many** hands sakshi the NUL terminator as part of the message. In
    JSON output that is an escaped NUL inside the string — legal JSON that breaks
    naive consumers, and that no test asserting on handler behaviour would ever
    notice.
  * **One too few** truncates the last character. "does not know this crew"
    becomes "does not know this cre", which then reads as a typo forever.

Neither is a compile error, neither is a lint warning, and neither fails a test:
the assertion suites check what handlers return, not what they log. This script
is the only thing standing between a miscount and production.

Exits non-zero on any mismatch. Run from the repo root.
"""
import codecs
import glob
import re
import sys

# sakshi_info("msg", N) and its level siblings.
BARE = re.compile(
    r'\b(sakshi_(?:info|warn|error|debug|trace))\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*\)')

# agnostic_log_kv_str/int(LEVEL, "msg", N, "key", K, ...)
KV = re.compile(
    r'\b(agnostic_log_kv_(?:str|int))\(\s*[A-Za-z_]+\s*,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*,')

# sakshi_log_kv(LEVEL, "msg", N, "key", K, ...)
SAKSHI_KV = re.compile(
    r'\bsakshi_log_kv\(\s*[A-Za-z_]+\s*,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*,\s*'
    r'"((?:[^"\\]|\\.)*)"\s*,\s*(\d+)\s*,')


def byte_len(literal):
    """The length sakshi is actually handed: bytes, after resolving escapes.

    `codecs.escape_decode` works on the UTF-8 bytes: it resolves `\\n`, `\\0`, `\\\\`
    and `\\"` and leaves every other byte as it is. Through 0.2.1 this read those
    bytes as Latin-1 and encoded each one again, so every non-ASCII byte counted
    twice and the gate would have demanded a length past the literal.
    """
    return len(codecs.escape_decode(literal.encode("utf-8"))[0])


# Known byte counts, checked before any file is scanned: a checker that mismeasures
# passes every literal sized by its own count. Each pair is (literal as written in
# source, bytes sakshi is handed).
SELF_TEST = [
    ("plain ascii", 11),
    ("a — b", 7),              # an em dash is 3 bytes
    ("café", 5),               # a 2-byte character
    ("line\\n", 5),            # \n is one byte
    ("nul\\0", 4),             # \0 is one byte
    ("q\\\"q", 3),             # \" is one byte
    ("back\\\\slash", 10),     # \\ is one byte
]


def self_test():
    wrong = [(lit, want, byte_len(lit)) for lit, want in SELF_TEST if byte_len(lit) != want]
    for lit, want, got in wrong:
        print("    self-test: %r is %d bytes, byte_len says %d" % (lit, want, got))
    return not wrong


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def describe(declared, actual):
    if declared == actual + 1:
        return "declares the NUL terminator"
    if declared > actual:
        return "overruns by %d" % (declared - actual)
    return "truncates by %d" % (actual - declared)


def check(path, bad):
    text = open(path, errors="ignore").read()

    def note(pos, what, literal, declared):
        actual = byte_len(literal)
        declared = int(declared)
        if actual == declared:
            return
        bad.append(
            '    %s:%d  %s declared %d, actual %d (%s)\n        "%s"'
            % (path, line_of(text, pos), what, declared, actual,
               describe(declared, actual), literal))

    for m in BARE.finditer(text):
        note(m.start(), m.group(1) + " message", m.group(2), m.group(3))
    for m in KV.finditer(text):
        note(m.start(), m.group(1) + " message", m.group(2), m.group(3))
        note(m.start(), m.group(1) + " key", m.group(4), m.group(5))
    for m in SAKSHI_KV.finditer(text):
        note(m.start(), "sakshi_log_kv message", m.group(1), m.group(2))
        note(m.start(), "sakshi_log_kv key", m.group(3), m.group(4))


def main():
    if not self_test():
        print("error: byte_len mismeasures a known literal, so no length here can be trusted.")
        return 1
    bad = []
    paths = (sorted(glob.glob("src/**/*.cyr", recursive=True))
             + sorted(glob.glob("tests/*.tcyr"))
             + sorted(glob.glob("benches/*.bcyr")))
    for p in paths:
        check(p, bad)
    if bad:
        print("\n".join(bad))
        print("")
        print("error: a log literal's declared length does not match the literal.")
        print("       One too many hands sakshi the NUL terminator; one too few")
        print("       truncates the message. Both fail silently at runtime.")
        return 1
    print("log lengths OK — every declared length matches its literal across %d files"
          % len(paths))
    return 0


sys.exit(main())
