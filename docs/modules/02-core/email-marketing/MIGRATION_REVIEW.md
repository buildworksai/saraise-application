# Email Marketing Module - Migration Review

**Date:** 2025-01-XX
**Status:** Review Complete - Issues Identified

## Executive Summary

This document reviews the existing migrations for the Email Marketing module, identifies issues, and documents required corrections per SARAISE migration standards.

## Current Migration State

### Existing Migration File

**File:** `backend/src/modules/email_marketing/migrations/versions/001_email_marketing_module_initial.py`

**Current State:**
- **Revision ID:** `001_email_marketing_module_initial`
- **Down Revision:** `None` (branch root)
- **Depends On:** `None`
- **Purpose:** Placeholder migration for module tracking
- **Table Creation:** None (tables created by marketing module migrations)

**Note in Migration:**
> "Email Marketing module tables are created by the marketing module migrations. This migration exists for module tracking purposes and to ensure proper migration orchestration."

## Table Creation Analysis

### Tables Created by Marketing Module Migration

The marketing module migration `002_marketing_initial.py` creates the following Email Marketing tables:

1. **`email_segments`** - Email audience segments
2. **`email_templates`** - Email templates
3. **`email_automations`** - Email automation workflows
4. **`email_campaigns`** - Email campaigns
5. **`email_activities`** - Email activity tracking (sends, opens, clicks, bounces)
6. **`email_unsubscribes`** - Email unsubscribe list

**Migration:** `backend/src/modules/email_marketing/migrations/0001_initial.py` (Django migration)
**Down Revision:** `001_marketing_architecture`

### Resource System Table Creation

The Email Marketing module uses the Resource system, which automatically creates tables when Resources are registered via the `@post_install` hook in `hooks.py`.

**ResourceService Behavior:**
- Creates tables with standard fields: `id`, `tenant_id`, `created_at`, `created_by`, `updated_at`, `updated_by`
- Creates indexes for `tenant_id` and fields marked as `required` or `indexed`
- **Does NOT automatically create foreign key constraints**
- **Does NOT create composite indexes**
- **Does NOT create unique constraints**

## Issues Identified

### ISSUE #1: Migration Dependency Missing ⚠️ CRITICAL

**Problem:**
- Email Marketing module migration has `down_revision: None`, making it a branch root
- Should depend on `002_marketing_initial` which creates the Email Marketing tables
- Without proper dependency, migration order is undefined

**Current Code:**
```python
down_revision: Union[str, None] = None
depends_on: Union[str, Sequence[str], None] = None
```

**Required Fix:**
```python
down_revision: Union[str, None] = "002_marketing_initial"
depends_on: Union[str, Sequence[str], None] = None
```

**Impact:**
- Migration might run before marketing module creates tables
- Could cause errors if Resource system tries to create tables that already exist
- Module tracking may be incorrect

---

### ISSUE #2: Table Creation Conflict Risk ⚠️ HIGH

**Problem:**
- Marketing module migration (`002_marketing_initial`) creates Email Marketing tables
- Resource system (`ResourceService._create_table`) also creates tables when Resources are registered
- Potential conflict if both try to create the same tables

**Analysis:**
- Marketing module migration uses `IF NOT EXISTS` checks, so it's safe if tables already exist
- Resource system uses `CREATE TABLE IF NOT EXISTS`, so it's also safe
- **However:** Resource-created tables may have different structure (no foreign keys, different indexes)

**Required Action:**
- Verify that Resource registration does NOT create tables if they already exist from marketing migration
- OR: Ensure Resource system uses marketing module tables instead of creating new ones
- Document the decision in migration comments

---

### ISSUE #3: Missing Foreign Key Constraints ⚠️ MEDIUM

**Problem:**
- Marketing module migration creates tables with foreign keys
- Resource system does NOT automatically create foreign keys
- If Resource system creates tables, foreign keys will be missing

**Current Foreign Keys in Marketing Migration:**
- `email_segments.tenant_id` → `tenants.id`
- `email_segments.created_by` → `users.id`
- `email_segments.updated_by` → `users.id`
- `email_templates.tenant_id` → `tenants.id`
- `email_templates.created_by` → `users.id`
- `email_templates.updated_by` → `users.id`
- `email_automations.tenant_id` → `tenants.id`
- `email_automations.entry_segment_id` → `email_segments.id`
- `email_automations.created_by` → `users.id`
- `email_automations.updated_by` → `users.id`
- `email_campaigns.tenant_id` → `tenants.id`
- `email_campaigns.segment_id` → `email_segments.id`
- `email_campaigns.automation_workflow_id` → `email_automations.id`
- `email_campaigns.created_by` → `users.id`
- `email_campaigns.updated_by` → `users.id`
- `email_activities.tenant_id` → `tenants.id`
- `email_activities.campaign_id` → `email_campaigns.id`
- `email_activities.automation_id` → `email_automations.id`
- `email_unsubscribes.tenant_id` → `tenants.id`
- `email_unsubscribes.campaign_id` → `email_campaigns.id`
- `email_unsubscribes.automation_id` → `email_automations.id`

**Required Action:**
- Verify foreign keys exist after Resource registration
- If missing, create a migration to add foreign key constraints
- Document foreign key relationships

---

### ISSUE #4: Missing Composite Indexes ⚠️ MEDIUM

**Problem:**
- Marketing module migration creates composite indexes (e.g., `idx_email_campaign_tenant_status`)
- Resource system only creates single-column indexes
- Composite indexes may be missing if Resource system creates tables

**Current Composite Indexes in Marketing Migration:**
- `idx_email_segment_tenant_name` on `email_segments(tenant_id, segment_name)`
- `idx_email_template_tenant_name` on `email_templates(tenant_id, template_name)`
- `idx_email_automation_tenant_status` on `email_automations(tenant_id, status)`
- `idx_email_campaign_tenant_status` on `email_campaigns(tenant_id, status)`
- `idx_email_activity_tenant_type` on `email_activities(tenant_id, activity_type)`
- `idx_email_unsubscribe_tenant` on `email_unsubscribes(tenant_id)`

**Required Action:**
- Verify composite indexes exist after Resource registration
- If missing, create a migration to add composite indexes
- Document index requirements

---

### ISSUE #5: Missing Unique Constraints ⚠️ MEDIUM

**Problem:**
- Marketing module migration creates unique constraints (e.g., `uq_tenant_email_unsubscribe`)
- Resource system does NOT automatically create unique constraints
- Unique constraints may be missing if Resource system creates tables

**Current Unique Constraints in Marketing Migration:**
- `uq_tenant_email_unsubscribe` on `email_unsubscribes(tenant_id, email)`

**Required Action:**
- Verify unique constraints exist after Resource registration
- If missing, create a migration to add unique constraints
- Document unique constraint requirements

---

### ISSUE #6: Module Revision Map Missing ⚠️ LOW

**Problem:**
- Email Marketing module revision `001_email_marketing_module_initial` is NOT in `MODULE_REVISION_MAP`
- Module tracking may be incorrect
- Migration orchestrator may not recognize Email Marketing module

**Current MODULE_REVISION_MAP:**
```python
"marketing": {
    "001_marketing_architecture",
    "002_marketing_initial",  # Creates Email Marketing tables
    # ... other marketing revisions
}
```

**Required Action:**
- Add Email Marketing module to `MODULE_REVISION_MAP` in `backend/src/core/migration_orchestrator.py`
- OR: Document that Email Marketing is tracked as part of Marketing module

---

### ISSUE #7: Tenant Isolation Verification ⚠️ MEDIUM

**Problem:**
- Need to verify all tables have `tenant_id` column with proper foreign key
- Need to verify all queries filter by `tenant_id` for multi-tenant isolation

**Current State:**
- All tables in marketing migration have `tenant_id` column
- All tables have foreign key to `tenants.id`
- All tables have index on `tenant_id`

**Required Action:**
- Verify Resource-created tables also have `tenant_id` column
- Verify all service queries filter by `tenant_id`
- Document tenant isolation compliance

---

### ISSUE #8: Timestamp Columns Verification ⚠️ LOW

**Problem:**
- Need to verify all tables have `created_at` and `updated_at` columns with timezone support

**Current State:**
- All tables in marketing migration have `created_at` and `updated_at` with `DateTime(timezone=True)`
- All tables use `server_default=sa.text('now()')` for `created_at`
- All tables use `auto_now=True` for `updated_at` (handled by Django ORM)

**Required Action:**
- Verify Resource-created tables also have proper timestamp columns
- Document timestamp column requirements

---

## Required Corrections

### Correction #1: Fix Migration Dependency

**File:** `backend/src/modules/email_marketing/migrations/versions/001_email_marketing_module_initial.py`

**Change:**
```python
# Before
down_revision: Union[str, None] = None

# After
down_revision: Union[str, None] = "002_marketing_initial"
```

**Rationale:**
- Ensures Email Marketing migration runs after marketing module creates tables
- Maintains proper migration order
- Prevents table creation conflicts

---

### Correction #2: Verify Table Creation Strategy

**Decision Required:**
1. **Option A:** Resource system uses existing marketing module tables (no table creation)
2. **Option B:** Resource system creates tables, marketing migration is skipped (if tables exist)
3. **Option C:** Hybrid approach - marketing migration creates tables, Resource system only registers metadata

**Recommended:** Option C (Hybrid)
- Marketing migration creates tables with proper structure (foreign keys, indexes, constraints)
- Resource system registers metadata only (no table creation if tables exist)
- Ensures consistent table structure across environments

**Required Action:**
- Verify `ResourceService._create_table` checks if table exists before creating
- Document table creation strategy in migration comments
- Update `hooks.py` to handle existing tables gracefully

---

### Correction #3: Add Foreign Key Verification Migration (If Needed)

**File:** `backend/src/modules/email_marketing/migrations/versions/002_email_marketing_foreign_keys.py` (NEW)

**Purpose:**
- Verify all foreign key constraints exist
- Add missing foreign keys if Resource system created tables without them

**Required Foreign Keys:**
- All foreign keys listed in ISSUE #3 above

**Implementation:**
```python
def upgrade() -> None:
    # Check and add foreign keys if missing
    # Use IF NOT EXISTS pattern for idempotency
    pass
```

---

### Correction #4: Add Composite Index Migration (If Needed)

**File:** `backend/src/modules/email_marketing/migrations/versions/003_email_marketing_indexes.py` (NEW)

**Purpose:**
- Verify all composite indexes exist
- Add missing composite indexes if Resource system created tables without them

**Required Composite Indexes:**
- All composite indexes listed in ISSUE #4 above

**Implementation:**
```python
def upgrade() -> None:
    # Check and add composite indexes if missing
    # Use IF NOT EXISTS pattern for idempotency
    pass
```

---

### Correction #5: Add Unique Constraint Migration (If Needed)

**File:** `backend/src/modules/email_marketing/migrations/versions/004_email_marketing_constraints.py` (NEW)

**Purpose:**
- Verify all unique constraints exist
- Add missing unique constraints if Resource system created tables without them

**Required Unique Constraints:**
- `uq_tenant_email_unsubscribe` on `email_unsubscribes(tenant_id, email)`

**Implementation:**
```python
def upgrade() -> None:
    # Check and add unique constraints if missing
    # Use IF NOT EXISTS pattern for idempotency
    pass
```

---

### Correction #6: Update Module Revision Map

**File:** `backend/src/core/migration_orchestrator.py`

**Change:**
```python
# Add email_marketing module to MODULE_REVISION_MAP
"email_marketing": {
    "001_email_marketing_module_initial",
    # Future migrations will be added here
}
```

**OR:**
- Document that Email Marketing is tracked as part of Marketing module
- Update migration comments to reflect this

---

## Migration Structure Review

### Current Structure

```
backend/src/modules/email_marketing/migrations/
├── versions/
│   └── 001_email_marketing_module_initial.py  # Placeholder migration
└── env.py  # (if exists)
```

### Required Structure

```
backend/src/modules/email_marketing/migrations/
├── versions/
│   ├── 001_email_marketing_module_initial.py  # Fixed: depends on 002_marketing_initial
│   ├── 002_email_marketing_foreign_keys.py     # NEW: Verify/add foreign keys
│   ├── 003_email_marketing_indexes.py          # NEW: Verify/add composite indexes
│   └── 004_email_marketing_constraints.py       # NEW: Verify/add unique constraints
└── env.py  # (if exists)
```

---

## Compliance Checklist

### SARAISE Migration Standards

- [x] **Migration Structure:** File follows `NNN_module_description.py` format
- [x] **Revision ID:** Matches filename (`001_email_marketing_module_initial`)
- [ ] **Down Revision:** ❌ Should be `"002_marketing_initial"` not `None`
- [ ] **Depends On:** ✅ Correctly set to `None` (dependency handled by `down_revision`)
- [ ] **Branch Labels:** ✅ Correctly set to `None`
- [x] **Tenant Isolation:** All tables have `tenant_id` column (in marketing migration)
- [x] **Timestamp Columns:** All tables have `created_at` and `updated_at` (in marketing migration)
- [x] **Indexes:** All tables have proper indexes (in marketing migration)
- [x] **Foreign Keys:** All tables have proper foreign keys (in marketing migration)
- [x] **Unique Constraints:** All unique constraints defined (in marketing migration)
- [ ] **Idempotency:** ✅ Migration is idempotent (no-op)
- [ ] **Downgrade:** ✅ Downgrade function exists (no-op)

---

## Testing Requirements

### Migration Upgrade Test

```bash
# Test migration upgrade
cd backend
python manage.py migrate email_marketing

# Verify:
# 1. Email Marketing migration runs after marketing migration
# 2. No table creation conflicts
# 3. All tables exist with proper structure
# 4. All foreign keys exist
# 5. All indexes exist
# 6. All unique constraints exist
```

### Migration Downgrade Test

```bash
# Test migration downgrade
cd backend
python manage.py migrate email_marketing 0001_initial

# Verify:
# 1. Email Marketing migration can be rolled back
# 2. No errors during rollback
# 3. Tables remain (created by marketing migration)
```

### Resource Registration Test

```bash
# Test Resource registration
python -c "
from src.modules.email_marketing.hooks import register_email_marketing_resources
import asyncio
asyncio.run(register_email_marketing_resources())
"

# Verify:
# 1. Resource registration does NOT create tables (tables already exist)
# 2. Resource metadata is registered correctly
# 3. No errors during registration
```

---

## Recommendations

### Immediate Actions

1. **Fix Migration Dependency:** Update `down_revision` to `"002_marketing_initial"`
2. **Verify Table Creation Strategy:** Ensure Resource system does not create tables if they already exist
3. **Document Decision:** Update migration comments to explain table creation strategy

### Future Actions

1. **Add Verification Migrations:** Create migrations to verify/add foreign keys, indexes, and constraints
2. **Update Module Revision Map:** Add Email Marketing to `MODULE_REVISION_MAP`
3. **Add Integration Tests:** Test migration upgrade/downgrade paths
4. **Document Architecture:** Update module documentation to explain migration strategy

---

## Related Documentation

- **SARAISE Migration Standards:** See `docs/migrations/` directory
- **Resource System:** See `backend/src/metadata/services/resource_service.py`
- **Marketing Module Migration:** See `backend/src/modules/email_marketing/migrations/0001_initial.py`
- **Module Revision Map:** See `backend/src/core/migration_orchestrator.py`

---

## Conclusion

The Email Marketing module migration is a placeholder that correctly does not create tables (tables are created by marketing module migration). However, the migration dependency is incorrect and should be fixed to ensure proper migration order. Additional verification migrations may be needed to ensure foreign keys, indexes, and constraints are present if Resource system creates tables.

**Priority:** Fix migration dependency (ISSUE #1) is CRITICAL and should be addressed immediately.
