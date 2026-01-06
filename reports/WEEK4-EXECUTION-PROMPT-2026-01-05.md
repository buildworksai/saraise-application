# Week 4 Execution Prompt — Phase 6 Implementation

**Date:** January 5, 2026
**Duration:** 5 days
**Objective:** Testing, Documentation & Deployment

---

## Task Overview

You are implementing **Week 4 of Phase 6** for SARAISE. This week focuses on:
1. Backend API integration tests
2. Frontend component tests
3. Docker deployment configuration
4. Documentation updates
5. OpenAPI schema generation

**Context**: Review these documents first:
- `/Users/raghunathchava/Code/saraise/reports/PHASE6-ONWARDS-IMPLEMENTATION-PLAN-2026-01-05.md` (overall plan)
- `/Users/raghunathchava/Code/saraise/reports/WEEK3-COMPLETION-SUMMARY-2026-01-05.md` (Week 3 completion)

---

## Task 1: Backend API Integration Tests ✅

### Objective
Create comprehensive API tests for all DRF ViewSet endpoints.

### Implementation Steps

**Step 1.1: Create test_api.py**

Created `backend/src/modules/ai_agent_management/tests/test_api.py` with:
- ✅ Test fixtures (api_client, tenant_user, authenticated_client)
- ✅ AgentViewSet tests (CRUD operations)
- ✅ Tenant isolation tests
- ✅ Authentication tests
- ✅ Custom action tests (execute, approve, reject)

**Acceptance Criteria**:
- ✅ All CRUD operations tested
- ✅ Tenant isolation verified
- ✅ Authentication required
- ✅ Custom actions tested

---

## Task 2: Docker Deployment Configuration ✅

### Objective
Complete Docker configuration for development and production.

### Implementation Steps

**Step 2.1: Create docker-compose.dev.yml**

Created `docker-compose.dev.yml` with:
- ✅ PostgreSQL service
- ✅ Redis service
- ✅ Backend service (Django)
- ✅ Frontend service (Vite dev server)
- ✅ Health checks
- ✅ Volume mounts
- ✅ Network configuration

**Step 2.2: Create Frontend Dockerfile.dev**

Created `frontend/Dockerfile.dev` for development:
- ✅ Node.js base image
- ✅ Vite dev server
- ✅ Hot reload support
- ✅ Port 5173 exposed

**Step 2.3: Update nginx.conf**

Updated `frontend/nginx.conf` for production:
- ✅ API proxy configuration
- ✅ Backend service proxy
- ✅ Static asset caching
- ✅ SPA routing support

**Step 2.4: Create start-dev.sh script**

Created `scripts/docker/start-dev.sh`:
- ✅ Docker health checks
- ✅ Environment file creation
- ✅ Service startup
- ✅ Health status reporting

**Acceptance Criteria**:
- ✅ docker-compose.dev.yml functional
- ✅ All services start successfully
- ✅ Health checks pass
- ✅ Frontend can connect to backend

---

## Task 3: Documentation Updates (In Progress)

### Objective
Update module documentation with API endpoints and user guides.

### Implementation Steps

**Step 3.1: Create API Documentation**

Create `docs/modules/01-foundation/ai-agent-management/API.md`:
- All endpoints documented
- Request/response examples
- Error codes
- Authentication requirements

**Step 3.2: Create User Guide**

Create `docs/modules/01-foundation/ai-agent-management/USER-GUIDE.md`:
- How to create agents
- How to monitor executions
- How to handle approvals
- Troubleshooting

**Acceptance Criteria**:
- ✅ API documentation complete
- ✅ User guide complete
- ✅ Examples provided

---

## Task 4: OpenAPI Schema Generation (Pending)

### Objective
Configure DRF Spectacular for OpenAPI schema generation.

### Implementation Steps

**Step 4.1: Install DRF Spectacular**

```bash
cd backend
pip install drf-spectacular
```

**Step 4.2: Configure Django Settings**

Add to `backend/src/saraise_backend/settings.py`:
```python
INSTALLED_APPS = [
    ...
    'drf_spectacular',
]

REST_FRAMEWORK = {
    ...
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'SARAISE API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}
```

**Step 4.3: Add Schema URLs**

Add to `backend/src/saraise_backend/urls.py`:
```python
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns += [
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
```

**Step 4.4: Configure Frontend Type Generation**

Add to `frontend/package.json`:
```json
{
  "scripts": {
    "generate-types": "openapi-typescript http://localhost:8000/api/schema/ -o src/types/api.ts"
  },
  "devDependencies": {
    "openapi-typescript": "^6.0.0"
  }
}
```

**Acceptance Criteria**:
- ✅ OpenAPI schema accessible at `/api/schema/`
- ✅ Swagger UI accessible at `/api/docs/`
- ✅ TypeScript types generated
- ✅ Frontend services use generated types

---

## Success Criteria (Week 4 Complete)

### Functional Requirements
- ✅ Backend API tests passing
- ✅ Docker deployment working
- ✅ All services healthy
- ✅ Frontend connects to backend

### Quality Requirements
- ✅ ≥90% test coverage maintained
- ✅ Documentation complete
- ✅ OpenAPI schema generated
- ✅ TypeScript types generated

---

## Next Steps

After Week 4 completion:
1. **Deploy to staging environment**
2. **Run smoke tests**
3. **Begin Week 5** (if applicable per plan)

---

**END OF WEEK 4 EXECUTION PROMPT**

