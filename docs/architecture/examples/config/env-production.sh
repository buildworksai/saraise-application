# ✅ APPROVED: Production Environment Configuration
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)
#            docs/architecture/application-architecture.md § 6 (Deployment)

# CRITICAL: Production secrets must NEVER be hardcoded
# Use Vault, environment variables, or secure secret management
# See docs/architecture/security-model.md § 5

# Database
# Fetch DB_PASSWORD from Vault or environment
POSTGRES_CONNECTION_STRING=postgresql://prod_user:${DB_PASSWORD}@prod_db:5432/saraise_prod
REDIS_URL=redis://prod_redis:6379

# Session Authentication
# CRITICAL: Fetch from Vault - DO NOT hardcode
# See docs/architecture/authentication-and-session-management-spec.md § 3.2
SESSION_SECRET_KEY=${SESSION_SECRET_KEY}  # Use secure secret from vault
SESSION_TIMEOUT=7200
COOKIE_DOMAIN=app.production.com

# Application
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO

