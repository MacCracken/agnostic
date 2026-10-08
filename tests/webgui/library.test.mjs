// The Library view's logic (src/webgui/plugins/library/index.html), run in Node against a fake agnostic:
// the preset library (read-only) and agent definitions (POST 201 / 409, PUT 200 / 404, DELETE), as
// the server answers them.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadPage, tick } from './harness.mjs';

const page = loadPage('src/webgui/plugins/library/index.html');
const L = page.get(`({ parseTools, definitionFromFields, fieldsFromDefinition, definitionFromPresetAgent, paramsFor,
  PresetShelf, DefinitionShelf, LibraryApp })`);

class FakeAgnostic {
  constructor() {
    this.presets = new Map([['devops-lean', { name: 'devops-lean', description: 'Lean DevOps', domain: 'devops', size: 'lean', version: '1.0.0',
      workflow_mode: 'consolidated', agents: [{ agent_key: 'deploy-manager', name: 'Deployment Manager', role: 'Release manager', goal: 'Ship safely',
        backstory: 'Seasoned.', focus: 'canaries', domain: 'devops', tools: ['kubectl', 'helm'], complexity: 'high', celery_queue: 'q', redis_prefix: 'r', allow_delegation: true }] }]]);
    this.defs = new Map();
    this.revs = new Map();    // key -> revision number; the ETag is derived from it
    this.calls = [];
  }
  answer(status, data, etag) { return Promise.resolve({ status, data: data === undefined ? null : structuredClone(data), etag: etag || null }); }
  tag(key) { return '"' + String(this.revs.get(key) || 0).padStart(16, '0') + '"'; }
  body(d) { return { definition: d, unforwarded: ['focus', 'allow_delegation'].filter((k) => k in d), etag: this.tag(d.key), storage: 'patra' }; }
  stale(opts, key) { return opts && opts.ifMatch && opts.ifMatch !== this.tag(key); }
  bump(key) { this.revs.set(key, (this.revs.get(key) || 0) + 1); }
  request(method, path, body, opts) {
    this.calls.push({ method, path, body, opts });
    let m;
    if (method === 'GET' && path === '/api/v1/presets') {
      return this.answer(200, { presets: [...this.presets.values()].map((p) => ({ name: p.name, domain: p.domain, size: p.size, agent_count: p.agents.length })), total: this.presets.size });
    }
    if (method === 'GET' && (m = path.match(/^\/api\/v1\/presets\/([a-z0-9-]+)$/))) {
      return this.presets.has(m[1]) ? this.answer(200, this.presets.get(m[1])) : this.answer(404, { error: 'preset not found' });
    }
    if (method === 'GET' && path === '/api/v1/agents/definitions') {
      return this.answer(200, { definitions: [...this.defs.values()].map((d) => ({ key: d.key, name: d.name, role: d.role })), total: this.defs.size, storage: 'patra' });
    }
    if (method === 'POST' && path === '/api/v1/agents/definitions') {
      for (const k of ['agent_key', 'celery_queue', 'redis_prefix']) if (k in body) return this.answer(422, { error: "'" + k + "' is unsupported" });
      if (this.defs.has(body.key)) return this.answer(409, { error: 'exists' });
      this.defs.set(body.key, structuredClone(body));
      this.bump(body.key);
      return this.answer(201, this.body(body), this.tag(body.key));
    }
    if ((m = path.match(/^\/api\/v1\/agents\/definitions\/([a-z0-9-]+)$/))) {
      const key = m[1];
      if (method === 'GET') return this.defs.has(key) ? this.answer(200, this.body(this.defs.get(key)), this.tag(key)) : this.answer(404, { error: 'agent definition not found' });
      if (method === 'PUT') {
        if (!this.defs.has(key)) return this.answer(404, { error: 'agent definition not found' });
        if (this.stale(opts, key)) return this.answer(412, { error: 'the definition is not the revision this write was made from; read it again', code: 'revision' });
        if (body.key !== key) return this.answer(400, { error: "the 'key' in the body must match the key in the path" });
        this.defs.set(key, structuredClone(body));
        this.bump(key);
        return this.answer(200, this.body(body), this.tag(key));
      }
      if (method === 'DELETE') {
        if (!this.defs.has(key)) return this.answer(404, { error: 'agent definition not found' });
        if (this.stale(opts, key)) return this.answer(412, { error: 'stale', code: 'revision' });
        this.defs.delete(key);
        return this.answer(200, { key, status: 'deleted' });
      }
    }
    return this.answer(404, { error: 'no route' });
  }
}

function hostFor(fake, { params = '', perms = ['presets:read', 'definitions:read', 'definitions:write'], role = 'operator' } = {}) {
  const changes = new Set(), paramFns = new Set();
  const host = {
    mode: 'connected', params, navigated: [],
    request: (m, p, b, o) => fake.request(m, p, b, o),
    can: (x) => perms.includes(x), has: () => true, pluginId: () => 'library', mayWrite: () => role !== 'viewer',
    hasView: () => true,
    param(name) {
      for (const pair of host.params.split('&')) {
        const i = pair.indexOf('=');
        if ((i < 0 ? pair : pair.slice(0, i)) === name) return decodeURIComponent(i < 0 ? '' : pair.slice(i + 1));
      }
      return '';
    },
    navigate(to, p) {
      host.navigated.push([to, p || '']);
      setTimeout(() => { host.params = p || ''; for (const fn of paramFns) fn(host.params); }, 0);
      return true;
    },
    onChange: (fn) => { changes.add(fn); return () => changes.delete(fn); },
    onParams: (fn) => { paramFns.add(fn); return () => paramFns.delete(fn); },
    connect() { for (const fn of changes) fn(host); },
  };
  return host;
}

test('a definition from the editor: required fields, and optional ones only when given', () => {
  assert.match(L.definitionFromFields({ key: 'Bad Key', role: 'r', goal: 'g' }).error, /key/);
  assert.match(L.definitionFromFields({ key: 'ok', role: ' ', goal: 'g' }).error, /role/);
  assert.match(L.definitionFromFields({ key: 'ok', role: 'r', goal: '' }).error, /goal/);
  assert.match(L.definitionFromFields({ key: 'ok', role: 'r', goal: 'g', gpu_memory_min_mb: '1.5' }).error, /whole number/);
  const { def } = L.definitionFromFields({ key: 'qa-lead', name: '', role: 'QA lead', goal: 'Find bugs', backstory: '  ', tools: 'pytest, , pytest,\nplaywright',
    complexity: 'high', gpu_required: false, gpu_preferred: true, gpu_memory_min_mb: '2048', allow_delegation: true });
  assert.deepEqual({ ...def, tools: [...def.tools] }, { key: 'qa-lead', role: 'QA lead', goal: 'Find bugs', complexity: 'high',
    tools: ['pytest', 'playwright'], gpu_preferred: true, gpu_memory_min_mb: 2048, allow_delegation: true },
    'an empty optional field is absent — never "" — and tools are trimmed and deduplicated');
  const back = L.definitionFromFields(L.fieldsFromDefinition(def)).def;
  assert.deepEqual(JSON.parse(JSON.stringify(back)), JSON.parse(JSON.stringify(def)), 'the editor round-trips a definition');
  assert.deepEqual([...L.parseTools('a,b\nc, a')], ['a', 'b', 'c']);
});

test("a preset's agent becomes a definition without the fields a definition refuses", () => {
  const fake = new FakeAgnostic();
  const { def } = L.definitionFromPresetAgent(fake.presets.get('devops-lean').agents[0]);
  assert.equal(def.key, 'deploy-manager', 'agent_key becomes key');
  assert.equal('agent_key' in def, false);
  assert.equal('celery_queue' in def, false, 'the broker tier stays behind');
  assert.equal('redis_prefix' in def, false);
  assert.deepEqual([...def.tools], ['kubectl', 'helm']);
  assert.equal(def.focus, 'canaries');
  assert.equal(def.allow_delegation, true);
  assert.equal(L.paramsFor('presets', ''), '');
  assert.equal(L.paramsFor('definitions', 'qa lead'), 'tab=definitions&item=qa%20lead');
});

test('the presets: listed, and one opened', async () => {
  const fake = new FakeAgnostic();
  const shelf = new L.PresetShelf(hostFor(fake));
  assert.equal(await shelf.load(), true);
  assert.equal(shelf.items.length, 1);
  assert.equal((await shelf.read('devops-lean')).agents.length, 1);
  assert.equal(await shelf.read('nope'), null);
  assert.equal(shelf.openError, 'There is no such preset.');
  assert.equal(await shelf.read('../etc'), null, 'a name that is not one is not even asked for');
  assert.equal(fake.calls.filter((c) => c.path.includes('..')).length, 0);
});

test('definitions: create, a duplicate refused, replace, delete', async () => {
  const fake = new FakeAgnostic();
  const shelf = new L.DefinitionShelf(hostFor(fake));
  await shelf.load();
  assert.equal(shelf.items.length, 0);
  const def = L.definitionFromFields({ key: 'qa-lead', role: 'QA lead', goal: 'Find bugs', focus: 'edge cases' }).def;
  const c = await shelf.save(def, true);
  assert.equal(c.ok, true);
  assert.equal(shelf.items.length, 1, 'the list is read again');
  assert.deepEqual([...shelf.unforwarded], ['focus'], 'and the server says what it keeps but does not use');
  assert.equal((await shelf.save(def, true)).message, 'A definition with the key qa-lead already exists.', 'a POST never overwrites');
  const r = await shelf.save(Object.assign({}, def, { goal: 'Find every bug' }), false);
  assert.equal(r.ok, true);
  assert.equal(fake.defs.get('qa-lead').goal, 'Find every bug');
  assert.equal((await shelf.save({ key: 'ghost', role: 'r', goal: 'g' }, false)).message, 'ghost no longer exists — someone deleted it.');
  assert.equal((await shelf.remove('qa-lead')).ok, true);
  assert.equal(shelf.items.length, 0);
});

test('an edit names the revision it was made from, and a stale one is refused (agnostic 0.1.15)', async () => {
  const fake = new FakeAgnostic();
  const mine = new L.DefinitionShelf(hostFor(fake));
  const theirs = new L.DefinitionShelf(hostFor(fake));
  const def = L.definitionFromFields({ key: 'qa-lead', role: 'QA lead', goal: 'Find bugs' }).def;
  assert.equal((await mine.save(def, true)).ok, true);
  assert.equal(mine.etag, fake.tag('qa-lead'), 'a create keeps the revision it made');
  await theirs.read('qa-lead');
  assert.equal(theirs.etag, fake.tag('qa-lead'), 'a read keeps the revision it read');

  const t = await theirs.save(Object.assign({}, def, { goal: 'Their goal' }), false);
  assert.equal(t.ok, true, 'their edit, from the current revision, lands');
  assert.equal(fake.calls.at(-2).opts.ifMatch, '"0000000000000001"', 'sent as If-Match');
  assert.equal(theirs.etag, fake.tag('qa-lead'), 'and they now hold the new revision');

  const m = await mine.save(Object.assign({}, def, { goal: 'My goal' }), false);
  assert.equal(m.ok, false, '⭐ my edit, from the old revision, is refused');
  assert.equal(m.stale, true);
  assert.match(m.message, /Someone else changed qa-lead/);
  assert.equal(fake.defs.get('qa-lead').goal, 'Their goal', 'and does not undo theirs');

  assert.equal((await mine.remove('qa-lead')).ok, false, '⭐ nor can I delete from the old revision');
  assert.ok(fake.defs.has('qa-lead'));
  await mine.read('qa-lead');
  assert.equal((await mine.save(Object.assign({}, def, { goal: 'My goal' }), false)).ok, true, 'after a reload, my edit lands');
  assert.equal((await mine.remove('qa-lead')).ok, true, 'and so does a delete');
});

test('the app: tab and item from the link; the editor; adopting a preset agent', async () => {
  const fake = new FakeAgnostic();
  const host = hostFor(fake, { params: 'item=devops-lean' });
  const app = new L.LibraryApp(host);
  host.connect();
  await tick(5);
  assert.equal(app.tab, 'presets');
  assert.equal(app.presets.open.name, 'devops-lean', 'the preset in the link is open');

  const r = await app.adopt(app.presets.open.agents[0]);
  assert.equal(r.ok, true);
  assert.equal(app.message.text, 'Saved deploy-manager as a definition.');
  assert.ok(fake.defs.has('deploy-manager'));
  assert.equal((await app.adopt(app.presets.open.agents[0])).ok, false, 'twice is a duplicate');

  app.go('definitions', 'deploy-manager');
  await tick(10);
  assert.equal(app.tab, 'definitions');
  assert.equal(app.defs.open.key, 'deploy-manager');
  app.edit(false);
  assert.equal(app.editing.fields.key, 'deploy-manager');
  const fields = Object.assign({}, app.editing.fields, { goal: 'Ship faster', key: 'renamed' });
  assert.equal((await app.saveEdit(fields)).ok, true);
  assert.equal(fake.defs.get('deploy-manager').goal, 'Ship faster', 'an edit keeps the key it opened with');
  assert.equal(fake.defs.has('renamed'), false);

  app.edit(true);
  assert.equal((await app.saveEdit({ key: 'x', role: '', goal: 'g' })).ok, false, 'checked before it is sent');
  assert.ok(app.editing, 'and the editor stays open with what was typed');
  assert.equal((await app.saveEdit({ key: 'writer', role: 'Writer', goal: 'Write' })).ok, true);
  await tick(10);
  assert.deepEqual(host.navigated.at(-1), ['library', 'tab=definitions&item=writer'], 'a new definition opens');

  assert.equal((await app.remove('writer')).ok, true);
  assert.equal(fake.defs.has('writer'), false);
});

test('a viewer, or a build without definitions:write, cannot edit', () => {
  const fake = new FakeAgnostic();
  const viewer = new L.LibraryApp(hostFor(fake, { role: 'viewer' }));
  assert.equal(viewer.mayWrite(), false);
  viewer.edit(true);
  assert.equal(viewer.editing, null);
  assert.equal(new L.LibraryApp(hostFor(fake, { perms: ['presets:read', 'definitions:read'] })).mayWrite(), false);
  assert.equal(new L.LibraryApp(hostFor(fake, { perms: [] })).state(), 'forbidden');
});
