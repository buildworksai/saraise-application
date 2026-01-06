# SARAISE Control Plane / Runtime Plane Separation

**Status:** Authoritative — Freeze Blocking  
**Version:** 1.0.0  
**Last Updated:** January 7, 2026

This document defines the **non-negotiable architectural separation** between the Platform (Control Plane) and Application (Runtime Plane) layers in SARAISE.

**VIOLATIONS OF THIS SEPARATION ARE ARCHITECTURAL DEFECTS AND WILL BE REJECTED IMMEDIATELY.**

---

## 0) Non-Negotiable Principles

1. **Control Plane is the brain.** Runtime Plane never makes policy decisions.
2. **Runtime Plane is dumb by design.** It executes, enforces, and reports.
3. **Control Plane never serves end-user traffic.** Only internal orchestration APIs.
4. **Runtime Plane serves all end-user traffic.** Business logic execution only.
5. **All lifecycle actions are explicit.** No implicit creation, upgrade, or deletion.
6. **Global safety > tenant convenience.** The platform must protect itself.

---

## 1) Repository Structure (MANDATORY)

### 1.1 Platform Repository (`saraise-platform/`)

**Purpose:** Control Plane services that orchestrate and govern the application layer.

**Contains:**
- `saraise-auth/` — Authentication Subsystem (session issuance, validation)
- `saraise-policy-engine/` — Policy definition and evaluation engine
- `saraise-runtime/` — Request handler and policy enforcement
- `saraise-control-plane/` — Tenant lifecycle, module enablement, orchestration
- `saraise-platform-core/` — Shared platform libraries

**Responsibilities:**
- Tenant lifecycle management (create, suspend, terminate)
- Policy definition and distribution
- Module enablement and versioning
- Shard provisioning and placement
- Migration orchestration
- Quota and entitlement enforcement
- Kill-switch execution

**FORBIDDEN:**
- ❌ Serving end-user traffic
- ❌ Business logic execution
- ❌ ERP module implementation
- ❌ Tenant-scoped data mutations (except orchestration)

### 1.2 Application Repository (`saraise-application/`)

**Purpose:** Runtime Plane that executes business logic and serves end-user traffic.

**Contains:**
- `backend/` — Django application with business modules
- `frontend/` — React UI for tenant users
- `docs/` — Application architecture and module specifications
- `modules/` — 108+ business modules (CRM, Finance, HR, etc.)

**Responsibilities:**
- Request handling (end-user traffic)
- Authorization enforcement (via Policy Engine from Platform)
- Workflow execution
- Data persistence (business data)
- Search indexing
- Audit emission
- Session validation (delegates to Auth Service)

**FORBIDDEN:**
- ❌ Tenant lifecycle operations (create, suspend, terminate)
- ❌ Policy definition or mutation
- ❌ Module enablement decisions
- ❌ Shard placement decisions
- ❌ Platform configuration management
- ❌ Authentication implementation (login, logout, session issuance)

---

## 2) Communication Model (MANDATORY)

### 2.1 Control Plane → Runtime Plane

**Direction:** Control Plane orchestrates Runtime Plane

**Mechanisms:**
- Internal REST APIs (not exposed to end-users)
- Policy distribution (signed bundles)
- Configuration push (tenant routing, module enablement)
- Health monitoring (runtime reports status)

**Example:**
```
Control Plane creates tenant → Provisions shard → Enables modules → 
Pushes policy bundle → Runtime Plane receives config → Serves tenant traffic
```

### 2.2 Runtime Plane → Control Plane

**Direction:** Runtime Plane reports to Control Plane

**Mechanisms:**
- Health metrics
- Saturation signals
- Policy evaluation stats
- Quota violations
- Audit events

**Example:**
```
Runtime Plane handles request → Evaluates policy → Enforces quota → 
Reports metrics → Control Plane reacts (throttle, isolate, etc.)
```

### 2.3 End Users → Runtime Plane Only

**Direction:** End users ONLY interact with Runtime Plane

**Mechanisms:**
- REST APIs (Django backend)
- Web UI (React frontend)
- WebSocket connections (real-time updates)

**FORBIDDEN:**
- ❌ End users accessing Control Plane services directly
- ❌ Platform management UI in application frontend
- ❌ Tenant lifecycle APIs in application backend

---

## 3) Architectural Violations (IMMEDIATE REJECTION)

### 3.1 Violation: Application Backend Implementing Control Plane Operations

**❌ FORBIDDEN:**
```python
# In saraise-application/backend/src/modules/tenant_management/
class TenantViewSet(viewsets.ModelViewSet):
    def create_tenant(self, request):
        # VIOLATION: Application layer creating tenants
        tenant = Tenant.objects.create(...)
```

**✅ CORRECT:**
```python
# In saraise-platform/saraise-control-plane/
def create_tenant(tenant_id: str, ...):
    # Control Plane creates tenant
    # Then orchestrates Runtime Plane to provision resources
    tenant = TenantStore.create(...)
    # Push config to Runtime Plane
    runtime_client.provision_tenant(tenant_id, ...)
```

### 3.2 Violation: Application Backend Managing Platform Configuration

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
    # Then distributes to Runtime Plane
    setting = PlatformConfig.update(key, value)
    runtime_client.push_config(setting)
```

### 3.3 Violation: Frontend Mixing Platform and Application UI

**❌ FORBIDDEN:**
```typescript
// In saraise-application/frontend/src/App.tsx
<Route path="/platform/dashboard" element={<PlatformDashboard />} />
<Route path="/tenant/dashboard" element={<TenantDashboard />} />
// VIOLATION: Single app serving both platform and application UI
```

**✅ CORRECT:**
```
saraise-platform/frontend/  → Platform UI (separate app)
saraise-application/frontend/ → Application UI (tenant users only)
```

### 3.4 Violation: Runtime Plane Making Policy Decisions

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

## 4) Implementation Checklist (MANDATORY)

### 4.1 Platform Repository (`saraise-platform/`)

- [ ] All tenant lifecycle operations in Control Plane
- [ ] All policy definition in Policy Engine
- [ ] All module enablement in Control Plane
- [ ] No end-user traffic served
- [ ] Internal APIs only (not exposed to internet)
- [ ] Orchestration layer connecting to Runtime Plane

### 4.2 Application Repository (`saraise-application/`)

- [ ] All business logic in Django backend
- [ ] All tenant-scoped data operations
- [ ] All end-user traffic served
- [ ] No tenant lifecycle operations
- [ ] No platform configuration management
- [ ] Policy enforcement only (delegates to Policy Engine)
- [ ] Session validation only (delegates to Auth Service)

---

## 5) Migration Path (For Existing Violations)

### 5.1 Move Tenant Management from Application to Platform

**Current State:**
- `saraise-application/backend/src/modules/tenant_management/` exists

**Target State:**
- Move tenant lifecycle operations to `saraise-platform/saraise-control-plane/`
- Application backend only reads tenant status (for filtering)
- Control Plane orchestrates tenant provisioning

### 5.2 Move Platform Management from Application to Platform

**Current State:**
- `saraise-application/backend/src/modules/platform_management/` exists

**Target State:**
- Move platform configuration to `saraise-platform/saraise-control-plane/`
- Application backend only reads platform config (for feature flags)
- Control Plane manages all platform settings

### 5.3 Separate Frontend Applications

**Current State:**
- Single React app serving both platform and application UI

**Target State:**
- `saraise-platform/frontend/` — Platform management UI
- `saraise-application/frontend/` — Application UI (tenant users only)

---

## 6) Enforcement Rules

### 6.1 Code Review Checklist

Every PR MUST answer:
- [ ] Does this change violate Control Plane / Runtime Plane separation?
- [ ] Is tenant lifecycle operation in Application layer? → **REJECT**
- [ ] Is platform configuration in Application layer? → **REJECT**
- [ ] Is business logic in Platform layer? → **REJECT**
- [ ] Is end-user traffic served by Platform layer? → **REJECT**

### 6.2 Automated Checks

- Pre-commit hooks check for forbidden patterns
- CI/CD validates architectural boundaries
- Linters flag cross-boundary violations

---

## 7) References

- **Control Plane Spec**: `docs/architecture/control-plane-and-runtime-plane-deep-spec.md`
- **Authentication Spec**: `docs/architecture/authentication-and-session-management-spec.md`
- **Policy Engine Spec**: `docs/architecture/policy-engine-spec.md`
- **Module Framework**: `docs/architecture/module-framework.md`

---

**End of Document**

**AUTHORITY**: This document is the authoritative source for Control Plane / Runtime Plane separation. All implementations MUST comply. Violations are architectural defects and will be rejected immediately.

