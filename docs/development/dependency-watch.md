# Dependency Watch

This document tracks third-party dependencies that are currently blocking upgrades or require monitoring for compatibility changes. Update this file whenever a blocker is resolved or a new one is identified.

---

## Active Blockers

### chromadb — Python 3.14 support

| | |
|---|---|
| **Affected dep** | `chromadb` (transitive via `crewai`) |
| **Blocker for** | Python 3.14 support |
| **Since** | 2026-02-22 |
| **Status** | Unresolved — chromadb 1.5.1 (latest) still affected |

**Problem:** `chromadb/config.py` defines its `Settings` class by inheriting from `pydantic.v1.BaseSettings`. On Python 3.14 the `pydantic.v1` compatibility shim fails at class-definition time because `ForwardRef._evaluate` was removed, raising:

```
pydantic.v1.errors.ConfigError: unable to infer type for attribute "chroma_server_nofile"
```

**Why it blocks us:** Every released crewai version (0.x through 1.x) depends on chromadb. The import fails before any agent code runs. Production containers use Python 3.11 where everything works.

**Fix needed (upstream):** `chromadb/config.py` must replace:
```python
# current (broken on 3.14)
from pydantic.v1 import BaseSettings, validator
```
with:
```python
# correct pydantic v2 native equivalent
from pydantic_settings import BaseSettings
from pydantic import field_validator
```

**What to watch:**
- chromadb releases: https://github.com/chroma-core/chroma/releases
- chromadb issue tracker for "pydantic v2" / "Python 3.14" labels
- When resolved, re-test `crewai` import on Python 3.14 and update `pyproject.toml`'s `requires-python` upper bound

---

### crewai / LangChain — API upgrade (0.11.x → 1.x)

| | |
|---|---|
| **Affected dep** | `crewai`, `langchain`, `langchain-openai`, `langchain-community` |
| **Resolved in** | 2026-02-28 |
| **Status** | **Resolved** — moved to Resolved section below |

---

### chainlit — FastAPI version conflict

| | |
|---|---|
| **Affected dep** | `chainlit`, `fastapi` |
| **Blocker for** | Installing `web` extras with `pip install -e .[web]` |
| **Since** | 2026-02-22 |
| **Status** | Unresolved |

**Problem:** `pyproject.toml` specifies `chainlit>=1.1.304,<2.0.0` and `fastapi>=0.115.0`. All chainlit 1.x releases require `fastapi<0.113`, making these constraints mutually exclusive. `pip install -e .[dev,test,web,ml,...]` fails with `ResolutionImpossible`.

**Workaround:** Install without the `web` extra for development (`pip install -e .[dev,test,ml,observability]`). The WebGUI tests mock FastAPI/Chainlit, so the test suite passes without them installed.

**Fix options:**
1. Upgrade to `chainlit>=2.0.0` (drops the fastapi<0.113 restriction) — requires testing for breaking changes in the Chainlit UI
2. Pin `fastapi<0.113` (downgrade) — loses newer FastAPI features used in `webgui/api.py`

**What to watch:**
- chainlit 2.x releases and changelog: https://github.com/Chainlit/chainlit/releases
- Confirm chainlit 2.x still supports Python 3.11 (production target)

---

## Resolved

### crewai 1.x migration — LangChain removed

| | |
|---|---|
| **Resolved** | 2026-02-28 |
| **Resolved by** | Migrating all agent and config code to crewai 1.x + litellm |

**Changes made:**
- `pyproject.toml`: `crewai>=1.0.0,<2.0.0`; removed `langchain`, `langchain-openai`, `langchain-community`; removed `numpy <2.0` cap
- `config/llm_integration.py`: replaced `ChatOpenAI` + `HumanMessage`/`SystemMessage` with `litellm.acompletion()`
- `config/universal_llm_adapter.py`: replaced `langchain.llms.base.LLM` subclass with `crewai.LLM` factory
- All 6 agent files: `from langchain_openai import ChatOpenAI` → `from crewai import LLM`; `ChatOpenAI(...)` → `LLM(...)`
- `agents/performance/qa_performance.py`: `from langchain.tools import BaseTool` → `from shared.crewai_compat import BaseTool`

**Note:** crewai 1.x still requires `Python <3.14`. The chromadb blocker above must resolve before Python 3.14 dev support is possible. Production Docker containers (Python 3.11) are unaffected.

---

## How to update this file

1. **New blocker found**: Add an entry under "Active Blockers" with the affected dependency, what it blocks, the date discovered, and the exact error or constraint that causes the conflict.
2. **Blocker resolved upstream**: Move the entry to "Resolved", add the resolution date, the upstream version that fixed it, and the commit/PR in this repo that applied the fix.
3. **After any `pip install` failure on a new Python version**: Capture the error, identify the leaf package at fault (not just the top-level dep), and add or update the relevant entry here.
