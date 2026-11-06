// The Users view's logic (src/webgui/plugins/users/index.html), run in Node against a fake agnostic that
// answers as src/routes/identity.cyr does: the refusals a caller can meet, not only the happy path.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync } from 'node:fs';
import { loadPage, pageScripts } from './harness.mjs';

const page = loadPage('src/webgui/plugins/users/index.html');
const U = page.get(`({ TABS, ROLES, rolesFor, passwordError, userBody, limitFrom, tenantBody, limitText, paramsFor, UserDirectory, TenantDirectory })`);

const ID1 = '00000000000000a1';
const ID2 = '00000000000000b2';
const KEY = '00000000000000c3';
const PW = 'correct-horse-battery';

class FakeAgnostic {
  constructor() {
    this.users = new Map([[ID1, { id: ID1, email: 'ada@acme.test', role: 'admin', tenant: 'acme', created_at: 1700000000000 }],
      [ID2, { id: ID2, email: 'bob@acme.test', role: 'viewer', tenant: 'acme', created_at: 1700000000000 }]]);
    this.tenants = new Map([['acme', { key: 'acme', name: 'Acme', created_at: 1700000000000, rate_limit: 0, max_crews: 0 }]]);
    this.keys = new Map([[ID2, [{ id: KEY, label: 'ci', created_at: 1700000000000 }]]]);
    this.calls = [];
    this.refuse = null;     // a {status, error} the next write answers
  }
  answer(status, data) { return Promise.resolve({ status, data: data === undefined ? null : structuredClone(data), etag: null }); }
  request(method, path, body) {
    this.calls.push({ method, path, body });
    if (method !== 'GET' && this.refuse) { const r = this.refuse; this.refuse = null; return this.answer(r.status, { error: r.error }); }
    let m;
    if (path === '/api/v1/users' && method === 'GET') return this.answer(200, { users: [...this.users.values()], total: this.users.size });
    if (path === '/api/v1/users' && method === 'POST') {
      for (const u of this.users.values()) if (u.email === body.email) return this.answer(409, { error: 'a user with this address already exists' });
      const id = '00000000000000d' + this.users.size;
      const u = { id, email: body.email, role: body.role, tenant: body.tenant || '', created_at: 1700000000000 };
      this.users.set(id, u);
      return this.answer(201, { user: u });
    }
    if ((m = path.match(/^\/api\/v1\/users\/([0-9a-f]{16})$/))) {
      if (!this.users.has(m[1])) return this.answer(404, { error: 'no such user' });
      if (method === 'PUT') { this.users.get(m[1]).role = body.role; return this.answer(200, { user: this.users.get(m[1]) }); }
      if (method === 'DELETE') { this.users.delete(m[1]); return this.answer(200, { id: m[1], status: 'deleted' }); }
    }
    if ((m = path.match(/^\/api\/v1\/users\/([0-9a-f]{16})\/password$/)) && method === 'PUT') return this.answer(200, { id: m[1], status: 'changed' });
    if ((m = path.match(/^\/api\/v1\/users\/([0-9a-f]{16})\/api-keys$/)) && method === 'GET') {
      const k = this.keys.get(m[1]) || [];
      return this.answer(200, { keys: k, total: k.length });
    }
    if ((m = path.match(/^\/api\/v1\/users\/([0-9a-f]{16})\/api-keys\/([0-9a-f]{16})$/)) && method === 'DELETE') {
      this.keys.set(m[1], (this.keys.get(m[1]) || []).filter((k) => k.id !== m[2]));
      return this.answer(200, { id: m[2], status: 'revoked' });
    }
    if (path === '/api/v1/tenants' && method === 'GET') return this.answer(200, { tenants: [...this.tenants.values()], total: this.tenants.size });
    if (path === '/api/v1/tenants' && method === 'POST') {
      if (this.tenants.has(body.key)) return this.answer(409, { error: 'a tenant with this key already exists' });
      const t = { key: body.key, name: body.name || body.key, created_at: 1700000000000, rate_limit: body.rate_limit || 0, max_crews: body.max_crews || 0 };
      this.tenants.set(body.key, t);
      return this.answer(201, { tenant: t });
    }
    if ((m = path.match(/^\/api\/v1\/tenants\/([a-z0-9-]+)$/))) {
      if (!this.tenants.has(m[1])) return this.answer(404, { error: 'no such tenant' });
      if (method === 'PUT') { Object.assign(this.tenants.get(m[1]), body); return this.answer(200, { tenant: this.tenants.get(m[1]) }); }
      if (method === 'DELETE') {
        for (const u of this.users.values()) if (u.tenant === m[1]) return this.answer(409, { error: 'this tenant still has users' });
        this.tenants.delete(m[1]);
        return this.answer(200, { key: m[1], status: 'deleted' });
      }
    }
    return this.answer(404, { error: 'no route' });
  }
}
const hostFor = (fake) => ({ request: (m, p, b) => fake.request(m, p, b) });

test('an administrator hands out at most their own role, and with auth off nobody hands out any', () => {
  assert.deepEqual([...U.rolesFor('super_admin')], ['viewer', 'operator', 'admin', 'super_admin']);
  assert.deepEqual([...U.rolesFor('admin')], ['viewer', 'operator', 'admin']);
  assert.deepEqual([...U.rolesFor('viewer')], ['viewer']);
  assert.deepEqual([...U.rolesFor(null)], [], 'auth off has no users to give a role to');
  assert.deepEqual([...U.rolesFor('owner')], [], 'a role this build does not know grants nothing');
});

test('a password is measured in bytes, as the server measures it', () => {
  assert.equal(U.passwordError(PW), '');
  assert.match(U.passwordError('short'), /at least 12/);
  assert.equal(U.passwordError('é'.repeat(6)), '', 'six characters of two bytes are twelve bytes');
  assert.match(U.passwordError('x'.repeat(1025)), /at most 1024/);
  assert.match(U.passwordError(''), /at least/);
  assert.match(U.passwordError(undefined), /at least/);
});

test('a new user body has what the server takes, and no empty tenant', () => {
  const ok = U.userBody({ email: ' a@b.test ', password: PW, role: 'operator', tenant: 'acme' });
  assert.deepEqual({ ...ok.body }, { email: 'a@b.test', password: PW, role: 'operator', tenant: 'acme' });
  const none = U.userBody({ email: 'a@b.test', password: PW, role: 'viewer', tenant: '' });
  assert.equal('tenant' in none.body, false, 'no tenant is left out, not sent empty');
  assert.match(U.userBody({ email: 'nope', password: PW }).error, /email/);
  assert.match(U.userBody({ email: 'a@b', password: 'short' }).error, /at least/);
  assert.match(U.userBody({ email: 'a@b', password: PW, role: 'root' }).error, /role/);
  assert.match(U.userBody({ email: 'a@b', password: PW, role: 'viewer', tenant: 'Bad Key' }).error, /tenant key/);
});

test('a limit left empty is the server default, and a limit is a whole number in range', () => {
  assert.equal(U.limitFrom('', 'x').value, 0);
  assert.equal(U.limitFrom(undefined, 'x').value, 0);
  assert.equal(U.limitFrom(' 60 ', 'x').value, 60);
  assert.equal(U.limitFrom('1000000', 'x').value, 1000000);
  assert.match(U.limitFrom('1000001', 'Crews').error, /^Crews/);
  assert.match(U.limitFrom('-1', 'x').error, /whole number/);
  assert.match(U.limitFrom('1.5', 'x').error, /whole number/);
  assert.match(U.limitFrom('many', 'x').error, /whole number/);
  assert.equal(U.limitText(0), 'server default');
  assert.equal(U.limitText(60), '60');
});

test('a tenant body sends a key only when creating: a key cannot change', () => {
  const made = U.tenantBody({ key: 'acme', name: 'Acme', rate_limit: '60', max_crews: '' }, true);
  assert.deepEqual({ ...made.body }, { key: 'acme', name: 'Acme', rate_limit: 60, max_crews: 0 });
  const edited = U.tenantBody({ key: 'other', name: 'New', rate_limit: '', max_crews: '5' }, false);
  assert.equal('key' in edited.body, false);
  assert.equal(edited.body.rate_limit, 0, 'an emptied limit goes back to the default, so it must be sent');
  assert.match(U.tenantBody({ key: 'Bad Key' }, true).error, /tenant key/);
  assert.match(U.tenantBody({ key: 'k', name: 'x'.repeat(256) }, true).error, /name/);
  assert.match(U.tenantBody({ key: 'k', rate_limit: 'x' }, true).error, /Crews a minute/);
  assert.match(U.tenantBody({ key: 'k', max_crews: '-1' }, true).error, /Unfinished crews/);
});

test('the URL carries the tab and the item, leaving out the defaults', () => {
  assert.equal(U.paramsFor('users', ''), '');
  assert.equal(U.paramsFor('users', ID1), 'item=' + ID1);
  assert.equal(U.paramsFor('tenants', 'acme'), 'tab=tenants&item=acme');
});

test('the directory lists the users, and drops a row it could not address', async () => {
  const fake = new FakeAgnostic();
  fake.users.set('../../evil', { id: '../../evil', email: 'x@y', role: 'viewer' });
  const d = new U.UserDirectory(hostFor(fake));
  assert.equal(await d.load(), true);
  assert.equal(d.users.length, 2, 'an id that is not 16 hex digits never reaches a path');
  assert.equal(d.get(ID1).email, 'ada@acme.test');
  assert.equal(d.get('nope'), null);
});

test('a refused read says what to do about it, and an empty list is not a refusal', async () => {
  const say = async (status, data) => {
    const d = new U.UserDirectory({ request: () => Promise.resolve({ status, data, etag: null }) });
    assert.equal(await d.load(), false);
    return d.error;
  };
  assert.match(await say(401, { error: 'x' }), /Sign in as an administrator/);
  assert.match(await say(403, { error: 'x' }), /for administrators/);
  assert.match(await say(403, { error: 'off', code: 'plugin_off' }), /off/, 'a plugin refusal is the server’s words');
  assert.match(await say(409, { error: 'authentication is off' }), /authentication is off/, 'with auth off there is nobody to manage');
  assert.match(await say(0, { error: 'the shell did not answer' }), /did not answer/);
  const d = new U.UserDirectory({ request: () => Promise.resolve({ status: 200, data: { users: [], total: 0 }, etag: null }) });
  assert.equal(await d.load(), true);
  assert.equal(d.error, '');
});

test('creating a user sends the form, shows a refusal in the server’s words, and reloads', async () => {
  const fake = new FakeAgnostic();
  const d = new U.UserDirectory(hostFor(fake));
  await d.load();
  const made = await d.create({ email: 'new@acme.test', password: PW, role: 'viewer' });
  assert.equal(typeof made.id, 'string');
  assert.equal(d.users.length, 3, 'the list is read again');
  const dup = await d.create({ email: 'new@acme.test', password: PW, role: 'viewer' });
  assert.match(dup.error, /already exists/);
  const before = fake.calls.length;
  const bad = await d.create({ email: 'nope', password: PW });
  assert.match(bad.error, /email/);
  assert.equal(fake.calls.length, before, 'a form the server would refuse is not sent');
});

test('what the server refuses is shown as it said it: the role above yours, the last super administrator', async () => {
  const fake = new FakeAgnostic();
  const d = new U.UserDirectory(hostFor(fake));
  await d.load();
  fake.refuse = { status: 403, error: 'a role above your own cannot be granted' };
  assert.match((await d.setRole(ID2, 'super_admin')).error, /above your own/);
  fake.refuse = { status: 409, error: 'the last super administrator cannot be removed' };
  assert.match((await d.remove(ID1)).error, /last super administrator/);
  assert.equal(d.users.length, 2, 'and nothing changed');
  fake.refuse = { status: 403, error: 'use the change-password route for your own password' };
  assert.match((await d.setPassword(ID1, PW)).error, /your own password/);
  assert.equal((await d.setRole(ID2, 'operator')).error, undefined);
  assert.equal(d.get(ID2).role, 'operator', 'a change is read back');
});

test('a password is sent once and kept nowhere', async () => {
  const fake = new FakeAgnostic();
  const d = new U.UserDirectory(hostFor(fake));
  await d.load();
  assert.equal((await d.setPassword(ID2, PW)).error, undefined);
  const call = fake.calls.at(-1);
  assert.equal(call.path, '/api/v1/users/' + ID2 + '/password', 'never in a URL');
  assert.equal(call.body.password, PW);
  assert.doesNotMatch(JSON.stringify({ users: d.users, error: d.error }), new RegExp(PW), 'the directory holds no password');
  const before = fake.calls.length;
  assert.match((await d.setPassword(ID2, 'short')).error, /at least/);
  assert.equal(fake.calls.length, before, 'a short one is not sent');
});

test('no id reaches a path unchecked', async () => {
  const fake = new FakeAgnostic();
  const d = new U.UserDirectory(hostFor(fake));
  const before = fake.calls.length;
  for (const bad of ['../tenants/acme', ID1 + '/password', '', 'ABCDEF0123456789']) {
    assert.ok((await d.setRole(bad, 'viewer')).error);
    assert.ok((await d.setPassword(bad, PW)).error);
    assert.ok((await d.remove(bad)).error);
    assert.ok((await d.keysOf(bad)).error);
    assert.ok((await d.revokeKey(ID1, bad)).error);
    assert.ok((await d.revokeKey(bad, KEY)).error);
  }
  assert.equal(fake.calls.length, before, 'none of them went out');
  const t = new U.TenantDirectory(hostFor(fake));
  assert.ok((await t.update('../users', { name: 'x' })).error);
  assert.ok((await t.remove('../users')).error);
  assert.equal(fake.calls.length, before);
});

test('a user’s keys are listed by label and revoked by id, and no secret is shown', async () => {
  const fake = new FakeAgnostic();
  const d = new U.UserDirectory(hostFor(fake));
  const listed = await d.keysOf(ID2);
  assert.equal(listed.keys.length, 1);
  assert.equal(listed.keys[0].label, 'ci');
  assert.equal((await d.revokeKey(ID2, KEY)).error, undefined);
  assert.equal((await d.keysOf(ID2)).keys.length, 0);
  fake.refuse = { status: 403, error: 'nope' };
  assert.match((await d.revokeKey(ID2, KEY)).error, /nope/);
});

test('tenants: made with limits, edited, and a tenant with users stays', async () => {
  const fake = new FakeAgnostic();
  const t = new U.TenantDirectory(hostFor(fake));
  assert.equal(await t.load(), true);
  const made = await t.create({ key: 'zeta', name: 'Zeta', rate_limit: '30', max_crews: '4' });
  assert.equal(made.key, 'zeta');
  assert.equal(t.get('zeta').rate_limit, 30);
  assert.match((await t.create({ key: 'zeta' })).error, /already exists/);
  assert.equal((await t.update('zeta', { name: 'Zeta Inc', rate_limit: '', max_crews: '4' })).error, undefined);
  assert.equal(t.get('zeta').rate_limit, 0, 'emptied, it is the server’s default again');
  assert.equal(t.get('zeta').name, 'Zeta Inc');
  assert.match((await t.update('nobody', {})).error, /no such tenant/);
  assert.match((await t.remove('acme')).error, /still has users/);
  assert.equal((await t.remove('zeta')).error, undefined);
  assert.equal(t.get('zeta'), null);
});

test('an administrator is told tenants are not theirs, in place of an empty list', async () => {
  const t = new U.TenantDirectory({ request: () => Promise.resolve({ status: 403, data: { error: 'x' }, etag: null }) });
  assert.equal(await t.load(), false);
  assert.match(t.error, /super administrators/);
  assert.equal(t.tenants.length, 0);
  assert.equal(t.loaded, true);
});

// ⚠ The shell frames a plugin with `sandbox="allow-scripts allow-downloads"`, so a modal is refused:
// window.confirm answers false at once and throws nothing. A delete behind one looks like a button
// that does nothing, and no test that runs the logic without a browser can see it.
test('no plugin page asks through a modal, which its sandbox refuses', () => {
  for (const id of readdirSync(new URL('../../src/webgui/plugins/', import.meta.url))) {
    const code = pageScripts('src/webgui/plugins/' + id + '/index.html').join('\n')
      .replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
    // `this.modal.confirm(…)` is a page's own dialog, and the right answer to this.
    assert.doesNotMatch(code, /(?:window\.|[!=(]\s*)(?:confirm|alert|prompt)\(/, id + ' calls a modal');
  }
});
