from __future__ import annotations

import hashlib
import json
import logging
import random  # nosec B311 - used for test data generation, not security
from datetime import datetime, timedelta
from typing import Any

from faker import Faker

# Add config path for imports
from config.environment import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UnifiedDataGenerator:
    """Centralized data generation service optimized for all QA agents"""

    def __init__(self) -> None:
        self.faker = Faker()
        self.redis_client = config.get_redis_client()
        self.celery_app = config.get_celery_app("data_generator")

        # Data generation presets for different test types
        self.presets = {
            "api_testing": self._get_api_testing_preset,
            "form_testing": self._get_form_testing_preset,
            "performance_testing": self._get_performance_testing_preset,
            "security_testing": self._get_security_testing_preset,
            "accessibility_testing": self._get_accessibility_testing_preset,
            "mobile_testing": self._get_mobile_testing_preset,
            "database_testing": self._get_database_testing_preset,
            "regression_testing": self._get_regression_testing_preset,
        }

    def generate_test_data(
        self, data_type: str, count: int = 10, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Generate test data based on type and configuration"""
        config = config or {}
        preset_func = self.presets.get(data_type, self._get_generic_preset)
        preset = preset_func()

        # Override preset with custom config
        preset.update(config)

        generated_data = []
        for i in range(count):
            data_item = self._generate_data_item(preset, i)
            generated_data.append(data_item)

        # Store in Redis for reuse
        cache_key = f"test_data:{data_type}:{hashlib.sha256(str(config).encode()).hexdigest()[:16]}"
        self.redis_client.setex(
            cache_key, 3600, json.dumps(generated_data)
        )  # Cache for 1 hour

        return {
            "data_type": data_type,
            "count": count,
            "config": config,
            "generated_data": generated_data,
            "cache_key": cache_key,
            "generated_at": datetime.now().isoformat(),
            "data_schema": self._get_data_schema(preset),
        }

    def _generate_data_item(self, preset: dict[str, Any], index: int) -> dict[str, Any]:
        """Generate a single data item based on preset configuration"""
        item: dict[str, Any] = {}

        for field_name, field_config in preset.items():
            if field_name.startswith("_") or not isinstance(field_config, dict):
                continue
            field_type = field_config.get("type", "string")
            field_options = field_config.get("options", {})

            if field_type == "string":
                if "pattern" in field_options:
                    item[field_name] = self._generate_pattern_string(
                        field_options["pattern"], index
                    )
                elif "values" in field_options:
                    item[field_name] = random.choice(field_options["values"])  # nosec B311
                else:
                    item[field_name] = self.faker.sentence(
                        nb_words=field_options.get("words", 5)
                    )

            elif field_type == "email":
                item[field_name] = self.faker.email()

            elif field_type == "number":
                if "range" in field_options:
                    min_val, max_val = field_options["range"]
                    item[field_name] = random.randint(min_val, max_val)  # nosec B311
                else:
                    item[field_name] = self.faker.random_int()

            elif field_type == "float":
                if "range" in field_options:
                    min_val, max_val = field_options["range"]
                    item[field_name] = round(
                        random.uniform(min_val, max_val),  # nosec B311
                        field_options.get("decimals", 2),
                    )
                else:
                    item[field_name] = round(random.uniform(0, 100), 2)  # nosec B311

            elif field_type == "date":
                if "range" in field_options:
                    start_date, end_date = field_options["range"]
                    start_dt = datetime.fromisoformat(start_date)
                    end_dt = datetime.fromisoformat(end_date)
                    random_date = start_dt + timedelta(
                        seconds=random.randint(  # nosec B311
                            0, int((end_dt - start_dt).total_seconds())
                        )
                    )
                    item[field_name] = random_date.isoformat()
                else:
                    item[field_name] = self.faker.date_between(
                        start_date="-30d", end_date="today"
                    ).isoformat()

            elif field_type == "boolean":
                item[field_name] = random.choice([True, False])  # nosec B311

            elif field_type == "enum":
                item[field_name] = random.choice(field_options.get("values", []))  # nosec B311

            elif field_type == "array":
                array_size = field_options.get("size", 3)
                item[field_name] = [self.faker.word() for _ in range(array_size)]

            elif field_type == "object":
                item[field_name] = self._generate_nested_object(
                    field_options.get("schema", {})
                )

        # Add metadata
        item["_generated_at"] = datetime.now().isoformat()
        item["_index"] = index
        item["_preset"] = preset.get("_name", "custom")

        return item

    def _generate_pattern_string(self, pattern: str, index: int) -> str:
        """Generate string based on pattern"""
        patterns = {
            "username": lambda: f"user_{index:04d}",
            "email": lambda: f"user{index:04d}@example.com",
            "id": lambda: f"id_{index:06d}",
            "uuid": lambda: f"uuid_{index:04d}_{random.randint(1000, 9999)}",  # nosec B311
        }
        return patterns.get(pattern, lambda: f"item_{index}")()

    def _generate_nested_object(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Generate nested object based on schema"""
        obj: dict[str, Any] = {}
        for key, value in schema.items():
            if isinstance(value, dict):
                obj[key] = self._generate_nested_object(value)
            elif isinstance(value, list):
                obj[key] = [random.choice(value) for _ in range(random.randint(1, 3))]  # nosec B311
            else:
                obj[key] = str(value)
        return obj

    def _get_data_schema(self, preset: dict[str, Any]) -> dict[str, Any]:
        """Extract schema from preset for documentation"""
        schema = {}
        for field_name, field_config in preset.items():
            if field_name.startswith("_") or not isinstance(field_config, dict):
                continue

            schema[field_name] = {
                "type": field_config.get("type", "string"),
                "required": field_config.get("required", False),
                "description": field_config.get("description", ""),
                "options": field_config.get("options", {}),
            }
        return schema

    def get_cached_data(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve cached test data"""
        cached_data = self.redis_client.get(cache_key)
        if cached_data:
            result: dict[str, Any] = json.loads(cached_data)  # type: ignore[arg-type]
            return result
        return None

    def generate_edge_case_data(
        self, base_data_type: str, edge_cases: list[str] | None = None
    ) -> dict[str, Any]:
        """Generate edge case data for testing"""
        edge_cases = edge_cases or [
            "boundary",
            "null",
            "empty",
            "max_length",
            "special_chars",
        ]

        base_preset = self.presets.get(base_data_type, self._get_generic_preset)()
        edge_case_data = []

        for edge_case in edge_cases:
            edge_item = self._generate_edge_case_item(base_preset, edge_case)
            edge_case_data.append(edge_item)

        return {
            "data_type": base_data_type,
            "edge_case_type": "multi",
            "edge_cases": edge_cases,
            "edge_case_data": edge_case_data,
            "generated_at": datetime.now().isoformat(),
        }

    def _generate_edge_case_item(
        self, preset: dict[str, Any], edge_case: str
    ) -> dict[str, Any]:
        """Generate a single edge case item"""
        item: dict[str, Any] = {}

        for field_name, field_config in preset.items():
            if field_name.startswith("_"):
                continue

            field_type = field_config.get("type", "string")

            if edge_case == "null":
                item[field_name] = None
            elif edge_case == "empty":
                item[field_name] = (
                    ""
                    if field_type == "string"
                    else []
                    if field_type == "array"
                    else {}
                )
            elif edge_case == "max_length":
                if field_type == "string":
                    max_len = field_config.get("options", {}).get("max_length", 255)
                    item[field_name] = "x" * max_len
                else:
                    item[field_name] = self._generate_data_item(preset, 0)[field_name]
            elif edge_case == "special_chars":
                if field_type == "string":
                    item[field_name] = "!@#$%^&*()_+-={}[]|\\:;\"'<>?,./"
                else:
                    item[field_name] = self._generate_data_item(preset, 0)[field_name]
            elif edge_case == "boundary":
                if field_type in ["number", "float"]:
                    range_vals = field_config.get("options", {}).get("range", [0, 100])
                    item[field_name] = (
                        range_vals[0] - 1
                        if random.choice([True, False])  # nosec B311
                        else range_vals[1] + 1
                    )
                else:
                    item[field_name] = self._generate_data_item(preset, 0)[field_name]
            else:
                item[field_name] = self._generate_data_item(preset, 0)[field_name]

        item["_edge_case"] = edge_case
        item["_generated_at"] = datetime.now().isoformat()

        return item

    # Preset configurations for different test types
    def _get_api_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "api_testing",
            "id": {
                "type": "number",
                "required": True,
                "description": "Unique identifier",
            },
            "name": {
                "type": "string",
                "required": True,
                "options": {"pattern": "username"},
            },
            "email": {"type": "email", "required": True},
            "age": {
                "type": "number",
                "required": False,
                "options": {"range": [18, 99]},
            },
            "active": {"type": "boolean", "required": False},
            "created_at": {"type": "date", "required": False},
            "tags": {"type": "array", "required": False, "options": {"size": 3}},
            "metadata": {
                "type": "object",
                "required": False,
                "options": {"schema": {"source": "api", "version": "1.0"}},
            },
        }

    def _get_form_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "form_testing",
            "first_name": {
                "type": "string",
                "required": True,
                "description": "User first name",
            },
            "last_name": {
                "type": "string",
                "required": True,
                "description": "User last name",
            },
            "email": {"type": "email", "required": True},
            "phone": {"type": "string", "required": False},
            "country": {
                "type": "enum",
                "required": False,
                "options": {"values": ["US", "CA", "UK", "AU"]},
            },
            "newsletter": {"type": "boolean", "required": False},
            "birth_date": {
                "type": "date",
                "required": False,
                "options": {"range": ["1950-01-01", "2005-12-31"]},
            },
            "comments": {
                "type": "string",
                "required": False,
                "options": {"max_length": 500},
            },
        }

    def _get_performance_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "performance_testing",
            "endpoint": {
                "type": "string",
                "required": True,
                "options": {"values": ["/api/users", "/api/products", "/api/orders"]},
            },
            "method": {
                "type": "enum",
                "required": True,
                "options": {"values": ["GET", "POST", "PUT", "DELETE"]},
            },
            "payload_size": {
                "type": "number",
                "required": False,
                "options": {"range": [0, 10000]},
            },
            "concurrent_users": {
                "type": "number",
                "required": False,
                "options": {"range": [1, 1000]},
            },
            "response_time_ms": {
                "type": "float",
                "required": False,
                "options": {"range": [0.1, 10000.0]},
            },
            "cache_hit": {"type": "boolean", "required": False},
        }

    def _get_security_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "security_testing",
            "username": {"type": "string", "required": True},
            "password": {
                "type": "string",
                "required": True,
                "options": {"max_length": 128},
            },
            "email": {"type": "email", "required": True},
            "role": {
                "type": "enum",
                "required": False,
                "options": {"values": ["user", "admin", "guest"]},
            },
            "permissions": {"type": "array", "required": False, "options": {"size": 5}},
            "last_login": {"type": "date", "required": False},
            "failed_attempts": {
                "type": "number",
                "required": False,
                "options": {"range": [0, 10]},
            },
        }

    def _get_accessibility_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "accessibility_testing",
            "element_type": {
                "type": "enum",
                "required": True,
                "options": {"values": ["button", "link", "input", "image", "heading"]},
            },
            "text": {
                "type": "string",
                "required": True,
                "options": {"max_length": 100},
            },
            "alt_text": {
                "type": "string",
                "required": False,
                "options": {"max_length": 200},
            },
            "aria_label": {"type": "string", "required": False},
            "tab_index": {
                "type": "number",
                "required": False,
                "options": {"range": [-1, 100]},
            },
            "keyboard_accessible": {"type": "boolean", "required": False},
            "screen_reader_supported": {"type": "boolean", "required": False},
        }

    def _get_mobile_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "mobile_testing",
            "device_type": {
                "type": "enum",
                "required": True,
                "options": {"values": ["mobile", "tablet", "desktop"]},
            },
            "os": {
                "type": "enum",
                "required": True,
                "options": {"values": ["iOS", "Android", "Windows", "macOS"]},
            },
            "os_version": {"type": "string", "required": False},
            "screen_width": {
                "type": "number",
                "required": False,
                "options": {"range": [320, 2560]},
            },
            "screen_height": {
                "type": "number",
                "required": False,
                "options": {"range": [568, 1440]},
            },
            "orientation": {
                "type": "enum",
                "required": False,
                "options": {"values": ["portrait", "landscape"]},
            },
            "touch_enabled": {"type": "boolean", "required": False},
            "network_type": {
                "type": "enum",
                "required": False,
                "options": {"values": ["wifi", "4g", "3g", "2g"]},
            },
        }

    def _get_database_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "database_testing",
            "table_name": {"type": "string", "required": True},
            "operation": {
                "type": "enum",
                "required": True,
                "options": {"values": ["INSERT", "UPDATE", "DELETE", "SELECT"]},
            },
            "record_id": {"type": "number", "required": False},
            "data": {
                "type": "object",
                "required": True,
                "options": {"schema": {"field1": "value1", "field2": "value2"}},
            },
            "query_time_ms": {
                "type": "float",
                "required": False,
                "options": {"range": [0.1, 10000.0]},
            },
            "rows_affected": {
                "type": "number",
                "required": False,
                "options": {"range": [0, 10000]},
            },
            "transaction_id": {"type": "string", "required": False},
        }

    def _get_regression_testing_preset(self) -> dict[str, Any]:
        return {
            "_name": "regression_testing",
            "test_case_id": {
                "type": "string",
                "required": True,
                "options": {"pattern": "id"},
            },
            "test_name": {"type": "string", "required": True},
            "module": {"type": "string", "required": True},
            "priority": {
                "type": "enum",
                "required": False,
                "options": {"values": ["high", "medium", "low"]},
            },
            "expected_result": {"type": "string", "required": True},
            "actual_result": {"type": "string", "required": False},
            "status": {
                "type": "enum",
                "required": False,
                "options": {"values": ["pass", "fail", "skip"]},
            },
            "execution_time_ms": {
                "type": "float",
                "required": False,
                "options": {"range": [0.1, 300000.0]},
            },
            "environment": {
                "type": "string",
                "required": False,
                "options": {"values": ["dev", "staging", "prod"]},
            },
        }

    def _get_generic_preset(self) -> dict[str, Any]:
        return {
            "_name": "generic",
            "id": {"type": "number", "required": True},
            "name": {"type": "string", "required": True},
            "description": {"type": "string", "required": False},
            "active": {"type": "boolean", "required": False},
            "created_at": {"type": "date", "required": False},
            "metadata": {"type": "object", "required": False},
        }


# Celery tasks for asynchronous data generation
_celery_app = config.get_celery_app("data_generator")


@_celery_app.task  # type: ignore[untyped-decorator]
def generate_test_data_async(
    data_type: str, count: int, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Asynchronous test data generation task"""
    generator = UnifiedDataGenerator()
    return generator.generate_test_data(data_type, count, config)


@_celery_app.task  # type: ignore[untyped-decorator]
def generate_edge_case_data_async(
    base_data_type: str, edge_cases: list[str] | None = None
) -> dict[str, Any]:
    """Asynchronous edge case data generation task"""
    generator = UnifiedDataGenerator()
    return generator.generate_edge_case_data(base_data_type, edge_cases)


class DataOptimizationService:
    """Service for optimizing data generation across all QA agents"""

    def __init__(self) -> None:
        self.generator = UnifiedDataGenerator()
        self.redis_client = config.get_redis_client()

    def optimize_for_agent(
        self, agent_type: str, task_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Optimize data generation for specific agent type"""
        optimization_strategies = {
            "performance": self._optimize_for_performance,
            "security_compliance": self._optimize_for_security_compliance,
            "resilience": self._optimize_for_resilience,
            "user_experience": self._optimize_for_user_experience,
            "senior": self._optimize_for_senior,
            "junior": self._optimize_for_junior,
        }

        strategy = optimization_strategies.get(agent_type, self._optimize_generic)
        return strategy(task_config)

    def _optimize_for_performance(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optimize data generation for performance testing"""
        return {
            "data_type": "performance_testing",
            "count": config.get("load_size", 100),
            "config": {
                "endpoint": config.get("target_endpoint", "/api/test"),
                "method": config.get("method", "GET"),
                "payload_size": config.get("payload_size_range", [100, 5000]),
                "concurrent_users": config.get("concurrent_users", 10),
            },
        }

    def _optimize_for_security_compliance(
        self, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Optimize data generation for security and compliance testing"""
        base_config = {
            "data_type": "security_testing",
            "count": 50,
            "config": {
                "include_admin_roles": True,
                "include_malicious_payloads": False,
                "role_distribution": ["user", "admin", "guest"],
            },
        }

        # Add compliance-specific data if needed
        if config.get("test_gdpr", False):
            base_config["gdpr_data"] = self.generator.generate_test_data(
                "gdpr_testing", 20
            )

        return base_config

    def _optimize_for_resilience(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optimize data generation for resilience testing"""
        return {
            "data_type": "database_testing",
            "count": config.get("test_scenarios", 30),
            "config": {
                "operations": ["INSERT", "UPDATE", "SELECT", "DELETE"],
                "include_transactions": True,
                "stress_level": config.get("stress_level", "medium"),
            },
        }

    def _optimize_for_user_experience(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optimize data generation for UX testing"""
        base_data = self.generator.generate_test_data("accessibility_testing", 25)
        mobile_data = self.generator.generate_test_data("mobile_testing", 20)

        return {
            "accessibility_data": base_data,
            "mobile_data": mobile_data,
            "cross_device_scenarios": self._generate_cross_device_scenarios(),
            "wcag_test_cases": self._generate_wcag_test_cases(),
        }

    def _optimize_for_senior(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optimize data generation for senior QA agent"""
        return {
            "edge_case_data": self.generator.generate_edge_case_data("api_testing"),
            "boundary_test_data": self.generator.generate_test_data("form_testing", 10),
            "complex_scenarios": self._generate_complex_scenarios(),
        }

    def _optimize_for_junior(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optimize data generation for junior QA agent"""
        return {
            "regression_data": self.generator.generate_test_data(
                "regression_testing", 50
            ),
            "synthetic_users": self.generator.generate_test_data("api_testing", 100),
            "form_test_data": self.generator.generate_test_data("form_testing", 30),
        }

    def _optimize_generic(self, config: dict[str, Any]) -> dict[str, Any]:
        """Generic optimization strategy"""
        return {
            "data_type": config.get("data_type", "generic"),
            "count": config.get("count", 20),
            "config": config.get("custom_config", {}),
        }

    def _generate_cross_device_scenarios(self) -> list[dict[str, Any]]:
        """Generate cross-device test scenarios"""
        return [
            {"device": "mobile", "orientation": "portrait", "viewport": "375x667"},
            {"device": "mobile", "orientation": "landscape", "viewport": "667x375"},
            {"device": "tablet", "orientation": "portrait", "viewport": "768x1024"},
            {"device": "tablet", "orientation": "landscape", "viewport": "1024x768"},
            {"device": "desktop", "viewport": "1440x900"},
        ]

    def _generate_wcag_test_cases(self) -> list[dict[str, Any]]:
        """Generate WCAG-specific test cases"""
        return [
            {"criterion": "1.1.1", "test": "Image alt text", "elements": ["img"]},
            {
                "criterion": "2.1.1",
                "test": "Keyboard accessibility",
                "elements": ["button", "link", "input"],
            },
            {
                "criterion": "3.3.2",
                "test": "Form labels",
                "elements": ["input", "select", "textarea"],
            },
            {
                "criterion": "4.1.2",
                "test": "ARIA roles",
                "elements": ["nav", "main", "section"],
            },
        ]

    def _generate_complex_scenarios(self) -> list[dict[str, Any]]:
        """Generate complex test scenarios for edge case testing"""
        return [
            {"scenario": "nested_objects", "complexity": "high", "data_type": "object"},
            {"scenario": "large_arrays", "complexity": "high", "data_type": "array"},
            {
                "scenario": "circular_references",
                "complexity": "medium",
                "data_type": "object",
            },
            {
                "scenario": "unicode_handling",
                "complexity": "medium",
                "data_type": "string",
            },
        ]


# Main service class for external access
class DataGenerationService:
    """Main service for optimized data generation across all QA agents"""

    def __init__(self) -> None:
        self.generator = UnifiedDataGenerator()
        self.optimizer = DataOptimizationService()

    def generate_for_agent(
        self, agent_type: str, task_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate optimized data for specific agent type"""
        # Optimize configuration for agent
        optimized_config = self.optimizer.optimize_for_agent(agent_type, task_config)

        # Generate the data
        if "data_type" in optimized_config:
            result = self.generator.generate_test_data(
                optimized_config["data_type"],
                optimized_config["count"],
                optimized_config.get("config", {}),
            )
        else:
            # Handle multiple data types
            result = {"multi_type_data": {}}
            for data_key, data_config in optimized_config.items():
                if isinstance(data_config, dict) and "data_type" in data_config:
                    generated = self.generator.generate_test_data(
                        data_config["data_type"],
                        data_config.get("count", 10),
                        data_config.get("config", {}),
                    )
                    result["multi_type_data"][data_key] = generated

        # Add optimization metadata
        result["optimization_metadata"] = {
            "agent_type": agent_type,
            "optimized_at": datetime.now().isoformat(),
            "strategy": "agent_specific",
        }

        return result

    def get_usage_statistics(self) -> dict[str, Any]:
        """Get data generation usage statistics"""
        return {
            "available_data_types": list(self.generator.presets.keys()),
            "supported_agents": [
                "performance",
                "security_compliance",
                "senior",
                "junior",
                "analyst",
            ],
            "optimization_strategies": 6,
            "cache_enabled": True,
            "async_generation": True,
        }


if __name__ == "__main__":
    service = DataGenerationService()

    # Example usage
    result = service.generate_for_agent(
        "performance",
        {"target_endpoint": "/api/users", "load_size": 50, "method": "GET"},
    )

    logger.debug("Generated data: %s", json.dumps(result, indent=2))
