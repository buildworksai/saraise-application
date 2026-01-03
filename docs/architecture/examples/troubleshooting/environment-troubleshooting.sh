#!/bin/bash
# ✅ APPROVED: Environment-Specific Troubleshooting Commands
# Reference: docs/architecture/operational-runbooks.md § 2 (Troubleshooting)
# Also: docs/architecture/security-model.md § 5 (Environment Configuration)
# 
# CRITICAL NOTES:
# - All environment variables sourced from files (never hardcoded)
# - Secrets MUST be managed via Vault or CI/CD secret management
# - Configuration validation at startup ensures no missing required variables

# Development Environment
# Quick development fixes
# Reset everything
docker-compose down -v
docker-compose up -d

# Clear all data
docker-compose exec db psql -U saraise -d saraise -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
cd backend && python manage.py migrate && cd ..

# Check all services
docker-compose ps
docker-compose logs --tail=50

# Staging Environment
# Staging-specific checks
# Check environment variables
env | grep -E "(STAGING|STAGE)"

# Verify SSL certificates
openssl s_client -connect staging.saraise.com:443 -servername staging.saraise.com

# Check staging database
psql -h staging-db.saraise.com -U saraise -d saraise_staging -c "SELECT version();"

# Monitor staging logs
kubectl logs -f deployment/saraise-api -n staging

# Production Environment
# Production-specific checks
# Check production health
curl -f https://saraise.com/health

# Verify production database
psql -h prod-db.saraise.com -U saraise -d saraise_prod -c "SELECT COUNT(*) FROM users;"

# Check production logs
kubectl logs -f deployment/saraise-api -n production

# Monitor production metrics
kubectl top pods -n production

