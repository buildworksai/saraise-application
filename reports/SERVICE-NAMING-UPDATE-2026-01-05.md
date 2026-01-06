# Service Naming Update — Architecture-Aligned Names

**Date:** January 5, 2026  
**Status:** ✅ COMPLETE

---

## Summary

Updated Docker service names from phase-based names to architecture-aligned names for better clarity and maintainability.

---

## Changes

### Container Names Updated

| Old Name | New Name | Purpose |
|----------|----------|---------|
| `saraise-phase6-backend` | `saraise-backend` | Main Platform API (Django backend with modules) |
| `saraise-backend-phase1` | `saraise-backend-legacy` | Legacy Backend (Phase 4/5 compatibility) |
| `saraise-phase6-frontend` | `saraise-frontend` | Frontend UI (React application) |

### Service Names Updated

| Old Service Name | New Service Name | Purpose |
|------------------|------------------|---------|
| `backend-phase1` | `backend-legacy` | Legacy backend service |
| `backend` | `backend` | Main platform API (unchanged service name) |

---

## Rationale

### Architecture Alignment

Based on `docs/architecture/examples/config/env-naming.sh`:
- **Main Backend:** `saraise-backend` - The primary Django Platform API that hosts all modules
- **Legacy Backend:** `saraise-backend-legacy` - Legacy backend from Phase 4/5 for compatibility/testing

### Benefits

1. **Clear Purpose:** Names reflect architectural role, not implementation phase
2. **Maintainability:** Easier to understand service purpose without knowing phase history
3. **Consistency:** Aligns with architecture documentation naming standards
4. **Future-Proof:** Names remain meaningful as phases evolve

---

## Updated Files

### Docker Configuration
- `docker-compose.dev.yml` - Updated container names and service names

### Scripts
- `scripts/docker/start-all.sh` - Updated service descriptions

### Documentation
- `README-DOCKER-CONSOLIDATED.md` - Updated service names and descriptions
- `reports/SERVICE-NAMING-UPDATE-2026-01-05.md` - This document

---

## Verification

### Check Container Names
```bash
docker ps --format "{{.Names}}" | grep saraise | grep -E "(backend|frontend)"
```

**Expected Output:**
```
saraise-backend
saraise-backend-legacy
saraise-frontend
```

### Check Service Status
```bash
docker-compose -f docker-compose.dev.yml ps backend backend-legacy
```

### Test Platform API
```bash
curl http://localhost:18000/api/v1/ai-agents/health/
```

---

## Migration Notes

### Breaking Changes
- Container names changed (if scripts reference container names directly)
- Service name `backend-phase1` → `backend-legacy` (if scripts reference service names)

### Update Required
- Scripts that reference old container names
- Documentation that references old names
- CI/CD pipelines that reference old names
- Monitoring/alerting configurations

---

## Service URLs (Unchanged)

- **Platform API:** http://localhost:18000
- **Backend Legacy:** http://localhost:18005
- **Frontend UI:** http://localhost:15173

---

**Status:** ✅ COMPLETE

All service names updated to architecture-aligned names. Services running successfully.

---

**Last Updated:** January 5, 2026

