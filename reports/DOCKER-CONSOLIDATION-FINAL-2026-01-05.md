# Docker Consolidation Final — All Services Running

**Date:** January 5, 2026  
**Status:** ✅ COMPLETE

---

## Summary

Successfully created consolidated `docker-compose.dev.yml` with all SARAISE services (Phase 1-6) running in a single network.

---

## Consolidated Services (12 Total)

### Infrastructure (2 services)
- ✅ **PostgreSQL:** `saraise-db` - Port `5432:5432` (standard port)
- ✅ **Redis:** `saraise-redis` - Port `6379:6379` (standard port)

### Phase 2 Services (4 services)
- ✅ **Auth Service:** `saraise-auth` - Port `18001:8001` (+ metrics `19101`)
- ✅ **Runtime Service:** `saraise-runtime` - Port `18002:8002` (+ metrics `19102`)
- ✅ **Policy Engine:** `saraise-policy-engine` - Port `18003:8003` (+ metrics `19103`)
- ✅ **Control Plane:** `saraise-control-plane` - Port `18004:8004` (+ metrics `19104`)

### Phase 4/5 Services (1 service)
- ✅ **Backend (Legacy):** `saraise-backend-phase1` - Port `18005:8005`

### Phase 6 Services (2 services)
- ✅ **Backend API:** `saraise-phase6-backend` - Port `18000:8000`
- ✅ **Frontend UI:** `saraise-phase6-frontend` - Port `15173:5173`

### Observability (3 services)
- ✅ **Prometheus:** `saraise-prometheus` - Port `19090:9090`
- ✅ **Grafana:** `saraise-grafana` - Port `13000:3000`
- ✅ **Jaeger:** `saraise-jaeger` - Port `16686:16686` (UI) + others

---

## Port Mapping Summary

| Service | Internal Port | External Port | Status |
|---------|--------------|---------------|--------|
| PostgreSQL | 5432 | 5432 | ✅ Running |
| Redis | 6379 | 6379 | ✅ Running |
| Auth Service | 8001 | 18001 | ✅ Healthy |
| Runtime Service | 8002 | 18002 | ✅ Healthy |
| Policy Engine | 8003 | 18003 | ✅ Healthy |
| Control Plane | 8004 | 18004 | ✅ Healthy |
| Backend (Phase 1) | 8005 | 18005 | ✅ Running |
| Backend (Phase 6) | 8000 | 18000 | ✅ Running |
| Frontend (Phase 6) | 5173 | 15173 | ✅ Running |
| Prometheus | 9090 | 19090 | ✅ Running |
| Grafana | 3000 | 13000 | ✅ Running |
| Jaeger UI | 16686 | 16686 | ✅ Running |

**Note:** PostgreSQL and Redis use standard ports (5432, 6379) for compatibility. All application services use "1" prefix for external ports.

---

## Network Architecture

**Single Network:** `saraise-network` (bridge driver)

**All 12 containers on shared network:**
- saraise-auth
- saraise-backend-phase1
- saraise-control-plane
- saraise-db
- saraise-grafana
- saraise-jaeger
- saraise-phase6-backend
- saraise-phase6-frontend
- saraise-policy-engine
- saraise-prometheus
- saraise-redis
- saraise-runtime

---

## Service URLs

### Phase 6 Services
- **Frontend UI:** http://localhost:15173
- **Backend API:** http://localhost:18000
- **Health Check:** http://localhost:18000/api/v1/ai-agents/health/
- **Swagger UI:** http://localhost:18000/api/schema/swagger-ui/
- **ReDoc:** http://localhost:18000/api/schema/redoc/

### Phase 2 Services
- **Auth Service:** http://localhost:18001
- **Runtime Service:** http://localhost:18002
- **Policy Engine:** http://localhost:18003
- **Control Plane:** http://localhost:18004

### Phase 4/5 Services
- **Backend (Legacy):** http://localhost:18005

### Observability
- **Prometheus:** http://localhost:19090
- **Grafana:** http://localhost:13000
- **Jaeger UI:** http://localhost:16686

### Infrastructure
- **PostgreSQL:** localhost:5432
- **Redis:** localhost:6379

---

## Usage

### Start All Services
```bash
./scripts/docker/start-all.sh
```

**Or manually:**
```bash
docker-compose -f docker-compose.dev.yml up -d --build
```

### Stop All Services
```bash
./scripts/docker/stop-all.sh
```

**Or manually:**
```bash
docker-compose -f docker-compose.dev.yml down
```

### View Logs
```bash
# All services
docker-compose -f docker-compose.dev.yml logs -f

# Specific service
docker-compose -f docker-compose.dev.yml logs -f backend
docker-compose -f docker-compose.dev.yml logs -f frontend
docker-compose -f docker-compose.dev.yml logs -f auth
```

### Check Status
```bash
docker-compose -f docker-compose.dev.yml ps
```

### Restart Service
```bash
docker-compose -f docker-compose.dev.yml restart [service_name]
```

---

## Verification

### Check All Containers
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep saraise
```

### Check Network
```bash
docker network inspect saraise-network --format '{{range .Containers}}{{.Name}} {{end}}'
```

### Test Services
```bash
# Backend (Phase 6)
curl http://localhost:18000/api/v1/ai-agents/health/

# Frontend
curl http://localhost:15173

# Auth Service
curl http://localhost:18001/health

# Prometheus
curl http://localhost:19090/-/healthy

# Grafana
curl http://localhost:13000/api/health
```

---

## Files Created/Modified

### Docker Configuration
- `docker-compose.dev.yml` - Consolidated compose file (all 12 services)
- `scripts/docker/start-all.sh` - Start script for all services
- `scripts/docker/stop-all.sh` - Stop script for all services

### Documentation
- `reports/DOCKER-CONSOLIDATION-COMPLETE-2026-01-05.md` - Initial consolidation doc
- `reports/DOCKER-CONSOLIDATION-FINAL-2026-01-05.md` - This document

---

## Benefits

1. **Single File:** All services in one docker-compose file
2. **Single Network:** All services communicate via `saraise-network`
3. **Port Standardization:** Application services use "1" prefix
4. **Simplified Management:** One command to start/stop everything
5. **Consistent Configuration:** Unified environment variables
6. **Easy Debugging:** All logs in one place
7. **Health Checks:** All services have health check endpoints
8. **Dependencies:** Proper service dependencies ensure correct startup order

---

## Service Dependencies

### Startup Order
1. **Infrastructure:** postgres, redis (health checks)
2. **Phase 2:** auth, policy-engine (health checks)
3. **Phase 2:** runtime (depends on auth, policy-engine)
4. **Phase 2:** control-plane
5. **Phase 4/5:** backend-phase1 (depends on postgres, redis)
6. **Phase 6:** backend (depends on postgres, redis)
7. **Phase 6:** frontend (depends on backend)
8. **Observability:** prometheus, grafana (depends on prometheus), jaeger

---

## Environment Variables

### Default Ports (can be overridden via .env)
```env
POSTGRES_PORT=5432
REDIS_PORT=6379
BACKEND_PORT=18000
FRONTEND_PORT=15173
SECRET_KEY=<auto-generated>
```

---

## Troubleshooting

### Service Won't Start
```bash
# Check logs
docker-compose -f docker-compose.dev.yml logs [service_name]

# Check health
docker-compose -f docker-compose.dev.yml ps

# Restart service
docker-compose -f docker-compose.dev.yml restart [service_name]
```

### Network Issues
```bash
# Check network
docker network inspect saraise-network

# Recreate network
docker network rm saraise-network
docker network create saraise-network
docker-compose -f docker-compose.dev.yml up -d
```

### Port Conflicts
```bash
# Check port usage
lsof -i :18000
lsof -i :15173

# Change ports in .env file
BACKEND_PORT=18001
FRONTEND_PORT=15174
```

---

**Status:** ✅ COMPLETE

All 12 services running successfully in consolidated docker-compose file with single network architecture.

---

**Last Updated:** January 5, 2026

