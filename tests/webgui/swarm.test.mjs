// Swarm Command's logic (src/webgui/plugins/swarm/index.html), run in Node against a fake agnostic.
//
// The fake implements what the plugin reaches through the bridge, the way 0.1.9's server answers
// it: plugin documents with revisions (ETag / If-Match / If-None-Match, 412), crews with numbered
// and timed events (`?after=` cursor), the plan route, outcomes with metered usage, and
// Idempotency-Key replays. The simulator, the spec normalizer and the crew builder run unchanged.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadPage, tick } from './harness.mjs';

const page = loadPage('src/webgui/plugins/swarm/index.html');
const S = page.get(`({ defaultSpec, normalizeSpec, specToCrewRequest, validateSpec, compileSpec, specBytes, storableSpec,
  capRuns, fitSpec, planFromServer, taskTitle, SwarmLibrary, LiveCrewSource, Sim, MockSource, estimateSpec, specSig,
  SPEC_MAX_BYTES, SPEC_RESERVE, SPEC_MAX_LIVE_RUNS, SPEC_MAX_SIM_RUNS, SPEC_VERSION })`);

/* ------------------------------------------------------------------ the fake server */

const uuid = (n) => '00000000-0000-4000-8000-' + String(n).padStart(12, '0');
function tagOf(text) {
  let h = 0xcbf29ce484222325n;
  for (const ch of Buffer.from(text)) { h ^= BigInt(ch); h = (h * 0x100000001b3n) & 0xffffffffffffffffn; }
  return '"' + h.toString(16).padStart(16, '0') + '"';
}

class FakeAgnostic {
  constructor() {
    this.docs = new Map();      // key → stored text
    this.crews = new Map();     // id → crew
    this.calls = [];
    this.inject = [];           // statuses to answer the next requests with, before doing anything
    this.n = 0;
  }
  answer(status, data, etag) { return Promise.resolve({ status, data: data === undefined ? null : JSON.parse(JSON.stringify(data)), etag: etag || null }); }
  request(method, path, body, opts = {}) {
    this.calls.push({ method, path, body, opts });
    if (this.inject.length) { const st = this.inject.shift(); if (st !== null) return this.answer(st, { error: 'injected ' + st }); }
    const [bare, query] = path.split('?');
    const q = new URLSearchParams(query || '');
    let m;
    if (bare === '/api/v1/plugins/swarm/data' && method === 'GET') {
      return this.answer(200, { documents: [...this.docs].map(([key, t]) => ({ key, updated: 1, bytes: t.length })), total: this.docs.size, scope: '_' });
    }
    if ((m = /^\/api\/v1\/plugins\/swarm\/data\/([a-z0-9._-]+)$/.exec(bare))) {
      const key = m[1], cur = this.docs.get(key);
      if (method === 'GET') return cur === undefined ? this.answer(404, { error: 'no such document' }) : this.answer(200, JSON.parse(cur), tagOf(cur));
      if (opts.ifNoneMatch === '*' && cur !== undefined) return this.answer(412, { error: 'exists', code: 'revision' });
      if (opts.ifMatch && (cur === undefined || tagOf(cur) !== opts.ifMatch)) return this.answer(412, { error: 'stale', code: 'revision' });
      if (method === 'PUT') {
        const text = JSON.stringify(body);
        this.docs.set(key, text);
        return this.answer(cur === undefined ? 201 : 200, { key, etag: tagOf(text), created: cur === undefined });
      }
      if (method === 'DELETE') { if (cur === undefined) return this.answer(404, {}); this.docs.delete(key); return this.answer(200, {}); }
    }
    if (bare === '/api/v1/crews' && method === 'POST') {
      for (const c of this.crews.values()) if (opts.idempotencyKey && c.key === opts.idempotencyKey) return this.answer(202, Object.assign(this.accepted(c), { replayed: true }));
      const id = uuid(++this.n);
      const c = { id, key: opts.idempotencyKey || null, request: body, status: 'pending', events: [], t: 0, results: [], usage: null,
        taskIds: body.tasks.map((_, i) => uuid(1000 * this.n + i)), times: { submitted: 1_000_000, started: 0, finished: 0 } };
      this.crews.set(id, c);
      return this.answer(202, this.accepted(c));
    }
    if ((m = /^\/api\/v1\/crews\/([0-9a-f-]{36})\/events$/.exec(bare))) {
      const c = this.crews.get(m[1]);
      if (!c) return this.answer(404, {});
      const after = Number(q.get('after') || 0);
      const events = c.events.filter((e) => e.seq > after);
      const next = c.events.length ? c.events[c.events.length - 1].seq : after;
      return this.answer(200, { crew_id: c.id, status: c.status, events, next: Math.max(next, after), missed: 0, lost_events: 0, dropped_events: 0 });
    }
    if ((m = /^\/api\/v1\/crews\/([0-9a-f-]{36})\/plan$/.exec(bare))) {
      const c = this.crews.get(m[1]);
      if (!c || c.noPlan) return this.answer(404, { error: 'not held' });
      return this.answer(200, { crew_id: c.id, name: c.request.name, process: c.request.process || 'sequential', max_concurrency: c.request.max_concurrency,
        agents: c.request.agents.map((a) => ({ key: a.key, name: a.name, role: a.role, llm_model: a.llm_model })),
        tasks: c.request.tasks.map((t, i) => ({ task_id: c.taskIds[i], index: i, description: t.description, priority: t.priority || 'normal', dependencies: t.dependencies || [] })) });
    }
    if ((m = /^\/api\/v1\/crews\/([0-9a-f-]{36})\/cancel$/.exec(bare)) && method === 'POST') {
      const c = this.crews.get(m[1]);
      if (!c) return this.answer(404, {});
      if (c.status === 'completed') return this.answer(409, {});
      c.status = 'cancelled';
      return this.answer(200, { crew_id: c.id, status: 'cancelled' });
    }
    if ((m = /^\/api\/v1\/crews\/([0-9a-f-]{36})$/.exec(bare))) {
      const c = this.crews.get(m[1]);
      if (!c) return this.answer(404, {});
      return this.answer(200, { crew_id: c.id, status: c.status, results: c.results, usage: c.usage, engine_mode: 'live',
        submitted_at: c.times.submitted, started_at: c.times.started || undefined, finished_at: c.times.finished || undefined, process: c.request.process });
    }
    return this.answer(404, { error: 'no route ' + method + ' ' + bare });
  }
  accepted(c) { return { crew_id: c.id, status: c.status, name: c.request.name, engine_mode: 'live', unforwarded: [], task_ids: c.taskIds, submitted_at: c.times.submitted, scope: '_' }; }
  publish(c, type, data, dt = 100) { c.t += dt; c.events.push({ seq: c.events.length + 1, at_ms: c.t, type, data }); }
  /** Run crew `c` to the end: every task answered by the "LLM", metered, and (optionally) priced. */
  finish(c, { price = 1500, reverse = false } = {}) {
    c.status = 'running';
    c.times.started = c.times.submitted + 50;
    this.publish(c, 'crew_started', { name: c.request.name, task_count: c.taskIds.length });
    let tok = 0, cost = 0;
    const order = c.taskIds.map((tid, i) => [tid, i]);
    if (reverse) order.reverse(); // the engine runs ready tasks in its own order — not the plan's
    order.forEach(([tid, i]) => {
      this.publish(c, 'task_started', { task_id: tid, description: c.request.tasks[i].description, agent: c.request.agents[0].key });
      this.publish(c, 'token', { task_id: tid, token: 'answer ' + i, complete: true });
      this.publish(c, 'task_completed', { task_id: tid, status: 'completed' });
      const usage = { model: 'gpt-x', provider: 'openai', prompt_tokens: 100, completion_tokens: 20 + i, total_tokens: 120 + i, duration_ms: 400 };
      if (price != null) usage.cost_micro_usd = price;
      tok += usage.total_tokens; cost += price || 0;
      c.results.push({ task_id: tid, status: 'completed', output: 'answer ' + i, usage });
    });
    this.publish(c, 'crew_completed', { status: 'completed', task_count: c.taskIds.length, wall_ms: 4321 });
    c.usage = { prompt_tokens: 100 * c.taskIds.length, completion_tokens: 0, total_tokens: tok, metered_tasks: c.taskIds.length, costed_tasks: price != null ? c.taskIds.length : 0 };
    if (price != null) c.usage.cost_micro_usd = cost;
    c.status = 'completed';
    c.times.finished = c.times.started + 9000;
  }
}

/** A Host for the page, wired to `fake` — the interface SwarmLibrary and LiveCrewSource use. */
function hostFor(fake, { role = null, features = ['query', 'revisions', 'idempotency'] } = {}) {
  const listeners = new Set();
  return {
    mode: 'connected',
    info: { plugin: { id: 'swarm' }, permissions: ['storage', 'presets:read', 'crews:read', 'crews:write'], features, user: { auth: role ? 'required' : 'off', signedIn: !!role, role } },
    can(p) { return this.info.permissions.includes(p); },
    has(f) { return this.info.features.includes(f); },
    role() { return this.info.user.auth === 'required' ? this.info.user.role : null; },
    pluginId: () => 'swarm',
    onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    changed() { for (const fn of listeners) fn(this); },
    request: (m, p, b, o) => fake.request(m, p, b, o),
  };
}

/** Run a LiveCrewSource fast, collecting what it emits, until it finishes (or `ms` passes). */
async function drive(src, { ms = 3000, during = null } = {}) {
  const events = [];
  src.subscribe((e) => events.push(e));
  Object.assign(src, { firstPollMs: 1, pollMs: 2, hiddenPollMs: 2, retryMs: 1 });
  let summary = null;
  const done = new Promise((resolve) => { src.onFinished = (st, sum) => { summary = sum; resolve(); }; });
  src.start();
  if (during) await during();
  await Promise.race([done, tick(ms)]);
  return { events, summary };
}

/* ------------------------------------------------------------------ specs and requests */

test('a spec survives the round trip through the store and keeps its runs capped by kind', () => {
  const s = S.defaultSpec('custom', 1);
  for (let i = 0; i < 30; i++) s.runs.push({ kind: 'sim', at: i, status: 'complete', seed: i, cost: 1, done: 1, failed: 0, total: 1 });
  for (let i = 0; i < 30; i++) s.runs.push({ kind: 'live', at: 100 + i, status: 'completed', crew: uuid(i), engine: 'live' });
  const n = S.normalizeSpec(JSON.parse(JSON.stringify(s)));
  assert.equal(n.runs.filter((r) => r.kind === 'live').length, S.SPEC_MAX_LIVE_RUNS, 'the newest live runs are kept');
  assert.equal(n.runs.filter((r) => r.kind === 'sim').length, S.SPEC_MAX_SIM_RUNS, 'simulations are capped apart — they never push out a crew');
  assert.equal(n.runs.at(-1).crew, uuid(29), 'newest last');
});

test('a document from a newer Swarm Command is read-only, and on-screen flags never reach the store', () => {
  const s = S.defaultSpec('custom', 1);
  const n = S.normalizeSpec(Object.assign(JSON.parse(JSON.stringify(s)), { v: S.SPEC_VERSION + 1 }));
  assert.equal(n.readOnly, true);
  assert.equal('readOnly' in S.storableSpec(n), false);
});

test('a run record may exist before its crew does: an idempotency key, no crew id yet', () => {
  const s = S.defaultSpec('custom', 1);
  s.runs = [{ kind: 'live', at: 1, status: 'submitting', key: 'sw-abc-123456789012' }, { kind: 'live', at: 2, status: 'x' /* no key, no crew */ }];
  const n = S.normalizeSpec(JSON.parse(JSON.stringify(s)));
  assert.equal(n.runs.length, 1);
  assert.equal(n.runs[0].key, 'sw-abc-123456789012');
});

test('fitSpec trims what can be spared — simulations first, then the estimate — before refusing', () => {
  const s = S.defaultSpec('custom', 1);
  // A spec of tasks just under the limit, pushed over it by its run records and estimate.
  let i = 0;
  while (S.specBytes(s) < S.SPEC_MAX_BYTES - 1200) s.tasks.push(Object.assign({}, s.tasks[0], { key: 'k' + i++, title: 'Padding task ' + i, deps: [] }));
  for (let j = 0; j < 10; j++) s.runs.push({ kind: 'sim', at: j, status: 'complete', seed: j, cost: 1.2345, durationMs: 123456, done: 10, failed: 0, total: 10 });
  s.runs.push({ kind: 'live', at: 99, status: 'completed', crew: uuid(1), engine: 'live', done: 3, failed: 0, total: 3 });
  s.estimate = { sig: 'abcdefgh', at: 1, runs: 8, cost: { min: 1, p50: 2, max: 3 }, durationMs: { p50: 1, max: 2 }, tokens: { p50: 1 }, peak: { p50: 1 }, failed: 0, over: 0, stalled: 0 };
  assert.ok(S.specBytes(S.storableSpec(s)) > S.SPEC_MAX_BYTES, 'over the limit to begin with');
  S.fitSpec(s);
  assert.ok(S.specBytes(S.storableSpec(s)) <= S.SPEC_MAX_BYTES, 'it fits');
  assert.equal(s.runs.filter((r) => r.kind === 'live').length, 1, 'the live crew is kept — it is the record of real work');
  assert.ok(s.runs.filter((r) => r.kind === 'sim').length < 10, 'simulations went first');
});

test('specToCrewRequest numbers tasks in topological order, and the plan keeps their keys', () => {
  const s = S.defaultSpec('custom', 1);
  const { request, plan } = S.specToCrewRequest(s, null);
  assert.equal(request.tasks.length, plan.tasks.length);
  plan.tasks.forEach((t, i) => assert.equal(request.tasks[i].description, t.description, 'the plan and the request agree position by position'));
  assert.equal(request.process, 'dag', 'auto is a DAG when tasks depend on each other');
});

test('taskTitle strips the mission prefix the plugin adds; planFromServer keeps a swarm\'s own titles', () => {
  assert.equal(S.taskTitle('Mission: do it\nTask: Plan the work', 0), 'Plan the work');
  assert.equal(S.taskTitle('A task from somewhere else', 3), 'A task from somewhere else');
  const s = S.defaultSpec('custom', 1);
  const built = S.specToCrewRequest(s, null);
  const server = { process: 'dag', agents: [{ key: 'planner', name: 'Planner', role: 'Planner' }],
    tasks: built.request.tasks.map((t, i) => ({ task_id: uuid(i), description: t.description, dependencies: t.dependencies || [] })) };
  const mine = S.planFromServer(server, built);
  assert.equal(mine.tasks[0].title, built.plan.tasks[0].title, 'the same tasks: the swarm\'s own titles');
  assert.equal(mine.tasks[0].engineId, uuid(0), 'bound to the engine\'s ids');
  const other = S.planFromServer(Object.assign({}, server, { tasks: server.tasks.slice(1) }), built);
  assert.equal(other.tasks[0].key, 't0', 'different tasks: the crew\'s own');
});

/* ------------------------------------------------------------------ the simulator */

/** Run spec `s` headless on `seed` and return what the orchestrator reported at the end. */
function simulate(s, seed) {
  const { sc, cfg } = S.compileSpec(s);
  const sim = new S.Sim(sc, { seed, scale: s.scale, cfg });
  const src = new S.MockSource(sim);
  let summary = null;
  src.subscribe((e) => { if (e.type === 'agent.completed' && e.agentId === 'orch' && e.payload.summary) summary = e.payload.summary; });
  src.runToEnd();
  return summary;
}

test('the simulator is deterministic: one seed, one outcome — so a run can be replayed and compared', () => {
  for (const tpl of ['custom', 'research']) {
    const s = S.defaultSpec(tpl, 1);
    const a = simulate(s, 4242), b = simulate(s, 4242);
    assert.ok(a, tpl + ' finishes');
    assert.equal(a.cost, b.cost, tpl + ': the same cost');
    assert.equal(a.durationMs, b.durationMs, tpl + ': the same duration');
    assert.equal(a.tasksDone, b.tasksDone, tpl + ': the same tasks done');
  }
});

test('an estimate prices a swarm over several seeds, and is tied to the settings it priced', async () => {
  const s = S.defaultSpec('custom', 1);
  const est = await S.estimateSpec(s, { runs: 4 });
  assert.equal(est.runs, 4);
  assert.ok(est.cost.min <= est.cost.p50 && est.cost.p50 <= est.cost.max, 'p50 lies inside the range');
  assert.ok(est.cost.max > 0, 'and something costs money');
  assert.equal(est.sig, S.specSig(s), 'it is marked with the settings it priced');
  const changed = Object.assign({}, s, { budget: s.budget * 2, policy: Object.assign({}, s.policy, { crash: 0.5 }) });
  assert.notEqual(S.specSig(changed), est.sig, 'so a change to them makes it stale');
});

/* ------------------------------------------------------------------ the library */

test('the library reads revisions and writes with them', async () => {
  const fake = new FakeAgnostic();
  const lib = new S.SwarmLibrary(hostFor(fake));
  const s = S.defaultSpec('custom', 1);
  const created = await lib.save(s, { isNew: true });
  assert.equal(created.ok, true);
  assert.equal(fake.calls.at(-1).opts.ifNoneMatch, '*', 'a new swarm is created only if absent');
  const again = await lib.save(Object.assign({}, created.spec, { name: 'Renamed' }));
  assert.equal(again.ok, true);
  assert.match(fake.calls.at(-1).opts.ifMatch, /^"[0-9a-f]{16}"$/, 'a replace names the revision it was made from');
  const lib2 = new S.SwarmLibrary(hostFor(fake));
  await lib2.load();
  assert.equal(lib2.get(s.id).name, 'Renamed', 'and another reader sees it');
  assert.ok(lib2.etags.get(s.id), 'with its revision');
});

test('⭐ two tabs: a save from a stale copy is a conflict, never a silent overwrite', async () => {
  const fake = new FakeAgnostic();
  const a = new S.SwarmLibrary(hostFor(fake)), b = new S.SwarmLibrary(hostFor(fake));
  const s = S.defaultSpec('custom', 1);
  await a.save(s, { isNew: true });
  await b.load();
  const first = await a.save(Object.assign(S.normalizeSpec(JSON.parse(fake.docs.get('swarm-' + s.id))), { id: s.id, name: 'Tab A' }));
  assert.equal(first.ok, true);
  const second = await b.save(Object.assign({}, b.get(s.id), { name: 'Tab B' }));
  assert.equal(second.ok, false);
  assert.equal(second.conflict, true, 'tab B is told, not ignored');
  assert.equal(JSON.parse(fake.docs.get('swarm-' + s.id)).name, 'Tab A', 'and tab A\'s save stands');
  const forced = await b.save(Object.assign({}, b.get(s.id), { name: 'Tab B' }), { force: true });
  assert.equal(forced.ok, true, 'overwriting is a choice the user makes');
});

test('⭐ a background record is applied to the LATEST copy: a run recorded while someone else edits loses neither', async () => {
  const fake = new FakeAgnostic();
  const editor = new S.SwarmLibrary(hostFor(fake)), recorder = new S.SwarmLibrary(hostFor(fake));
  const s = S.defaultSpec('custom', 1);
  await editor.save(s, { isNew: true });
  await recorder.load();
  await editor.save(Object.assign({}, editor.get(s.id), { name: 'Edited elsewhere' }));
  const saved = await recorder.patch(s.id, (x) => { x.runs.push({ kind: 'live', at: 5, status: 'running', crew: uuid(7) }); }, { touch: false });
  assert.ok(saved, 'the patch lands after re-reading');
  const stored = JSON.parse(fake.docs.get('swarm-' + s.id));
  assert.equal(stored.name, 'Edited elsewhere', 'the other edit survives');
  assert.equal(stored.runs.length, 1, 'and so does the run');
  assert.ok(fake.calls.some((c) => c.method === 'PUT' && c.opts.ifMatch), 'every write was conditional');
});

test('patches to one swarm queue: two at once both land', async () => {
  const fake = new FakeAgnostic();
  const lib = new S.SwarmLibrary(hostFor(fake));
  const s = S.defaultSpec('custom', 1);
  await lib.save(s, { isNew: true });
  await Promise.all([
    lib.patch(s.id, (x) => { x.runs.push({ kind: 'live', at: 1, status: 'running', crew: uuid(1) }); }, { touch: false }),
    lib.patch(s.id, (x) => { x.runs.push({ kind: 'live', at: 2, status: 'running', crew: uuid(2) }); }, { touch: false }),
  ]);
  assert.equal(JSON.parse(fake.docs.get('swarm-' + s.id)).runs.length, 2);
});

test('a viewer may look but not write; a background record stays on screen only', async () => {
  const fake = new FakeAgnostic();
  const s = S.defaultSpec('custom', 1);
  fake.docs.set('swarm-' + s.id, JSON.stringify(s));
  const lib = new S.SwarmLibrary(hostFor(fake, { role: 'viewer' }));
  await lib.load();
  const r = await lib.save(lib.get(s.id));
  assert.equal(r.ok, false);
  assert.match(r.message, /viewer/);
  const puts = fake.calls.filter((c) => c.method === 'PUT').length;
  await lib.patch(s.id, (x) => { x.estimate = null; x.name = 'local only'; });
  assert.equal(fake.calls.filter((c) => c.method === 'PUT').length, puts, 'nothing was sent');
  assert.equal(lib.get(s.id).name, 'local only', 'but the change shows for this session');
});

/* ------------------------------------------------------------------ live crews */

function liveRun(fake, spec, opts = {}) {
  const built = S.specToCrewRequest(spec, null);
  return new S.LiveCrewSource(hostFor(fake, opts.host), spec, built, { idempotencyKey: 'sw-test-' + Math.random().toString(36).slice(2, 12), ...opts.src });
}

test('⭐ a live run: submitted once, read by cursor, bound by task id, and ended with what agnostic metered', async () => {
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  const src = liveRun(fake, spec);
  const { summary } = await drive(src, { during: async () => {
    await tick(10);
    fake.finish([...fake.crews.values()][0]);
  } });
  assert.ok(summary, 'the crew finished');
  assert.equal(summary.status, 'completed');
  assert.equal(fake.crews.size, 1, 'one crew');
  const n = spec.tasks.length;
  assert.equal(summary.tasksDone, n, 'every task bound and done');
  assert.equal(summary.tokensActual, true, '⭐ the token count is what agnostic metered');
  assert.equal(summary.tokens, [...Array(n).keys()].reduce((t, i) => t + 120 + i, 0), 'to the token');
  assert.equal(summary.costMicro, 1500 * n, '⭐ and the cost is the gateway\'s, not a simulation\'s');
  assert.equal(summary.durationMs, 9000, 'the duration is the crew\'s own, from its started and finished times');
  assert.equal(summary.results[0].output, 'answer 0', 'outputs come back');
  const cursors = fake.calls.filter((c) => c.path.includes('/events?after=')).map((c) => Number(c.path.split('after=')[1]));
  assert.ok(cursors.length >= 1);
  for (let i = 1; i < cursors.length; i++) assert.ok(cursors[i] >= cursors[i - 1], 'the cursor only moves forward');
  assert.equal(new Set(fake.calls.filter((c) => c.method === 'POST').map((c) => c.opts.idempotencyKey)).size, 1, 'submitted with one key');
});

test('⭐ tasks that share a title, run in another order: each still gets ITS output — bound by id, never by text', async () => {
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  for (const t of spec.tasks) { t.title = 'Same title'; t.deps = []; }
  const src = liveRun(fake, spec);
  const { summary } = await drive(src, { during: async () => { await tick(10); fake.finish([...fake.crews.values()][0], { reverse: true }); } });
  assert.equal(summary.tasksDone, spec.tasks.length);
  summary.results.forEach((r, i) => assert.equal(r.output, 'answer ' + i, 'task ' + i + ' got its own output, not another identical task\'s'));
});

test('a gateway that reports no cost leaves it n/a — never zero, never simulated', async () => {
  const fake = new FakeAgnostic();
  const src = liveRun(fake, S.defaultSpec('custom', 1));
  const { summary } = await drive(src, { during: async () => { await tick(10); fake.finish([...fake.crews.values()][0], { price: null }); } });
  assert.equal(summary.costMicro, null);
  assert.equal(summary.tokensActual, true, 'its tokens are still metered');
});

test('⭐ no answer to the submission: retried with the SAME key, and one crew results', async () => {
  const fake = new FakeAgnostic();
  fake.inject = [0, 0]; // the first two POSTs never reach the server
  const src = liveRun(fake, S.defaultSpec('custom', 1));
  const { summary } = await drive(src, { during: async () => {
    while (!fake.crews.size) await tick(2);
    fake.finish([...fake.crews.values()][0]);
  } });
  const posts = fake.calls.filter((c) => c.method === 'POST' && c.path === '/api/v1/crews');
  assert.equal(posts.length, 3, 'two lost, the third answered');
  assert.equal(new Set(posts.map((c) => c.opts.idempotencyKey)).size, 1, 'all with one key — safe to repeat');
  assert.equal(fake.crews.size, 1);
  assert.equal(summary.status, 'completed');
});

test('never an answer at all: the run is unconfirmed — not refused, not lost', async () => {
  const fake = new FakeAgnostic();
  fake.inject = [0, 0, 0, 0, 0];
  let submitted = null;
  const src = liveRun(fake, S.defaultSpec('custom', 1), { src: { onSubmitted: (id, mode, st) => { submitted = st; } } });
  const { summary } = await drive(src);
  assert.equal(summary.status, 'unconfirmed');
  assert.equal(submitted, 'unconfirmed');
});

test('⭐ losing contact pauses the watch, and a sign-in resumes it — no permanent "lost"', async () => {
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  const host = hostFor(fake);
  const src = new S.LiveCrewSource(host, spec, S.specToCrewRequest(spec, null), { idempotencyKey: 'sw-pause-12345678' });
  const { summary } = await drive(src, { during: async () => {
    while (!fake.crews.size) await tick(2);
    await tick(5);
    fake.inject = [401];               // the next poll: signed out
    await tick(20);
    assert.ok(src.waiting, 'paused, waiting for a sign-in');
    assert.equal(src.finished, false, 'and not finished');
    fake.finish([...fake.crews.values()][0]);
    host.changed();                    // the shell re-sent init
  } });
  assert.equal(summary.status, 'completed', 'it caught up and finished normally');
});

test('watching a crew this page did not submit: bound through its plan', async () => {
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  const built = S.specToCrewRequest(spec, null);
  const accepted = (await fake.request('POST', '/api/v1/crews', built.request, {})).data;
  fake.finish(fake.crews.get(accepted.crew_id));
  const src = new S.LiveCrewSource(hostFor(fake), spec, built, { crewId: accepted.crew_id });
  const { summary } = await drive(src);
  assert.equal(summary.status, 'completed');
  assert.equal(summary.tasksDone, spec.tasks.length);
  assert.ok(fake.calls.some((c) => c.path.endsWith('/plan')), 'it asked for the plan');
  assert.equal(summary.results[0].title, built.plan.tasks[0].title, 'and, the tasks being the swarm\'s own, kept their titles');
});

test('a crew from before the last restart — no plan, no events — is shown from its outcome', async () => {
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  const built = S.specToCrewRequest(spec, null);
  const accepted = (await fake.request('POST', '/api/v1/crews', built.request, {})).data;
  const c = fake.crews.get(accepted.crew_id);
  fake.finish(c);
  c.noPlan = true;
  c.events = [];
  const src = new S.LiveCrewSource(hostFor(fake), spec, built, { crewId: accepted.crew_id });
  const { summary } = await drive(src);
  assert.equal(summary.status, 'completed');
  assert.equal(summary.tasksDone, spec.tasks.length, 'a task per result');
  assert.equal(summary.tokensActual, true);
});

test('a parallel crew shows no more tasks at work than its concurrency limit', async () => {
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  spec.live.process = 'parallel';
  spec.live.maxConcurrency = 2;
  const src = liveRun(fake, spec);
  let peakActive = 0;
  const { summary } = await drive(src, { during: async () => {
    while (!fake.crews.size) await tick(2);
    const c = [...fake.crews.values()][0];
    c.status = 'running';
    fake.publish(c, 'crew_started', { task_count: c.taskIds.length });
    c.taskIds.forEach((tid, i) => fake.publish(c, 'task_started', { task_id: tid, description: c.request.tasks[i].description, agent: c.request.agents[0].key }, 1));
    await tick(30);
    peakActive = src.activeCount();
    c.events = c.events.slice(); // keep what was published
    fake.finish(Object.assign(c, { events: c.events }));
  } });
  assert.equal(peakActive, 2, 'two at work, the rest queued');
  assert.equal(summary.status, 'completed');
});
