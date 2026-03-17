"""Unit tests for YEOMAN MCP Bridge WebSocket support.

Tests the task subscription flow in the realtime module and
task status publishing in the API layer.
"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestTaskSubscription:
    """Tests for subscribe_to_task in RealtimeManager."""

    @pytest.fixture
    def manager(self):
        with patch("webgui.realtime.config") as mock_config:
            mock_config.get_redis_client.return_value = MagicMock()
            from webgui.realtime import RealtimeManager

            mgr = RealtimeManager()
            mgr.pubsub = MagicMock()
            return mgr

    @pytest.mark.asyncio
    async def test_subscribe_to_task_creates_channel(self, manager):
        manager.connection_subscriptions["conn-1"] = set()

        await manager.subscribe_to_task("conn-1", "task-abc")

        assert "task:task-abc" in manager.connection_subscriptions["conn-1"]

    @pytest.mark.asyncio
    async def test_subscribe_to_task_subscribes_redis(self, manager):
        manager.connection_subscriptions["conn-1"] = set()

        await manager.subscribe_to_task("conn-1", "task-abc")

        manager.pubsub.subscribe.assert_called_with("task:task-abc")

    @pytest.mark.asyncio
    async def test_subscribe_to_task_creates_subscription_set_if_missing(self, manager):
        # connection_subscriptions does not have conn-1 yet
        await manager.subscribe_to_task("conn-1", "task-xyz")

        assert "conn-1" in manager.connection_subscriptions
        assert "task:task-xyz" in manager.connection_subscriptions["conn-1"]

    @pytest.mark.asyncio
    async def test_subscribe_to_task_no_pubsub(self, manager):
        """When pubsub is not initialized, subscription still tracked locally."""
        manager.pubsub = None
        manager.connection_subscriptions["conn-1"] = set()

        await manager.subscribe_to_task("conn-1", "task-nopub")

        assert "task:task-nopub" in manager.connection_subscriptions["conn-1"]

    @pytest.mark.asyncio
    async def test_multiple_task_subscriptions(self, manager):
        manager.connection_subscriptions["conn-1"] = set()

        await manager.subscribe_to_task("conn-1", "task-1")
        await manager.subscribe_to_task("conn-1", "task-2")

        assert "task:task-1" in manager.connection_subscriptions["conn-1"]
        assert "task:task-2" in manager.connection_subscriptions["conn-1"]


class TestTaskStatusRouting:
    """Tests for task: channel routing in _handle_redis_message."""

    @pytest.fixture
    def manager(self):
        with patch("webgui.realtime.config") as mock_config:
            mock_config.get_redis_client.return_value = MagicMock()
            from webgui.realtime import RealtimeManager

            mgr = RealtimeManager()
            return mgr

    @pytest.mark.asyncio
    async def test_task_message_routed_to_subscriber(self, manager):
        mock_ws = AsyncMock()
        manager.websockets = {"conn-1": mock_ws}
        manager.connection_subscriptions = {"conn-1": {"task:task-abc"}}

        redis_message = {
            "channel": b"task:task-abc",
            "data": json.dumps(
                {
                    "type": "task_status_changed",
                    "task_id": "task-abc",
                    "status": "completed",
                    "timestamp": "2026-03-05T12:00:00",
                    "result": {"passed": True},
                }
            ),
        }

        await manager._handle_redis_message(redis_message)

        mock_ws.send_json.assert_called_once()
        sent = mock_ws.send_json.call_args[0][0]
        assert sent["type"] == "task_status_changed"

    @pytest.mark.asyncio
    async def test_task_message_not_routed_to_non_subscriber(self, manager):
        mock_ws = AsyncMock()
        manager.websockets = {"conn-1": mock_ws}
        manager.connection_subscriptions = {"conn-1": {"task:other-task"}}

        redis_message = {
            "channel": b"task:task-abc",
            "data": json.dumps(
                {
                    "type": "task_status_changed",
                    "task_id": "task-abc",
                    "status": "completed",
                    "timestamp": "2026-03-05T12:00:00",
                }
            ),
        }

        await manager._handle_redis_message(redis_message)

        mock_ws.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_message_routed_to_multiple_subscribers(self, manager):
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        manager.websockets = {"conn-1": mock_ws1, "conn-2": mock_ws2}
        manager.connection_subscriptions = {
            "conn-1": {"task:task-abc"},
            "conn-2": {"task:task-abc"},
        }

        redis_message = {
            "channel": b"task:task-abc",
            "data": json.dumps(
                {
                    "type": "task_status_changed",
                    "task_id": "task-abc",
                    "status": "running",
                    "timestamp": "2026-03-05T12:00:00",
                }
            ),
        }

        await manager._handle_redis_message(redis_message)

        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()


class TestClientSubscribeTaskMessage:
    """Tests for subscribe_task client message handling."""

    @pytest.fixture
    def handler(self):
        with patch("webgui.realtime.config") as mock_config:
            mock_config.get_redis_client.return_value = MagicMock()
            from webgui.realtime import RealtimeManager, WebSocketHandler

            mgr = MagicMock(spec=RealtimeManager)
            mgr.subscribe_to_task = AsyncMock()
            mgr.send_to_connection = AsyncMock()
            return WebSocketHandler(mgr)

    @pytest.mark.asyncio
    async def test_subscribe_task_message(self, handler):
        await handler._handle_client_message(
            "conn-1", {"type": "subscribe_task", "task_id": "task-xyz"}
        )

        handler.realtime_manager.subscribe_to_task.assert_called_with(
            "conn-1", "task-xyz"
        )

    @pytest.mark.asyncio
    async def test_subscribe_task_sends_confirmation(self, handler):
        await handler._handle_client_message(
            "conn-1", {"type": "subscribe_task", "task_id": "task-xyz"}
        )

        handler.realtime_manager.send_to_connection.assert_called_once()
        call_args = handler.realtime_manager.send_to_connection.call_args[0]
        assert call_args[0] == "conn-1"
        assert "task-xyz" in call_args[1].data["message"]

    @pytest.mark.asyncio
    async def test_subscribe_task_no_task_id_ignored(self, handler):
        await handler._handle_client_message("conn-1", {"type": "subscribe_task"})

        handler.realtime_manager.subscribe_to_task.assert_not_called()


class TestTaskStatusEventType:
    """Tests for the TASK_STATUS_CHANGED event type."""

    def test_task_status_changed_event_exists(self):
        from webgui.realtime import EventType

        assert hasattr(EventType, "TASK_STATUS_CHANGED")
        assert EventType.TASK_STATUS_CHANGED.value == "task_status_changed"
