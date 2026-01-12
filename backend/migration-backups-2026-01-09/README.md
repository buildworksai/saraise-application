# Migration Backups - January 9, 2026

## Purpose

This directory contains backups of large migration files that were split into smaller migrations per SARAISE migration standards.

**Standard**: Maximum 200 lines per migration file
**Reason**: Maintainability, reviewability, and rollback granularity

## Backed Up Files

### 1. Core Migration 0004
- **Original**: `core/migrations/0004_compliancecheck_entitlementcheck_guardrailrule_and_more.py`
- **Size**: 871 lines (39KB)
- **Backup**: `0004_compliancecheck_entitlementcheck_guardrailrule_and_more.py`
- **Split Into**: 5 migrations (0004-0008)
  - 0004_create_compliancecheck.py
  - 0005_create_entitlementcheck.py
  - 0006_create_guardrailrule.py
  - 0007_create_moduleinstallation.py
  - 0008_create_module_registry_and_upgrade.py

### 2. AI Agent Management Migration 0001
- **Original**: `ai_agent_management/migrations/0001_initial.py`
- **Size**: 2,205 lines (80KB)
- **Backup**: `ai_agent_0001_initial_BACKUP.py`
- **Split Into**: 11 migrations (0001-0011)
  - 0001_initial_agent.py
  - 0002_create_agent_execution.py
  - 0003_create_tool.py
  - 0004_create_tool_invocation.py
  - 0005_create_approval_request.py
  - 0006_create_sod_policy.py
  - 0007_create_tenant_quota.py
  - 0008_create_quota_usage.py
  - 0009_add_agent_indexes.py
  - 0010_add_execution_indexes.py
  - 0011_add_tool_indexes.py

### 3. Tenant Management Migration 0001
- **Original**: `tenant_management/migrations/0001_initial.py`
- **Size**: 600+ lines (24KB)
- **Backup**: `tenant_mgmt_0001_initial_BACKUP.py`
- **Split Into**: 4 migrations (0001-0004)
  - 0001_initial_tenant.py
  - 0002_create_feature_flag.py
  - 0003_create_tenant_settings.py
  - 0004_create_audit_event.py

## Restore Procedure (If Needed)

If splitting causes issues:

```bash
# 1. Remove split migrations
rm src/core/migrations/0004_*.py
rm src/core/migrations/0005_*.py
rm src/core/migrations/0006_*.py
rm src/core/migrations/0007_*.py
rm src/core/migrations/0008_*.py

# 2. Restore original
cp migration-backups-2026-01-09/0004_*.py src/core/migrations/

# 3. Rollback database
python manage.py migrate core 0003

# 4. Re-apply
python manage.py migrate core
```

## Migration Split Timestamp

**Date**: 2026-01-09
**Agent**: Claude Sonnet 4.5
**Task**: Surgical migration splitting per SARAISE standards
**Authority**: [migration-coordination-strategy.md](../../../saraise-documentation/database/migration-coordination-strategy.md)

---

**IMPORTANT**: Do not delete this directory. These backups are permanent historical records.
