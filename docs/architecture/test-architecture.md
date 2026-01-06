# SARAISE Test Architecture

**Status:** Authoritative — Freeze Blocking  
**Version:** 1.0.0  
**Last Updated:** January 5, 2026

This document defines the **test strategy, patterns, and requirements** for SARAISE. Testing is not optional — it is a quality gate that blocks deployment.

---

## 0) Non-Negotiable Principles

1. **Tests are documentation.** They define expected behavior.
2. **Coverage is mandatory.** ≥90% coverage is a release gate.
3. **Tests must be fast.** Slow tests are skipped tests.
4. **Tests must be reliable.** Flaky tests are deleted or fixed.
5. **Tenant isolation must be tested.** Security is proven by tests.

---

## 1) Test Pyramid

SARAISE follows the **Test Pyramid** strategy:

```
         /\
        /  \  E2E Tests (5%)
       /    \  - Critical user journeys only
      /------\
     /        \  Integration Tests (25%)
    /          \  - API contracts, module interactions
   /------------\
  /              \  Unit Tests (70%)
 /                \  - Business logic, utilities, services
/------------------\
```

### 1.1 Distribution Targets

| Test Type | Target Coverage | Execution Time |
|-----------|-----------------|----------------|
| Unit tests | 70% of test suite | ≤30 seconds |
| Integration tests | 25% of test suite | ≤5 minutes |
| E2E tests | 5% of test suite | ≤15 minutes |

---

## 2) Backend Test Patterns

### 2.1 Test Framework & Tools

| Tool | Purpose |
|------|---------|
| pytest | Test runner |
| pytest-django | Django integration |
| pytest-cov | Coverage reporting |
| factory_boy | Test data factories |
| freezegun | Time mocking |
| responses | HTTP mocking |

### 2.2 Test Directory Structure

```
backend/
├── tests/                    # Global test utilities
│   ├── __init__.py
│   ├── conftest.py          # Global fixtures
│   └── factories.py         # Shared factories
└── src/
    └── modules/
        └── module_name/
            └── tests/
                ├── __init__.py
                ├── conftest.py      # Module-specific fixtures
                ├── test_models.py   # Model unit tests
                ├── test_api.py      # API integration tests
                ├── test_services.py # Service unit tests
                └── test_isolation.py # Tenant isolation tests
```

### 2.3 Fixture Pattern (conftest.py)

```python
# backend/tests/conftest.py

import pytest
from django.test import Client
from rest_framework.test import APIClient
import uuid

@pytest.fixture
def tenant_id():
    """Generate unique tenant ID for test isolation."""
    return str(uuid.uuid4())

@pytest.fixture
def other_tenant_id():
    """Generate different tenant ID for isolation tests."""
    return str(uuid.uuid4())

@pytest.fixture
def user_fixture(tenant_id):
    """Create authenticated user for tenant."""
    from src.core.user_models import User
    return User.objects.create(
        id=str(uuid.uuid4()),
        email=f"test-{uuid.uuid4()}@example.com",
        tenant_id=tenant_id,
    )

@pytest.fixture
def api_client(user_fixture):
    """Create authenticated API client."""
    client = APIClient()
    client.force_authenticate(user=user_fixture)
    return client

@pytest.fixture
def unauthenticated_client():
    """Create unauthenticated API client."""
    return APIClient()
```

### 2.4 Model Test Pattern

```python
# backend/src/modules/module_name/tests/test_models.py

import pytest
from django.core.exceptions import ValidationError
from ..models import Resource

@pytest.mark.django_db
class TestResourceModel:
    """Unit tests for Resource model."""

    def test_create_resource_with_valid_data(self, tenant_id):
        """Resource can be created with valid data."""
        resource = Resource.objects.create(
            tenant_id=tenant_id,
            name="Test Resource",
            status="active",
        )
        assert resource.id is not None
        assert resource.tenant_id == tenant_id
        assert resource.name == "Test Resource"

    def test_tenant_id_is_required(self):
        """Resource creation fails without tenant_id."""
        with pytest.raises(ValidationError):
            Resource.objects.create(
                name="Test Resource",
                # Missing tenant_id
            )

    def test_name_max_length(self, tenant_id):
        """Resource name respects max length constraint."""
        with pytest.raises(ValidationError):
            Resource.objects.create(
                tenant_id=tenant_id,
                name="x" * 300,  # Exceeds max_length=255
            )
```

### 2.5 API Test Pattern

```python
# backend/src/modules/module_name/tests/test_api.py

import pytest
from rest_framework import status
from ..models import Resource

@pytest.mark.django_db
class TestResourceAPI:
    """Integration tests for Resource API."""

    def test_list_resources_authenticated(self, api_client, tenant_id):
        """Authenticated user can list their tenant's resources."""
        # Create test data
        Resource.objects.create(tenant_id=tenant_id, name="Resource 1")
        Resource.objects.create(tenant_id=tenant_id, name="Resource 2")

        response = api_client.get("/api/v1/module-name/resources/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2

    def test_list_resources_unauthenticated(self, unauthenticated_client):
        """Unauthenticated request is rejected."""
        response = unauthenticated_client.get("/api/v1/module-name/resources/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_resource_success(self, api_client):
        """Valid POST creates resource."""
        data = {"name": "New Resource", "status": "active"}

        response = api_client.post(
            "/api/v1/module-name/resources/",
            data,
            format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Resource"

    def test_create_resource_validation_error(self, api_client):
        """Invalid data returns 400 with error details."""
        data = {"name": ""}  # Name is required

        response = api_client.post(
            "/api/v1/module-name/resources/",
            data,
            format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "name" in response.data
```

### 2.6 Tenant Isolation Test Pattern (MANDATORY)

```python
# backend/src/modules/module_name/tests/test_isolation.py

import pytest
from rest_framework import status
from ..models import Resource

@pytest.mark.django_db
class TestTenantIsolation:
    """
    CRITICAL: Tenant isolation tests.
    These tests verify that tenants cannot access each other's data.
    """

    def test_user_cannot_list_other_tenant_resources(
        self, api_client, tenant_id, other_tenant_id
    ):
        """User sees only their tenant's resources in list."""
        # Create resource for current tenant
        Resource.objects.create(tenant_id=tenant_id, name="My Resource")

        # Create resource for other tenant
        Resource.objects.create(tenant_id=other_tenant_id, name="Other Resource")

        response = api_client.get("/api/v1/module-name/resources/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["name"] == "My Resource"

    def test_user_cannot_access_other_tenant_resource(
        self, api_client, tenant_id, other_tenant_id
    ):
        """User cannot GET other tenant's resource by ID."""
        other_resource = Resource.objects.create(
            tenant_id=other_tenant_id,
            name="Other Resource"
        )

        response = api_client.get(
            f"/api/v1/module-name/resources/{other_resource.id}/"
        )

        # MUST return 404 (not 403) to hide existence
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_resource(
        self, api_client, tenant_id, other_tenant_id
    ):
        """User cannot PUT to other tenant's resource."""
        other_resource = Resource.objects.create(
            tenant_id=other_tenant_id,
            name="Other Resource"
        )

        response = api_client.put(
            f"/api/v1/module-name/resources/{other_resource.id}/",
            {"name": "Hacked"},
            format="json"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Verify data unchanged
        other_resource.refresh_from_db()
        assert other_resource.name == "Other Resource"

    def test_user_cannot_delete_other_tenant_resource(
        self, api_client, tenant_id, other_tenant_id
    ):
        """User cannot DELETE other tenant's resource."""
        other_resource = Resource.objects.create(
            tenant_id=other_tenant_id,
            name="Other Resource"
        )

        response = api_client.delete(
            f"/api/v1/module-name/resources/{other_resource.id}/"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # Verify resource still exists
        assert Resource.objects.filter(id=other_resource.id).exists()
```

---

## 3) Frontend Test Patterns

### 3.1 Test Framework & Tools

| Tool | Purpose |
|------|---------|
| Vitest | Test runner |
| @testing-library/react | Component testing |
| @testing-library/user-event | User interaction simulation |
| msw | API mocking |
| @tanstack/react-query | Query testing utilities |

### 3.2 Test Directory Structure

```
frontend/
├── src/
│   └── modules/
│       └── module_name/
│           ├── pages/
│           │   └── ListPage.tsx
│           ├── services/
│           │   └── module-service.ts
│           └── tests/
│               ├── ListPage.test.tsx
│               └── module-service.test.ts
├── tests/
│   ├── setup.ts           # Global test setup
│   └── mocks/
│       └── handlers.ts    # MSW handlers
```

### 3.3 Component Test Pattern

```typescript
// frontend/src/modules/module_name/tests/ListPage.test.tsx

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ListPage } from '../pages/ListPage';
import { server } from '@/tests/mocks/server';
import { http, HttpResponse } from 'msw';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
  },
});

const renderWithProviders = (ui: React.ReactElement) => {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
};

describe('ListPage', () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it('renders loading state initially', () => {
    renderWithProviders(<ListPage />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders resources after successful fetch', async () => {
    server.use(
      http.get('/api/v1/module-name/resources/', () => {
        return HttpResponse.json({
          results: [
            { id: '1', name: 'Resource 1' },
            { id: '2', name: 'Resource 2' },
          ],
        });
      })
    );

    renderWithProviders(<ListPage />);

    await waitFor(() => {
      expect(screen.getByText('Resource 1')).toBeInTheDocument();
      expect(screen.getByText('Resource 2')).toBeInTheDocument();
    });
  });

  it('renders error state on fetch failure', async () => {
    server.use(
      http.get('/api/v1/module-name/resources/', () => {
        return new HttpResponse(null, { status: 500 });
      })
    );

    renderWithProviders(<ListPage />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

### 3.4 Service Test Pattern

```typescript
// frontend/src/modules/module_name/tests/module-service.test.ts

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { moduleService } from '../services/module-service';
import { apiClient } from '@/services/api-client';

vi.mock('@/services/api-client');

describe('moduleService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listResources', () => {
    it('calls correct endpoint', async () => {
      const mockData = { results: [] };
      vi.mocked(apiClient.get).mockResolvedValue(mockData);

      await moduleService.listResources();

      expect(apiClient.get).toHaveBeenCalledWith(
        '/api/v1/module-name/resources/'
      );
    });
  });

  describe('createResource', () => {
    it('posts data to correct endpoint', async () => {
      const newResource = { name: 'New Resource' };
      vi.mocked(apiClient.post).mockResolvedValue({ id: '1', ...newResource });

      await moduleService.createResource(newResource);

      expect(apiClient.post).toHaveBeenCalledWith(
        '/api/v1/module-name/resources/',
        newResource
      );
    });
  });
});
```

---

## 4) E2E Test Patterns

### 4.1 E2E Test Framework

| Tool | Purpose |
|------|---------|
| Playwright | Browser automation |
| @playwright/test | Test runner |

### 4.2 E2E Test Structure

```
e2e/
├── playwright.config.ts
├── tests/
│   ├── auth.spec.ts        # Authentication flows
│   ├── resources.spec.ts   # Resource CRUD
│   └── tenant-isolation.spec.ts
├── fixtures/
│   └── auth.ts             # Auth fixtures
└── pages/
    ├── login.page.ts       # Page objects
    └── resources.page.ts
```

### 4.3 Critical E2E Scenarios (MANDATORY)

1. **Authentication flow**
   - Login success
   - Login failure
   - Logout
   - Session expiration handling

2. **CRUD operations**
   - Create resource
   - Read resource list
   - Update resource
   - Delete resource

3. **Tenant isolation**
   - Cross-tenant access blocked

---

## 5) Test Coverage Requirements

### 5.1 Coverage Thresholds

| Metric | Minimum | Target |
|--------|---------|--------|
| Line coverage | 90% | 95% |
| Branch coverage | 80% | 90% |
| Function coverage | 90% | 95% |
| Statement coverage | 90% | 95% |

### 5.2 Coverage Exclusions

Only the following may be excluded:
- Generated code (migrations, OpenAPI types)
- Type definitions (`.d.ts` files)
- Test files themselves

### 5.3 Coverage Enforcement

```yaml
# Backend: pytest.ini
[pytest]
addopts = --cov=src --cov-report=term --cov-report=html --cov-fail-under=90

# Frontend: vitest.config.ts
coverage: {
  threshold: {
    global: {
      statements: 90,
      branches: 80,
      functions: 90,
      lines: 90,
    },
  },
}
```

---

## 6) Test Data Management

### 6.1 Factory Pattern

```python
# backend/tests/factories.py

import factory
from factory.django import DjangoModelFactory
from src.modules.module_name.models import Resource
import uuid

class ResourceFactory(DjangoModelFactory):
    class Meta:
        model = Resource

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    tenant_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.Faker('company')
    status = 'active'
```

### 6.2 Test Database Rules

- Use separate test database
- Transactions rolled back after each test
- No shared state between tests
- No production data in tests

---

## 7) Test Execution

### 7.1 Local Execution

```bash
# Backend
cd backend
pytest tests/ -v --cov=src --cov-report=html
# Open htmlcov/index.html for coverage report

# Frontend
cd frontend
npm test
npm run test:coverage
```

### 7.2 CI Execution

```yaml
# .github/workflows/quality-guardrails.yml
- name: Backend Tests
  run: pytest tests/ --cov=src --cov-report=xml --cov-fail-under=90

- name: Frontend Tests
  run: npm test -- --coverage
```

### 7.3 Performance Requirements

| Test Suite | Max Duration |
|------------|--------------|
| Unit tests | 2 minutes |
| Integration tests | 5 minutes |
| Full test suite | 10 minutes |

---

## 8) Test Quality Gates

### 8.1 Pre-Merge Requirements

All PRs MUST:
- [ ] Pass all existing tests
- [ ] Include tests for new code
- [ ] Maintain ≥90% coverage
- [ ] Include tenant isolation tests (if data model added)
- [ ] Have no skipped tests without justification

### 8.2 Release Requirements

All releases MUST:
- [ ] Pass full test suite
- [ ] Pass E2E critical scenarios
- [ ] Show no coverage regression
- [ ] Pass security tests
- [ ] Pass performance tests

---

## 9) What Is Explicitly Forbidden

- ❌ Tests that depend on execution order
- ❌ Tests that share state
- ❌ Tests that hit production APIs
- ❌ Tests without assertions
- ❌ Skipped tests in production code
- ❌ Flaky tests (fix or delete)
- ❌ Missing tenant isolation tests for new models
- ❌ Coverage below 90%

---

## 10) Final Warning

Tests are the **primary defense** against bugs reaching production.

If a module doesn't have comprehensive tests, it doesn't ship.

---

**Verification Checksum**
- Document: test-architecture.md
- Purpose: Define test strategy, patterns, and requirements
- Status: Authoritative — Freeze Blocking

---

**End of document**

