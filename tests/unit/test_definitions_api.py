"""Unit tests for agent definition and preset management API (Phase 2)."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not available", allow_module_level=True)

try:
    from webgui.api import api_router, get_current_user
except ImportError:
    pytest.skip("webgui.api module not available", allow_module_level=True)

from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    test_app = FastAPI()
    test_app.include_router(api_router)
    return test_app


@pytest.fixture()
def admin_user():
    return {
        "user_id": "admin-1",
        "email": "admin@example.com",
        "role": "super_admin",
        "permissions": ["sessions:read", "sessions:write", "system:configure"],
    }


@pytest.fixture()
def regular_user():
    return {
        "user_id": "user-1",
        "email": "user@example.com",
        "role": "qa_engineer",
        "permissions": ["sessions:read"],
    }


@pytest.fixture()
def admin_client(app, admin_user):
    async def override():
        return admin_user

    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def user_client(app, regular_user):
    async def override():
        return regular_user

    app.dependency_overrides[get_current_user] = override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def tmp_definitions(tmp_path, monkeypatch):
    """Redirect definitions and presets dirs to tmp_path."""
    import webgui.routes.definitions as defs_mod

    defs_dir = tmp_path / "definitions"
    presets_dir = defs_dir / "presets"
    defs_dir.mkdir()
    presets_dir.mkdir()

    monkeypatch.setattr(defs_mod, "DEFINITIONS_DIR", defs_dir)
    monkeypatch.setattr(defs_mod, "PRESETS_DIR", presets_dir)
    return {"definitions": defs_dir, "presets": presets_dir}


SAMPLE_DEFINITION = {
    "agent_key": "test-agent",
    "name": "Test Agent",
    "role": "Tester",
    "goal": "Test things well",
    "backstory": "A thorough tester with many years of experience.",
    "domain": "testing",
    "focus": "Unit testing",
}


# ---------------------------------------------------------------------------
# Definition CRUD tests
# ---------------------------------------------------------------------------


class TestDefinitionCRUD:
    def test_list_empty(self, admin_client, tmp_definitions):
        resp = admin_client.get("/api/v1/definitions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_definition(self, admin_client, tmp_definitions):
        resp = admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_key"] == "test-agent"
        assert data["domain"] == "testing"

        # File was created
        path = tmp_definitions["definitions"] / "test-agent.json"
        assert path.exists()

    def test_create_duplicate_returns_409(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        resp = admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        assert resp.status_code == 409

    def test_get_definition(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        resp = admin_client.get("/api/v1/definitions/test-agent")
        assert resp.status_code == 200
        assert resp.json()["agent_key"] == "test-agent"

    def test_get_definition_not_found(self, admin_client, tmp_definitions):
        resp = admin_client.get("/api/v1/definitions/nonexistent")
        assert resp.status_code == 404

    def test_update_definition(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        updated = {**SAMPLE_DEFINITION, "focus": "Integration testing"}
        resp = admin_client.put("/api/v1/definitions/test-agent", json=updated)
        assert resp.status_code == 200
        assert resp.json()["focus"] == "Integration testing"

    def test_update_key_mismatch(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        updated = {**SAMPLE_DEFINITION, "agent_key": "different-key"}
        resp = admin_client.put("/api/v1/definitions/test-agent", json=updated)
        assert resp.status_code == 400

    def test_update_not_found(self, admin_client, tmp_definitions):
        missing = {**SAMPLE_DEFINITION, "agent_key": "nonexistent"}
        resp = admin_client.put("/api/v1/definitions/nonexistent", json=missing)
        assert resp.status_code == 404

    def test_delete_definition(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        resp = admin_client.delete("/api/v1/definitions/test-agent")
        assert resp.status_code == 204

        # File is gone
        path = tmp_definitions["definitions"] / "test-agent.json"
        assert not path.exists()

    def test_delete_not_found(self, admin_client, tmp_definitions):
        resp = admin_client.delete("/api/v1/definitions/nonexistent")
        assert resp.status_code == 404

    def test_list_with_domain_filter(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        other = {**SAMPLE_DEFINITION, "agent_key": "other-agent", "domain": "devops"}
        admin_client.post("/api/v1/definitions", json=other)

        resp = admin_client.get("/api/v1/definitions?domain=testing")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["agent_key"] == "test-agent"

    def test_list_pagination(self, admin_client, tmp_definitions):
        for i in range(5):
            d = {**SAMPLE_DEFINITION, "agent_key": f"agent-{i:02d}"}
            admin_client.post("/api/v1/definitions", json=d)

        resp = admin_client.get("/api/v1/definitions?limit=2&offset=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_non_admin_cannot_create(self, user_client, tmp_definitions):
        resp = user_client.post("/api/v1/definitions", json=SAMPLE_DEFINITION)
        assert resp.status_code == 403

    def test_non_admin_can_list(self, user_client, tmp_definitions):
        resp = user_client.get("/api/v1/definitions")
        assert resp.status_code == 200

    def test_non_admin_cannot_delete(self, user_client, tmp_definitions):
        resp = user_client.delete("/api/v1/definitions/test-agent")
        assert resp.status_code == 403

    def test_invalid_agent_key_rejected(self, admin_client, tmp_definitions):
        bad = {**SAMPLE_DEFINITION, "agent_key": "UPPER_CASE"}
        resp = admin_client.post("/api/v1/definitions", json=bad)
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Preset management tests
# ---------------------------------------------------------------------------


SAMPLE_PRESET_AGENTS = [
    {
        "agent_key": "lead",
        "name": "Lead",
        "role": "Leader",
        "goal": "Lead the team",
        "backstory": "An experienced leader.",
    },
    {
        "agent_key": "worker",
        "name": "Worker",
        "role": "Executor",
        "goal": "Execute tasks",
        "backstory": "A diligent worker.",
    },
]


class TestPresetManagement:
    def test_list_presets_empty(self, admin_client, tmp_definitions):
        resp = admin_client.get("/api/v1/presets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_preset(self, admin_client, tmp_definitions):
        resp = admin_client.post("/api/v1/presets", json={
            "name": "my-crew",
            "description": "Test crew",
            "domain": "testing",
            "agents": SAMPLE_PRESET_AGENTS,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my-crew"
        assert data["agent_count"] == 2

    def test_create_preset_duplicate(self, admin_client, tmp_definitions):
        payload = {
            "name": "my-crew",
            "description": "Test crew",
            "domain": "testing",
            "agents": SAMPLE_PRESET_AGENTS,
        }
        admin_client.post("/api/v1/presets", json=payload)
        resp = admin_client.post("/api/v1/presets", json=payload)
        assert resp.status_code == 409

    def test_get_preset(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/presets", json={
            "name": "my-crew",
            "description": "Test crew",
            "domain": "testing",
            "agents": SAMPLE_PRESET_AGENTS,
        })
        resp = admin_client.get("/api/v1/presets/my-crew")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_count"] == 2
        assert len(data["agents"]) == 2

    def test_get_preset_not_found(self, admin_client, tmp_definitions):
        resp = admin_client.get("/api/v1/presets/nonexistent")
        assert resp.status_code == 404

    def test_delete_preset(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/presets", json={
            "name": "my-crew",
            "description": "Test crew",
            "domain": "testing",
            "agents": SAMPLE_PRESET_AGENTS,
        })
        resp = admin_client.delete("/api/v1/presets/my-crew")
        assert resp.status_code == 204

    def test_delete_builtin_preset_blocked(self, admin_client, tmp_definitions):
        # Create a quality-standard preset to make it exist
        (tmp_definitions["presets"] / "quality-standard.json").write_text(json.dumps({
            "name": "quality-standard",
            "description": "QA",
            "domain": "quality",
            "agents": SAMPLE_PRESET_AGENTS,
        }))
        resp = admin_client.delete("/api/v1/presets/quality-standard")
        assert resp.status_code == 403

    def test_list_presets_with_domain_filter(self, admin_client, tmp_definitions):
        admin_client.post("/api/v1/presets", json={
            "name": "crew-a",
            "description": "A",
            "domain": "quality",
            "agents": SAMPLE_PRESET_AGENTS,
        })
        admin_client.post("/api/v1/presets", json={
            "name": "crew-b",
            "description": "B",
            "domain": "devops",
            "agents": SAMPLE_PRESET_AGENTS,
        })

        resp = admin_client.get("/api/v1/presets?domain=quality")
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "crew-a"

    def test_non_admin_cannot_create_preset(self, user_client, tmp_definitions):
        resp = user_client.post("/api/v1/presets", json={
            "name": "my-crew",
            "description": "Test",
            "domain": "testing",
            "agents": SAMPLE_PRESET_AGENTS,
        })
        assert resp.status_code == 403

    def test_non_admin_can_list_presets(self, user_client, tmp_definitions):
        resp = user_client.get("/api/v1/presets")
        assert resp.status_code == 200

    def test_preset_requires_at_least_one_agent(self, admin_client, tmp_definitions):
        resp = admin_client.post("/api/v1/presets", json={
            "name": "empty-crew",
            "description": "Empty",
            "domain": "testing",
            "agents": [],
        })
        assert resp.status_code == 422
