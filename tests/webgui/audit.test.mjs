// The Audit view's logic (src/webgui/plugins/audit/index.html), run in Node against a fake agnostic:
// GET /api/v1/audit (the summary) and GET /api/v1/audit/entries (newest first, `next` → `?before=`),
// both ADMIN, as the server answers them.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadPage } from './harness.mjs';

const page = loadPage('src/webgui/plugins/audit/index.html');
const A = page.get('({ validEntry, passesSeverity, matchesText, linkStates, mergeNewest, AuditTrail, PAGE })');

const hash = (i) => String(i).padStart(64, 'a');
const entry = (i, over = {}) => Object.assign({ index: i, timestamp: '2026-10-02T12:00:0' + (i % 10) + 'Z', severity: 'info', source: 'agnostic',
  action: 'crew.submit', details: 'crew_id=' + i, hash: hash(i), prev_hash: i ? hash(i - 1) : '0'.repeat(64) }, over);

class FakeAgnostic {
  constructor(n) { this.entries = []; for (let i = 0; i < n; i++) this.entries.push(entry(i)); this.role = 'admin'; this.calls = []; }
  answer(status, data) { return Promise.resolve({ status, data: structuredClone(data), etag: null }); }
  request(method, path) {
    this.calls.push(path);
    if (this.role !== 'admin') return this.answer(403, { error: 'insufficient role' });
    const [bare, query] = path.split('?');
    const q = new URLSearchParams(query || '');
    if (bare === '/api/v1/audit') return this.answer(200, { total: this.entries.length, entries_at_open: 0, appended: this.entries.length, dropped: 0, verified: 'open', intact: true, storage: 'patra' });
    if (bare === '/api/v1/audit/entries') {
      const limit = Number(q.get('limit') || 50);
      const before = q.has('before') ? Number(q.get('before')) : this.entries.length;
      const rows = this.entries.filter((e) => e.index < before).reverse().slice(0, limit);
      const out = { entries: rows, total: this.entries.length, oldest_held: 0 };
      if (rows.length && rows[rows.length - 1].index > 0) out.next = rows[rows.length - 1].index;
      return this.answer(200, out);
    }
    return this.answer(404, { error: 'no route' });
  }
}
const hostFor = (fake) => ({ mode: 'connected', request: (m, p) => fake.request(m, p), can: () => true });

test('filters: severity at least, and text over action and details', () => {
  assert.equal(A.passesSeverity(entry(1), 'all'), true);
  assert.equal(A.passesSeverity(entry(1), 'warning'), false);
  assert.equal(A.passesSeverity(entry(1, { severity: 'warning' }), 'warning'), true);
  assert.equal(A.passesSeverity(entry(1, { severity: 'security' }), 'error'), true, 'security is worse than error');
  assert.equal(A.passesSeverity(entry(1, { severity: 'mystery' }), 'error'), true, 'an unknown severity is shown, not hidden');
  assert.equal(A.matchesText(entry(7), 'CREW_ID=7'), true, 'case-insensitive, in the details');
  assert.equal(A.matchesText(entry(7), 'definition'), false);
  assert.equal(A.matchesText(entry(7), '  '), true);
  assert.equal(A.validEntry({ index: -1, action: 'x' }), false);
});

test('the chain column compares each link with the entry below it, as sent', () => {
  const rows = [entry(3), entry(2, { hash: 'f'.repeat(64) }), entry(1), entry(0)];
  const s = A.linkStates(rows);
  assert.equal(s.get(3), 'broken', '#3 names a hash #2 was not sent with');
  assert.equal(s.get(2), 'ok');
  assert.equal(s.get(1), 'ok');
  assert.equal(s.get(0), '', 'the first entry has nothing below it');
  assert.equal(A.linkStates([entry(9), entry(5)]).get(9), '', 'nor does one whose neighbour is not on screen');
});

test('the trail pages by index, newest first, and a refresh puts new entries on top', async () => {
  const fake = new FakeAgnostic(A.PAGE + 30);
  const t = new A.AuditTrail(hostFor(fake));
  assert.equal(await t.load(), true);
  assert.equal(t.summary.intact, true);
  assert.equal(t.entries.length, A.PAGE);
  assert.equal(t.entries[0].index, A.PAGE + 29, 'newest first');
  assert.equal(t.next, 30);
  await t.more();
  assert.equal(t.entries.length, A.PAGE + 30, 'then the older ones');
  assert.equal(t.entries.at(-1).index, 0);
  assert.equal(t.next, null);

  fake.entries.push(entry(A.PAGE + 30, { action: 'definition.delete', severity: 'warning' }));
  await t.refresh();
  assert.equal(t.entries[0].action, 'definition.delete', 'a new entry goes on top');
  assert.equal(t.entries.length, A.PAGE + 31, 'and nothing is lost or repeated');
  assert.equal(new Set(t.entries.map((e) => e.index)).size, t.entries.length);

  for (let i = 0; i < A.PAGE + 5; i++) fake.entries.push(entry(fake.entries.length));
  await t.refresh();
  assert.equal(t.entries[0].index, fake.entries.length - 1);
  const idx = t.entries.map((e) => e.index);
  assert.ok(idx.every((v, i) => i === 0 || idx[i - 1] === v + 1), 'more than a page arrived: it starts again from the newest, with no hole');
  assert.equal(t.next, idx.at(-1));
});

test('mergeNewest adds only what is newer', () => {
  const held = [entry(5), entry(4)];
  assert.deepEqual(A.mergeNewest(held, [entry(7), entry(6), entry(5)]).map((e) => e.index), [7, 6, 5, 4]);
  assert.deepEqual(A.mergeNewest([], [entry(1)]).map((e) => e.index), [1]);
});

test('a role that is not admin is told the trail is for administrators', async () => {
  const fake = new FakeAgnostic(3);
  fake.role = 'operator';
  const t = new A.AuditTrail(hostFor(fake));
  assert.equal(await t.load(), false);
  assert.match(t.error, /for administrators/);
  assert.match(t.summaryError, /for administrators/);
});
