# Both Platform and Application Containers Running

**Date:** 2026-01-08  
**Status:** ✅ Both platform and application containers are running simultaneously

---

## Port Convention Summary

✅ **Platform containers: 1xxxx ports** (e.g., 18000, 18001, 18002, etc.)  
✅ **Application containers: 2xxxx ports** (e.g., 28000, 28001, 28002, etc.)

---

## Current Running Services

### Platform Services (1xxxx ports)
- **Control Plane**: `http://localhost:18004` ✅
- **Auth Service**: `http://localhost:18001` ✅
- **Policy Engine**: `http://localhost:18003` ✅
- **Runtime Service**: `http://localhost:18002` ✅
- **PostgreSQL**: `localhost:15432` ✅
- **Redis**: `localhost:16379` ✅
- **Prometheus**: `http://localhost:19090` ✅
- **Grafana**: `http://localhost:13000` ✅
- **Jaeger UI**: `http://localhost:16686` ✅

### Application Services (2xxxx ports)
- **Backend (Django)**: `http://localhost:28000` ✅
- **Frontend (React)**: `http://localhost:25173` ✅
- **PostgreSQL**: `localhost:25432` ✅
- **Redis**: `localhost:26379` ✅
- **Prometheus**: `http://localhost:29090` ✅
- **Grafana**: `http://localhost:23000` ✅
- **Jaeger UI**: `http://localhost:26686` ✅
- **Alertmanager**: `http://localhost:29093` ✅

---

## Architecture Notes

### Shared Infrastructure
- Both docker-compose files share the same Docker network (`saraise-network`)
- Both docker-compose files share the same PostgreSQL volume (`saraise-postgres-data`)
- Platform services are **only** managed by `saraise-platform/docker-compose.dev.yml`
- Application services are **only** managed by `saraise-application/docker-compose.dev.yml`

### Container Name Strategy
- Platform services use standard names (e.g., `saraise-control-plane`, `saraise-auth`)
- Application observability services use prefixed names (e.g., `saraise-application-prometheus`, `saraise-application-jaeger`)
- This avoids container name conflicts when both docker-compose files run simultaneously

---

## Quick Start Commands

### Start Platform Services
```bash
cd saraise-platform
docker-compose -f docker-compose.dev.yml up -d
```

### Start Application Services
```bash
cd saraise-application
docker-compose -f docker-compose.dev.yml up -d
```

### Stop Platform Services
```bash
cd saraise-platform
docker-compose -f docker-compose.dev.yml down
```

### Stop Application Services
```bash
cd saraise-application
docker-compose -f docker-compose.dev.yml down
```

### View All Running Containers
```bash
docker ps | grep saraise
```

---

## Testing Endpoints

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

# Frontend (browser)
open http://localhost:25173
```

---

## Port Mapping Reference

See `PORT_MAPPING.md` for complete port mapping documentation.

---

## Troubleshooting

### Container Name Conflicts
If you see "container name already in use" errors:
1. Stop all containers: `docker ps -a | grep saraise | xargs docker rm -f`
2. Restart platform services first
3. Then restart application services

### Port Conflicts
If you see "port already allocated" errors:
1. Check which process is using the port: `lsof -i :PORT`
2. Ensure you're using the correct port convention (1xxxx for platform, 2xxxx for application)

### Network Issues
If services can't communicate:
1. Verify both are on the same network: `docker network inspect saraise-network`
2. Use service names (not localhost) for inter-container communication

---

## Summary

✅ **Both platform and application containers are running**  
✅ **Clear port separation (1xxxx vs 2xxxx)**  
✅ **No container name conflicts**  
✅ **Shared network and volumes**  
✅ **Ready for testing and development**

