**What this changes, and why**

**How it was tested**

- [ ] `cyrius build` and `cyrius test` pass
- [ ] `./scripts/check-clean.sh` passes
- [ ] A new regression test fails without the fix
- [ ] A change to the serve path or the store also ran `scripts/boot-probe.sh` and `scripts/load-test.py`

**Docs**

- [ ] `CHANGELOG.md`, under `[Unreleased]`
- [ ] `docs/development/state.md`, and an ADR if the change earned one
- [ ] A change to the HTTP surface regenerated the API schema and updated `skills/agnostic/SKILL.md`

One change at a time. See [`CONTRIBUTING.md`](../CONTRIBUTING.md).
