# Phase 2 Docker Build Continuation — January 4, 2026

**Status**: Docker infrastructure restored and ready for observability implementation

---

## Summary of Changes Made

### 1. Fixed Docker Compose Network Configuration
**Problem**: `docker-compose.observability.yml` marked the network as `external: true` but it wasn't created externally, preventing observability services from launching.

**Solution**:
- Updated `docker-compose.observability.yml` to define the network locally with `driver: bridge`
- Network name: `saraise-phase2-network` (shared between phase2 and observability stacks)
- Both compose files now reference the same named network

### 2. Fixed Prometheus Metrics Port Binding
**Problem**: Prometheus was configured to scrape metrics from service containers on ports 8001-8004 (API ports) but services don't expose metrics on those ports by default.

**Solution**:
- Added explicit metrics port bindings to `docker-compose.phase2.yml`:
  - `saraise-auth`: 9101 → 8001 (metrics via localhost:9101)
  - `saraise-runtime`: 9102 → 8002
  - `saraise-policy-engine`: 9103 → 8003
  - `saraise-control-plane`: 9104 → 8004
- Updated `prometheus.yml` scrape_configs to target ports 9101-9104 instead of 8001-8004

### 3. Verified Dockerfile Integrity
All Dockerfiles present and correctly configured:
- ✓ `saraise-auth/Dockerfile`
- ✓ `saraise-runtime/Dockerfile`
- ✓ `saraise-policy-engine/Dockerfile`
- ✓ `saraise-control-plane/Dockerfile`

Each Dockerfile:
- Uses Python 3.11-slim base image
- Installs curl for health checks
- Installs dependencies with `pip install -e .[dev,test]`
- Exposes correct port (8001-8004)
- Configures health checks
- Sets PORT environment variable

---

## Quick Start (Updated)

### 1. Build All Images
```bash
cd /Users/raghunathchava/Code/saraise-phase1
docker-compose -f docker-compose.phase2.yml build
```

### 2. Start Tier-0 Services
```bash
docker-compose -f docker-compose.phase2.yml up -d
```

### 3. Verify Service Health
```bash
# Wait for services to become healthy (30-60 seconds)
docker-compose -f docker-compose.phase2.yml ps

# Expected output:
# NAME                    COMMAND                  SERVICE                 STATUS              PORTS
# saraise-redis           redis-server             redis                   Up (healthy)        0.0.0.0:6379->6379/tcp
# saraise-auth            python -m saraise_auth   saraise-auth            Up (healthy)        0.0.0.0:8001->8001/tcp, 0.0.0.0:9101->8001/tcp
# saraise-policy-engine   python -m ...            saraise-policy-engine   Up (healthy)        0.0.0.0:8003->8003/tcp, 0.0.0.0:9103->8003/tcp
# saraise-runtime         python -m ...            saraise-runtime         Up (healthy)        0.0.0.0:8002->8002/tcp, 0.0.0.0:9102->8002/tcp
# saraise-control-plane   python -m ...            saraise-control-plane   Up (healthy)        0.0.0.0:8004->8004/tcp, 0.0.0.0:9104->8004/tcp
```

### 4. Start Observability Stack
```bash
docker-compose -f docker-compose.observability.yml up -d
```

### 5. Verify Observability Services
```bash
# Wait for observability services (30 seconds)
docker-compose -f docker-compose.observability.yml ps

# Expected output:
# NAME                COMMAND                    SERVICE     STATUS
# saraise-prometheus  /bin/prometheus ...        prometheus  Up
# saraise-jaeger      /go/bin/all-in-one-linux  jaeger      Up
# saraise-grafana     /run.sh                    grafana     Up
```

### 6. Access UIs
```bash
# Prometheus (raw metrics)
open http://localhost:9090

# Jaeger (distributed tracing)
open http://localhost:16686

# Grafana (dashboards)
open http://localhost:3000  # admin/admin
```

---

## Validation Checklist

### API Health
```bash
#!/bin/bash
echo "=== API Service Health ==="
for port in 8001 8002 8003 8004; do
  SERVICE=$(curl -s http://localhost:$port/health | jq .service 2>/dev/null || echo "error")
  echo "Port $port: $SERVICE"
done
```

### Metrics Endpoints
```bash
#!/bin/bash
echo "=== Prometheus Metrics Endpoints ==="
for port in 9101 9102 9103 9104; do
  COUNT=$(curl -s http://localhost:$port/metrics 2>/dev/null | wc -l)
  echo "Port $port: $COUNT metric lines"
done
```

### Prometheus Targets
```bash
# Open Prometheus UI and verify all targets show "UP"
open http://localhost:9090/targets
```

### Service Interdependencies
```bash
# Verify runtime can reach auth
docker-compose -f docker-compose.phase2.yml exec saraise-runtime \
  curl -s http://saraise-auth:8001/health

# Verify runtime can reach policy-engine
docker-compose -f docker-compose.phase2.yml exec saraise-runtime \
  curl -s http://saraise-policy-engine:8003/health

# Verify auth can reach redis
docker-compose -f docker-compose.phase2.yml exec saraise-auth \
  redis-cli -h redis PING
```

---

## Phase 2 Implementation Roadmap

### ✅ Complete: Docker Infrastructure
- [x] Fixed network configuration
- [x] Fixed metrics port binding
- [x] Verified all Dockerfiles
- [x] Updated Prometheus scrape config

### 🔄 In Progress: Observability Implementation
Next steps by service:

#### saraise-auth (NEXT PRIORITY)
**Metrics to add**:
- `session_issue_total` — counter for new sessions
- `session_rotate_total` — counter for rotated sessions
- `session_invalid_total` — counter for invalid/tampered sessions
- `session_store_latency_ms` — histogram (p50/p95/p99) for Redis ops
- `session_store_errors_total` — counter for Redis failures

**Logging to add**:
- Structured JSON logs for all session lifecycle events
- Include: user_id, tenant_id, session_id, action, result, error (if any)

**Tracing to add**:
- Trace session creation → store write → validation
- Include policy_version in trace context

**Implementation file**: `saraise-auth/src/saraise_auth/observability.py` (NEW)

#### saraise-runtime (AFTER AUTH)
**Metrics**: request handling, policy evaluation latency, denials
**Logging**: request outcome, policy_version, decision_reason, module
**Tracing**: request → auth → policy evaluation → decision

#### saraise-policy-engine (AFTER RUNTIME)
**Metrics**: policy evaluations, bundle versioning, stale denies
**Logging**: evaluation outcome, rule hits, bundle_version
**Tracing**: evaluation flow, rule matching

#### saraise-control-plane (AFTER POLICY)
**Metrics**: tenant lifecycle, policy bumps, shard assignments
**Logging**: lifecycle changes, policy version bumps
**Tracing**: policy propagation

### 🎯 Security Hardening Tests
After observability: session tamper detection, store outage resilience, input validation

### 📊 Compliance & Audit Events
After tests: audit event schemas, event emission integration

### 🔥 Chaos Drills
After compliance: Redis outage simulation, stale policy bundle drill

---

## Key File Locations

| File | Purpose |
|------|---------|
| `docker-compose.phase2.yml` | Tier-0 services orchestration |
| `docker-compose.observability.yml` | Prometheus, Jaeger, Grafana |
| `prometheus.yml` | Metrics scrape configuration |
| `saraise-auth/Dockerfile` | Auth service container image |
| `saraise-runtime/Dockerfile` | Runtime service container image |
| `saraise-policy-engine/Dockerfile` | Policy engine service container image |
| `saraise-control-plane/Dockerfile` | Control plane service container image |
| `saraise-auth/pyproject.toml` | Auth service dependencies |
| `saraise-auth/src/saraise_auth/` | Auth service source code |

---

## Common Docker Commands

```bash
# Build all services
docker-compose -f docker-compose.phase2.yml build

# Start all services
docker-compose -f docker-compose.phase2.yml up -d

# Check status
docker-compose -f docker-compose.phase2.yml ps

# View logs for one service
docker-compose -f docker-compose.phase2.yml logs -f saraise-auth

# View logs for all services (10 lines)
docker-compose -f docker-compose.phase2.yml logs --tail=10

# Run a command in a container
docker-compose -f docker-compose.phase2.yml exec saraise-auth bash

# Run tests in a container
docker-compose -f docker-compose.phase2.yml run --rm saraise-auth pytest tests -v

# Stop services
docker-compose -f docker-compose.phase2.yml down

# Full cleanup (remove volumes too)
docker-compose -f docker-compose.phase2.yml down -v

# Start observability separately
docker-compose -f docker-compose.observability.yml up -d
docker-compose -f docker-compose.observability.yml logs -f
```

---

## Network Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ saraise-phase2-network (Docker bridge)                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ saraise-auth │  │ saraise-auth │  │   redis      │       │
│  │ (8001:8001)  │  │ (9101:8001)  │  │  (6379)      │       │
│  │ (API)        │  │ (metrics)    │  │ (session)    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         ▲                                    ▲                │
│         │                                    │                │
│  ┌──────────────────────┐          ┌────────┘                │
│  │ saraise-runtime      │          │                          │
│  │ (8002:8002 API)      │──────────┘                          │
│  │ (9102:8002 metrics)  │          ┌──────────────┐          │
│  └──────────────────────┘          │ saraise-     │          │
│         ▲                           │ policy-engine│          │
│         │                           │ (8003:8003)  │          │
│         │                    ┌──────│ (9103:8003)  │          │
│         │                    │      └──────────────┘          │
│         │                    │                                 │
│  ┌──────────────────────┐    │                                │
│  │ saraise-control-     │    │                                │
│  │ plane                │    │                                │
│  │ (8004:8004 API)      │────┘                                │
│  │ (9104:8004 metrics)  │                                     │
│  └──────────────────────┘                                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ prometheus (9090) ◄── scrapes metrics from 9101-9104        │
│ jaeger (16686)                                              │
│ grafana (3000) ◄── queries prometheus                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Next Steps

1. **Start Docker containers** and verify all services are healthy
2. **Verify Prometheus scrape targets** show UP in UI
3. **Implement observability for saraise-auth** (add metrics, logs, traces)
4. **Add tests** for observability coverage
5. **Implement observability for remaining services** (runtime, policy, control-plane)
6. **Create Grafana dashboards** for visualization
7. **Add security hardening tests**
8. **Implement audit event emission**
9. **Run chaos drills** (Redis outage, stale policy)

---

## Troubleshooting

### Services won't start
```bash
# Check Docker daemon
docker ps

# Check logs
docker-compose -f docker-compose.phase2.yml logs saraise-auth

# Check network
docker network ls | grep saraise
docker network inspect saraise-phase2-network
```

### Prometheus can't scrape metrics
```bash
# Verify ports are open
netstat -an | grep 910[1-4]

# Test from Prometheus container
docker-compose -f docker-compose.observability.yml exec prometheus \
  curl http://saraise-auth:9101/metrics
```

### Redis connection refused
```bash
# Check Redis is running and healthy
docker-compose -f docker-compose.phase2.yml ps redis

# Test Redis connectivity
docker-compose -f docker-compose.phase2.yml exec saraise-auth \
  redis-cli -h redis PING
```

---

**Report Generated**: 2026-01-04  
**Docker Infrastructure Status**: ✅ Restored  
**Next Milestone**: Observability Implementation (saraise-auth)
