"""Tests for shared/data_generation_service.py — UnifiedDataGenerator and helpers."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Patch config before importing module under test
_mock_redis = MagicMock()
_mock_celery = MagicMock()


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    """Patch config.get_redis_client and config.get_celery_app globally."""
    monkeypatch.setattr("config.environment.config.get_redis_client", lambda: _mock_redis)
    monkeypatch.setattr(
        "config.environment.config.get_celery_app", lambda name: _mock_celery
    )


def _make_generator():
    from shared.data_generation_service import UnifiedDataGenerator

    return UnifiedDataGenerator()


class TestUnifiedDataGeneratorInit:
    def test_has_presets(self):
        gen = _make_generator()
        expected = {
            "api_testing",
            "form_testing",
            "performance_testing",
            "security_testing",
            "accessibility_testing",
            "mobile_testing",
            "database_testing",
            "regression_testing",
        }
        assert set(gen.presets.keys()) == expected


class TestGenerateTestData:
    def test_returns_correct_structure(self):
        gen = _make_generator()
        result = gen.generate_test_data("api_testing", count=3)
        assert result["data_type"] == "api_testing"
        assert result["count"] == 3
        assert len(result["generated_data"]) == 3
        assert "cache_key" in result
        assert "data_schema" in result

    def test_generic_fallback_for_unknown_type(self):
        gen = _make_generator()
        result = gen.generate_test_data("unknown_type", count=2)
        assert result["data_type"] == "unknown_type"
        assert len(result["generated_data"]) == 2

    def test_caches_to_redis(self):
        _mock_redis.reset_mock()
        gen = _make_generator()
        gen.generate_test_data("api_testing", count=1)
        _mock_redis.setex.assert_called_once()


class TestGenerateDataItem:
    def test_string_field(self):
        gen = _make_generator()
        preset = {"name": {"type": "string"}}
        item = gen._generate_data_item(preset, 0)
        assert isinstance(item["name"], str)

    def test_string_with_pattern(self):
        gen = _make_generator()
        preset = {"name": {"type": "string", "options": {"pattern": "username"}}}
        item = gen._generate_data_item(preset, 5)
        assert item["name"] == "user_0005"

    def test_string_with_values(self):
        gen = _make_generator()
        preset = {"color": {"type": "string", "options": {"values": ["red", "blue"]}}}
        item = gen._generate_data_item(preset, 0)
        assert item["color"] in ("red", "blue")

    def test_email_field(self):
        gen = _make_generator()
        preset = {"email": {"type": "email"}}
        item = gen._generate_data_item(preset, 0)
        assert "@" in item["email"]

    def test_number_field_with_range(self):
        gen = _make_generator()
        preset = {"age": {"type": "number", "options": {"range": [18, 65]}}}
        item = gen._generate_data_item(preset, 0)
        assert 18 <= item["age"] <= 65

    def test_float_field_with_range(self):
        gen = _make_generator()
        preset = {"score": {"type": "float", "options": {"range": [0.0, 1.0], "decimals": 3}}}
        item = gen._generate_data_item(preset, 0)
        assert 0.0 <= item["score"] <= 1.0

    def test_date_field(self):
        gen = _make_generator()
        preset = {"created": {"type": "date"}}
        item = gen._generate_data_item(preset, 0)
        assert isinstance(item["created"], str)

    def test_date_field_with_range(self):
        gen = _make_generator()
        preset = {"d": {"type": "date", "options": {"range": ["2024-01-01", "2024-12-31"]}}}
        item = gen._generate_data_item(preset, 0)
        assert item["d"].startswith("2024-")

    def test_boolean_field(self):
        gen = _make_generator()
        preset = {"active": {"type": "boolean"}}
        item = gen._generate_data_item(preset, 0)
        assert isinstance(item["active"], bool)

    def test_enum_field(self):
        gen = _make_generator()
        preset = {"role": {"type": "enum", "options": {"values": ["admin", "user"]}}}
        item = gen._generate_data_item(preset, 0)
        assert item["role"] in ("admin", "user")

    def test_array_field(self):
        gen = _make_generator()
        preset = {"tags": {"type": "array", "options": {"size": 4}}}
        item = gen._generate_data_item(preset, 0)
        assert isinstance(item["tags"], list)
        assert len(item["tags"]) == 4

    def test_object_field(self):
        gen = _make_generator()
        preset = {"meta": {"type": "object", "options": {"schema": {"k": "v"}}}}
        item = gen._generate_data_item(preset, 0)
        assert isinstance(item["meta"], dict)

    def test_metadata_fields_added(self):
        gen = _make_generator()
        item = gen._generate_data_item({"x": {"type": "string"}}, 7)
        assert item["_index"] == 7
        assert "_generated_at" in item


class TestPatternString:
    def test_username_pattern(self):
        gen = _make_generator()
        assert gen._generate_pattern_string("username", 3) == "user_0003"

    def test_email_pattern(self):
        gen = _make_generator()
        assert gen._generate_pattern_string("email", 1) == "user0001@example.com"

    def test_id_pattern(self):
        gen = _make_generator()
        assert gen._generate_pattern_string("id", 42) == "id_000042"

    def test_unknown_pattern_fallback(self):
        gen = _make_generator()
        assert gen._generate_pattern_string("zzz", 0) == "item_0"


class TestEdgeCaseData:
    def test_generates_default_edge_cases(self):
        gen = _make_generator()
        result = gen.generate_edge_case_data("api_testing")
        assert "edge_case_data" in result
        assert len(result["edge_case_data"]) == 5  # 5 default edge cases
        assert result["edge_cases"] == ["boundary", "null", "empty", "max_length", "special_chars"]

    def test_null_edge_case(self):
        gen = _make_generator()
        result = gen.generate_edge_case_data("api_testing", edge_cases=["null"])
        item = result["edge_case_data"][0]
        assert item["_edge_case"] == "null"
        # All non-meta fields should be None
        for k, v in item.items():
            if not k.startswith("_"):
                assert v is None

    def test_empty_edge_case(self):
        gen = _make_generator()
        result = gen.generate_edge_case_data("api_testing", edge_cases=["empty"])
        item = result["edge_case_data"][0]
        assert item["_edge_case"] == "empty"

    def test_special_chars_edge_case(self):
        gen = _make_generator()
        result = gen.generate_edge_case_data("form_testing", edge_cases=["special_chars"])
        item = result["edge_case_data"][0]
        # String fields should have special chars
        assert "!@#" in str(item.get("first_name", ""))


class TestGetCachedData:
    def test_returns_cached_data(self):
        _mock_redis.get.return_value = b'[{"a": 1}]'
        gen = _make_generator()
        result = gen.get_cached_data("test:key")
        assert result == [{"a": 1}]

    def test_returns_none_when_no_cache(self):
        _mock_redis.get.return_value = None
        gen = _make_generator()
        assert gen.get_cached_data("missing") is None


class TestDataSchema:
    def test_schema_excludes_private_fields(self):
        gen = _make_generator()
        preset = {
            "_name": "test",
            "field1": {"type": "string", "required": True, "description": "A field"},
        }
        schema = gen._get_data_schema(preset)
        assert "_name" not in schema
        assert "field1" in schema
        assert schema["field1"]["type"] == "string"


class TestAllPresets:
    @pytest.mark.parametrize(
        "preset_name",
        [
            "api_testing",
            "form_testing",
            "performance_testing",
            "security_testing",
            "accessibility_testing",
            "mobile_testing",
            "database_testing",
            "regression_testing",
        ],
    )
    def test_preset_generates_data(self, preset_name):
        gen = _make_generator()
        result = gen.generate_test_data(preset_name, count=2)
        assert len(result["generated_data"]) == 2
        # Each item should have metadata
        for item in result["generated_data"]:
            assert "_generated_at" in item
            assert "_index" in item


class TestDataGenerationService:
    def test_get_usage_statistics(self):
        from shared.data_generation_service import DataGenerationService

        service = DataGenerationService()
        stats = service.get_usage_statistics()
        assert "available_data_types" in stats
        assert len(stats["available_data_types"]) == 8
        assert stats["cache_enabled"] is True

    def test_generate_for_agent_performance(self):
        from shared.data_generation_service import DataGenerationService

        service = DataGenerationService()
        result = service.generate_for_agent("performance", {"load_size": 5})
        assert "optimization_metadata" in result
        assert result["optimization_metadata"]["agent_type"] == "performance"

    def test_generate_for_agent_generic(self):
        from shared.data_generation_service import DataGenerationService

        service = DataGenerationService()
        result = service.generate_for_agent("unknown_agent", {"data_type": "generic", "count": 3})
        assert "optimization_metadata" in result
