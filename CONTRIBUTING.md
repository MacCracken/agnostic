# Contributing to Agnostic

## Getting Started

⚠ **Agnostic is a Cyrius project.** There is no `pyproject.toml` build path and
no `Makefile` — the Python tree is frozen at `python-port/` as the behavioural
oracle and is never built or shipped. Do not run `pip install`, `pytest`, or
anything under `python-port/` expecting it to produce the product.

⚠ **`python-port/` is a reference, not a spec.** `ORACLE-AUDIT.md` records 85
verified defects in it. Check that document before porting any behaviour — several
of the oracle's paths are wrong, and reproducing them faithfully would reproduce
the bugs.

```bash
git clone https://github.com/maccracken/agnostic.git
cd agnostic

# 1. Provision the pinned stdlib snapshot. `cyrius deps` only OVERLAYS
#    [deps.NAME] on top of lib/ — against an empty lib/ it fails.
cyrius lib sync --full

# 2. Resolve the git dependencies
cyrius deps

# 3. Build — produces build/agnostic
cyrius build src/main.cyr build/agnostic

# 4. Every test suite, recursively
cyrius tests tests

# 5. Benchmarks and the coverage gate (its own CI step)
cyrius bench
cyrius coverage --min 80

# 6. Everything else CI runs
./scripts/check-clean.sh && ./scripts/check-symbols.sh
```

⚠ **`check-clean.sh` does not compile `tests/` or `benches/`.** It can be green
while a suite fails to build, which has happened. Before opening a PR, confirm
every unit compiles:

```bash
for f in tests/*.tcyr benches/*.bcyr fuzz/*.fcyr; do
    cyrius build "$f" /tmp/cb >/dev/null || echo "FAIL: $f"
done
```

## Project Structure

`src/` mirrors the oracle where a module survives the port — `foo/bar.py` becomes
`foo/bar.cyr` — so a reader can check any module against `python-port/`. Two
things break the mirror deliberately:

- **Most of the oracle does not survive.** AgnosAI owns the engine tier (crews,
  tasks, agents, scheduling, LLM routing, fleet, tools, sandboxing), so the
  corresponding `python-port/` modules have no counterpart here. See
  `CYRIUS-PORT-BRIEF.md` for the three-way split of what is ported, what is
  delegated to a dependency, and what is dropped.
- **Python package layout is not Cyrius layout.** Cyrius has one flat symbol
  namespace, so directory nesting carries no scoping — it is organisational only.

The module tree is recorded in `docs/architecture/` and
`docs/development/state.md` as each milestone lands, rather than being fixed up
front. The roadmap holds only open work; what shipped is in `CHANGELOG.md`.

## Development Guidelines

### Code Style

- `cyrius fmt <file> --check` before committing — including `tests/*.tcyr`,
  which `check-clean.sh` does not reach
- `cyrius lint <file>` must be clean. ⚠ It takes a FILE; bare, it prints usage
  and exits 1, so a gate written without one lints nothing
- `cyrius vet src/main.cyr` and `cyrius deny src/main.cyr` must pass
- **Prefix every public symbol `agnostic_*`.** Cyrius has ONE flat namespace and
  last-definition-wins; `_`-prefix genuine internals so they leave the coverage
  denominator
- **Thread the `_a` allocator variants** on anything request-reachable; the bare
  form allocates on a process-wide no-free bump
- Every public function needs a doc comment — `cyrius doc --check` enforces it,
  and it must sit immediately above the `fn`

### Testing

- Suites are `tests/*.tcyr` and may `include "src/foo.cyr"` directly
- ⚠ Never end a `.tcyr` with the stock epilogue — the exit code is masked
  `& 0xFF`, so exactly 256/512/768 failures score PASS. Use:
  `var f = main(); if (f > 0) { f = 1; } syscall(60, f);`
- ⚠ Do NOT `include` a stdlib module in a `.tcyr`/`.bcyr` — the stdlib is
  auto-prepended, so an explicit include lands after it and single-passes into
  an undefined-symbol error
- **Mutation-verify anything that matters**: apply the mutation, re-run, name the
  assertion that failed, restore. A test that stays green under the mutation is
  not covering the thing you think it is

### Commit Messages

Use conventional commits:

```
feat(tools): add OWASP compliance scanner
fix(mcp): return the crew id on submit, not the local uuid
refactor(api): fold the two crew-status paths into one
test(reports): cover the quality-trend aggregation
docs: drop the shipped M6 items from the roadmap
```

## Reporting Issues

Open an issue with:
- What you expected
- What happened
- Minimal reproduction steps
- Toolchain version (`cyrius --version`, which also prints the manifest pin and any drift)

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting. Do not open public
issues for security vulnerabilities.
