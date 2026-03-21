"""Tests for the backend router and abstraction layer."""

import pytest


class TestGetBackend:
    def test_default_is_crewai(self, monkeypatch):
        monkeypatch.delenv("AGNOSTIC_BACKEND", raising=False)
        from agents.backend.router import get_backend
        from agents.backend.crewai_backend import CrewAIBackend

        backend = get_backend()
        assert isinstance(backend, CrewAIBackend)

    def test_crewai_explicit(self, monkeypatch):
        monkeypatch.setenv("AGNOSTIC_BACKEND", "crewai")
        from agents.backend.router import get_backend
        from agents.backend.crewai_backend import CrewAIBackend

        backend = get_backend()
        assert isinstance(backend, CrewAIBackend)

    def test_agnosai_backend(self, monkeypatch):
        monkeypatch.setenv("AGNOSTIC_BACKEND", "agnosai")
        monkeypatch.setenv("AGNOSAI_URL", "http://test:8080")
        from agents.backend.router import get_backend
        from agents.backend.agnosai_backend import AgnosAIBackend

        backend = get_backend()
        assert isinstance(backend, AgnosAIBackend)
        assert backend.base_url == "http://test:8080"

    def test_agnosai_with_api_key(self, monkeypatch):
        monkeypatch.setenv("AGNOSTIC_BACKEND", "agnosai")
        monkeypatch.setenv("AGNOSAI_URL", "http://test:8080")
        monkeypatch.setenv("AGNOSAI_API_KEY", "secret-key")
        from agents.backend.router import get_backend
        from agents.backend.agnosai_backend import AgnosAIBackend

        backend = get_backend()
        assert isinstance(backend, AgnosAIBackend)
        assert backend.api_key == "secret-key"

    def test_invalid_backend_raises(self, monkeypatch):
        monkeypatch.setenv("AGNOSTIC_BACKEND", "invalid")
        from agents.backend.router import get_backend

        with pytest.raises(ValueError, match="Invalid AGNOSTIC_BACKEND"):
            get_backend()

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("AGNOSTIC_BACKEND", "AgnosAI")
        monkeypatch.setenv("AGNOSAI_URL", "http://test:8080")
        from agents.backend.router import get_backend
        from agents.backend.agnosai_backend import AgnosAIBackend

        backend = get_backend()
        assert isinstance(backend, AgnosAIBackend)
