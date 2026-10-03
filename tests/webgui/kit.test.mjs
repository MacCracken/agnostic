// The bridge client every plugin page carries verbatim (src/webgui/kit/host.js, 0.1.10):
// the hello/init handshake, requests and their answers, params and navigation, standalone.
//
// scripts/gen-webgui.sh refuses a page whose copy differs from this file by a byte, so testing
// the file tests every page's copy.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadScript, tick } from './harness.mjs';

/** A framed page: a `window` whose parent records what is posted to it. */
function framed() {
  const posted = [];
  const handlers = [];
  const parent = { postMessage: (m) => posted.push(structuredClone(m)) };
  const window = { parent, addEventListener: (type, fn) => { if (type === 'message') handlers.push(fn); } };
  const page = loadScript('src/webgui/kit/host.js', { globals: { window } });
  const deliver = (data, source = parent) => { for (const fn of handlers) fn({ source, data }); };
  return { page, posted, deliver, parent, window };
}
const INIT = {
  type: 'agnostic:init', protocol: 1, features: ['query', 'revisions', 'idempotency', 'navigate'],
  plugin: { id: 'crews', name: 'Crews', version: '0.1.0' }, permissions: ['crews:read'],
  user: { auth: 'required', signedIn: true, role: 'viewer' },
  params: 'crew=6ba7b810-9dad-41d1-80b4-00c04fd430c8&q=a%20b', views: [{ id: 'crews', name: 'Crews' }, { id: 'swarm', name: 'Swarm Command' }],
};

test('framed, it says hello and connects on init: permissions, features, role, views, params', () => {
  const { page, posted, deliver } = framed();
  const host = page.get('new Host()');
  assert.equal(host.mode, 'connecting');
  assert.deepEqual(posted[0], { type: 'agnostic:hello', protocol: 1 });
  let changes = 0;
  host.onChange(() => changes++);
  deliver(INIT);
  assert.equal(host.mode, 'connected');
  assert.equal(changes, 1);
  assert.equal(host.can('crews:read'), true);
  assert.equal(host.can('crews:write'), false);
  assert.equal(host.has('navigate'), true);
  assert.equal(host.pluginId(), 'crews');
  assert.equal(host.role(), 'viewer');
  assert.equal(host.mayWrite(), false, 'a viewer may not write');
  assert.equal(host.hasView('swarm'), true);
  assert.equal(host.hasView('library'), false, 'a view that is not switched on is not offered');
  assert.equal(host.param('crew'), '6ba7b810-9dad-41d1-80b4-00c04fd430c8');
  assert.equal(host.param('q'), 'a b', 'a value is percent-decoded');
  assert.equal(host.param('missing'), '');
  clearTimeout(host.timer);
});

test('it hears only its parent, and only well-formed messages', () => {
  const { page, deliver } = framed();
  const host = page.get('new Host()');
  deliver(INIT, { postMessage() {} });
  deliver(null);
  deliver('agnostic:init');
  deliver({ type: 42 });
  assert.equal(host.mode, 'connecting', 'another window cannot connect it');
  deliver({ type: 'agnostic:init', permissions: 'all', features: [1, 'navigate'], user: 'admin', views: [{ id: 1 }, null] });
  assert.equal(host.mode, 'connected');
  assert.equal(host.can('all'), false, 'a malformed init grants nothing');
  assert.equal(host.has('navigate'), true);
  assert.equal(host.role(), null, 'and a user that is not an object is nobody');
  assert.equal(host.hasView('1'), false);
  assert.equal(host.pluginId(), '', 'no plugin id is the empty string');
  clearTimeout(host.timer);
});

test('params: a deep link while open is told by agnostic:params; an init that changes them, too', () => {
  const { page, deliver } = framed();
  const host = page.get('new Host()');
  const seen = [];
  host.onParams((p) => seen.push(p));
  deliver(INIT);
  assert.deepEqual(seen, [INIT.params], 'the first init carries them');
  deliver(INIT);
  assert.equal(seen.length, 1, 'a re-sent init (a sign-in) with the same params is not a change');
  deliver({ type: 'agnostic:params', params: 'crew=other' });
  assert.equal(host.param('crew'), 'other');
  deliver({ type: 'agnostic:params', params: 7 });
  assert.equal(host.params, '', 'params that are not a string are none');
  deliver({ type: 'agnostic:params', params: 'crew=%E0%A4%A' });
  assert.equal(host.param('crew'), '', 'a malformed escape reads as absent, never throws');
  assert.equal(seen.length, 4);
  clearTimeout(host.timer);
});

test('navigate posts to the shell — only when the shell carries it', () => {
  const { page, posted, deliver } = framed();
  const host = page.get('new Host()');
  assert.equal(host.navigate('swarm', 'crew=x'), false, 'not before init');
  deliver(Object.assign({}, INIT, { features: ['query'] }));
  assert.equal(host.navigate('swarm', 'crew=x'), false, 'nor to a shell without the feature');
  deliver(INIT);
  assert.equal(host.navigate('swarm', 'crew=x'), true);
  assert.deepEqual(posted.at(-1), { type: 'agnostic:navigate', to: 'swarm', params: 'crew=x' });
  host.navigate('overview');
  assert.deepEqual(posted.at(-1), { type: 'agnostic:navigate', to: 'overview', params: '' });
  clearTimeout(host.timer);
});

test('request: an id per page load, the answer by id, options only when carried', async () => {
  const { page, posted, deliver } = framed();
  const host = page.get('new Host()');
  const early = await host.request('GET', '/api/v1/crews');
  assert.equal(early.status, 0, 'not connected yet: answered at once, never sent');
  deliver(Object.assign({}, INIT, { features: ['query'] }));
  const p = host.request('PUT', '/api/v1/plugins/crews/data/k', { a: 1 }, { ifMatch: '"0123456789abcdef"', idempotencyKey: 'k-12345678' });
  const sent = posted.at(-1);
  assert.equal(sent.type, 'agnostic:request');
  assert.match(sent.id, /^q[a-z0-9]{6}-1$/);
  assert.deepEqual(sent.body, { a: 1 });
  assert.equal('ifMatch' in sent, false, 'a shell without revisions is not sent ifMatch');
  assert.equal('idempotencyKey' in sent, false);
  deliver({ type: 'agnostic:response', id: 'someone-else', status: 200, data: {} });
  deliver({ type: 'agnostic:response', id: sent.id, status: 200, data: { ok: true }, etag: '"aaaaaaaaaaaaaaaa"' });
  assert.deepEqual({ ...(await p) }, { status: 200, data: { ok: true }, etag: '"aaaaaaaaaaaaaaaa"' });
  deliver(INIT);
  host.request('POST', '/api/v1/crews', {}, { idempotencyKey: 'k-12345678' });
  assert.equal(posted.at(-1).idempotencyKey, 'k-12345678', 'carried once the shell lists it');
  assert.match(posted.at(-1).id, /-2$/);
  clearTimeout(host.timer);
});

test('a request the shell never answers resolves with status 0', async () => {
  const { page, deliver } = framed();
  const host = page.get('new Host({ timeoutMs: 20 })');
  deliver(INIT);
  const r = await host.request('GET', '/api/v1/crews');
  assert.equal(r.status, 0);
  assert.equal(page.get('errOf')(r), 'the shell did not answer');
  assert.equal(host.pending.size, 0);
  clearTimeout(host.timer);
});

test('unframed it stands alone at once; framed by a silent parent it stands alone after helloMs', async () => {
  const win = { addEventListener() { throw new Error('a standalone page listens to nothing'); } };
  win.parent = win;
  const alone = loadScript('src/webgui/kit/host.js', { globals: { window: win } }).get('new Host()');
  assert.equal(alone.mode, 'standalone');
  assert.equal(alone.can('crews:read'), false);
  assert.equal(alone.navigate('swarm'), false);
  const { page } = framed();
  const host = page.get('new Host({ helloMs: 10 })');
  let told = 0;
  host.onChange(() => told++);
  await tick(30);
  assert.equal(host.mode, 'standalone');
  assert.equal(told, 1);
});

test('errOf: the server\'s error, else the status, else unreachable', () => {
  const { page } = framed();
  const errOf = page.get('errOf');
  assert.equal(errOf({ status: 422, data: { error: 'bad crew' } }), 'bad crew');
  assert.equal(errOf({ status: 500, data: null }), 'HTTP 500');
  assert.equal(errOf({ status: 0, data: null }), 'the server is unreachable');
  assert.equal(errOf(null), 'the server is unreachable');
});
