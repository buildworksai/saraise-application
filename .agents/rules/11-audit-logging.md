---
description: Immutable audit logging for admin/billing/data operations (complete implementation)
globs: backend/src/**/*.py
alwaysApply: true
---

# SARAISE-10001 Audit Logging (Immutable)

**Related Documentation:**
- Security Model: `docs/architecture/security-model.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`

## SARAISE-10001 Required Audit Fields

**Minimum fields for all audit entries:**
- `actor_sub` - User ID performing action
- `actor_email` - User email
- `tenant_id` - Tenant context (null for platform operations)
- `resource` - Resource type (users, agents, workflows, billing, etc.)
- `action` - Operation (CREATE, READ, UPDATE, DELETE, EXECUTE)
- `result` - Outcome (success, error)
- `timestamp` - When action occurred
- `ip_address` - Client IP
- `metadata` - Additional context (JSON)

## SARAISE-10002 Database Schema

### Audit Log Model

See [Audit Log Model](docs/architecture/examples/backend/services/audit-log-model.py).

**Key Fields:**
- `actor_sub`, `actor_email`, `tenant_id`, `resource`, `action`, `result`
- `error_message`, `metadata`, `ip_address`, `user_agent`
- Indexes: `idx_audit_tenant_resource`, `idx_audit_actor_timestamp`

**Migration Note:** Create append-only table (no UPDATE/DELETE permissions)

## SARAISE-10003 Audit Service

### Implementation

See [Audit Service Implementation](docs/architecture/examples/backend/services/audit-service.py).

**Key Methods:**
- `log_event()` - Log immutable audit event with secret redaction
- `query_logs()` - Query audit logs with filtering (explicit tenant_id filtering provides tenant isolation)
- `_redact_secrets()` - Redact sensitive fields from metadata

## SARAISE-10004 Route Integration

### Usage Example

See [Audit Route Integration](docs/architecture/examples/backend/services/audit-route-integration.py).

**Key Requirements:**
- Audit both success and failure cases
- Include request context (IP address, user agent)
- Redact sensitive fields automatically

## SARAISE-10005 Auditor Endpoints

### Query Audit Logs

See [Auditor Endpoints](docs/architecture/examples/backend/services/auditor-endpoints.py).

**Key Endpoints:**
- Platform auditor: Query all audit logs
- Tenant auditor: Query tenant audit logs (explicit tenant_id filtering provides tenant isolation)

## SARAISE-10006 Testing Requirements

See [Audit Logging Tests](docs/architecture/examples/backend/tests/audit-logging-tests.py) for complete test examples.

**Required Tests:**
- Audit log created on success
- Audit log created on failure with error message

## SARAISE-10007 Future Audit Logging Enhancements (Planned)

**⚠️ CRITICAL**: The following audit logging enhancements are documented but NOT YET IMPLEMENTED. Current audit logs track standard RBAC events only.

### SoD (Separation of Duties) Audit Events - 🔴 Pending Q1 2025

**Status**: NOT IMPLEMENTED - No SoD-specific audit events currently logged

**Planned Enhancement**: Audit all SoD validation attempts and violations

**New Audit Events**:
```python
# Future: Log SoD violation attempts
await audit_service.log_event(
    actor_sub=admin_user.id,
    actor_email=admin_user.email,
    tenant_id=tenant_id,
    resource="user_roles",
    action="sod_violation",
    result="blocked",
    metadata={
        "target_user_id": user_id,
        "attempted_role": "invoice_approver",
        "conflicting_role": "invoice_creator",
        "sod_rule_id": "FIN-001",
        "sod_rule_name": "Invoice Creation vs. Approval",
    }
)

# Future: Log SoD compliance reports
await audit_service.log_event(
    actor_sub=auditor_user.id,
    actor_email=auditor_user.email,
    tenant_id=tenant_id,
    resource="sod_compliance",
    action="report_generated",
    result="success",
    metadata={
        "total_users": 150,
        "violations_found": 3,
        "report_format": "pdf",
    }
)
```

**Compliance**: SOX, ISO 27001 require audit trail of SoD enforcement

**Reference**: See `12-auth-enforcement.md` for SoD validation implementation details

### Role Hierarchy Audit Events - 🔴 Pending Q1 2025

**Status**: NOT IMPLEMENTED - Audit logs track direct role assignments only

**Planned Enhancement**: Log effective (inherited) roles in audit events

**Enhanced Audit Metadata**:
```python
# Future: Include both direct and effective roles
await audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=tenant_id,
    resource="workflow_execution",
    action="execute",
    result="success",
    metadata={
        "workflow_id": workflow_id,
        "direct_roles": ["tenant_admin"],  # What was assigned
        "effective_roles": ["tenant_admin", "tenant_developer", "tenant_user"],  # What was checked
        "permission_checked": "tenant_user",  # Required role
        "granted_via": "inheritance",  # How permission was granted
    }
)
```

**Benefit**: Auditors can understand how permissions were granted (direct vs. inherited)

**Reference**: See `12-auth-enforcement.md` for role hierarchy implementation details

### Resource-Level Access Audit - 🔴 Pending Q2 2025

**Status**: NOT IMPLEMENTED - Audit logs track route-level access only

**Planned Enhancement**: Log resource-level (row-level) access decisions

**New Audit Detail**:
```python
# Future: Log fine-grained resource access
await audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=tenant_id,
    resource="workflow",
    action="READ",
    result="success",
    metadata={
        "resource_id": workflow_id,
        "resource_owner": "other-user-id",
        "access_reason": "shared_with_user",  # Why access was granted
        "permission_level": "read_only",
    }
)

# Future: Log resource access denials
await audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=tenant_id,
    resource="workflow",
    action="READ",
    result="denied",
    metadata={
        "resource_id": workflow_id,
        "resource_owner": "other-user-id",
        "denial_reason": "not_owner_or_shared",
    }
)
```

**Reference**: `docs/architecture/security-model.md` (§ 8 Audit & Event Logging)

### JIT Access Audit Events - 🔴 Pending Q3 2025

**Status**: NOT IMPLEMENTED - No temporary privilege elevation tracking

**Planned Enhancement**: Audit temporary privilege grants and expirations

**New Audit Events**:
```python
# Future: Log JIT access requests
await audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=tenant_id,
    resource="jit_access",
    action="request",
    result="approved",
    metadata={
        "requested_role": "tenant_admin",
        "duration_hours": 2,
        "justification": "Emergency production fix",
        "approver_id": manager_user.id,
        "expires_at": "2025-01-01T12:00:00Z",
    }
)

# Future: Log JIT access expirations
await audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=tenant_id,
    resource="jit_access",
    action="expired",
    result="success",
    metadata={
        "expired_role": "tenant_admin",
        "granted_at": "2025-01-01T10:00:00Z",
        "expired_at": "2025-01-01T12:00:00Z",
        "actions_taken": 15,  # Number of privileged actions during elevation
    }
)
```

**Compliance**: Critical for SOX compliance - time-bounded privilege elevation must be audited

**Reference**: `docs/architecture/security-model.md` (§ 8 Audit & Event Logging)

### ABAC Policy Evaluation Audit - 🔴 Pending Q3 2025

**Status**: NOT IMPLEMENTED - No ABAC policy logging

**Planned Enhancement**: Log ABAC policy evaluation decisions

**New Audit Events**:
```python
# Future: Log ABAC policy denials
await audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=tenant_id,
    resource="sensitive_data",
    action="READ",
    result="denied",
    metadata={
        "rbac_check": "passed",  # Role was correct
        "abac_check": "failed",  # Context failed
        "failed_policies": [
            {"policy": "time_of_day", "required": "09:00-17:00", "actual": "22:30"},
            {"policy": "ip_allowlist", "required": "office_network", "actual": "home_network"},
        ]
    }
)
```

**Reference**: `docs/architecture/security-model.md` (§ 8 Audit & Event Logging)

### Additional Planned Enhancements - 🔴 Pending Q2-Q4 2025

The following audit logging features are documented but not yet implemented:
- **Delegated Administration Audit** - Track tenant admin actions on their own users (Q2 2025)
- **Permission Discovery Audit** - Log permission API queries for compliance (Q2 2025)
- **Dynamic Role Activation Audit** - Track which roles users activate in each session (Q3 2025)
- **Audit Log Retention Policies** - Automated archival and compliance-driven retention (Q3 2025)
- **Real-Time Audit Streaming** - Stream audit events to SIEM systems (Q4 2025)
- **Audit Log Analytics Dashboard** - Compliance dashboards for auditors (Q4 2025)

**Reference**: `docs/architecture/implementation-sequencing-and-build-order.md`

## Related Documentation

- Session Auth: See `10-session-auth.md` (SARAISE-07011-07030)
- Auth Enforcement: See `12-auth-enforcement.md` (SARAISE-07031-07050)
- RBAC Tests: See `07-rbac-security.md` (SARAISE-14001+)
