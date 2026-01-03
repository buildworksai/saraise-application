---
description: Service integration patterns, monitoring, and observability for SARAISE infrastructure
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# 🔗 SARAISE Service Integration & Monitoring

**Rule IDs**: SARAISE-16001 to SARAISE-16013, SARAISE-17001 to SARAISE-17007
**Consolidates**: `19-service-monitoring.md`, `19-service-monitoring.md`

**Related Documentation:**
- Service Layer Patterns: See `docs/architecture/application-architecture.md` for service patterns
- API Gateway Integration: See Kong configuration in `docs/architecture/examples/infrastructure/` (Kong is optional edge gateway)

---

## Service Integration Patterns

### SARAISE-16001 Service Integration Architecture

**Core Principles:**
- **Environment-Aware**: Use environment variables for all service connections (see `09-infrastructure-config.md`)
- **Error Resilient**: Implement retry logic and circuit breakers
- **Observable**: Include proper logging and metrics
- **Secure**: Use proper authentication and encryption
- **Testable**: Support mocking and testing patterns

### SARAISE-16002 Database Integration Patterns

See [Database Integration](docs/architecture/examples/backend/services/database-integration.py) for implementation.

### SARAISE-16003 Redis Integration Patterns

See [Redis Integration](docs/architecture/examples/backend/services/redis-integration.py) for implementation.

### SARAISE-16004 MinIO Object Storage Integration

See [MinIO Integration](docs/architecture/examples/backend/services/minio-integration.py) for implementation.

### SARAISE-16005 Email Service Integration

See [Email Integration](docs/architecture/examples/backend/services/email-integration.py) for implementation.

### SARAISE-16006 Kong API Gateway Integration

See [Kong Integration](docs/architecture/examples/backend/services/kong-integration.py) for implementation.

### SARAISE-16007 Celery Task Queue Integration

See [Celery Integration](docs/architecture/examples/backend/services/celery-integration.py) for implementation.

### SARAISE-16008 Vault Secrets Integration

See [Vault Integration](docs/architecture/examples/backend/services/vault-integration.py) for implementation.

### SARAISE-16009 Circuit Breaker Pattern

See [Circuit Breaker](docs/architecture/examples/backend/core/circuit-breaker.py) for implementation.

### SARAISE-16010 Frontend Service Integration

See [Frontend API Service](docs/architecture/examples/frontend/services/api-service.ts) for implementation.

### SARAISE-16011 Service Health Checks

See [Service Health Checker](docs/architecture/examples/backend/services/service-health-checker.py) for implementation.

### SARAISE-16012 Error Handling Patterns

See [Service Error Handler](docs/architecture/examples/backend/services/service-error-handler.py) for implementation.

### SARAISE-16013 Testing Service Integration

See [Service Mocking Fixtures](docs/architecture/examples/backend/tests/service-mocking-fixtures.py) for implementation.

---

## Monitoring & Observability

### SARAISE-17001 Monitoring Architecture Overview

**Core Monitoring Stack:**
- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization and dashboards
- **Loki**: Log aggregation and querying
- **Flower**: Celery task monitoring

**Service URLs (Development):**
- Prometheus: `http://localhost:${PROMETHEUS_HOST_PORT:-19090}`
- Grafana: `http://localhost:${GRAFANA_HOST_PORT:-13001}` (admin/admin)
- Loki: `http://localhost:${LOKI_HOST_PORT:-13100}`
- Flower: `http://localhost:${FLOWER_HOST_PORT:-15555}` (admin/admin)

### SARAISE-17002 Application Metrics Implementation

**Prometheus Metrics:**

```python
from prometheus_client import Counter, Histogram, Gauge

# HTTP Metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status_code'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])

# Database Metrics
DB_CONNECTIONS = Gauge('database_connections_active', 'Active database connections')
DB_QUERY_DURATION = Histogram('database_query_duration_seconds', 'Query duration', ['query_type'])

# Business Metrics
USER_REGISTRATIONS = Counter('user_registrations_total', 'Total user registrations', ['tenant_id'])
AI_AGENT_EXECUTIONS = Counter('ai_agent_executions_total', 'AI agent executions', ['agent_type', 'status'])
WORKFLOW_EXECUTIONS = Counter('workflow_executions_total', 'Workflow executions', ['workflow_id', 'status'])
ACTIVE_SESSIONS = Gauge('active_sessions_total', 'Active user sessions')
```

### SARAISE-17003 Logging Standards

**Structured Logging:**

```python
class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        # JSON formatter for structured logs

    def log_request(self, method: str, path: str, status_code: int, duration: float, user_id: str = None):
        self.logger.info(
            f"HTTP request processed",
            extra={"event_type": "http_request", "method": method, "path": path,
                   "status_code": status_code, "duration_ms": duration * 1000, "user_id": user_id}
        )
```

### SARAISE-17004 Health Check Implementation

**Comprehensive Health Checks:**

```python
@router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.0"}

@router.get("/health/detailed")
async def detailed_health_check():
    # Check database, Redis, and other services
    # Return aggregated health status

@router.get("/health/readiness")
async def readiness_check():
    # Kubernetes readiness probe
    # Check all critical services

@router.get("/health/liveness")
async def liveness_check():
    return {"status": "alive"}
```

### SARAISE-17005 Alerting Rules

**Prometheus Alert Rules:**

```yaml
groups:
  - name: saraise.rules
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status_code=~"5.."}[5m]) > 0.1
        for: 5m
        labels: {severity: warning}

      - alert: HighResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels: {severity: warning}

      - alert: DatabaseConnectionHigh
        expr: database_connections_active > 80
        for: 5m
        labels: {severity: warning}

      - alert: RedisDown
        expr: up{job="redis"} == 0
        for: 1m
        labels: {severity: critical}
```

### SARAISE-17006 Frontend Monitoring

**Frontend Error Tracking:**

```typescript
class FrontendMonitoring {
  trackError(error: Error, context: Record<string, any> = {}) {
    fetch(`${this.apiUrl}/api/v1/monitoring/errors`, {
      method: 'POST',
      credentials: 'include',
      body: JSON.stringify({
        message: error.message, stack: error.stack, context,
        timestamp: new Date().toISOString(), url: window.location.href
      })
    }).catch(() => {});
  }
}

// Global error handler
window.addEventListener('error', (event) => {
  monitoring.trackError(event.error, {filename: event.filename, lineno: event.lineno});
});
```

### SARAISE-17007 Monitoring Best Practices

**Performance Monitoring:**
- Track 50th, 95th, and 99th percentiles for response time
- Monitor requests per second (throughput)
- Track 4xx and 5xx error rates
- Monitor CPU, memory, and disk usage

**Business Metrics:**
- User activity (registrations, logins, actions)
- Feature usage patterns
- Per-tenant usage metrics
- AI agent execution success rates

**Alerting Strategy:**
- **Critical**: Service down, high error rate, security issues
- **Warning**: High response time, resource usage, queue backlog
- **Info**: Deployment notifications, configuration changes

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
