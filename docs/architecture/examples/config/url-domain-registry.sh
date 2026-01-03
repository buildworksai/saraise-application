# ✅ APPROVED: Base URLs and Domain Registry
# Reference: docs/architecture/application-architecture.md § 6 (Deployment)

# CRITICAL: All URLs must be environment-configured
# No hardcoded URLs in code
# See docs/architecture/application-architecture.md § 6

FRONTEND_BASE_URL=http://localhost:${FRONTEND_HOST_PORT:-20000}
API_BASE_URL=http://localhost:${API_HOST_PORT:-20001}
STAGING_BASE_URL=https://staging.saraise.com
PRODUCTION_BASE_URL=https://saraise.com
API_PRODUCTION_URL=https://api.saraise.com

# Development URLs
DEV_FRONTEND_URL=http://localhost:${FRONTEND_HOST_PORT:-20000}
DEV_API_URL=http://localhost:${API_HOST_PORT:-20001}
DEV_MAILHOG_URL=http://localhost:${MAILHOG_UI_HOST_PORT:-20007}
DEV_VAULT_URL=http://localhost:${VAULT_HOST_PORT:-20008}

# Service URLs
POSTGRES_URL=postgresql://postgres:postgres@localhost:${POSTGRES_HOST_PORT:-20002}/saraise
REDIS_URL=redis://localhost:${REDIS_HOST_PORT:-20003}
MINIO_URL=http://localhost:${MINIO_API_HOST_PORT:-20004}
MINIO_CONSOLE_URL=http://localhost:${MINIO_CONSOLE_HOST_PORT:-20005}

# Repository URLs
REPO_URL=https://github.com/buildworksai/saraise.git
DOCKER_REGISTRY_URL=${DOCKER_REGISTRY:-docker.io/buildworksai}

