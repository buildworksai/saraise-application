<!-- SPDX-License-Identifier: Apache-2.0 -->
# Process Mining - API Documentation

**Version:** 1.0.0
**Last Updated:** 2025-01-20

---

## Overview

This document describes the API endpoints for the Process Mining module.

## Base Path

All endpoints are prefixed with `/api/v1/process-mining/`

## Authentication

All endpoints require authentication. See [Authentication Documentation](../../../architecture/11-session-auth.mdc) for details.

---

## Process Discovery Endpoints

### POST /discovery

Create a new process discovery run.

**Request Body:**
```json
{
  "event_log_id": "string",
  "algorithm": "alpha|inductive|heuristic",
  "config": {
    "noise_threshold": 0.2,
    "min_frequency": 0.1
  }
}
```

**Response:** `201 Created`
```json
{
  "id": "string",
  "tenant_id": "string",
  "event_log_id": "string",
  "status": "pending|running|completed|failed",
  "algorithm": "string",
  "config": {},
  "created_at": "2025-01-20T00:00:00Z",
  "updated_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

### GET /discovery

List process discovery runs.

**Query Parameters:**
- `status` (optional): Filter by status
- `event_log_id` (optional): Filter by event log ID
- `limit` (optional, default: 100): Number of results
- `offset` (optional, default: 0): Pagination offset

**Response:** `200 OK`
```json
[
  {
    "id": "string",
    "event_log_id": "string",
    "status": "string",
    "created_at": "2025-01-20T00:00:00Z"
  }
]
```

**Required Roles:** `tenant_user`

---

### GET /discovery/{discovery_run_id}

Get a specific discovery run.

**Response:** `200 OK`
```json
{
  "id": "string",
  "tenant_id": "string",
  "event_log_id": "string",
  "status": "string",
  "process_map": {},
  "variants": [],
  "statistics": {},
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

### GET /discovery/{discovery_run_id}/map

Get process map for a discovery run.

**Response:** `200 OK`
```json
{
  "id": "string",
  "name": "string",
  "nodes": {},
  "edges": {},
  "frequencies": {},
  "durations": {}
}
```

**Required Roles:** `tenant_user`

---

## Conformance Checking Endpoints

### POST /conformance

Create a new conformance check run.

**Request Body:**
```json
{
  "process_map_id": "string",
  "reference_model_id": "string",
  "config": {}
}
```

**Response:** `201 Created`
```json
{
  "id": "string",
  "tenant_id": "string",
  "process_map_id": "string",
  "reference_model_id": "string",
  "status": "pending|running|completed|failed",
  "conformance_score": 0.85,
  "violations": [],
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

### GET /conformance

List conformance runs.

**Query Parameters:**
- `status` (optional): Filter by status
- `process_map_id` (optional): Filter by process map ID
- `limit` (optional, default: 100)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
[
  {
    "id": "string",
    "process_map_id": "string",
    "status": "string",
    "conformance_score": 0.85,
    "created_at": "2025-01-20T00:00:00Z"
  }
]
```

**Required Roles:** `tenant_user`

---

### GET /conformance/{conformance_run_id}

Get a specific conformance run.

**Response:** `200 OK`
```json
{
  "id": "string",
  "process_map_id": "string",
  "reference_model_id": "string",
  "status": "string",
  "conformance_score": 0.85,
  "fitness_score": 0.90,
  "precision_score": 0.80,
  "violations": [],
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

## Optimization Endpoints

### GET /optimization/recommendations

List optimization recommendations.

**Query Parameters:**
- `process_map_id` (required): Process map ID
- `status` (optional): Filter by status
- `limit` (optional, default: 100)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
[
  {
    "id": "string",
    "process_map_id": "string",
    "recommendation_type": "string",
    "title": "string",
    "description": "string",
    "impact_score": 0.85,
    "effort_score": 0.45,
    "priority": "low|medium|high|critical",
    "status": "pending|approved|applied|rejected",
    "created_at": "2025-01-20T00:00:00Z"
  }
]
```

**Required Roles:** `tenant_user`

---

### POST /optimization/recommendations/{recommendation_id}/apply

Apply an optimization recommendation.

**Request Body:**
```json
{
  "workflow_config": {}
}
```

**Response:** `200 OK`
```json
{
  "id": "string",
  "status": "applied",
  "workflow_id": "string",
  "applied_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_developer`

---

## Bottleneck Analysis Endpoints

### POST /bottlenecks

Create a new bottleneck analysis.

**Request Body:**
```json
{
  "process_map_id": "string",
  "time_window_start": "2025-01-01T00:00:00Z",
  "time_window_end": "2025-01-31T23:59:59Z"
}
```

**Response:** `201 Created`
```json
{
  "id": "string",
  "tenant_id": "string",
  "process_map_id": "string",
  "bottleneck_activities": {},
  "wait_times": {},
  "resource_utilization": {},
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

### GET /bottlenecks

List bottleneck analyses.

**Query Parameters:**
- `process_map_id` (optional): Filter by process map ID
- `limit` (optional, default: 100)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
[
  {
    "id": "string",
    "process_map_id": "string",
    "bottleneck_activities": {},
    "created_at": "2025-01-20T00:00:00Z"
  }
]
```

**Required Roles:** `tenant_user`

---

### GET /bottlenecks/{analysis_id}

Get a specific bottleneck analysis.

**Response:** `200 OK`
```json
{
  "id": "string",
  "process_map_id": "string",
  "bottleneck_activities": {},
  "wait_times": {},
  "resource_utilization": {},
  "trends": {},
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

## Event Log Endpoints

### POST /event-logs

Upload an event log.

**Request Body:**
```json
{
  "name": "string",
  "description": "string",
  "source_type": "file_upload|api|database",
  "source_config": {}
}
```

**Response:** `201 Created`
```json
{
  "id": "string",
  "tenant_id": "string",
  "name": "string",
  "source_type": "string",
  "event_count": 0,
  "status": "active|archived|deleted",
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

### GET /event-logs

List event logs.

**Query Parameters:**
- `source_type` (optional): Filter by source type
- `status` (optional): Filter by status
- `limit` (optional, default: 100)
- `offset` (optional, default: 0)

**Response:** `200 OK`
```json
[
  {
    "id": "string",
    "name": "string",
    "source_type": "string",
    "event_count": 0,
    "status": "string",
    "created_at": "2025-01-20T00:00:00Z"
  }
]
```

**Required Roles:** `tenant_user`

---

### GET /event-logs/{event_log_id}

Get a specific event log.

**Response:** `200 OK`
```json
{
  "id": "string",
  "name": "string",
  "description": "string",
  "source_type": "string",
  "event_count": 1000,
  "date_range_start": "2025-01-01T00:00:00Z",
  "date_range_end": "2025-01-31T23:59:59Z",
  "status": "string",
  "created_at": "2025-01-20T00:00:00Z"
}
```

**Required Roles:** `tenant_user`

---

### DELETE /event-logs/{event_log_id}

Delete an event log.

**Response:** `204 No Content`

**Required Roles:** `tenant_admin`

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "detail": "Validation error message"
}
```

### 401 Unauthorized
```json
{
  "detail": "Authentication required"
}
```

### 403 Forbidden
```json
{
  "detail": "Insufficient permissions"
}
```

### 404 Not Found
```json
{
  "detail": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

---

## Request/Response Formats

All requests and responses use JSON format. Dates are in ISO 8601 format (UTC).

---

## Rate Limiting

API endpoints are subject to rate limiting based on tenant subscription plan. See [Rate Limiting Documentation](../../../architecture/rate-limiting.mdc) for details.

---

**Last Updated:** 2025-01-20
**License:** Apache-2.0
