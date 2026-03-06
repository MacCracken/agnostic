# Dependency Watch

This document tracks third-party dependencies that are currently blocking upgrades or require monitoring for compatibility changes. Update this file whenever a blocker is resolved or a new one is identified.

---

## Active Blockers

### crewai — Python 3.14 `requires-python` upper bound

| | |
|---|---|
| **Affected dep** | `crewai` (all 1.x releases through 1.10.1) |
| **Blocker for** | Python 3.14 dev environment |
| **Since** | 2026-02-22 |
| **Status** | Unresolved — every crewai 1.x release has `Requires-Python: >=3.10,<3.14` |

**Problem:** crewai's `pyproject.toml` sets `requires-python = ">=3.10,<3.14"`. pip refuses to install any 1.x release on Python 3.14, regardless of whether dependencies would work. This is the **primary** blocker — even if chromadb were fixed, crewai won't install.

**Why they set the bound:** crewai depends on chromadb, which uses `pydantic.v1.BaseSettings` (broken on 3.14). crewai PR [#2325](https://github.com/crewAIInc/crewAI/pull/2325) made chromadb optional, but the `requires-python` upper bound has not been relaxed in any release yet.

**Fix needed (upstream):** crewai must:
1. Ship a release where chromadb is truly optional (PR #2325 merged but not in a release that relaxes the Python bound)
2. Update `requires-python` to `>=3.10,<3.15` (or remove the upper bound)

**What to watch:**
- crewai releases: https://github.com/crewAIInc/crewAI/releases
- crewai issues/PRs mentioning "Python 3.14" or "requires-python"
- When a release allows `>=3.14`, test install + import in our dev venv

---

### chromadb — pydantic v1 broken on Python 3.14

| | |
|---|---|
| **Affected dep** | `chromadb` (1.1.1 latest, transitive via `crewai`) |
| **Blocker for** | Python 3.14 support (secondary — crewai's `requires-python` is the primary blocker) |
| **Since** | 2026-02-22 |
| **Status** | Unresolved — tracked in [chroma-core/chroma#5996](https://github.com/chroma-core/chroma/issues/5996) |

**Problem:** `chromadb/config.py` defines its `Settings` class by inheriting from `pydantic.v1.BaseSettings`. On Python 3.14 the `pydantic.v1` compatibility shim fails at class-definition time because `ForwardRef._evaluate` was removed, raising:

```
pydantic.v1.errors.ConfigError: unable to infer type for attribute "chroma_server_nofile"
```

**Why it blocks us:** If crewai relaxes its `requires-python` bound before chromadb is fixed, importing chromadb will still fail at runtime on Python 3.14. However, since we don't use chromadb directly and crewai PR #2325 makes it optional, this becomes a non-issue once crewai ships a release without the hard chromadb requirement.

**Note:** chromadb is currently installed in our dev venv but is orphaned — nothing in our code imports it and `pip show chromadb` shows no reverse dependencies. It can be safely uninstalled from dev environments.

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
- [chroma-core/chroma#5996](https://github.com/chroma-core/chroma/issues/5996) — Python 3.14 tracking issue
- chromadb releases: https://github.com/chroma-core/chroma/releases
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
| **Resolved in** | 2026-03-03 |
| **Status** | **Resolved** — moved to Resolved section below |

---

## Resolved

### chainlit 2.x upgrade — FastAPI conflict resolved

| | |
|---|---|
| **Resolved** | 2026-03-03 |
| **Resolved by** | Upgrading to chainlit 2.x (`>=2.0.0,<3.0.0`) which drops the `fastapi<0.113` restriction |

**Changes made:**
- `pyproject.toml`: `chainlit>=2.0.0,<3.0.0` (was `>=1.1.304,<2.0.0`); `fastapi>=0.116.1` (was `>=0.115.0`); `uvicorn>=0.35.0` (was `>=0.32.0`)
- `webgui/Dockerfile`: `CHAINLIT_SERVER_ROOT` renamed to `CHAINLIT_ROOT_PATH` (2.x canonical name)
- `webgui/app.py`: migrated deprecated `@app.on_event("startup"/"shutdown")` to `lifespan` async context manager (required by starlette >=0.47 pulled in by chainlit 2.x)

**Note:** Chainlit APIs used by this project (`@cl.on_chat_start`, `@cl.on_message`, `@cl.on_chat_end`, `cl.Message`, `cl.user_session`) are fully compatible with chainlit 2.x and required no code changes. Chainlit 2.x supports Python `>=3.10,<4.0.0`.

---

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

**Note:** crewai 1.x still requires `Python <3.14` (see active blocker above). The dev venv runs crewai 0.11.2 as the latest version pip can resolve on Python 3.14. Production Docker containers (Python 3.11) use crewai 1.x and are unaffected.

---

## How to update this file

1. **New blocker found**: Add an entry under "Active Blockers" with the affected dependency, what it blocks, the date discovered, and the exact error or constraint that causes the conflict.
2. **Blocker resolved upstream**: Move the entry to "Resolved", add the resolution date, the upstream version that fixed it, and the commit/PR in this repo that applied the fix.
3. **After any `pip install` failure on a new Python version**: Capture the error, identify the leaf package at fault (not just the top-level dep), and add or update the relevant entry here.
