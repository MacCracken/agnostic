"""Tests for agents/constants.py — shared constants and utilities."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.constants import (
    DOMAINS,
    PRESETS_DIR,
    SAFE_KEY_RE,
    SIZES,
    make_agent_key,
    validate_agent_key,
)


class TestDomains:
    def test_has_expected_domains(self):
        assert "quality" in DOMAINS
        assert "software-engineering" in DOMAINS
        assert "design" in DOMAINS
        assert "data-engineering" in DOMAINS
        assert "devops" in DOMAINS

    def test_no_legacy_qa(self):
        assert "qa" not in DOMAINS


class TestSizes:
    def test_has_all_sizes(self):
        assert SIZES == ("lean", "standard", "large")


class TestMakeAgentKey:
    def test_simple(self):
        assert make_agent_key("QA Manager") == "qa-manager"

    def test_special_chars(self):
        assert (
            make_agent_key("Senior QA Engineer & Tester") == "senior-qa-engineer-tester"
        )

    def test_empty(self):
        assert make_agent_key("") == "agent"

    def test_already_kebab(self):
        assert make_agent_key("qa-manager") == "qa-manager"

    def test_output_matches_safe_key_re(self):
        """Generated keys must pass SAFE_KEY_RE validation."""
        test_roles = [
            "UX Lead",
            "Game Designer",
            "Backend Engineer",
            "Performance & Resilience Specialist",
            "CI/CD Expert",
        ]
        for role in test_roles:
            key = make_agent_key(role)
            assert SAFE_KEY_RE.match(key), (
                f"Key {key!r} from {role!r} doesn't match SAFE_KEY_RE"
            )


class TestValidateAgentKey:
    def test_valid(self):
        validate_agent_key("qa-manager")
        validate_agent_key("senior-qa")
        validate_agent_key("a")

    def test_invalid_raises(self):
        import pytest

        with pytest.raises(ValueError):
            validate_agent_key("../path-traversal")
        with pytest.raises(ValueError):
            validate_agent_key("-starts-with-dash")
        with pytest.raises(ValueError):
            validate_agent_key("HAS_CAPS")


class TestPresetsDir:
    def test_exists(self):
        assert PRESETS_DIR.exists()

    def test_has_presets(self):
        presets = list(PRESETS_DIR.glob("*.json"))
        assert len(presets) >= 18
