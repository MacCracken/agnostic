// tests/webgui/harness.mjs — load a WebGUI page's inline scripts into a Node `vm` context.
//
// The WebGUI's pages are single self-contained HTML files (ADR 0004), and their logic —
// the shell's bridge gate, Swarm Command's simulator, spec normalizer, crew request
// builder and live crew source — is plain JavaScript with no top-level DOM access. So it
// runs in Node: each inline <script> is evaluated, in order, in one context, and a test
// reads what it declared by evaluating an expression in that same context (top-level
// `const` / `class` declarations live in the context's global lexical scope, not on its
// global object, so `page.get('({A, B})')` is how they are reached).
//
// Run with `node --test tests/webgui/*.test.mjs` from the repository root (name the files: since
// Node 21 a directory argument is not searched), or through `scripts/check-webgui-js.sh`, which CI runs.

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

export const ROOT = fileURLToPath(new URL('../../', import.meta.url));

/** The bodies of every inline <script> in the page at `rel` (relative to the repo root). */
export function pageScripts(rel) {
  const html = readFileSync(ROOT + rel, 'utf8');
  const out = [];
  const re = /<script(\s[^>]*)?>([\s\S]*?)<\/script\s*>/gi;
  let m;
  while ((m = re.exec(html))) out.push(m[2]);
  return out;
}

/**
 * Evaluate the page's scripts (all, or the indices in `only`) in a fresh context holding
 * the given globals. Returns `{ ctx, get(expr) }`.
 *
 * Timers are the real ones unless a test passes its own; nothing here fakes a DOM, so a
 * script that touches `document` at load time fails loudly rather than half-running.
 */
export function loadPage(rel, { globals = {}, only = null } = {}) {
  const ctx = vm.createContext({
    console, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    performance, TextEncoder, TextDecoder, URL, Blob, structuredClone, crypto: globalThis.crypto,
    ...globals,
  });
  pageScripts(rel).forEach((src, i) => {
    if (only && !only.includes(i)) return;
    vm.runInContext(src, ctx, { filename: rel + '#script' + i });
  });
  return { ctx, get: (expr) => vm.runInContext(expr, ctx) };
}

/**
 * Evaluate one plain script file (relative to the repo root) in a fresh context holding the
 * given globals — the bridge client, `src/webgui/kit/host.js`, which pages carry verbatim.
 * Returns `{ ctx, get(expr) }`, as `loadPage` does.
 */
export function loadScript(rel, { globals = {} } = {}) {
  const ctx = vm.createContext({
    console, setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
    performance, TextEncoder, TextDecoder, URL, Blob, structuredClone, crypto: globalThis.crypto,
    ...globals,
  });
  vm.runInContext(readFileSync(ROOT + rel, 'utf8'), ctx, { filename: rel });
  return { ctx, get: (expr) => vm.runInContext(expr, ctx) };
}

/** A promise that settles after every pending microtask and timer callback queued so far. */
export const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
