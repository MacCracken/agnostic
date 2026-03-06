# ADR-023: YEOMAN MCP Bridge WebSocket Support

**Status**: Accepted (updated with reconnection support)
**Date**: 2026-03-05
**Authors**: Agnostic team

---

## Context

YEOMAN's MCP bridge tools (`agnostic_task_status`, `agnostic_submit_qa`) poll the Agnostic REST API to check task status. Polling introduces latency (up to the poll interval) and wastes resources when tasks are idle. With the WebSocket real-time infrastructure already in place ([ADR-002](./002-realtime-communication-infrastructure.md)), we can offer push-based task updates to MCP bridge clients.

---

## Decision

Extend the existing WebSocket endpoint (`/ws/realtime`) with a `subscribe_task` message type. When a client sends `{"type": "subscribe_task", "task_id": "..."}`, the server subscribes that connection to the `task:{task_id}` Redis pub/sub channel. Task status transitions (pending, running, completed, failed) publish updates to this channel, which are forwarded to all subscribed WebSocket connections.

### How It Works

1. **MCP bridge connects** to `ws://host:8000/ws/realtime?token=...`
2. **Bridge sends** `{"type": "subscribe_task", "task_id": "task-abc"}`
3. **Server confirms** with a notification message
4. **API publishes** task status changes to `task:task-abc` Redis channel (in `_run_task_async`)
5. **RealtimeManager routes** the Redis message to all WebSocket connections subscribed to `task:task-abc`
6. **Bridge receives** `{"type": "task_status_changed", "task_id": "task-abc", "status": "completed", ...}`

### Task Status Publishing

In `webgui/api.py`, the `_run_task_async` function publishes to Redis on each status transition:

```python
redis_client.publish(f"task:{task_id}", json.dumps({
    "type": "task_status_changed",
    "task_id": task_id,
    "status": status,
    "timestamp": datetime.now(UTC).isoformat(),
    "result": result,
}))
```

### Channel Routing

In `webgui/realtime.py`, `_handle_redis_message` routes `task:*` channels to subscribed connections:

```python
elif channel.startswith("task:"):
    for conn_id, subscriptions in self.connection_subscriptions.items():
        if channel in subscriptions:
            target_connections.append(conn_id)
```

---

## Reconnection & Missed Message Recovery

Redis pub/sub is fire-and-forget — disconnected clients lose messages. To address this, messages are also buffered in **Redis Streams** alongside pub/sub.

### How It Works

1. Every message published to a channel is also appended to a Redis Stream (`stream:{channel}`) via `XADD`, capped at `REALTIME_STREAM_MAX_LEN` (default: 1000) entries.
2. Live messages include a `stream_id` field so clients can track their position.
3. On reconnection, the client includes `last_message_id` in the subscribe message:
   ```json
   {"type": "subscribe_task", "task_id": "task-abc", "last_message_id": "1709654321000-0"}
   ```
4. The server calls `XRANGE stream:task:task-abc (last_message_id +` to fetch missed messages (up to `REALTIME_STREAM_REPLAY_LIMIT`, default: 100).
5. Missed messages are sent with `"replayed": true` so the client can distinguish them from live updates.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REALTIME_STREAM_MAX_LEN` | `1000` | Max messages retained per stream |
| `REALTIME_STREAM_REPLAY_LIMIT` | `100` | Max messages replayed on reconnection |

### Backward Compatibility

- Clients that don't send `last_message_id` get the same behavior as before (no replay).
- REST API polling via `GET /api/tasks/{id}` remains fully supported.
- The `stream_id` field on live messages is informational — clients can ignore it.

---

## Files Modified

- `webgui/realtime.py` — `MessageBuffer` class (Redis Streams XADD/XRANGE), `replay_missed_messages()`, `subscribe_to_task()`, `subscribe_task`/`subscribe_session` client message handlers with `last_message_id` support
- `webgui/api.py` — `_run_task_async()` publishes to `task:{task_id}` Redis channel
- `webgui/static/js/dashboard.js` — Client-side `subscribe_task` message support
- `tests/unit/test_yeoman_websocket.py` — 14 unit tests (original)
- `tests/unit/test_message_buffer.py` — 15 unit tests for message buffering, replay, and reconnection

---

## Consequences

### Positive
- MCP bridge receives task updates in real-time (sub-second latency vs seconds of polling)
- Reduced API load — no more repeated `GET /api/tasks/{id}` calls
- Same infrastructure as session subscriptions — no new dependencies
- Disconnected clients can recover missed messages on reconnection

### Negative
- Redis Streams add storage overhead (mitigated by MAXLEN cap)
- Replay is bounded — very long disconnections may still miss messages beyond the buffer

### Neutral
- Polling via REST API remains fully supported — WebSocket is an optimization, not a replacement
