# Phase 2 Observability Implementation Runbook — saraise-auth

**Status**: Foundation complete; ready for integration testing  
**Target**: Metrics, logs, traces emitted and validated  
**Priority**: P1 — Critical path for Phase 2

---

## Current State

### ✅ Completed
1. **Prometheus Metrics Defined**
   - `session_issue_total` — counter with tenant_id + result labels
   - `session_rotate_total` — counter with tenant_id + result labels
   - `session_invalidate_total` — counter with tenant_id + result labels
   - `session_validate_total` — counter with tenant_id + result labels
   - `session_store_errors_total` — counter with operation label (put, get, delete)
   - `session_store_latency_ms` — histogram (p50/p95/p99) for Redis ops
   - Buckets: 1ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s

2. **Structured JSON Logging**
   - Configured logger: `auth_logger` emits JSON with timestamp, level, message, tenant_id, action, result, error_reason, user_id, policy_version
   - Separate audit logger: `audit_logger` for compliance events

3. **Session Lifecycle Instrumentation**
   - `issue_session()` — increments `session_issue_total` on success/error
   - `rotate_session()` — increments `session_rotate_total` on success/error
   - `MetricsContext` context manager — wraps Redis ops to measure latency
   - Error handling — records `session_store_errors_total` on exceptions

4. **Flask HTTP Service**
   - `/health` endpoint — responds with service status
   - `/metrics` endpoint — exposes Prometheus metrics
   - Prometheus client library integrated

### 🔄 In Progress
- Integration testing of metrics/logs in realistic session flows
- Distributed tracing instrumentation (OpenTelemetry)
- Docker container health checks verified

### ❌ Not Started
- Trace instrumentation (need OpenTelemetry setup)
- Session tamper detection tests
- Store outage resilience tests
- Compliance event schema integration

---

## Step-by-Step Implementation

### Phase 1: Verify Docker Build & Startup (5 mins)

```bash
cd /Users/raghunathchava/Code/saraise-phase1

# Build the image
docker-compose -f docker-compose.phase2.yml build saraise-auth

# Start the service
docker-compose -f docker-compose.phase2.yml up -d redis saraise-auth

# Check health
docker-compose -f docker-compose.phase2.yml ps

# Should show:
# saraise-redis        ... Up (healthy)
# saraise-auth         ... Up (healthy)
```

### Phase 2: Verify Metrics Endpoint (5 mins)

```bash
# Check /health endpoint
curl http://localhost:8001/health
# Expected: {"status": "healthy", "service": "saraise-auth", "version": "0.0.0"}

# Check /metrics endpoint
curl http://localhost:8001/metrics
# Expected: Prometheus metric output including auth_health_checks_total, auth_request_duration_seconds
```

### Phase 3: Run Integration Tests (10 mins)

```bash
# Run existing tests in container
docker-compose -f docker-compose.phase2.yml run --rm saraise-auth pytest tests -v

# Expected coverage areas:
# - test_session_manager_baseline.py: session issue/rotate/invalidate/validate
# - test_redis_session_store.py: Redis put/get/delete operations
# - test_smoke.py: basic service startup
```

### Phase 4: Verify Metrics Emission (10 mins)

Create a test script to trigger session operations and verify metrics are emitted:

```python
# File: test_metrics_integration.py
import json
from datetime import timedelta
import redis

from saraise_auth.session_manager import issue_session, rotate_session, invalidate_session
from saraise_auth.redis_session_store import RedisSessionStore
from saraise_platform_core.contracts import IdentitySnapshot
from prometheus_client import REGISTRY


def test_metrics_emission():
    """Verify metrics are incremented on session operations."""
    
    # Connect to Redis
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    store = RedisSessionStore(r)
    
    # Create identity snapshot
    identity = IdentitySnapshot(
        session_id="test-session-123",
        tenant_id="tenant-001",
        policy_version=1,
        roles=("user",),
        groups=("default",),
        jit_grants=(),
    )
    
    # Issue a session
    issue_session(store, identity, ttl=timedelta(hours=2))
    
    # Get metrics
    metrics_before = REGISTRY.collect()
    
    # Rotate session
    new_identity = IdentitySnapshot(
        session_id="test-session-456",
        tenant_id="tenant-001",
        policy_version=1,
        roles=("user",),
        groups=("default",),
        jit_grants=(),
    )
    rotate_session(store, "test-session-123", new_identity, ttl=timedelta(hours=2))
    
    # Verify metrics incremented
    # Expected:
    # - session_issue_total{tenant_id="tenant-001",result="success"} = 2
    # - session_rotate_total{tenant_id="tenant-001",result="success"} = 1
    # - session_store_latency_ms{operation="put"} = histogram with observations
    # - session_store_latency_ms{operation="delete"} = histogram with observations


if __name__ == "__main__":
    test_metrics_emission()
```

Run it in the container:
```bash
docker-compose -f docker-compose.phase2.yml run --rm saraise-auth \
  python -m pytest test_metrics_integration.py -v -s
```

### Phase 5: Verify Structured Logs (5 mins)

Trigger a session operation and check logs:

```bash
# Watch logs in real-time
docker-compose -f docker-compose.phase2.yml logs -f saraise-auth

# In another terminal, trigger an operation
docker-compose -f docker-compose.phase2.yml exec saraise-auth bash -c "
  python -c '
    import redis
    from datetime import timedelta
    from saraise_auth.session_manager import issue_session
    from saraise_auth.redis_session_store import RedisSessionStore
    from saraise_platform_core.contracts import IdentitySnapshot
    
    r = redis.Redis(host=\"localhost\", port=6379, decode_responses=True)
    store = RedisSessionStore(r)
    
    identity = IdentitySnapshot(
        session_id=\"test-123\",
        tenant_id=\"tenant-001\",
        policy_version=1,
        roles=(\"user\",),
        groups=(\"default\",),
        jit_grants=(),
    )
    
    issue_session(store, identity, ttl=timedelta(hours=2))
  '
"

# Expected log output (JSON):
# {
#   "timestamp": "2026-01-04T...",
#   "level": "INFO",
#   "message": "Session issued",
#   "logger": "saraise_auth",
#   "tenant_id": "tenant-001",
#   "action": "issue",
#   "result": "success"
# }
```

### Phase 6: Prometheus Scrape Validation (5 mins)

```bash
# Start observability stack
docker-compose -f docker-compose.observability.yml up -d

# Open Prometheus UI
open http://localhost:9090

# Navigate to Targets
# Expected: All four services show "UP"
# - saraise-auth:9101 — UP
# - saraise-runtime:9102 — DOWN (not started)
# - saraise-policy-engine:9103 — DOWN (not started)
# - saraise-control-plane:9104 — DOWN (not started)

# Run a query to verify metrics are scraped
# In Prometheus UI, search for: saraise_auth_session_issue_total
# Expected: Metric appears with value > 0
```

### Phase 7: Add Distributed Tracing (Optional - Phase 2 stretch goal)

To enable OpenTelemetry distributed tracing, add dependencies to `pyproject.toml`:

```toml
dependencies = [
  "flask==3.1.0",
  "prometheus-client==0.21.0",
  "redis==5.2.1",
  "opentelemetry-api==1.24.0",
  "opentelemetry-sdk==1.24.0",
  "opentelemetry-exporter-jaeger==1.24.0",
  "opentelemetry-instrumentation-flask==0.45b0",
  "opentelemetry-instrumentation-redis==0.45b0",
]
```

Then update `__main__.py` to initialize tracing:

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

# Initialize Jaeger exporter
jaeger_exporter = JaegerExporter(
    agent_host_name="jaeger",
    agent_port=6831,
)

# Set up tracer
trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(jaeger_exporter))

# Auto-instrument Flask and Redis
FlaskInstrumentor().instrument_app(app)
RedisInstrumentor().instrument()

# Get tracer
tracer = trace.get_tracer(__name__)
```

---

## Validation Checklist

### Metrics Verification
- [ ] `saraise_auth_session_issue_total` counter increments on `issue_session()`
- [ ] `saraise_auth_session_rotate_total` counter increments on `rotate_session()`
- [ ] `saraise_auth_session_invalidate_total` counter increments on `invalidate_session()`
- [ ] `saraise_auth_session_validate_total` counter increments on `validate_session()`
- [ ] `saraise_auth_session_store_errors_total` increments on Redis exceptions
- [ ] `saraise_auth_session_store_latency_ms` histogram records p50/p95/p99 latencies
- [ ] Prometheus scrapes metrics from `localhost:9101/metrics`
- [ ] Prometheus UI shows all metrics with correct labels

### Logging Verification
- [ ] JSON logs output to stdout with proper timestamp/level/message
- [ ] Structured fields present: tenant_id, action, result, error_reason
- [ ] Login events: action=login, result=success|store_error
- [ ] Rotate events: action=rotate, result=success|store_error
- [ ] Invalidate events: action=invalidate, result=success|store_error
- [ ] Error logs include exception traceback

### Tracing Verification (if implemented)
- [ ] Jaeger UI shows traces for session operations
- [ ] Trace includes spans: issue_session → put → success
- [ ] Trace includes spans: rotate_session → delete → issue_session → put
- [ ] policy_version included in trace context

### Docker Verification
- [ ] saraise-auth container starts healthily
- [ ] Health check passes: `/health` returns 200 OK
- [ ] Metrics endpoint accessible: `/metrics` returns 200 OK
- [ ] Prometheus target shows "UP" in UI
- [ ] Redis connectivity works: operations succeed, latency metrics recorded

---

## Troubleshooting

### Metrics not appearing in Prometheus

1. Check if service is running:
```bash
docker-compose -f docker-compose.phase2.yml ps saraise-auth
```

2. Verify metrics endpoint works:
```bash
curl http://localhost:9101/metrics | head -20
```

3. Check Prometheus scrape logs:
```bash
docker-compose -f docker-compose.observability.yml logs prometheus | grep saraise-auth
```

4. Verify network connectivity from Prometheus to service:
```bash
docker-compose -f docker-compose.observability.yml exec prometheus \
  curl http://saraise-auth:9101/metrics | head -20
```

### Logs not appearing as JSON

1. Check if logger is configured:
```python
from saraise_auth.structured_logging import auth_logger
auth_logger.info("Test message", extra={"tenant_id": "test"})
```

2. Check if StructuredJsonFormatter is applied:
```bash
docker-compose -f docker-compose.phase2.yml logs saraise-auth | head -5
```

3. Verify formatter is JSON (should see `{` not plain text)

### Redis connection refused

1. Check Redis is running:
```bash
docker-compose -f docker-compose.phase2.yml ps redis
```

2. Test Redis connectivity from service:
```bash
docker-compose -f docker-compose.phase2.yml exec saraise-auth \
  redis-cli -h redis PING
# Should respond with PONG
```

3. Check Redis logs:
```bash
docker-compose -f docker-compose.phase2.yml logs redis
```

---

## Next Phases

### Phase 3: Security Hardening Tests
- [ ] Session tamper detection: modify token and verify rejection
- [ ] Store outage resilience: kill Redis and verify graceful failure
- [ ] Input validation: test oversized/malformed payloads

### Phase 4: Compliance Event Schema
- [ ] Create `AuditEvent` dataclass in `saraise_platform_core`
- [ ] Emit events for: login, logout, rotate, store_error
- [ ] Define immutable audit log store

### Phase 5: Chaos Drill
- [ ] Simulate Redis outage
- [ ] Measure MTTR (mean time to recovery)
- [ ] Verify alert firing
- [ ] Document post-mortem

---

## Implementation Files Reference

| File | Purpose | Status |
|------|---------|--------|
| `saraise-auth/src/saraise_auth/observability.py` | Prometheus metrics | ✅ Complete |
| `saraise-auth/src/saraise_auth/structured_logging.py` | JSON logging | ✅ Complete |
| `saraise-auth/src/saraise_auth/session_manager.py` | Session ops + instrumentation | ✅ Complete |
| `saraise-auth/src/saraise_auth/redis_session_store.py` | Redis backend | ✅ Complete |
| `saraise-auth/src/saraise_auth/__main__.py` | Flask app + /metrics endpoint | ✅ Complete |
| `saraise-auth/Dockerfile` | Container image | ✅ Complete |
| `docker-compose.phase2.yml` | Service orchestration | ✅ Fixed |
| `prometheus.yml` | Metrics scraping | ✅ Fixed |

---

## Key Metrics Query Examples

### Query: Session issue rate (per minute)
```promql
rate(saraise_auth_session_issue_total[1m])
```

### Query: Session store latency (p95)
```promql
histogram_quantile(0.95, rate(saraise_auth_session_store_latency_ms_bucket[5m]))
```

### Query: Session store error rate
```promql
rate(saraise_auth_session_store_errors_total[1m])
```

### Query: Total sessions active
```promql
saraise_auth_session_issue_total - saraise_auth_session_invalidate_total
```

---

**Runbook Created**: 2026-01-04  
**Status**: Ready for implementation  
**Estimated Effort**: 2 hours (including testing)  
**Blocker**: None — all dependencies available
