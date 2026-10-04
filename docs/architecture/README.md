# Architecture notes

Non-obvious constraints, quirks, and invariants that a reader cannot derive from the code alone. Numbered chronologically — never renumber.

Not decisions (those live in [`../adr/`](../adr/)) and not guides (those live in [`../guides/`](../guides/)). An item here describes *how the world is*, not *what we chose* or *how to do something*.

## Items

| # | Item |
|---|---|
| [001](001-what-survives-a-restart.md) | What survives a restart — every kind of state, where it lives, and what the next start does with it; one agnostic process per database file |

Add the next as `002-kebab-case-title.md`. Do not write entries for decisions — those are ADRs.
