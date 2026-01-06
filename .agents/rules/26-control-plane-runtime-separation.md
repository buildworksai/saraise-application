---
description: Control Plane / Runtime Plane Separation (NON-NEGOTIABLE)
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# Control Plane / Runtime Plane Separation

**Rule ID**: SARAISE-26001  
**Severity**: CRITICAL — Architectural Violation  
**Enforcement**: IMMEDIATE REJECTION

---

## 0) Non-Negotiable Principle

**The Control Plane (Platform) orchestrates the Runtime Plane (Application). They are architecturally separate and MUST remain so.**

**VIOLATIONS OF THIS SEPARATION ARE ARCHITECTURAL DEFECTS AND WILL BE REJECTED IMMEDIATELY.**

---

## 1) Repository Boundaries (MANDATORY)

### 1.1 Platform Repository (`saraise-platform/`)

**Purpose**: Control Plane services that orchestrate and govern

**Contains:**
- `saraise-auth/` — Authentication Subsystem
- `saraise-policy-engine/` — Policy definition and evaluation
- `saraise-runtime/` — Request handler (platform-level)
- `saraise-control-plane/` — Tenant lifecycle, orchestration
- `saraise-platform-core/` — Shared platform libraries

**Responsibilities:**
- ✅ Tenant lifecycle (create, suspend, terminate)
- ✅ Policy definition and distribution
- ✅ Module enablement and versioning
- ✅ Shard provisioning and placement
- ✅ Migration orchestration
- ✅ Quota and entitlement enforcement
- ✅ Kill-switch execution

**FORBIDDEN:**
- ❌ Serving end-user traffic
- ❌ Business logic execution
- ❌ ERP module implementation
- ❌ Tenant-scoped data mutations (except orchestration)

### 1.2 Application Repository (`saraise-application/`)

**Purpose**: Runtime Plane that executes business logic

**Contains:**
- `backend/` — Django application with business modules
- `frontend/` — React UI for tenant users
- `docs/` — Application architecture
- `modules/` — 108+ business modules

**Responsibilities:**
- ✅ Request handling (end-user traffic)
- ✅ Authorization enforcement (delegates to Policy Engine)
- ✅ Workflow execution
- ✅ Data persistence (business data)
- ✅ Search indexing
- ✅ Audit emission
- ✅ Session validation (delegates to Auth Service)

**FORBIDDEN:**
- ❌ Tenant lifecycle operations (create, suspend, terminate)
- ❌ Policy definition or mutation
- ❌ Module enablement decisions
- ❌ Shard placement decisions
- ❌ Platform configuration management
- ❌ Authentication implementation (login, logout, session issuance)

---

## 2) Architectural Violations (IMMEDIATE REJECTION)

### 2.1 Violation: Tenant Lifecycle in Application Layer

**❌ FORBIDDEN:**
```python
# In saraise-application/backend/src/modules/tenant_management/
class TenantManagementService:
    @staticmethod
    def create_tenant(name: str, slug: str, ...):
        # VIOLATION: Application layer creating tenants
        tenant = Tenant.objects.create(...)
```

**✅ CORRECT:**
```python
# In saraise-platform/saraise-control-plane/
def create_tenant(tenant_id: str, ...):
    # Control Plane creates tenant
    tenant = TenantStore.create(...)
    # Then orchestrates Runtime Plane
    runtime_client.provision_tenant(tenant_id, ...)
```

### 2.2 Violation: Platform Configuration in Application Layer

**❌ FORBIDDEN:**
```python
# In saraise-application/backend/src/modules/platform_management/
class PlatformSettingViewSet(viewsets.ModelViewSet):
    # VIOLATION: Application layer managing platform settings
    def update_setting(self, request):
        PlatformSetting.objects.update(...)
```

**✅ CORRECT:**
```python
# In saraise-platform/saraise-control-plane/
def update_platform_setting(key: str, value: str):
    # Control Plane manages platform config
    setting = PlatformConfig.update(key, value)
    # Then distributes to Runtime Plane
    runtime_client.push_config(setting)
```

### 2.3 Violation: Platform UI in Application Frontend

**❌ FORBIDDEN:**
```typescript
// In saraise-application/frontend/src/App.tsx
<Route path="/platform/dashboard" element={<PlatformDashboard />} />
// VIOLATION: Platform UI in application frontend
```

**✅ CORRECT:**
```
saraise-platform/frontend/  → Platform UI (separate app)
saraise-application/frontend/ → Application UI (tenant users only)
```

### 2.4 Violation: Policy Decisions in Runtime Plane

**❌ FORBIDDEN:**
```python
# In saraise-application/backend/
def check_permission(user, resource, action):
    # VIOLATION: Runtime making policy decisions
    if user.role == 'admin':
        return True
```

**✅ CORRECT:**
```python
# In saraise-application/backend/
def check_permission(user, resource, action):
    # Runtime delegates to Policy Engine (Platform service)
    decision = policy_engine_client.evaluate(
        identity=user.identity_snapshot,
        resource=resource,
        action=action
    )
    return decision.allowed
```

---

## 3) Code Review Checklist (MANDATORY)

Every PR MUST answer these questions:

- [ ] Does this change violate Control Plane / Runtime Plane separation?
- [ ] Is tenant lifecycle operation in Application layer? → **REJECT**
- [ ] Is platform configuration in Application layer? → **REJECT**
- [ ] Is business logic in Platform layer? → **REJECT**
- [ ] Is end-user traffic served by Platform layer? → **REJECT**
- [ ] Is policy decision made in Runtime Plane? → **REJECT**

---

## 4) Enforcement Rules

### 4.1 Pre-Commit Hooks

- Check for `TenantManagementService` in `saraise-application/backend/` → **FAIL**
- Check for `PlatformSettingViewSet` in `saraise-application/backend/` → **FAIL**
- Check for platform routes in `saraise-application/frontend/` → **FAIL**

### 4.2 CI/CD Validation

- Architectural boundary tests
- Cross-repository dependency checks
- Service communication validation

---

## 5) References

- **Control Plane / Runtime Plane Separation**: `docs/architecture/control-plane-runtime-plane-separation.md`
- **Control Plane Deep Spec**: `docs/architecture/control-plane-and-runtime-plane-deep-spec.md`
- **Authentication Spec**: `docs/architecture/authentication-and-session-management-spec.md`
- **Policy Engine Spec**: `docs/architecture/policy-engine-spec.md`

---

**AUTHORITY**: This rule is non-negotiable. Violations are architectural defects and will be rejected immediately.

