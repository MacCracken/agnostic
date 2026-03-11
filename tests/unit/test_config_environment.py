import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from config.environment import Config
except ImportError:
    pytest.skip("config.environment module not available", allow_module_level=True)


class TestConfigInit:
    """Tests for Config class initialization"""

    def test_default_values(self):
        cfg = Config()
        # Should have sensible defaults (either from env or hardcoded)
        assert isinstance(cfg.redis_host, str)
        assert len(cfg.redis_host) > 0
        assert isinstance(cfg.redis_port, int)
        assert cfg.redis_port > 0

    def test_custom_env_values(self):
        env = {
            "REDIS_HOST": "custom-redis",
            "REDIS_PORT": "6380",
            "REDIS_DB": "2",
            "RABBITMQ_HOST": "custom-rabbit",
            "RABBITMQ_PORT": "5673",
            "RABBITMQ_USER": "myuser",
            "RABBITMQ_PASSWORD": "mypass",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = Config()
        assert cfg.redis_host == "custom-redis"
        assert cfg.redis_port == 6380
        assert cfg.redis_db == 2
        assert cfg.rabbitmq_host == "custom-rabbit"
        assert cfg.rabbitmq_port == 5673
        assert cfg.rabbitmq_user == "myuser"


class TestValidation:
    """Tests for environment variable validation"""

    def test_validate_returns_dict(self):
        cfg = Config()
        result = cfg.validate_required_env_vars()
        assert isinstance(result, dict)
        assert len(result) > 0
        # All values should be booleans
        assert all(isinstance(v, bool) for v in result.values())


class TestConnectionInfo:
    """Tests for connection info retrieval"""

    def test_get_connection_info(self):
        cfg = Config()
        info = cfg.get_connection_info()
        assert "redis" in info
        assert "rabbitmq" in info
        assert "url" in info["redis"]
        assert "url" in info["rabbitmq"]

    def test_redis_url_format(self):
        env = {"REDIS_HOST": "myhost", "REDIS_PORT": "6379", "REDIS_DB": "0"}
        remove = {k: "" for k in ("REDIS_URL",) if k in os.environ}
        with patch.dict(os.environ, {**env, **remove}, clear=False):
            os.environ.pop("REDIS_URL", None)
            cfg = Config()
        assert "myhost" in cfg.redis_url

    def test_rabbitmq_url_format(self):
        env = {"RABBITMQ_HOST": "rabbithost", "RABBITMQ_PORT": "5672"}
        remove = {k: "" for k in ("RABBITMQ_URL",) if k in os.environ}
        with patch.dict(os.environ, {**env, **remove}, clear=False):
            os.environ.pop("RABBITMQ_URL", None)
            cfg = Config()
        assert "rabbithost" in cfg.rabbitmq_url
