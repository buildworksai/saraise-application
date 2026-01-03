---
description: Platform & Tenant Management
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# Platform & Tenant Management

**Rule IDs**: SARAISE-32001 to SARAISE-32010, SARAISE-33001 to SARAISE-33010
**Consolidates**: `21-platform-tenant.md`, `21-platform-tenant.md`

---


# 🏛️ SARAISE Platform Management

**⚠️ CRITICAL**: All platform management operations MUST follow these patterns for consistency, security, and auditability.

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`

## SARAISE-32001 Platform Management Overview

### Core Principles
- **Platform Isolation**: Platform operations are separate from tenant operations
- **Platform Roles**: Only platform roles can perform platform operations
- **Audit Logging**: All platform operations must be audited
- **Multi-Tenant Support**: Platform manages multiple tenants

## SARAISE-32002 Platform Configuration

### Platform Settings

See [Platform Settings Model](docs/architecture/examples/backend/models/platform-settings-model.py).

### Platform Configuration Service

See [Platform Configuration Service](docs/architecture/examples/backend/services/platform-config-service.py).

**Key Methods:**
- `get_setting()` - Get platform setting by key
- `set_setting()` - Set platform setting
- `get_all_settings()` - Get all platform settings

## SARAISE-32003 Platform Routes

### Platform Management Routes

See [Platform Routes](docs/architecture/examples/backend/services/platform-routes.py).

**Key Endpoints:**
- `GET /settings` - Get platform settings (RequirePlatformOwner)
- `POST /settings` - Update platform settings (RequirePlatformOwner)

## SARAISE-32004 Platform Health Monitoring

### Platform Health Checks

See [Platform Health Service](docs/architecture/examples/backend/services/platform-health-service.py).

**Key Methods:**
- `get_platform_health()` - Get platform health status with service checks and metrics
- Service health checks for database and Redis
- Platform metrics (tenant count, user count, active sessions)

## SARAISE-32005 Platform Maintenance

### Maintenance Operations

See [Platform Maintenance Service](docs/architecture/examples/backend/services/platform-maintenance-service.py).

**Key Methods:**
- `run_maintenance_task()` - Run platform maintenance task
- `cleanup_old_sessions()` - Clean up old sessions from Redis
- `cleanup_old_audit_logs()` - Archive old audit logs

## SARAISE-32006 Platform Security

### Security Management

See [Platform Security Service](docs/architecture/examples/backend/services/platform-security-service.py).

**Key Methods:**
- `get_security_status()` - Get platform security status
- Vulnerability and misconfiguration checks

## SARAISE-32007 Platform Backup and Recovery

### Backup Management

See [Platform Backup Service](docs/architecture/examples/backend/services/platform-backup-service.py).

**Key Methods:**
- `create_backup()` - Create platform backup (full, database, redis, storage)
- `restore_backup()` - Restore platform from backup

## SARAISE-32008 Platform Analytics

### Platform Analytics

See [Platform Analytics Service](docs/architecture/examples/backend/services/platform-analytics-service.py).

**Key Methods:**
- `get_platform_analytics()` - Get platform analytics with tenant, user, usage, and revenue metrics

## SARAISE-32009 Platform API Endpoints

### Platform API Routes

See [Platform API Routes](docs/architecture/examples/backend/services/platform-api-routes.py).

**Key Endpoints:**
- `GET /health` - Get platform health (RequirePlatformOperator)
- `GET /analytics` - Get platform analytics (RequirePlatformOwner)
- `POST /backup` - Create platform backup (RequirePlatformOwner)

## SARAISE-32010 Platform Testing

### Platform Test Patterns

See [Platform Tests](docs/architecture/examples/backend/tests/test_platform.py) for complete test examples.

**Required Tests:**
- Platform settings management
- Platform health checks

---

**Next Steps**: Use these patterns to implement platform management. Ensure all platform operations are properly secured, audited, and monitored.

---


# 🏢 SARAISE Tenant Management

**⚠️ CRITICAL**: All tenant management operations MUST follow these patterns for tenant isolation, security, and scalability.

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Application Architecture: `docs/architecture/application-architecture.md`

## SARAISE-33001 Tenant Management Overview

### Core Principles (FROZEN ARCHITECTURE - DO NOT DEVIATE)
- **Row-Level Multitenancy (Shared Schema)**: ALL tenants share the same database schema. **ALL tenant-scoped tables MUST have a `tenant_id` column**.
- **Tenant Isolation**: Isolation enforced by mandatory `tenant_id` filtering in all queries and service layers.
- **No Schema-per-Tenant**: Tenants do NOT have separate schemas. Shared schema with row-level security.
- **Tenant Lifecycle**: Clear lifecycle: creation → activation → suspension → deletion
- **User Quotas**: User limits based on subscription tier
- **Rate Limiting**: API rate limits based on subscription tier

**CRITICAL FROZEN RULE**: ALL business models MUST include `tenant_id` column. No exceptions. Schema is shared across all tenants.

## SARAISE-33002 Tenant Model

### Tenant Definition

See [Tenant Model](docs/architecture/examples/backend/models/tenant-model.py).

**Key Features (FROZEN ARCHITECTURE):**
- Platform-level registry model
- Row-level multitenancy - shared schema with `tenant_id` scoping
- Subscription and quota tracking
- **NO schema_name** - all tenants share same schema

## SARAISE-33003 Tenant Service

### Tenant Management Service

See [Tenant Service](docs/architecture/examples/backend/services/tenant-service.py).

**Key Methods:**
- `create_tenant()` - Create new tenant with subscription
- `get_tenant()` - Get tenant by ID (platform-level lookup)
- `update_tenant()` - Update tenant properties
- `suspend_tenant()` - Suspend tenant and invalidate sessions
- `activate_tenant()` - Activate tenant
- `delete_tenant()` - Delete tenant (soft/hard delete)

## SARAISE-33004 User Quota Management

### User Quota Service

See [User Quota Service](docs/architecture/examples/backend/services/user-quota-service.py).

**Key Methods:**
- `check_user_quota()` - Check if tenant can add more users
- `increment_user_count()` - Increment tenant user count
- `decrement_user_count()` - Decrement tenant user count
- `update_user_quota()` - Update tenant user quota

## SARAISE-33005 Tenant Routes

### Tenant Management Routes

See [Tenant Routes](docs/architecture/examples/backend/services/tenant-routes.py).

**Key Endpoints:**
- `POST /tenants` - Create tenant (RequirePlatformOwner)
- `GET /tenants/{tenant_id}` - Get tenant (RequireTenantAdmin)
- `PATCH /tenants/{tenant_id}/quota` - Update user quota (RequirePlatformOwner)

## SARAISE-33006 Tenant Isolation Enforcement

### Tenant Isolation Service

See [Tenant Isolation Service](docs/architecture/examples/backend/services/tenant-isolation-service.py).

**Key Features (FROZEN ARCHITECTURE):**
- Platform-level tenant validation
- Mandatory `tenant_id` filtering in ALL queries
- Automatic row-level isolation via service layer enforcement
- **NO schema-per-tenant** - shared schema with `tenant_id` scoping

## SARAISE-33007 Tenant User Management

### Tenant User Service

See [Tenant User Service](docs/architecture/examples/backend/services/tenant-user-service.py).

**Key Methods:**
- `create_tenant_user()` - Create user with quota check
- `get_tenant_user()` - Get user (explicit tenant_id filtering provides isolation)
- `delete_tenant_user()` - Delete user with tenant validation

## SARAISE-33008 Tenant Subscription Management

### Tenant Subscription Service

See [Tenant Subscription Service](docs/architecture/examples/backend/services/tenant-subscription-service.py).

**Key Methods:**
- `update_tenant_subscription()` - Update tenant subscription and quota

## SARAISE-33009 Tenant Analytics

### Tenant Analytics Service

See [Tenant Analytics Service](docs/architecture/examples/backend/services/tenant-analytics-service.py).

**Key Methods:**
- `get_tenant_analytics()` - Get tenant analytics with user, usage, and activity metrics

## SARAISE-33010 Tenant Testing

### Tenant Test Patterns

See [Tenant Testing Examples](docs/architecture/examples/backend/tests/test_tenant.py) for complete test examples.

**Required Tests:**
- Tenant creation
- Tenant isolation via `tenant_id` filtering
- Tenant user isolation via row-level security
- Mandatory `tenant_id` enforcement in all queries


---

**Next Steps**: Use these patterns to implement tenant management. Ensure all tenant operations maintain proper isolation, enforce quotas, and are properly audited.

---


**Audit**: Version 7.0.0; Consolidated 2025-12-23
