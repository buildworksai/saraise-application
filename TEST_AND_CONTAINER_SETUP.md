# Test and Container Setup Guide

**Date:** 2026-01-07

## Quick Start: Run Tests

### Frontend Tests

```bash
cd frontend
npm test -- --coverage --run
```

**Expected Output:**
- Test Files: 20+ passed
- Tests: 100+ passed
- Coverage: Should be approaching 90%

### Backend Tests

```bash
cd backend

# Set up virtual environment (if not already done)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e .[dev]

# Run licensing tests
pytest src/core/licensing/tests/ -v --cov=src/core/licensing --cov-report=html --cov-fail-under=90

# Run all backend tests
pytest src/ -v --cov=src --cov-report=html --cov-fail-under=90
```

---

## Container Setup

### Prerequisites

1. **Docker and Docker Compose** must be installed and running
2. **Network** must exist: `saraise-network`

### Step 1: Create Network (if needed)

```bash
docker network create saraise-network || true
```

### Step 2: Start Containers

```bash
cd /Users/raghunathchava/Code/saraise-application

# Start all services
docker-compose -f docker-compose.dev.yml up -d --build

# Check status
docker-compose -f docker-compose.dev.yml ps

# View logs
docker-compose -f docker-compose.dev.yml logs -f
```

### Step 3: Wait for Services

Wait ~30 seconds for services to be healthy:

```bash
# Check backend health
curl http://localhost:28000/api/v1/health/

# Check frontend
curl http://localhost:25173/
```

### Step 4: Run Tests in Containers

#### Frontend Tests (in container)

```bash
# Run tests inside frontend container
docker-compose -f docker-compose.dev.yml exec frontend npm test -- --coverage --run
```

#### Backend Tests (in container)

```bash
# Run tests inside backend container
docker-compose -f docker-compose.dev.yml exec backend pytest src/core/licensing/tests/ -v --cov=src/core/licensing --cov-report=term --cov-fail-under=90
```

---

## Services and Ports

| Service | Container Name | Port | URL |
|---------|---------------|------|-----|
| Backend API | `api` | 28000 | http://localhost:28000 |
| Frontend UI | `ui-web` | 25173 | http://localhost:25173 |
| PostgreSQL | `application-db` | 25432 | localhost:25432 |
| Redis | `application-redis` | 26379 | localhost:26379 |
| Prometheus | `application-prometheus` | 29090 | http://localhost:29090 |
| Grafana | `application-grafana` | 23000 | http://localhost:23000 |
| Jaeger | `application-jaeger` | 26686 | http://localhost:26686 |

---

## Troubleshooting

### Containers won't start

1. **Check Docker is running:**
   ```bash
   docker ps
   ```

2. **Check port conflicts:**
   ```bash
   lsof -i :28000
   lsof -i :25173
   ```

3. **Check network exists:**
   ```bash
   docker network ls | grep saraise-network
   ```

4. **View container logs:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs backend
   docker-compose -f docker-compose.dev.yml logs frontend
   ```

### Tests failing

1. **Frontend:**
   - Ensure `@testing-library/user-event` is installed: `npm install`
   - Check for TypeScript errors: `npm run typecheck`
   - Check for linting errors: `npm run lint`

2. **Backend:**
   - Ensure virtual environment is activated
   - Install dependencies: `pip install -e .[dev]`
   - Run migrations: `python manage.py migrate`

### Database connection issues

1. **Check PostgreSQL is running:**
   ```bash
   docker-compose -f docker-compose.dev.yml ps postgres
   ```

2. **Check database health:**
   ```bash
   docker-compose -f docker-compose.dev.yml exec postgres pg_isready -U postgres
   ```

3. **Run migrations:**
   ```bash
   docker-compose -f docker-compose.dev.yml exec backend python manage.py migrate
   ```

---

## Stop Containers

```bash
# Stop all containers
docker-compose -f docker-compose.dev.yml down

# Stop and remove volumes
docker-compose -f docker-compose.dev.yml down -v
```

---

## Test Coverage Goals

| Component | Target | Current |
|-----------|--------|---------|
| Frontend | ≥90% | ~35-40% (improving) |
| Backend - Licensing | ≥90% | ~95% (estimated) |
| Backend - Overall | ≥90% | Needs verification |

---

## Next Steps

1. ✅ **Frontend tests added** - 19+ new test files
2. ⚠️ **Run coverage** - Verify current percentage
3. ⚠️ **Add more tests** - If below 90%, add tests for remaining components
4. ⚠️ **Backend tests** - Set up environment and verify coverage

---

**Last Updated:** 2026-01-07
