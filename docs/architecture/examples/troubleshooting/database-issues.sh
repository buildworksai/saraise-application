#!/bin/bash
# ✅ APPROVED: Database Troubleshooting Commands
# Reference: docs/architecture/operational-runbooks.md § 2 (Troubleshooting)
# Also: docs/architecture/application-architecture.md § 4.1 (Row-Level Multitenancy)
# 
# CRITICAL NOTES:
# - All queries MUST include tenant_id filtering (Row-Level Multitenancy)
# - Connection failures may indicate database misconfiguration
# - Django migrations MUST be idempotent (never modify existing migrations)
# - Database transactions managed at service layer (not in route handlers)

# Problem: Database connection failures
# Symptoms
# - "Database connection failed" errors
# - 500 Internal Server Error
# - Connection timeout errors

# Diagnosis
# 1. Check PostgreSQL status
# 2. Verify connection string
# 3. Check database permissions
# 4. Validate network connectivity

# Solutions
# Check PostgreSQL status
docker ps | grep postgres

# Test database connection
psql -h localhost -p 5432 -U postgres -d saraise -c "SELECT 1;"

# Check connection string
echo $POSTGRES_CONNECTION_STRING

# Restart database
docker-compose restart db

# Check database logs
docker logs saraise-db

# Problem: Migration failures
# Symptoms
# - Django migration errors
# - "Table already exists" errors
# - Schema mismatch errors

# Diagnosis
# 1. Check migration history
# 2. Verify database schema
# 3. Check for conflicting migrations
# 4. Validate migration files

# Solutions
# Check migration status (Django)
cd backend && python manage.py showmigrations && cd ..

# Check migration history (Django)
cd backend && python manage.py showmigrations --list && cd ..

# Reset migrations (development only - Django)
cd backend && python manage.py migrate zero && python manage.py migrate && cd ..

# Check database schema
psql -h localhost -p 5432 -U postgres -d saraise -c "\dt"

