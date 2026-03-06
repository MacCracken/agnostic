"""
Real-time Communication Module
WebSocket infrastructure for live updates and notifications.

Supports:
- Redis pub/sub for fire-and-forget broadcasts
- Redis Streams for message buffering and missed-message recovery
- Client reconnection with last_message_id replay
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# Add config path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.environment import config

logger = logging.getLogger(__name__)

# Maximum number of messages to retain per stream
STREAM_MAX_LEN = int(os.getenv("REALTIME_STREAM_MAX_LEN", "1000"))
# Maximum number of messages to replay on reconnection
STREAM_REPLAY_LIMIT = int(os.getenv("REALTIME_STREAM_REPLAY_LIMIT", "100"))


class EventType(Enum):
    SESSION_CREATED = "session_created"
    SESSION_STATUS_CHANGED = "session_status_changed"
    TEST_STEP_COMPLETED = "test_step_completed"
    AGENT_TASK_ASSIGNED = "agent_task_assigned"
    ERROR_OCCURRED = "error_occurred"
    NOTIFICATION = "notification"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    RESOURCE_UPDATE = "resource_update"
    TASK_STATUS_CHANGED = "task_status_changed"


@dataclass
class WebSocketMessage:
    type: EventType
    timestamp: str
    session_id: str | None = None
    agent_name: str | None = None
    user_id: str | None = None
    data: dict[str, Any] | None = None


class MessageBuffer:
    """Redis Streams–based message buffer for missed-message recovery.

    Each subscribed channel gets a stream key: ``stream:{channel}``.
    Messages are appended with XADD (capped at STREAM_MAX_LEN).
    On reconnection the client provides a ``last_message_id`` and
    receives all buffered messages since that ID via XRANGE.
    """

    def __init__(self, redis_client):
        self.redis = redis_client
        self.max_len = STREAM_MAX_LEN
        self.replay_limit = STREAM_REPLAY_LIMIT

    def _stream_key(self, channel: str) -> str:
        return f"stream:{channel}"

    def buffer_message(self, channel: str, message_data: dict[str, Any]) -> str | None:
        """Append a message to the channel's stream. Returns the stream ID."""
        try:
            stream_key = self._stream_key(channel)
            msg_id = self.redis.xadd(
                stream_key,
                {"payload": json.dumps(message_data)},
                maxlen=self.max_len,
            )
            return msg_id if isinstance(msg_id, str) else msg_id.decode() if msg_id else None
        except Exception as e:
            logger.debug(f"Stream buffer write failed for {channel}: {e}")
            return None

    def get_messages_since(
        self, channel: str, last_id: str = "0-0"
    ) -> list[tuple[str, dict[str, Any]]]:
        """Read messages from the stream after *last_id*.

        Returns list of ``(stream_id, parsed_payload)`` tuples.
        """
        try:
            stream_key = self._stream_key(channel)
            # XRANGE is inclusive on min; use '(' prefix for exclusive
            exclusive_id = f"({last_id}" if last_id != "0-0" else "-"
            entries = self.redis.xrange(
                stream_key, min=exclusive_id, max="+", count=self.replay_limit
            )
            results = []
            for entry_id, fields in entries:
                eid = entry_id if isinstance(entry_id, str) else entry_id.decode()
                raw = fields.get(b"payload") or fields.get("payload")
                if raw:
                    payload = json.loads(raw if isinstance(raw, str) else raw.decode())
                    results.append((eid, payload))
            return results
        except Exception as e:
            logger.debug(f"Stream replay failed for {channel}: {e}")
            return []


class RealtimeManager:
    """Manages WebSocket connections and real-time communication"""

    def __init__(self):
        self.redis_client = config.get_redis_client()
        self.active_connections: dict[
            str, set[str]
        ] = {}  # user_id -> set of connection_ids
        self.connection_subscriptions: dict[
            str, set[str]
        ] = {}  # connection_id -> set of channels
        self.websockets: dict[str, Any] = {}  # connection_id -> websocket
        self.pubsub = None
        self.background_tasks = set()
        self.message_buffer = MessageBuffer(self.redis_client)

    async def initialize(self):
        """Initialize Redis pub/sub subscription"""
        try:
            self.pubsub = self.redis_client.pubsub()

            # Subscribe to all webgui channels
            channels = [
                "webgui:session_updates",
                "webgui:agent_activity",
                "webgui:test_progress",
                "webgui:notifications",
                "webgui:resource_updates",
            ]

            # Also subscribe to agent task notifications for real-time task updates
            agent_channels = [
                "manager:tasks",
                "senior:tasks",
                "junior:tasks",
                "analyst:tasks",
                "security:tasks",
                "performance:tasks",
            ]
            channels.extend(agent_channels)

            self.pubsub.subscribe(*channels)
            logger.info(f"Subscribed to {len(channels)} channels")

            # Start background listener
            task = asyncio.create_task(self._redis_listener())
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)

        except Exception as e:
            logger.error(f"Failed to initialize pub/sub: {e}")

    async def add_connection(self, user_id: str, connection_id: str, websocket):
        """Add a new WebSocket connection"""
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()

        self.active_connections[user_id].add(connection_id)
        self.connection_subscriptions[connection_id] = set()

        # Store websocket reference
        self.websockets[connection_id] = websocket

        logger.info(f"Added connection {connection_id} for user {user_id}")

        # Send welcome message
        await self.send_to_connection(
            connection_id,
            WebSocketMessage(
                type=EventType.NOTIFICATION,
                timestamp=datetime.now().isoformat(),
                user_id=user_id,
                data={"message": "Connected to real-time updates"},
            ),
        )

    async def remove_connection(self, connection_id: str):
        """Remove a WebSocket connection"""
        # Find user_id for this connection
        user_id = None
        for uid, connections in self.active_connections.items():
            if connection_id in connections:
                user_id = uid
                connections.remove(connection_id)
                break

        if user_id and not self.active_connections[user_id]:
            del self.active_connections[user_id]

        # Clean up subscriptions
        if connection_id in self.connection_subscriptions:
            del self.connection_subscriptions[connection_id]

        # Clean up websocket reference
        self.websockets.pop(connection_id, None)

        logger.info(f"Removed connection {connection_id} for user {user_id}")

    async def subscribe_to_session(self, connection_id: str, session_id: str):
        """Subscribe connection to specific session updates"""
        if connection_id not in self.connection_subscriptions:
            self.connection_subscriptions[connection_id] = set()

        channel = f"webgui:session:{session_id}"
        self.connection_subscriptions[connection_id].add(channel)

        # Also subscribe to Redis channel
        if self.pubsub:
            self.pubsub.subscribe(channel)

    async def subscribe_to_task(self, connection_id: str, task_id: str):
        """Subscribe connection to specific task updates (for MCP bridge polling replacement)"""
        if connection_id not in self.connection_subscriptions:
            self.connection_subscriptions[connection_id] = set()

        channel = f"task:{task_id}"
        self.connection_subscriptions[connection_id].add(channel)

        # Subscribe to task status changes in Redis
        if self.pubsub:
            self.pubsub.subscribe(channel)

        logger.info(f"Connection {connection_id} subscribed to task {task_id}")

    async def unsubscribe_from_session(self, connection_id: str, session_id: str):
        """Unsubscribe connection from specific session updates"""
        if connection_id in self.connection_subscriptions:
            channel = f"webgui:session:{session_id}"
            self.connection_subscriptions[connection_id].discard(channel)

        logger.info(
            f"Connection {connection_id} unsubscribed from session {session_id}"
        )

    async def broadcast_to_user(self, user_id: str, message: WebSocketMessage):
        """Send message to all connections for a user"""
        if user_id in self.active_connections:
            for connection_id in self.active_connections[user_id]:
                await self.send_to_connection(connection_id, message)

    async def send_to_connection(self, connection_id: str, message: WebSocketMessage):
        """Send message to specific connection"""
        try:
            if connection_id in self.websockets:
                websocket = self.websockets[connection_id]
                await websocket.send_json(
                    {
                        "type": message.type.value,
                        "timestamp": message.timestamp,
                        "session_id": message.session_id,
                        "agent_name": message.agent_name,
                        "user_id": message.user_id,
                        "data": message.data,
                    }
                )
        except Exception as e:
            logger.error(f"Error sending to connection {connection_id}: {e}")
            # Connection might be dead, clean it up
            await self.remove_connection(connection_id)

    async def publish_event(self, channel: str, message: WebSocketMessage):
        """Publish event to Redis pub/sub and buffer in stream"""
        try:
            event_data = {
                "type": message.type.value,
                "timestamp": message.timestamp,
                "session_id": message.session_id,
                "agent_name": message.agent_name,
                "user_id": message.user_id,
                "data": message.data,
            }

            self.redis_client.publish(channel, json.dumps(event_data))

            # Buffer in Redis Stream for replay on reconnection
            self.message_buffer.buffer_message(channel, event_data)

            logger.debug(f"Published event to {channel}: {message.type.value}")

        except Exception as e:
            logger.error(f"Error publishing event to {channel}: {e}")

    async def replay_missed_messages(
        self, connection_id: str, channel: str, last_message_id: str
    ) -> int:
        """Replay messages the client missed while disconnected.

        Returns the number of replayed messages.
        """
        messages = self.message_buffer.get_messages_since(channel, last_message_id)
        count = 0
        for stream_id, data in messages:
            try:
                msg = WebSocketMessage(
                    type=EventType(data["type"]),
                    timestamp=data["timestamp"],
                    session_id=data.get("session_id"),
                    agent_name=data.get("agent_name"),
                    user_id=data.get("user_id"),
                    data=data.get("data"),
                )
                # Attach stream_id so client can track position
                if connection_id in self.websockets:
                    websocket = self.websockets[connection_id]
                    payload = {
                        "type": msg.type.value,
                        "timestamp": msg.timestamp,
                        "session_id": msg.session_id,
                        "agent_name": msg.agent_name,
                        "user_id": msg.user_id,
                        "data": msg.data,
                        "stream_id": stream_id,
                        "replayed": True,
                    }
                    await websocket.send_json(payload)
                    count += 1
            except Exception as e:
                logger.error(f"Error replaying message {stream_id}: {e}")

        if count:
            logger.info(f"Replayed {count} missed messages for {connection_id} on {channel}")
        return count

    async def _redis_listener(self):
        """Background task to listen to Redis pub/sub messages"""
        logger.info("Starting Redis pub/sub listener")

        try:
            while True:
                if self.pubsub:
                    message = self.pubsub.get_message(timeout=1.0)
                    if message and message["type"] == "message":
                        await self._handle_redis_message(message)

                await asyncio.sleep(0.01)  # Small delay to prevent CPU spin

        except Exception as e:
            logger.error(f"Redis listener error: {e}")
            # Restart listener
            await asyncio.sleep(5)
            task = asyncio.create_task(self._redis_listener())
            self.background_tasks.add(task)
            task.add_done_callback(self.background_tasks.discard)

    async def _handle_redis_message(self, redis_message):
        """Handle incoming Redis pub/sub message and buffer to stream"""
        try:
            channel = redis_message["channel"].decode()
            data = json.loads(redis_message["data"])

            # Buffer message in Redis Stream for replay
            stream_id = self.message_buffer.buffer_message(channel, data)

            # Determine target connections
            target_connections = []

            if channel.startswith("webgui:session:"):
                # Session-specific updates
                session_id = channel.split(":")[-1]
                for conn_id, subscriptions in self.connection_subscriptions.items():
                    if channel in subscriptions:
                        target_connections.append(conn_id)

            elif channel.startswith("manager:tasks") or channel.endswith(":tasks"):
                # Agent task notifications - broadcast to connections subscribed to the session
                session_id = data.get("session_id")
                if session_id:
                    session_channel = f"webgui:session:{session_id}"
                    for conn_id, subscriptions in self.connection_subscriptions.items():
                        if session_channel in subscriptions:
                            target_connections.append(conn_id)
                    # Also notify all connected clients about task activity
                    target_connections.extend(list(self.connection_subscriptions.keys()))

            elif channel == "webgui:notifications":
                # Global notifications - send to all connections
                target_connections = list(self.connection_subscriptions.keys())

            elif channel == "webgui:agent_activity":
                # Agent activity - send to connections subscribed to relevant sessions
                session_id = data.get("session_id")
                if session_id:
                    session_channel = f"webgui:session:{session_id}"
                    for conn_id, subscriptions in self.connection_subscriptions.items():
                        if session_channel in subscriptions:
                            target_connections.append(conn_id)

            elif channel.startswith("task:"):
                # Task-specific updates (for MCP bridge WebSocket support)
                for conn_id, subscriptions in self.connection_subscriptions.items():
                    if channel in subscriptions:
                        target_connections.append(conn_id)

            # Send to target connections with stream_id for tracking
            for connection_id in target_connections:
                message = WebSocketMessage(
                    type=EventType(data["type"]),
                    timestamp=data["timestamp"],
                    session_id=data.get("session_id"),
                    agent_name=data.get("agent_name"),
                    user_id=data.get("user_id"),
                    data=data.get("data"),
                )
                if stream_id and connection_id in self.websockets:
                    # Include stream_id so client can track position
                    websocket = self.websockets[connection_id]
                    payload = {
                        "type": message.type.value,
                        "timestamp": message.timestamp,
                        "session_id": message.session_id,
                        "agent_name": message.agent_name,
                        "user_id": message.user_id,
                        "data": message.data,
                        "stream_id": stream_id,
                    }
                    try:
                        await websocket.send_json(payload)
                    except Exception as e:
                        logger.error(f"Error sending to connection {connection_id}: {e}")
                        await self.remove_connection(connection_id)
                else:
                    await self.send_to_connection(connection_id, message)

        except Exception as e:
            logger.error(f"Error handling Redis message: {e}")

    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up real-time manager")

        # Cancel background tasks
        for task in self.background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close pub/sub
        if self.pubsub:
            self.pubsub.close()

        # Clear connections
        self.active_connections.clear()
        self.connection_subscriptions.clear()
        self.websockets.clear()


class WebSocketHandler:
    """FastAPI WebSocket endpoint handler"""

    def __init__(self, realtime_manager: RealtimeManager):
        self.realtime_manager = realtime_manager

    async def handle_websocket(self, websocket, user_id: str):
        """Handle WebSocket connection lifecycle"""
        connection_id = f"{user_id}_{uuid.uuid4().hex}"

        try:
            # Accept connection
            await websocket.accept()

            # Add to manager
            await self.realtime_manager.add_connection(
                user_id, connection_id, websocket
            )

            # Handle messages
            while True:
                try:
                    data = await websocket.receive_json()
                    await self._handle_client_message(connection_id, data)

                except Exception as e:
                    logger.error(f"Error handling client message: {e}")
                    break

        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
        finally:
            # Clean up
            await self.realtime_manager.remove_connection(connection_id)

    async def _handle_client_message(self, connection_id: str, data: dict[str, Any]):
        """Handle incoming message from client"""
        message_type = data.get("type")

        if message_type == "subscribe_session":
            session_id = data.get("session_id")
            if session_id:
                await self.realtime_manager.subscribe_to_session(
                    connection_id, session_id
                )
                # Replay missed messages if client provides last_message_id
                last_id = data.get("last_message_id")
                if last_id:
                    channel = f"webgui:session:{session_id}"
                    await self.realtime_manager.replay_missed_messages(
                        connection_id, channel, last_id
                    )

        elif message_type == "unsubscribe_session":
            session_id = data.get("session_id")
            if session_id:
                await self.realtime_manager.unsubscribe_from_session(
                    connection_id, session_id
                )

        elif message_type == "subscribe_task":
            # Subscribe to task updates (for MCP bridge polling replacement)
            task_id = data.get("task_id")
            if task_id:
                await self.realtime_manager.subscribe_to_task(connection_id, task_id)
                await self.realtime_manager.send_to_connection(
                    connection_id,
                    WebSocketMessage(
                        type=EventType.NOTIFICATION,
                        timestamp=datetime.now().isoformat(),
                        data={"message": f"Subscribed to task {task_id}"},
                    ),
                )
                # Replay missed messages if client provides last_message_id
                last_id = data.get("last_message_id")
                if last_id:
                    channel = f"task:{task_id}"
                    count = await self.realtime_manager.replay_missed_messages(
                        connection_id, channel, last_id
                    )
                    if count:
                        await self.realtime_manager.send_to_connection(
                            connection_id,
                            WebSocketMessage(
                                type=EventType.NOTIFICATION,
                                timestamp=datetime.now().isoformat(),
                                data={"message": f"Replayed {count} missed messages"},
                            ),
                        )

        elif message_type == "ping":
            # Respond with pong
            await self.realtime_manager.send_to_connection(
                connection_id,
                WebSocketMessage(
                    type=EventType.NOTIFICATION,
                    timestamp=datetime.now().isoformat(),
                    data={"message": "pong"},
                ),
            )


# Singleton instance
realtime_manager = RealtimeManager()
websocket_handler = WebSocketHandler(realtime_manager)
