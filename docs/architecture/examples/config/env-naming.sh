# ✅ APPROVED: Naming Standards
# Reference: docs/architecture/application-architecture.md § 1 (Naming Conventions)

# CRITICAL: All names must follow consistent naming standards
# See docs/architecture/application-architecture.md § 1

# Product & Company Names
COMPANY_NAME="SARAISE"
PRODUCT_NAME="SARAISE"
FULL_PRODUCT_NAME="SARAISE - Secure and Reliable AI Symphony ERP"
SHORT_NAME="SARAISE"

# Database Names
DATABASE_NAME="saraise"
DATABASE_DEV_NAME="saraise_dev"
DATABASE_STAGING_NAME="saraise_staging"
DATABASE_PROD_NAME="saraise_prod"

# Container Names
CONTAINER_FRONTEND="ui"
CONTAINER_BACKEND="api"
CONTAINER_DATABASE="db"
CONTAINER_REDIS="redis"
CONTAINER_MINIO="minio"
CONTAINER_VAULT="vault"
CONTAINER_MAILHOG="mailhog"

# Network Names
NETWORK_DEV="saraise-dev"
NETWORK_STAGING="saraise-staging"
NETWORK_PROD="saraise-prod"

# Volume Names
VOLUME_POSTGRES_DATA="saraise-postgres-data"
VOLUME_REDIS_DATA="saraise-redis-data"
VOLUME_MINIO_DATA="saraise-minio-data"
VOLUME_VAULT_DATA="saraise-vault-data"

# Service Names
SERVICE_FRONTEND="frontend"
SERVICE_BACKEND="backend"
SERVICE_DATABASE="database"
SERVICE_REDIS="redis"
SERVICE_MINIO="minio"
SERVICE_VAULT="vault"
SERVICE_MAILHOG="mailhog"

# Environment Names
ENV_DEVELOPMENT="development"
ENV_STAGING="staging"
ENV_PRODUCTION="production"
ENV_TESTING="testing"

# File Naming Conventions
ENV_FILE_PREFIX=".env"
DOCKER_COMPOSE_PREFIX="docker-compose"
DOCKERFILE_NAME="Dockerfile"
README_NAME="README.md"
GITIGNORE_NAME=".gitignore"
DOCKERIGNORE_NAME=".dockerignore"

