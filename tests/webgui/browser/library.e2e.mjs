// The Library view in a real browser, on what 0.4.3 gave it: a definition's versions, a rollback, a
// deleted definition brought back, and a package out as a download and back in through the file input.
// A sandboxed frame, a file chooser and a download are what a Node test cannot see. The same harness as
// `users.e2e.mjs`.
//
// By hand, and not in CI, which has no browser:
//   node tests/webgui/browser/library.e2e.mjs "$PWD/build/agnostic" <directory for screenshots>
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync, readdirSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BIN = process.argv[2], PORT = 18762, DEBUG = 18763, BASE = `http://127.0.0.1:${PORT}`;
const OUT = process.argv[3];
const work = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'e2e-'));
const server = spawn(BIN, [], { env: { ...process.env, AGNOSTIC_ADDR: '127.0.0.1', AGNOSTIC_PORT: String(PORT), AGNOSTIC_AUTH: 'required',
  AGNOSTIC_BOOTSTRAP_EMAIL: 'root@example.com', AGNOSTIC_BOOTSTRAP_PASSWORD: 'root-password-123',
  AGNOSTIC_TARGET_HOSTS: 'sut.example,other.example',
  AGNOSTIC_DB_PATH: join(work, 'db.patra'), AGNOSTIC_AUDIT_PATH: join(work, 'audit.patra') }, stdio: 'ignore' });
const chrome = spawn('/usr/bin/chromium', ['--headless=new', `--remote-debugging-port=${DEBUG}`, `--user-data-dir=${join(work, 'chrome')}`,
  '--no-sandbox', '--disable-gpu', '--disable-features=IsolateSandboxedIframes', '--disable-site-isolation-trials', '--window-size=1280,860', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
const ok = (c, what) => { if (c) { pass++; console.log('  ok: ' + what); } else { fail++; console.log('  FAIL: ' + what); } };

async function waitUrl(u) { for (let i = 0; i < 100; i++) { try { const r = await fetch(u); if (r.ok) return r; } catch (e) {} await sleep(100); } throw new Error('no answer from ' + u); }
process.on('exit', () => { try { chrome.kill('SIGKILL'); server.kill('SIGKILL'); } catch (e) {} });
process.on('uncaughtException', (e) => { console.log('HARNESS ERROR:', e.message); process.exit(2); });
process.on('unhandledRejection', (e) => { console.log('HARNESS ERROR:', e && e.message); process.exit(2); });
await waitUrl(BASE + '/health');
const login = await (await fetch(BASE + '/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'root@example.com', password: 'root-password-123' }) })).json();
const auth = { Authorization: 'Bearer ' + login.token, 'Content-Type': 'application/json' };
await fetch(BASE + '/api/v1/plugins/library', { method: 'PUT', headers: auth, body: '{"enabled":true}' });
const def = (key, goal) => JSON.stringify({ key, name: 'Reviewer', role: 'reviewer', goal, focus: 'edges' });
const DEFS = BASE + '/api/v1/agents/definitions';
await fetch(DEFS, { method: 'POST', headers: auth, body: def('reviewer', 'first goal') });
await fetch(DEFS + '/reviewer', { method: 'PUT', headers: auth, body: def('reviewer', 'second goal') });
await fetch(DEFS, { method: 'POST', headers: auth, body: def('keeper', 'kept goal') });
const goal = async (key) => { const r = await fetch(DEFS + '/' + key, { headers: auth }); return r.status === 200 ? (await r.json()).definition.goal : r.status; };
const DOWNLOADS = mkdtempSync(join(work, 'dl-'));

await waitUrl(`http://127.0.0.1:${DEBUG}/json/version`);
const version = await (await fetch(`http://127.0.0.1:${DEBUG}/json/version`)).json();
const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((r) => { ws.onopen = r; });
let id = 0; const waiting = new Map(); const errors = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) { const w = waiting.get(d.id); waiting.delete(d.id); d.error ? w.rej(new Error(JSON.stringify(d.error))) : w.res(d.result); return; }
  if (d.method === 'Runtime.exceptionThrown') errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error') errors.push(d.params.entry.text + ' ' + (d.params.entry.url || ''));
  if (d.method === 'Runtime.consoleAPICalled' && d.params.type === 'error') errors.push(d.params.args.map((a) => a.value).join(' '));
};
const send = (method, params = {}, sessionId) => new Promise((res, rej) => { const n = ++id; waiting.set(n, { res, rej }); ws.send(JSON.stringify({ id: n, method, params, ...(sessionId ? { sessionId } : {}) })); });
const pages = (await send('Target.getTargets')).targetInfos.filter((t) => t.type === 'page');
const { sessionId: pageSession } = await send('Target.attachToTarget', { targetId: pages[0].targetId, flatten: true });
await send('Page.enable', {}, pageSession); await send('Runtime.enable', {}, pageSession); await send('Log.enable', {}, pageSession);
await send('Page.navigate', { url: BASE + '/ui#plugin/library?tab=definitions&item=reviewer' }, pageSession);
await sleep(1200);

const top = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }, pageSession); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value; };
await top(`(async () => {
  document.getElementById('signin-email').value = 'root@example.com';
  document.getElementById('signin-password').value = 'root-password-123';
  document.getElementById('signin-go').click();
})()`);
await sleep(1200);
await top(`location.hash = '#plugin/library?tab=definitions&item=reviewer'`);
await sleep(1500);

let world = null;
const inFrame = async (expr) => {
  const tree = (await send('Page.getFrameTree', {}, pageSession)).frameTree;
  const kid = (tree.childFrames || [])[0];
  if (!kid) throw new Error('no plugin frame; page is ' + tree.frame.url);
  if (!world || world.loader !== kid.frame.loaderId) {
    const w = await send('Page.createIsolatedWorld', { frameId: kid.frame.id, worldName: 'e2e' }, pageSession);
    world = { loader: kid.frame.loaderId, ctx: w.executionContextId };
  }
  const r = await send('Runtime.evaluate', { expression: expr, contextId: world.ctx, awaitPromise: true, returnByValue: true }, pageSession);
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};
const shot = async (name) => { const s = await send('Page.captureScreenshot', { format: 'png' }, pageSession); writeFileSync(join(OUT, name), Buffer.from(s.data, 'base64')); };

const click = (label) => inFrame(`(() => { const b = [...document.querySelectorAll('button')].find((x) => !x.hidden && x.textContent.trim() === ${JSON.stringify(label)}); if (!b) return false; b.click(); return true; })()`);
const text = () => inFrame(`document.body.innerText`);
const until = async (what, want) => { for (let i = 0; i < 40; i++) { if (want.test(await text())) return true; await sleep(100); } console.log('  waited for ' + want + ' in ' + what + '; page: ' + (await text()).slice(0, 300)); return false; };

ok(await until('the versions', /versions/i), 'the definition shows its versions');
let page = await text();
ok(/v2/.test(page) && /v1/.test(page), '⭐ both of them');
ok(/CURRENT/i.test(page), 'and which is current');
await shot('library-versions.png');

ok(await click('v1'), 'a version opens');
ok(await until('the comparison', /Roll back to version 1/), '⭐ with the way back');
page = await text();
ok(page.includes('first goal') && page.includes('second goal'), '⭐ it shows that version beside what is current');
await shot('library-compare.png');

ok(await click('Roll back to version 1'), 'a rollback is asked for');
ok(await until('the question', /It affects every crew/), '⭐ and asked about, in the page: a sandboxed frame has no confirm()');
ok(await click('Yes, roll back'), 'and answered');
ok(await until('the answer', /says what version 1 said/), 'it says what it did');
ok((await goal('reviewer')) === 'first goal', '⭐ the server holds it');
const vs = await (await fetch(DEFS + '/reviewer/versions', { headers: auth })).json();
ok(vs.total === 3, '⭐ as a new version, so that it can be undone');

// ⭐ If-Match reaches the server through the bridge: this is what the shell refused before 0.4.3.
ok(await click('v2'), 'an older version again');
ok(await until('the comparison', /Roll back to version 2/), 'it opens');
await fetch(DEFS + '/reviewer', { method: 'PUT', headers: auth, body: def('reviewer', 'theirs') });
await click('Roll back to version 2');
await until('the question', /It affects every crew/);
await click('Yes, roll back');
ok(await until('the refusal', /Someone else changed reviewer/), '⭐ a rollback from a stale page is refused');
ok((await goal('reviewer')) === 'theirs', '⭐ and their edit stands');

await inFrame(`[...document.querySelectorAll('button')].find((b) => b.textContent.includes('Back to the definition')).click()`);
await until('the definition', /versions/i);
await send('Page.reload', {}, pageSession);
await sleep(1500);
world = null;
await until('a reload', /versions/i);
ok(await click('Delete'), 'delete');
await until('the question', /Its versions are kept/);
ok(await click('Yes, delete it'), 'confirmed');
ok(await until('the answer', /bring it back/), '⭐ the message offers the way back');
ok((await goal('reviewer')) === 404, 'it is gone');
await inFrame(`[...document.querySelectorAll('button')].find((b) => b.textContent.includes('bring it back')).click()`);
ok(await until('the deleted page', /This definition was deleted/), 'the page says what happened');
await click('v1');
ok(await until('the version', /Bring it back as version 1/), 'a version of it opens');
await shot('library-deleted.png');
await click('Bring it back as version 1');
await until('the question', /Yes, bring it back/);
await click('Yes, bring it back');
ok(await until('the answer', /says what version 1 said/), 'it is back');
ok((await goal('reviewer')) === 'first goal', '⭐ on the server');

// A real download out of a sandboxed frame.
await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DOWNLOADS, browserContextId: undefined, eventsEnabled: false });
ok(await click('Export'), 'export');
let file = '';
for (let i = 0; i < 40 && !file; i++) { file = readdirSync(DOWNLOADS).find((f) => f.endsWith('.json') && !f.endsWith('.crdownload')) || ''; await sleep(100); }
ok(/^agnostic-definitions-\d{4}-\d{2}-\d{2}\.json$/.test(file), '⭐ a package is saved as a file, out of a sandboxed frame');
const pkg = file ? JSON.parse(readFileSync(join(DOWNLOADS, file), 'utf8')) : {};
ok(pkg.format === 'agnostic-package/1' && pkg.definitions.length === 2, 'holding both definitions');
ok(pkg.definitions.find((d) => d.key === 'keeper').focus === 'edges', '⭐ and what the engine has no slot for');

// And back in, through the page's own file input.
await fetch(DEFS + '/keeper', { method: 'DELETE', headers: auth });
const input = await send('Runtime.evaluate', { expression: `document.getElementById('import-file')`, contextId: world.ctx }, pageSession);
await send('DOM.enable', {}, pageSession);
await send('DOM.setFileInputFiles', { files: [join(DOWNLOADS, file)], objectId: input.result.objectId }, pageSession);
ok(await until('the package', /Import 2 definitions/), '⭐ a chosen file shows what it holds, and waits');
ok((await goal('keeper')) === 404, 'nothing has gone in yet');
await shot('library-import.png');
await click('Import 2 definitions');
ok(await until('the conflict', /Already stored: reviewer/), '⭐ a key already stored stops it, by name');
ok((await goal('keeper')) === 404, '⭐ and none of it went in');
await click('Replace them and import');
ok(await until('the answer', /Imported 1 new and replaced 1/), 'replacing is asked for, and done');
ok((await goal('keeper')) === 'kept goal', '⭐ the package is back');

const noise = errors.filter((e) => !/401|Failed to load resource/.test(e));
ok(noise.length === 0, 'no script error and no CSP violation in the console' + (noise.length ? ': ' + noise.slice(0, 3).join(' | ') : ''));
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
