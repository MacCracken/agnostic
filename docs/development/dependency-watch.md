# Dependency Watch

This document tracks third-party dependencies that are currently blocking upgrades or require monitoring for compatibility changes. Update this file whenever a blocker is resolved or a new one is identified.

---

## Active Blockers

### crewai — Python 3.14 `requires-python` upper bound

| | |
|---|---|
| **Affected dep** | `crewai` (all releases through 1.10.1) |
| **Blocker for** | Python 3.14 dev environment |
| **Since** | 2026-02-22 |
| **Status** | Unresolved — `Requires-Python: >=3.10,<3.14` |

**Problem:** crewai sets `requires-python = ">=3.10,<3.14"`. pip refuses to install on Python 3.14. The dev venv (Python 3.14.2) has crewai 0.11.2 force-installed but it fails at import time due to pydantic v1 incompatibility in its chromadb dependency.

**Docker status:** Docker containers use Python 3.13 with crewai 1.10.1 and are unaffected by this blocker.

**What to watch:**
- crewai releases: https://github.com/crewAIInc/crewAI/releases
- crewai issues/PRs mentioning "Python 3.14" or "requires-python"

---

### chromadb — pydantic v1 broken on Python 3.14

| | |
|---|---|
| **Affected dep** | `chromadb` (1.1.1 latest, transitive via `crewai`) |
| **Blocker for** | Python 3.14 support (secondary — crewai's `requires-python` is the primary blocker) |
| **Since** | 2026-02-22 |
| **Status** | Unresolved — tracked in [chroma-core/chroma#5996](https://github.com/chroma-core/chroma/issues/5996) |

**Problem:** `chromadb/config.py` inherits from `pydantic.v1.BaseSettings`. On Python 3.14 the `pydantic.v1` compatibility shim fails because `ForwardRef._evaluate` was removed.

**Note:** chromadb is installed in our dev venv but is orphaned — nothing in our code imports it. It can be safely uninstalled from dev environments.

**What to watch:**
- [chroma-core/chroma#5996](https://github.com/chroma-core/chroma/issues/5996)
- chromadb releases: https://github.com/chroma-core/chroma/releases

---

## Resolved

### Agent code — import / runtime errors fixed

| | |
|---|---|
| **Resolved** | 2026-03-07 |
| **Resolved by** | Adding `llm_service` singleton, pytest to Docker deps, ClassVar annotations, Faker property pattern |

**Changes made:**
- `config/llm_integration.py`: added `llm_service = LLMIntegrationService()` singleton
- `requirements-docker.txt`: added `pytest` and `Faker` (used at runtime by junior QA agent)
- `Dockerfile`: single image includes all code (agents, config, shared, webgui)
- Agent BaseTool subclasses: added `ClassVar` annotations for class-level attributes (pydantic v2 requirement)
- `SyntheticDataGeneratorTool`: converted `faker` from instance attribute to lazy ClassVar + property

---

### crewai 1.10.1 available on PyPI — Docker upgraded

| | |
|---|---|
| **Resolved** | 2026-03-07 |
| **Resolved by** | Upgrading Docker containers to `crewai[litellm]==1.10.1` on Python 3.13 |

**Problem:** crewai had confusing version history on PyPI — versions appeared to reset. The agent code was written for a version that exported `crewai.LLM`, which wasn't in the 0.11.x releases visible to Python 3.14.

**Resolution:** crewai 1.10.1 exists on PyPI with `Requires-Python: >=3.10,<3.14`. Docker containers now use Python 3.13 where it installs cleanly. crewai 1.10.1 has dropped langchain entirely and uses direct openai/litellm, eliminating the tiktoken version conflict.

**Changes made:**
- `Dockerfile`: `FROM python:3.13-slim` (was `python:3.11-slim`)
- `requirements-docker.txt`: `crewai[litellm]==1.10.1`; removed langchain stack; uses minimum version pins instead of exact pins to avoid transitive conflicts
- Removed `--no-deps` litellm workaround (no longer needed)

---

### Docker dependency split — requirements-docker.txt

| | |
|---|---|
| **Resolved** | 2026-03-07 |
| **Resolved by** | Creating `requirements-docker.txt` with runtime-only deps |

**Problem:** `requirements.txt` was generated from a Python 3.14 venv via `pip freeze`. It included dev/test/lint tools (`bandit`, `safety`, `mypy`, `ruff`, `pytest`, etc.) that caused cascading version conflicts on the Docker Python version.

**Changes made:**
- Created `requirements-docker.txt` — runtime deps only, minimum version pins
- `Dockerfile`: installs from `requirements-docker.txt` instead of `requirements.txt`

---

### Docker base image — Python 3.11 → 3.13

| | |
|---|---|
| **Resolved** | 2026-03-07 |
| **Resolved by** | Updating `Dockerfile` to `python:3.13-slim` |

**Changes made:**
- `Dockerfile`: `FROM python:3.13-slim` (consolidated from multiple Dockerfiles)
- `requirements-docker.txt`: added `audioop-lts>=0.2.0` (audioop removed from stdlib in 3.13)
- `.github/workflows/release.yml`: GHCR login + push steps with lowercase owner enforcement

---

### litellm / crewai — tiktoken version conflict

| | |
|---|---|
| **Resolved** | 2026-03-07 |
| **Resolved by** | Upgrading to crewai 1.10.1 which dropped langchain |

**Problem:** `crewai==0.11.2` → `langchain-openai>=0.0.5,<0.0.6` → `tiktoken<0.6.0`, but `litellm>=1.74.9` required `tiktoken>=0.7.0`.

**Resolution:** crewai 1.10.1 no longer depends on langchain or langchain-openai. tiktoken is only an optional dep (`crewai[embeddings]`). Conflict eliminated.

---

### chainlit 2.x upgrade — FastAPI conflict resolved

| | |
|---|---|
| **Resolved** | 2026-03-03 |
| **Resolved by** | Upgrading to chainlit 2.x (`>=2.0.0,<3.0.0`) which drops the `fastapi<0.113` restriction |

**Changes made:**
- `pyproject.toml`: `chainlit>=2.0.0,<3.0.0` (was `>=1.1.304,<2.0.0`); `fastapi>=0.116.1` (was `>=0.115.0`); `uvicorn>=0.35.0` (was `>=0.32.0`)
- `Dockerfile`: `CHAINLIT_ROOT_PATH` env var set (chainlit 2.x canonical name)
- `webgui/app.py`: migrated deprecated `@app.on_event("startup"/"shutdown")` to `lifespan` async context manager (required by starlette >=0.47 pulled in by chainlit 2.x)

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

---

## How to update this file

1. **New blocker found**: Add an entry under "Active Blockers" with the affected dependency, what it blocks, the date discovered, and the exact error or constraint that causes the conflict.
2. **Blocker resolved upstream**: Move the entry to "Resolved", add the resolution date, the upstream version that fixed it, and the commit/PR in this repo that applied the fix.
3. **After any `pip install` failure on a new Python version**: Capture the error, identify the leaf package at fault (not just the top-level dep), and add or update the relevant entry here.
