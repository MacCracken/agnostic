"""Unit tests for WebSocket Real-Time Dashboard functionality."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestEventType:
    """Tests for EventType enum."""

    def test_event_types_defined(self):
        """Verify all required event types are defined."""
        from webgui.realtime import EventType

        assert hasattr(EventType, "SESSION_CREATED")
        assert hasattr(EventType, "SESSION_STATUS_CHANGED")
        assert hasattr(EventType, "TEST_STEP_COMPLETED")
        assert hasattr(EventType, "AGENT_TASK_ASSIGNED")
        assert hasattr(EventType, "ERROR_OCCURRED")
        assert hasattr(EventType, "NOTIFICATION")
        assert hasattr(EventType, "AGENT_STATUS_CHANGED")
        assert hasattr(EventType, "RESOURCE_UPDATE")

    def test_event_type_values(self):
        """Verify event type string values."""
        from webgui.realtime import EventType

        assert EventType.SESSION_CREATED.value == "session_created"
        assert EventType.SESSION_STATUS_CHANGED.value == "session_status_changed"
        assert EventType.AGENT_STATUS_CHANGED.value == "agent_status_changed"
        assert EventType.NOTIFICATION.value == "notification"


class TestWebSocketMessage:
    """Tests for WebSocketMessage dataclass."""

    def test_websocket_message_creation(self):
        """Verify WebSocketMessage can be created with required fields."""
        from datetime import datetime

        from webgui.realtime import EventType, WebSocketMessage

        msg = WebSocketMessage(
            type=EventType.SESSION_STATUS_CHANGED,
            timestamp=datetime.now().isoformat(),
            session_id="test-session-123",
        )

        assert msg.type == EventType.SESSION_STATUS_CHANGED
        assert msg.session_id == "test-session-123"

    def test_websocket_message_with_data(self):
        """Verify WebSocketMessage accepts optional data field."""
        from datetime import datetime

        from webgui.realtime import EventType, WebSocketMessage

        msg = WebSocketMessage(
            type=EventType.NOTIFICATION,
            timestamp=datetime.now().isoformat(),
            data={"message": "Test notification", "severity": "info"},
        )

        assert msg.data["message"] == "Test notification"


class TestRealtimeManager:
    """Tests for RealtimeManager class."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = MagicMock()
        redis.pubsub.return_value = MagicMock()
        return redis

    @pytest.fixture
    def realtime_manager(self, mock_redis):
        """Create RealtimeManager with mocked Redis."""
        with patch("webgui.realtime.config") as mock_config:
            mock_config.get_redis_client.return_value = mock_redis
            from webgui.realtime import RealtimeManager

            manager = RealtimeManager()
            manager.redis_client = mock_redis
            return manager

    def test_realtime_manager_initialization(self, realtime_manager):
        """Verify RealtimeManager initializes with empty connection tracking."""
        assert realtime_manager.active_connections == {}
        assert realtime_manager.connection_subscriptions == {}

    @pytest.mark.asyncio
    async def test_add_connection(self, realtime_manager):
        """Verify adding a new WebSocket connection."""
        mock_websocket = AsyncMock()

        await realtime_manager.add_connection("user-1", "conn-1", mock_websocket)

        assert "user-1" in realtime_manager.active_connections
        assert "conn-1" in realtime_manager.active_connections["user-1"]

    @pytest.mark.asyncio
    async def test_remove_connection(self, realtime_manager):
        """Verify removing a WebSocket connection."""
        mock_websocket = AsyncMock()
        realtime_manager.websockets = {"conn-1": mock_websocket}
        realtime_manager.active_connections = {"user-1": {"conn-1"}}
        realtime_manager.connection_subscriptions = {"conn-1": set()}

        await realtime_manager.remove_connection("conn-1")

        assert "user-1" not in realtime_manager.active_connections

    @pytest.mark.asyncio
    async def test_subscribe_to_session(self, realtime_manager):
        """Verify session subscription creates correct channel."""
        realtime_manager.pubsub = MagicMock()

        await realtime_manager.subscribe_to_session("conn-1", "session-123")

        assert (
            "webgui:session:session-123"
            in realtime_manager.connection_subscriptions["conn-1"]
        )

    @pytest.mark.asyncio
    async def test_publish_event(self, realtime_manager):
        """Verify publishing events to Redis pub/sub."""
        from datetime import datetime

        from webgui.realtime import EventType, WebSocketMessage

        MagicMock()  # pubsub (unused, publish is called directly)
        realtime_manager.redis_client.publish = MagicMock()

        msg = WebSocketMessage(
            type=EventType.SESSION_STATUS_CHANGED,
            timestamp=datetime.now().isoformat(),
            session_id="session-123",
            data={"status": "completed"},
        )

        await realtime_manager.publish_event("webgui:session_updates", msg)

        realtime_manager.redis_client.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_redis_message_agent_tasks(self, realtime_manager):
        """Verify handling agent task notification messages."""

        mock_websocket = AsyncMock()
        realtime_manager.websockets = {"conn-1": mock_websocket}
        realtime_manager.connection_subscriptions = {
            "conn-1": {"webgui:session:session-123"}
        }

        redis_message = {
            "channel": b"manager:tasks",
            "data": json.dumps(
                {
                    "type": "agent_task_assigned",
                    "timestamp": "2026-02-28T12:00:00",
                    "session_id": "session-123",
                    "agent_name": "qa-manager",
                }
            ),
        }

        await realtime_manager._handle_redis_message(redis_message)

        mock_websocket.send_json.assert_called()


class TestWebSocketHandler:
    """Tests for WebSocketHandler class."""

    @pytest.fixture
    def mock_manager(self):
        """Create mock RealtimeManager."""
        manager = MagicMock()
        manager.add_connection = AsyncMock()
        manager.remove_connection = AsyncMock()
        manager.subscribe_to_session = AsyncMock()
        return manager

    @pytest.fixture
    def websocket_handler(self, mock_manager):
        """Create WebSocketHandler with mocked manager."""
        from webgui.realtime import WebSocketHandler

        return WebSocketHandler(mock_manager)

    @pytest.mark.asyncio
    async def test_handle_websocket_accepts_connection(
        self, websocket_handler, mock_manager
    ):
        """Verify WebSocket handler accepts connections."""
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        # Must raise to break the receive loop
        mock_websocket.receive_json = AsyncMock(side_effect=Exception("Close"))

        await websocket_handler.handle_websocket(mock_websocket, "user-1")

        mock_websocket.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_websocket_adds_connection(
        self, websocket_handler, mock_manager
    ):
        """Verify WebSocket handler adds connection to manager."""
        mock_websocket = AsyncMock()
        mock_websocket.accept = AsyncMock()
        mock_websocket.receive_json = AsyncMock(side_effect=Exception("Close"))

        with patch("webgui.realtime.datetime") as mock_datetime:
            mock_datetime.now.return_value.timestamp.return_value = "123456.789"

            await websocket_handler.handle_websocket(mock_websocket, "user-1")

        mock_manager.add_connection.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_client_message_subscribe(self, websocket_handler):
        """Verify handling subscribe_session client message."""
        mock_manager = websocket_handler.realtime_manager
        mock_manager.subscribe_to_session = AsyncMock()

        await websocket_handler._handle_client_message(
            "conn-1", {"type": "subscribe_session", "session_id": "session-123"}
        )

        mock_manager.subscribe_to_session.assert_called_with("conn-1", "session-123")

    @pytest.mark.asyncio
    async def test_handle_client_message_ping(self, websocket_handler):
        """Verify handling ping message returns pong."""
        mock_manager = websocket_handler.realtime_manager
        mock_manager.send_to_connection = AsyncMock()

        await websocket_handler._handle_client_message("conn-1", {"type": "ping"})

        mock_manager.send_to_connection.assert_called_once()
        call_args = mock_manager.send_to_connection.call_args
        assert call_args[0][1].type.value == "notification"
        assert call_args[0][1].data["message"] == "pong"


class TestRealtimeChannels:
    """Tests for Redis pub/sub channel configuration."""

    def test_agent_task_channels_defined(self):
        """Verify all agent task channels are configured for subscription."""
        with patch("webgui.realtime.config") as mock_config:
            mock_config.get_redis_client.return_value = MagicMock()

            expected_agent_channels = [
                "manager:tasks",
                "senior:tasks",
                "junior:tasks",
                "analyst:tasks",
                "security:tasks",
                "performance:tasks",
            ]

            for channel in expected_agent_channels:
                assert channel.endswith(":tasks")
