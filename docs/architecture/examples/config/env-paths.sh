# ✅ APPROVED: Environment Variables for File Paths & Directories
# Reference: docs/architecture/operational-runbooks.md § 1 (File Structure)

# CRITICAL: All file paths must be environment-configured
# No hardcoded paths in code
# See docs/architecture/operational-runbooks.md § 1

# Project Structure
PROJECT_ROOT=.
BACKEND_DIR=backend
FRONTEND_DIR=frontend
SCRIPTS_DIR=scripts
DOCS_DIR=docs
RULES_DIR=.cursor/rules

# Backend Paths
BACKEND_SRC_DIR=backend/src
BACKEND_TESTS_DIR=backend/tests
BACKEND_LOGS_DIR=backend/logs
BACKEND_UPLOADS_DIR=backend/uploads
BACKEND_STATIC_DIR=backend/static

# Frontend Paths
FRONTEND_SRC_DIR=frontend/src
FRONTEND_PUBLIC_DIR=frontend/public
FRONTEND_DIST_DIR=frontend/dist
FRONTEND_BUILD_DIR=frontend/build

# Docker Paths
DOCKER_COMPOSE_FILE=docker-compose.yml
DOCKERFILE_BACKEND=backend/Dockerfile
DOCKERFILE_FRONTEND=frontend/Dockerfile
DOCKER_VOLUME_BACKEND=./backend:/app
DOCKER_VOLUME_FRONTEND=./frontend:/app

# Database Paths
DB_DATA_DIR=./data/postgres
DB_BACKUP_DIR=./backups/postgres
DB_MIGRATIONS_DIR=backend/src/modules/*/migrations

# Redis Paths
REDIS_DATA_DIR=./data/redis
REDIS_BACKUP_DIR=./backups/redis

# MinIO Paths
MINIO_DATA_DIR=./data/minio
MINIO_CONFIG_DIR=./config/minio

# Vault Paths
VAULT_DATA_DIR=./data/vault
VAULT_CONFIG_DIR=./config/vault

# Logs & Monitoring
LOGS_DIR=./logs
MONITORING_DIR=./monitoring
PROMETHEUS_CONFIG=./monitoring/prometheus.yml
GRAFANA_CONFIG=./monitoring/grafana/dashboards

# Environment Files
ENV_FILE=.env
ENV_DEV_FILE=.env.development
ENV_STAGING_FILE=.env.staging
ENV_PROD_FILE=.env.production
ENV_LOCAL_FILE=.env.local

