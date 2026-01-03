---
description: Ports, CORS, deployment, and DevOps configuration for SARAISE infrastructure
globs: **/*
alwaysApply: true
---

# 🌐 SARAISE Infrastructure Configuration (Ports, CORS, Deployment)

**Rule IDs**: SARAISE-09000 to SARAISE-09010, SARAISE-15001 to SARAISE-15006
**Consolidates**: `09-infrastructure-config.md`, `09-infrastructure-config.md`

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Control Plane & Runtime Plane: `docs/architecture/control-plane-and-runtime-plane-deep-spec.md`

---

## Ports & CORS Configuration

### SARAISE-09000 Central URL & Domain Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All URLs, domains, and port numbers are defined here. Other files MUST reference these variables, not hardcode URLs or ports.

See [URL & Domain Registry](docs/architecture/examples/config/url-domain-registry.sh) for complete configuration.

**Key Variables:** Base URLs (frontend, API, staging, production), Development URLs, Service URLs (PostgreSQL, Redis, MinIO), Repository URLs

### SARAISE-09001 Central Port Registry (SINGLE SOURCE OF TRUTH)

**⚠️ CRITICAL**: All port numbers are defined here. Other files MUST reference these variables, not hardcode ports.

See [Port Registry](docs/architecture/examples/config/port-registry.sh) for complete configuration.

**Key Port Mappings:**
- Frontend: 20000:15000
- API: 20001:30000
- PostgreSQL: 20002:5432
- Redis: 20003:6379
- MinIO: 20004:9000, 20005:9001
- MailHog: 20006:1025, 20007:8025
- Vault: 20008:8200
- Monitoring: 20009-20016

### SARAISE-09002 URL Construction Helpers

**Python Helper Functions:**
See [Python URL Helpers](docs/architecture/examples/helper-functions/python-url-helpers.py)

Functions: `get_frontend_url()`, `get_api_url()`, `get_database_url()`, `get_redis_url()`, `get_minio_url()`, `get_cors_origins()`

**TypeScript Helper Functions:**
See [TypeScript URL Helpers](docs/architecture/examples/helper-functions/typescript-url-helpers.ts)

Functions: `getApiUrl()`, `getFrontendUrl()`, `getEnvironmentUrls()`

### SARAISE-09003 CORS Origins
- Primary frontend: `http://localhost:${FRONTEND_HOST_PORT}`
- API service: `http://localhost:${API_HOST_PORT}`
- Development origins: Use `get_cors_origins()` helper function
- Canonical Repository: `https://github.com/buildworksai/saraise.git`

### SARAISE-09004 Port Configuration Reference

**How to Change Ports:**
1. Update environment variables in this file
2. All other files automatically use the new port values
3. No need to update Docker Compose, connection strings, or documentation

**Port Usage Context:**
- Docker Compose: Uses `${VARIABLE_NAME:-default}` syntax
- Connection Strings: Uses environment variables with fallbacks
- CORS Origins: Uses helper functions
- Health Checks: Uses environment variables

### SARAISE-09007 Environment-Aware Network Security

**Development Environment:**
- ALLOWED: HTTP for localhost development (127.0.0.1, ::1)
- ALLOWED: Basic CORS configuration for local development
- REQUIRED: Localhost-only access restrictions

**Staging Environment:**
- REQUIRED: HTTPS with self-signed or staging certificates
- REQUIRED: Standard CORS configuration
- REQUIRED: Basic security headers

**Production Environment:**
- REQUIRED: HTTPS only with valid certificates
- REQUIRED: Strict CORS configuration
- REQUIRED: Full security headers (HSTS, CSP, etc.)
- REQUIRED: WAF protection and rate limiting

See [Network Security Configuration](docs/architecture/examples/backend/core/network-security.py) for implementation.

### SARAISE-09008 Environment-Aware CORS Configuration

**Environment-Specific CORS:**
- Development: Localhost origins, wildcard subdomains allowed
- Staging: Staging-specific origins only
- Production: Production origins only, strict headers

See [CORS Configuration](docs/architecture/examples/backend/core/cors-config.py) for implementation.

### SARAISE-09009 Service Connection Patterns

See [Service Connection Patterns](docs/architecture/examples/backend/core/service-connections.py) for implementation.

**Key Functions:** Database, Redis, MinIO, Kong Gateway, Monitoring service connections

### SARAISE-09010 Environment-Aware Security Headers

**Environment-Specific Headers:**
- Development: Basic security headers, relaxed CSP
- Staging: Standard security headers, moderate CSP
- Production: Full security headers, strict CSP, HSTS

See [Security Headers Middleware](docs/architecture/examples/backend/core/security-headers.py) for implementation.

---

## Deployment & DevOps

**⚠️ PORT CONFIGURATION**: All port numbers are defined above.
**⚠️ TECH STACK CONFIGURATION**: All technology versions and Docker images are defined in `03-tech-stack.md`.

### SARAISE-15001 Development Environment Setup

**Local Development with Docker:**

See [Development Docker Compose](docs/architecture/examples/infrastructure/docker-compose.dev.yml).

**Key Services:** Backend API (hot reload), Frontend (hot reload), PostgreSQL, Redis, MinIO, MailHog, Vault

**Development Scripts:**

See [Development Setup Script](docs/architecture/examples/infrastructure/dev-setup.sh) for implementation.

**Features:** Prerequisites checking, Environment file setup, Service startup/health checks, Database migrations

### SARAISE-15002 Staging Environment Setup

See [Staging Docker Compose](docs/architecture/examples/infrastructure/docker-compose.staging.yml).

**Features:** Production-like environment, Restart policies, Environment-specific configuration

### SARAISE-15003 Production Environment Setup

See [Production Docker Compose](docs/architecture/examples/infrastructure/docker-compose.prod.yml).

**Features:** Production-optimized configuration, Prometheus monitoring, Restart policies, Secure environment variables

### SARAISE-15004 CI/CD Pipeline

See [CI/CD Pipeline](docs/architecture/examples/infrastructure/ci-cd.yml).

**Key Jobs:**
- Quality Gates (linting, testing, security scanning)
- Build and Test (Docker image building)
- Deploy to Staging (on develop branch)
- Deploy to Production (on main branch)

### SARAISE-15005 Monitoring and Observability

**Prometheus Configuration:**

See [Prometheus Configuration](docs/architecture/examples/infrastructure/prometheus.yml) for setup.

**Application Metrics:**

See [Application Metrics](docs/architecture/examples/backend/core/metrics.py) for implementation.

**Key Metrics:** HTTP request count/duration, Active database connections, Prometheus metrics endpoint

### SARAISE-15006 Backup and Recovery

See [Database Backup Script](docs/architecture/examples/infrastructure/backup-database.sh) for implementation.

**Features:** Automated database backups, Compression, Automatic cleanup (7-day retention)

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
