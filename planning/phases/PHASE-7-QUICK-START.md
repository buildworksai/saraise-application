# Phase 7 Quick Start Guide

**Status:** 🟢 READY FOR EXECUTION  
**Start Date:** [To be filled]  
**Duration:** 5 weeks

---

## Prerequisites Check

Before starting, verify:

```bash
cd /Users/raghunathchava/Code/saraise

# 1. Phase 6 complete
ls backend/src/modules/ai_agent_management/manifest.yaml
# Should exist

# 2. Template module operational
pytest backend/src/modules/ai_agent_management/tests/ -v
# Should pass

# 3. Pre-commit hooks installed
pre-commit run --all-files
# Should pass

# 4. Frontend types generated
ls frontend/src/types/api.ts
# Should exist
```

---

## Week 1-2: Platform Management Module

### Day 1: Specification Review

```bash
# Read module specification
cat docs/modules/01-foundation/platform-management/README.md
cat docs/modules/01-foundation/platform-management/API.md

# Extract key information:
# - Data models: PlatformSetting, FeatureFlag, SystemHealth, PlatformAuditEvent
# - API endpoints: /api/v1/platform/settings/, /api/v1/platform/feature-flags/, etc.
# - Business rules: Settings can be platform-wide or tenant-specific
```

### Day 2-3: Backend Implementation

```bash
# Create module structure
cd backend/src/modules
mkdir -p platform_management/{migrations,tests}
touch platform_management/{__init__.py,manifest.yaml,models.py,serializers.py,api.py,urls.py,services.py,permissions.py,health.py}
touch platform_management/tests/{__init__.py,test_models.py,test_api.py,test_services.py,test_isolation.py}

# Follow detailed implementation in phase-7-foundation-part1.md
# Copy structure from ai_agent_management as template
```

### Day 3-4: Backend Tests

```bash
# Write tests following pattern
# See phase-7-foundation-part1.md for test examples

# Run tests with coverage
cd backend
pytest src/modules/platform_management/tests/ -v --cov=src/modules/platform_management --cov-report=html --cov-fail-under=90

# Verify ≥90% coverage
open htmlcov/index.html
```

### Day 4-5: Frontend Implementation

```bash
# Create frontend structure
cd frontend/src/modules
mkdir -p platform_management/{pages,components,services,types,tests}

# Implement following pattern from ai_agent_management frontend
# See phase-7-foundation-part1.md for TypeScript examples
```

### Day 5: Validation & Completion

```bash
# Full validation
cd /Users/raghunathchava/Code/saraise

# Pre-commit hooks
pre-commit run --all-files

# Backend quality
cd backend
black src/modules/platform_management
flake8 src/modules/platform_management --max-line-length=120
mypy src/modules/platform_management

# Frontend quality
cd ../frontend
npx tsc --noEmit
npx eslint src/modules/platform_management --max-warnings 0

# Generate schema and types
cd ../backend
python manage.py spectacular --file schema.yml
cd ../frontend
npm run generate-types

# Create completion report
cat > reports/platform-management-complete-$(date +%Y-%m-%d).md << 'EOF'
# Platform Management Module - Completion Report

**Date:** $(date +%Y-%m-%d)
**Status:** ✅ COMPLETE

## Deliverables
- [x] Backend: Models, Serializers, ViewSets, Services, Tests
- [x] Frontend: Types, Services, Pages, Routes
- [x] Coverage: ≥90%
- [x] Quality Gates: All passing

## Next Module
Tenant Management (Week 2-3)
EOF
```

---

## Week 2-3: Tenant Management Module

Follow same pattern as Platform Management:
1. Day 1: Read spec from `docs/modules/01-foundation/tenant-management/`
2. Day 2-3: Backend implementation
3. Day 3-4: Backend tests
4. Day 4-5: Frontend implementation
5. Day 5: Validation & completion report

---

## Week 3-5: Security & Access Control Module

**Note:** Extra time allocated (10-12 days) due to Policy Engine integration complexity.

Follow same pattern but allocate extra time for:
- Policy Engine integration testing
- Authorization decorator implementation
- Security audit

---

## Phase 7 Completion Checklist

- [ ] Platform Management module operational
- [ ] Tenant Management module operational
- [ ] Security & Access Control module operational
- [ ] All modules have ≥90% test coverage
- [ ] All pre-commit hooks passing
- [ ] Tenant isolation verified for all modules
- [ ] Policy Engine integration verified
- [ ] OpenAPI schema generated
- [ ] TypeScript types generated
- [ ] Completion reports created for all 3 modules

---

## Validation Command Sequence

```bash
# Final phase validation
cd /Users/raghunathchava/Code/saraise

# 1. Pre-commit
pre-commit run --all-files

# 2. Backend tests
cd backend
pytest src/modules/platform_management/tests/ -v --cov --cov-fail-under=90
pytest src/modules/tenant_management/tests/ -v --cov --cov-fail-under=90
pytest src/modules/security_access_control/tests/ -v --cov --cov-fail-under=90

# 3. Frontend checks
cd ../frontend
npx tsc --noEmit
npx eslint src/modules --max-warnings 0
npm test

# 4. Integration tests
cd ../backend
pytest tests/integration/test_platform_tenant_security.py -v

# 5. Generate schema
python manage.py spectacular --file schema.yml

# 6. Generate types
cd ../frontend
npm run generate-types
```

---

## Troubleshooting

### Issue: Test coverage below 90%

**Solution:**
```bash
# Check coverage report
cd backend
pytest src/modules/[module]/tests/ --cov=src/modules/[module] --cov-report=html
open htmlcov/index.html

# Add tests for uncovered lines
# Focus on edge cases and error scenarios
```

### Issue: Tenant isolation test failing

**Solution:**
```bash
# Verify tenant_id filtering in ViewSet
grep -A 5 "def get_queryset" backend/src/modules/[module]/api.py

# Should have:
# return Model.objects.filter(tenant_id=self.request.user.tenant_id)
```

### Issue: Pre-commit hooks failing

**Solution:**
```bash
# Run individual checks
cd backend
black src/modules/[module] --check
flake8 src/modules/[module] --max-line-length=120
mypy src/modules/[module]

cd ../frontend
npx tsc --noEmit
npx eslint src/modules/[module] --max-warnings 0
```

---

## Reference Documents

- **Phase Document:** `planning/phases/phase-7-foundation-part1.md`
- **Template Module:** `backend/src/modules/ai_agent_management/`
- **Architecture:** `docs/architecture/`
- **Module Specs:** `docs/modules/01-foundation/`
- **Agent Rules:** `.agents/rules/`

---

**Ready to begin?** Start with Day 1 of Platform Management module!

