// The Crews view's logic (src/webgui/plugins/crews/index.html), run in Node against a fake agnostic.
//
// The fake answers what the view reaches through the bridge the way the server does: the listing
// by cursor with `?status=` (0.1.10), a crew's outcome, its plan, its events by `?after=` cursor,
// and cancel — including a cancelled crew whose finished tasks' results arrive after the cancel.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadPage, tick } from './harness.mjs';

const page = loadPage('src/webgui/plugins/crews/index.html');
const C = page.get(`({ FILTERS, PAGE_SIZE, mergeFirstPage, paramsFor, listsBefore, validRow, taskTitle, fmtMicro,
  fmtTokens, fmtDuration, CrewList, CrewDetail, CrewsApp })`);

const uuid = (n) => '00000000-0000-4000-8000-' + String(n).padStart(12, '0');
const ACTIVE = ['pending', 'running'];

class FakeAgnostic {
  constructor() {
    this.crews = [];          // listing rows, any order
    this.docs = new Map();    // id → GET /crews/{id}
    this.plans = new Map();   // id → plan
    this.events = new Map();  // id → [{seq, at_ms, type, data}]
    this.status = new Map();  // id → live status for /events
    this.held = new Set();    // ids the ledger holds (events and plan answer)
    this.oldest = new Map();  // id → the oldest seq the window still holds (absent: 1)
    this.calls = [];
    this.cancelAnswer = 200;
  }
  answer(status, data) { return Promise.resolve({ status, data: data === undefined ? null : structuredClone(data), etag: null }); }
  addCrew(n, status, extra = {}) {
    const id = uuid(n);
    const row = Object.assign({ crew_id: id, name: 'crew ' + n, status, submitted_at: 1000 + n }, extra);
    this.crews.push(row);
    this.docs.set(id, { crew_id: id, status, name: row.name, submitted_at: row.submitted_at, results: [], usage: {} });
    this.status.set(id, status);
    this.events.set(id, []);
    this.held.add(id);
    return id;
  }
  emit(id, type, data) {
    const evs = this.events.get(id);
    evs.push({ seq: evs.length + 1, at_ms: evs.length * 10, type, data });
  }
  request(method, path, body) {
    this.calls.push({ method, path, body });
    const [bare, query] = path.split('?');
    const q = new URLSearchParams(query || '');
    let m;
    if (method === 'GET' && bare === '/api/v1/crews') {
      const limit = Number(q.get('limit') || 50);
      const st = q.get('status');
      let rows = this.crews.slice().sort((a, b) => (C.listsBefore(a, b) ? -1 : 1));
      if (st) rows = rows.filter((c) => (st === 'active' ? ACTIVE.includes(c.status) : c.status === st));
      const before = q.get('before');
      if (before) {
        const [ms, id] = [Number(before.split('.')[0]), before.slice(before.indexOf('.') + 1)];
        rows = rows.filter((c) => c.submitted_at < ms || (c.submitted_at === ms && c.crew_id < id));
      }
      const pageRows = rows.slice(0, limit);
      const out = { crews: pageRows, scope: 'acme' };
      if (rows.length > limit) { const l = pageRows[pageRows.length - 1]; out.next = l.submitted_at + '.' + l.crew_id; }
      return this.answer(200, out);
    }
    if ((m = bare.match(/^\/api\/v1\/crews\/([0-9a-f-]{36})$/)) && method === 'GET') {
      const d = this.docs.get(m[1]);
      return d ? this.answer(200, d) : this.answer(404, { error: 'crew not found' });
    }
    if ((m = bare.match(/^\/api\/v1\/crews\/([0-9a-f-]{36})\/plan$/)) && method === 'GET') {
      const p = this.plans.get(m[1]);
      return p && this.held.has(m[1]) ? this.answer(200, p) : this.answer(404, { error: 'not held' });
    }
    if ((m = bare.match(/^\/api\/v1\/crews\/([0-9a-f-]{36})\/events$/)) && method === 'GET') {
      if (!this.held.has(m[1])) return this.answer(404, { error: 'crew not found' });
      // As the server's ring answers: what is still held after the cursor, and how many
      // numbers after it had already left the window (`missed`).
      const after = Number(q.get('after') || 0);
      const oldest = this.oldest.get(m[1]) || 1;
      const evs = this.events.get(m[1]).filter((e) => e.seq > Math.max(after, oldest - 1));
      return this.answer(200, { crew_id: m[1], status: this.status.get(m[1]), events: evs,
        next: Math.max(after, this.events.get(m[1]).length), missed: Math.max(0, oldest - (after + 1)),
        lost_events: 0, dropped_events: oldest - 1 });
    }
    if ((m = bare.match(/^\/api\/v1\/crews\/([0-9a-f-]{36})\/cancel$/)) && method === 'POST') {
      if (this.cancelAnswer !== 200) return this.answer(this.cancelAnswer, { error: 'no' });
      this.status.set(m[1], 'cancelled');
      this.docs.get(m[1]).status = 'cancelled';
      return this.answer(200, { crew_id: m[1], status: 'cancelled' });
    }
    return this.answer(404, { error: 'no route ' + method + ' ' + bare });
  }
}

/** A host for the view, wired to `fake` — the kit's interface. */
function hostFor(fake, { params = '', perms = ['crews:read', 'crews:write'], role = 'operator', views = ['crews', 'swarm'], navigate = true } = {}) {
  const changes = new Set(), paramFns = new Set();
  const host = {
    mode: 'connected', params, navigated: [],
    request: (m, p, b, o) => fake.request(m, p, b, o),
    can: (x) => perms.includes(x), has: (f) => (f === 'navigate' ? navigate : true),
    pluginId: () => 'crews', role: () => role, mayWrite: () => role !== 'viewer',
    hasView: (id) => views.includes(id),
    param(name) {
      for (const pair of host.params.split('&')) {
        const i = pair.indexOf('=');
        if ((i < 0 ? pair : pair.slice(0, i)) === name) return decodeURIComponent(i < 0 ? '' : pair.slice(i + 1));
      }
      return '';
    },
    navigate(to, p) {
      if (!navigate) return false;
      host.navigated.push([to, p || '']);
      // The shell answers a navigate to this same view with its new params.
      if (to === 'crews') setTimeout(() => { host.params = p || ''; for (const fn of paramFns) fn(host.params); }, 0);
      return true;
    },
    onChange: (fn) => { changes.add(fn); return () => changes.delete(fn); },
    onParams: (fn) => { paramFns.add(fn); return () => paramFns.delete(fn); },
    connect() { for (const fn of changes) fn(host); },
  };
  return host;
}

test('mergeFirstPage keeps later pages and replaces what the fresh page covers', () => {
  const row = (n, st = 'completed') => ({ crew_id: uuid(n), status: st, submitted_at: 1000 + n });
  // held: 9..5 (two pages of the old listing), next after 5
  const held = [row(9, 'running'), row(8), row(7), row(6), row(5)];
  // fresh first page of 3: a new crew 10, and 9 finished
  const fresh = [row(10, 'running'), row(9), row(8)];
  const m = C.mergeFirstPage(held, 'cursor-after-5', fresh, 'cursor-after-8');
  assert.deepEqual(m.crews.map((c) => c.crew_id), [10, 9, 8, 7, 6, 5].map(uuid), 'new first, the rest kept after');
  assert.equal(m.crews[1].status, 'completed', 'and a crew the fresh page covers takes its fresh state');
  assert.equal(m.next, 'cursor-after-5', 'the cursor continues past what was kept');
  const all = C.mergeFirstPage(held, 'x', fresh, null);
  assert.equal(all.crews.length, 3, 'a fresh page with no next IS the whole listing');
  assert.equal(all.next, null);
  const none = C.mergeFirstPage(held, 'x', [row(9)], 'c9');
  assert.deepEqual(none.crews.map((c) => c.crew_id), [9, 8, 7, 6, 5].map(uuid));
  const gone = C.mergeFirstPage([row(9, 'running'), row(8)], null, [row(8)], null);
  assert.deepEqual(gone.crews.map((c) => c.crew_id), [uuid(8)], 'a crew that left the filter goes');
});

test('params name the filter and the crew, leaving out the defaults', () => {
  assert.equal(C.paramsFor('all', ''), '');
  assert.equal(C.paramsFor('active', ''), 'status=active');
  assert.equal(C.paramsFor('all', uuid(1)), 'crew=' + uuid(1));
  assert.equal(C.paramsFor('failed', uuid(2)), 'status=failed&crew=' + uuid(2));
  assert.equal(C.validRow({ crew_id: 'nope', status: 'running' }), false);
  assert.equal(C.taskTitle('', 2), 'Task 3');
  assert.equal(C.fmtMicro(4500), '$0.0045');
  assert.equal(C.fmtMicro(0), '$0', 'a real zero cost');
  assert.equal(C.fmtTokens(15300), '15k');
  assert.equal(C.fmtDuration(65000), '1 min 5 s');
});

test('the list pages by cursor under a status filter the server applies', async () => {
  const fake = new FakeAgnostic();
  for (let n = 1; n <= C.PAGE_SIZE + 5; n++) fake.addCrew(n, n % 5 === 0 ? 'running' : 'completed');
  const list = new C.CrewList(hostFor(fake));
  assert.equal(await list.load('all'), true);
  assert.equal(list.crews.length, C.PAGE_SIZE, 'a page');
  assert.equal(list.crews[0].crew_id, uuid(C.PAGE_SIZE + 5), 'newest first');
  assert.ok(list.next, 'with a cursor');
  assert.equal(list.scope, 'acme');
  await list.more();
  assert.equal(list.crews.length, C.PAGE_SIZE + 5, 'and the rest');
  assert.equal(list.next, null);
  assert.equal(new Set(list.crews.map((c) => c.crew_id)).size, list.crews.length, 'once each');

  await list.load('active');
  assert.match(fake.calls.at(-1).path, /[?&]status=active(&|$)/, 'the filter is the server\'s');
  assert.ok(list.crews.every((c) => c.status === 'running'));
  assert.equal(list.crews.length, 11);
  assert.equal(list.hasActive(), true);

  // A crew finishes: the refresh drops it from the active filter.
  fake.crews.find((c) => c.crew_id === uuid(5)).status = 'completed';
  await list.refresh();
  assert.equal(list.crews.some((c) => c.crew_id === uuid(5)), false);
  assert.equal(list.crews.length, 10);

  // A load answered after a newer one began is dropped.
  const slow = list.load('failed');
  const fast = list.load('completed');
  await Promise.all([slow, fast]);
  assert.equal(list.filter, 'completed');
  assert.ok(list.crews.every((c) => c.status === 'completed'));
});

test('a listing the server refuses says why', async () => {
  const fake = new FakeAgnostic();
  fake.request = () => Promise.resolve({ status: 401, data: { error: 'missing credentials' } });
  const list = new C.CrewList(hostFor(fake));
  assert.equal(await list.load(), false);
  assert.equal(list.error, 'Sign in to see your crews.');
});

test('an open crew: plan, progress by cursor, then the results and what they cost', async () => {
  const fake = new FakeAgnostic();
  const id = fake.addCrew(1, 'pending', { tasks_submitted: 2 });
  fake.plans.set(id, { crew_id: id, name: 'crew 1', process: 'parallel', max_concurrency: 2, agents: [],
    tasks: [{ task_id: 't-a', index: 0, description: 'Read the logs\nall of them', priority: 'normal', dependencies: [] },
            { task_id: 't-b', index: 1, description: 'Write the report', priority: 'high', dependencies: [0] }] });
  const d = new C.CrewDetail(hostFor(fake), id, { pollMs: 5 });
  await d.start();
  assert.equal(d.tasks.length, 2, 'the plan\'s tasks');
  assert.equal(d.tasks[0].title, 'Read the logs all of them');
  assert.deepEqual([...d.tasks[1].deps], [0]);
  assert.equal(d.waiting(), true);

  fake.status.set(id, 'running');
  fake.emit(id, 'crew_started', { task_count: 2 });
  fake.emit(id, 'task_started', { task_id: 't-a', agent: 'reader' });
  await tick(20);
  assert.equal(d.status, 'running');
  assert.equal(d.tasks[0].status, 'running');
  assert.equal(d.tasks[0].agent, 'reader');

  fake.emit(id, 'task_completed', { task_id: 't-a', status: 'completed' });
  fake.emit(id, 'token', { task_id: 't-b', token: 'x' });
  fake.emit(id, 'task_started', { task_id: 't-b' });
  fake.emit(id, 'task_completed', { task_id: 't-b', status: 'completed' });
  fake.emit(id, 'crew_completed', { status: 'completed', wall_ms: 1500 });
  Object.assign(fake.docs.get(id), {
    status: 'completed', started_at: 2000, finished_at: 3500, engine_mode: 'live',
    results: [{ task_id: 't-a', status: 'completed', output: 'logs read', agent_key: 'reader', usage: { total_tokens: 100, cost_micro_usd: 300, duration_ms: 800 } },
              { task_id: 't-b', status: 'completed', output: 'report', agent_key: 'writer', usage: { total_tokens: 50, duration_ms: 700 } }],
    usage: { total_tokens: 150, metered_tasks: 2, costed_tasks: 1, cost_micro_usd: 300 },
  });
  fake.status.set(id, 'completed');
  await tick(30);
  assert.equal(d.waiting(), false, 'finished');
  assert.equal(d.finalRead, true, 'and read once more for its results');
  assert.equal(d.tasks[0].output, 'logs read');
  assert.equal(d.tasks[1].usage.total_tokens, 50);
  assert.equal(d.tasks[0].agent, 'reader', 'the result names the agent the event did');
  assert.equal(d.tasks[1].agent, 'writer', 'and one whose task_started named none (agnostic 0.1.15)');
  assert.equal(d.tokens, 1, 'token events are counted, not listed');
  assert.ok(d.events.some((e) => e.text.startsWith('crew completed')));
  const s = d.summary();
  assert.equal(s.tokens, 150);
  assert.equal(s.cost, 300);
  assert.equal(s.done, 2);
  assert.equal(s.took, 1500);
  assert.equal(s.process, 'parallel');
  const polls = fake.calls.filter((c) => c.path.includes('/events')).length;
  await tick(30);
  assert.equal(fake.calls.filter((c) => c.path.includes('/events')).length, polls, 'and it stops polling');
});

test('events that left the window are counted, and the outcome settles their tasks', async () => {
  // H3: a reader that falls behind the server's window is told how far (`missed`) and gets
  // what is still held, from the oldest. Nothing mid-run can recover the events it lost —
  // the crew's own document carries no task results until it ends — so the task they were
  // about stays as last seen until the final read settles it.
  const fake = new FakeAgnostic();
  const id = fake.addCrew(5, 'running');
  fake.plans.set(id, { crew_id: id, process: 'sequential', agents: [],
    tasks: [{ task_id: 't-a', index: 0, description: 'one', dependencies: [] },
            { task_id: 't-b', index: 1, description: 'two', dependencies: [] }] });
  fake.emit(id, 'crew_started', { task_count: 2 });
  fake.emit(id, 'task_started', { task_id: 't-a' });
  fake.emit(id, 'task_completed', { task_id: 't-a', status: 'completed' });
  fake.emit(id, 'task_started', { task_id: 't-b' });
  fake.oldest.set(id, 4);
  const d = new C.CrewDetail(hostFor(fake), id, { pollMs: 5 });
  await d.start();
  assert.equal(d.missed, 3, 'the three events that left the window are counted');
  assert.equal(d.tasks[0].status, 'pending', 'the task they were about is stale mid-run');
  assert.equal(d.tasks[1].status, 'running', 'what was still held is applied');
  assert.equal(d.events.length, 1, 'and only it is listed');
  await tick(15);
  const evCalls = fake.calls.filter((c) => c.path.includes('/events'));
  assert.ok(evCalls.length >= 2);
  assert.match(evCalls[1].path, /[?&]after=4(&|$)/, 'the reader goes on from the window, not from 0');

  fake.emit(id, 'task_completed', { task_id: 't-b', status: 'completed' });
  fake.emit(id, 'crew_completed', { status: 'completed' });
  Object.assign(fake.docs.get(id), { status: 'completed',
    results: [{ task_id: 't-a', status: 'completed', output: 'a' }, { task_id: 't-b', status: 'completed', output: 'b' }] });
  fake.status.set(id, 'completed');
  await tick(30);
  assert.equal(d.waiting(), false);
  assert.equal(d.finalRead, true, 'the end is read once more');
  assert.equal(d.tasks[0].status, 'completed', 'which settles the task whose events were missed');
  assert.equal(d.tasks[0].output, 'a');
  assert.equal(d.missed, 3, 'and the gap is counted once, not again on every later poll');
});

test('cost is shown only when a call was priced; tokens only when metered', async () => {
  const fake = new FakeAgnostic();
  const id = fake.addCrew(2, 'completed');
  Object.assign(fake.docs.get(id), { usage: { total_tokens: 0, metered_tasks: 0, costed_tasks: 0 }, engine_mode: 'placeholder' });
  const d = new C.CrewDetail(hostFor(fake), id, { pollMs: 5 });
  await d.start();
  const s = d.summary();
  assert.equal(s.tokens, null, 'nothing metered is not zero tokens');
  assert.equal(s.cost, null, 'nothing priced is not $0');
  assert.equal(s.mode, 'placeholder');
  assert.equal(d.planNote.includes('no longer held'), true, 'a crew with no plan says why');
});

test('cancel: the crew stays watched until its last tasks report, and their results show', async () => {
  const fake = new FakeAgnostic();
  const id = fake.addCrew(3, 'running');
  fake.plans.set(id, { crew_id: id, process: 'sequential', agents: [],
    tasks: [{ task_id: 't1', index: 0, description: 'one', dependencies: [] }, { task_id: 't2', index: 1, description: 'two', dependencies: [] }] });
  const d = new C.CrewDetail(hostFor(fake), id, { pollMs: 5 });
  await d.start();
  fake.emit(id, 'task_started', { task_id: 't1' });
  await tick(15);
  const r = await d.cancel();
  assert.equal(r.ok, true);
  assert.equal(d.status, 'cancelled');
  assert.equal(d.waiting(), true, 'still waiting: a task was running');
  // The running task finishes; the engine's last word brings its result.
  fake.emit(id, 'task_completed', { task_id: 't1', status: 'completed' });
  fake.emit(id, 'crew_completed', { status: 'cancelled' });
  fake.docs.get(id).results = [{ task_id: 't1', status: 'completed', output: 'kept' }];
  await tick(40);
  assert.equal(d.waiting(), false);
  assert.equal(d.tasks[0].output, 'kept', 'the finished task\'s result is shown');
  assert.equal(d.tasks[1].status, 'pending', 'and the task that never started says so');
  assert.equal((await d.cancel()).ok, false, 'a finished crew cannot be cancelled again');

  const fake2 = new FakeAgnostic();
  const id2 = fake2.addCrew(4, 'running');
  fake2.cancelAnswer = 409;
  const d2 = new C.CrewDetail(hostFor(fake2), id2, { pollMs: 5 });
  await d2.start();
  assert.equal((await d2.cancel()).message, 'It had already finished.');
  d2.stop();
});

test('a crew a server restart interrupted ends interrupted: filtered, settled, never waited on', async () => {
  // agnostic 0.1.13 (ADR 0013): a crew accepted before a restart that had no outcome answers
  // 200 `interrupted` — terminal, no finished_at, its work lost — where it used to answer 404.
  assert.ok(C.FILTERS.some((f) => f.id === 'interrupted' && f.status === 'interrupted'), 'an Interrupted filter');
  assert.equal(C.paramsFor('interrupted', ''), 'status=interrupted');

  const fake = new FakeAgnostic();
  const id = fake.addCrew(6, 'running', { tasks_submitted: 2 });
  fake.plans.set(id, { crew_id: id, process: 'sequential', agents: [],
    tasks: [{ task_id: 't-a', index: 0, description: 'one', dependencies: [] },
            { task_id: 't-b', index: 1, description: 'two', dependencies: [] }] });
  fake.emit(id, 'crew_started', { task_count: 2 });
  fake.emit(id, 'task_started', { task_id: 't-a' });
  const d = new C.CrewDetail(hostFor(fake), id, { pollMs: 5 });
  await d.start();
  assert.equal(d.waiting(), true, 'watched while it runs');

  // The server restarts: its ledger is gone (events 404) and the crew answers interrupted.
  fake.held.delete(id);
  Object.assign(fake.docs.get(id), { status: 'interrupted', results: [], task_count: 0, tasks_submitted: 2,
    usage: { total_tokens: 0, metered_tasks: 0, costed_tasks: 0 }, interrupted_at: 5000,
    error: "the server restarted before this crew finished; tasks still in progress were lost" });
  fake.crews.find((c) => c.crew_id === id).status = 'interrupted';
  await tick(30);
  assert.equal(d.status, 'interrupted', 'the final read says interrupted');
  assert.equal(d.waiting(), false, '⭐ and it is not waited on: it will never run');
  assert.equal(d.notFound, false, 'it is not "no such crew"');
  const s = d.summary();
  assert.equal(s.took, null, 'no took: the downtime is not run time');
  assert.equal(s.interrupted, 5000, 'when it was declared interrupted');
  assert.match(s.error, /restarted/, 'and the error says why');
  assert.equal(s.tokens, null, 'nothing metered');
  const polls = fake.calls.filter((c) => c.path.includes('/events')).length;
  await tick(20);
  assert.equal(fake.calls.filter((c) => c.path.includes('/events')).length, polls, 'and it stops polling');

  const list = new C.CrewList(hostFor(fake));
  await list.load('interrupted');
  assert.match(fake.calls.at(-1).path, /[?&]status=interrupted(&|$)/, 'the filter is the server\'s');
  assert.deepEqual(list.crews.map((c) => c.crew_id), [id]);
});

test('a crew of another tenant, or none, is not found', async () => {
  const fake = new FakeAgnostic();
  const d = new C.CrewDetail(hostFor(fake), uuid(99), { pollMs: 5 });
  await d.start();
  assert.equal(d.notFound, true);
  assert.match(d.error, /no such crew/);
});

test('the app follows its params, and changes them through the shell', async () => {
  const fake = new FakeAgnostic();
  const a = fake.addCrew(1, 'running');
  fake.addCrew(2, 'failed');
  const host = hostFor(fake, { params: 'status=active&crew=' + a });
  const app = new C.CrewsApp(host, { pollMs: 5 });
  host.connect();
  await tick(10);
  assert.equal(app.state(), 'ready');
  assert.equal(app.list.filter, 'active', 'the filter from the link');
  assert.equal(app.selected, a, 'and the crew');
  assert.ok(app.detail);

  app.go('failed', '');
  assert.deepEqual(host.navigated.at(-1), ['crews', 'status=failed'], 'through the shell, so the URL is a link');
  await tick(10);
  assert.equal(app.list.filter, 'failed');
  assert.equal(app.detail, null, 'and nothing is open');

  host.params = 'crew=not-a-uuid';
  app.applyParams(false);
  assert.equal(app.selected, '', 'a malformed crew id opens nothing');
  assert.equal(app.list.filter, 'all', 'an absent filter is all');

  // Without the shell's navigation the view applies the change itself.
  const h2 = hostFor(fake, { navigate: false });
  const app2 = new C.CrewsApp(h2, { pollMs: 5 });
  h2.connect();
  app2.go('all', a);
  assert.equal(app2.selected, a);
  if (app2.detail) app2.detail.stop();
  if (app.detail) app.detail.stop();
});

test('cancel is offered only to a role that may write, with crews:write', () => {
  const fake = new FakeAgnostic();
  assert.equal(new C.CrewsApp(hostFor(fake)).mayCancel(), true);
  assert.equal(new C.CrewsApp(hostFor(fake, { role: 'viewer' })).mayCancel(), false);
  assert.equal(new C.CrewsApp(hostFor(fake, { perms: ['crews:read'] })).mayCancel(), false);
  const h = hostFor(fake, { perms: [] });
  const app = new C.CrewsApp(h);
  assert.equal(app.state(), 'forbidden', 'without crews:read it shows nothing');
  h.mode = 'standalone';
  assert.equal(app.state(), 'standalone');
});
