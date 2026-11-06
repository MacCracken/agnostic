// The Users view in a real browser: the real server, the shell, the sandboxed iframe, over the DevTools
// protocol. `*.test.mjs` runs the page's logic with no DOM, so it cannot see a modal the sandbox refuses
// or a control styled white on white. This found both, at 0.3.1.
//
// By hand, and not in CI, which has no browser:
//   node tests/webgui/browser/users.e2e.mjs "$PWD/build/agnostic" <directory for screenshots>
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BIN = process.argv[2], PORT = 18750, DEBUG = 18751, BASE = `http://127.0.0.1:${PORT}`;
const OUT = process.argv[3];
const work = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'e2e-'));
const server = spawn(BIN, [], { env: { ...process.env, AGNOSTIC_ADDR: '127.0.0.1', AGNOSTIC_PORT: String(PORT), AGNOSTIC_AUTH: 'required',
  AGNOSTIC_BOOTSTRAP_EMAIL: 'root@example.com', AGNOSTIC_BOOTSTRAP_PASSWORD: 'root-password-123',
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
await fetch(BASE + '/api/v1/plugins/users', { method: 'PUT', headers: auth, body: '{"enabled":true}' });
const seed = await fetch(BASE + '/api/v1/tenants', { method: 'POST', headers: auth, body: '{"key":"acme","name":"Acme"}' });
console.log('seeded tenant:', seed.status);

await waitUrl(`http://127.0.0.1:${DEBUG}/json/version`);
const version = await (await fetch(`http://127.0.0.1:${DEBUG}/json/version`)).json();
const ws = new WebSocket(version.webSocketDebuggerUrl);
await new Promise((r) => { ws.onopen = r; });
let id = 0; const waiting = new Map(); const errors = []; let frameSession = null;
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) { const w = waiting.get(d.id); waiting.delete(d.id); d.error ? w.rej(new Error(JSON.stringify(d.error))) : w.res(d.result); return; }
  if (d.method === 'Target.attachedToTarget' && d.params.targetInfo.type === 'iframe') {
    frameSession = d.params.sessionId;
    send('Runtime.enable', {}, frameSession).catch(() => {});
    send('Log.enable', {}, frameSession).catch(() => {});
    return;
  }
  if (d.method === 'Runtime.exceptionThrown') errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error') errors.push(d.params.entry.text + ' ' + (d.params.entry.url || ''));
  if (d.method === 'Runtime.consoleAPICalled' && d.params.type === 'error') errors.push(d.params.args.map((a) => a.value).join(' '));
};
const send = (method, params = {}, sessionId) => new Promise((res, rej) => { const n = ++id; waiting.set(n, { res, rej }); ws.send(JSON.stringify({ id: n, method, params, ...(sessionId ? { sessionId } : {}) })); });
const pages = (await send('Target.getTargets')).targetInfos.filter((t) => t.type === 'page');
const { sessionId: pageSession } = await send('Target.attachToTarget', { targetId: pages[0].targetId, flatten: true });
await send('Page.enable', {}, pageSession); await send('Runtime.enable', {}, pageSession); await send('Log.enable', {}, pageSession);
await send('Target.setDiscoverTargets', { discover: true });
await send('Page.navigate', { url: BASE + '/ui#plugin/users' }, pageSession);
await sleep(1200);

const top = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }, pageSession); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value; };
await top(`(async () => {
  document.getElementById('signin-email').value = 'root@example.com';
  document.getElementById('signin-password').value = 'root-password-123';
  document.getElementById('signin-go').click();
})()`);
await sleep(1200);
await top(`location.hash = '#plugin/users'`);
await sleep(1200);

// The sandboxed frame runs out of process, in a DevTools session of its own.
// `IsolateSandboxedIframes` off keeps the frame in the page's process, so it can be reached by frame id.
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
const text = (sel) => inFrame(`(document.querySelector(${JSON.stringify(sel)})||{}).textContent||''`);
const clickText = (label) => inFrame(`(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.trim()===${JSON.stringify(label)}); if(!b) return false; b.click(); return true; })()`);
const setField = (id, v) => inFrame(`(() => { const e=document.getElementById(${JSON.stringify(id)}); if(!e) return false; e.value=${JSON.stringify(v)}; return true; })()`);
const rows = () => inFrame(`[...document.querySelectorAll('#list .row .nm')].map(x=>x.textContent)`);
const shot = async (name) => { const s = await send('Page.captureScreenshot', { format: 'png' }, pageSession); writeFileSync(join(OUT, name), Buffer.from(s.data, 'base64')); };

console.log('sandbox:', await top(`document.getElementById('plugin-frame').getAttribute('sandbox')`));
ok((await rows()).includes('root@example.com'), 'the view lists the signed-in user');
ok((await inFrame(`[...document.querySelectorAll('#tabs button')].map(b=>b.textContent).join()`)) === 'Users,Tenants', 'a super administrator has both tabs');

ok(await clickText('New user'), 'New user opens the form');
await sleep(150);
ok(await inFrame(`document.querySelectorAll('#f-role option').length`) === 4, 'a super administrator can hand out all four roles');
await setField('f-email', 'ada@acme.test'); await setField('f-password', 'short'); await clickText('Create'); await sleep(250);
ok((await text('.box.bad')).includes('at least 12'), 'a short password is refused in the form');
ok((await inFrame(`document.getElementById('f-password') ? document.getElementById('f-password').value : 'gone'`)) === '', '⭐ and the password field is empty after');
await setField('f-email', 'ada@acme.test'); await setField('f-password', 'correct-horse-battery');
await inFrame(`(() => { document.getElementById('f-role').value='operator'; document.getElementById('f-tenant').value='acme'; })()`);
await clickText('Create'); await sleep(500);
ok((await rows()).includes('ada@acme.test'), '⭐ creating a user through the sandboxed frame reaches the server');
await shot('users-detail.png');
const made = await (await fetch(BASE + '/api/v1/users', { headers: auth })).json();
const ada = made.users.find((u) => u.email === 'ada@acme.test');
ok(ada && ada.role === 'operator' && ada.tenant === 'acme', 'with the role and tenant chosen');

await inFrame(`(() => { const s=document.querySelector('#detail select'); s.value='viewer'; })()`);
await clickText('Change role'); await sleep(400);
ok((await (await fetch(BASE + '/api/v1/users/' + ada.id, { headers: auth })).json()).user.role === 'viewer', '⭐ a role change lands');

await inFrame(`document.querySelector('#detail input[type=password]').value='another-good-password'`);
await clickText('Set password'); await sleep(900);
ok((await text('.box.ok')).includes('Password set'), 'setting a password says so');
ok((await inFrame(`document.querySelector('#detail input[type=password]').value`)) === '', '⭐ and clears the field');
const relog = await fetch(BASE + '/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'ada@acme.test', password: 'another-good-password' }) });
ok(relog.status === 200, '⭐ the new password signs in');

ok(await clickText('Delete this user'), 'Delete asks');
await sleep(150);
ok((await text('#detail')).includes('Their keys and sessions stop working'), 'inline, with what it will do');
ok((await rows()).includes('ada@acme.test'), 'and has not deleted yet');
await clickText('Keep'); await sleep(150);
ok(await clickText('Delete this user'), 'Keep goes back');
await sleep(150);
ok(await clickText('Yes, delete'), 'then Yes, delete');
await sleep(500);
ok(!(await rows()).includes('ada@acme.test'), '⭐ the delete works in the sandbox, where window.confirm would have answered false');
ok((await (await fetch(BASE + '/api/v1/users', { headers: auth })).json()).users.every((u) => u.email !== 'ada@acme.test'), 'and the server agrees');

await clickText('Tenants'); await sleep(400);
ok((await rows()).includes('acme'), 'the Tenants tab lists tenants');
await clickText('New tenant'); await sleep(150);
await setField('f-key', 'zeta'); await setField('f-crewsaminute', '30'); await setField('f-unfinishedcrews', '4');
await clickText('Create'); await sleep(500);
const z = (await (await fetch(BASE + '/api/v1/tenants/zeta', { headers: auth })).json()).tenant;
ok(z && z.rate_limit === 30 && z.max_crews === 4, '⭐ a tenant is made with its limits');
await shot('users-tenant.png');
await setField('f-crewsaminute', ''); await clickText('Save'); await sleep(400);
const z2 = (await (await fetch(BASE + '/api/v1/tenants/zeta', { headers: auth })).json()).tenant;
ok(z2.rate_limit === 0 && z2.max_crews === 4, 'emptying a limit hands it back to the server');
await clickText('Delete'); await sleep(150); await clickText('Yes, delete'); await sleep(500);
ok((await fetch(BASE + '/api/v1/tenants/zeta', { headers: auth })).status === 404, 'a tenant is deleted, in place');

// Refused by the server: the last super administrator.
await clickText('Users'); await sleep(400);
await inFrame(`[...document.querySelectorAll('#list .row')].find(r=>r.textContent.includes('root@example.com')).click()`);
await sleep(300);
await clickText('Delete this user'); await sleep(150); await clickText('Yes, delete'); await sleep(500);
ok((await text('.box.bad')).length > 0, '⭐ deleting the last super administrator shows the server’s refusal: ' + (await text('.box.bad')));

const noise = errors.filter((e) => !/401|Failed to load resource/.test(e));
ok(noise.length === 0, 'no script error and no CSP violation in the console' + (noise.length ? ': ' + noise.slice(0, 3).join(' | ') : ''));
console.log(`\n${pass} passed, ${fail} failed`);
chrome.kill('SIGKILL'); server.kill('SIGTERM');
await sleep(300);
process.exit(fail ? 1 : 0);
