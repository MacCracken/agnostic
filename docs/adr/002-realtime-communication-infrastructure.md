# ADR-002: Real-time Communication Infrastructure

## Status
Accepted

## Context
The WebGUI needs to provide real-time updates for:
1. Agent task execution progress
2. Session status changes
3. Test results and notifications
4. Multi-user collaboration features
5. Dashboard metrics and monitoring

The system already uses Redis and RabbitMQ for agent communication, so we need to decide how to integrate the WebGUI's real-time requirements with this existing infrastructure.

## Decision
We selected **Redis Pub/Sub + WebSocket** architecture for real-time communication:

- **Redis Pub/Sub** - Message broker between agents and WebGUI
- **WebSocket (FastAPI)** - Real-time bidirectional communication with clients
- **Event-driven architecture** - Agents publish events, WebGUI subscribes and pushes to clients
- **Channel-based filtering** - Separate channels for different event types

## Consequences

### Positive
- **Scalability**: Redis handles high-throughput message distribution
- **Decoupling**: Agents don't need to know about WebGUI clients
- **Reliability**: Redis persistence and clustering support
- **Performance**: Low-latency message delivery
- **Multi-client**: Easy to broadcast to multiple users
- **Existing Infrastructure**: Leverages existing Redis deployment

### Negative
- **Complexity**: Additional layer of message translation
- **Memory Usage**: Pub/Sub messages in memory until consumed
- **Ordering**: No guaranteed message ordering across channels
- **Error Handling**: Need robust reconnection logic

## Rationale

### Evaluation of Alternatives

1. **Direct RabbitMQ to WebSocket**
   - Pros: Single message broker
   - Cons: Complex topic routing, heavier weight for pub/sub
   
2. **Server-Sent Events (SSE)**
   - Pros: Simpler than WebSocket, HTTP-based
   - Cons: Unidirectional only, less flexible
   
3. **WebSocket Polling (Long Polling)**
   - Pros: Works everywhere, no special infrastructure
   - Cons: High latency, resource intensive
   
4. **Redis Pub/Sub + WebSocket** (Selected)
   - Pros: High performance, scales well, leverages existing Redis
   - Cons: Additional infrastructure component

### Architecture Flow

```
Agent → Redis Pub/Sub → WebGUI Server → WebSocket → Browser Client
```

### Channel Strategy

- `webgui:session:{id}` - Session-specific updates
- `webgui:agent:{name}` - Agent-specific status
- `webgui:global` - System-wide notifications
- `webgui:user:{id}` - User-specific messages

### Message Format

```json
{
  "type": "session_status_changed",
  "timestamp": "2024-01-01T12:00:00Z",
  "session_id": "sess_123",
  "data": {
    "status": "testing",
    "progress": 45,
    "message": "Executing UI tests..."
  }
}
```

## Implementation Notes

The real-time infrastructure consists of:

1. **Publisher Layer** - Agents publish events to Redis channels
2. **Subscription Layer** - WebGUI subscribes to relevant channels
3. **Distribution Layer** - FastAPI WebSocket handlers broadcast to clients
4. **Client Layer** - JavaScript handles real-time UI updates

Key features:
- Automatic reconnection with exponential backoff
- Message filtering and routing based on user permissions
- Connection pooling for WebSocket management
- Graceful degradation to polling when WebSocket unavailable

## Implementation Update (2026-03-02)

The WebSocket Real-Time Dashboard has been fully implemented:

- **WebSocket endpoint wired**: `/ws/realtime` now connected in `webgui/app.py`
- **Realtime manager initialized on startup**: `on_event("startup")` initializes Redis pub/sub
- **Agent task notifications**: Subscribes to all agent task channels (`manager:tasks`, `senior:tasks`, etc.)
- **Dashboard integration**: `dashboard.js` auto-subscribes to active sessions on connect
- **Channel routing**: Agent task notifications broadcast to relevant session subscribers

Files modified:
- `webgui/app.py` - Added startup/shutdown events and WebSocket endpoint
- `webgui/realtime.py` - Added agent task channel subscriptions
- `webgui/static/js/dashboard.js` - Added session subscription on connect