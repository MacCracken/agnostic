// Swarm Command's logic (src/webgui/plugins/swarm/index.html), run in Node against a fake agnostic.
//
// The fake implements what the plugin reaches through the bridge, the way 0.1.13's server answers
// it: plugin documents with revisions (ETag / If-Match / If-None-Match, 412), crews with numbered
// and timed events (`?after=` cursor, `missed` past the window), the plan route, outcomes with
// metered usage, a crew a restart left `interrupted`, and Idempotency-Key replays. The simulator,
// the spec normalizer and the crew builder run unchanged.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadPage, tick } from './harness.mjs';

const page = loadPage('src/webgui/plugins/swarm/index.html');
const S = page.get(`({ defaultSpec, normalizeSpec, specToCrewRequest, validateSpec, compileSpec, specBytes, storableSpec,
  capRuns, fitSpec, planFromServer, taskTitle, SwarmLibrary, LiveCrewSource, Sim, MockSource, estimateSpec, specSig,
  soloRun, soloLine, soloBox, quantile, SOLO, SOLO_NOTE, escapeHtml, Launcher, Editor, SPEC_MAX_BYTES, SPEC_RESERVE, SPEC_MAX_LIVE_RUNS, SPEC_MAX_SIM_RUNS, SPEC_VERSION })`);

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
      // `gone`: the server restarted, so its ledger — events and plan — no longer holds the crew.
      if (!c || c.gone) return this.answer(404, {});
      const after = Number(q.get('after') || 0);
      // `oldest`: the oldest seq the server's window still holds (absent: 1). A cursor older than it
      // gets everything still held and `missed`, the numbers after it the ring overwrote (H3).
      const oldest = c.oldest || 1;
      const events = c.events.filter((e) => e.seq > Math.max(after, oldest - 1));
      const next = c.events.length ? c.events[c.events.length - 1].seq : after;
      return this.answer(200, { crew_id: c.id, status: c.status, events, next: Math.max(next, after),
        missed: Math.max(0, oldest - (after + 1)), lost_events: 0, dropped_events: oldest - 1 });
    }
    if ((m = /^\/api\/v1\/crews\/([0-9a-f-]{36})\/plan$/.exec(bare))) {
      const c = this.crews.get(m[1]);
      if (!c || c.noPlan || c.gone) return this.answer(404, { error: 'not held' });
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
        submitted_at: c.times.submitted, started_at: c.times.started || undefined, finished_at: c.times.finished || undefined, process: c.request.process,
        tasks_submitted: c.taskIds.length, interrupted_at: c.times.interrupted || undefined, error: c.error || undefined });
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
  // A source that never finished is stopped, so its poll timer cannot keep Node alive and turn
  // a failing test into a hung run.
  if (!summary) src.stop();
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

test('a live swarm asks for each task\'s role, so the engine picks that role\'s agent (agnostic 0.1.15)', () => {
  const s = S.defaultSpec('custom', 1);
  const { request } = S.specToCrewRequest(s, null);
  assert.ok(request.agents.length > 1, 'precondition: more than one role');
  for (const a of request.agents) {
    assert.equal(a.domain, a.key, 'each role agent says what it is: its domain is its role');
    assert.ok(Array.isArray(a.tools) && a.tools.length, 'and what it can do: the tool kinds its role uses');
    for (const t of a.tools) assert.ok(s.roles[a.key].tools[t] > 0 && s.tools[t].on, 'only kinds it is given weight for, switched on');
  }
  const byKey = new Map(request.agents.map((a) => [a.key, a]));
  const { plan } = S.specToCrewRequest(s, null);
  request.tasks.forEach((t, i) => {
    const role = plan.tasks[i].role;
    assert.equal(t.domain, role, 'each task asks for its role');
    assert.deepEqual([...t.required_tools], [...byKey.get(role).tools], 'and for what that role uses');
  });
  const planner = byKey.get('planner');
  if (planner) assert.deepEqual([...planner.tools], ['llm', 'db', 'fs'], 'most-used first, ties in the catalogue order');

  // A tool kind switched off is not named; a role with no kind left asks for none.
  const off = S.defaultSpec('custom', 1);
  for (const k of ['llm', 'search', 'exec', 'db', 'fs']) off.tools[k].on = false;
  const o = S.specToCrewRequest(off, null).request;
  assert.ok(o.agents.every((a) => !('tools' in a)), 'no tools on, no tools named');
  assert.ok(o.tasks.every((t) => !('required_tools' in t) && typeof t.domain === 'string'), 'the domain still travels');

  // A preset roster carries its own domains, which no swarm role names: no hints.
  const p = S.defaultSpec('custom', 1);
  p.live.roster = 'preset';
  const preset = { agents: [{ agent_key: 'perf', role: 'Performance tester', goal: 'Load it', domain: 'performance' }] };
  const pr = S.specToCrewRequest(p, preset).request;
  assert.equal(pr.agents[0].domain, 'performance', 'a preset agent keeps its own domain');
  assert.ok(pr.tasks.every((t) => !('domain' in t) && !('required_tools' in t)), 'and its tasks ask for nothing');
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

/* ------------------------------------------------------------------ the one-agent baseline (ADR 0014) */

/** Run spec `s` headless on `seed` exactly as estimateSpec does, and take one run's row as it does. */
function headless(s, seed) {
  const { sc, cfg } = S.compileSpec(s);
  const sim = new S.Sim(sc, { seed, scale: s.scale, cfg });
  sim.headless = true;
  let sum = null;
  sim.out = (e) => { if (e.type === 'agent.completed' && e.agentId === 'orch') sum = e.payload.summary; };
  sim.start();
  while (!sim.done && sim.t < 6 * 3600 * 1000) sim.step();
  return sum ? { cost: sum.cost, ms: sum.durationMs, tokens: sum.tokens, peak: sum.peak, failed: sum.tasksFailed, stalled: sim.stalled }
    : { cost: sim.totals.cost, ms: sim.t, tokens: sim.totals.tokens, peak: sim.stats.peak, failed: sim.stats.tasksFailed, stalled: true };
}
/** A value from the page's realm as a plain one of this realm (deepEqual compares prototypes). */
const plain = (x) => JSON.parse(JSON.stringify(x));
const solo = (s, seed, budget) => S.soloRun(S.compileSpec(s), { seed, scale: s.scale, budget });
const settled = (r) => r.done + r.failed + r.unreached;

test('the one-agent baseline is deterministic: one seed and one budget, one outcome', () => {
  for (const tpl of ['custom', 'research']) {
    const s = S.defaultSpec(tpl, 1);
    const a = solo(s, 4242, 1e12);
    assert.deepEqual(a, solo(s, 4242, 1e12), tpl + ': the same seed, the same run');
    assert.ok(a.done > 0 && a.tokens > 0 && a.cost > 0 && a.ms > 0, tpl + ': and it works');
    assert.notDeepEqual(a, solo(s, 4243, 1e12), tpl + ': another seed, another run');
  }
});

test('every number the baseline restates is still the Sim\'s: change one there, and this names the SOLO entry to change', () => {
  const src = (m) => S.Sim.prototype[m].toString(), O = S.SOLO;
  // [the Sim method, the text it must still hold, the SOLO entry that restates it]
  const mirrored = [
    ['work', 'this.rng.range(' + O.workMs[0] + ', ' + O.workMs[1] + ')', 'workMs'],
    ['work', 'this.policy.crash * task.difficulty * (dur / ' + O.crashPerMs + ')', 'crashPerMs'],
    ['work', 'this.rng.range(' + O.crashAt[0] + ', ' + O.crashAt[1] + ') * dur', 'crashAt'],
    ['travelMs', O.far.ms + ' + this.latency(fromTerr, toTerr) * ' + O.far.perLatency + ' + this.rng.range(0, ' + O.far.jitter + ')', 'far'],
    ['travelMs', 'return ' + O.near.ms + ' + this.rng.range(0, ' + O.near.jitter + ')', 'near'],
    ['travelMs', 'return ' + O.here.ms + ' + this.rng.range(0, ' + O.here.jitter + ')', 'here'],
    ['latency', '|| ' + O.latencyMs + ')', 'latencyMs'],
    ['tickAgent', "case 'moving': f = " + O.compute.moving + ';', 'compute.moving'],
    ['tickAgent', '(C.models[a.model] ? C.models[a.model].tps : 1); f = ' + O.compute.working + ';', 'compute.working'],
    ['tickAgent', "case 'tool': f = " + O.compute.tool + ';', 'compute.tool'],
    ['tickAgent', 'let tps = 0, f = ' + O.compute.other + ';', 'compute.other'],
    ['callTool', "tool.kind === 'llm' ? " + O.localLlm + ' : 1', 'localLlm'],
    ['callTool', 'this.rng.range(' + O.slow[0] + ', ' + O.slow[1] + ')', 'slow'],
    ['toolReturn', 'task.own + ' + O.toolGain + ' * this.terr.get(a.territory).speed', 'toolGain'],
    ['toolReturn', '(c.slow ? ' + O.slowErr + ' : 1)', 'slowErr'],
    ['hurt', 'this.rng.int(' + O.damage[0] + ', ' + O.damage[1] + ')', 'damage'],
    ['hurt', 'this.rng.range(' + O.errorMs[0] + ', ' + O.errorMs[1] + ')', 'errorMs'],
    ['spawnAgent', 'cost: 0, health: ' + O.health + ', errors: 0', 'health'],
    ['spawnAgent', 'phaseEnd: this.t + ' + O.spawnMs + ',', 'spawnMs'],
    ['scheduleRetry', 'at: this.t + ' + O.retryMs + ',', 'retryMs'],
    ['scheduleRetry', 'task.difficulty > ' + O.keep.hardOver + ' ? ' + O.keep.hard + ' : ' + O.keep.soft, 'keep'],
    ['workCap', 'task.work * ' + O.leadShare, 'leadShare'],
    ['requestRework', 'task.own = task.work * ' + O.reworkFrom + ';', 'reworkFrom'],
  ];
  for (const [m, text, entry] of mirrored) {
    assert.ok(src(m).includes(text), 'Sim.' + m + ' no longer has `' + text + '`: change SOLO.' + entry + ' with it, and soloRun if the step itself changed');
  }
  const checked = new Set(mirrored.map(([, , entry]) => entry.split('.')[0]));
  assert.deepEqual(Object.keys(O).filter((k) => !checked.has(k)), ['maxSteps'], 'every entry is checked against the Sim, but the guard that is not the Sim\'s');
});

test('the baseline works the swarm\'s own plan on that seed', () => {
  // refactor's fan-out counts are drawn from the seed: 49 parts on 1337, 52 on 99991.
  const counts = new Set();
  for (const tpl of ['refactor', 'custom']) {
    const s = S.defaultSpec(tpl, 1);
    for (const seed of [1337, 99991]) {
      s.seed = seed;
      const v = S.validateSpec(s), so = solo(s, seed, 1e12);
      assert.equal(so.total - so.fixes, v.taskCount + v.fanout, tpl + ' on ' + seed + ': every task and part of the swarm\'s plan');
      assert.equal(settled(so), so.total, tpl + ' on ' + seed + ': each one done, failed or left');
      if (tpl === 'refactor') counts.add(so.total - so.fixes);
    }
  }
  assert.equal(counts.size, 2, 'and the plan follows the seed');
});

test('the baseline never spends more than its budget, and what it leaves undone is counted', () => {
  const s = S.defaultSpec('research', 1);
  const h = headless(s, s.seed);
  const paired = solo(s, s.seed, h.tokens);
  assert.ok(paired.tokens <= h.tokens, 'the swarm\'s own tokens bound it');
  assert.equal(settled(paired), paired.total);

  const small = solo(s, s.seed, 2000);
  assert.equal(small.out, true, 'it ran out');
  assert.ok(small.tokens <= 2000, 'at the budget, not past it');
  assert.ok(small.unreached > 0 && small.done < small.total, 'and what it never reached is counted');
  assert.equal(settled(small), small.total);

  const none = solo(s, s.seed, 0);
  assert.equal(none.done, 0);
  assert.equal(none.unreached, none.total, 'no tokens, nothing done');
  assert.equal(none.tokens, 0);

  const safe = S.defaultSpec('research', 1);
  safe.policy = Object.assign({}, safe.policy, { crash: 0, toolErr: 0 });
  const all = solo(safe, s.seed, 1e12);
  assert.equal(all.out, false);
  assert.equal(all.failed, 0);
  assert.equal(all.unreached, 0);
  assert.equal(all.done, all.total, 'with tokens to spare and nothing failing, everything is done');

  for (const k of Object.keys(safe.tools)) safe.tools[k].on = false;
  const quiet = solo(safe, s.seed, 1e12);
  assert.equal(quiet.done, quiet.total, 'every tool off: it only thinks, and still finishes');
  assert.ok(quiet.tokens > 0);

  // One long task, no tools, nothing failing, 100 tokens: the one work step it starts is cut where
  // they run out — so all its time is spawning, one walk to the task, and those 100 tokens' work.
  const one = S.defaultSpec('custom', 1);
  one.tasks = [Object.assign({}, one.tasks[0], { work: 600, deps: [], fanout: null, rework: null })];
  for (const k of Object.keys(one.tools)) one.tools[k].on = false;
  one.policy = Object.assign({}, one.policy, { crash: 0, toolErr: 0 });
  const tps = one.roles.planner.tps * one.models[one.roles.planner.model].tps;
  const cut = solo(one, 1, 100);
  assert.equal(cut.tokens, 100);
  assert.equal(cut.unreached, 1);
  const walk = cut.ms - S.SOLO.spawnMs - (100 / tps) * 1000;
  assert.ok(walk >= 1100 && walk <= 1800, 'the step stopped where the tokens ran out (' + walk + ' ms left for the walk)');

  // Out of tokens is the whole budget spent: a tool result larger than what is left is read up to the
  // budget, for its share of the work — the run does not stop early with tokens to spare.
  const heavy = S.defaultSpec('research', 1);
  for (const k of Object.keys(heavy.tools)) heavy.tools[k].tokens = [900000, 1000000];
  for (const seed of [1, 2, 3, 4, 5]) {
    const run = solo(heavy, seed, 1500000);
    assert.equal(run.out, true);
    assert.equal(run.tokens, 1500000, 'seed ' + seed + ': out of tokens, at the budget');
    assert.equal(settled(run), run.total);
  }

  // A fan-out lead that fails before its split never makes its parts: one task failed, as the Sim
  // counts it — the Sim creates the parts at the split, and a failed task fails only those that exist.
  const fragile = S.defaultSpec('custom', 1);
  // Its first work step crashes for certain (crash × difficulty ≥ 1), long before the work is done.
  fragile.tasks = [Object.assign({}, fragile.tasks[1], { deps: [], work: 600, difficulty: 100 })];
  for (const k of Object.keys(fragile.tools)) fragile.tools[k].on = false;
  fragile.policy = Object.assign({}, fragile.policy, { crash: 0.9, maxRetries: 0 });
  assert.ok(fragile.tasks[0].fanout.count > 0, 'a lead with parts to split into');
  const lost = solo(fragile, 1, 1e12);
  assert.equal(lost.failed, 1, 'the lead');
  assert.equal(lost.total, 1, 'and no part it never split into');
  assert.equal(lost.unreached, 0);
  assert.equal(lost.failed, headless(fragile, 1).failed, 'the swarm\'s own count of the same failure');
});

test('⭐ an estimate prices one agent at the swarm\'s own token spend, seed by seed — and the swarm\'s numbers are the simulations they always were', async () => {
  const s = S.defaultSpec('custom', 1);
  const est = await S.estimateSpec(s, { runs: 4 });
  const seeds = [0, 1, 2, 3].map((i) => ((s.seed - 1 + i * 7919) % 2147483647) + 1);
  const h = seeds.map((seed) => headless(s, seed));
  const col = (rows, k) => rows.map((r) => r[k]);
  const mean = (xs) => xs.reduce((a, b) => a + b, 0) / xs.length;

  // The swarm: recomputed from the Sim alone, run by run …
  assert.deepEqual(plain({ cost: est.cost, durationMs: est.durationMs, tokens: est.tokens, peak: est.peak, failed: est.failed, over: est.over, stalled: est.stalled }), {
    cost: { min: Math.min(...col(h, 'cost')), p50: S.quantile(col(h, 'cost'), 0.5), max: Math.max(...col(h, 'cost')) },
    durationMs: { p50: S.quantile(col(h, 'ms'), 0.5), max: Math.max(...col(h, 'ms')) },
    tokens: { p50: S.quantile(col(h, 'tokens'), 0.5) }, peak: { p50: S.quantile(col(h, 'peak'), 0.5) },
    failed: mean(col(h, 'failed')), over: h.filter((r) => r.cost > s.budget).length, stalled: h.filter((r) => r.stalled).length,
  }, 'the swarm\'s figures are the Sim\'s');
  // … and pinned to what Swarm Command 0.4 reported for this swarm, before the baseline existed.
  assert.deepEqual(plain({ cost: est.cost, durationMs: est.durationMs, tokens: est.tokens, peak: est.peak, failed: est.failed, over: est.over, stalled: est.stalled }), {
    cost: { min: 1.0729, p50: 1.3775499999999998, max: 1.6171 }, durationMs: { p50: 117425, max: 143800 }, tokens: { p50: 237476.5 }, peak: { p50: 11 },
    failed: 0, over: 0, stalled: 0,
  }, '⭐ bit for bit');

  // The baseline: on each seed, the tokens that seed's swarm spent.
  const so = seeds.map((seed, i) => solo(s, seed, h[i].tokens));
  const q = (xs) => S.quantile(xs, 0.5);
  assert.deepEqual(plain(est.solo), {
    tokens: { p50: q(col(so, 'tokens')) },
    cost: { min: Math.min(...col(so, 'cost')), p50: q(col(so, 'cost')), max: Math.max(...col(so, 'cost')) },
    durationMs: { p50: q(col(so, 'ms')), max: Math.max(...col(so, 'ms')) },
    ratio: {
      tokens: q(so.map((r, i) => r.tokens / Math.max(1, h[i].tokens))),
      cost: q(so.map((r, i) => (h[i].cost > 0 ? r.cost / h[i].cost : 0))),
      durationMs: q(so.map((r, i) => r.ms / Math.max(1, h[i].ms))),
    },
    failed: mean(col(so, 'failed')), unreached: mean(col(so, 'unreached')),
    out: so.filter((r) => r.out).length, stalled: so.filter((r) => r.stalled).length,
  }, 'paired seed by seed');
  assert.ok(est.solo.tokens.p50 <= est.tokens.p50, 'never more tokens than the swarm');
  assert.ok(est.solo.ratio.tokens <= 1);
  assert.ok(est.solo.durationMs.p50 > est.durationMs.p50, 'one agent, one task at a time: slower');
});

test('⭐ every template\'s estimate, at the estimator\'s eight runs, is the one Swarm Command 0.4 gave — bit for bit', async () => {
  // Read from Swarm Command 0.4.0's page (agnostic 0.1.12), before the baseline existed. One swarm
  // on four seeds can miss a change to the Sim (a millisecond more travel inside a region leaves
  // custom's four runs as they were); four swarms on eight seeds each, every estimate as the editor
  // makes it, do not.
  const pinned = {
    custom: { cost: { min: 1.0729, p50: 1.33365, max: 1.6171 }, durationMs: { p50: 116550, max: 143800 }, tokens: { p50: 231870 }, peak: { p50: 11 }, failed: 0, over: 0, stalled: 0 },
    refactor: { cost: { min: 5.4001, p50: 5.70225, max: 6.1647 }, durationMs: { p50: 155800, max: 180300 }, tokens: { p50: 1046788.5 }, peak: { p50: 54 }, failed: 0.75, over: 0, stalled: 0 },
    research: { cost: { min: 4.8017, p50: 5.22335, max: 5.667 }, durationMs: { p50: 134675, max: 159050 }, tokens: { p50: 772985.5 }, peak: { p50: 42 }, failed: 0.375, over: 0, stalled: 0 },
    incident: { cost: { min: 4.4848, p50: 4.8267500000000005, max: 5.1141 }, durationMs: { p50: 176675, max: 210300 }, tokens: { p50: 441284.5 }, peak: { p50: 36 }, failed: 0.25, over: 0, stalled: 0 },
  };
  for (const [tpl, want] of Object.entries(pinned)) {
    const est = await S.estimateSpec(S.defaultSpec(tpl, 1), { runs: 8 });
    assert.equal(est.runs, 8);
    assert.deepEqual(plain({ cost: est.cost, durationMs: est.durationMs, tokens: est.tokens, peak: est.peak, failed: est.failed, over: est.over, stalled: est.stalled }), want, tpl + ': bit for bit');
  }
});

test('⭐ every template\'s one-agent baseline, at the estimator\'s eight runs, is the one ADR 0014 reports — bit for bit', async () => {
  // The paired test above rebuilds `est.solo` from soloRun itself, so it cannot see soloRun's own
  // arithmetic. These can: a token left unpriced, the compute multiplier or a region's speed dropped
  // from a step, and a template's cost, time or tokens move. Read from Swarm Command 0.5.0's page.
  const pinned = {
    custom: { tokens: { p50: 201910.0136392052 }, cost: { min: 0.7574406925856846, p50: 0.9604344971572207, max: 1.4252194977306576 },
      durationMs: { p50: 302418.9374041449, max: 353730.7362391832 }, ratio: { tokens: 0.8762446217762629, cost: 0.7306019851396368, durationMs: 2.548487904710467 },
      failed: 0, unreached: 0.875, out: 1, stalled: 0 },
    refactor: { tokens: { p50: 1015699.6225048762 }, cost: { min: 4.694542593467505, p50: 5.27656163331045, max: 5.404960291238031 },
      durationMs: { p50: 1380813.177275923, max: 1551227.5583593587 }, ratio: { tokens: 0.9503913946357234, cost: 0.9253452304170686, durationMs: 8.865929939329018 },
      failed: 0.5, unreached: 2.375, out: 2, stalled: 0 },
    research: { tokens: { p50: 748749 }, cost: { min: 3.7261065662897948, p50: 4.339204304368607, max: 5.067353557265026 },
      durationMs: { p50: 1065019.803968438, max: 1135355.8427471013 }, ratio: { tokens: 0.9818065740873121, cost: 0.8371247974657923, durationMs: 7.634517665882628 },
      failed: 0, unreached: 0.5, out: 4, stalled: 0 },
    incident: { tokens: { p50: 403858.4673184281 }, cost: { min: 3.5065283647311096, p50: 3.904827618857333, max: 4.255479806543741 },
      durationMs: { p50: 1057129.2968596434, max: 1125543.6831930345 }, ratio: { tokens: 0.9219537961731424, cost: 0.828504025849552, durationMs: 6.330042783480099 },
      failed: 0.375, unreached: 0.25, out: 2, stalled: 0 },
  };
  // ADR 0014's table, as it prints them: tokens vs the swarm, cost, time, ran out of tokens.
  const adr = { custom: '88% $0.96 2.5× 1', refactor: '95% $5.28 8.9× 2', research: '98% $4.34 7.6× 4', incident: '92% $3.90 6.3× 2' };
  for (const [tpl, want] of Object.entries(pinned)) {
    const so = (await S.estimateSpec(S.defaultSpec(tpl, 1), { runs: 8 })).solo;
    assert.deepEqual(plain(so), want, tpl + ': bit for bit');
    assert.equal(Math.round(so.ratio.tokens * 100) + '% $' + so.cost.p50.toFixed(2) + ' ' + so.ratio.durationMs.toFixed(1) + '× ' + so.out, adr[tpl],
      tpl + ': and ADR 0014\'s table row is these figures');
  }
});

test('an estimate from before the baseline still reads; a baseline survives the store, clamped', async () => {
  const s = S.defaultSpec('custom', 1);
  const store = (estimate) => S.normalizeSpec(plain(Object.assign({}, s, { estimate }))).estimate;
  const before = { sig: 'abcdefgh', at: 1, runs: 8, cost: { min: 1, p50: 2, max: 3 }, durationMs: { p50: 4, max: 5 }, tokens: { p50: 6 }, peak: { p50: 7 }, failed: 0.5, over: 1, stalled: 0 };
  const old = store(before);
  assert.equal(old.solo, null, 'a 0.4 estimate has no baseline');
  assert.deepEqual(plain(old), Object.assign({}, before, { solo: null }), 'and keeps every figure it had');

  const est = await S.estimateSpec(s, { runs: 2 });
  assert.deepEqual(store(est).solo, est.solo, 'a baseline round-trips as it was');

  const hostile = store(Object.assign({}, before, { solo: { out: 99, stalled: -3, failed: -1, unreached: 'many', cost: 'x', ratio: [1], tokens: { p50: 1e99 } } }));
  assert.equal(hostile.solo.out, 8, 'no more runs out of tokens than runs');
  assert.equal(hostile.solo.stalled, 0);
  assert.equal(hostile.solo.failed, 0);
  assert.equal(hostile.solo.unreached, 0);
  assert.deepEqual(plain(hostile.solo.cost), { min: 0, p50: 0, max: 0 });
  assert.deepEqual(plain(hostile.solo.ratio), { tokens: 0, cost: 0, durationMs: 0 });
  assert.equal(hostile.solo.tokens.p50, 1e12, 'clamped');
  assert.equal(store(Object.assign({}, before, { solo: 'x' })).solo, null);
  assert.equal(store(Object.assign({}, before, { solo: [] })).solo, null);
});

test('the baseline line is labelled SIM, and absent without a baseline', async () => {
  const est = await S.estimateSpec(S.defaultSpec('custom', 1), { runs: 2 });
  assert.equal(S.soloLine(Object.assign({}, est, { solo: null })), '');
  assert.equal(S.soloLine(null), '');
  const line = (out, unreached = 0) => S.soloLine(Object.assign({}, est, { solo: Object.assign({}, est.solo, { out, unreached }) }));
  assert.match(line(0), /<span class="src-tag sim">SIM<\/span>1 agent, same tokens: ≈ \$/);
  assert.match(line(0), /× the swarm’s time\)<\/div>$/, 'how much longer one agent takes');
  assert.doesNotMatch(line(0), /· out of tokens/, 'nothing said of running out, when it did not');
  assert.match(line(2), /· out of tokens in 2<\/div>$/, 'running out is said, when it happened');
  assert.match(line(2, 0.75), /· out of tokens in 2 \(0\.8 tasks left \/ run\)<\/div>$/, 'with what it left undone, which its time does not cover');
});

test('the editor\'s baseline box is labelled SIM and says what it assumes; without a baseline, it says how to get one', async () => {
  const est = await S.estimateSpec(S.defaultSpec('custom', 1), { runs: 2 });
  const box = (solo, over = {}) => S.soloBox(Object.assign({}, est, over, { solo: Object.assign({}, est.solo, solo) }));
  const figure = (html, k) => { const m = html.match(new RegExp('<span>' + k + '</span><b>([^<]*)</b>')); return m && m[1]; };
  assert.equal(S.soloBox(null), '', 'no estimate, no box');

  const plainBox = box({ unreached: 0, stalled: 0, out: 1 });
  assert.match(plainBox, /^<div class="ed-box"><div class="panel-title" title="[^"]+">ONE AGENT, SAME TOKENS <span class="src-tag sim">SIM<\/span><\/div>/, 'labelled SIM');
  assert.doesNotMatch(plainBox, /src-tag live|LIVE/, 'and never LIVE');
  assert.ok(plainBox.includes('<p class="est-note">' + S.escapeHtml(S.SOLO_NOTE) + '</p>'), 'with what it assumes');
  assert.match(figure(plainBox, 'cost \\(p50\\)'), /^\$\d+\.\d\d · \d+% of swarm$/);
  assert.match(figure(plainBox, 'tokens \\(p50\\)'), /% of swarm$/);
  assert.match(figure(plainBox, 'duration \\(p50\\)'), /^\d+:\d\d · \d+\.\d× swarm$/);
  assert.equal(figure(plainBox, 'out of tokens'), '1 of 2');
  assert.equal(figure(plainBox, 'tasks left'), null, 'nothing left, no row');
  assert.equal(figure(plainBox, 'cut off'), null, 'nothing cut off, no row');

  const free = box({}, { cost: { min: 0, p50: 0, max: 0 } });
  assert.doesNotMatch(figure(free, 'cost \\(p50\\)'), /of swarm/, 'no share of a swarm that cost nothing');
  assert.match(figure(free, 'tokens \\(p50\\)'), /% of swarm$/);

  const short = box({ unreached: 1.5, stalled: 1, out: 2 });
  assert.equal(figure(short, 'tasks left'), '1.5 / run');
  assert.equal(figure(short, 'cut off'), '1 of 2');

  const none = S.soloBox(Object.assign({}, est, { solo: null }));
  assert.match(none, /ONE AGENT, SAME TOKENS <span class="src-tag sim">SIM<\/span>/);
  assert.ok(none.includes('<p class="est-note">No one-agent baseline in this estimate — Σ Estimate again.</p>'));
  assert.doesNotMatch(none, /est-row/, 'and no figures');
});

/**
 * Run `fn` with a stand-in for the few page elements a render touches, by id, created on first use.
 * It is installed after the page has loaded and removed after, so loading still fails loudly on a
 * script that reaches for `document` (the harness's rule), and no other test sees it.
 */
function withElements(fn) {
  const els = new Map();
  const el = (id) => { if (!els.has(id)) els.set(id, { id, innerHTML: '', disabled: false, querySelectorAll: () => [] }); return els.get(id); };
  page.ctx.document = { getElementById: el };
  try { return fn(el); } finally { delete page.ctx.document; }
}

test('⭐ a library card shows the baseline\'s SIM line with its estimate — and none while estimating, or without one', async () => {
  const s = S.defaultSpec('custom', 1);
  s.id = 'sw-solo-card';
  s.estimate = await S.estimateSpec(s, { runs: 2 });
  const launcher = Object.assign(Object.create(S.Launcher.prototype), {
    busy: new Map(), lib: { writable: () => true }, host: { can: () => true, role: () => 'operator', mode: 'embedded' },
  });
  const est = (spec) => { const m = launcher.card(spec).match(/<div class="sw-est">([\s\S]*)<\/div><div class="sw-runs">/); return m && m[1]; };

  const line = S.soloLine(s.estimate);
  assert.match(line, /<span class="src-tag sim">SIM<\/span>1 agent, same tokens/);
  assert.ok(est(s).startsWith('<b>≈ '), 'the swarm\'s own estimate first');
  assert.ok(est(s).endsWith(line), '⭐ and the baseline\'s SIM line under it, on the card');

  s.budget += 1; // a setting the estimate priced
  assert.match(est(s), /stale<\/span><div class="sw-solo"/, 'a stale estimate keeps its line, after the stale mark');
  assert.ok(est(s).endsWith(line));

  launcher.busy.set(s.id, { progress: 0.5 });
  assert.doesNotMatch(est(s), /sw-solo/, 'while estimating, no line from the old estimate');
  launcher.busy.clear();

  const old = Object.assign({}, s, { estimate: Object.assign({}, s.estimate, { solo: null }) });
  assert.match(est(old), /runs/, 'an estimate from before the baseline still shows');
  assert.doesNotMatch(est(old), /sw-solo|SIM/, 'with no line');
  assert.doesNotMatch(est(Object.assign({}, s, { estimate: null })), /sw-solo/);
});

test('⭐ the editor\'s side panel shows the baseline\'s SIM box under the cost estimate — and none while estimating, or with no estimate', async () => {
  const d = S.defaultSpec('custom', 1);
  d.estimate = await S.estimateSpec(d, { runs: 2 });
  const editor = Object.assign(Object.create(S.Editor.prototype), { draft: d, estJob: null, app: { library: { backend: () => 'server' } } });
  const side = () => withElements((el) => { editor.renderSide(); return el('ed-side').innerHTML; });

  const html = side(), box = S.soloBox(d.estimate);
  assert.match(box, /ONE AGENT, SAME TOKENS <span class="src-tag sim">SIM<\/span>/);
  const at = html.indexOf(box);
  assert.ok(at > 0, '⭐ the baseline\'s box is in the editor');
  const cost = html.indexOf('COST ESTIMATE');
  assert.ok(cost >= 0 && cost < at && at < html.indexOf('CHECKS'), 'under the swarm\'s cost estimate, above the checks');
  assert.equal(html.split('ONE AGENT, SAME TOKENS').length, 2, 'once');

  editor.estJob = { progress: 0.25, signal: { cancelled: false } };
  assert.doesNotMatch(side(), /ONE AGENT, SAME TOKENS/, 'while estimating, no box from the old estimate');
  editor.estJob = null;

  editor.draft = Object.assign({}, d, { estimate: Object.assign({}, d.estimate, { solo: null }) });
  assert.ok(side().includes('No one-agent baseline in this estimate — Σ Estimate again.'), 'an estimate without one says how to get one');

  editor.draft = Object.assign({}, d, { estimate: null });
  assert.doesNotMatch(side(), /ONE AGENT, SAME TOKENS/, 'no estimate, no box');
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

test('⭐ a crew interrupted by a restart ends interrupted — it does not poll forever', async () => {
  // agnostic 0.1.13 (ADR 0013): after a restart the crew's events and plan are gone (404) and
  // GET answers it `interrupted`, terminal, with no results. Unless the view counts that as an
  // end, it follows the crew's status forever as one still running.
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  const src = liveRun(fake, spec);
  const { events, summary } = await drive(src, { during: async () => {
    while (!fake.crews.size) await tick(2);
    const c = [...fake.crews.values()][0];
    c.status = 'running';
    fake.publish(c, 'crew_started', { task_count: c.taskIds.length });
    fake.publish(c, 'task_started', { task_id: c.taskIds[0], description: c.request.tasks[0].description, agent: c.request.agents[0].key });
    await tick(20);
    // The server restarts mid-run.
    Object.assign(c, { gone: true, status: 'interrupted', results: [], usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, metered_tasks: 0, costed_tasks: 0 },
      error: "the server restarted before this crew finished; tasks still in progress were lost" });
    c.times.started = 0;
    c.times.interrupted = c.times.submitted + 60000;
  } });
  assert.ok(summary, '⭐ the watch ended — it did not poll forever');
  assert.equal(summary.status, 'interrupted');
  assert.match(summary.error, /restarted/, 'with the reason');
  assert.equal(summary.tasksDone, 0, 'nothing it did was kept');
  assert.equal(summary.tasksFailed, spec.tasks.length, 'and every task is settled');
  assert.ok(summary.results.every((r) => r.status === 'failed'), 'none left pending or at work');
  assert.ok(events.some((e) => e.type === 'task.failed' && e.payload.reason === 'Interrupted by a server restart'),
    'each one says a restart cut it short');
  assert.equal(summary.tokensActual, false, 'and no metered tokens are claimed');
});

test('events that left the server\'s window are counted once as missed, and the outcome still settles every task', async () => {
  // H3 (0.1.13): a reader more than the server's window behind gets every event still held, from
  // the oldest, and `missed`. Nothing mid-run recovers the lost ones, so the tasks they covered are
  // settled by the crew's outcome, and EVENTS MISSED says how many there were.
  const fake = new FakeAgnostic();
  const spec = S.defaultSpec('custom', 1);
  const src = liveRun(fake, spec);
  const { summary } = await drive(src, { during: async () => {
    while (!fake.crews.size) await tick(2);
    const c = [...fake.crews.values()][0];
    // Between two polls the crew runs ahead, and the window moves past its first three events:
    // the start, and the whole of the first task.
    c.status = 'running';
    fake.publish(c, 'crew_started', { task_count: c.taskIds.length });
    fake.publish(c, 'task_started', { task_id: c.taskIds[0], description: c.request.tasks[0].description, agent: c.request.agents[0].key });
    fake.publish(c, 'task_completed', { task_id: c.taskIds[0], status: 'completed' });
    fake.publish(c, 'task_started', { task_id: c.taskIds[1], description: c.request.tasks[1].description, agent: c.request.agents[0].key });
    c.oldest = 4;
    await tick(20);
    fake.finish(c);
  } });
  assert.ok(summary, 'the crew finished');
  assert.equal(summary.status, 'completed');
  assert.equal(summary.missed, 3, 'the three events that left the window are counted, and only once');
  assert.equal(summary.dropped, 3, 'EVENTS MISSED: none dropped before agnostic took them, three missed');
  assert.equal(summary.tasksDone, spec.tasks.length, 'every task settled, the one whose events were missed included');
  assert.equal(summary.results[0].output, 'answer 0', 'its output from the outcome');
  const cursors = fake.calls.filter((c) => c.path.includes('/events?after=')).map((c) => Number(c.path.split('after=')[1]));
  assert.ok(cursors.some((n) => n >= 4), 'the cursor moved on from the window');
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
