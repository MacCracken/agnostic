// The Library view's logic (src/webgui/plugins/library/index.html), run in Node against a fake agnostic:
// the preset library (read-only) and agent definitions (POST 201 / 409, PUT 200 / 404, DELETE), as
// the server answers them.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadPage, tick } from './harness.mjs';

const page = loadPage('src/webgui/plugins/library/index.html');
const L = page.get(`({ parseTools, definitionFromFields, fieldsFromDefinition, definitionFromPresetAgent, paramsFor,
  versionFrom, compareDefinitions, whenSaved, validVersions, parsePackage, packageKeys, packageFileName, MAX_BRIDGE_BODY,
  PresetShelf, DefinitionShelf, LibraryApp })`);

class FakeAgnostic {
  constructor() {
    this.presets = new Map([['devops-lean', { name: 'devops-lean', description: 'Lean DevOps', domain: 'devops', size: 'lean', version: '1.0.0',
      workflow_mode: 'consolidated', agents: [{ agent_key: 'deploy-manager', name: 'Deployment Manager', role: 'Release manager', goal: 'Ship safely',
        backstory: 'Seasoned.', focus: 'canaries', domain: 'devops', tools: ['kubectl', 'helm'], complexity: 'high', celery_queue: 'q', redis_prefix: 'r', allow_delegation: true }] }]]);
    this.defs = new Map();
    this.revs = new Map();    // key -> revision number; the ETag is derived from it
    this.history = new Map(); // key -> [{version, saved_at, doc}], as the server keeps them
    this.calls = [];
  }
  // Every write is a version, and one that changes nothing adds none (ADR 0035).
  keep(key, doc) {
    const h = this.history.get(key) || [];
    const last = h[h.length - 1];
    if (last && JSON.stringify(last.doc) === JSON.stringify(doc)) return;
    h.push({ version: last ? last.version + 1 : 1, saved_at: 1800000000000 + h.length, doc: structuredClone(doc) });
    this.history.set(key, h);
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
      this.keep(body.key, body);
      this.bump(body.key);
      return this.answer(201, this.body(body), this.tag(body.key));
    }
    if ((m = path.match(/^\/api\/v1\/agents\/definitions\/([a-z0-9-]+)\/versions$/)) && method === 'GET') {
      const h = this.history.get(m[1]);
      if (!h && !this.defs.has(m[1])) return this.answer(404, { error: 'agent definition not found' });
      const cur = JSON.stringify(this.defs.get(m[1]));
      const versions = (h || []).slice().reverse().map((v) => (v.broken ? { version: v.version, saved_at: v.saved_at }
        : { version: v.version, saved_at: v.saved_at, etag: '"v' + v.version + '"', definition: { key: v.doc.key, name: v.doc.name, role: v.doc.role }, current: JSON.stringify(v.doc) === cur }));
      return this.answer(200, { key: m[1], versions, total: versions.length, storage: 'patra' });
    }
    if ((m = path.match(/^\/api\/v1\/agents\/definitions\/([a-z0-9-]+)\/versions\/([0-9]+)$/)) && method === 'GET') {
      const v = (this.history.get(m[1]) || []).find((x) => x.version === Number(m[2]));
      if (!v) return this.answer(404, { error: 'no such version of this definition' });
      if (v.broken) return this.answer(409, { error: 'this version no longer reads as a definition' });
      return this.answer(200, Object.assign(this.body(v.doc), { version: v.version, saved_at: v.saved_at }));
    }
    if ((m = path.match(/^\/api\/v1\/agents\/definitions\/([a-z0-9-]+)\/rollback$/)) && method === 'POST') {
      const key = m[1];
      if (this.defs.has(key) ? this.stale(opts, key) : opts && opts.ifMatch) return this.answer(412, { error: 'stale', code: 'revision' });
      const v = (this.history.get(key) || []).find((x) => x.version === body.version);
      if (!v) return this.answer(404, { error: 'no such version of this definition' });
      if (v.unfit) return this.answer(409, { error: 'this version would be refused as a definition today' });
      this.defs.set(key, structuredClone(v.doc));
      this.keep(key, v.doc);
      this.bump(key);
      return this.answer(200, Object.assign(this.body(v.doc), { rolled_back_to: body.version }), this.tag(key));
    }
    if (method === 'POST' && path === '/api/v1/packages/export') {
      return this.answer(200, { format: 'agnostic-package/1', name: body.name, version: '1.0.0', exported_at: 1800000000000, definitions: [...this.defs.values()], total: this.defs.size });
    }
    if (method === 'POST' && path.startsWith('/api/v1/packages/import')) {
      const overwrite = path.endsWith('?overwrite=true');
      const conflicts = body.definitions.map((d) => d.key).filter((k) => this.defs.has(k));
      if (conflicts.length && !overwrite) return this.answer(409, { error: 'already stored', conflicts });
      const created = [], replaced = [];
      for (const d of body.definitions) {
        (this.defs.has(d.key) ? replaced : created).push(d.key);
        this.defs.set(d.key, structuredClone(d));
        this.keep(d.key, d);
        this.bump(d.key);
      }
      return this.answer(200, { name: body.name, created, replaced, total: created.length + replaced.length, storage: 'patra' });
    }
    if ((m = path.match(/^\/api\/v1\/agents\/definitions\/([a-z0-9-]+)$/))) {
      const key = m[1];
      if (method === 'GET') return this.defs.has(key) ? this.answer(200, this.body(this.defs.get(key)), this.tag(key)) : this.answer(404, { error: 'agent definition not found' });
      if (method === 'PUT') {
        if (!this.defs.has(key)) return this.answer(404, { error: 'agent definition not found' });
        if (this.stale(opts, key)) return this.answer(412, { error: 'the definition is not the revision this write was made from; read it again', code: 'revision' });
        if (body.key !== key) return this.answer(400, { error: "the 'key' in the body must match the key in the path" });
        this.defs.set(key, structuredClone(body));
        this.keep(key, body);
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

/** A connected app on `fake`, opened at `params`. */
async function opened(fake, params, opts) {
  const host = hostFor(fake, Object.assign({ params }, opts));
  const app = new L.LibraryApp(host);
  host.connect();
  await tick(10);
  return { host, app };
}

/** Definition `key` written `goals.length` times: version 1 says the first goal. */
function written(fake, key, goals) {
  for (const [i, goal] of goals.entries()) {
    const body = { key, name: 'QA lead', role: 'tester', goal, focus: 'edges' };
    fake.request(i ? 'PUT' : 'POST', '/api/v1/agents/definitions' + (i ? '/' + key : ''), body);
  }
}

test('the link carries the version, and only a real one', () => {
  assert.equal(L.paramsFor('definitions', 'qa', 3), 'tab=definitions&item=qa&version=3');
  assert.equal(L.paramsFor('definitions', 'qa', 0), 'tab=definitions&item=qa');
  assert.equal(L.paramsFor('definitions', '', 3), 'tab=definitions', 'no version with no item');
  for (const bad of ['', '0', '-1', '1.5', '01', 'x', '1e3', '1234567890']) assert.equal(L.versionFrom(bad), 0, bad);
  assert.equal(L.versionFrom('12'), 12);
});

test('a comparison shows a row for each field either holds, and which differ', () => {
  const rows = L.compareDefinitions({ role: 'a', goal: 'old', tools: ['x', 'y'], gpu_required: true }, { role: 'a', goal: 'new', tools: ['x', 'y'], focus: 'f' });
  const by = Object.fromEntries(rows.map((r) => [r.key, r]));
  assert.equal(by.role.differs, false, 'the same');
  assert.equal(by.goal.differs, true);
  assert.equal(by.goal.then, 'old');
  assert.equal(by.goal.now, 'new');
  assert.equal(by.tools.then, 'x, y');
  assert.equal(by.tools.differs, false, 'lists compare as what they say');
  assert.equal(by.gpu_required.then, 'yes');
  assert.equal(by.gpu_required.differs, true, 'a field only one holds differs');
  assert.equal(by.focus.then, '');
  assert.equal(by.name, undefined, 'a field neither holds is not a row');
  const gone = L.compareDefinitions({ role: 'a' }, null);
  assert.equal(gone[0].now, '', 'nothing to compare with: a deleted definition');
  assert.equal(L.whenSaved(0), 'before versions were kept', 'the first version of an old definition says when it does not know');
  assert.equal(L.whenSaved(1800000000000), '2027-01-15 08:00 UTC');
});

test('a definition shows what it has been, and a link opens one version', async () => {
  const fake = new FakeAgnostic();
  written(fake, 'qa', ['one', 'two', 'three']);
  const { app } = await opened(fake, 'tab=definitions&item=qa');
  assert.deepEqual([...app.defs.versions].map((v) => v.version), [3, 2, 1], 'newest first');
  assert.equal(app.defs.versions[0].current, true);
  assert.equal(app.defs.version, null, 'none open');

  app.go('definitions', 'qa', 1);
  await tick(10);
  assert.equal(app.versionNo, 1);
  assert.equal(app.defs.version.definition.goal, 'one', 'what it said then');
  assert.equal(app.defs.open.goal, 'three', 'and what it says now, to compare it with');

  const none = await opened(fake, 'tab=definitions&item=qa&version=9');
  assert.equal(none.app.defs.version, null);
  assert.match(none.app.defs.versionError, /no such version/);
  fake.history.get('qa')[0].broken = true;
  const broken = await opened(fake, 'tab=definitions&item=qa&version=1');
  assert.match(broken.app.defs.versionError, /no longer reads/);
  assert.equal(broken.app.defs.versions.at(-1).definition, undefined, 'it stays on the list, saying only that');
});

test('a rollback is a new version, sent from the revision that was read', async () => {
  const fake = new FakeAgnostic();
  written(fake, 'qa', ['one', 'two']);
  const { app, host } = await opened(fake, 'tab=definitions&item=qa&version=1');
  const r = await app.rollback(1);
  assert.equal(r.ok, true);
  const call = fake.calls.find((c) => c.path.endsWith('/rollback'));
  assert.deepEqual(JSON.parse(JSON.stringify(call.body)), { version: 1 });
  assert.equal(call.opts.ifMatch, '"0000000000000002"', '⭐ it says which revision it was made from');
  assert.equal(fake.defs.get('qa').goal, 'one');
  assert.equal(fake.history.get('qa').length, 3, '⭐ as a new version');
  await tick(10);
  assert.deepEqual(host.navigated.at(-1), ['library', 'tab=definitions&item=qa'], 'back to the definition');
  assert.match(app.message.text, /says what version 1 said/);
  assert.equal(app.defs.open.goal, 'one');
  assert.deepEqual([...app.defs.versions].map((v) => v.version), [3, 2, 1], 'and the list holds it');
});

test('a rollback from a stale page undoes nobody', async () => {
  const fake = new FakeAgnostic();
  written(fake, 'qa', ['one', 'two']);
  const { app } = await opened(fake, 'tab=definitions&item=qa&version=1');
  fake.request('PUT', '/api/v1/agents/definitions/qa', { key: 'qa', role: 'tester', goal: 'theirs' });
  const r = await app.rollback(1);
  assert.equal(r.ok, false);
  assert.equal(r.stale, true);
  assert.match(app.message.text, /Someone else changed qa/);
  assert.equal(fake.defs.get('qa').goal, 'theirs', '⭐ their edit stands');

  fake.history.get('qa')[0].unfit = true;
  await app.defs.read('qa');
  assert.match((await app.rollback(1)).message, /would be refused as a definition today/);
  assert.match((await app.rollback(99)).message, /no version 99/);
});

test('a deleted definition can be brought back, and says it can', async () => {
  const fake = new FakeAgnostic();
  written(fake, 'qa', ['one', 'two']);
  const { app, host } = await opened(fake, 'tab=definitions&item=qa');
  await app.remove('qa');
  assert.equal(app.message.deleted, 'qa', '⭐ the message offers the way back');
  assert.match(app.message.text, /Deleted qa/);
  await tick(10);

  app.go('definitions', 'qa');
  await tick(10);
  assert.equal(app.defs.open, null, 'it is gone');
  assert.match(app.defs.openError, /no such definition/);
  assert.deepEqual([...app.defs.versions].map((v) => v.version), [2, 1], '⭐ and its versions are not');

  app.go('definitions', 'qa', 1);
  await tick(10);
  assert.equal(app.defs.version.definition.goal, 'one');
  const r = await app.rollback(1);
  assert.equal(r.ok, true, '⭐ it comes back');
  const call = fake.calls.filter((c) => c.path.endsWith('/rollback')).at(-1);
  assert.equal(call.opts, undefined, 'with no revision to send: nothing is current');
  assert.equal(fake.defs.get('qa').goal, 'one');
  await tick(10);
  assert.equal(app.defs.open.goal, 'one');
  assert.equal(app.defs.openError, '');
  assert.deepEqual(host.navigated.at(-1), ['library', 'tab=definitions&item=qa']);
});

test('a key nothing was ever written under has no past to show', async () => {
  const fake = new FakeAgnostic();
  const { app } = await opened(fake, 'tab=definitions&item=nobody');
  assert.equal(app.defs.versions.length, 0);
  assert.match(app.defs.openError, /no such definition/);
  assert.equal(app.defs.versionsError, '', '⭐ having none is not a failure to read them');
});

test('a file is a package, or says what it is not', () => {
  assert.match(L.parsePackage('nope').error, /not JSON/);
  assert.match(L.parsePackage('[1]').error, /not a package/);
  assert.match(L.parsePackage('{"format":"agnostic-package/2","definitions":[{}]}').error, /not an agnostic package/);
  assert.match(L.parsePackage('{"format":"agnostic-package/1","definitions":[]}').error, /holds no definitions/);
  const { pkg } = L.parsePackage('{"format":"agnostic-package/1","name":"k","definitions":[{"key":"a"},{"role":"r"}]}');
  assert.deepEqual([...L.packageKeys(pkg)], ['a', '?'], 'what cannot be named is the door\'s to refuse');
  assert.equal(L.packageFileName(1800000000000), 'agnostic-definitions-2027-01-15.json');
});

test('export hands the view a file, and import goes in whole or asks', async () => {
  const fake = new FakeAgnostic();
  written(fake, 'one', ['g1']);
  written(fake, 'two', ['g2']);
  const { app } = await opened(fake, 'tab=definitions');

  const out = await app.exportAll(1800000000000);
  assert.equal(out.ok, true);
  assert.equal(out.file, 'agnostic-definitions-2027-01-15.json');
  assert.match(app.message.text, /Exported 2/);
  const pkg = out.text;

  assert.equal(app.choosePackage('not a package'), false);
  assert.match(app.message.text, /not JSON/);
  assert.equal(app.importing, null, 'nothing waits');

  assert.equal(app.choosePackage(pkg), true);
  assert.deepEqual([...app.importing.keys], ['one', 'two'], 'it shows what the package holds first');
  assert.equal(fake.calls.filter((c) => c.path.startsWith('/api/v1/packages/import')).length, 0, '⭐ and nothing goes in until asked');

  fake.defs.delete('one');
  const r = await app.runImport(false);
  assert.equal(r.ok, false);
  assert.deepEqual([...app.importing.conflicts], ['two'], '⭐ a key already stored stops it, and says which');
  assert.equal(fake.defs.has('one'), false, 'and nothing went in');

  const over = await app.runImport(true);
  assert.equal(over.ok, true, 'replacing is asked for');
  assert.equal(fake.calls.at(-2).path, '/api/v1/packages/import?overwrite=true');
  assert.match(app.message.text, /Imported 1 new and replaced 1/);
  assert.equal(app.importing, null);
  assert.equal(fake.defs.has('one'), true);
  app.choosePackage(pkg);
  app.cancelImport();
  assert.equal(app.importing, null);
});

test('a package past what the bridge carries is refused here, with where to take it', async () => {
  const fake = new FakeAgnostic();
  const { app } = await opened(fake, 'tab=definitions');
  const big = JSON.stringify({ format: 'agnostic-package/1', name: 'k', definitions: [{ key: 'a', role: 'r', goal: 'x'.repeat(L.MAX_BRIDGE_BODY) }] });
  app.choosePackage(big);
  const before = fake.calls.length;
  const r = await app.runImport(false);
  assert.equal(r.ok, false);
  assert.match(r.message, /256 KB/);
  assert.match(r.message, /POST \/api\/v1\/packages\/import/);
  assert.equal(fake.calls.length, before, 'nothing was sent');
});

