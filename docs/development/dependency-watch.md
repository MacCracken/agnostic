# Dependency Watch

This document tracks third-party dependencies that are currently blocking upgrades or require monitoring for compatibility changes. Resolved items are moved to the [Changelog](../project/changelog.md).

---

## Active Blockers

### crewai — Python 3.14 `requires-python` upper bound

| | |
|---|---|
| **Affected dep** | `crewai` (all releases through 1.10.1) |
| **Blocker for** | Python 3.14 dev environment |
| **Since** | 2026-02-22 |
| **Status** | Unresolved — `Requires-Python: >=3.10,<3.14` |

**Problem:** crewai sets `requires-python = ">=3.10,<3.14"`. pip refuses to install on Python 3.14. This is the sole remaining Python 3.14 blocker — chromadb 1.1.1 is now unblocked.

**Docker status:** Docker containers use Python 3.13 with crewai 1.10.1 and are unaffected.

**What to watch:**
- crewai releases: https://github.com/crewAIInc/crewAI/releases
- crewai issues/PRs mentioning "Python 3.14" or "requires-python"

---

## How to update this file

1. **New blocker found**: Add an entry under "Active Blockers" with the affected dependency, what it blocks, the date discovered, and the exact error or constraint that causes the conflict.
2. **Blocker resolved upstream**: Move the entry to the [Changelog](../project/changelog.md) under the appropriate version's "Dependency Updates" section.
3. **After any `pip install` failure on a new Python version**: Capture the error, identify the leaf package at fault, and add or update the relevant entry here.
