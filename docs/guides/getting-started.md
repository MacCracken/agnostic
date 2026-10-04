# Getting started with agnostic

## Build

```sh
cyrius deps                              # resolve dependencies
cyrius build src/main.cyr build/agnostic    # compile
cyrius test                              # run [build].test + tests/*.tcyr
```

## Run it, and open the WebGUI

```sh
./build/agnostic        # binds 127.0.0.1:8000; AGNOSTIC_PORT / AGNOSTIC_ADDR change that
```

Then open `http://127.0.0.1:8000/ui`. Plugins such as Swarm Command start switched off — turn one on
in Settings; see [`webgui-plugins.md`](webgui-plugins.md).

To let a coding agent drive the API, see [`skills/agnostic/SKILL.md`](../../skills/agnostic/SKILL.md)
and the install note in the README's API section.

## Ask the binary for its API

```sh
./build/agnostic api schema   # the HTTP API as JSON; needs no configuration and opens nothing
./build/agnostic help         # the commands
```

The output is committed as [`../api/generated/schema.json`](../api/generated/schema.json); an API
change regenerates it with `./scripts/gen-api-schema.sh` (see [`../api/README.md`](../api/README.md)).

## Layout

- `src/main.cyr` — entry point. Top-level `var r = main(); sys_exit_group(r);`.
  Use `sys_exit_group`, not `syscall(SYS_EXIT, r)` — the latter is exit(2) and ends
  only the calling thread, so it hangs once the program spawns its first worker.
- `src/test.cyr` — top-level test entry referenced by `cyrius.cyml [build].test`. Add unit cases here or in `tests/agnostic.tcyr`.
- `tests/agnostic.tcyr` — primary test suite (`cyrius test` auto-discovers).
- `tests/agnostic.bcyr` — benchmarks (`cyrius bench`).
- `tests/agnostic.fcyr` — fuzz harness (`cyrius fuzz`).

## Adding a feature

1. Edit `src/main.cyr` (or add a new module and `include` it).
2. Add a test case to `tests/agnostic.tcyr`.
3. Run `cyrius test`.
4. Bump `VERSION` and add a CHANGELOG entry before tagging.

See [`../adr/template.md`](../adr/template.md) when a non-trivial design choice deserves an ADR.
