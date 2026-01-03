# ✅ APPROVED: Docker Image Registry
# Reference: docs/architecture/operational-runbooks.md § 0 (Infrastructure Components)

# CRITICAL: All Docker images must be from trusted registries
# Use specific version tags - never 'latest' in production
# See docs/architecture/operational-runbooks.md § 0

# Core Services
POSTGRES_IMAGE=postgres:${POSTGRES_VERSION}-alpine
REDIS_IMAGE=redis:${REDIS_VERSION}-alpine
VAULT_IMAGE=hashicorp/vault:1.15.2
MINIO_IMAGE=minio/minio:latest
MAILHOG_IMAGE=mailhog/mailhog:latest
PROMETHEUS_IMAGE=prom/prometheus:latest
KONG_IMAGE=kong/kong:latest
LOKI_IMAGE=grafana/loki:2.9.0
GRAFANA_IMAGE=grafana/grafana:10.2.0
CELERY_IMAGE=celery:${CELERY_VERSION}-alpine
FLOWER_IMAGE=mher/flower:${FLOWER_VERSION}

