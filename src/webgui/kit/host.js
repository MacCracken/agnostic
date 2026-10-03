/* agnostic-kit:host begin — DO NOT EDIT A COPY: the canonical source is src/webgui/kit/host.js,
 * and scripts/gen-webgui.sh refuses a plugin page whose copy differs (`--sync-kit` rewrites them).
 *
 *  Host — the plugin side of agnostic's host bridge (ADR 0005, 0007, 0010).
 *
 *  Framed by the agnostic shell, a plugin page runs in an opaque origin with connect-src 'none': it
 *  cannot reach the API. It asks the shell by postMessage, and the shell answers only what this
 *  plugin's manifest permits, with the signed-in user's own credential (which the page never sees)
 *  — and the server checks the same permissions, and that user's role, again. Protocol 1:
 *
 *     page  → shell   {type:'agnostic:hello', protocol}
 *     shell → page    {type:'agnostic:init', protocol, features[], plugin:{id,name,version},
 *                      permissions[], user:{auth, signedIn, role}, params, views[{id,name}]}
 *     page  → shell   {type:'agnostic:request', id, method, path, body?, ifMatch?, ifNoneMatch?,
 *                      idempotencyKey?}
 *     shell → page    {type:'agnostic:response', id, status, data, etag?}  status 0 = never reached it
 *     page  → shell   {type:'agnostic:navigate', to, params?}             open another view (0.1.10)
 *     shell → page    {type:'agnostic:params', params}                    this view's params changed
 *
 *  The shell re-sends init after a sign-in or sign-out. `params` is the part of the shell's URL after
 *  `#plugin/<id>?` — a deep link into this view, e.g. `crew=<uuid>`. `views` lists the views switched
 *  on, so a page offers a link only to one that will open. Opened on its own (a new tab) there is no
 *  shell: `mode` is 'standalone', and the page must degrade.
 */
class Host {
  constructor({ helloMs = 3000, timeoutMs = 30000 } = {}) {
    this.mode = 'connecting';  // 'connecting' | 'connected' | 'standalone'
    this.info = null;          // the latest agnostic:init
    this.params = '';          // this view's params, from init or agnostic:params
    this.pending = new Map();  // request id → {resolve, timer}
    this.seq = 0;
    this.timeoutMs = timeoutMs;
    // A random prefix per page load: request ids restart with every load, and a reply the shell
    // sends after a reload must never match a request of this page that happens to share a number.
    this.prefix = 'q' + Host.token(6) + '-';
    this.listeners = new Set();
    this.paramListeners = new Set();
    let framed = false;
    try { framed = window.parent !== window; } catch (err) { framed = true; }
    if (!framed) { this.mode = 'standalone'; return; }
    window.addEventListener('message', (e) => this.onMessage(e));
    try { window.parent.postMessage({ type: 'agnostic:hello', protocol: 1 }, '*'); } catch (err) { /* detached */ }
    // A parent that never answers is not the agnostic shell (or is an older one): stand alone.
    this.timer = setTimeout(() => { if (this.mode === 'connecting') this.setMode('standalone'); }, helloMs);
  }
  /** `n` random characters of [a-z0-9]. */
  static token(n) {
    const b = new Uint8Array(n);
    try { crypto.getRandomValues(b); } catch (err) { for (let i = 0; i < n; i++) b[i] = Math.floor(Math.random() * 256); }
    let s = '';
    for (const x of b) s += (x % 36).toString(36);
    return s;
  }
  onMessage(e) {
    if (e.source !== window.parent) return;
    const m = e.data;
    if (!m || typeof m !== 'object' || typeof m.type !== 'string') return;
    if (m.type === 'agnostic:init') {
      const u = m.user && typeof m.user === 'object' ? m.user : {};
      this.info = {
        plugin: m.plugin && typeof m.plugin === 'object' ? m.plugin : {},
        permissions: Array.isArray(m.permissions) ? m.permissions.filter((x) => typeof x === 'string') : [],
        features: Array.isArray(m.features) ? m.features.filter((x) => typeof x === 'string') : [],
        user: { auth: typeof u.auth === 'string' ? u.auth : 'unknown', signedIn: !!u.signedIn, role: typeof u.role === 'string' ? u.role : null },
        views: Array.isArray(m.views) ? m.views.filter((v) => v && typeof v.id === 'string' && typeof v.name === 'string') : [],
      };
      clearTimeout(this.timer);
      const params = typeof m.params === 'string' ? m.params : '';
      const changed = params !== this.params;
      this.params = params;
      this.setMode('connected');
      if (changed) this.emitParams();
    } else if (m.type === 'agnostic:params') {
      this.params = typeof m.params === 'string' ? m.params : '';
      this.emitParams();
    } else if (m.type === 'agnostic:response') {
      const r = this.pending.get(m.id);
      if (!r) return;
      this.pending.delete(m.id);
      clearTimeout(r.timer);
      r.resolve({ status: Number.isInteger(m.status) ? m.status : 0, data: m.data === undefined ? null : m.data, etag: typeof m.etag === 'string' ? m.etag : null });
    }
  }
  setMode(mode) { this.mode = mode; for (const fn of this.listeners) fn(this); }
  /** Called on every init (and the fall back to standalone); returns an unsubscribe. */
  onChange(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  /** Called when this view's params change — a deep link followed while it is open. */
  onParams(fn) { this.paramListeners.add(fn); return () => this.paramListeners.delete(fn); }
  emitParams() { for (const fn of this.paramListeners) fn(this.params); }
  /** One param of this view: `param('crew')` for `crew=<uuid>`; '' when absent. */
  param(name) {
    for (const pair of this.params.split('&')) {
      const i = pair.indexOf('=');
      const k = i < 0 ? pair : pair.slice(0, i);
      if (k === name) { try { return decodeURIComponent(i < 0 ? '' : pair.slice(i + 1)); } catch (err) { return ''; } }
    }
    return '';
  }
  can(permission) { return this.mode === 'connected' && this.info.permissions.includes(permission); }
  /** Whether the shell's bridge carries `feature` ('query' | 'revisions' | 'idempotency' | 'navigate'). */
  has(feature) { return this.mode === 'connected' && this.info.features.includes(feature); }
  pluginId() { return (this.info && typeof this.info.plugin.id === 'string' && this.info.plugin.id) || ''; }
  /** The user's role when the server enforces roles; null when auth is off or unknown. */
  role() { return this.info && this.info.user.auth === 'required' ? this.info.user.role : null; }
  /** Whether the user may write at all: any role but viewer. */
  mayWrite() { return this.mode === 'connected' && this.role() !== 'viewer'; }
  /** Whether view `id` is switched on — so a link to it will open. */
  hasView(id) { return this.mode === 'connected' && this.info.views.some((v) => v.id === id); }
  /** Open another view (or 'overview' / 'settings'), with params for it. Resolves false when it cannot. */
  navigate(to, params) {
    if (!this.has('navigate')) return false;
    try { window.parent.postMessage({ type: 'agnostic:navigate', to: String(to), params: params ? String(params) : '' }, '*'); } catch (err) { return false; }
    return true;
  }
  /** `opts`: {ifMatch, ifNoneMatch, idempotencyKey}, each sent only when the shell carries it. */
  request(method, path, body, opts) {
    if (this.mode !== 'connected') return Promise.resolve({ status: 0, data: { error: 'not connected to agnostic' }, etag: null });
    const id = this.prefix + ++this.seq;
    return new Promise((resolve) => {
      const timer = setTimeout(() => { if (this.pending.delete(id)) resolve({ status: 0, data: { error: 'the shell did not answer' }, etag: null }); }, this.timeoutMs);
      this.pending.set(id, { resolve, timer });
      const msg = { type: 'agnostic:request', id, method, path };
      if (body !== undefined) msg.body = body;
      const o = opts || {};
      if (o.ifMatch && this.has('revisions')) msg.ifMatch = o.ifMatch;
      if (o.ifNoneMatch && this.has('revisions')) msg.ifNoneMatch = o.ifNoneMatch;
      if (o.idempotencyKey && this.has('idempotency')) msg.idempotencyKey = o.idempotencyKey;
      try { window.parent.postMessage(msg, '*'); } catch (err) { this.pending.delete(id); clearTimeout(timer); resolve({ status: 0, data: { error: 'the shell is gone' }, etag: null }); }
    });
  }
}
/** The error text of a bridge response. */
function errOf(r) {
  if (r && r.data && typeof r.data.error === 'string') return r.data.error;
  return r && r.status ? 'HTTP ' + r.status : 'the server is unreachable';
}
/* agnostic-kit:host end */
