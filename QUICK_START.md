# Quick Start: Rebuild and Test

## Fixes Applied ✅

1. ✅ Added `requests` dependency to `pyproject.toml`
2. ✅ Fixed `LicenseStatus` import in middleware
3. ✅ Updated Dockerfile to install `[dev]` dependencies
4. ✅ Created robust startup script with error handling

## Commands to Run

### 1. Rebuild and Start Containers

```bash
cd /Users/raghunathchava/Code/saraise-application

# Stop existing
docker-compose -f docker-compose.dev.yml down

# Create network if needed
docker network create saraise-network 2>/dev/null || true

# Rebuild backend
docker-compose -f docker-compose.dev.yml build --no-cache backend

# Start all services
docker-compose -f docker-compose.dev.yml up -d

# Wait for startup
sleep 30

# Check status
docker-compose -f docker-compose.dev.yml ps
```

### 2. Verify Backend is Running

```bash
# Check logs
docker-compose -f docker-compose.dev.yml logs backend --tail=50

# Test health endpoint
curl http://localhost:28000/api/v1/health/
```

### 3. Run Tests

#### Frontend Tests
```bash
# In container
docker-compose -f docker-compose.dev.yml exec frontend npm test -- --coverage --run

# Or directly
cd frontend && npm test -- --coverage --run
```

#### Backend Tests
```bash
# In container
docker-compose -f docker-compose.dev.yml exec backend pytest src/core/licensing/tests/ -v --cov=src/core/licensing --cov-report=term --cov-fail-under=90

# Or directly (if venv set up)
cd backend
source venv/bin/activate
pytest src/core/licensing/tests/ -v --cov=src/core/licensing --cov-report=html --cov-fail-under=90
```

## Expected Results

- ✅ Backend container starts successfully
- ✅ All migrations run
- ✅ Default users seeded
- ✅ Server running on port 28000
- ✅ Frontend tests: 100+ tests passing
- ✅ Backend tests: All licensing tests passing
- ✅ Coverage: Frontend approaching 90%, Backend ~95% for licensing

---

**Ready to execute!** Run the commands above to rebuild and test.
