# ✅ APPROVED: Required Environment Variables
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)
#            docs/architecture/application-architecture.md § 6 (Deployment)

# CRITICAL: All sensitive values must be sourced from environment or Vault
# NO hardcoded secrets in configuration files
# See docs/architecture/security-model.md § 5

# Database Configuration
# ⚠️ Ports defined in docs/architecture/operational-runbooks.md § 1
POSTGRES_CONNECTION_STRING=postgresql://postgres:postgres@localhost:${POSTGRES_HOST_PORT:-25432}/saraise
REDIS_URL=redis://localhost:${REDIS_HOST_PORT:-26379}

# Object Storage (MinIO)
# ⚠️ Ports defined in docs/architecture/operational-runbooks.md § 2.2
MINIO_ENDPOINT=localhost:${MINIO_API_HOST_PORT:-19000}
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=saraise-storage
MINIO_SECURE=false

# Session Authentication
# CRITICAL: SESSION_SECRET_KEY must be cryptographically random
# Generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'
# See docs/architecture/authentication-and-session-management-spec.md § 3.2
SESSION_SECRET_KEY=your-session-secret-key-generate-a-strong-one
SESSION_TIMEOUT=7200  # 2 hours in seconds
COOKIE_DOMAIN=localhost

# Application Configuration
APP_ENV=development
APP_DEBUG=true
LOG_LEVEL=INFO

# Email Configuration (MailHog)
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=false

# AI/ML Configuration (OpenAI)
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_ORG_ID=your-openai-org-id-here

# Vault Configuration
VAULT_ADDR=http://localhost:18200
VAULT_TOKEN=dev-token
VAULT_NAMESPACE=

# Multi-tenant Configuration
DEFAULT_TENANT_ID=default
TENANT_ISOLATION_MODE=schema-per-tenant

