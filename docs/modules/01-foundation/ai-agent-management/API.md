# AI Agent Management API Documentation

**Module:** `ai-agent-management`  
**Version:** 1.0.0  
**Base Path:** `/api/v1/ai-agents/`

---

## Overview

The AI Agent Management API provides endpoints for managing AI agents, their executions, approvals, quotas, and related resources.

**Authentication:** All endpoints require authentication via session cookies.

**Tenant Isolation:** All endpoints automatically filter by the authenticated user's `tenant_id`.

---

## Endpoints

### Agents

#### List Agents
```http
GET /api/v1/ai-agents/agents/
```

**Response:** `200 OK`
```json
[
  {
    "id": "uuid",
    "tenant_id": "tenant-1",
    "name": "Customer Support Agent",
    "description": "Handles customer inquiries",
    "identity_type": "user_bound",
    "subject_id": "user-123",
    "session_id": "session-456",
    "framework": "langgraph",
    "config": {"temperature": 0.7},
    "is_active": true,
    "created_by": "user-123",
    "created_at": "2026-01-05T10:00:00Z",
    "updated_at": "2026-01-05T10:00:00Z"
  }
]
```

#### Create Agent
```http
POST /api/v1/ai-agents/agents/
```

**Request Body:**
```json
{
  "name": "New Agent",
  "description": "Agent description",
  "identity_type": "system_bound",
  "subject_id": "system-role-1",
  "session_id": "session-123",  // Required for user_bound
  "framework": "langgraph",
  "config": {"key": "value"}
}
```

**Response:** `201 Created`
```json
{
  "id": "uuid",
  "tenant_id": "tenant-1",
  "name": "New Agent",
  ...
}
```

**Validation Errors:** `400 Bad Request`
- User-bound agents must have `session_id`
- System-bound agents must not have `session_id`

#### Get Agent Detail
```http
GET /api/v1/ai-agents/agents/{id}/
```

**Response:** `200 OK` (agent object)

**Not Found:** `404 Not Found` (if agent doesn't exist or belongs to different tenant)

#### Update Agent
```http
PUT /api/v1/ai-agents/agents/{id}/
PATCH /api/v1/ai-agents/agents/{id}/
```

**Request Body:** (same as create, all fields optional for PATCH)

**Response:** `200 OK` (updated agent object)

#### Delete Agent
```http
DELETE /api/v1/ai-agents/agents/{id}/
```

**Response:** `204 No Content`

#### Execute Agent
```http
POST /api/v1/ai-agents/agents/{id}/execute/
```

**Request Body:**
```json
{
  "task_definition": {
    "task": "process_invoice",
    "params": {}
  },
  "metadata": {
    "priority": "high"
  }
}
```

**Response:** `201 Created`
```json
{
  "id": "execution-uuid",
  "agent_id": "agent-uuid",
  "agent_name": "Agent Name",
  "state": "running",
  "started_at": "2026-01-05T10:00:00Z",
  ...
}
```

#### Pause Agent Execution
```http
POST /api/v1/ai-agents/agents/{id}/pause/
```

**Request Body:**
```json
{
  "execution_id": "execution-uuid"
}
```

**Response:** `200 OK` (updated execution object)

#### Resume Agent Execution
```http
POST /api/v1/ai-agents/agents/{id}/resume/
```

**Request Body:**
```json
{
  "execution_id": "execution-uuid"
}
```

**Response:** `200 OK` (updated execution object)

#### Terminate Agent Execution
```http
POST /api/v1/ai-agents/agents/{id}/terminate/
```

**Request Body:**
```json
{
  "execution_id": "execution-uuid"
}
```

**Response:** `200 OK` (updated execution object)

---

### Executions

#### List Executions
```http
GET /api/v1/ai-agents/executions/?agent_id={agent_id}
```

**Query Parameters:**
- `agent_id` (optional): Filter by agent ID

**Response:** `200 OK`
```json
[
  {
    "id": "execution-uuid",
    "agent_id": "agent-uuid",
    "agent_name": "Agent Name",
    "state": "completed",
    "started_at": "2026-01-05T10:00:00Z",
    "completed_at": "2026-01-05T10:05:00Z",
    "error_message": null,
    "result": {"output": "success"},
    ...
  }
]
```

#### Get Execution Detail
```http
GET /api/v1/ai-agents/executions/{id}/
```

**Response:** `200 OK` (execution object)

---

### Approvals

#### List Approval Requests
```http
GET /api/v1/ai-agents/approvals/?status={status}
```

**Query Parameters:**
- `status` (optional): Filter by status (`pending`, `approved`, `rejected`)

**Response:** `200 OK`
```json
[
  {
    "id": "approval-uuid",
    "tool_name": "create_invoice",
    "agent_execution_id": "execution-uuid",
    "status": "pending",
    "requested_by": "user-123",
    "requested_for": "user-123",
    "justification": "Processing monthly invoice",
    "requested_at": "2026-01-05T10:00:00Z"
  }
]
```

#### Approve Request
```http
POST /api/v1/ai-agents/approvals/{id}/approve/
```

**Response:** `200 OK` (updated approval object)

#### Reject Request
```http
POST /api/v1/ai-agents/approvals/{id}/reject/
```

**Request Body:**
```json
{
  "reason": "Violates SoD policy"
}
```

**Response:** `200 OK` (updated approval object)

---

### Health Check

#### Module Health
```http
GET /api/v1/ai-agents/health/
```

**Response:** `200 OK`
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "agent_queue": {
      "status": "ok",
      "active_agents": 5
    }
  }
}
```

**Unhealthy:** `503 Service Unavailable` (if any check fails)

---

## Error Responses

### 400 Bad Request
```json
{
  "message": "Validation error",
  "errors": {
    "session_id": ["User-bound agents must have session_id"]
  }
}
```

### 401 Unauthorized
```json
{
  "message": "Authentication required"
}
```

### 403 Forbidden
```json
{
  "message": "Insufficient permissions"
}
```

### 404 Not Found
```json
{
  "message": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "message": "Internal server error"
}
```

---

## Rate Limiting

Rate limits are enforced per tenant:
- **Default:** 100 requests per minute
- **Burst:** 200 requests per minute

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1641388800
```

---

## Pagination

List endpoints support pagination:
```http
GET /api/v1/ai-agents/agents/?page=1&page_size=20
```

**Response:**
```json
{
  "count": 100,
  "next": "/api/v1/ai-agents/agents/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Filtering & Sorting

List endpoints support filtering and sorting:
```http
GET /api/v1/ai-agents/agents/?is_active=true&ordering=-created_at
```

**Filter Fields:**
- `is_active` (boolean)
- `identity_type` (string)
- `framework` (string)

**Sort Fields:**
- `created_at`, `-created_at`
- `updated_at`, `-updated_at`
- `name`, `-name`

---

## Webhooks (Future)

Webhook endpoints for execution events:
- `execution.started`
- `execution.completed`
- `execution.failed`
- `approval.requested`
- `approval.approved`
- `approval.rejected`

---

**Last Updated:** January 5, 2026
