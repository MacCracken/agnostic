# Architecture notes

Non-obvious constraints, quirks, and invariants that a reader cannot derive from the code alone. Numbered chronologically — never renumber.

Not decisions (those live in [`../adr/`](../adr/)) and not guides (those live in [`../guides/`](../guides/)). An item here describes *how the world is*, not *what we chose* or *how to do something*.

## Items

| # | Item |
|---|---|
| [001](001-what-survives-a-restart.md) | What survives a restart — every kind of state, where it lives, and what the next start does with it; one agnostic process per database file |
| [002](002-the-dependency-pins.md) | The dependency pins — why the Cyrius pin and dep tags move together, why there is no `path` and no override pin, and why the root blocks are in this order |

Add the next as `003-kebab-case-title.md`. Do not write entries for decisions — those are ADRs.
