// The shell's host-bridge gate (src/webgui/index.html, its first <script>): what a plugin may ask
// for, and the shape a request must have, decided before anything reaches the network.
//
// The grants come from the SAME vocabulary the server enforces — src/webgui/permissions.json,
// served as `catalogue` by GET /api/v1/plugins — so these tests read that file, not a copy.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadPage, ROOT } from './harness.mjs';

const page = loadPage('src/webgui/index.html', { globals: { window: {} }, only: [0] });
const B = page.get('window.AgnosticBridge');
const catalogue = JSON.parse(readFileSync(ROOT + 'src/webgui/permissions.json', 'utf8'));
const swarm = JSON.parse(readFileSync(ROOT + 'src/webgui/plugins/swarm/plugin.json', 'utf8'));
const grants = B.grantsFor(swarm, catalogue);
const UUID = '6ba7b810-9dad-41d1-80b4-00c04fd430c8';
const req = (method, path, extra) => Object.assign({ type: 'agnostic:request', id: 'q1', method, path }, extra || {});

test('the gate is pure: it loads without a DOM, and exports what the app uses', () => {
  for (const k of ['METHODS', 'MAX_BODY', 'MAX_INFLIGHT', 'compileRoute', 'grantsFor', 'granted', 'check', 'parseRoute', 'checkNavigate']) assert.ok(k in B, k);
  assert.equal(B.MAX_INFLIGHT, 16);
  assert.ok(Object.isFrozen(B), 'and cannot be changed from outside');
});

test("a plugin's grants are its manifest's permissions, from the catalogue", () => {
  const yes = [
    ['GET', '/api/v1/plugins/swarm/data'], ['GET', '/api/v1/plugins/swarm/data/swarm-abc123'],
    ['PUT', '/api/v1/plugins/swarm/data/swarm-abc123'], ['DELETE', '/api/v1/plugins/swarm/data/swarm-abc123'],
    ['GET', '/api/v1/presets'], ['GET', '/api/v1/presets/quality-lean'],
    ['GET', '/api/v1/crews'], ['GET', '/api/v1/crews?limit=20&before=17.' + UUID],
    ['GET', '/api/v1/crews/' + UUID], ['GET', '/api/v1/crews/' + UUID + '/events?after=12'], ['GET', '/api/v1/crews/' + UUID + '/plan'],
    ['POST', '/api/v1/crews'], ['POST', '/api/v1/crews/' + UUID + '/cancel'],
  ];
  for (const [m, p] of yes) assert.equal(B.granted(grants, m, p), true, m + ' ' + p);
  const no = [
    ['GET', '/api/v1/plugins/other/data'], ['GET', '/api/v1/plugins/other/data/k'], // :self is the plugin's own id
    ['PUT', '/api/v1/plugins/swarm'], ['GET', '/api/v1/plugins'],                      // not its switch, not the list
    ['GET', '/api/v1/audit'], ['GET', '/api/v1/agents/definitions'],                    // not asked for
    ['DELETE', '/api/v1/crews/' + UUID], ['PUT', '/api/v1/presets/x'],                   // a granted path, another method
    ['GET', '/api/v1/crews/' + UUID + '/events/more'],                                   // an extra segment
  ];
  for (const [m, p] of no) assert.equal(B.granted(grants, m, p), false, m + ' ' + p);
});

test('an unknown permission grants nothing, and a route is matched literally', () => {
  // (Arrays made inside the page's context have that context's prototype: compare lengths.)
  assert.equal(B.grantsFor({ id: 'x', permissions: ['root:everything'] }, catalogue).length, 0);
  assert.equal(B.grantsFor({ id: 'x', permissions: ['toString', '__proto__'] }, catalogue).length, 0, 'no prototype keys');
  const g = [B.compileRoute('GET /api/v1/a.b', 'x')];
  assert.equal(B.granted(g, 'GET', '/api/v1/a.b'), true);
  assert.equal(B.granted(g, 'GET', '/api/v1/aXb'), false, 'a dot in a route is a dot, not "any character"');
  const self = [B.compileRoute('GET /api/v1/plugins/:self/data', 'my.plugin')];
  assert.equal(B.granted(self, 'GET', '/api/v1/plugins/my.plugin/data'), true);
  assert.equal(B.granted(self, 'GET', '/api/v1/plugins/myXplugin/data'), false, ':self is escaped too');
});

test('check() accepts a well-formed granted request and says what to send', () => {
  const c = B.check(req('GET', '/api/v1/crews/' + UUID + '/events?after=3'), swarm, grants);
  assert.equal(c.ok, true);
  assert.equal(c.method, 'GET');
  assert.equal(c.path, '/api/v1/crews/' + UUID + '/events?after=3', 'the query string travels');
  assert.equal(Object.keys(c.headers).length, 0, 'and no extra headers');
  const lower = B.check(req('post', '/api/v1/crews', { body: { name: 'x' } }), swarm, grants);
  assert.equal(lower.ok, true, 'a method is case-insensitive');
  assert.equal(lower.method, 'POST');
});

test('check() refuses a malformed request with 400, before anything else', () => {
  const bad = [
    req('GET', '/api/v1/presets', { id: { not: 'an id' } }), req('GET', '/api/v1/presets', { id: 'x'.repeat(65) }),
    req('PATCH', '/api/v1/presets'), req('GET', '/health'), req('GET', '/api/v1/../ui'), req('GET', '/api/v1//presets'),
    req('GET', '/api/v1/presets?x=<script>'), req('GET', '/api/v1/pre sets'), req('GET', 42),
  ];
  for (const m of bad) {
    const c = B.check(m, swarm, grants);
    assert.equal(c.ok, false, JSON.stringify(m));
    assert.equal(c.status, 400, JSON.stringify(m));
  }
});

test('check() refuses what the plugin is not granted with 403, naming it', () => {
  const c = B.check(req('GET', '/api/v1/audit'), swarm, grants);
  assert.equal(c.ok, false);
  assert.equal(c.status, 403);
  assert.match(c.error, /Swarm Command is not permitted to GET \/api\/v1\/audit/);
});

test('check() enforces the body rules: none on GET or DELETE, JSON, at most 256 KB', () => {
  assert.equal(B.check(req('GET', '/api/v1/presets', { body: {} }), swarm, grants).status, 400);
  assert.equal(B.check(req('DELETE', '/api/v1/plugins/swarm/data/k', { body: {} }), swarm, grants).status, 400);
  const cyclic = {}; cyclic.self = cyclic;
  assert.equal(B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: cyclic }), swarm, grants).status, 400);
  const big = { s: 'x'.repeat(B.MAX_BODY) };
  assert.equal(B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: big }), swarm, grants).status, 413);
  assert.equal(B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: { s: 'fine' } }), swarm, grants).ok, true);
});

test('revisions and idempotency keys become headers — only on the methods they mean something on', () => {
  const etag = '"0123456789abcdef"';
  const put = B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: {}, ifMatch: etag }), swarm, grants);
  assert.equal(put.ok, true);
  assert.equal(put.headers['If-Match'], etag);
  assert.equal(B.check(req('DELETE', '/api/v1/plugins/swarm/data/k', { ifMatch: etag }), swarm, grants).headers['If-Match'], etag);
  assert.equal(B.check(req('GET', '/api/v1/plugins/swarm/data/k', { ifMatch: etag }), swarm, grants).status, 400, 'not on a GET');
  assert.equal(B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: {}, ifMatch: 'W/"weak"' }), swarm, grants).status, 400, 'not a weak or foreign tag');
  assert.equal(B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: {}, ifNoneMatch: '*' }), swarm, grants).headers['If-None-Match'], '*');
  assert.equal(B.check(req('PUT', '/api/v1/plugins/swarm/data/k', { body: {}, ifNoneMatch: etag }), swarm, grants).status, 400, "If-None-Match is only '*'");
  const post = B.check(req('POST', '/api/v1/crews', { body: {}, idempotencyKey: 'sw-run-abc12345' }), swarm, grants);
  assert.equal(post.headers['Idempotency-Key'], 'sw-run-abc12345');
  assert.equal(B.check(req('POST', '/api/v1/crews', { body: {}, idempotencyKey: 'short' }), swarm, grants).status, 400);
  assert.equal(B.check(req('POST', '/api/v1/crews', { body: {}, idempotencyKey: 'has spaces in it' }), swarm, grants).status, 400);
  assert.equal(B.check(req('GET', '/api/v1/crews', { idempotencyKey: 'sw-run-abc12345' }), swarm, grants).status, 400, 'only a POST');
});

test('the route is read from the hash: a view, and a plugin with params', () => {
  const r = (h) => { const x = B.parseRoute(h); return [x.view, x.id, x.params]; };
  assert.deepEqual(r(''), ['overview', '', '']);
  assert.deepEqual(r('#overview'), ['overview', '', '']);
  assert.deepEqual(r('#settings'), ['settings', '', '']);
  assert.deepEqual(r('#nonsense'), ['overview', '', ''], 'anything else is the overview');
  assert.deepEqual(r('#plugin/swarm'), ['plugin', 'swarm', '']);
  assert.deepEqual(r('#plugin/crews?crew=' + UUID), ['plugin', 'crews', 'crew=' + UUID], 'the id stops at the ?');
  assert.deepEqual(r('#plugin/crews?status=running&crew=a%2Fb'), ['plugin', 'crews', 'status=running&crew=a%2Fb']);
  assert.deepEqual(r('#plugin/crews?crew=<script>'), ['plugin', 'crews', ''], 'params outside the charset are dropped, not passed on');
  assert.deepEqual(r('#plugin/crews?' + 'a'.repeat(257)), ['plugin', 'crews', ''], 'and so are params over 256 characters');
});

test('navigate opens only a view that is switched on, with params only for a plugin', () => {
  const on = ['swarm', 'crews'];
  const nav = (to, params) => B.checkNavigate({ type: 'agnostic:navigate', to, params }, on);
  assert.deepEqual({ ...nav('crews', 'crew=' + UUID) }, { ok: true, hash: 'plugin/crews?crew=' + UUID });
  assert.deepEqual({ ...nav('swarm') }, { ok: true, hash: 'plugin/swarm' }, 'params are optional');
  assert.deepEqual({ ...nav('swarm', '') }, { ok: true, hash: 'plugin/swarm' });
  assert.deepEqual({ ...nav('overview', 'x=1') }, { ok: true, hash: 'overview' }, 'the shell\'s own views take no params');
  assert.deepEqual({ ...nav('settings') }, { ok: true, hash: 'settings' });
  assert.equal(nav('library').ok, false, 'a plugin that is off (or absent) is refused');
  assert.equal(nav('Crews').ok, false, 'ids are matched exactly');
  assert.equal(nav('../ui').ok, false);
  assert.equal(nav('crews', 'crew=a b').ok, false, 'params keep to the charset');
  assert.equal(nav('crews', 'x'.repeat(257)).ok, false, 'and to 256 characters');
  assert.equal(nav('crews', 42).ok, false, 'and are a string');
  assert.equal(B.checkNavigate({ type: 'agnostic:navigate' }, on).ok, false, 'a navigate names its view');
  for (const p of ['crew=' + UUID, 'status=running&after=1759400000000.' + UUID, 'q=a%20b']) {
    const n = nav('crews', p);
    assert.equal(n.ok, true, p);
    assert.equal(B.parseRoute('#' + n.hash).params, p, 'and what it allows survives the round trip through the URL');
  }
});
