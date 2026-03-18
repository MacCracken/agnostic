"""Tests for agent packaging (.agpkg), definition versioning, inter-crew delegation,
and custom tool upload."""

import json
import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Packaging tests
# ---------------------------------------------------------------------------


class TestPackaging:
    def test_export_and_import_roundtrip(self, tmp_path, monkeypatch):
        import agents.packaging as pkg

        defs_dir = tmp_path / "definitions"
        presets_dir = defs_dir / "presets"
        defs_dir.mkdir()
        presets_dir.mkdir()
        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(pkg, "PRESETS_DIR", presets_dir)

        # Create a definition and a preset
        (defs_dir / "my-agent.json").write_text(
            json.dumps(
                {
                    "agent_key": "my-agent",
                    "name": "My Agent",
                    "role": "R",
                    "goal": "G",
                    "backstory": "B",
                }
            )
        )
        (presets_dir / "my-preset.json").write_text(
            json.dumps(
                {
                    "name": "my-preset",
                    "description": "Test",
                    "domain": "testing",
                    "agents": [],
                }
            )
        )

        # Export
        data = pkg.export_package(
            "test-pkg",
            definition_keys=["my-agent"],
            preset_names=["my-preset"],
            version="2.0.0",
            description="Test package",
        )
        assert len(data) > 0

        # Verify ZIP contents
        with zipfile.ZipFile(BytesIO(data)) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "definitions/my-agent.json" in names
            assert "presets/my-preset.json" in names

            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["name"] == "test-pkg"
            assert manifest["version"] == "2.0.0"

        # Clear and reimport
        (defs_dir / "my-agent.json").unlink()
        (presets_dir / "my-preset.json").unlink()

        result = pkg.import_package(data)
        assert "my-agent" in result["definitions_installed"]
        assert "my-preset" in result["presets_installed"]
        assert (defs_dir / "my-agent.json").exists()
        assert (presets_dir / "my-preset.json").exists()

    def test_import_skips_existing(self, tmp_path, monkeypatch):
        import agents.packaging as pkg

        defs_dir = tmp_path / "definitions"
        presets_dir = defs_dir / "presets"
        defs_dir.mkdir()
        presets_dir.mkdir()
        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(pkg, "PRESETS_DIR", presets_dir)

        (defs_dir / "existing.json").write_text('{"agent_key": "existing"}')

        # Build a package with an "existing" definition
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "pkg"}))
            zf.writestr(
                "definitions/existing.json", '{"agent_key": "existing", "new": true}'
            )
        data = buf.getvalue()

        result = pkg.import_package(data, overwrite=False)
        assert "definition:existing" in result["skipped"]

    def test_import_overwrites_when_requested(self, tmp_path, monkeypatch):
        import agents.packaging as pkg

        defs_dir = tmp_path / "definitions"
        presets_dir = defs_dir / "presets"
        defs_dir.mkdir()
        presets_dir.mkdir()
        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(pkg, "PRESETS_DIR", presets_dir)

        (defs_dir / "existing.json").write_text('{"agent_key": "existing"}')

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "pkg"}))
            zf.writestr(
                "definitions/existing.json", '{"agent_key": "existing", "new": true}'
            )

        result = pkg.import_package(buf.getvalue(), overwrite=True)
        assert "existing" in result["definitions_installed"]

    def test_import_bad_zip(self):
        import agents.packaging as pkg

        result = pkg.import_package(b"not a zip file")
        assert len(result["errors"]) > 0

    def test_export_missing_definition(self, tmp_path, monkeypatch):
        import agents.packaging as pkg

        defs_dir = tmp_path / "definitions"
        defs_dir.mkdir()
        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(pkg, "PRESETS_DIR", defs_dir / "presets")

        # Should not crash, just skip missing
        data = pkg.export_package("pkg", definition_keys=["nonexistent"])
        with zipfile.ZipFile(BytesIO(data)) as zf:
            assert "definitions/nonexistent.json" not in zf.namelist()


# ---------------------------------------------------------------------------
# Versioning tests
# ---------------------------------------------------------------------------


class TestVersioning:
    def test_save_and_list_versions(self, tmp_path, monkeypatch):
        import agents.versioning as ver

        defs_dir = tmp_path / "definitions"
        versions_dir = defs_dir / "versions"
        defs_dir.mkdir()
        monkeypatch.setattr(ver, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(ver, "VERSIONS_DIR", versions_dir)

        # Create an active definition
        defn = {"agent_key": "test", "name": "Test", "domain": "qa"}
        (defs_dir / "test.json").write_text(json.dumps(defn))

        # Save version
        result = ver.save_version("test")
        assert result["version"] == 1

        # Save another
        defn["name"] = "Test v2"
        (defs_dir / "test.json").write_text(json.dumps(defn))
        result2 = ver.save_version("test")
        assert result2["version"] == 2

        # List
        versions = ver.list_versions("test")
        assert len(versions) == 2
        assert versions[0]["version"] == 1
        assert versions[1]["version"] == 2

    def test_get_version(self, tmp_path, monkeypatch):
        import agents.versioning as ver

        defs_dir = tmp_path / "definitions"
        defs_dir.mkdir()
        monkeypatch.setattr(ver, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(ver, "VERSIONS_DIR", defs_dir / "versions")

        defn = {"agent_key": "test", "name": "Test"}
        (defs_dir / "test.json").write_text(json.dumps(defn))
        ver.save_version("test")

        data = ver.get_version("test", 1)
        assert data is not None
        assert data["name"] == "Test"

        assert ver.get_version("test", 99) is None

    def test_rollback(self, tmp_path, monkeypatch):
        import agents.versioning as ver

        defs_dir = tmp_path / "definitions"
        defs_dir.mkdir()
        monkeypatch.setattr(ver, "DEFINITIONS_DIR", defs_dir)
        monkeypatch.setattr(ver, "VERSIONS_DIR", defs_dir / "versions")

        # v1
        defn_v1 = {"agent_key": "test", "name": "V1"}
        (defs_dir / "test.json").write_text(json.dumps(defn_v1))
        ver.save_version("test")

        # v2 (current)
        defn_v2 = {"agent_key": "test", "name": "V2"}
        (defs_dir / "test.json").write_text(json.dumps(defn_v2))
        ver.save_version("test")

        # Rollback to v1
        result = ver.rollback("test", 1)
        assert result["status"] == "ok"

        with open(defs_dir / "test.json") as f:
            active = json.load(f)
        assert active["name"] == "V1"

    def test_rollback_nonexistent_version(self, tmp_path, monkeypatch):
        import agents.versioning as ver

        monkeypatch.setattr(ver, "DEFINITIONS_DIR", tmp_path)
        monkeypatch.setattr(ver, "VERSIONS_DIR", tmp_path / "versions")

        result = ver.rollback("test", 99)
        assert "error" in result

    def test_save_version_no_active_definition(self, tmp_path, monkeypatch):
        import agents.versioning as ver

        monkeypatch.setattr(ver, "DEFINITIONS_DIR", tmp_path)
        monkeypatch.setattr(ver, "VERSIONS_DIR", tmp_path / "versions")

        result = ver.save_version("nonexistent")
        assert "error" in result


# ---------------------------------------------------------------------------
# Inter-crew delegation tests
# ---------------------------------------------------------------------------


class TestInterCrewDelegation:
    @pytest.fixture(autouse=True)
    def _mock_infra(self):
        # Ensure config.llm_integration is importable even when deps are missing
        fake_llm_mod = ModuleType("config.llm_integration")
        fake_llm_mod.llm_service = MagicMock()  # type: ignore[attr-defined]
        sys.modules.setdefault("config.llm_integration", fake_llm_mod)
        with (
            patch("agents.base.config") as mock_config,
            patch("config.llm_integration.llm_service"),
            patch("agents.base.LLM"),
            patch("agents.base.Agent"),
        ):
            mock_config.get_redis_client.return_value = MagicMock()
            mock_config.get_celery_app.return_value = MagicMock()
            yield

    @pytest.mark.asyncio
    async def test_delegate_to(self, tmp_path):
        from agents.base import AgentDefinition, BaseAgent

        # Create source agent
        source_defn = AgentDefinition(
            agent_key="source",
            name="Source",
            role="R",
            goal="G",
            backstory="B",
            domain="domain-a",
        )
        source = BaseAgent(source_defn)

        # Create target definition file
        target_data = {
            "agent_key": "target",
            "name": "Target",
            "role": "R",
            "goal": "G",
            "backstory": "B",
            "domain": "domain-b",
        }

        # Mock AgentFactory.from_file to return a mock agent
        mock_target = MagicMock()
        mock_target.handle_task = AsyncMock(return_value={"status": "completed"})

        with patch("agents.factory.AgentFactory.from_file", return_value=mock_target):
            result = await source.delegate_to("target", {"scenario": {"id": "t1"}})

        assert result["status"] == "completed"
        # Verify delegation context was injected
        call_args = mock_target.handle_task.call_args[0][0]
        assert call_args["_delegated_from"] == "source"
        assert call_args["_delegated_domain"] == "domain-a"


# ---------------------------------------------------------------------------
# Custom tool upload tests
# ---------------------------------------------------------------------------


class TestCustomToolUpload:
    def test_load_valid_tool(self):
        from agents.tool_registry import _REGISTRY, load_tool_from_source

        source = """
class MyCustomTool(BaseTool):
    name: str = "my_custom"
    description: str = "A custom tool"

    def _run(self, input_data: str) -> str:
        return "result"
"""
        cls = load_tool_from_source("MyCustomTool", source)
        assert cls is not None
        assert "MyCustomTool" in _REGISTRY
        # Cleanup
        _REGISTRY.pop("MyCustomTool", None)

    def test_load_invalid_source(self):
        from agents.tool_registry import load_tool_from_source

        with pytest.raises(ValueError, match="[Ss]yntax"):
            load_tool_from_source("Bad", "this is not valid python {{{")

    def test_load_no_basetool(self):
        from agents.tool_registry import load_tool_from_source

        with pytest.raises(ValueError, match="[Nn]o.*class"):
            load_tool_from_source("Empty", "x = 42")

    def test_list_registered_tools(self):
        from agents.tool_registry import (
            _REGISTRY,
            list_registered_tools,
            register_tool_class,
        )

        class DummyTool:
            name = "dummy"
            description = "A dummy tool"

        register_tool_class("DummyTool", DummyTool)
        tools = list_registered_tools()
        names = [t["name"] for t in tools]
        assert "DummyTool" in names
        _REGISTRY.pop("DummyTool", None)


# ---------------------------------------------------------------------------
# API endpoint tests (versioning, packaging, tool upload)
# ---------------------------------------------------------------------------


class TestPhase4Endpoints:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        import webgui.routes.definitions as defs_mod

        self.defs_dir = tmp_path / "definitions"
        self.presets_dir = self.defs_dir / "presets"
        self.defs_dir.mkdir()
        self.presets_dir.mkdir()
        monkeypatch.setattr(defs_mod, "DEFINITIONS_DIR", self.defs_dir)
        monkeypatch.setattr(defs_mod, "PRESETS_DIR", self.presets_dir)

    @pytest.fixture()
    def admin_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from webgui.api import api_router, get_current_user

        app = FastAPI()
        app.include_router(api_router)

        async def admin_override():
            return {
                "user_id": "admin",
                "email": "a@b.com",
                "role": "super_admin",
                "permissions": [],
            }

        app.dependency_overrides[get_current_user] = admin_override
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()

    def test_version_lifecycle(self, admin_client):
        # Create a definition
        defn = {
            "agent_key": "ver-test",
            "name": "Version Test",
            "role": "R",
            "goal": "G",
            "backstory": "B",
        }
        admin_client.post("/api/v1/definitions", json=defn)

        # Patch versioning paths
        import agents.versioning as ver

        ver_dir = self.defs_dir / "versions"
        with (
            patch.object(ver, "DEFINITIONS_DIR", self.defs_dir),
            patch.object(ver, "VERSIONS_DIR", ver_dir),
        ):
            # Save version
            resp = admin_client.post("/api/v1/definitions/ver-test/versions")
            assert resp.status_code == 201
            assert resp.json()["version"] == 1

            # List versions
            resp = admin_client.get("/api/v1/definitions/ver-test/versions")
            assert resp.status_code == 200
            assert len(resp.json()["versions"]) == 1

    def test_tool_upload(self, admin_client):
        source = """
class UploadedTool(BaseTool):
    name: str = "uploaded"
    description: str = "An uploaded tool"
    def _run(self, x: str) -> str:
        return x
"""
        resp = admin_client.post(
            "/api/v1/tools/upload",
            json={
                "name": "UploadedTool",
                "source_code": source,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "registered"

        # List tools
        resp = admin_client.get("/api/v1/tools")
        assert resp.status_code == 200
        names = [t["name"] for t in resp.json()["tools"]]
        assert "UploadedTool" in names

        # Cleanup
        from agents.tool_registry import _REGISTRY

        _REGISTRY.pop("UploadedTool", None)

    def test_tool_upload_invalid_source(self, admin_client):
        resp = admin_client.post(
            "/api/v1/tools/upload",
            json={
                "name": "BadTool",
                "source_code": "this is not python {{{",
            },
        )
        assert resp.status_code == 400

    def test_rollback_endpoint(self, admin_client):
        """API-level rollback test."""
        import agents.versioning as ver

        defn = {
            "agent_key": "rb-test",
            "name": "V1",
            "role": "R",
            "goal": "G",
            "backstory": "B",
        }
        admin_client.post("/api/v1/definitions", json=defn)

        ver_dir = self.defs_dir / "versions"
        with (
            patch.object(ver, "DEFINITIONS_DIR", self.defs_dir),
            patch.object(ver, "VERSIONS_DIR", ver_dir),
        ):
            # Save v1
            admin_client.post("/api/v1/definitions/rb-test/versions")

            # Update to v2
            defn["name"] = "V2"
            admin_client.put("/api/v1/definitions/rb-test", json=defn)
            admin_client.post("/api/v1/definitions/rb-test/versions")

            # Rollback to v1
            resp = admin_client.post(
                "/api/v1/definitions/rb-test/rollback", json={"version": 1}
            )
            assert resp.status_code == 200
            assert resp.json()["rolled_back_to"] == 1

            # Verify active is now V1
            resp = admin_client.get("/api/v1/definitions/rb-test")
            assert resp.json()["name"] == "V1"

    def test_rollback_nonexistent_version_endpoint(self, admin_client):
        import agents.versioning as ver

        defn = {
            "agent_key": "rb-miss",
            "name": "Test",
            "role": "R",
            "goal": "G",
            "backstory": "B",
        }
        admin_client.post("/api/v1/definitions", json=defn)

        ver_dir = self.defs_dir / "versions"
        with (
            patch.object(ver, "DEFINITIONS_DIR", self.defs_dir),
            patch.object(ver, "VERSIONS_DIR", ver_dir),
        ):
            resp = admin_client.post(
                "/api/v1/definitions/rb-miss/rollback", json={"version": 99}
            )
            assert resp.status_code == 404


# ---------------------------------------------------------------------------
# ZIP bomb / entry count limit tests
# ---------------------------------------------------------------------------


class TestPackageSafetyLimits:
    def test_entry_count_limit(self, tmp_path, monkeypatch):
        """Reject packages with more than _MAX_ENTRY_COUNT entries."""
        import agents.packaging as pkg

        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", tmp_path / "d")
        monkeypatch.setattr(pkg, "PRESETS_DIR", tmp_path / "p")

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "bomb"}))
            for i in range(pkg._MAX_ENTRY_COUNT + 1):
                zf.writestr(f"definitions/agent-{i:04d}.json", '{"agent_key": "x"}')

        result = pkg.import_package(buf.getvalue())
        assert any("entries" in e for e in result.get("errors", []))

    def test_total_size_limit(self, tmp_path, monkeypatch):
        """Reject packages exceeding _MAX_UNCOMPRESSED_SIZE."""
        import agents.packaging as pkg

        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", tmp_path / "d")
        monkeypatch.setattr(pkg, "PRESETS_DIR", tmp_path / "p")

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "big"}))
            # Single large entry exceeding total limit
            big_data = "x" * (pkg._MAX_UNCOMPRESSED_SIZE + 1)
            zf.writestr("definitions/big.json", big_data)

        result = pkg.import_package(buf.getvalue())
        assert any("size" in e.lower() for e in result.get("errors", []))

    def test_per_entry_size_limit(self, tmp_path, monkeypatch):
        """Reject individual entries exceeding _MAX_ENTRY_SIZE."""
        import agents.packaging as pkg

        monkeypatch.setattr(pkg, "DEFINITIONS_DIR", tmp_path / "d")
        monkeypatch.setattr(pkg, "PRESETS_DIR", tmp_path / "p")
        (tmp_path / "d").mkdir()

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"name": "big-entry"}))
            big_json = json.dumps(
                {"agent_key": "big", "data": "x" * (pkg._MAX_ENTRY_SIZE + 1)}
            )
            zf.writestr("definitions/big.json", big_json)

        result = pkg.import_package(buf.getvalue())
        assert any("too large" in e for e in result.get("errors", []))


# ---------------------------------------------------------------------------
# AgentFactory cache tests
# ---------------------------------------------------------------------------


class TestFactoryCache:
    @pytest.fixture(autouse=True)
    def _mock_infra(self):
        fake_llm_mod = ModuleType("config.llm_integration")
        fake_llm_mod.llm_service = MagicMock()
        sys.modules.setdefault("config.llm_integration", fake_llm_mod)
        with (
            patch("agents.base.config") as mock_config,
            patch("config.llm_integration.llm_service"),
            patch("agents.base.LLM"),
            patch("agents.base.Agent"),
        ):
            mock_config.get_redis_client.return_value = MagicMock()
            mock_config.get_celery_app.return_value = MagicMock()
            yield

    def test_invalidate_cache_selective(self, tmp_path):
        from agents.factory import AgentFactory

        AgentFactory._definition_cache.clear()

        defn_data = {
            "agent_key": "cache-test",
            "name": "Cache",
            "role": "R",
            "goal": "G",
            "backstory": "B",
        }
        p = tmp_path / "cache-test.json"
        p.write_text(json.dumps(defn_data))

        # Load to populate cache
        with patch.object(AgentFactory, "from_file") as mock_ff:
            # Call the real _load_definition_file
            AgentFactory._load_definition_file(p)

        assert str(p.resolve()) in AgentFactory._definition_cache

        # Selective invalidation
        AgentFactory.invalidate_cache(str(p))
        assert str(p.resolve()) not in AgentFactory._definition_cache

    def test_cache_eviction_at_max_size(self, tmp_path):
        from agents.factory import AgentFactory

        AgentFactory._definition_cache.clear()
        old_max = AgentFactory._CACHE_MAX_SIZE
        AgentFactory._CACHE_MAX_SIZE = 3

        try:
            for i in range(4):
                defn_data = {
                    "agent_key": f"evict-{i}",
                    "name": f"E{i}",
                    "role": "R",
                    "goal": "G",
                    "backstory": "B",
                }
                p = tmp_path / f"evict-{i}.json"
                p.write_text(json.dumps(defn_data))
                AgentFactory._load_definition_file(p)

            # Should have evicted the oldest
            assert len(AgentFactory._definition_cache) <= 3
        finally:
            AgentFactory._CACHE_MAX_SIZE = old_max
            AgentFactory._definition_cache.clear()

    def test_registry_max_size(self):
        from agents.tool_registry import (
            _REGISTRY,
            _REGISTRY_MAX_SIZE,
            _check_registry_capacity,
        )

        old_size = len(_REGISTRY)
        # This just tests the check doesn't raise when under limit
        _check_registry_capacity("test-tool-xyz")

        # Simulate full registry
        saved = dict(_REGISTRY)
        try:
            _REGISTRY.clear()
            for i in range(_REGISTRY_MAX_SIZE):
                _REGISTRY[f"tool-{i}"] = MagicMock()

            with pytest.raises(ValueError, match="full"):
                _check_registry_capacity("one-too-many")
        finally:
            _REGISTRY.clear()
            _REGISTRY.update(saved)


# ---------------------------------------------------------------------------
# YAML definition loading test
# ---------------------------------------------------------------------------


class TestYAMLLoading:
    @pytest.fixture(autouse=True)
    def _mock_infra(self):
        fake_llm_mod = ModuleType("config.llm_integration")
        fake_llm_mod.llm_service = MagicMock()
        sys.modules.setdefault("config.llm_integration", fake_llm_mod)
        with (
            patch("agents.base.config") as mock_config,
            patch("config.llm_integration.llm_service"),
            patch("agents.base.LLM"),
            patch("agents.base.Agent"),
        ):
            mock_config.get_redis_client.return_value = MagicMock()
            mock_config.get_celery_app.return_value = MagicMock()
            yield

    def test_from_file_yaml(self, tmp_path):
        pytest.importorskip("yaml")
        from agents.factory import AgentFactory

        yaml_content = """
agent_key: yaml-agent
name: YAML Agent
role: tester
goal: test yaml loading
backstory: loaded from yaml
domain: quality
"""
        p = tmp_path / "yaml-agent.yml"
        p.write_text(yaml_content)

        agent = AgentFactory.from_file(p)
        assert agent.definition.agent_key == "yaml-agent"
        assert agent.definition.domain == "quality"
        AgentFactory.invalidate_cache(str(p))


# ---------------------------------------------------------------------------
# delegate_to() edge cases
# ---------------------------------------------------------------------------


class TestDelegateToEdgeCases:
    @pytest.fixture(autouse=True)
    def _mock_infra(self):
        fake_llm_mod = ModuleType("config.llm_integration")
        fake_llm_mod.llm_service = MagicMock()
        sys.modules.setdefault("config.llm_integration", fake_llm_mod)
        with (
            patch("agents.base.config") as mock_config,
            patch("config.llm_integration.llm_service"),
            patch("agents.base.LLM"),
            patch("agents.base.Agent"),
        ):
            mock_config.get_redis_client.return_value = MagicMock()
            mock_config.get_celery_app.return_value = MagicMock()
            yield

    @pytest.mark.asyncio
    async def test_invalid_key_rejected(self):
        from agents.base import AgentDefinition, BaseAgent

        agent = BaseAgent(
            AgentDefinition(
                agent_key="src", name="S", role="R", goal="G", backstory="B"
            )
        )
        with pytest.raises(ValueError, match="Invalid"):
            await agent.delegate_to("../traversal", {})

    @pytest.mark.asyncio
    async def test_missing_target_file(self):
        from agents.base import AgentDefinition, BaseAgent

        agent = BaseAgent(
            AgentDefinition(
                agent_key="src", name="S", role="R", goal="G", backstory="B"
            )
        )
        with pytest.raises(FileNotFoundError):
            await agent.delegate_to("nonexistent-agent", {})

    @pytest.mark.asyncio
    async def test_delegation_failure_propagates(self):
        from agents.base import AgentDefinition, BaseAgent

        agent = BaseAgent(
            AgentDefinition(
                agent_key="src", name="S", role="R", goal="G", backstory="B"
            )
        )
        mock_target = MagicMock()
        mock_target.handle_task = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("agents.factory.AgentFactory.from_file", return_value=mock_target):
            with pytest.raises(RuntimeError, match="boom"):
                await agent.delegate_to("valid-target", {})
