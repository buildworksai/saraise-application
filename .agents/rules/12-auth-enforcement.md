---
description: Route protection, RBAC enforcement, and CRUD permission matrices
globs: backend/src/api/routes/**/*.py
alwaysApply: true
---

# SARAISE-07031 Authentication Enforcement

**Related Documentation:**
- Policy Engine: `docs/architecture/policy-engine-spec.md`
- Security Model: `docs/architecture/security-model.md`
- Application Architecture: `docs/architecture/application-architecture.md`

## SARAISE-07031 Deny-by-Default Authorization

**REQUIRED:** All protected routes MUST declare an explicit RBAC enforcer dependency

See [Deny-by-Default Authorization](docs/architecture/examples/backend/services/deny-by-default-authorization.py) for examples.

**Key Requirements:**
- ✅ CORRECT: Explicit role enforcement via Policy Engine in DRF ViewSet methods
- ✅ CORRECT: Use `get_current_user_from_session(request)` + `PolicyEngine().evaluate()`
- ❌ FORBIDDEN: Routes without Policy Engine authorization check
- ❌ FORBIDDEN: FastAPI `Depends()` pattern (use DRF ViewSet instead)

## SARAISE-07032 Platform Resource Permissions

**Platform roles** (`session.roles`):

| Resource | Create | Read | Update | Delete |
|----|-----|---|-----|-----|
| tenants | platform_owner | platform_owner, platform_operator, platform_auditor | platform_owner | platform_owner |
| global_settings | platform_owner | platform_owner, platform_operator, platform_auditor | platform_owner | platform_owner |
| integrations | platform_owner | platform_owner, platform_operator, platform_auditor | platform_owner | platform_owner |
| billing | platform_billing_manager | platform_billing_manager, platform_auditor | platform_billing_manager | platform_billing_manager |
| platform_logs | - | platform_auditor | - | - |
| log_retention | platform_owner | platform_auditor | platform_owner | platform_owner |
| system_jobs | platform_owner, platform_operator | platform_owner, platform_operator | platform_owner, platform_operator | platform_owner |

**Implementation:**

See [Platform Resource Permissions](docs/architecture/examples/backend/services/platform-resource-permissions.py) for complete examples.

**Key Routes:**
- Tenants: `RequirePlatformOwner` (create), `RequirePlatformOperator` (list)
- Billing: `RequirePlatformBillingManager`
- Audit logs: `RequirePlatformAuditor` (read-only)

## SARAISE-07033 Tenant Resource Permissions

**Tenant roles** (`session.tenant_roles`):

| Resource | tenant_admin | tenant_developer | tenant_operator | tenant_billing_manager | tenant_auditor | tenant_user | tenant_viewer |
|----|-----|---|-----|----|----|----|---|
| users | CRUD | R | R | R | R | - | - |
| roles | CRUD | R | R | R | R | - | - |
| workflows | CRUD | CRUD | Deploy/Execute | R | R | Execute | R |
| agents | CRUD | CRUD | Start/Stop/Execute | R | R | Interact | R |
| data | CRUD | CRUD | R (ops-safe) | R | R | R (own) | R |
| tenant_settings | CRUD | R | R | R | R | - | R |
| integrations | CRUD | CRU (no D) | R | R | R | - | R |
| tenant_billing | CRUD | R | R | CRUD | R | - | R |
| logs | CRUD | R | R | R | R | - | R |
| jobs | CRUD | CRUD | Start/Stop | R | R | - | R |

**Implementation:**

See [Tenant Resource Permissions](docs/architecture/examples/backend/services/tenant-resource-permissions.py) for complete examples.

**Key Points (FROZEN ARCHITECTURE - Row-Level Multitenancy):**
- Tenant isolation via mandatory tenant_id filtering in all queries
- ALL tenant-scoped tables MUST have tenant_id column
- Services MUST filter by tenant_id from authenticated user's session
- Row-level security enforces data separation (shared schema, not schema-per-tenant)

## SARAISE-07034 Row-Level Tenant Isolation (FROZEN ARCHITECTURE)

**CRITICAL:** Tenant isolation via mandatory tenant_id filtering. Routes do NOT include tenant_id in paths (it comes from session).

See [Row-Level Tenant Isolation](docs/architecture/examples/backend/services/schema-tenant-isolation.py) for examples.

**Key Requirements (FROZEN ARCHITECTURE - Row-Level Multitenancy):**
- ✅ CORRECT: Mandatory tenant_id filtering in ALL queries (filter by session.tenant_id)
- ✅ CORRECT: Tenant isolation enforced at service layer via tenant_id filtering
- ✅ CORRECT: Shared schema with row-level security (ALL tenant tables have tenant_id column)
- ❌ FORBIDDEN: Omitting tenant_id filtering (data leakage risk)
- ❌ FORBIDDEN: Including tenant_id in URL path (comes from authenticated session, not URL)

## SARAISE-07035 Role Enforcer Dependencies

**Available Dependencies:** ([backend/src/core/auth_decorators.py](backend/src/core/auth_decorators.py))

**Platform Enforcers:**
- `RequirePlatformOwner` - Full platform control (inherits all platform roles)
- `RequirePlatformDeveloper` - Platform development access
- `RequirePlatformOperator` - Platform operations (inherits `platform_auditor`)
- `RequirePlatformAuditor` - Platform audit/compliance
- `RequirePlatformBillingManager` - Platform billing management

**Tenant Enforcers:**
- `RequireTenantAdmin` - Full tenant control (inherits all tenant roles)
- `RequireTenantDeveloper` - Tenant development (inherits `tenant_user`, `tenant_viewer`)
- `RequireTenantOperator` - Tenant operations (inherits `tenant_user`, `tenant_viewer`)
- `RequireTenantBillingManager` - Tenant billing (inherits `tenant_viewer`)
- `RequireTenantAuditor` - Tenant audit (inherits `tenant_viewer`)
- `RequireTenantUser` - Standard tenant access (inherits `tenant_viewer`)
- `RequireTenantViewer` - Read-only tenant access

**Role Hierarchy Support**: ✅ **IMPLEMENTED**

All role enforcers use **effective roles** (includes inherited roles from hierarchy):
- Enforcers call `has_effective_platform_role()` and `has_effective_tenant_role()` from ```backend/src/core/role_hierarchy.py```
- Senior roles automatically have permissions of junior roles (e.g., `platform_owner` can access `platform_auditor` endpoints)
- No changes required to route definitions (backward compatible)

**Code References**:
- Role Enforcers: ```backend/src/core/auth_decorators.py``` - uses `has_effective_platform_role()` and `has_effective_tenant_role()`
- Role Hierarchy: ```backend/src/core/role_hierarchy.py``` - effective role computation

**Usage:**

See [Role Enforcer Usage Examples](docs/architecture/examples/backend/services/role-enforcer-usage.py) for complete examples.

## SARAISE-07036 Sensitive Operations Protection

**REQUIRED:** High-risk operations require step-up MFA (see [07-rbac-security.md](07-rbac-security.md))

**Sensitive Operations:**
- Delete tenant
- Purge data
- Rotate encryption keys
- Role escalations (user → admin)
- Financial transactions (charge/refund)
- Export sensitive data

See [Sensitive Operations Protection](docs/architecture/examples/backend/services/sensitive-operations-protection.py).

**Key Requirements:**
- Use `RequireStepUpAuth` dependency for high-risk operations
- Double verification for destructive actions
- Platform-level operations (not tenant-scoped routes)

## SARAISE-07037 SoD Validation in Role Assignment

**✅ IMPLEMENTED**: Separation of Duties (SoD) validation is enforced during role assignment to prevent conflicting role assignments.

**Implementation**:
- SoD validation is performed in `assign_role()` method of ```backend/src/services/auth_service.py```
- Uses `validate_sod_assignment()` from ```backend/src/core/sod_rules.py```
- Prevents assignment of conflicting roles (e.g., `invoice_creator` + `invoice_approver`)

**Code References**:
- Role Assignment: ```238:252:backend/src/services/auth_service.py``` - `assign_role()` method with SoD validation
- SoD Rules: ```backend/src/core/sod_rules.py``` - `validate_sod_assignment()` function
- SoD Rules Definition: ```16:67:backend/src/core/sod_rules.py``` - `STATIC_SOD_RULES`

**Example**:

See [SoD Validation in Role Assignment](docs/architecture/examples/backend/services/sod-validation-role-assignment.py).

**Key Points:**
- SoD validation is automatic in `assign_role()`
- Raises `AuthorizationError` if role conflicts with existing roles
- `validate_sod=True` by default

**SoD Rules Enforced**:
- Financial workflow: `invoice_creator` ⊥ `invoice_approver` ⊥ `payment_processor`
- Procurement workflow: `purchase_requester` ⊥ `purchase_approver` ⊥ `vendor_manager`
- Expense workflow: `expense_creator` ⊥ `expense_approver` ⊥ `payment_processor`
- Accounting controls: `journal_entry_creator` ⊥ `journal_entry_approver` ⊥ `account_reconciler`

**Compliance**: SOX, ISO 27001, NIST Constrained RBAC

## SARAISE-07038 Audit Logging Requirement

**REQUIRED:** Admin/billing/data-impacting operations MUST emit immutable audit entries (see `11-audit-logging.md`)

See [Audit Logging Requirement](docs/architecture/examples/backend/services/audit-logging-requirement.py).

**Required Steps:**
1. Perform role update (SoD validation is automatic in `assign_role()`)
2. Explicit tenant_id filtering provides tenant isolation (Row-Level Multitenancy)
3. **REQUIRED:** Audit log all role changes

## SARAISE-07039 CORS Configuration for Authentication

**REQUIRED:** CORS must allow session cookies (see `docs/architecture/examples/backend/core/cors-auth-config.py`)

See [CORS Auth Configuration](docs/architecture/examples/backend/core/cors-auth-config.py).

## SARAISE-07040 Testing Requirements

**REQUIRED:** Test route protection (see `07-rbac-security.md` for testing requirements)

See [Auth Enforcement Tests](docs/architecture/examples/backend/tests/test-auth-enforcement.py) for complete test examples.

## SARAISE-07041 Forbidden Patterns

See [Forbidden Auth Patterns](docs/architecture/examples/backend/services/forbidden-auth-patterns.py) for complete examples of forbidden and correct patterns.

## SARAISE-07042 Implemented Authorization Enhancements

**✅ Role Hierarchy Support**: Role enforcers use effective roles (includes inherited roles). See [Role Hierarchy Example](docs/architecture/examples/backend/services/role-hierarchy-example.py). Code: ```backend/src/core/auth_decorators.py```, ```backend/src/core/role_hierarchy.py```. Reference: ADR-0016.

**✅ SoD Validation**: Enforced during role assignment. Prevents conflicting roles (e.g., invoice_creator ⊥ invoice_approver). Code: ```16:67:backend/src/core/sod_rules.py```, ```238:252:backend/src/services/auth_service.py```. Reference: ADR-0016.

## SARAISE-07043 Future Authorization Enhancements (Planned)

**⚠️ CRITICAL**: The following are documented but NOT YET IMPLEMENTED.

**Pending Q2 2025**: Resource-Level Permissions (Row-Level Security). See [Future Enhancements Examples](docs/architecture/examples/backend/services/future-enhancements-examples.py).

**Pending Q3-Q4 2025**: JIT Access, Dynamic Role Activation, Delegated Administration, MFA, Time-Based Access Control, Role Analytics. Reference: `docs/architecture/security-model.md` (§ 6 JIT Privileges), `docs/architecture/implementation-sequencing-and-build-order.md`.

## Related Documentation

- Session Auth: See `10-session-auth.md` (SARAISE-07011-07030)
- RBAC Roles: See `07-rbac-security.md` (SARAISE-07001-07010)
- Step-Up Auth: See `07-rbac-security.md` (SARAISE-07051-07060)
- RBAC Tests: See `07-rbac-security.md` (SARAISE-14001+)
