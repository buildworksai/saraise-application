# ✅ APPROVED: Development Environment Configuration
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)
#            docs/architecture/authentication-and-session-management-spec.md § 3.2

# CRITICAL: Development secrets are NOT suitable for production
# Use Vault or environment variables for production
# See docs/architecture/security-model.md § 5

# Database
POSTGRES_CONNECTION_STRING=postgresql://postgres:postgres@localhost:25432/saraise_dev
REDIS_URL=redis://localhost:26379

# Session Authentication
# NOTE: This is a development key - must be changed for production
SESSION_SECRET_KEY=dev-session-secret-key-change-in-production
SESSION_TIMEOUT=7200
COOKIE_DOMAIN=localhost

# Application
APP_ENV=development
APP_DEBUG=true
LOG_LEVEL=DEBUG

