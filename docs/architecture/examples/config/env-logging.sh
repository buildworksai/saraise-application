# ✅ APPROVED: Environment Variables for Logging & Monitoring
# Reference: docs/architecture/security-model.md § 4.2 (Audit Logging)
#            docs/architecture/operational-runbooks.md § 4.1 (Health Monitoring)

# CRITICAL: All authorization decisions must be logged for compliance
# See docs/architecture/security-model.md § 4.2

# Logging Configuration
LOG_LEVEL_DEVELOPMENT=DEBUG
LOG_LEVEL_STAGING=INFO
LOG_LEVEL_PRODUCTION=WARN
LOG_FORMAT=json
LOG_OUTPUT=console

# Monitoring & Observability
PROMETHEUS_ENABLED=true
PROMETHEUS_PORT=19090
GRAFANA_ENABLED=true
GRAFANA_PORT=13000
JAEGER_ENABLED=false
JAEGER_ENDPOINT=http://localhost:14268/api/traces

# Health Check Configuration
HEALTH_CHECK_INTERVAL=60
HEALTH_CHECK_TIMEOUT=30
HEALTH_CHECK_RETRIES=3

# Alerting Configuration
ALERT_MANAGER_ENABLED=true
ALERT_MANAGER_PORT=19093
SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
EMAIL_ALERTS_ENABLED=true
EMAIL_FROM=noreply@saraise.com

# Metrics Configuration
METRICS_ENABLED=true
METRICS_PORT=19187
CUSTOM_METRICS_ENABLED=true
BUSINESS_METRICS_ENABLED=true

