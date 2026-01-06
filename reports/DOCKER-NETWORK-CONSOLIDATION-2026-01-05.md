# Docker Network Consolidation — Single Network Architecture

**Date:** January 5, 2026  
**Status:** ✅ COMPLETE

---

## Summary

Consolidated all Docker containers to use a single `saraise-network` and updated all external ports to use "1" prefix to avoid conflicts.

---

## Changes Made

### 1. Network Consolidation

**Before:**
- Phase 6 containers used `saraise-network` as external
- Separate network created (`saraise_saraise-network`)

**After:**
- All containers use single `saraise-network`
- Network created automatically if it doesn't exist
- Shared with existing phase1 containers (saraise-db, saraise-redis, etc.)

### 2. Port Standardization

**Port Mapping Rule:** All external ports start with "1" prefix

| Service | Internal Port | External Port | URL |
|---------|--------------|---------------|-----|
| Backend API | 8000 | 18000 | http://localhost:18000 |
| Frontend UI | 5173 | 15173 | http://localhost:15173 |
| PostgreSQL | 5432 | 5432 | localhost:5432 (shared) |
| Redis | 6379 | 6379 | localhost:6379 (shared) |

**Rationale:**
- Avoids conflicts with existing phase1 services (8001-8005)
- Clear port numbering convention
- Easy to identify Phase 6 services (ports start with 1)

---

## Updated Files

### Docker Configuration
- `docker-compose.dev.yml` - Updated ports and network configuration
- `scripts/docker/start-dev.sh` - Updated port checks and messaging

### Frontend Configuration
- `frontend/vite.config.ts` - Updated proxy target to port 18000
- `frontend/src/services/api-client.ts` - Updated default base URL

### Documentation
- `README-DOCKER.md` - Updated all port references
- `reports/DOCKER-NETWORK-CONSOLIDATION-2026-01-05.md` - This document

---

## Network Architecture

```
┌─────────────────────────────────────────┐
│         saraise-network                  │
│         (Single Network)                 │
│                                          │
│  ┌──────────┐  ┌──────────┐            │
│  │ Frontend │──│ Backend  │            │
│  │ :5173    │  │ :8000    │            │
│  │ (15173)  │  │ (18000)  │            │
│  └──────────┘  └────┬─────┘            │
│                     │                   │
│              ┌──────┴──────┐            │
│              │             │            │
│         ┌────▼───┐   ┌────▼───┐        │
│         │Postgres│   │ Redis  │        │
│         │ :5432  │   │ :6379  │        │
│         │(shared)│   │(shared)│        │
│         └────────┘   └────────┘        │
│                                          │
│  Phase 1 Services (also on network):    │
│  - saraise-auth (8001)                  │
│  - saraise-runtime (8002)               │
│  - saraise-policy-engine (8003)         │
│  - saraise-control-plane (8004)         │
│  - saraise-backend (8005)               │
│  - saraise-grafana (3000)               │
│  - saraise-prometheus (9090)            │
│  - saraise-jaeger (16686)               │
└─────────────────────────────────────────┘
```

---

## Service URLs (Updated)

### Phase 6 Services
- **Frontend UI:** http://localhost:15173
- **Backend API:** http://localhost:18000
- **Health Check:** http://localhost:18000/api/v1/ai-agents/health/
- **Swagger UI:** http://localhost:18000/api/schema/swagger-ui/
- **ReDoc:** http://localhost:18000/api/schema/redoc/

### Shared Infrastructure
- **PostgreSQL:** localhost:5432 (saraise-db)
- **Redis:** localhost:6379 (saraise-redis)

### Phase 1 Services (Existing)
- **Auth Service:** http://localhost:8001
- **Runtime Service:** http://localhost:8002
- **Policy Engine:** http://localhost:8003
- **Control Plane:** http://localhost:8004
- **Backend (Phase 1):** http://localhost:8005
- **Grafana:** http://localhost:3000
- **Prometheus:** http://localhost:9090
- **Jaeger:** http://localhost:16686

---

## Environment Variables

### Default Ports (can be overridden via .env)
```env
BACKEND_PORT=18000
FRONTEND_PORT=15173
```

### Backend Environment
```env
VITE_API_BASE_URL=http://localhost:18000
```

---

## Verification

### Check Network
```bash
docker network inspect saraise-network --format '{{range .Containers}}{{.Name}} {{end}}'
```

### Check Ports
```bash
docker ps --format "{{.Names}}\t{{.Ports}}" | grep saraise
```

### Test Services
```bash
# Backend
curl http://localhost:18000/api/v1/ai-agents/health/

# Frontend
curl http://localhost:15173
```

---

## Benefits

1. **Single Network:** All services communicate via one network
2. **No Conflicts:** Ports starting with "1" avoid conflicts with phase1
3. **Clear Convention:** Easy to identify Phase 6 services
4. **Shared Infrastructure:** Reuses existing postgres and redis
5. **Simplified Management:** One network to manage

---

## Migration Notes

### Breaking Changes
- Frontend URL changed from `http://localhost:5173` to `http://localhost:15173`
- Backend URL changed from `http://localhost:8000` to `http://localhost:18000`

### Update Required
- Browser bookmarks
- API client configurations
- Environment variables
- Documentation references

---

**Status:** ✅ COMPLETE

All containers now use single `saraise-network` and ports follow "1" prefix convention.

---

**Last Updated:** January 5, 2026

