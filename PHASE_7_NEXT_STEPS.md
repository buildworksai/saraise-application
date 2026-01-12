# Phase 7 - Next Steps (Docker Environment)

**Quick start guide for Phase 7 implementation in Docker.**

---

## 🚀 Immediate Actions Required

### 1. Rebuild Backend Container

**CRITICAL:** The Dockerfile has been updated with WeasyPrint system dependencies. You must rebuild:

```bash
# Rebuild backend container
docker-compose -f docker-compose.dev.yml build backend

# Restart services
docker-compose -f docker-compose.dev.yml up -d
```

**Or use convenience scripts:**
```bash
./scripts/docker/stop-dev.sh
./scripts/docker/start-dev.sh
```

### 2. Verify Migrations

Migrations run automatically on startup. Check logs:

```bash
docker-compose -f docker-compose.dev.yml logs backend | grep -i migration
```

**Expected output:**
```
🔄 Running migrations...
✅ Migrations complete
```

The new migration `0007_add_push_notification_token.py` will create the `push_notification_tokens` table.

### 3. Test New Functionality

```bash
# Run Phase 7 tests
./scripts/docker/run-tests.sh api src/modules/workflow_automation/tests/test_action_executor.py
./scripts/docker/run-tests.sh api src/core/notifications/tests/test_services.py
./scripts/docker/run-tests.sh api src/modules/billing_subscriptions/tests/test_payment_service.py
./scripts/docker/run-tests.sh api src/modules/integration_platform/tests/test_services_additional.py
```

---

## 📋 Checklist

- [ ] Rebuild backend container
- [ ] Verify migrations completed successfully
- [ ] Run Phase 7 tests
- [ ] Configure environment variables (if using external services)
- [ ] Test SMS notifications (requires AWS SNS)
- [ ] Test push notifications (requires Firebase)
- [ ] Test payment processing (requires Stripe/Razorpay)
- [ ] Run full test suite
- [ ] Verify all services are running

---

## 🔧 Docker Commands Quick Reference

### Container Management
```bash
# Start all services
docker-compose -f docker-compose.dev.yml up -d

# Stop all services
docker-compose -f docker-compose.dev.yml down

# View logs
docker-compose -f docker-compose.dev.yml logs -f backend

# Restart backend
docker-compose -f docker-compose.dev.yml restart backend
```

### Running Commands
```bash
# Run migrations
./scripts/docker/run-migrations.sh

# Run tests
./scripts/docker/run-tests.sh

# Install dependencies
./scripts/docker/install-deps.sh

# Backend shell
docker exec -it api bash

# Django shell
docker exec -it api python manage.py shell
```

---

## 🌐 Service URLs

- **Backend API:** http://localhost:28000
- **Frontend UI:** http://localhost:25173
- **PostgreSQL:** localhost:25432
- **Redis:** localhost:26379

---

## 📚 Documentation

- **Full Implementation Details:** `PHASE_7_IMPLEMENTATION_COMPLETE.md`
- **Docker Setup Guide:** `PHASE_7_DOCKER_SETUP.md`
- **Docker General Guide:** `README-DOCKER.md`

---

## ⚠️ Important Notes

1. **All commands run in Docker** - Use `docker exec -it api` or convenience scripts
2. **Migrations run automatically** - On container startup via `start.sh`
3. **Dependencies installed on build** - Rebuild container after `pyproject.toml` changes
4. **Environment variables** - Add to `.env` or `docker-compose.dev.yml`

---

## 🐛 Troubleshooting

### Container won't start
```bash
docker-compose -f docker-compose.dev.yml logs backend
```

### Migrations fail
```bash
docker exec -it api python manage.py migrate --noinput
```

### Dependencies missing
```bash
docker-compose -f docker-compose.dev.yml build --no-cache backend
```

---

**Ready to proceed!** Start with rebuilding the container, then verify migrations and run tests.
