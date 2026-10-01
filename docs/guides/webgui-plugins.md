# WebGUI plugins — switching one on, and adding one

The WebGUI is served at **`/ui`** (`http://127.0.0.1:8000/ui` on the default bind). It has an
Overview, a tab for each plugin that is switched on, and Settings. Why plugins are compiled in rather
than loaded is [ADR 0004](../adr/0004-webgui-plugins-compiled-in-switched-at-run-time.md).

## Switch a plugin on

Every plugin starts **off**. Switching one needs the **admin** role, applies to the whole
deployment, survives a restart, and is recorded in the audit trail.

- **From the WebGUI:** Settings → Plugins → flip the switch. With `AGNOSTIC_AUTH=required` the shell
  asks you to sign in first.
- **From the API:**

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" -d '{"enabled": true}' http://127.0.0.1:8000/api/v1/plugins/swarm
```

`GET /api/v1/plugins` lists every plugin with its state. A switched-off plugin's page,
`/ui/plugins/<id>`, answers 404.

⚠ **Read the `data` field.** `"simulated"` means the view runs on its own simulator and shows no real
crew activity; the shell badges it SIMULATED. Swarm Command is simulated today.

## Add a plugin

1. **Create `src/webgui/plugins/<id>/`.** The id is `[a-z0-9][a-z0-9-]*`, at most 32 characters,
   and is also the directory name.
2. **Write `plugin.json`** with exactly these keys — an unknown or missing key fails the generator:

   ```json
   {
     "id": "my-view",
     "name": "My View",
     "description": "What it shows, in a sentence or two.",
     "version": "0.1.0",
     "data": "simulated",
     "entry": "index.html"
   }
   ```

   `data` is `simulated` or `live`. Say `live` only when every number on screen comes from this
   server.
3. **Write `index.html`: one self-contained page.** The generator refuses a page that its CSP would
   break, so these are build errors, not browser surprises:
   - no external scripts, stylesheets, images or fonts — inline everything (`default-src 'none'`);
   - no inline event handlers (`onclick=`) and no `javascript:` URLs — use `addEventListener`;
     inline `<script>` blocks are fine, and are admitted by hash;
   - LF line endings, and no NUL bytes;
   - no line that starts with `fn`, `var`, `enum`, `struct` or `include` at column 0 — the gates
     that scan `src/` read such a line as a Cyrius definition. Indent it.
4. **Add the id to `PLUGINS` in `scripts/gen-webgui.sh`.** The list is the order plugins are listed
   and tabbed in; a directory missing from it fails the generator.
5. **Regenerate, build, test:**

```bash
./scripts/gen-webgui.sh && cyrius build src/main.cyr build/agnostic && cyrius test
```

## What a plugin page can and cannot do

The shell frames a plugin in `<iframe sandbox="allow-scripts allow-downloads">`. The page runs in an
**opaque origin**, so:

- it **can** run scripts, draw, take keyboard and mouse input, and save files the user downloads;
- it **cannot** read the shell's session token, call the API as the signed-in user, or reach the
  shell's DOM — `localStorage` and `sessionStorage` throw, so wrap them in `try`/`catch`;
- opened directly at `/ui/plugins/<id>` (the shell's "Open in a new tab"), it runs unsandboxed, under
  its CSP, in a tab holding no session: the link is `noopener`, so the shell's `sessionStorage` —
  where its token lives — is not copied into it.

A plugin that needs live data from this server cannot fetch it itself; the shell would have to pass
it in. That bridge does not exist yet — see ADR 0004.
