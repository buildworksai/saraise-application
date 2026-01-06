# Phase 2 Quick Reference Card

**Session Date**: January 4, 2026  
**Status**: Docker infrastructure restored; ready for testing  
**Time to Next Milestone**: 1-2 hours

---

## Start Services (Copy & Paste)

```bash
cd /Users/raghunathchava/Code/saraise-phase1

# Build
docker-compose -f docker-compose.phase2.yml build

# Start Tier-0
docker-compose -f docker-compose.phase2.yml up -d

# Wait
sleep 60

# Check
docker-compose -f docker-compose.phase2.yml ps

# Start observability
docker-compose -f docker-compose.observability.yml up -d
```

---

## Access UIs

- **Prometheus**: http://localhost:9090
- **Jaeger**: http://localhost:16686
- **Grafana**: http://localhost:3000 (admin/admin)
- **Health**: http://localhost:8001/health, 8002, 8003, 8004
- **Metrics**: http://localhost:9101/metrics, 9102, 9103, 9104

---

## Quick Validation

```bash
# API health
for p in 8001 8002 8003 8004; do curl http://localhost:$p/health; done

# Metrics endpoints
for p in 9101 9102 9103 9104; do curl -s http://localhost:$p/metrics | head -1; done

# Run tests
docker-compose -f docker-compose.phase2.yml run --rm saraise-auth pytest tests -v
```

---

## Essential Files

| File | Purpose |
|------|---------|
| `docker-compose.phase2.yml` | Tier-0 services |
| `docker-compose.observability.yml` | Prometheus/Jaeger/Grafana |
| `prometheus.yml` | Metrics scraping config |
| Runbook: `phase2-docker-continuation-2026-01-04.md` | Docker guide |
| Runbook: `phase2-auth-observability-implementation-2026-01-04.md` | Implementation steps |

---

## Metrics Ready Now (saraise-auth)

- `saraise_auth_session_issue_total` — sessions issued
- `saraise_auth_session_rotate_total` — sessions rotated
- `saraise_auth_session_store_latency_ms` — operation latency
- `saraise_auth_session_store_errors_total` — Redis errors
- Full JSON logging to stdout

---

## Next 3 Hours

1. ✅ Build & start Docker (15 min)
2. ✅ Verify endpoints (10 min)
3. ✅ Run tests (10 min)
4. ⏳ Validate metrics (15 min)
5. ⏳ Implement saraise-runtime (60 min)

---

## If Something Breaks

- **Docker won't build**: Check Docker daemon, pyproject.toml deps
- **Services won't start**: Check ports in use, logs, Redis health
- **Prometheus can't scrape**: Verify ports 9101-9104 are open
- **Tests fail**: Check Redis is healthy, check logs

---

## Key Ports

| Port | Service | Purpose |
|------|---------|---------|
| 8001 | Auth | API |
| 9101 | Auth | Metrics |
| 8002 | Runtime | API |
| 9102 | Runtime | Metrics |
| 8003 | Policy Engine | API |
| 9103 | Policy Engine | Metrics |
| 8004 | Control Plane | API |
| 9104 | Control Plane | Metrics |
| 6379 | Redis | Session store |
| 9090 | Prometheus | Metrics DB |
| 16686 | Jaeger | Traces UI |
| 3000 | Grafana | Dashboards |

---

## Metrics Query Examples

```promql
# Session issue rate
rate(saraise_auth_session_issue_total[1m])

# Store latency (p95)
histogram_quantile(0.95, rate(saraise_auth_session_store_latency_ms_bucket[5m]))

# Store error rate
rate(saraise_auth_session_store_errors_total[1m])
```

---

## Phase 2 Progress

| Component | Status | Effort |
|-----------|--------|--------|
| Docker infrastructure | ✅ Fixed | 0 |
| saraise-auth observability | 80% | 2h |
| saraise-runtime observability | 0% | 2h |
| saraise-policy-engine observability | 0% | 2h |
| saraise-control-plane observability | 0% | 2h |
| Security hardening | 0% | 3h |
| Compliance events | 0% | 2h |
| Chaos drills | 0% | 3h |
| **TOTAL** | **11%** | **16h** |

---

## Contact Points

**If Docker issues**:
- See: `phase2-docker-continuation-2026-01-04.md` → Troubleshooting
- Check: `docker logs -f <container>`

**If observability issues**:
- See: `phase2-auth-observability-implementation-2026-01-04.md` → Validation steps
- Check: `curl http://localhost:9101/metrics`

**If general questions**:
- See: `PHASE2-CONTINUATION-HANDBOOK-2026-01-04.md` → Overall context
- See: `.agents/rules/` → Authoritative patterns

---

**Last Updated**: 2026-01-04  
**Status**: READY FOR EXECUTION  
**Confidence**: HIGH
