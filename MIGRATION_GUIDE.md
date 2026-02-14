# Migration Guide for 17 New Modules

**Date:** 2026-01-10  
**Status:** Ready for Migration Generation

## Overview

17 new modules have been fully implemented and are ready for migration generation:

1. `accounting_finance`
2. `inventory_management`
3. `human_resources`
4. `purchase_management`
5. `sales_management`
6. `project_management`
7. `master_data_management`
8. `multi_company`
9. `asset_management`
10. `bank_reconciliation`
11. `budget_management`
12. `business_intelligence`
13. `communication_hub`
14. `compliance_management`
15. `compliance_risk_management`
16. `email_marketing`
17. `fixed_assets`

## Pre-Migration Validation

✅ **All modules pass validation:**
- All required files present (models.py, api.py, urls.py, manifest.yaml, health.py)
- All test files present (test_isolation.py, test_models.py, test_api.py, test_services.py)
- All models have TenantBaseModel with tenant_id UUIDField
- All models have Meta classes with db_table
- All Python files compile without syntax errors
- All modules registered in INSTALLED_APPS
- All modules registered in urls.py

## Migration Generation

### Option 1: Docker Environment (Recommended)

```bash
cd /Users/raghunathchava/Code/saraise/saraise-application

# Ensure Docker network exists
docker network create saraise-network 2>/dev/null || true

# Start services
docker-compose -f docker-compose.dev.yml up -d postgres redis

# Wait for database
sleep 10

# Generate migrations for all new modules
docker-compose -f docker-compose.dev.yml exec backend python manage.py makemigrations \
    accounting_finance \
    inventory_management \
    human_resources \
    purchase_management \
    sales_management \
    project_management \
    master_data_management \
    multi_company \
    asset_management \
    bank_reconciliation \
    budget_management \
    business_intelligence \
    communication_hub \
    compliance_management \
    compliance_risk_management \
    email_marketing \
    fixed_assets

# Or use the convenience script
docker-compose -f docker-compose.dev.yml exec backend bash scripts/generate_migrations.sh
```

### Option 2: Local Virtual Environment

```bash
cd /Users/raghunathchava/Code/saraise/saraise-application/backend

# Activate virtual environment
source venv/bin/activate  # or: python3 -m venv venv && source venv/bin/activate

# Install dependencies
pip install -e .[dev]

# Generate migrations
python manage.py makemigrations \
    accounting_finance \
    inventory_management \
    human_resources \
    purchase_management \
    sales_management \
    project_management \
    master_data_management \
    multi_company \
    asset_management \
    bank_reconciliation \
    budget_management \
    business_intelligence \
    communication_hub \
    compliance_management \
    compliance_risk_management \
    email_marketing \
    fixed_assets
```

## Expected Migration Files

Each module should generate a `0001_initial.py` migration file in:
```
backend/src/modules/{module_name}/migrations/0001_initial.py
```

## Verification Steps

After generating migrations:

1. **Check migration files exist:**
   ```bash
   ls -la backend/src/modules/*/migrations/0001_initial.py
   ```

2. **Review migration structure:**
   - Each migration should create tables with `tenant_id UUIDField`
   - Each migration should include proper indexes
   - Each migration should include `db_table` specification

3. **Run migrations:**
   ```bash
   # Docker
   docker-compose -f docker-compose.dev.yml exec backend python manage.py migrate

   # Local
   python manage.py migrate
   ```

4. **Verify tables created:**
   ```bash
   # Docker
   docker-compose -f docker-compose.dev.yml exec postgres psql -U postgres -d saraise -c "\dt" | grep -E "(accounting|inventory|human|purchase|sales|project|master|multi|asset|bank|budget|business|communication|compliance|email|fixed)"

   # Local
   psql -U postgres -d saraise -c "\dt" | grep -E "(accounting|inventory|human|purchase|sales|project|master|multi|asset|bank|budget|business|communication|compliance|email|fixed)"
   ```

## Post-Migration Testing

After migrations complete:

1. **Run module tests:**
   ```bash
   # Docker
   docker-compose -f docker-compose.dev.yml exec backend pytest \
       src/modules/accounting_finance/tests/ \
       src/modules/inventory_management/tests/ \
       src/modules/human_resources/tests/ \
       -v --cov=src --cov-fail-under=90

   # Local
   pytest src/modules/accounting_finance/tests/ \
       src/modules/inventory_management/tests/ \
       src/modules/human_resources/tests/ \
       -v --cov=src --cov-fail-under=90
   ```

2. **Run tenant isolation tests:**
   ```bash
   pytest src/modules/*/tests/test_isolation.py -v
   ```

3. **Run full test suite:**
   ```bash
   pytest tests/ -v --cov=src --cov-fail-under=90
   ```

## Troubleshooting

### Migration Errors

**Error: "No changes detected"**
- Verify module is in INSTALLED_APPS
- Check models.py has non-abstract models
- Verify models inherit from TenantBaseModel or models.Model

**Error: "Circular dependency"**
- Check for circular ForeignKey relationships
- Verify imports are correct

**Error: "Field type not recognized"**
- Verify all field types are valid Django field types
- Check for typos in field definitions

### Database Connection Issues

**Error: "Connection refused"**
- Verify PostgreSQL is running: `docker-compose ps postgres`
- Check DATABASE_URL in environment
- Verify network connectivity

## Next Steps After Migrations

1. ✅ Migrations generated
2. ⏳ Run migrations: `python manage.py migrate`
3. ⏳ Run tests: `pytest tests/ -v --cov=src --cov-fail-under=90`
4. ⏳ Run pre-commit hooks: `pre-commit run --all-files`
5. ⏳ Verify API endpoints: Test each module's health endpoint

## Module Registration Status

✅ **URLs Registered:** All 17 modules in `saraise_backend/urls.py`  
✅ **INSTALLED_APPS:** All 17 modules in `saraise_backend/settings.py`  
✅ **Module Structure:** All modules have complete structure  
✅ **Tests:** All modules have test_isolation.py with real tests  
✅ **Validation:** All modules pass pre-migration validation  

---

**Ready to generate migrations!** Run the commands above when Django environment is available.
