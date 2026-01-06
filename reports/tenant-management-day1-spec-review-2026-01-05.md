# Tenant Management Module — Day 1 Specification Review

**Date:** January 5, 2026  
**Phase:** Phase 7, Week 2-3  
**Status:** ✅ COMPLETE

---

## Executive Summary

Completed specification review for Tenant Management module. This is a **platform-level module** (no tenant_id) that manages tenant organizations, modules, resource usage, settings, and health scores.

---

## Key Findings

### ✅ Backend Status
- **Models:** ✅ Complete (5 models: Tenant, TenantModule, TenantResourceUsage, TenantSettings, TenantHealthScore)
- **Serializers:** ✅ Complete (5 serializers)
- **API ViewSets:** ✅ Complete (5 ViewSets)
- **URLs:** ✅ Complete (routes registered)
- **Services:** ❌ Missing (needs implementation)
- **Tests:** ❌ Missing (tests directory empty)

### Architecture Notes

**CRITICAL:** This is a **platform-level module**:
- Models do NOT have `tenant_id` (they ARE tenants)
- Only platform owners can access these endpoints
- Uses `get_user_platform_role()` for authorization
- Manages tenant lifecycle, not tenant-scoped data

---

## Data Models Extracted

### 1. Tenant (Platform-Level)
- Basic info: name, slug, subdomain, custom_domain
- Status: trial, active, suspended, cancelled, archived
- Subscription: plan_id, trial_ends_at, subscription dates
- Contact: primary_contact, billing_email, technical_email
- Company: logo_url, website_url, industry, company_size, tax_id
- Configuration: timezone, language, currency, fiscal year
- Branding: primary_color, secondary_color, accent_color
- Features: features_enabled (JSON)
- Resource limits: max_users, max_storage_gb, max_api_calls_per_day
- Metadata: onboarded_by, metadata (JSON)

### 2. TenantModule (Platform-Level)
- Links tenant to module
- Fields: tenant, module_name, is_enabled, installed_at, installed_by, version, configuration, last_used_at, usage_count

### 3. TenantResourceUsage (Platform-Level)
- Daily resource tracking per tenant
- Fields: tenant, date, active_users, api_calls, storage_used_gb, bandwidth_used_gb, email_sent, sms_sent, avg_response_time_ms, error_count, slow_query_count

### 4. TenantSettings (Platform-Level)
- Tenant-specific key-value settings
- Fields: tenant, category, key, value (JSON), is_encrypted, updated_by

### 5. TenantHealthScore (Platform-Level)
- Health tracking per tenant
- Fields: tenant, date, overall_score, usage_score, performance_score, error_score, engagement_score, churn_risk, at_risk_reasons, calculated_at, metadata

---

## API Endpoints Extracted

### Tenant Management
- `GET /api/v1/tenant-management/tenants/` — List all tenants
- `POST /api/v1/tenant-management/tenants/` — Create tenant
- `GET /api/v1/tenant-management/tenants/{id}/` — Get tenant detail
- `PUT /api/v1/tenant-management/tenants/{id}/` — Update tenant
- `PATCH /api/v1/tenant-management/tenants/{id}/` — Partial update
- `DELETE /api/v1/tenant-management/tenants/{id}/` — Delete tenant
- `POST /api/v1/tenant-management/tenants/{id}/suspend/` — Suspend tenant
- `POST /api/v1/tenant-management/tenants/{id}/activate/` — Activate tenant
- `GET /api/v1/tenant-management/tenants/{id}/modules/` — Get tenant modules
- `GET /api/v1/tenant-management/tenants/{id}/resource_usage/` — Get resource usage
- `GET /api/v1/tenant-management/tenants/{id}/health_scores/` — Get health scores

### Module Management
- `GET /api/v1/tenant-management/modules/` — List all tenant modules
- `POST /api/v1/tenant-management/modules/` — Install module for tenant
- `GET /api/v1/tenant-management/modules/{id}/` — Get module detail
- `PUT /api/v1/tenant-management/modules/{id}/` — Update module
- `DELETE /api/v1/tenant-management/modules/{id}/` — Uninstall module
- `POST /api/v1/tenant-management/modules/{id}/enable/` — Enable module
- `POST /api/v1/tenant-management/modules/{id}/disable/` — Disable module

### Resource Usage
- `GET /api/v1/tenant-management/resource-usage/` — List resource usage (read-only)

### Settings
- `GET /api/v1/tenant-management/settings/` — List tenant settings
- `POST /api/v1/tenant-management/settings/` — Create setting
- `GET /api/v1/tenant-management/settings/{id}/` — Get setting
- `PUT /api/v1/tenant-management/settings/{id}/` — Update setting
- `DELETE /api/v1/tenant-management/settings/{id}/` — Delete setting

### Health Scores
- `GET /api/v1/tenant-management/health-scores/` — List health scores (read-only)

---

## Business Rules Extracted

1. **Platform-Level Access:** Only platform owners can access tenant management endpoints
2. **Tenant Status:** Cannot delete active tenants (must suspend/cancel first)
3. **Module Installation:** Modules can be enabled/disabled per tenant
4. **Resource Tracking:** Daily resource usage tracked per tenant
5. **Health Scoring:** Health scores calculated daily per tenant
6. **Settings:** Key-value settings organized by category

---

## Implementation Checklist

### Backend (Days 2-3)
- [x] Models implemented
- [x] Serializers implemented
- [x] API ViewSets implemented
- [x] URLs configured
- [ ] Services layer (business logic)
- [ ] Migrations verified

### Backend Tests (Days 3-4)
- [ ] test_models.py — Model validation and constraints
- [ ] test_api.py — API endpoint tests
- [ ] test_services.py — Service layer tests
- [ ] test_isolation.py — Platform-level access control (NOT tenant isolation)
- [ ] test_health.py — Health check tests

### Frontend (Days 4-5)
- [ ] Service client (tenant-service.ts)
- [ ] Tenant list page
- [ ] Tenant detail page
- [ ] Tenant create/edit dialogs
- [ ] Module management page
- [ ] Resource usage dashboard
- [ ] Health scores dashboard
- [ ] Settings management page

---

## Next Steps

**Day 2-3:** Backend Implementation
1. Create services.py with business logic
2. Verify migrations are applied
3. Test API endpoints manually

**Day 3-4:** Backend Tests
1. Write comprehensive test suite
2. Achieve ≥90% coverage
3. Verify platform-level access control

**Day 4-5:** Frontend Implementation
1. Create service client
2. Implement pages and components
3. Add routes

---

**Status:** ✅ Specification review complete. Ready for Day 2-3 backend implementation.

