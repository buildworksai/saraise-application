# SARAISE Real-Time Architecture

**Status:** Authoritative — Freeze Blocking  
**Version:** 1.0.0  
**Last Updated:** January 5, 2026

This document defines the **real-time communication patterns** for SARAISE. Real-time capabilities are critical for live dashboards, notifications, and collaborative features.

---

## 0) Non-Negotiable Principles

1. **Real-time is tenant-isolated.** No cross-tenant message leakage.
2. **Connections are authenticated.** Anonymous WebSocket connections are forbidden.
3. **Real-time supplements, not replaces.** REST APIs remain source of truth.
4. **Graceful degradation required.** App must work without WebSocket.
5. **Scale horizontally.** No single point of failure.

---

## 1) Use Cases

### 1.1 Supported Use Cases

| Use Case | Priority | Implementation Phase |
|----------|----------|---------------------|
| Dashboard live updates | P1 | Phase 8 |
| Notification delivery | P1 | Phase 8 |
| Workflow state changes | P2 | Phase 8 |
| AI agent execution status | P2 | Phase 8 |
| Collaborative editing | P3 | Phase 9+ |
| Presence (who's online) | P3 | Phase 9+ |

### 1.2 NOT Supported via Real-Time

- Data mutations (use REST API)
- Large data transfers (use file upload)
- Authentication (use HTTP endpoints)

---

## 2) Connection Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Load Balancer                           │
│                    (WebSocket-aware, sticky sessions)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┼───────────────┐
                │               │               │
         ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐
         │  WS Server  │ │  WS Server  │ │  WS Server  │
         │   Node 1    │ │   Node 2    │ │   Node 3    │
         └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
                │               │               │
                └───────────────┼───────────────┘
                                │
                    ┌───────────┴───────────┐
                    │     Redis Pub/Sub     │
                    │    (Message Broker)   │
                    └───────────────────────┘
```

### 2.2 Connection Flow

1. Client authenticates via REST API (session established)
2. Client opens WebSocket with session cookie
3. Server validates session before accepting connection
4. Server subscribes client to tenant-scoped channels
5. Messages flow bidirectionally through channels

### 2.3 Connection URL

```
wss://app.saraise.com/ws/?token={connection_token}
```

Connection token:
- Short-lived (5 minutes)
- Single-use
- Obtained from REST endpoint
- Contains encrypted session reference

---

## 3) Authentication & Authorization

### 3.1 WebSocket Authentication (MANDATORY)

```python
# backend/src/core/ws_auth.py

async def authenticate_websocket(
    websocket: WebSocket,
    token: str
) -> Optional[SessionContext]:
    """Authenticate WebSocket connection."""

    # 1. Validate connection token
    token_data = validate_connection_token(token)
    if not token_data:
        await websocket.close(code=4001, reason="Invalid token")
        return None

    # 2. Validate session is still active
    session = await get_session(token_data["session_id"])
    if not session or session.is_expired:
        await websocket.close(code=4002, reason="Session invalid")
        return None

    # 3. Validate tenant
    tenant_id = session.tenant_id
    if not await is_tenant_active(tenant_id):
        await websocket.close(code=4003, reason="Tenant inactive")
        return None

    return SessionContext(
        session_id=session.id,
        user_id=session.user_id,
        tenant_id=tenant_id,
    )
```

### 3.2 Channel Authorization

Users can only subscribe to channels they have access to:

```python
CHANNEL_PERMISSIONS = {
    "tenant.{tenant_id}.notifications": ["tenant_user"],
    "tenant.{tenant_id}.dashboard": ["tenant_user"],
    "tenant.{tenant_id}.admin": ["tenant_admin"],
    "tenant.{tenant_id}.workflow.{workflow_id}": ["workflow_participant"],
}
```

### 3.3 Connection Token Endpoint

```python
# backend/src/core/ws_api.py

@router.post("/api/v1/ws/token")
def get_websocket_token(request: Request) -> dict:
    """Generate short-lived WebSocket connection token."""

    # Requires valid session
    session = get_current_session(request)
    if not session:
        raise HTTPException(401, "Authentication required")

    token = create_connection_token(
        session_id=session.id,
        tenant_id=session.tenant_id,
        expires_in=300,  # 5 minutes
    )

    return {"token": token, "expires_in": 300}
```

---

## 4) Channel Architecture

### 4.1 Channel Naming Convention

```
{scope}.{tenant_id}.{resource_type}.{resource_id?}

Examples:
tenant.abc123.notifications
tenant.abc123.dashboard.metrics
tenant.abc123.workflow.wf-001
tenant.abc123.agent.agent-001.execution
platform.health  # Platform-level only
```

### 4.2 Channel Types

| Channel Type | Pattern | Use Case |
|--------------|---------|----------|
| Tenant broadcast | `tenant.{tenant_id}.{topic}` | All tenant users |
| User-specific | `tenant.{tenant_id}.user.{user_id}` | Personal notifications |
| Resource-specific | `tenant.{tenant_id}.{type}.{id}` | Resource updates |
| Platform | `platform.{topic}` | System-wide (admin only) |

### 4.3 Channel Isolation (CRITICAL)

```python
def validate_channel_access(
    session: SessionContext,
    channel: str
) -> bool:
    """Validate user can access channel."""

    # Extract tenant from channel name
    channel_tenant = extract_tenant_from_channel(channel)

    # CRITICAL: Tenant isolation check
    if channel_tenant and channel_tenant != session.tenant_id:
        return False  # Cross-tenant access denied

    # Check role-based access
    required_roles = get_channel_required_roles(channel)
    return any(role in session.roles for role in required_roles)
```

---

## 5) Message Protocol

### 5.1 Message Envelope

All messages use JSON envelope:

```json
{
  "type": "message_type",
  "channel": "tenant.abc123.dashboard",
  "timestamp": "2026-01-05T12:00:00.000Z",
  "payload": {
    // Type-specific data
  }
}
```

### 5.2 Client → Server Messages

| Type | Purpose | Payload |
|------|---------|---------|
| `subscribe` | Join channel | `{ "channel": "..." }` |
| `unsubscribe` | Leave channel | `{ "channel": "..." }` |
| `ping` | Keep-alive | `{}` |

### 5.3 Server → Client Messages

| Type | Purpose | Payload |
|------|---------|---------|
| `subscribed` | Confirm subscription | `{ "channel": "..." }` |
| `unsubscribed` | Confirm unsubscription | `{ "channel": "..." }` |
| `pong` | Keep-alive response | `{}` |
| `message` | Data message | `{ "data": {...} }` |
| `error` | Error notification | `{ "code": "...", "message": "..." }` |

### 5.4 Example Messages

**Client subscribing to dashboard:**

```json
// Client → Server
{
  "type": "subscribe",
  "channel": "tenant.abc123.dashboard.metrics"
}

// Server → Client
{
  "type": "subscribed",
  "channel": "tenant.abc123.dashboard.metrics",
  "timestamp": "2026-01-05T12:00:00.000Z"
}
```

**Server pushing metric update:**

```json
{
  "type": "message",
  "channel": "tenant.abc123.dashboard.metrics",
  "timestamp": "2026-01-05T12:00:01.000Z",
  "payload": {
    "event": "metric.updated",
    "data": {
      "metric_name": "active_users",
      "value": 142,
      "timestamp": "2026-01-05T12:00:00.000Z"
    }
  }
}
```

---

## 6) Scaling Architecture

### 6.1 Horizontal Scaling

- WebSocket servers are stateless
- Connection state stored in Redis
- Redis Pub/Sub for cross-server communication
- Sticky sessions for connection stability (not required)

### 6.2 Redis Pub/Sub Channels

```
saraise:ws:tenant:{tenant_id}:{channel_name}
saraise:ws:platform:{channel_name}
```

### 6.3 Connection State (Redis)

```json
// Key: saraise:ws:connection:{connection_id}
{
  "session_id": "sess-123",
  "user_id": "user-456",
  "tenant_id": "tenant-789",
  "server_id": "ws-server-1",
  "connected_at": "2026-01-05T12:00:00.000Z",
  "channels": ["tenant.789.notifications", "tenant.789.dashboard"]
}
```

### 6.4 Scaling Limits

| Metric | Limit | Notes |
|--------|-------|-------|
| Connections per server | 10,000 | Node.js optimized |
| Channels per connection | 50 | Memory constraint |
| Messages per second (inbound) | 100 | Per connection |
| Messages per second (outbound) | 1,000 | Per connection |
| Max message size | 64KB | Larger = HTTP upload |

---

## 7) Frontend Integration

### 7.1 WebSocket Client Service

```typescript
// frontend/src/services/websocket-client.ts

import { apiClient } from './api-client';

type MessageHandler = (message: WebSocketMessage) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  async connect(): Promise<void> {
    // Get connection token from REST API
    const { token } = await apiClient.post<{ token: string }>(
      '/api/v1/ws/token'
    );

    const wsUrl = `${this.getWsBaseUrl()}/ws/?token=${token}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = this.handleOpen.bind(this);
    this.ws.onmessage = this.handleMessage.bind(this);
    this.ws.onclose = this.handleClose.bind(this);
    this.ws.onerror = this.handleError.bind(this);
  }

  subscribe(channel: string, handler: MessageHandler): () => void {
    // Send subscribe message
    this.send({ type: 'subscribe', channel });

    // Register handler
    if (!this.handlers.has(channel)) {
      this.handlers.set(channel, new Set());
    }
    this.handlers.get(channel)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.handlers.get(channel)?.delete(handler);
      if (this.handlers.get(channel)?.size === 0) {
        this.send({ type: 'unsubscribe', channel });
        this.handlers.delete(channel);
      }
    };
  }

  private handleMessage(event: MessageEvent): void {
    const message = JSON.parse(event.data);

    if (message.type === 'message' && message.channel) {
      const handlers = this.handlers.get(message.channel);
      handlers?.forEach(handler => handler(message));
    }
  }

  private handleClose(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      const delay = Math.pow(2, this.reconnectAttempts) * 1000;
      setTimeout(() => {
        this.reconnectAttempts++;
        this.connect();
      }, delay);
    }
  }

  private getWsBaseUrl(): string {
    const httpUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
    return httpUrl.replace('http', 'ws');
  }
}

export const wsClient = new WebSocketClient();
```

### 7.2 React Hook for Real-Time Data

```typescript
// frontend/src/hooks/useRealtimeChannel.ts

import { useEffect, useState } from 'react';
import { wsClient } from '@/services/websocket-client';

export function useRealtimeChannel<T>(
  channel: string,
  initialData: T
): { data: T; isConnected: boolean } {
  const [data, setData] = useState<T>(initialData);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    wsClient.connect().then(() => setIsConnected(true));

    const unsubscribe = wsClient.subscribe(channel, (message) => {
      if (message.payload?.data) {
        setData(prev => ({
          ...prev,
          ...message.payload.data,
        }));
      }
    });

    return () => {
      unsubscribe();
    };
  }, [channel]);

  return { data, isConnected };
}
```

### 7.3 Dashboard Integration Example

```typescript
// frontend/src/modules/platform_management/pages/Dashboard.tsx

import { useRealtimeChannel } from '@/hooks/useRealtimeChannel';
import { useAuthStore } from '@/stores/auth-store';

export function Dashboard() {
  const tenantId = useAuthStore(state => state.tenantId);
  const channel = `tenant.${tenantId}.dashboard.metrics`;

  const { data: metrics, isConnected } = useRealtimeChannel(
    channel,
    { activeUsers: 0, requestsPerMinute: 0 }
  );

  return (
    <div>
      <ConnectionStatus connected={isConnected} />
      <MetricCard title="Active Users" value={metrics.activeUsers} />
      <MetricCard title="Requests/min" value={metrics.requestsPerMinute} />
    </div>
  );
}
```

---

## 8) Backend Publishing

### 8.1 Publishing Service

```python
# backend/src/core/realtime_publisher.py

import json
import redis.asyncio as redis

class RealtimePublisher:
    """Publish messages to WebSocket channels."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def publish(
        self,
        channel: str,
        event: str,
        data: dict,
        tenant_id: str = None
    ) -> None:
        """Publish message to channel."""

        # Validate tenant isolation
        if tenant_id:
            channel_tenant = self._extract_tenant(channel)
            if channel_tenant and channel_tenant != tenant_id:
                raise ValueError("Cross-tenant publish forbidden")

        message = {
            "type": "message",
            "channel": channel,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {
                "event": event,
                "data": data,
            }
        }

        redis_channel = f"saraise:ws:{channel}"
        await self.redis.publish(redis_channel, json.dumps(message))

    async def publish_to_user(
        self,
        tenant_id: str,
        user_id: str,
        event: str,
        data: dict
    ) -> None:
        """Publish message to specific user."""
        channel = f"tenant.{tenant_id}.user.{user_id}"
        await self.publish(channel, event, data, tenant_id)
```

### 8.2 Publishing from Services

```python
# backend/src/modules/workflow/services.py

class WorkflowService:
    def __init__(self, realtime: RealtimePublisher):
        self.realtime = realtime

    async def transition_workflow(
        self,
        workflow_id: str,
        tenant_id: str,
        new_state: str
    ) -> Workflow:
        # Update workflow state
        workflow = await self._update_state(workflow_id, new_state)

        # Publish real-time update
        await self.realtime.publish(
            channel=f"tenant.{tenant_id}.workflow.{workflow_id}",
            event="workflow.transitioned",
            data={
                "workflow_id": workflow_id,
                "previous_state": workflow.previous_state,
                "current_state": new_state,
            },
            tenant_id=tenant_id
        )

        return workflow
```

---

## 9) Error Handling & Resilience

### 9.1 Client Reconnection

- Exponential backoff: 1s, 2s, 4s, 8s, 16s
- Max reconnection attempts: 5
- After max attempts: fallback to polling

### 9.2 Server Disconnect Codes

| Code | Meaning | Client Action |
|------|---------|---------------|
| 1000 | Normal close | No action |
| 1001 | Going away | Reconnect |
| 4001 | Invalid token | Re-authenticate |
| 4002 | Session invalid | Re-authenticate |
| 4003 | Tenant inactive | Show error |
| 4004 | Rate limited | Wait and retry |

### 9.3 Graceful Degradation

If WebSocket unavailable:
1. Show "real-time updates unavailable" indicator
2. Fall back to polling (30-second interval)
3. All functionality must work via REST API

---

## 10) Monitoring

### 10.1 Required Metrics

- `ws_connections_total` (gauge, by tenant)
- `ws_messages_received_total` (counter)
- `ws_messages_sent_total` (counter)
- `ws_connection_duration_seconds` (histogram)
- `ws_errors_total` (counter, by error type)

### 10.2 Alerting

| Metric | Warning | Critical |
|--------|---------|----------|
| Connection errors/min | >100 | >500 |
| Message latency (p99) | >500ms | >2s |
| Connection drop rate | >5% | >20% |

---

## 11) What Is Explicitly Forbidden

- ❌ Unauthenticated WebSocket connections
- ❌ Cross-tenant message delivery
- ❌ Data mutations via WebSocket
- ❌ Large payloads (>64KB) via WebSocket
- ❌ WebSocket as sole data source
- ❌ Storing sensitive data in message history

---

## 12) Implementation Timeline

| Phase | Scope | Timeline |
|-------|-------|----------|
| Phase 8 | Notifications, dashboard updates | Q2 2026 |
| Phase 9 | Workflow live updates, presence | Q3 2026 |
| Phase 10 | Collaborative editing | Q4 2026 |

---

## 13) Final Warning

Real-time features are complex and high-risk for security.

Follow tenant isolation rules exactly. Test thoroughly.

---

**Verification Checksum**
- Document: realtime-architecture.md
- Purpose: Define real-time communication patterns
- Status: Authoritative — Freeze Blocking

---

**End of document**

