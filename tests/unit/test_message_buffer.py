"""Tests for WebSocket message buffering and reconnection replay."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestMessageBuffer:
    """Tests for Redis Streams-based MessageBuffer."""

    def _make_buffer(self):
        from webgui.realtime import MessageBuffer

        redis = MagicMock()
        buf = MessageBuffer(redis)
        return buf, redis

    def test_stream_key_format(self):
        """Stream keys are prefixed with 'stream:'."""
        buf, _ = self._make_buffer()
        assert buf._stream_key("task:abc") == "stream:task:abc"
        assert buf._stream_key("webgui:session:xyz") == "stream:webgui:session:xyz"

    def test_buffer_message_calls_xadd(self):
        """buffer_message calls XADD with maxlen."""
        buf, redis = self._make_buffer()
        redis.xadd.return_value = b"1234567890-0"

        msg = {"type": "task_status_changed", "timestamp": "now"}
        result = buf.buffer_message("task:abc", msg)

        redis.xadd.assert_called_once_with(
            "stream:task:abc",
            {"payload": json.dumps(msg)},
            maxlen=buf.max_len,
        )
        assert result == "1234567890-0"

    def test_buffer_message_returns_string_id(self):
        """buffer_message handles string return from xadd."""
        buf, redis = self._make_buffer()
        redis.xadd.return_value = "1234567890-0"

        result = buf.buffer_message("task:abc", {"type": "test"})
        assert result == "1234567890-0"

    def test_buffer_message_handles_error(self):
        """buffer_message returns None on error."""
        buf, redis = self._make_buffer()
        redis.xadd.side_effect = Exception("Redis down")

        result = buf.buffer_message("task:abc", {"type": "test"})
        assert result is None

    def test_get_messages_since_calls_xrange(self):
        """get_messages_since calls XRANGE with exclusive ID."""
        buf, redis = self._make_buffer()
        redis.xrange.return_value = [
            (
                b"100-0",
                {
                    b"payload": json.dumps(
                        {"type": "notification", "timestamp": "t1"}
                    ).encode()
                },
            ),
            (
                b"200-0",
                {
                    b"payload": json.dumps(
                        {"type": "notification", "timestamp": "t2"}
                    ).encode()
                },
            ),
        ]

        results = buf.get_messages_since("task:abc", "50-0")

        redis.xrange.assert_called_once_with(
            "stream:task:abc", min="(50-0", max="+", count=buf.replay_limit
        )
        assert len(results) == 2
        assert results[0] == ("100-0", {"type": "notification", "timestamp": "t1"})
        assert results[1] == ("200-0", {"type": "notification", "timestamp": "t2"})

    def test_get_messages_since_zero_uses_dash(self):
        """get_messages_since with '0-0' uses '-' for full range."""
        buf, redis = self._make_buffer()
        redis.xrange.return_value = []

        buf.get_messages_since("task:abc", "0-0")

        redis.xrange.assert_called_once_with(
            "stream:task:abc", min="-", max="+", count=buf.replay_limit
        )

    def test_get_messages_since_handles_error(self):
        """get_messages_since returns empty list on error."""
        buf, redis = self._make_buffer()
        redis.xrange.side_effect = Exception("Redis down")

        results = buf.get_messages_since("task:abc", "0-0")
        assert results == []

    def test_get_messages_since_handles_string_keys(self):
        """get_messages_since handles string (not bytes) keys from Redis."""
        buf, redis = self._make_buffer()
        redis.xrange.return_value = [
            (
                "100-0",
                {"payload": json.dumps({"type": "notification", "timestamp": "t1"})},
            ),
        ]

        results = buf.get_messages_since("task:abc", "0-0")
        assert len(results) == 1
        assert results[0][0] == "100-0"


class TestReplayMissedMessages:
    """Tests for RealtimeManager.replay_missed_messages."""

    @pytest.mark.asyncio
    async def test_replay_sends_messages_to_connection(self):
        """replay_missed_messages sends buffered messages to the websocket."""
        from webgui.realtime import RealtimeManager

        mgr = RealtimeManager.__new__(RealtimeManager)
        mgr.redis_client = MagicMock()
        mgr.websockets = {}
        mgr.connection_subscriptions = {}
        mgr.active_connections = {}
        mgr.pubsub = None
        mgr.background_tasks = set()

        mock_ws = AsyncMock()
        conn_id = "user1_abc"
        mgr.websockets[conn_id] = mock_ws

        mock_buffer = MagicMock()
        mock_buffer.get_messages_since.return_value = [
            (
                "100-0",
                {
                    "type": "task_status_changed",
                    "timestamp": "t1",
                    "session_id": None,
                    "agent_name": None,
                    "user_id": None,
                    "data": {"status": "running"},
                },
            ),
            (
                "200-0",
                {
                    "type": "task_status_changed",
                    "timestamp": "t2",
                    "session_id": None,
                    "agent_name": None,
                    "user_id": None,
                    "data": {"status": "completed"},
                },
            ),
        ]
        mgr.message_buffer = mock_buffer

        count = await mgr.replay_missed_messages(conn_id, "task:abc", "50-0")

        assert count == 2
        assert mock_ws.send_json.call_count == 2

        # Verify replayed messages include stream_id and replayed flag
        first_call = mock_ws.send_json.call_args_list[0][0][0]
        assert first_call["stream_id"] == "100-0"
        assert first_call["replayed"] is True

    @pytest.mark.asyncio
    async def test_replay_returns_zero_when_no_messages(self):
        """replay_missed_messages returns 0 when buffer is empty."""
        from webgui.realtime import RealtimeManager

        mgr = RealtimeManager.__new__(RealtimeManager)
        mgr.redis_client = MagicMock()
        mgr.websockets = {"conn1": AsyncMock()}
        mgr.connection_subscriptions = {}
        mgr.active_connections = {}
        mgr.pubsub = None
        mgr.background_tasks = set()

        mock_buffer = MagicMock()
        mock_buffer.get_messages_since.return_value = []
        mgr.message_buffer = mock_buffer

        count = await mgr.replay_missed_messages("conn1", "task:abc", "0-0")
        assert count == 0


class TestWebSocketReconnection:
    """Tests for client reconnection with last_message_id."""

    @pytest.mark.asyncio
    async def test_subscribe_session_with_last_message_id_triggers_replay(self):
        """subscribe_session with last_message_id replays missed messages."""
        from webgui.realtime import RealtimeManager, WebSocketHandler

        mgr = MagicMock(spec=RealtimeManager)
        mgr.subscribe_to_session = AsyncMock()
        mgr.replay_missed_messages = AsyncMock(return_value=3)

        handler = WebSocketHandler(mgr)
        await handler._handle_client_message(
            "conn1",
            {
                "type": "subscribe_session",
                "session_id": "sess-1",
                "last_message_id": "500-0",
            },
        )

        mgr.subscribe_to_session.assert_called_once_with("conn1", "sess-1")
        mgr.replay_missed_messages.assert_called_once_with(
            "conn1", "webgui:session:sess-1", "500-0"
        )

    @pytest.mark.asyncio
    async def test_subscribe_session_without_last_id_no_replay(self):
        """subscribe_session without last_message_id does not replay."""
        from webgui.realtime import RealtimeManager, WebSocketHandler

        mgr = MagicMock(spec=RealtimeManager)
        mgr.subscribe_to_session = AsyncMock()
        mgr.replay_missed_messages = AsyncMock()

        handler = WebSocketHandler(mgr)
        await handler._handle_client_message(
            "conn1",
            {
                "type": "subscribe_session",
                "session_id": "sess-1",
            },
        )

        mgr.subscribe_to_session.assert_called_once()
        mgr.replay_missed_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscribe_task_with_last_message_id_triggers_replay(self):
        """subscribe_task with last_message_id replays missed messages."""
        from webgui.realtime import RealtimeManager, WebSocketHandler

        mgr = MagicMock(spec=RealtimeManager)
        mgr.subscribe_to_task = AsyncMock()
        mgr.send_to_connection = AsyncMock()
        mgr.replay_missed_messages = AsyncMock(return_value=5)

        handler = WebSocketHandler(mgr)
        await handler._handle_client_message(
            "conn1",
            {
                "type": "subscribe_task",
                "task_id": "task-abc",
                "last_message_id": "300-0",
            },
        )

        mgr.subscribe_to_task.assert_called_once_with("conn1", "task-abc")
        mgr.replay_missed_messages.assert_called_once_with(
            "conn1", "task:task-abc", "300-0"
        )

    @pytest.mark.asyncio
    async def test_subscribe_task_without_last_id_no_replay(self):
        """subscribe_task without last_message_id does not replay."""
        from webgui.realtime import RealtimeManager, WebSocketHandler

        mgr = MagicMock(spec=RealtimeManager)
        mgr.subscribe_to_task = AsyncMock()
        mgr.send_to_connection = AsyncMock()
        mgr.replay_missed_messages = AsyncMock()

        handler = WebSocketHandler(mgr)
        await handler._handle_client_message(
            "conn1",
            {
                "type": "subscribe_task",
                "task_id": "task-abc",
            },
        )

        mgr.subscribe_to_task.assert_called_once()
        mgr.replay_missed_messages.assert_not_called()


class TestPublishEventBuffering:
    """Tests for publish_event buffering to streams."""

    @pytest.mark.asyncio
    async def test_publish_event_buffers_to_stream(self):
        """publish_event writes to both pub/sub and stream buffer."""
        from webgui.realtime import EventType, RealtimeManager, WebSocketMessage

        mgr = RealtimeManager.__new__(RealtimeManager)
        mgr.redis_client = MagicMock()
        mgr.websockets = {}
        mgr.connection_subscriptions = {}
        mgr.active_connections = {}
        mgr.pubsub = None
        mgr.background_tasks = set()

        mock_buffer = MagicMock()
        mock_buffer.buffer_message.return_value = "123-0"
        mgr.message_buffer = mock_buffer

        msg = WebSocketMessage(
            type=EventType.TASK_STATUS_CHANGED,
            timestamp="2026-01-01T00:00:00",
            data={"status": "completed"},
        )

        await mgr.publish_event("task:abc", msg)

        # Pub/sub publish
        mgr.redis_client.publish.assert_called_once()

        # Stream buffer
        mock_buffer.buffer_message.assert_called_once()
        buffered_data = mock_buffer.buffer_message.call_args[0][1]
        assert buffered_data["type"] == "task_status_changed"
