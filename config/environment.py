"""
Configuration utilities for the Agentic QA Team System.
Handles environment variable parsing and connection string building.
"""

import os
from typing import Any
from urllib.parse import urlparse

import redis
from celery import Celery


class Config:
    """Configuration class for managing environment variables and connections."""

    def __init__(self) -> None:
        self._redis_client: redis.Redis | None = None
        self.load_environment()

    def load_environment(self) -> None:
        """Load environment variables with defaults."""
        # Application Configuration (loaded first — used by validation below)
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.environment = os.getenv("ENVIRONMENT", "development")

        # Redis Configuration
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_db = int(os.getenv("REDIS_DB", "0"))
        self.redis_password = os.getenv("REDIS_PASSWORD")
        self.redis_url = os.getenv(
            "REDIS_URL", f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
        )

        # RabbitMQ Configuration
        self.rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        self.rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.getenv("RABBITMQ_USER")
        self.rabbitmq_password = os.getenv("RABBITMQ_PASSWORD")
        self.rabbitmq_vhost = os.getenv("RABBITMQ_VHOST", "/")

        # Validate RabbitMQ credentials in production
        if self.environment == "production" and (
            not self.rabbitmq_user or not self.rabbitmq_password
        ):
            raise ValueError(
                "RABBITMQ_USER and RABBITMQ_PASSWORD must be set in production"
            )
        self.rabbitmq_url = os.getenv(
            "RABBITMQ_URL",
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}{self.rabbitmq_vhost}",
        )

    def get_redis_client(self, **kwargs) -> redis.Redis:
        """Return a cached Redis client with connection pooling.

        The first call creates the client; subsequent calls return the same
        instance.  Pass explicit **kwargs to force a new (non-cached) client.
        """
        # If caller passes custom kwargs, create a one-off client
        if kwargs:
            return self._create_redis_client(**kwargs)

        # Return cached singleton
        if self._redis_client is None:
            self._redis_client = self._create_redis_client()
        return self._redis_client

    def _create_redis_client(self, **kwargs) -> redis.Redis:
        """Create a new Redis client with environment configuration."""
        if "url" in kwargs or self.redis_url:
            redis_url = kwargs.get("url", self.redis_url)
            parsed = urlparse(redis_url)

            redis_kwargs = {
                "host": parsed.hostname or self.redis_host,
                "port": parsed.port or self.redis_port,
                "db": parsed.path.lstrip("/") if parsed.path else self.redis_db,
                "password": parsed.password or self.redis_password,
                "decode_responses": True,
                "connection_pool": redis.ConnectionPool(
                    max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
                    retry_on_timeout=True,
                    socket_keepalive=True,
                    socket_connect_timeout=5,
                ),
                **kwargs,
            }
        else:
            redis_kwargs = {
                "host": self.redis_host,
                "port": self.redis_port,
                "db": self.redis_db,
                "password": self.redis_password,
                "decode_responses": True,
                "connection_pool": redis.ConnectionPool(
                    max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
                    retry_on_timeout=True,
                    socket_keepalive=True,
                    socket_connect_timeout=5,
                ),
                **kwargs,
            }

        redis_kwargs.pop("url", None)
        return redis.Redis(**redis_kwargs)

    def get_celery_app(self, app_name: str, **kwargs) -> Celery:
        """Create a Celery app with environment configuration."""
        broker_url = kwargs.get("broker", self.rabbitmq_url)

        celery_kwargs = {
            "broker": broker_url,
            "backend": broker_url,  # Use same broker for backend
            **kwargs,
        }

        # Remove broker from kwargs to avoid duplicate
        celery_kwargs.pop("broker", None)

        app = Celery(app_name, **celery_kwargs)

        # Configure Celery with common settings
        app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
            task_time_limit=30 * 60,  # 30 minutes
            task_soft_time_limit=25 * 60,  # 25 minutes
            worker_prefetch_multiplier=1,
            worker_max_tasks_per_child=1000,
            task_acks_late=True,
            task_reject_on_worker_lost=True,
            task_default_retry_delay=60,
            task_max_retries=3,
            worker_cancel_long_running_tasks_on_connection_loss=True,
        )

        return app

    def validate_required_env_vars(self) -> dict[str, bool]:
        """Validate that required environment variables are set."""
        required_vars = {
            "REDIS_HOST": bool(self.redis_host),
            "REDIS_PORT": True,  # Has default
            "RABBITMQ_HOST": bool(self.rabbitmq_host),
            "RABBITMQ_PORT": True,  # Has default
        }

        return required_vars

    def get_connection_info(self) -> dict[str, Any]:
        """Get connection information for logging/debugging."""
        return {
            "redis": {
                "host": self.redis_host,
                "port": self.redis_port,
                "db": self.redis_db,
                "has_password": bool(self.redis_password),
                "url": self.redis_url.replace(self.redis_password or "", "***")
                if self.redis_password
                else self.redis_url,
            },
            "rabbitmq": {
                "host": self.rabbitmq_host,
                "port": self.rabbitmq_port,
                "user": self.rabbitmq_user,
                "vhost": self.rabbitmq_vhost,
                "has_password": bool(self.rabbitmq_password),
                "url": self.rabbitmq_url.replace(self.rabbitmq_password, "***")
                if self.rabbitmq_password
                else self.rabbitmq_url,
            },
            "environment": self.environment,
            "log_level": self.log_level,
        }


# Global configuration instance
config = Config()
