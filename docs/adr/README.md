# Architecture Decision Records

Decisions about agnostic — what we chose, the context, and the consequences we accept. Use these when a future reader would reasonably ask *"why did we do it this way?"*

## Conventions

- **Filename**: `NNNN-kebab-case-title.md`, zero-padded to four digits. Never renumber.
- **One decision per ADR.** If a decision supersedes a prior one, add a new ADR and set the old one's status to `Superseded by NNNN`.
- **Status lifecycle**: `Proposed` → `Accepted` → (optionally) `Superseded` or `Deprecated`.
- Use [`template.md`](template.md) as the starting point.

## ADR vs. architecture note vs. guide

| Kind | Lives in | Answers |
|---|---|---|
| ADR | `docs/adr/` | *Why did we choose X over Y?* |
| Architecture note | `docs/architecture/` | *What non-obvious constraint is true about the code?* |
| Guide | `docs/guides/` | *How do I do X?* |

## Index

| ADR | Decision |
|---|---|
| [0001](0001-health-and-readiness-are-separate.md) | Health and readiness are separate probes |
| [0002](0002-daimon-tier-1-deferred.md) | Daimon Tier 1 registration is deferred |
| [0003](0003-one-store-lock-not-a-handle-per-worker.md) | One store lock, not a patra handle per worker |
