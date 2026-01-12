# CRM Module - Migrations

## Overview

This directory contains Django migrations for the CRM module. All migrations follow SARAISE migration standards and enforce Row-Level Multitenancy.

## Creating Migrations

When Django environment is set up, create migrations using:

```bash
cd backend
python manage.py makemigrations crm
python manage.py migrate
```

## Expected Migrations

The following migrations will be created:

1. **0001_initial.py** - Creates all core tables:
   - `crm_leads` (Lead model)
   - `crm_accounts` (Account model)
   - `crm_contacts` (Contact model)
   - `crm_opportunities` (Opportunity model)
   - `crm_activities` (Activity model)

2. **0002_add_soft_delete.py** - Adds soft delete fields (if not in initial):
   - `is_deleted` boolean field
   - `deleted_at` timestamp field

3. **0003_add_metadata_fields.py** - Adds metadata JSON fields (if not in initial):
   - `metadata` JSONField for custom fields

## Migration Requirements

All migrations MUST:

1. **Include tenant_id**: All tenant-scoped tables must have `tenant_id` column (UUIDField) with proper indexes
2. **Create indexes**: All foreign keys and frequently queried fields must have indexes
3. **Be idempotent**: Migrations must handle concurrent execution safely
4. **Follow Expand/Contract pattern**: See migration best practices
5. **Never modify existing migrations**: Create new migrations for changes

## Critical Tables

The following tables are critical for module operation:
- `crm_leads` - Lead tracking
- `crm_accounts` - Account management
- `crm_contacts` - Contact management
- `crm_opportunities` - Sales pipeline
- `crm_activities` - Activity tracking

## Indexes

All migrations create comprehensive indexes on:
- `tenant_id` (for Row-Level Multitenancy filtering)
- Foreign keys (for join performance)
- Frequently queried fields (`status`, `stage`, `owner_id`, `created_at`)
- Composite indexes for common query patterns (e.g., `tenant_id + status`)

## Verification

After migrations are created, verify:

```bash
# Check migration files
ls -la backend/src/modules/crm/migrations/

# Check tables created
python manage.py dbshell
\dt crm_*

# Verify indexes
\d crm_leads
```
