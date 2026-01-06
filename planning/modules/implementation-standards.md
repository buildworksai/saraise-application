# Module Implementation Standards (NON-NEGOTIABLE)

**Authority**: STRICT COMPLIANCE REQUIRED
**Violations**: IMMEDIATE REJECTION
**Review**: Every commit, every module, every phase

---

## Architectural Standards (FROZEN)

### 1. Django Framework ONLY ✅

**REQUIRED**:
```python
# Django ORM models
from django.db import models

class Entity(models.Model):
    tenant_id = models.UUIDField(db_index=True)  # REQUIRED
    # ... fields
```

**FORBIDDEN**:
```python
# ❌ SQLAlchemy (FastAPI pattern)
from sqlalchemy import Column, String
class Entity(Base):
    __tablename__ = "entities"
```

**Risk Mitigation**:
- Pre-commit hook enforces Django imports
- Code review rejects non-Django patterns
- CI fails on SQLAlchemy imports

---

### 2. Row-Level Multitenancy ✅

**REQUIRED**:
```python
# All tenant-scoped models MUST have tenant_id
class Customer(models.Model):
    tenant_id = models.UUIDField(db_index=True)  # MANDATORY
    name = models.CharField(max_length=255)

    class Meta:
        db_table = 'crm_customers'
        unique_together = [['tenant_id', 'email']]  # Tenant isolation
```

**REQUIRED**:
```python
# All queries MUST filter by tenant_id
def get_queryset(self):
    return Customer.objects.filter(
        tenant_id=self.request.user.tenant_id  # MANDATORY filtering
    )
```

**FORBIDDEN**:
```python
# ❌ No tenant_id filtering (data leakage!)
def get_queryset(self):
    return Customer.objects.all()  # SECURITY VIOLATION
```

**Risk Mitigation**:
- Pre-commit hook checks for tenant_id in models
- Code review enforces filtering in all ViewSets
- Integration tests verify isolation
- Security audit scans for missing filters

---

### 3. Session Authentication ONLY ✅

**REQUIRED**:
```python
# Session-based authentication
from django.contrib.sessions.middleware import SessionMiddleware

# Identity-only in session (NO authorization state)
session_data = {
    "user_id": user.id,
    "tenant_id": user.tenant_id,
    # NO roles, permissions, or authorization state
}
```

**FORBIDDEN**:
```python
# ❌ JWT tokens for interactive users
from rest_framework_simplejwt.tokens import RefreshToken

# ❌ Caching roles in session
session_data = {
    "user_id": user.id,
    "roles": ["admin", "user"]  # VIOLATION - no role caching
}
```

**Risk Mitigation**:
- Architecture spec enforces session-only auth
- Code review rejects JWT for interactive users
- Security audit checks session structure

---

### 4. Policy Engine Authorization ✅

**REQUIRED**:
```python
# Runtime authorization via Policy Engine
from backend.src.core.policy_engine import PolicyEngine

def create(self, request):
    # Evaluate permission per-request (NOT cached)
    decision = policy_engine.evaluate(
        user_id=request.user.id,
        tenant_id=request.user.tenant_id,
        action="crm.customers:create",
        resource={"type": "customer"},
        context={}
    )

    if decision.effect == Effect.DENY:
        raise PermissionDenied(decision.reason)

    # Proceed with creation...
```

**FORBIDDEN**:
```python
# ❌ Checking cached roles from session
if "admin" not in request.session.get("roles", []):
    raise PermissionDenied()  # VIOLATION - session should NOT have roles
```

**Risk Mitigation**:
- Policy Engine integration tests
- Code review enforces policy evaluation
- No role caching allowed in session structure

---

### 5. manifest.yaml REQUIRED ✅

**REQUIRED**:
```yaml
# backend/src/modules/crm/manifest.yaml
name: crm
version: 1.0.0
description: Customer Relationship Management
type: core
lifecycle: managed
dependencies:
  - core-identity >=1.0
  - workflow-automation >=1.0
permissions:
  - crm.customers:create
  - crm.customers:read
  - crm.customers:update
  - crm.customers:delete
sod_actions:
  - crm.customers:create
  - crm.customers:approve
search_indexes:
  - crm_customers
ai_tools:
  - create_customer_tool
```

**FORBIDDEN**:
```python
# ❌ Python dict MODULE_MANIFEST in __init__.py
MODULE_MANIFEST = {
    "name": "crm",
    "version": "1.0.0"
}  # VIOLATION - must be YAML file
```

**Risk Mitigation**:
- Pre-commit hook checks for manifest.yaml
- Module loader rejects modules without manifest
- CI validates YAML syntax

---

### 6. Test Coverage ≥90% ✅

**REQUIRED**:
```bash
# Run tests with coverage
cd backend
pytest src/modules/crm/tests/ -v --cov=src/modules/crm --cov-report=html

# Coverage report MUST show ≥90%
# TOTAL coverage: 90% (enforced by CI)
```

**FORBIDDEN**:
```python
# ❌ Skipping tests
@pytest.mark.skip("TODO: write tests")
def test_create_customer():
    pass  # VIOLATION - all tests must be implemented
```

**Risk Mitigation**:
- CI fails build if coverage <90%
- Pre-commit hook runs pytest
- Code review checks test completeness

---

### 7. Pre-Commit Hooks PASS ✅

**REQUIRED**:
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# All commits MUST pass these checks:
# ✅ TypeScript: tsc --noEmit (0 errors)
# ✅ ESLint: --max-warnings 0
# ✅ Black: Python formatting
# ✅ Flake8: Python linting
# ✅ MyPy: Python type checking (≤4540 errors baseline)
# ✅ File quality: trailing whitespace, YAML validation
```

**FORBIDDEN**:
```bash
# ❌ Bypassing pre-commit hooks
git commit --no-verify  # VIOLATION - never bypass hooks
```

**Risk Mitigation**:
- Pre-commit hooks enforced on all commits
- CI runs same checks (double verification)
- Code review rejects bypass attempts

---

### 8. Template Pattern ✅

**REQUIRED**:
```
# Use ai_agent_management as template
backend/src/modules/new_module/
├── __init__.py
├── manifest.yaml           # Module contract
├── models.py               # Django ORM models
├── serializers.py          # DRF serializers
├── api.py                  # DRF ViewSets
├── urls.py                 # URL routing
├── services.py             # Business logic
├── permissions.py          # Permission declarations
├── migrations/             # Django migrations
└── tests/                  # ≥90% coverage
    ├── test_api.py
    ├── test_services.py
    └── test_models.py
```

**FORBIDDEN**:
```
# ❌ Deviating from template structure
backend/src/modules/new_module/
├── routes.py              # VIOLATION - use api.py not routes.py
├── schemas.py             # VIOLATION - use serializers.py not schemas.py
└── database.py            # VIOLATION - use models.py not database.py
```

**Risk Mitigation**:
- Module generation script creates template structure
- Code review enforces template adherence
- Architecture docs specify template

---

## Quality Standards (ENFORCED)

### Code Quality

**TypeScript**:
```bash
# ✅ MUST pass with 0 errors
cd frontend
npx tsc --noEmit

# ✅ MUST pass with 0 warnings
npx eslint src --ext .ts,.tsx --max-warnings 0
```

**Python**:
```bash
# ✅ MUST pass Black formatting
cd backend
black src tests

# ✅ MUST pass Flake8 linting
flake8 src tests --max-line-length=120

# ✅ MUST not exceed MyPy error baseline
mypy src --exclude "/tests/"  # ≤4540 errors
```

**Risk Mitigation**:
- Pre-commit hooks enforce all checks
- CI fails build on violations
- Zero tolerance policy

---

### Testing Standards

**Backend Tests**:
```python
# Django test structure
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

class CustomerAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Setup tenant and user with session

    def test_create_customer_success(self):
        """Test: Create customer with valid data"""
        data = {"name": "Acme Corp", "email": "info@acme.com"}
        response = self.client.post('/api/v1/crm/customers', data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_customer_duplicate_email(self):
        """Test: Duplicate email validation"""
        # ... test duplicate handling

    def test_tenant_isolation(self):
        """Test: User cannot see other tenant's customers"""
        # ... test tenant isolation
```

**Frontend Tests**:
```typescript
// Vitest + React Testing Library
import { render, screen } from '@testing-library/react';
import { CustomerList } from './CustomerList';

describe('CustomerList', () => {
  it('renders customer list', async () => {
    render(<CustomerList />);
    expect(screen.getByText('Customers')).toBeInTheDocument();
  });

  it('displays customers from API', async () => {
    // ... test API integration
  });
});
```

**Risk Mitigation**:
- ≥90% coverage enforced by CI
- Test fixtures in conftest.py (backend) and test-utils.tsx (frontend)
- Integration tests verify end-to-end functionality

---

## Security Standards (CRITICAL)

### 1. No Auth in Modules ✅

**FORBIDDEN**:
```python
# ❌ Module implementing authentication
@router.post("/login")
def login(username: str, password: str):
    # VIOLATION - authentication is platform-level only
    pass

# ❌ Module managing sessions
def create_session(user):
    # VIOLATION - session management is platform-level only
    pass
```

**REQUIRED**:
```python
# ✅ Module declares permissions only
# backend/src/modules/crm/permissions.py

PERMISSIONS = [
    "crm.customers:create",
    "crm.customers:read",
    "crm.customers:update",
    "crm.customers:delete"
]

# Authorization checked by Policy Engine (platform-level)
```

**Risk Mitigation**:
- Code review rejects auth implementation in modules
- Security audit scans for auth code
- Architecture spec explicitly forbids module-level auth

---

### 2. Tenant Isolation ✅

**REQUIRED**:
```python
# Security test: Verify tenant isolation
def test_tenant_isolation(self):
    """Verify user cannot access other tenant's data"""
    # Create customer for tenant A
    tenant_a_customer = Customer.objects.create(
        tenant_id=self.tenant_a.id,
        name="Tenant A Customer"
    )

    # Login as tenant B user
    self.client.force_authenticate(user=self.tenant_b_user)

    # Attempt to access tenant A's customer
    response = self.client.get(f'/api/v1/crm/customers/{tenant_a_customer.id}')

    # MUST return 404 (not 403 - hide existence)
    self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
```

**Risk Mitigation**:
- Integration tests verify isolation for every module
- Security audit scans for missing tenant filters
- Penetration testing validates isolation

---

### 3. Immutable Audit Logs ✅

**REQUIRED**:
```python
# Audit logs are write-only
class AuditLog(models.Model):
    # No update/delete allowed
    class Meta:
        permissions = [
            ("view_auditlog", "Can view audit logs"),
            # NO update/delete permissions
        ]
```

**FORBIDDEN**:
```python
# ❌ Modifying audit logs
audit_log.action = "modified"  # VIOLATION
audit_log.save()

# ❌ Deleting audit logs
audit_log.delete()  # VIOLATION
```

**Risk Mitigation**:
- Database constraints prevent updates/deletes
- Audit log models have no update/delete methods
- Security audit verifies immutability

---

## Validation Gates (PER MODULE)

### Gate 1: Code Review ✅

**Checklist**:
- [ ] Django patterns used (no FastAPI/SQLAlchemy)
- [ ] tenant_id in all models
- [ ] tenant_id filtering in all queries
- [ ] Session authentication (no JWT)
- [ ] Policy Engine authorization (no cached roles)
- [ ] manifest.yaml exists and valid
- [ ] Template structure followed
- [ ] No auth implementation in module

### Gate 2: Quality Checks ✅

**Checklist**:
- [ ] TypeScript: 0 errors (tsc --noEmit)
- [ ] ESLint: 0 warnings
- [ ] Black: Python formatted
- [ ] Flake8: Python linted
- [ ] MyPy: ≤baseline errors
- [ ] Pre-commit hooks pass

### Gate 3: Testing ✅

**Checklist**:
- [ ] Test coverage ≥90%
- [ ] All tests passing
- [ ] Tenant isolation tests pass
- [ ] Authorization tests pass
- [ ] Integration tests pass

### Gate 4: Security Audit ✅

**Checklist**:
- [ ] No auth implementation in module
- [ ] Tenant isolation verified
- [ ] Audit logs immutable
- [ ] No SQL injection vulnerabilities
- [ ] No XSS vulnerabilities
- [ ] OWASP Top 10 compliance

---

## Risk Mitigation Summary

### Risk Level: 5% (Implementation Complexity Only)

**Mitigations**:
1. ✅ **Template pattern** - ai_agent_management proven
2. ✅ **Pre-commit hooks** - Catch issues before commit
3. ✅ **CI enforcement** - Build fails on violations
4. ✅ **Code review** - Human verification
5. ✅ **Integration tests** - End-to-end validation
6. ✅ **Security audit** - Penetration testing
7. ✅ **Quality gates** - 4 gates per module

**Confidence**: 95%

---

## Document Status

**Status**: AUTHORITATIVE STANDARDS
**Authority**: NON-NEGOTIABLE
**Last Updated**: 2026-01-05
**Next Review**: After Phase 7 completion

---
