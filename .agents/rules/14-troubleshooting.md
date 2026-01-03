---
description: Troubleshooting and debugging guides for SARAISE infrastructure
globs: **/*
alwaysApply: true
---

# 🔧 SARAISE Troubleshooting & Debugging Guide

**⚠️ CRITICAL**: Use these systematic debugging approaches to resolve issues quickly and efficiently.

## SARAISE-19001 Troubleshooting Methodology

### Debugging Process
1. **Identify**: What is the problem?
2. **Isolate**: Which service/component is affected?
3. **Investigate**: Check logs, metrics, and health checks
4. **Diagnose**: Root cause analysis
5. **Resolve**: Apply fix and verify
6. **Prevent**: Document and implement safeguards

### Service Health Check Commands
```bash
# ✅ REQUIRED: Quick health check commands
# Check all services status
docker-compose ps

# Check service logs
docker-compose logs [service_name]

# Check service health endpoints
curl -f http://localhost:${API_HOST_PORT:-30000}/health
curl -f http://localhost:${FRONTEND_HOST_PORT:-20000}
curl -f http://localhost:${PROMETHEUS_HOST_PORT:-19090}/-/healthy
curl -f http://localhost:${GRAFANA_HOST_PORT:-13001}/api/health
curl -f http://localhost:${LOKI_HOST_PORT:-13100}/ready
curl -f http://localhost:${FLOWER_HOST_PORT:-15555}/api/workers
```

## SARAISE-19002 Common Issues & Solutions

### Database Issues

#### Problem: Database Connection Failed
```bash
# Symptoms
ERROR: could not connect to server: Connection refused
ERROR: database "saraise" does not exist

# Diagnosis
docker-compose logs db
docker exec saraise-db-1 pg_isready -U postgres

# Solutions
# 1. Check if database is running
docker-compose up -d db

# 2. Check database logs
docker-compose logs db --tail 50

# 3. Verify connection string
echo $POSTGRES_CONNECTION_STRING

# 4. Test connection
docker exec -it saraise-db-1 psql -U postgres -d saraise -c "SELECT 1;"
```

#### Problem: Django Migration Failed
```bash
# Symptoms
ERROR: relation "users" does not exist
ERROR: django.core.management.base.CommandError: No migrations to apply

# Diagnosis
cd backend
python manage.py showmigrations
python manage.py showmigrations --list

# Solutions
# 1. Check migration status
python manage.py showmigrations

# 2. Reset migrations (development only)
python manage.py migrate zero
python manage.py migrate

# 3. Create new migration
python manage.py makemigrations module_name

# 4. Apply migration
python manage.py migrate
```

### Redis Issues

#### Problem: Redis Connection Failed
```bash
# Symptoms
redis.exceptions.ConnectionError: Error 111 connecting to redis:6379
ERROR: Redis connection failed

# Diagnosis
docker-compose logs redis
docker exec saraise-redis-1 redis-cli ping

# Solutions
# 1. Check Redis status
docker-compose ps redis

# 2. Check Redis logs
docker-compose logs redis --tail 20

# 3. Test Redis connection
docker exec saraise-redis-1 redis-cli ping

# 4. Restart Redis
docker-compose restart redis
```

### MinIO Issues

#### Problem: MinIO Connection Failed
```bash
# Symptoms
ERROR: The specified bucket does not exist
ERROR: Access Denied

# Diagnosis
docker-compose logs minio
curl -f http://localhost:${MINIO_API_HOST_PORT:-19000}/minio/health/live

# Solutions
# 1. Check MinIO status
docker-compose ps minio

# 2. Check MinIO logs
docker-compose logs minio --tail 20

# 3. Test MinIO connection
curl -f http://localhost:${MINIO_API_HOST_PORT:-19000}/minio/health/live

# 4. Verify credentials
echo $MINIO_ACCESS_KEY
echo $MINIO_SECRET_KEY

# 5. Restart MinIO
docker-compose restart minio
```

## SARAISE-19003 Application-Specific Issues

### API Issues

#### Problem: API Not Starting
```bash
# Symptoms
ERROR: ModuleNotFoundError: No module named 'src'
ERROR: ImportError: cannot import name 'app'

# Diagnosis
docker-compose logs api
docker exec saraise-api-1 python -c "import src.main"

# Solutions
# 1. Check Python path
docker exec saraise-api-1 python -c "import sys; print(sys.path)"

# 2. Check imports
docker exec saraise-api-1 python -c "from src.main import app"

# 3. Install dependencies
docker exec saraise-api-1 pip install -e .

# 4. Check environment variables
docker exec saraise-api-1 env | grep -E "(POSTGRES|REDIS|MINIO)"

# 5. Restart API
docker-compose restart api
```

### Frontend Issues

#### Problem: Frontend Not Loading
```bash
# Symptoms
ERROR: Connection refused
ERROR: 404 Not Found

# Diagnosis
docker-compose logs ui
curl -f http://localhost:${FRONTEND_HOST_PORT:-15000}

# Solutions
# 1. Check frontend status
docker-compose ps ui

# 2. Check frontend logs
docker-compose logs ui --tail 20

# 3. Test frontend health
curl -f http://localhost:${FRONTEND_HOST_PORT:-15000}

# 4. Check build
docker exec saraise-ui-1 npm run build

# 5. Restart frontend
docker-compose restart ui
```

## SARAISE-19004 Performance Issues

### Slow Response Times
```bash
# Diagnosis
# 1. Check response times
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:${API_HOST_PORT:-30000}/api/v1/health

# 2. Check database performance
docker exec saraise-db-1 psql -U postgres -d saraise -c "SELECT * FROM pg_stat_activity;"

# 3. Check Redis performance
docker exec saraise-redis-1 redis-cli --latency

# 4. Check Prometheus metrics
curl -f http://localhost:${PROMETHEUS_HOST_PORT:-19090}/api/v1/query?query=rate(http_request_duration_seconds[5m])

# Solutions
# 1. Optimize database queries
# 2. Add database indexes
# 3. Implement caching
# 4. Scale services
```

## SARAISE-19005 Network Issues

### Port Conflicts
```bash
# Symptoms
ERROR: bind: address already in use
ERROR: port is already allocated

# Diagnosis
# 1. Check port usage
netstat -tulpn | grep :${API_HOST_PORT:-30000}
lsof -i :${API_HOST_PORT:-30000}

# 2. Check Docker port mapping
docker-compose ps

# Solutions
# 1. Stop conflicting services
sudo lsof -ti:${API_HOST_PORT:-30000} | xargs kill -9

# 2. Change port mapping
# Edit docker-compose.yml
ports:
  - "30001:30000"  # Change host port

# 3. Restart services
docker-compose down
docker-compose up -d
```

## SARAISE-19006 Log Analysis

### Log Collection
```bash
# ✅ REQUIRED: Log collection commands
# Collect all logs
docker-compose logs --tail 100 > all_logs.txt

# Collect specific service logs
docker-compose logs --tail 100 api > api_logs.txt
docker-compose logs --tail 100 db > db_logs.txt
docker-compose logs --tail 100 redis > redis_logs.txt

# Collect logs with timestamps
docker-compose logs -t --tail 100 > logs_with_timestamps.txt
```

### Log Analysis Patterns
```bash
# ✅ REQUIRED: Log analysis commands
# Find errors
grep -i "error\|exception\|failed" all_logs.txt

# Find warnings
grep -i "warning\|warn" all_logs.txt

# Find specific patterns
grep -i "connection.*refused" all_logs.txt
grep -i "timeout" all_logs.txt
grep -i "cors" all_logs.txt

# Count occurrences
grep -c "ERROR" all_logs.txt
grep -c "WARNING" all_logs.txt

# Find recent errors
grep -i "error" all_logs.txt | tail -20
```

## SARAISE-19007 Emergency Procedures

### Service Recovery
```bash
# ✅ REQUIRED: Emergency recovery procedures
# 1. Stop all services
docker-compose down

# 2. Clean up containers
docker-compose rm -f

# 3. Clean up volumes (if needed)
docker-compose down -v

# 4. Restart services
docker-compose up -d

# 5. Check service health
./scripts/test-services.sh
```

### Data Recovery
```bash
# ✅ REQUIRED: Data recovery procedures
# 1. Backup database
docker exec saraise-db-1 pg_dump -U postgres saraise > backup.sql

# 2. Backup Redis data
docker exec saraise-redis-1 redis-cli BGSAVE

# 3. Backup MinIO data
docker exec saraise-minio-1 mc mirror /data /backup

# 4. Restore database
docker exec -i saraise-db-1 psql -U postgres saraise < backup.sql
```

## SARAISE-19008 Debugging Tools

### Container Debugging
```bash
# ✅ REQUIRED: Container debugging commands
# Access container shell
docker exec -it saraise-api-1 /bin/bash
docker exec -it saraise-db-1 /bin/bash
docker exec -it saraise-redis-1 /bin/bash

# Check container resources
docker stats saraise-api-1
docker exec saraise-api-1 top
docker exec saraise-api-1 df -h

# Check container network
docker exec saraise-api-1 netstat -tulpn
```

### Service Debugging
```bash
# ✅ REQUIRED: Service debugging commands
# Check service configuration
docker exec saraise-api-1 python -c "from src.config.settings import settings; print(settings.model_dump())"

# Check service health
curl -f http://localhost:${API_HOST_PORT:-30000}/health
curl -f http://localhost:${API_HOST_PORT:-30000}/health/detailed

# Check service metrics
curl -f http://localhost:${API_HOST_PORT:-30000}/metrics

# Check service logs
docker-compose logs -f api
```

## SARAISE-19009 Prevention Strategies

### Monitoring Setup
```bash
# ✅ REQUIRED: Monitoring setup
# 1. Set up Prometheus alerts
# 2. Configure Grafana dashboards
# 3. Set up log aggregation
# 4. Implement health checks
# 5. Set up automated testing
```

### Regular Maintenance
```bash
# ✅ REQUIRED: Regular maintenance tasks
# 1. Update dependencies
docker-compose pull
docker-compose up -d

# 2. Clean up old containers
docker system prune -f

# 3. Clean up old images
docker image prune -f

# 4. Backup data
./scripts/backup-data.sh

# 5. Update configurations
# Review and update environment variables
# Review and update service configurations
```

---

**Next Steps**: Use these troubleshooting procedures systematically. Document any new issues and solutions for future reference. Implement monitoring and alerting to prevent issues from occurring.
