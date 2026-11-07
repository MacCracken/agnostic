// The Crews view in a real browser, on what a crew's body can say since 0.4.0: its target, a task's own,
// and an answer out of the shape it declared, which takes a gateway since 0.4.2: a placeholder is not
// judged, so this runs `scripts/fake-gateway.py`. Since 0.4.3 it starts a crew by who it needs, too. The
// same harness as `users.e2e.mjs`.
//
// By hand, and not in CI, which has no browser:
//   node tests/webgui/browser/crews.e2e.mjs "$PWD/build/agnostic" <directory for screenshots>
import { spawn } from 'node:child_process';
import { writeFileSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const BIN = process.argv[2], PORT = 18752, DEBUG = 18753, BASE = `http://127.0.0.1:${PORT}`;
const OUT = process.argv[3];
const work = mkdtempSync(join(process.env.TMPDIR || tmpdir(), 'e2e-'));
const GATEWAY = 18754;
const gateway = spawn('python3', ['scripts/fake-gateway.py', String(GATEWAY)], { stdio: 'ignore' });
const server = spawn(BIN, [], { env: { ...process.env, AGNOSTIC_ADDR: '127.0.0.1', AGNOSTIC_PORT: String(PORT), AGNOSTIC_AUTH: 'required',
  AGNOSTIC_BOOTSTRAP_EMAIL: 'root@example.com', AGNOSTIC_BOOTSTRAP_PASSWORD: 'root-password-123',
  AGNOSTIC_TARGET_HOSTS: 'sut.example,other.example', AGNOSTIC_LLM_URL: `http://127.0.0.1:${GATEWAY}`,
  AGNOSTIC_DB_PATH: join(work, 'db.patra'), AGNOSTIC_AUDIT_PATH: join(work, 'audit.patra') }, stdio: 'ignore' });
const chrome = spawn('/usr/bin/chromium', ['--headless=new', `--remote-debugging-port=${DEBUG}`, `--user-data-dir=${join(work, 'chrome')}`,
  '--no-sandbox', '--disable-gpu', '--disable-features=IsolateSandboxedIframes', '--disable-site-isolation-trials', '--window-size=1280,860', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
const ok = (c, what) => { if (c) { pass++; console.log('  ok: ' + what); } else { fail++; console.log('  FAIL: ' + what); } };

async function waitUrl(u) { for (let i = 0; i < 100; i++) { try { const r = await fetch(u); if (r.ok) return r; } catch (e) {} await sleep(100); } throw new Error('no answer from ' + u); }
process.on('exit', () => { try { chrome.kill('SIGKILL'); server.kill('SIGKILL'); gateway.kill('SIGKILL'); } catch (e) {} });
process.on('uncaughtException', (e) => { console.log('HARNESS ERROR:', e.message); process.exit(2); });
process.on('unhandledRejection', (e) => { console.log('HARNESS ERROR:', e && e.message); process.exit(2); });
await waitUrl(BASE + '/health');
await sleep(500);   // the gateway has no route to wait on
const login = await (await fetch(BASE + '/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: 'root@example.com', password: 'root-password-123' }) })).json();
const auth = { Authorization: 'Bearer ' + login.token, 'Content-Type': 'application/json' };
await fetch(BASE + '/api/v1/plugins/crews', { method: 'PUT', headers: auth, body: '{"enabled":true}' });
await fetch(BASE + '/api/v1/agents/definitions', { method: 'POST', headers: auth, body: JSON.stringify({ key: 'reviewer', name: 'Reviewer', role: 'reviewer', goal: 'find what is wrong' }) });
const crew = await fetch(BASE + '/api/v1/crews', { method: 'POST', headers: auth, body: JSON.stringify({
  name: 'aimed crew', target: { url: 'https://sut.example/app' }, agents: [{ definition: 'reviewer' }],
  tasks: [{ description: 'say-prose about the login page', output_schema: { type: 'object', required: ['verdict'] } },
          { description: 'compare with the other one', target: { url: 'https://other.example/' } }] }) });
console.log('submitted:', crew.status);
const crewId = (await crew.json()).crew_id;

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
await send('Page.navigate', { url: BASE + '/ui#plugin/crews' }, pageSession);
await sleep(1200);

const top = async (expr) => { const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }, pageSession); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value; };
await top(`(async () => {
  document.getElementById('signin-email').value = 'root@example.com';
  document.getElementById('signin-password').value = 'root-password-123';
  document.getElementById('signin-go').click();
})()`);
await sleep(1200);
await top(`location.hash = '#plugin/crews'`);
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

ok((await inFrame(`document.body.textContent`)).includes('aimed crew'), 'the list shows the crew');
ok((await inFrame(`[...document.querySelectorAll('.row .sub')].map(x=>x.textContent).join(' ')`)).includes('https://sut.example/app'), '⭐ and what it was pointed at');
await inFrame(`[...document.querySelectorAll('button.row')].find(b=>b.textContent.includes('aimed crew')).click()`);
await sleep(1500);
const page = await inFrame(`document.body.innerText`);
ok(/target/i.test(page) && page.includes('https://sut.example/app'), '⭐ the detail has a Target fact');
ok(page.includes('against https://other.example/'), '⭐ a task with its own target says so');
ok(!page.includes('against https://sut.example/app'), 'and one running against its crew’s does not repeat it');
ok(page.includes('Its output is not in the shape this task declared.'), '⭐ a task the engine failed for its shape says so');
ok(page.includes('output failed validation'), '⭐ and why');
const plan = await (await fetch(BASE + '/api/v1/crews/' + crewId + '/plan', { headers: auth })).json();
ok(plan.agents[0].key === 'reviewer' && plan.agents[0].name === 'Reviewer', 'the agent is the stored definition it named');
ok((await inFrame(`[...document.querySelectorAll('.fact a')].length`)) === 0, '⭐ a target is text, never a link');
await shot('crews-target.png');

// The composer (0.4.3): a crew said by who it needs, on the same gateway.
const click = (label) => inFrame(`(() => { const b = [...document.querySelectorAll('button')].find((x) => !x.hidden && x.textContent.trim() === ${JSON.stringify(label)}); if (!b) return false; b.click(); return true; })()`);
const text = () => inFrame(`document.body.innerText`);
const until = async (want) => { for (let i = 0; i < 40; i++) { if (want.test(await text())) return true; await sleep(100); } console.log('  waited for ' + want + '; page: ' + (await text()).slice(0, 300)); return false; };
// Typed as a person types: the view keeps what an `input` event hands it, and nothing else.
const type = (selector, value) => inFrame(`(() => { const i = document.querySelector(${JSON.stringify(selector)}); if (!i) return false; i.value = ${JSON.stringify(value)}; i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);

ok(await click('New crew'), 'a crew can be started from here');
ok(await until(/Say who the crew needs/), 'the composer opens');
await type('#c-name', 'team crew');
await type('#c-about', 'a thorough regression audit');
ok(await click('Suggest a preset'), 'it asks which preset fits');
ok(await until(/quality-large/), '⭐ and the server answers');
ok((await text()).includes('It went on: regression'), '⭐ with what it went on');
await shot('crews-suggest.png');
await click('Use its roles');
ok(await until(/These are the roles of quality-large/), 'a preset fills the team');
const roles = await inFrame(`[...document.querySelectorAll('.line:not(.task) input[type=text]:first-child')].map((i) => i.value)`);
ok(roles.length > 1 && roles.every(Boolean), '⭐ with its roles: ' + roles.length);
ok((await inFrame(`document.querySelector('#c-name').value`)) === 'team crew', '⭐ and what was typed survives the redraw');
await type('.line.task textarea', 'look at the login page');
await type('#c-target', 'https://nowhere.example/');
await click('Start crew');
ok(await until(/not one this deployment may test/), '⭐ the door refuses a target off the list, in the form');
ok((await inFrame(`document.querySelector('#c-name').value`)) === 'team crew', 'and nothing typed is lost');
await type('#c-target', 'https://sut.example/app');
await shot('crews-compose.png');
await click('Start crew');
ok(await until(/agents/i), '⭐ it starts, and opens');
const started = await inFrame(`document.querySelector('.id').textContent`);
const madePlan = await (await fetch(BASE + '/api/v1/crews/' + started + '/plan', { headers: auth })).json();
ok(madePlan.agents.length === roles.length, '⭐ one agent for each role');
ok(madePlan.agents.every((a) => (a.key || '').length > 0) && (await text()).includes(madePlan.agents[0].role), '⭐ and the page says who it became');
ok(!madePlan.agents[0].key.includes(' '), 'under keys a crew can hold');
await shot('crews-started.png');

const noise = errors.filter((e) => !/401|Failed to load resource/.test(e));
ok(noise.length === 0, 'no script error and no CSP violation in the console' + (noise.length ? ': ' + noise.slice(0, 3).join(' | ') : ''));
console.log(`\n${pass} passed, ${fail} failed`);
chrome.kill('SIGKILL'); server.kill('SIGTERM');
await sleep(300);
process.exit(fail ? 1 : 0);
