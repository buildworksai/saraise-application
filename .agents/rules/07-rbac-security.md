---
description: RBAC roles, permissions, step-up MFA, and testing requirements
globs: backend/src/**/*.py, backend/tests/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# 🔐 SARAISE RBAC Security (Roles, Step-Up, Testing)

**Rule IDs**: SARAISE-07001 to SARAISE-07010, SARAISE-07051 to SARAISE-07064
**Consolidates**: `07-rbac-security.md`, `07-rbac-security.md`, `07-rbac-security.md`

**Related Documentation:**
- Security Model: `docs/architecture/security-model.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`
- Module Framework: `docs/architecture/module-framework.md`

---

## RBAC Roles & Permissions

### SARAISE-07001 Authorization via Policy Engine (Authoritative)

**Policy Engine is the single source of truth for authorization (FROZEN ARCHITECTURE):**
- ALL authorization decisions evaluated by Policy Engine at request time
- Sessions contain **identity snapshot** (roles[], groups[], jit_grants[], policy_version) - NOT effective permissions
- Sessions DO NOT cache effective permissions (e.g., "finance.ledger:post") or authorization decisions
- Policy Engine evaluates: identity_snapshot + resource_attrs + context_attrs → allow/deny
- Policy Engine maps roles → permissions internally (cached inside Policy Engine, NOT in session)
- RBAC + ABAC evaluated at runtime for every request
- Implementation: See `docs/architecture/policy-engine-spec.md`

**Required platform roles (session.roles):**
- `platform_owner` (Super Admin) — full platform control, tenant provisioning, system configuration
- `platform_developer` — workflows/agents/data/jobs CRUD; settings R; integrations C/R/U (no D); deployment management
- `platform_operator` — tenant provisioning/support, jobs control (no destructive deletes), system monitoring
- `platform_auditor` — read-only across platform (logs/audit/config read), compliance reporting
- `platform_billing_manager` — platform billing CRUD, payment processing, subscription management

**Required tenant roles (session.tenant_roles):**
- `tenant_admin` — full control within tenant: users/roles/workflows/agents/data/settings/integrations/billing CRUD
- `tenant_developer` — workflows/agents/data/jobs CRUD; settings R; integrations C/R/U (no D); deployment management
- `tenant_operator` — ops: deploy/rollback/start/stop/execute; data R (ops-safe); monitoring/alerts access
- `tenant_billing_manager` — tenant billing CRUD, payment methods, usage reports, subscription changes
- `tenant_auditor` — tenant read-only access: logs/audit/compliance reports; no data modification
- `tenant_user` — workflow execution, agent interaction, data viewing (own scope), basic feature access
- `tenant_viewer` — read-only dashboard access, reports viewing, no execution permissions

**Authorization Enforcement:**
- All protected endpoints invoke Policy Engine for authorization checks
- Policy Engine evaluates permissions based on roles, ABAC conditions, SoD constraints
- Deny-by-default: no permission = deny
- Implementation: See `docs/architecture/policy-engine-spec.md`

**Tenant isolation:**
- All queries MUST include tenant_id filtering
- Policy Engine enforces row-level access based on ABAC context

### SARAISE-07007 Step-up & Audit Requirements
- **Step-up authentication**: Sensitive operations require re-authentication and privilege elevation (JIT)
- **Audit logging**: Admin/billing/data-impacting actions must be immutably audited
- Implementation: See `docs/architecture/security-model.md` (§ 6 JIT Privileges)

### SARAISE-07008 Frontend Integration
- Frontend queries backend API for authorization decisions
- Backend invokes Policy Engine for each authorization check
- UI renders based on authorization responses
- Never cache authorization state client-side

### SARAISE-07009 Testing Requirements
- Test Policy Engine integration for all protected endpoints
- Assert correct allow/deny decisions for different roles
- Test ABAC conditions when applicable
- Required: 100% coverage of protected endpoints

### SARAISE-07010 Authorization Capabilities

**DRBAC (Dynamic RBAC):**
- Roles defined per tenant with permissions
- Platform ships role templates
- Tenants can customize within guardrails
- Implementation: See `docs/architecture/security-model.md` (§ 3.2)

**ABAC (Attribute-Based Access Control):**
- Policy conditions on org_unit, site, project, cost_center, region, classification, time, device posture, risk score
- Evaluated at runtime by Policy Engine
- Implementation: See `docs/architecture/security-model.md` (§ 3.3), `docs/architecture/abac-attributes-architecture.md`

**Separation of Duties (SoD):**
- SoD rules define conflicting action sets
- Enforced at workflow transitions
- Violations block execution
- Implementation: See `docs/architecture/security-model.md` (§ 5), `docs/architecture/module-framework.md` (§ 4.4)

**Just-In-Time (JIT) Privileges:**
- Time-bound privilege grants
- Approval-gated
- Forced re-authentication required
- Implementation: See `docs/architecture/security-model.md` (§ 6)

---

## Authentication Security

### SARAISE-07051 Authentication Requirements

**Server-Managed Sessions:**
- Stateful sessions stored server-side
- HTTP-only, secure cookies
- Sessions establish identity only
- No JWT for interactive users

**Forced Re-Authentication:**
Required on privilege elevation:
- Role assignment changes
- JIT privilege grants
- Transition to SoD-sensitive actions

Implementation: See `docs/architecture/authentication-and-session-management-spec.md`, `docs/architecture/security-model.md` (§ 6.2)

### SARAISE-07052 Session Invalidation

**Required invalidation triggers:**
- Logout
- Role or policy changes
- JIT grant or expiry
- Suspicious activity
- Privilege elevation

Implementation: See `docs/architecture/security-model.md` (§ 2.3)

---

## Testing

### SARAISE-07061 Authorization Testing Requirements

**Required Tests:**
- Test Policy Engine authorization for all protected endpoints
- Test allow/deny for different roles and permissions
- Test ABAC condition evaluation
- Test SoD enforcement at workflow transitions
- Test tenant isolation (cross-tenant access denied)
- Required: 100% coverage of authorization checks

### SARAISE-07062 Authentication Testing

**Required Tests:**
- Test session creation and validation
- Test session invalidation on logout and privilege changes
- Test forced re-authentication on privilege elevation
- Test session expiry handling
- Test CSRF protection

---

## Related Documentation

- Security Model: `docs/architecture/security-model.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`
- Authentication: `docs/architecture/authentication-and-session-management-spec.md`
- ABAC: `docs/architecture/abac-attributes-architecture.md`
- Module Framework: `docs/architecture/module-framework.md`

---

**Audit**: Version 8.0.0; Updated 2026-01-03
