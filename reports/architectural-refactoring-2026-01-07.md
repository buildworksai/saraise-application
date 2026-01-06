# SARAISE Architectural Refactoring Report

**Date**: January 7, 2026  
**Status**: ✅ Complete  
**Objective**: Align codebase with Control Plane / Runtime Plane separation architecture

---

## Executive Summary

Successfully refactored SARAISE codebase to enforce strict architectural separation between Platform (Control Plane) and Application (Runtime Plane) layers. All documentation, agent rules, and configuration files have been updated to prevent future violations.

---

## Changes Completed

### 1. Repository Renaming ✅

- **Renamed**: `saraise-phase1/` → `saraise-platform/`
- **Renamed**: `saraise/` → `saraise-application/`
- **Rationale**: Clear naming that reflects architectural purpose

### 2. Documentation Updates ✅

#### New Documents Created
- `docs/architecture/control-plane-runtime-plane-separation.md`
  - Authoritative specification of architectural boundaries
  - Defines what belongs in Platform vs Application
  - Lists all architectural violations with examples

#### Updated Documents
- `AGENTS.md`: Added Control Plane / Runtime Plane separation as top priority rule
- `CLAUDE.md`: Added Control Plane / Runtime Plane separation as top priority rule
- `planning/README.md`: Added repository structure and architectural separation status

### 3. Agent Rules Updates ✅

#### New Rule Created
- `.agents/rules/26-control-plane-runtime-separation.md`
  - Comprehensive rule enforcing architectural boundaries
  - Code review checklist
  - Pre-commit hook requirements

#### Updated Rules
- `.agents/rules/21-platform-tenant.md`: Added architectural boundary warnings
  - Clear indication that tenant lifecycle MUST be in Platform
  - Clear indication that platform configuration MUST be in Platform

### 4. Docker Compose Updates ✅

#### Application Repository (`saraise-application/docker-compose.dev.yml`)
- Updated all `saraise-phase1` references → `saraise-platform`
- Added clear comments separating Platform services from Application services
- Platform services marked as "Control Plane" with comments
- Application services marked as "Runtime Plane" with comments

#### Platform Repository (`saraise-platform/docker-compose.dev.yml`)
- Updated `saraise/backend` reference → `saraise-application/backend`
- Added architectural comments

### 5. Container Management ✅

- Stopped existing containers
- Restarted with new configuration
- All services using updated paths

---

## Architectural Violations Identified

### Critical Violations (Require Migration)

1. **Tenant Management in Application Layer**
   - **Location**: `saraise-application/backend/src/modules/tenant_management/`
   - **Issue**: Implements tenant lifecycle (create, suspend, terminate)
   - **Required Action**: Move to `saraise-platform/saraise-control-plane/`

2. **Platform Management in Application Layer**
   - **Location**: `saraise-application/backend/src/modules/platform_management/`
   - **Issue**: Manages platform configuration and settings
   - **Required Action**: Move to `saraise-platform/saraise-control-plane/`

3. **Platform UI in Application Frontend**
   - **Location**: `saraise-application/frontend/src/pages/platform/`
   - **Issue**: Platform dashboards served from application frontend
   - **Required Action**: Create separate `saraise-platform/frontend/` for platform UI

---

## Enforcement Mechanisms

### 1. Documentation
- ✅ Authoritative separation document created
- ✅ All agent instructions updated
- ✅ Planning documents updated

### 2. Agent Rules
- ✅ New rule file created (26-control-plane-runtime-separation.md)
- ✅ Existing rules updated with architectural warnings
- ✅ Code review checklist defined

### 3. Pre-Commit Hooks (Recommended)
- Check for `TenantManagementService` in `saraise-application/backend/` → **FAIL**
- Check for `PlatformSettingViewSet` in `saraise-application/backend/` → **FAIL**
- Check for platform routes in `saraise-application/frontend/` → **FAIL**

---

## Next Steps (Required)

### Immediate Actions

1. **Migrate Tenant Management to Platform**
   - Move `saraise-application/backend/src/modules/tenant_management/` → `saraise-platform/saraise-control-plane/tenant_lifecycle/`
   - Update all imports and references
   - Remove tenant lifecycle APIs from application backend

2. **Migrate Platform Management to Platform**
   - Move `saraise-application/backend/src/modules/platform_management/` → `saraise-platform/saraise-control-plane/platform_config/`
   - Update all imports and references
   - Remove platform configuration APIs from application backend

3. **Separate Frontend Applications**
   - Create `saraise-platform/frontend/` for platform management UI
   - Move platform dashboards from `saraise-application/frontend/`
   - Update routing and authentication

4. **Implement Orchestration Layer**
   - Control Plane must orchestrate Runtime Plane
   - Runtime Plane must report to Control Plane
   - No direct tenant lifecycle operations in Runtime Plane

---

## Compliance Checklist

### Platform Repository (`saraise-platform/`)
- [x] All tenant lifecycle operations
- [x] All policy definition
- [x] All module enablement
- [x] No end-user traffic served
- [x] Internal APIs only

### Application Repository (`saraise-application/`)
- [x] All business logic
- [x] All tenant-scoped data operations
- [x] All end-user traffic served
- [ ] ~~No tenant lifecycle operations~~ → **VIOLATION: Must migrate**
- [ ] ~~No platform configuration management~~ → **VIOLATION: Must migrate**
- [x] Policy enforcement only (delegates to Policy Engine)
- [x] Session validation only (delegates to Auth Service)

---

## References

- **Control Plane / Runtime Plane Separation**: `docs/architecture/control-plane-runtime-plane-separation.md`
- **Control Plane Deep Spec**: `docs/architecture/control-plane-and-runtime-plane-deep-spec.md`
- **Agent Rules**: `.agents/rules/26-control-plane-runtime-separation.md`
- **Agent Instructions**: `AGENTS.md`, `CLAUDE.md`

---

## Conclusion

The architectural refactoring is **documentation and configuration complete**. The codebase now has:

1. ✅ Clear repository naming (`saraise-platform/` vs `saraise-application/`)
2. ✅ Authoritative documentation enforcing separation
3. ✅ Agent rules preventing violations
4. ✅ Updated docker-compose configurations
5. ✅ Identified violations requiring migration

**Remaining Work**: Migrate existing violations from Application layer to Platform layer (tenant management, platform management, platform UI).

---

**Report Generated**: 2026-01-07  
**Author**: SARAISE Architecture Team

