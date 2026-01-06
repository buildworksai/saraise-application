# Phase 7: Foundation Modules Implementation Plan

**Status**: READY FOR EXECUTION
**Timeline**: 10-12 weeks
**Modules**: 22 Foundation modules
**Prerequisites**: ✅ Phase 6 complete (ai_agent_management operational)

---

## Objectives

### Primary Goal
Implement 22 Foundation modules that enable multi-tenancy, AI, workflow, security, and platform operations

### Success Criteria
- ✅ All 22 Foundation modules operational (backend + frontend + tests)
- ✅ ≥90% test coverage per module
- ✅ All pre-commit hooks passing
- ✅ Template pattern proven across diverse modules
- ✅ Platform ready for Phase 8 (Core modules)

---

## Module Priority Order

### Tier 1: Critical Infrastructure (P0) - Implement First

**Week 1-2: Platform Management**
- **Priority**: P0 (Highest)
- **Dependencies**: None
- **Spec**: `docs/modules/01-foundation/platform-management/`
- **Purpose**: System admin, health monitoring, configuration
- **Timeline**: 5-7 days
- **Risk**: LOW (well-defined, straightforward)

**Week 2-3: Tenant Management**
- **Priority**: P0
- **Dependencies**: Platform Management
- **Spec**: `docs/modules/01-foundation/tenant-management/`
- **Purpose**: Multi-tenant lifecycle, quotas, isolation
- **Timeline**: 5-7 days
- **Risk**: LOW (clear requirements)

**Week 3-5: Security & Access Control**
- **Priority**: P0
- **Dependencies**: Tenant Management
- **Spec**: `docs/modules/01-foundation/security-access-control/`
- **Purpose**: RBAC, Policy Engine, permissions
- **Timeline**: 7-10 days (complex - Policy Engine integration)
- **Risk**: MEDIUM (Policy Engine runtime evaluation critical)

---

### Tier 2: Platform Services (P1) - Implement Next

**Week 5-6: Workflow Automation**
- **Priority**: P1
- **Dependencies**: Security & Access Control
- **Spec**: `docs/modules/01-foundation/workflow-automation/`
- **Purpose**: Visual workflow builder, state machine
- **Timeline**: 5-7 days
- **Risk**: LOW (clear workflow patterns)

**Week 6-7: Metadata Modeling**
- **Priority**: P1
- **Dependencies**: Security & Access Control
- **Spec**: `docs/modules/01-foundation/metadata-modeling/`
- **Purpose**: Custom fields, dynamic schemas
- **Timeline**: 5-7 days
- **Risk**: LOW (well-documented)

**Week 7-8: Document Management (DMS)**
- **Priority**: P1
- **Dependencies**: Security, Metadata Modeling
- **Spec**: `docs/modules/01-foundation/dms/`
- **Purpose**: File storage, versioning, access control
- **Timeline**: 5-7 days
- **Risk**: LOW (standard patterns)

**Week 8-9: Integration Platform**
- **Priority**: P1
- **Dependencies**: Security, Workflow
- **Spec**: `docs/modules/01-foundation/integration-platform/`
- **Purpose**: REST integrations, webhooks, transformations
- **Timeline**: 5-7 days
- **Risk**: LOW (HTTP client patterns)

---

### Tier 3: Advanced Features (P2) - Implement Last

**Week 9-10: Performance Monitoring**
- **Priority**: P2
- **Dependencies**: Platform Management
- **Spec**: `docs/modules/01-foundation/performance-monitoring/`
- **Purpose**: Metrics, alerts, dashboards
- **Timeline**: 5-7 days
- **Risk**: LOW (monitoring patterns)

**Week 10: API Management**
- **Priority**: P2
- **Dependencies**: Security
- **Spec**: `docs/modules/01-foundation/api-management/`
- **Purpose**: GraphQL, REST gateway, rate limiting
- **Timeline**: 3-5 days
- **Risk**: LOW (gateway patterns)

---

## Complete Module List (22 Modules)

### Tier 1: Critical (P0) - 3 modules
1. ✅ Platform Management (Week 1-2)
2. ✅ Tenant Management (Week 2-3)
3. ✅ Security & Access Control (Week 3-5)

### Tier 2: Platform Services (P1) - 11 modules
4. ✅ Workflow Automation (Week 5-6)
5. ✅ Metadata Modeling (Week 6-7)
6. ✅ Document Management (DMS) (Week 7-8)
7. ✅ Integration Platform (Week 8-9)
8. Billing & Subscriptions (Week 9-10)
9. Data Migration Framework (Week 10-11)
10. Customization Framework (Week 11-12)
11. Localization & Internationalization (Week 12)
12. AI Provider Configuration (Week 12)
13. AI Agent Management (✅ COMPLETE - Phase 6)
14. Document Intelligence (Week 13)

### Tier 3: Advanced (P2) - 8 modules
15. Performance Monitoring (Week 9-10)
16. API Management (Week 10)
17. Backup & Disaster Recovery (Week 13)
18. Process Mining & Analytics (Week 13-14)
19. Automation Orchestration (Week 14)
20. Blockchain Traceability (Week 14)
21. Backup & Recovery (Week 14-15)
22. Regional Compliance (Week 15)

**Note**: Weeks 10-15 modules can run in parallel if resources available

---

## Per-Module Implementation Process

### Day 1: Planning & Specification Review

**Tasks**:
1. Read module spec from `docs/modules/01-foundation/[module-name]/`
   - README.md - Overview, features, data models
   - API.md - REST endpoints, schemas
   - CUSTOMIZATION.md - Custom fields
   - USER-GUIDE.md - End-user docs

2. Extract implementation requirements:
   - Data models (entities, fields, relationships)
   - Business rules (validation, workflows)
   - API contracts (endpoints, request/response)
   - Test scenarios (happy path, edge cases)

3. Create implementation checklist:
   ```markdown
   ## [Module Name] Implementation Checklist

   ### Backend (Day 2-3)
   - [ ] Models created (Django ORM with tenant_id)
   - [ ] Migrations created
   - [ ] Serializers created (DRF)
   - [ ] ViewSets created (DRF)
   - [ ] Services created (business logic)
   - [ ] URLs configured

   ### Tests (Day 3-4)
   - [ ] API tests written
   - [ ] Service tests written
   - [ ] Tenant isolation tests written
   - [ ] Coverage ≥90%

   ### Frontend (Day 4-5)
   - [ ] Components created (React)
   - [ ] API service created
   - [ ] TanStack Query integration
   - [ ] UI tested

   ### Validation Gates
   - [ ] Pre-commit hooks pass
   - [ ] All tests pass
   - [ ] Code review approved
   - [ ] Security audit pass
   ```

---

### Day 2-3: Backend Implementation

**Step 1: Create module structure**
```bash
cd backend/src/modules
mkdir -p [module-name]/{migrations,tests}
touch [module-name]/{__init__.py,manifest.yaml,models.py,serializers.py,api.py,urls.py,services.py,permissions.py}
touch [module-name]/tests/{__init__.py,test_api.py,test_services.py}
```

**Step 2: Implement Django models**
```python
# backend/src/modules/[module-name]/models.py

from django.db import models
import uuid

class Entity(models.Model):
    """
    Entity description from spec
    Implements data model from docs/modules/01-foundation/[module-name]/README.md
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)  # REQUIRED for multitenancy

    # Fields from spec
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Active'), ('inactive', 'Inactive')],
        default='active'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = '[module]_entity'
        unique_together = [['tenant_id', 'name']]  # From spec constraints
        indexes = [
            models.Index(fields=['tenant_id', 'status']),
        ]

    def __str__(self):
        return self.name
```

**Step 3: Create migrations**
```bash
cd backend
python manage.py makemigrations [module-name]
python manage.py migrate
```

**Step 4: Implement DRF serializers**
```python
# backend/src/modules/[module-name]/serializers.py

from rest_framework import serializers
from .models import Entity

class EntitySerializer(serializers.ModelSerializer):
    """Serializer for Entity API (from spec API.md)"""

    class Meta:
        model = Entity
        fields = ['id', 'tenant_id', 'name', 'status', 'created_at', 'updated_at']
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate_name(self, value):
        """Validation rules from spec"""
        if not value or len(value) < 3:
            raise serializers.ValidationError("Name must be at least 3 characters")
        return value
```

**Step 5: Implement DRF ViewSets**
```python
# backend/src/modules/[module-name]/api.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Entity
from .serializers import EntitySerializer

class EntityViewSet(viewsets.ModelViewSet):
    """
    API endpoints for Entity (from spec API.md)
    """
    serializer_class = EntitySerializer

    def get_queryset(self):
        """Filter by tenant (REQUIRED for multitenancy)"""
        return Entity.objects.filter(
            tenant_id=self.request.user.tenant_id  # MANDATORY
        )

    def perform_create(self, serializer):
        """Set tenant_id automatically"""
        serializer.save(tenant_id=self.request.user.tenant_id)
```

**Step 6: Configure URLs**
```python
# backend/src/modules/[module-name]/urls.py

from rest_framework.routers import DefaultRouter
from .api import EntityViewSet

router = DefaultRouter()
router.register(r'entities', EntityViewSet, basename='entity')
urlpatterns = router.urls
```

**Step 7: Create manifest.yaml**
```yaml
# backend/src/modules/[module-name]/manifest.yaml

name: [module-name]
version: 1.0.0
description: Module description from spec
type: foundation
lifecycle: platform
dependencies:
  - platform-management >=1.0
permissions:
  - [module].entity:create
  - [module].entity:read
  - [module].entity:update
  - [module].entity:delete
sod_actions:
  - [module].entity:create
  - [module].entity:approve
search_indexes:
  - [module]_entities
ai_tools:
  - [module]_entity_tool
```

---

### Day 3-4: Backend Tests

**Step 1: API tests**
```python
# backend/src/modules/[module-name]/tests/test_api.py

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from ..models import Entity

class EntityAPITestCase(TestCase):
    """Test cases from spec"""

    def setUp(self):
        self.client = APIClient()
        # Setup authenticated user with session
        self.user = create_test_user(tenant_id="test-tenant")
        self.client.force_authenticate(user=self.user)

    def test_create_entity_success(self):
        """Test: Create entity with valid data (from spec)"""
        data = {"name": "Test Entity", "status": "active"}
        response = self.client.post('/api/v1/[module]/entities', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Test Entity")
        self.assertEqual(response.data['tenant_id'], self.user.tenant_id)

    def test_create_entity_validation_error(self):
        """Test: Validation error for short name"""
        data = {"name": "AB"}  # Too short
        response = self.client.post('/api/v1/[module]/entities', data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Name must be at least 3 characters", str(response.data))

    def test_tenant_isolation(self):
        """Test: User cannot access other tenant's entities"""
        # Create entity for different tenant
        other_entity = Entity.objects.create(
            tenant_id="other-tenant",
            name="Other Entity"
        )

        # Try to access
        response = self.client.get(f'/api/v1/[module]/entities/{other_entity.id}')

        # Must return 404 (not 403 - hide existence)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_entities_filtered_by_tenant(self):
        """Test: List only returns current tenant's entities"""
        # Create entities for current tenant
        Entity.objects.create(tenant_id=self.user.tenant_id, name="Entity 1")
        Entity.objects.create(tenant_id=self.user.tenant_id, name="Entity 2")

        # Create entity for other tenant (should not appear)
        Entity.objects.create(tenant_id="other-tenant", name="Other Entity")

        response = self.client.get('/api/v1/[module]/entities')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)  # Only current tenant's
```

**Step 2: Run tests with coverage**
```bash
cd backend
pytest src/modules/[module-name]/tests/ -v --cov=src/modules/[module-name] --cov-report=html

# Verify ≥90% coverage
open htmlcov/index.html
```

---

### Day 4-5: Frontend Implementation

**Step 1: Create frontend structure**
```bash
cd frontend/src/modules
mkdir -p [module-name]/{pages,components,services,types}
touch [module-name]/{index.ts,routes.tsx}
```

**Step 2: API service**
```typescript
// frontend/src/modules/[module-name]/services/[module]-service.ts

import { apiClient } from '@/services/api-client';

export interface Entity {
  id: string;
  tenant_id: string;
  name: string;
  status: 'active' | 'inactive';
  created_at: string;
  updated_at: string;
}

export class ModuleService {
  async list(): Promise<Entity[]> {
    return apiClient.get<Entity[]>(`/api/v1/[module]/entities`);
  }

  async create(data: Partial<Entity>): Promise<Entity> {
    return apiClient.post<Entity>(`/api/v1/[module]/entities`, data);
  }

  async get(id: string): Promise<Entity> {
    return apiClient.get<Entity>(`/api/v1/[module]/entities/${id}`);
  }

  async update(id: string, data: Partial<Entity>): Promise<Entity> {
    return apiClient.put<Entity>(`/api/v1/[module]/entities/${id}`, data);
  }

  async delete(id: string): Promise<void> {
    return apiClient.delete(`/api/v1/[module]/entities/${id}`);
  }
}

export const moduleService = new ModuleService();
```

**Step 3: React components**
```typescript
// frontend/src/modules/[module-name]/pages/EntityList.tsx

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { moduleService } from '../services/[module]-service';

export function EntityList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['entities'],
    queryFn: () => moduleService.list()
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <h1>Entities</h1>
      <ul>
        {data?.map(entity => (
          <li key={entity.id}>{entity.name}</li>
        ))}
      </ul>
    </div>
  );
}
```

---

## Validation Gates (Per Module)

### Gate 1: Code Review ✅

**Checklist**:
- [ ] Django ORM used (no SQLAlchemy)
- [ ] tenant_id in all models
- [ ] tenant_id filtering in all ViewSets
- [ ] Session authentication (no JWT)
- [ ] Policy Engine authorization
- [ ] manifest.yaml valid
- [ ] Template structure followed
- [ ] No auth in module

**Approval Required**: Senior developer or architect

---

### Gate 2: Quality Checks ✅

```bash
# Backend checks
cd backend
black src/modules/[module-name]
flake8 src/modules/[module-name] --max-line-length=120
mypy src/modules/[module-name]

# Frontend checks
cd frontend
npx tsc --noEmit
npx eslint src/modules/[module-name] --max-warnings 0
```

**Pass Criteria**: All checks pass with 0 errors/warnings

---

### Gate 3: Testing ✅

```bash
# Backend tests
cd backend
pytest src/modules/[module-name]/tests/ -v --cov=src/modules/[module-name]

# Frontend tests
cd frontend
npm test -- src/modules/[module-name]
```

**Pass Criteria**:
- All tests pass
- Coverage ≥90%
- Tenant isolation tests pass

---

### Gate 4: Security Audit ✅

**Checklist**:
- [ ] No auth implementation in module
- [ ] Tenant isolation verified (integration tests)
- [ ] No SQL injection vulnerabilities
- [ ] No XSS vulnerabilities
- [ ] OWASP Top 10 compliance

**Approval Required**: Security team sign-off

---

## Timeline & Milestones

### Week 1-2: Platform Management (P0)
**Deliverable**: Platform configuration, health monitoring, feature flags
**Risk**: LOW

### Week 2-3: Tenant Management (P0)
**Deliverable**: Multi-tenant lifecycle, quotas, isolation
**Risk**: LOW

### Week 3-5: Security & Access Control (P0)
**Deliverable**: RBAC, Policy Engine, permissions
**Risk**: MEDIUM (Policy Engine critical)
**Mitigation**: Extra week allocated, thorough testing

### Week 5-10: Platform Services (P1)
**Deliverable**: Workflow, Metadata, DMS, Integration, Billing, Data Migration, Customization
**Risk**: LOW (parallel implementation possible)

### Week 10-12: Advanced Features (P2)
**Deliverable**: Monitoring, API Gateway, Backup, Process Mining, etc.
**Risk**: LOW

**Total**: 10-12 weeks

---

## Risk Mitigation

### Risk 1: Policy Engine Integration Complex
**Probability**: 30%
**Impact**: MEDIUM
**Mitigation**:
- Extra week allocated for Security module
- Policy Engine tested thoroughly
- Reference implementation in ai_agent_management

### Risk 2: Template Pattern Doesn't Scale
**Probability**: 10%
**Impact**: LOW
**Mitigation**:
- ai_agent_management already proven
- Refine template after first 2-3 modules
- Validation gates catch issues early

### Risk 3: Timeline Overrun
**Probability**: 20%
**Impact**: LOW
**Mitigation**:
- Conservative estimates (5-7 days per module)
- Parallel implementation where possible
- Validation gates prevent rework

**Overall Risk**: 5-10% (LOW)
**Confidence**: 90-95% (HIGH)

---

## Success Criteria

### Technical
- ✅ 22 Foundation modules operational
- ✅ Backend + Frontend + Tests for each
- ✅ ≥90% test coverage per module
- ✅ All pre-commit hooks passing
- ✅ All security audits passing

### Architectural
- ✅ Django patterns enforced
- ✅ Multitenancy enforced (tenant_id)
- ✅ Session authentication operational
- ✅ Policy Engine operational
- ✅ Template pattern proven

### Business
- ✅ Platform ready for Phase 8 (Core modules)
- ✅ Foundation modules enable business modules
- ✅ AI, workflow, security operational

---

## Document Status

**Status**: READY FOR EXECUTION
**Prerequisites**: ✅ Phase 6 complete
**Timeline**: 10-12 weeks
**Next Phase**: Phase 8 (Core modules)
**Risk**: 5-10% (LOW)
**Confidence**: 90-95% (HIGH)

---
