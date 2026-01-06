# SARAISE Port Mapping Convention

**Date:** 2026-01-08  
**Status:** Standardized port mapping for clarity

---

## Port Convention

### Platform Containers: **1xxxx** ports
All platform services use ports starting with **1**:
- Example: `18000:8000` (external:internal)

### Application Containers: **2xxxx** ports
All application services use ports starting with **2**:
- Example: `28000:8000` (external:internal)

---

## Platform Services (1xxxx)

| Service | External Port | Internal Port | URL |
|---------|--------------|---------------|-----|
| PostgreSQL | 15432 | 5432 | `localhost:15432` |
| Redis | 16379 | 6379 | `localhost:16379` |
| Auth Service | 18001 | 8001 | `http://localhost:18001` |
| Runtime Service | 18002 | 8002 | `http://localhost:18002` |
| Policy Engine | 18003 | 8003 | `http://localhost:18003` |
| Control Plane | 18004 | 8004 | `http://localhost:18004` |
| Prometheus | 19090 | 9090 | `http://localhost:19090` |
| Grafana | 13000 | 3000 | `http://localhost:13000` |
| Jaeger UI | 16686 | 16686 | `http://localhost:16686` |

**Metrics Endpoints (1xxxx):**
- Auth Metrics: `19101:8001`
- Runtime Metrics: `19102:8002`
- Policy Engine Metrics: `19103:8003`
- Control Plane Metrics: `19104:8004`

---

## Application Services (2xxxx)

| Service | External Port | Internal Port | URL |
|---------|--------------|---------------|-----|
| PostgreSQL | 25432 | 5432 | `localhost:25432` |
| Redis | 26379 | 6379 | `localhost:26379` |
| Backend (Django) | 28000 | 8000 | `http://localhost:28000` |
| Frontend (React) | 25173 | 5173 | `http://localhost:25173` |
| Auth Service | 28001 | 8001 | `http://localhost:28001` |
| Runtime Service | 28002 | 8002 | `http://localhost:28002` |
| Policy Engine | 28003 | 8003 | `http://localhost:28003` |
| Control Plane | 28004 | 8004 | `http://localhost:28004` |
| Backend Legacy | 28005 | 8005 | `http://localhost:28005` |
| Prometheus | 29090 | 9090 | `http://localhost:29090` |
| Grafana | 23000 | 3000 | `http://localhost:23000` |
| Jaeger UI | 26686 | 16686 | `http://localhost:26686` |
| Alertmanager | 29093 | 9093 | `http://localhost:29093` |

**Metrics Endpoints (2xxxx):**
- Auth Metrics: `29101:8001`
- Runtime Metrics: `29102:8002`
- Policy Engine Metrics: `29103:8003`
- Control Plane Metrics: `29104:8004`

---

## Quick Reference

### Platform Docker Compose
```bash
cd saraise-platform
docker-compose -f docker-compose.dev.yml up -d
```

**Access:**
- Control Plane: `http://localhost:18004`
- Auth: `http://localhost:18001`
- Policy Engine: `http://localhost:18003`
- Runtime: `http://localhost:18002`

### Application Docker Compose
```bash
cd saraise-application
docker-compose -f docker-compose.dev.yml up -d
```

**Access:**
- Backend: `http://localhost:28000`
- Frontend: `http://localhost:25173`
- Control Plane: `http://localhost:28004`
- Auth: `http://localhost:28001`

---

## Notes

- Both docker-compose files can run simultaneously
- They share the same Docker network (`saraise-network`)
- They share the same PostgreSQL volume (`saraise-postgres-data`)
- Port conflicts are avoided by using different port ranges (1xxxx vs 2xxxx)
- Internal container ports remain the same (8000, 8001, etc.)
- Only external ports differ (18000 vs 28000)

---

## Environment Variables

### Application Backend
```bash
BACKEND_PORT=28000  # Application: 2xxxx
FRONTEND_PORT=25173  # Application: 2xxxx
```

### Platform Services
All platform services use 1xxxx ports by default in their docker-compose configuration.

---

## Testing

### Platform Services
```bash
# Control Plane
curl http://localhost:18004/health

# Auth
curl http://localhost:18001/health

# Policy Engine
curl http://localhost:18003/health

# Runtime
curl http://localhost:18002/health
```

### Application Services
```bash
# Backend
curl http://localhost:28000/api/health

# Control Plane
curl http://localhost:28004/health

# Auth
curl http://localhost:28001/health
```

---

## Summary

✅ **Platform = 1xxxx ports** (e.g., 18000, 18001, 18002, etc.)  
✅ **Application = 2xxxx ports** (e.g., 28000, 28001, 28002, etc.)  
✅ **No port conflicts** - Clear separation  
✅ **Both can run simultaneously** - Shared network and volumes

