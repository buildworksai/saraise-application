# SARAISE Docker Deployment Guide

**Last Updated:** January 5, 2026

---

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- Git

### Start Development Environment

```bash
# Clone repository
git clone <repository-url>
cd saraise

# Start all services
./scripts/docker/start-dev.sh
```

**Services will be available at:**
- Frontend UI: http://localhost:15173
- Backend API: http://localhost:18000
- PostgreSQL: localhost:5432 (saraise-db)
- Redis: localhost:6379 (saraise-redis)

**Note:** All external ports start with "1" prefix to avoid conflicts. Internal container ports remain standard (8000, 5173, etc.).

---

## Docker Services

### Frontend (Vite Dev Server)
- **External Port:** 15173 (mapped to internal 5173)
- **Image:** Node.js 18.19.1 Alpine
- **Hot Reload:** Enabled
- **API Proxy:** Configured to backend

### Backend (Django API)
- **External Port:** 18000 (mapped to internal 8000)
- **Image:** Python (from backend/Dockerfile)
- **Database:** PostgreSQL
- **Cache:** Redis
- **Auto-migrate:** Enabled on startup

### PostgreSQL
- **Port:** 5432
- **Database:** saraise
- **User:** postgres
- **Password:** postgres
- **Volume:** Persistent data storage

### Redis
- **Port:** 6379
- **Purpose:** Session store & caching
- **Volume:** Persistent data storage

---

## Environment Variables

Create `.env` file in project root:

```env
# Database
POSTGRES_PORT=5432

# Redis
REDIS_PORT=6379

# Backend
BACKEND_PORT=8000
SECRET_KEY=your-secret-key-here

# Frontend
FRONTEND_PORT=5173
```

**Note:** `.env` file is gitignored. Never commit secrets.

---

## Docker Commands

### Start Services
```bash
./scripts/docker/start-dev.sh
# or
docker-compose -f docker-compose.dev.yml up -d
```

### Stop Services
```bash
./scripts/docker/stop-dev.sh
# or
docker-compose -f docker-compose.dev.yml down
```

### View Logs
```bash
# All services
./scripts/docker/logs.sh

# Specific service
./scripts/docker/logs.sh backend
./scripts/docker/logs.sh frontend
./scripts/docker/logs.sh postgres
./scripts/docker/logs.sh redis
```

### Rebuild Services
```bash
docker-compose -f docker-compose.dev.yml build
docker-compose -f docker-compose.dev.yml up -d
```

### Access Container Shell
```bash
# Backend
docker exec -it saraise-backend bash

# Frontend
docker exec -it saraise-frontend sh
```

### Database Access
```bash
# PostgreSQL CLI
docker exec -it saraise-postgres psql -U postgres -d saraise

# Redis CLI
docker exec -it saraise-redis redis-cli
```

---

## Health Checks

### Backend Health
```bash
curl http://localhost:18000/api/v1/ai-agents/health/
```

Expected response:
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "redis": "ok",
    "agent_queue": {
      "status": "ok",
      "active_agents": 0
    }
  }
}
```

### Frontend Health
```bash
curl http://localhost:15173
```

Should return HTML page.

---

## Troubleshooting

### Services Won't Start

1. **Check Docker is running:**
   ```bash
   docker info
   ```

2. **Check ports are available:**
   ```bash
   # Check if ports are in use (external ports start with 1)
   lsof -i :18000  # Backend
   lsof -i :15173  # Frontend
   lsof -i :5432   # PostgreSQL
   lsof -i :6379   # Redis
   ```

3. **View service logs:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs
   ```

### Database Connection Issues

1. **Check PostgreSQL is healthy:**
   ```bash
   docker-compose -f docker-compose.dev.yml ps postgres
   ```

2. **Check database logs:**
   ```bash
   docker-compose -f docker-compose.dev.yml logs postgres
   ```

3. **Verify connection string:**
   - Should be: `postgresql://postgres:postgres@postgres:5432/saraise`
   - Note: Use service name `postgres`, not `localhost`

### Frontend Can't Connect to Backend

1. **Check backend is running:**
   ```bash
   curl http://localhost:18000/api/v1/ai-agents/health/
   ```

2. **Check Vite proxy configuration:**
   - File: `frontend/vite.config.ts`
   - Proxy target: `http://localhost:18000`

3. **Check network:**
   ```bash
   docker network inspect saraise_saraise-network
   ```

### Volume Issues

1. **List volumes:**
   ```bash
   docker volume ls
   ```

2. **Remove volumes (WARNING: deletes data):**
   ```bash
   docker-compose -f docker-compose.dev.yml down -v
   ```

---

## Production Deployment

For production deployment:

1. **Create production docker-compose:**
   ```bash
   cp docker-compose.dev.yml docker-compose.prod.yml
   ```

2. **Update configurations:**
   - Use production Dockerfiles
   - Configure SSL/TLS
   - Set secure secrets
   - Enable monitoring

3. **Use production nginx:**
   - File: `frontend/nginx.conf`
   - Configure API proxy
   - Enable caching
   - Set security headers

---

## Development Workflow

### Making Changes

1. **Code changes are hot-reloaded:**
   - Frontend: Vite dev server auto-reloads
   - Backend: Django runserver auto-reloads (if configured)

2. **Database migrations:**
   ```bash
   docker exec -it saraise-backend python manage.py makemigrations
   docker exec -it saraise-backend python manage.py migrate
   ```

3. **Install new dependencies:**
   ```bash
   # Backend
   docker exec -it saraise-backend pip install <package>
   
   # Frontend
   docker exec -it saraise-frontend npm install <package>
   ```

### Running Tests

```bash
# Backend tests
docker exec -it saraise-backend pytest tests -v

# Frontend tests
docker exec -it saraise-frontend npm test
```

---

## Network Architecture

```
┌─────────────────────────────────────────┐
│         Docker Network                   │
│         (saraise-network)                │
│                                          │
│  ┌──────────┐  ┌──────────┐            │
│  │ Frontend │──│ Backend  │            │
│  │ :5173    │  │ :8000    │            │
│  └──────────┘  └────┬─────┘            │
│                     │                   │
│              ┌──────┴──────┐            │
│              │             │            │
│         ┌────▼───┐   ┌────▼───┐        │
│         │Postgres│   │ Redis  │        │
│         │ :5432  │   │ :6379  │        │
│         └────────┘   └────────┘        │
└─────────────────────────────────────────┘
```

**Service Communication:**
- Frontend → Backend: Via Docker network (`http://backend:8000` - internal port)
- Backend → PostgreSQL: Via Docker network (`saraise-db:5432`)
- Backend → Redis: Via Docker network (`saraise-redis:6379`)

**External Access (ports start with "1" prefix):**
- Frontend: `http://localhost:15173` (host machine)
- Backend: `http://localhost:18000` (host machine)
- PostgreSQL: `localhost:5432` (host machine, shared with phase1)
- Redis: `localhost:6379` (host machine, shared with phase1)

**Network:**
- All services use single `saraise-network` (shared with phase1 containers)

---

## Security Notes

1. **Never commit `.env` files** - Contains secrets
2. **Use strong SECRET_KEY** - Generate with: `python3 -c 'import secrets; print(secrets.token_hex(32))'`
3. **Change default passwords** - PostgreSQL and Redis use default passwords in dev
4. **Enable SSL/TLS** - For production deployments
5. **Restrict network access** - Use firewall rules in production

---

## Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Django Deployment Guide](https://docs.djangoproject.com/en/stable/howto/deployment/)
- [Vite Configuration](https://vitejs.dev/config/)
- [Nginx Configuration](https://nginx.org/en/docs/)

---

**For issues or questions, see:** `docs/modules/01-foundation/ai-agent-management/USER-GUIDE.md`

