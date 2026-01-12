# Platform Management Mode-Aware Architecture Correction

**Date:** 2026-01-10  
**Status:** ✅ COMPLETE

## Summary

Corrected the architectural violation by making `platform_management` module **mode-aware** instead of removing it. The module now correctly supports both self-hosted and SaaS modes.

## Problem

Initially, `platform_management` was incorrectly moved entirely to Control Plane, which broke self-hosted mode where Control Plane services are not deployed.

## Solution: Mode-Aware Architecture

The `platform_management` module now behaves differently based on `SARAISE_MODE`:

### Self-Hosted Mode (`SARAISE_MODE: self-hosted`)

- **Full CRUD operations** in application repo
- No Control Plane dependency
- Platform settings, feature flags, health, audit managed locally
- `PlatformFeatureFlagService` queries local models

### SaaS Mode (`SARAISE_MODE: saas`)

- **Read-only operations** in application repo
- Mutations must go through Control Plane APIs
- `PlatformFeatureFlagService` queries Control Plane APIs
- Control Plane has full CRUD for platform configuration

## Changes Made

### 1. Application Repo (`saraise-application/`)

**Restored:**
- ✅ `platform_management` in `INSTALLED_APPS`
- ✅ `platform_management` URL routes (`/api/v1/platform/`)
- ✅ `platform_management` in `FOUNDATION_MODULES` list

**Updated:**
- ✅ `api.py` - ViewSets are now mode-aware:
  - `_get_viewset_base()` function returns `ModelViewSet` (self-hosted) or `ReadOnlyModelViewSet` (SaaS)
  - `PlatformSettingViewSet`, `FeatureFlagViewSet`, `SystemHealthViewSet`, `PlatformMetricsViewSet` are mode-aware
  - Mutations (create/update/delete) raise `PermissionDenied` in SaaS mode with clear error message
  - `FeatureFlagViewSet` has `toggle` action (self-hosted only)

- ✅ `platform_feature_flags.py` - Service is now mode-aware:
  - `is_feature_enabled()` queries local models in self-hosted, Control Plane in SaaS
  - `get_setting()` queries local models in self-hosted, Control Plane in SaaS
  - Separate methods: `_check_local_flag()`, `_check_control_plane_flag()`, `_get_local_setting()`, `_get_control_plane_setting()`

### 2. Platform Repo (`saraise-platform/`)

**No changes needed** - Control Plane implementation remains for SaaS mode.

## Architecture Compliance

✅ **Self-Hosted Mode:** Application manages platform configuration (no Control Plane)  
✅ **SaaS Mode:** Application is read-only, Control Plane manages configuration  
✅ **Mode-Aware:** All ViewSets and services check `SARAISE_MODE`  
✅ **Clear Error Messages:** SaaS mode mutations return helpful error messages directing to Control Plane

## API Behavior

### Self-Hosted Mode

```python
# Full CRUD available
POST   /api/v1/platform/settings/          # Create setting
GET    /api/v1/platform/settings/          # List settings
GET    /api/v1/platform/settings/{id}/     # Get setting
PUT    /api/v1/platform/settings/{id}/     # Update setting
DELETE /api/v1/platform/settings/{id}/     # Delete setting

POST   /api/v1/platform/feature-flags/     # Create flag
POST   /api/v1/platform/feature-flags/{id}/toggle/  # Toggle flag
```

### SaaS Mode

```python
# Read-only (mutations return PermissionDenied)
GET    /api/v1/platform/settings/          # List settings ✅
GET    /api/v1/platform/settings/{id}/     # Get setting ✅
POST   /api/v1/platform/settings/         # ❌ PermissionDenied (use Control Plane)
PUT    /api/v1/platform/settings/{id}/    # ❌ PermissionDenied (use Control Plane)
DELETE /api/v1/platform/settings/{id}/    # ❌ PermissionDenied (use Control Plane)
```

## Runtime Feature Flag Checks

Application code uses `PlatformFeatureFlagService` which is mode-aware:

```python
from src.core.platform_feature_flags import PlatformFeatureFlagService

# Works in both modes (queries local models in self-hosted, Control Plane in SaaS)
if PlatformFeatureFlagService.is_feature_enabled("new_feature", tenant_id=tenant_id):
    # Feature is enabled
    pass

# Works in both modes
value = PlatformFeatureFlagService.get_setting("setting_key", tenant_id=tenant_id)
```

## Testing

### Self-Hosted Mode Testing

```bash
export SARAISE_MODE=self-hosted
python manage.py runserver

# Test full CRUD
curl -X POST http://localhost:8000/api/v1/platform/settings/ \
  -H "Content-Type: application/json" \
  -d '{"key": "test_setting", "value": "test_value"}'
```

### SaaS Mode Testing

```bash
export SARAISE_MODE=saas
export SARAISE_PLATFORM_URL=http://localhost:18004
python manage.py runserver

# Test read-only (should work)
curl http://localhost:8000/api/v1/platform/settings/

# Test mutation (should return PermissionDenied)
curl -X POST http://localhost:8000/api/v1/platform/settings/ \
  -H "Content-Type: application/json" \
  -d '{"key": "test_setting", "value": "test_value"}'
# Response: {"detail": "Platform settings can only be created via Control Plane in SaaS mode..."}
```

## References

- Phase 7 Documentation: `saraise-documentation/planning/phases/phase-7-foundation-part1.md`
- Architecture: `saraise-documentation/architecture/existing/control-plane-runtime-plane-separation.md`
- Rule: `saraise-documentation/rules/agent-rules/26-control-plane-runtime-separation.md`
