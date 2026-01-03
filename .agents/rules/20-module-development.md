---
description: Module development standards and best practices for SARAISE
globs: backend/src/modules/**/*.py, frontend/src/modules/**/*.{ts,tsx}
alwaysApply: true
---

# 🛠️ SARAISE Module Development Standards

**⚠️ CRITICAL**: All modules MUST follow these development standards for consistency, quality, and maintainability.

**Related Documentation:**
- Module Framework: `docs/architecture/module-framework.md`
- Application Architecture: `docs/architecture/application-architecture.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`
- Security Model: `docs/architecture/security-model.md`

## SARAISE-27001 Module Development Standards

### Code Quality Requirements
- **Code Coverage**: ≥ 90% test coverage (see `02-quality-enforcement.md`)
- **Type Safety**: Full TypeScript/Python type annotations
- **Documentation**: Comprehensive documentation for all modules
- **Testing**: Unit, integration, and end-to-end tests required
- **Security**: Zero vulnerabilities, A-rated security (see `02-quality-enforcement.md`)

## SARAISE-27002 Module Structure Standards

### Required Files
```python
# ✅ REQUIRED: Module file structure
backend/src/modules/module_name/
├── manifest.yaml            # Module metadata and dependencies
├── __init__.py              # Module initialization
├── models.py                # Django ORM models (with tenant_id)
├── views.py                 # DRF ViewSet and APIView
├── serializers.py           # DRF serializers
├── urls.py                  # URL routing
├── services.py              # Business logic
├── permissions.py           # DRF permission classes
├── policies.py              # Policy definitions
├── workflows.py             # Workflow definitions
├── search.py                # Search index configuration
├── migrations/              # Django migrations
│   ├── 0001_initial.py
│   ├── 0002_*.py
│   └── __init__.py
├── tests/                   # Module tests (≥90% coverage)
│   ├── test_models.py
│   ├── test_views.py
│   ├── test_services.py
│   └── conftest.py
└── README.md                # Module documentation
```

## SARAISE-27003 Module Testing Standards

### Test Structure
```python
# ✅ REQUIRED: Module test structure
# backend/src/modules/module_name/tests/test_models.py
import pytest
from django.test import TestCase
from src.modules.module_name.models import ModuleSpecificModel
from tests.conftest import tenant_fixture, user_fixture, db_session

def test_create_module_item(db_session, tenant_fixture):
    """Test creating module item with tenant isolation"""
    item = ModuleSpecificModel.objects.create(
        name="Test Item",
        description="Test Description",
        tenant_id=tenant_fixture.id
    )

    assert item.id is not None
    assert item.name == "Test Item"
    assert item.tenant_id == tenant_fixture.id  # CRITICAL: Verify tenant isolation

# backend/src/modules/module_name/tests/test_views.py
import pytest
from django.test import Client
from rest_framework.test import APIClient
from tests.conftest import authenticated_client, user_fixture, tenant_fixture

def test_create_item_route(authenticated_client, tenant_fixture, user_fixture):
    """Test create item DRF view"""
    response = authenticated_client.post(
        "/api/v1/module_name/items/",
        data={"name": "Test Item", "description": "Test Description"},
        format="json"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Item"
    assert data["tenant_id"] == tenant_fixture.id
```

## SARAISE-27004 Module Documentation Standards

### Module README
```markdown
# ✅ REQUIRED: Module README structure
# backend/src/modules/module_name/README.md

# Module Name

## Description
Brief description of the module and its purpose.

## Features
- Feature 1
- Feature 2
- Feature 3

## Dependencies
- base
- auth
- billing (optional)

## Installation
```bash
python scripts/install_module.py module_name
```

## Configuration
Environment variables and configuration options.

## Usage
Examples of how to use the module.

## API Endpoints
- `POST /api/v1/module_name/items` - Create item
- `GET /api/v1/module_name/items` - List items

## Permissions
- `module_name.view` - View items
- `module_name.create` - Create items
- `module_name.update` - Update items
- `module_name.delete` - Delete items

## Testing
```bash
pytest backend/src/modules/module_name/tests/
```

## License
Apache-2.0
```

## SARAISE-27005 Module Versioning

### Version Management
```python
# ✅ REQUIRED: Module versioning
# backend/src/modules/module_name/__init__.py
MODULE_VERSION = "1.0.0"  # Semantic versioning: MAJOR.MINOR.PATCH

# Version history
VERSION_HISTORY = [
    {
        "version": "1.0.0",
        "date": "2025-01-01",
        "changes": [
            "Initial release",
            "Basic CRUD operations",
            "Tenant isolation"
        ]
    }
]
```

## SARAISE-27006 Module Migration Standards

### Migration Structure
```python
# ✅ REQUIRED: Module migration structure
# backend/src/modules/module_name/migrations/0001_initial_schema.py
"""Initial module schema"""
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenants', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModuleSpecificItem',
            fields=[
                ('id', models.CharField(max_length=36, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.CharField(max_length=1000, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant_id', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tenants.tenant')),
            ],
            options={
                'db_table': 'module_specific_table',
                'indexes': [models.Index(fields=['tenant_id'], name='idx_module_tenant')],
            },
        ),
    ]
```

## SARAISE-27007 Module Security Standards

### Security Requirements
```python
# ✅ REQUIRED: Module security standards
# backend/src/modules/module_name/routes.py
from src.core.auth_decorators import RequireTenantUser, RequireTenantAdmin
from src.services.audit_service import AuditService

# ✅ CORRECT: DRF ViewSet pattern (no FastAPI, no AsyncSession)
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from src.core.permissions import SessionAuthentication
from src.core.policy_engine import PolicyEngine
from src.core.auth import get_current_user_from_session

class ModuleItemViewSet(viewsets.ModelViewSet):
    """Module item management with audit logging."""
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    
    def create(self, request):
        """Create item with audit logging - requires tenant_user role."""
        current_user = get_current_user_from_session(request)
        policy_engine = PolicyEngine()
        
        # Policy Engine authorization check
        decision = policy_engine.evaluate(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            resource="module_name.items",
            action="create",
            context={}
        )
        
        if not decision.allowed:
            return Response(
                {"error": "Insufficient permissions"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # ✅ CORRECT: Django ORM - no db parameter needed
        service = ModuleService()  # Uses Model.objects directly
        item = service.create_item(request.data, current_user.tenant_id)

    # Audit log
    audit_service = AuditService(db)
    await audit_service.log_event(
        actor_sub=current_user.id,
        actor_email=current_user.email,
        tenant_id=current_user.tenant_id,
        resource="module_name.items",
        action="CREATE",
        result="success",
        metadata={"item_id": item.module_id},
        request=request
    )

    return item
```

## SARAISE-27008 Module Error Handling

### Error Handling Standards
```python
# ✅ REQUIRED: Module error handling
# backend/src/modules/module_name/services.py
from src.core.errors import ValidationError, DatabaseError

class ModuleService:
    async def create_item(self, item_data: ModuleItemCreate, tenant_id: str):
        """Create item with proper error handling"""
        try:
            # Validate data
            if not item_data.name:
                raise ValidationError("Item name is required")

            # ✅ CORRECT: Django ORM - use Model.objects.create()
            item = ModuleSpecificModel.objects.create(
                **item_data,
                tenant_id=tenant_id
            )
            return item

        except Exception as e:
            if isinstance(e, ValidationError):
                raise e
            raise DatabaseError(f"Failed to create item: {e}")
```

## SARAISE-27009 Module Performance Standards

### Performance Requirements
- **Response Time**: < 200ms (95th percentile)
- **Database Queries**: < 100ms (95th percentile)
- **Caching**: Use Redis for frequently accessed data
- **Pagination**: All list endpoints must support pagination

### Performance Optimization
```python
# ✅ REQUIRED: Module performance optimization
# backend/src/modules/module_name/services.py
from src.services.redis_service import RedisService

class ModuleService:
    def __init__(self):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.redis = RedisService()
        self.cache_ttl = 3600  # 1 hour

    def get_item(self, item_id: str, tenant_id: str):
        """Get item with caching (explicit tenant_id filtering for Row-Level Multitenancy)"""
        # ✅ CORRECT: Include tenant_id in cache key for tenant isolation
        cache_key = f"module_name:item:{tenant_id}:{item_id}"

        # Check cache first
        cached = self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # ✅ CORRECT: Django ORM - use Model.objects.filter() with explicit tenant_id
        item = ModuleSpecificModel.objects.filter(
            module_id=item_id,
            tenant_id=tenant_id  # CRITICAL: Explicit tenant filter
        ).first()

        if item:
            # Cache result
            self.redis.set(
                cache_key,
                json.dumps(item.__dict__),
                ex=self.cache_ttl
            )

        return item
```

## SARAISE-27010 Module Integration Standards

### Integration Patterns
```python
# ✅ REQUIRED: Module integration patterns
# backend/src/modules/module_name/services.py
from src.modules.billing.services import BillingService
from src.modules.subscriptions.services import SubscriptionService

class ModuleService:
    async def create_item_with_billing(self, item_data: ModuleItemCreate, tenant_id: str):
        """Create item with billing integration"""
        # Check subscription limits
        subscription_service = SubscriptionService(self.db)
        subscription = await subscription_service.get_tenant_subscription(tenant_id)

        if not subscription or not subscription.is_active:
            raise ValidationError("Active subscription required")

        # Create item
        item = await self.create_item(item_data, tenant_id)

        # Record usage
        billing_service = BillingService(self.db)
        await billing_service.record_usage(
            tenant_id=tenant_id,
            resource="module_name.items",
            quantity=1
        )

        return item
```

---

**Next Steps**: Use these standards when developing new modules. Ensure all modules meet code quality, security, and performance requirements before deployment.
