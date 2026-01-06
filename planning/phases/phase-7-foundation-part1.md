# Phase 7: Foundation Modules Part 1 — Critical Infrastructure

**Duration:** 5 weeks  
**Modules:** Platform Management, Tenant Management, Security & Access Control  
**Status:** 🟢 READY FOR EXECUTION  
**Executor:** AI Agent  
**Prerequisites:** Phase 6 complete (ai_agent_management operational)

---

## Phase Objectives

### Primary Goal
Implement the 3 most critical Foundation modules that enable multi-tenancy, platform operations, and security infrastructure.

### Success Criteria
- [ ] 3 modules operational (backend + frontend + tests)
- [ ] ≥90% test coverage per module
- [ ] All pre-commit hooks passing
- [ ] Tenant isolation verified
- [ ] Policy Engine integration verified

---

## Week 1-2: Platform Management Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `platform_management` |
| Type | Foundation |
| Priority | P0 (Highest) |
| Dependencies | None |
| Spec Location | `docs/modules/01-foundation/platform-management/` |
| Timeline | 7-10 days |
| Risk | LOW |

### Day 1: Specification Review & Planning

**Task 1.1: Read module specification**
```bash
# AI Agent: Read and understand the specification
cat docs/modules/01-foundation/platform-management/README.md
cat docs/modules/01-foundation/platform-management/API.md
```

**Task 1.2: Extract data models**
```
Expected entities from spec:
- PlatformSetting (key, value, category, is_secret)
- FeatureFlag (name, enabled, description, tenant_specific)
- SystemHealth (service_name, status, last_check, metrics)
- AuditEvent (action, actor, resource, timestamp, details)
```

**Task 1.3: Extract API endpoints**
```
Expected endpoints from spec:
- GET/POST/PUT /api/v1/platform/settings/
- GET/POST/PUT /api/v1/platform/feature-flags/
- GET /api/v1/platform/health/
- GET /api/v1/platform/audit-events/
```

### Day 2-3: Backend Implementation

**Task 2.1: Create module directory structure**
```bash
cd /Users/raghunathchava/Code/saraise/backend/src/modules

# Create directory structure
mkdir -p platform_management/{migrations,tests}

# Create required files
touch platform_management/__init__.py
touch platform_management/manifest.yaml
touch platform_management/models.py
touch platform_management/serializers.py
touch platform_management/api.py
touch platform_management/urls.py
touch platform_management/services.py
touch platform_management/permissions.py
touch platform_management/health.py

# Create test files
touch platform_management/tests/__init__.py
touch platform_management/tests/test_models.py
touch platform_management/tests/test_api.py
touch platform_management/tests/test_services.py
touch platform_management/tests/test_isolation.py
```

**Task 2.2: Implement manifest.yaml**
```yaml
# backend/src/modules/platform_management/manifest.yaml
name: platform-management
version: 1.0.0
description: Platform administration, health monitoring, and configuration management
type: foundation
lifecycle: platform
dependencies: []
permissions:
  - platform.settings:create
  - platform.settings:read
  - platform.settings:update
  - platform.settings:delete
  - platform.feature-flags:create
  - platform.feature-flags:read
  - platform.feature-flags:update
  - platform.feature-flags:delete
  - platform.health:read
  - platform.audit:read
sod_actions:
  - platform.settings:update
  - platform.settings:approve
search_indexes:
  - platform_settings
  - platform_audit_events
ai_tools:
  - update_platform_setting
  - toggle_feature_flag
```

**Task 2.3: Implement models.py**
```python
# backend/src/modules/platform_management/models.py
"""
Platform Management Models
Implements: Platform settings, feature flags, health checks, audit events

Architecture Compliance:
- ✅ Django ORM
- ✅ tenant_id for tenant-specific settings
- ✅ Indexes on frequently queried fields
"""

from django.db import models
import uuid


class PlatformSetting(models.Model):
    """Platform-wide or tenant-specific configuration settings."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)  # null = platform-wide

    key = models.CharField(max_length=255)
    value = models.TextField()
    category = models.CharField(max_length=100, default='general')
    description = models.TextField(blank=True)
    is_secret = models.BooleanField(default=False)
    data_type = models.CharField(
        max_length=20,
        choices=[
            ('string', 'String'),
            ('integer', 'Integer'),
            ('boolean', 'Boolean'),
            ('json', 'JSON'),
        ],
        default='string'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.UUIDField(null=True, blank=True)
    updated_by = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = 'platform_settings'
        unique_together = [['tenant_id', 'key']]
        indexes = [
            models.Index(fields=['tenant_id', 'category']),
            models.Index(fields=['key']),
        ]

    def __str__(self):
        return f"{self.key}={self.value[:50]}"


class FeatureFlag(models.Model):
    """Feature flags for gradual rollout and A/B testing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)  # null = platform-wide

    name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    rollout_percentage = models.IntegerField(default=100)  # 0-100%

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'platform_feature_flags'
        unique_together = [['tenant_id', 'name']]
        indexes = [
            models.Index(fields=['tenant_id', 'enabled']),
            models.Index(fields=['name']),
        ]

    def __str__(self):
        return f"{self.name}: {'ON' if self.enabled else 'OFF'}"


class SystemHealth(models.Model):
    """Health check results for platform services."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    service_name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=[
            ('healthy', 'Healthy'),
            ('degraded', 'Degraded'),
            ('unhealthy', 'Unhealthy'),
        ],
        default='healthy'
    )
    last_check = models.DateTimeField(auto_now=True)
    response_time_ms = models.IntegerField(null=True, blank=True)
    details = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'platform_system_health'
        indexes = [
            models.Index(fields=['service_name', 'status']),
            models.Index(fields=['last_check']),
        ]

    def __str__(self):
        return f"{self.service_name}: {self.status}"


class PlatformAuditEvent(models.Model):
    """
    Immutable audit log for platform operations.
    
    CRITICAL: This model is APPEND-ONLY. Updates and deletes are forbidden.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True, null=True, blank=True)

    action = models.CharField(max_length=100)
    actor_type = models.CharField(max_length=20)  # user, system, agent
    actor_id = models.UUIDField()
    resource_type = models.CharField(max_length=100)
    resource_id = models.UUIDField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    details = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = 'platform_audit_events'
        indexes = [
            models.Index(fields=['tenant_id', 'timestamp']),
            models.Index(fields=['actor_id', 'timestamp']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
        # CRITICAL: No update/delete allowed
        managed = True

    def save(self, *args, **kwargs):
        if self.pk and PlatformAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValueError("Audit events are immutable - updates forbidden")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events are immutable - deletes forbidden")

    def __str__(self):
        return f"{self.action} by {self.actor_id} at {self.timestamp}"
```

**Task 2.4: Create Django migrations**
```bash
cd /Users/raghunathchava/Code/saraise/backend
python manage.py makemigrations platform_management
python manage.py migrate
```

**Task 2.5: Implement serializers.py**
```python
# backend/src/modules/platform_management/serializers.py
"""
Platform Management Serializers
DRF serializers for API validation and transformation
"""

from rest_framework import serializers
from .models import PlatformSetting, FeatureFlag, SystemHealth, PlatformAuditEvent


class PlatformSettingSerializer(serializers.ModelSerializer):
    """Serializer for platform settings."""

    class Meta:
        model = PlatformSetting
        fields = [
            'id', 'tenant_id', 'key', 'value', 'category',
            'description', 'is_secret', 'data_type',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate_key(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Key must be at least 2 characters")
        return value.lower().replace(' ', '_')

    def to_representation(self, instance):
        """Mask secret values in output."""
        data = super().to_representation(instance)
        if instance.is_secret:
            data['value'] = '********'
        return data


class PlatformSettingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating platform settings."""

    class Meta:
        model = PlatformSetting
        fields = ['key', 'value', 'category', 'description', 'is_secret', 'data_type']

    def validate_key(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Key must be at least 2 characters")
        return value.lower().replace(' ', '_')


class FeatureFlagSerializer(serializers.ModelSerializer):
    """Serializer for feature flags."""

    class Meta:
        model = FeatureFlag
        fields = [
            'id', 'tenant_id', 'name', 'enabled',
            'description', 'rollout_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate_name(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters")
        return value.lower().replace(' ', '_')

    def validate_rollout_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Rollout percentage must be 0-100")
        return value


class FeatureFlagCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating feature flags."""

    class Meta:
        model = FeatureFlag
        fields = ['name', 'enabled', 'description', 'rollout_percentage']


class SystemHealthSerializer(serializers.ModelSerializer):
    """Serializer for system health status."""

    class Meta:
        model = SystemHealth
        fields = [
            'id', 'service_name', 'status', 'last_check',
            'response_time_ms', 'details', 'error_message'
        ]
        read_only_fields = ['id', 'last_check']


class PlatformAuditEventSerializer(serializers.ModelSerializer):
    """Serializer for audit events (read-only)."""

    class Meta:
        model = PlatformAuditEvent
        fields = [
            'id', 'tenant_id', 'action', 'actor_type', 'actor_id',
            'resource_type', 'resource_id', 'timestamp',
            'details', 'ip_address'
        ]
        read_only_fields = fields  # All fields are read-only
```

**Task 2.6: Implement api.py (ViewSets)**
```python
# backend/src/modules/platform_management/api.py
"""
Platform Management API ViewSets
DRF ViewSets with tenant isolation and Policy Engine authorization
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from .models import PlatformSetting, FeatureFlag, SystemHealth, PlatformAuditEvent
from .serializers import (
    PlatformSettingSerializer, PlatformSettingCreateSerializer,
    FeatureFlagSerializer, FeatureFlagCreateSerializer,
    SystemHealthSerializer, PlatformAuditEventSerializer
)
from .services import PlatformManagementService


class PlatformSettingViewSet(viewsets.ModelViewSet):
    """
    API endpoints for platform settings.
    
    Architecture Compliance:
    - ✅ Tenant filtering in get_queryset
    - ✅ tenant_id set on create
    - ✅ Audit logging on mutations
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PlatformSettingCreateSerializer
        return PlatformSettingSerializer

    def get_queryset(self):
        """Filter settings by tenant_id for tenant-specific settings."""
        user = self.request.user
        tenant_id = getattr(user, 'tenant_id', None)

        # Return platform-wide settings + tenant-specific settings
        if tenant_id:
            return PlatformSetting.objects.filter(
                models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id)
            )
        return PlatformSetting.objects.filter(tenant_id__isnull=True)

    def perform_create(self, serializer):
        """Set tenant_id and audit on create."""
        tenant_id = getattr(self.request.user, 'tenant_id', None)
        instance = serializer.save(
            tenant_id=tenant_id,
            created_by=self.request.user.id
        )
        # Audit logging
        PlatformManagementService.log_audit_event(
            action='platform.setting.created',
            actor_id=self.request.user.id,
            resource_type='PlatformSetting',
            resource_id=instance.id,
            tenant_id=tenant_id,
            details={'key': instance.key}
        )

    def perform_update(self, serializer):
        """Audit on update."""
        instance = serializer.save(updated_by=self.request.user.id)
        PlatformManagementService.log_audit_event(
            action='platform.setting.updated',
            actor_id=self.request.user.id,
            resource_type='PlatformSetting',
            resource_id=instance.id,
            tenant_id=instance.tenant_id,
            details={'key': instance.key}
        )


class FeatureFlagViewSet(viewsets.ModelViewSet):
    """API endpoints for feature flags."""
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return FeatureFlagCreateSerializer
        return FeatureFlagSerializer

    def get_queryset(self):
        """Filter flags by tenant_id."""
        user = self.request.user
        tenant_id = getattr(user, 'tenant_id', None)

        if tenant_id:
            return FeatureFlag.objects.filter(
                models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id)
            )
        return FeatureFlag.objects.filter(tenant_id__isnull=True)

    def perform_create(self, serializer):
        tenant_id = getattr(self.request.user, 'tenant_id', None)
        serializer.save(tenant_id=tenant_id)

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle feature flag on/off."""
        flag = self.get_object()
        flag.enabled = not flag.enabled
        flag.save()

        PlatformManagementService.log_audit_event(
            action='platform.feature_flag.toggled',
            actor_id=request.user.id,
            resource_type='FeatureFlag',
            resource_id=flag.id,
            tenant_id=flag.tenant_id,
            details={'name': flag.name, 'enabled': flag.enabled}
        )

        return Response(FeatureFlagSerializer(flag).data)


class SystemHealthViewSet(viewsets.ReadOnlyModelViewSet):
    """API endpoints for system health (read-only)."""
    permission_classes = [IsAuthenticated]
    serializer_class = SystemHealthSerializer
    queryset = SystemHealth.objects.all()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get health summary for all services."""
        services = SystemHealth.objects.all()
        healthy = services.filter(status='healthy').count()
        degraded = services.filter(status='degraded').count()
        unhealthy = services.filter(status='unhealthy').count()

        return Response({
            'status': 'healthy' if unhealthy == 0 and degraded == 0 else 'degraded' if unhealthy == 0 else 'unhealthy',
            'healthy': healthy,
            'degraded': degraded,
            'unhealthy': unhealthy,
            'total': services.count(),
            'timestamp': timezone.now().isoformat()
        })


class PlatformAuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for audit events (read-only).
    
    CRITICAL: No create/update/delete allowed.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PlatformAuditEventSerializer

    def get_queryset(self):
        """Filter audit events by tenant_id."""
        user = self.request.user
        tenant_id = getattr(user, 'tenant_id', None)

        if tenant_id:
            return PlatformAuditEvent.objects.filter(
                models.Q(tenant_id__isnull=True) | models.Q(tenant_id=tenant_id)
            ).order_by('-timestamp')
        return PlatformAuditEvent.objects.filter(
            tenant_id__isnull=True
        ).order_by('-timestamp')
```

**Task 2.7: Implement services.py**
```python
# backend/src/modules/platform_management/services.py
"""
Platform Management Business Logic
"""

from typing import Optional
import uuid
from .models import PlatformSetting, FeatureFlag, PlatformAuditEvent


class PlatformManagementService:
    """Business logic for platform management operations."""

    @staticmethod
    def get_setting(key: str, tenant_id: Optional[uuid.UUID] = None, default=None):
        """Get a platform setting by key."""
        try:
            if tenant_id:
                # Try tenant-specific first
                setting = PlatformSetting.objects.filter(
                    tenant_id=tenant_id, key=key
                ).first()
                if setting:
                    return setting.value

            # Fall back to platform-wide
            setting = PlatformSetting.objects.filter(
                tenant_id__isnull=True, key=key
            ).first()
            return setting.value if setting else default
        except Exception:
            return default

    @staticmethod
    def is_feature_enabled(
        name: str,
        tenant_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> bool:
        """Check if a feature flag is enabled."""
        try:
            flag = None

            # Check tenant-specific flag first
            if tenant_id:
                flag = FeatureFlag.objects.filter(
                    tenant_id=tenant_id, name=name
                ).first()

            # Fall back to platform-wide
            if not flag:
                flag = FeatureFlag.objects.filter(
                    tenant_id__isnull=True, name=name
                ).first()

            if not flag:
                return False

            if not flag.enabled:
                return False

            # Check rollout percentage
            if flag.rollout_percentage < 100 and user_id:
                # Simple hash-based rollout
                user_hash = hash(str(user_id)) % 100
                return user_hash < flag.rollout_percentage

            return flag.enabled
        except Exception:
            return False

    @staticmethod
    def log_audit_event(
        action: str,
        actor_id: uuid.UUID,
        resource_type: str,
        resource_id: Optional[uuid.UUID] = None,
        tenant_id: Optional[uuid.UUID] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None
    ) -> PlatformAuditEvent:
        """Log an immutable audit event."""
        return PlatformAuditEvent.objects.create(
            action=action,
            actor_type='user',
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            details=details or {},
            ip_address=ip_address
        )
```

**Task 2.8: Implement urls.py**
```python
# backend/src/modules/platform_management/urls.py
"""
Platform Management URL Configuration
"""

from rest_framework.routers import DefaultRouter
from .api import (
    PlatformSettingViewSet,
    FeatureFlagViewSet,
    SystemHealthViewSet,
    PlatformAuditEventViewSet
)

router = DefaultRouter()
router.register(r'settings', PlatformSettingViewSet, basename='platform-settings')
router.register(r'feature-flags', FeatureFlagViewSet, basename='feature-flags')
router.register(r'health', SystemHealthViewSet, basename='system-health')
router.register(r'audit-events', PlatformAuditEventViewSet, basename='audit-events')

urlpatterns = router.urls
```

**Task 2.9: Register module in main urls**
```python
# Add to backend/saraise_backend/urls.py
from django.urls import path, include

urlpatterns = [
    # ... existing urls ...
    path('api/v1/platform/', include('src.modules.platform_management.urls')),
]
```

### Day 3-4: Backend Tests

**Task 3.1: Implement test_api.py**
```python
# backend/src/modules/platform_management/tests/test_api.py
"""
Platform Management API Tests
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from ..models import PlatformSetting, FeatureFlag
import uuid


class PlatformSettingAPITestCase(TestCase):
    """Test cases for Platform Settings API."""

    def setUp(self):
        self.client = APIClient()
        self.tenant_id = str(uuid.uuid4())

        # Create mock user with tenant_id
        # Note: Use your actual user fixture
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.user.tenant_id = self.tenant_id
        self.client.force_authenticate(user=self.user)

    def test_create_setting_success(self):
        """Test: Create setting with valid data."""
        data = {
            'key': 'test_setting',
            'value': 'test_value',
            'category': 'general',
            'is_secret': False
        }
        response = self.client.post('/api/v1/platform/settings/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['key'], 'test_setting')

    def test_create_setting_validation_error(self):
        """Test: Validation error for short key."""
        data = {'key': 'a', 'value': 'test'}  # Key too short
        response = self.client.post('/api/v1/platform/settings/', data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_settings_filtered_by_tenant(self):
        """Test: List returns tenant-specific and platform-wide settings."""
        # Create platform-wide setting
        PlatformSetting.objects.create(
            tenant_id=None,
            key='platform_setting',
            value='platform_value'
        )

        # Create tenant-specific setting
        PlatformSetting.objects.create(
            tenant_id=self.tenant_id,
            key='tenant_setting',
            value='tenant_value'
        )

        # Create other tenant's setting (should not appear)
        other_tenant = str(uuid.uuid4())
        PlatformSetting.objects.create(
            tenant_id=other_tenant,
            key='other_setting',
            value='other_value'
        )

        response = self.client.get('/api/v1/platform/settings/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        keys = [s['key'] for s in response.data['results']]
        self.assertIn('platform_setting', keys)
        self.assertIn('tenant_setting', keys)
        self.assertNotIn('other_setting', keys)

    def test_secret_value_masked(self):
        """Test: Secret values are masked in response."""
        PlatformSetting.objects.create(
            tenant_id=self.tenant_id,
            key='secret_key',
            value='super_secret_password',
            is_secret=True
        )

        response = self.client.get('/api/v1/platform/settings/')

        secret_setting = next(
            s for s in response.data['results'] if s['key'] == 'secret_key'
        )
        self.assertEqual(secret_setting['value'], '********')


class FeatureFlagAPITestCase(TestCase):
    """Test cases for Feature Flags API."""

    def setUp(self):
        self.client = APIClient()
        self.tenant_id = str(uuid.uuid4())

        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.user.tenant_id = self.tenant_id
        self.client.force_authenticate(user=self.user)

    def test_toggle_feature_flag(self):
        """Test: Toggle feature flag on/off."""
        flag = FeatureFlag.objects.create(
            tenant_id=self.tenant_id,
            name='test_feature',
            enabled=False
        )

        response = self.client.post(
            f'/api/v1/platform/feature-flags/{flag.id}/toggle/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['enabled'])

        # Toggle again
        response = self.client.post(
            f'/api/v1/platform/feature-flags/{flag.id}/toggle/'
        )
        self.assertFalse(response.data['enabled'])


class SystemHealthAPITestCase(TestCase):
    """Test cases for System Health API."""

    def setUp(self):
        self.client = APIClient()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.client.force_authenticate(user=self.user)

    def test_health_summary(self):
        """Test: Get health summary."""
        from ..models import SystemHealth
        SystemHealth.objects.create(
            service_name='api',
            status='healthy'
        )
        SystemHealth.objects.create(
            service_name='database',
            status='healthy'
        )

        response = self.client.get('/api/v1/platform/health/summary/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'healthy')
        self.assertEqual(response.data['healthy'], 2)
```

**Task 3.2: Implement test_isolation.py (MANDATORY)**
```python
# backend/src/modules/platform_management/tests/test_isolation.py
"""
Tenant Isolation Tests for Platform Management

CRITICAL: These tests verify that tenants cannot access each other's data.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from ..models import PlatformSetting, FeatureFlag
import uuid


class TenantIsolationTestCase(TestCase):
    """
    CRITICAL: Tenant isolation tests.
    These tests verify that tenants cannot access each other's data.
    """

    def setUp(self):
        self.client = APIClient()

        # Tenant A
        self.tenant_a_id = str(uuid.uuid4())
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user_a = User.objects.create_user(
            username='user_a',
            password='testpass'
        )
        self.user_a.tenant_id = self.tenant_a_id

        # Tenant B
        self.tenant_b_id = str(uuid.uuid4())
        self.user_b = User.objects.create_user(
            username='user_b',
            password='testpass'
        )
        self.user_b.tenant_id = self.tenant_b_id

    def test_user_cannot_list_other_tenant_settings(self):
        """Test: User sees only their tenant's settings in list."""
        # Create setting for tenant A
        PlatformSetting.objects.create(
            tenant_id=self.tenant_a_id,
            key='tenant_a_setting',
            value='a_value'
        )

        # Create setting for tenant B
        PlatformSetting.objects.create(
            tenant_id=self.tenant_b_id,
            key='tenant_b_setting',
            value='b_value'
        )

        # Login as tenant A
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get('/api/v1/platform/settings/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        keys = [s['key'] for s in response.data['results']]
        self.assertIn('tenant_a_setting', keys)
        self.assertNotIn('tenant_b_setting', keys)

    def test_user_cannot_access_other_tenant_setting(self):
        """Test: User cannot GET other tenant's setting by ID."""
        # Create setting for tenant B
        other_setting = PlatformSetting.objects.create(
            tenant_id=self.tenant_b_id,
            key='other_setting',
            value='other_value'
        )

        # Login as tenant A
        self.client.force_authenticate(user=self.user_a)

        response = self.client.get(
            f'/api/v1/platform/settings/{other_setting.id}/'
        )

        # MUST return 404 (not 403) to hide existence
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_update_other_tenant_setting(self):
        """Test: User cannot PUT to other tenant's setting."""
        # Create setting for tenant B
        other_setting = PlatformSetting.objects.create(
            tenant_id=self.tenant_b_id,
            key='other_setting',
            value='original_value'
        )

        # Login as tenant A
        self.client.force_authenticate(user=self.user_a)

        response = self.client.put(
            f'/api/v1/platform/settings/{other_setting.id}/',
            {'key': 'other_setting', 'value': 'hacked_value'}
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify data unchanged
        other_setting.refresh_from_db()
        self.assertEqual(other_setting.value, 'original_value')

    def test_user_cannot_delete_other_tenant_setting(self):
        """Test: User cannot DELETE other tenant's setting."""
        # Create setting for tenant B
        other_setting = PlatformSetting.objects.create(
            tenant_id=self.tenant_b_id,
            key='other_setting',
            value='other_value'
        )

        # Login as tenant A
        self.client.force_authenticate(user=self.user_a)

        response = self.client.delete(
            f'/api/v1/platform/settings/{other_setting.id}/'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify setting still exists
        self.assertTrue(
            PlatformSetting.objects.filter(id=other_setting.id).exists()
        )

    def test_feature_flag_tenant_isolation(self):
        """Test: Feature flags are tenant-isolated."""
        # Create flag for tenant B
        other_flag = FeatureFlag.objects.create(
            tenant_id=self.tenant_b_id,
            name='other_feature',
            enabled=True
        )

        # Login as tenant A
        self.client.force_authenticate(user=self.user_a)

        # Try to toggle other tenant's flag
        response = self.client.post(
            f'/api/v1/platform/feature-flags/{other_flag.id}/toggle/'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify flag unchanged
        other_flag.refresh_from_db()
        self.assertTrue(other_flag.enabled)
```

**Task 3.3: Run tests and verify coverage**
```bash
cd /Users/raghunathchava/Code/saraise/backend

# Run tests with coverage
pytest src/modules/platform_management/tests/ -v --cov=src/modules/platform_management --cov-report=html --cov-report=term

# Verify coverage ≥90%
# If below 90%, add more tests until threshold met
```

### Day 4-5: Frontend Implementation

**Task 4.1: Create frontend structure**
```bash
cd /Users/raghunathchava/Code/saraise/frontend/src/modules

mkdir -p platform_management/{pages,components,services,types,tests}

touch platform_management/index.ts
touch platform_management/routes.tsx
touch platform_management/services/platform-service.ts
touch platform_management/types/index.ts
touch platform_management/pages/SettingsPage.tsx
touch platform_management/pages/FeatureFlagsPage.tsx
touch platform_management/pages/HealthDashboard.tsx
touch platform_management/pages/AuditLogPage.tsx
```

**Task 4.2: Implement types**
```typescript
// frontend/src/modules/platform_management/types/index.ts

export interface PlatformSetting {
  id: string;
  tenant_id: string | null;
  key: string;
  value: string;
  category: string;
  description: string;
  is_secret: boolean;
  data_type: 'string' | 'integer' | 'boolean' | 'json';
  created_at: string;
  updated_at: string;
}

export interface PlatformSettingCreate {
  key: string;
  value: string;
  category?: string;
  description?: string;
  is_secret?: boolean;
  data_type?: string;
}

export interface FeatureFlag {
  id: string;
  tenant_id: string | null;
  name: string;
  enabled: boolean;
  description: string;
  rollout_percentage: number;
  created_at: string;
  updated_at: string;
}

export interface FeatureFlagCreate {
  name: string;
  enabled?: boolean;
  description?: string;
  rollout_percentage?: number;
}

export interface SystemHealth {
  id: string;
  service_name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  last_check: string;
  response_time_ms: number | null;
  details: Record<string, unknown>;
  error_message: string;
}

export interface HealthSummary {
  status: 'healthy' | 'degraded' | 'unhealthy';
  healthy: number;
  degraded: number;
  unhealthy: number;
  total: number;
  timestamp: string;
}

export interface AuditEvent {
  id: string;
  tenant_id: string | null;
  action: string;
  actor_type: string;
  actor_id: string;
  resource_type: string;
  resource_id: string | null;
  timestamp: string;
  details: Record<string, unknown>;
  ip_address: string | null;
}
```

**Task 4.3: Implement API service**
```typescript
// frontend/src/modules/platform_management/services/platform-service.ts

import { apiClient } from '@/services/api-client';
import type {
  PlatformSetting,
  PlatformSettingCreate,
  FeatureFlag,
  FeatureFlagCreate,
  SystemHealth,
  HealthSummary,
  AuditEvent,
} from '../types';

const BASE_URL = '/api/v1/platform';

export const platformService = {
  // Settings
  listSettings: () =>
    apiClient.get<{ results: PlatformSetting[] }>(`${BASE_URL}/settings/`),

  getSetting: (id: string) =>
    apiClient.get<PlatformSetting>(`${BASE_URL}/settings/${id}/`),

  createSetting: (data: PlatformSettingCreate) =>
    apiClient.post<PlatformSetting>(`${BASE_URL}/settings/`, data),

  updateSetting: (id: string, data: Partial<PlatformSettingCreate>) =>
    apiClient.put<PlatformSetting>(`${BASE_URL}/settings/${id}/`, data),

  deleteSetting: (id: string) =>
    apiClient.delete(`${BASE_URL}/settings/${id}/`),

  // Feature Flags
  listFeatureFlags: () =>
    apiClient.get<{ results: FeatureFlag[] }>(`${BASE_URL}/feature-flags/`),

  getFeatureFlag: (id: string) =>
    apiClient.get<FeatureFlag>(`${BASE_URL}/feature-flags/${id}/`),

  createFeatureFlag: (data: FeatureFlagCreate) =>
    apiClient.post<FeatureFlag>(`${BASE_URL}/feature-flags/`, data),

  updateFeatureFlag: (id: string, data: Partial<FeatureFlagCreate>) =>
    apiClient.put<FeatureFlag>(`${BASE_URL}/feature-flags/${id}/`, data),

  toggleFeatureFlag: (id: string) =>
    apiClient.post<FeatureFlag>(`${BASE_URL}/feature-flags/${id}/toggle/`),

  deleteFeatureFlag: (id: string) =>
    apiClient.delete(`${BASE_URL}/feature-flags/${id}/`),

  // Health
  listHealth: () =>
    apiClient.get<{ results: SystemHealth[] }>(`${BASE_URL}/health/`),

  getHealthSummary: () =>
    apiClient.get<HealthSummary>(`${BASE_URL}/health/summary/`),

  // Audit Events
  listAuditEvents: (params?: { page?: number; limit?: number }) =>
    apiClient.get<{ results: AuditEvent[]; count: number }>(
      `${BASE_URL}/audit-events/`,
      { params }
    ),
};
```

**Task 4.4: Implement pages (reference ai_agent_management patterns)**
```typescript
// frontend/src/modules/platform_management/pages/SettingsPage.tsx

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { platformService } from '../services/platform-service';
import type { PlatformSetting, PlatformSettingCreate } from '../types';

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['platform-settings'],
    queryFn: platformService.listSettings,
  });

  const createMutation = useMutation({
    mutationFn: platformService.createSetting,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['platform-settings'] });
      setShowCreateDialog(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: platformService.deleteSetting,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['platform-settings'] });
    },
  });

  if (isLoading) {
    return <div className="p-6">Loading settings...</div>;
  }

  if (error) {
    return <div className="p-6 text-red-600">Error loading settings</div>;
  }

  const settings = data?.results || [];

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Platform Settings</h1>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Add Setting
        </button>
      </div>

      <div className="bg-white shadow rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Key
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Value
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Category
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {settings.map((setting) => (
              <tr key={setting.id}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {setting.key}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {setting.value}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {setting.category}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  <button
                    onClick={() => deleteMutation.mutate(setting.id)}
                    className="text-red-600 hover:text-red-900"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

**Task 4.5: Add routes**
```typescript
// frontend/src/modules/platform_management/routes.tsx

import { lazy } from 'react';
import type { RouteObject } from 'react-router-dom';

const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);
const FeatureFlagsPage = lazy(() =>
  import('./pages/FeatureFlagsPage').then((m) => ({ default: m.FeatureFlagsPage }))
);
const HealthDashboard = lazy(() =>
  import('./pages/HealthDashboard').then((m) => ({ default: m.HealthDashboard }))
);
const AuditLogPage = lazy(() =>
  import('./pages/AuditLogPage').then((m) => ({ default: m.AuditLogPage }))
);

export const platformManagementRoutes: RouteObject[] = [
  { path: 'platform/settings', element: <SettingsPage /> },
  { path: 'platform/feature-flags', element: <FeatureFlagsPage /> },
  { path: 'platform/health', element: <HealthDashboard /> },
  { path: 'platform/audit', element: <AuditLogPage /> },
];
```

**Task 4.6: Run frontend quality checks**
```bash
cd /Users/raghunathchava/Code/saraise/frontend

# TypeScript check
npx tsc --noEmit

# ESLint check
npx eslint src/modules/platform_management --ext .ts,.tsx --max-warnings 0

# Run tests
npm test -- src/modules/platform_management
```

### Day 5: Validation & Completion

**Task 5.1: Run full quality checks**
```bash
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
```

**Task 5.2: Generate OpenAPI schema and types**
```bash
cd /Users/raghunathchava/Code/saraise/backend
python manage.py spectacular --file schema.yml

cd ../frontend
npm run generate-types
```

**Task 5.3: Create completion report**
```bash
# Create report in reports/ folder
cat > /Users/raghunathchava/Code/saraise/reports/platform-management-complete-$(date +%Y-%m-%d).md << 'EOF'
# Platform Management Module - Completion Report

**Date:** [Current Date]
**Status:** ✅ COMPLETE

## Deliverables

### Backend
- [x] Models: PlatformSetting, FeatureFlag, SystemHealth, PlatformAuditEvent
- [x] Serializers: All CRUD serializers
- [x] ViewSets: 4 ViewSets with tenant isolation
- [x] Services: Business logic layer
- [x] URLs: Registered at /api/v1/platform/
- [x] Migrations: Created and applied

### Frontend
- [x] Types: Full TypeScript definitions
- [x] Service: API client with all endpoints
- [x] Pages: Settings, FeatureFlags, Health, AuditLog
- [x] Routes: Lazy-loaded routes

### Tests
- [x] API tests: CRUD operations
- [x] Isolation tests: Tenant isolation verified
- [x] Coverage: ≥90%

### Quality Gates
- [x] Pre-commit hooks: PASS
- [x] TypeScript: 0 errors
- [x] ESLint: 0 warnings
- [x] Black: Formatted
- [x] Flake8: PASS
- [x] MyPy: PASS

## Next Module
Tenant Management (Week 2-3)
EOF
```

---

## Week 2-3: Tenant Management Module

[Similar detailed structure as Platform Management - abbreviated for space]

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `tenant_management` |
| Type | Foundation |
| Priority | P0 |
| Dependencies | Platform Management |
| Spec Location | `docs/modules/01-foundation/tenant-management/` |
| Timeline | 5-7 days |

### Key Entities

```python
# From spec
- Tenant (name, slug, status, plan, settings, quotas)
- TenantUser (tenant_id, user_id, role, permissions)
- TenantQuota (tenant_id, resource_type, limit, used)
- TenantInvitation (tenant_id, email, role, expires_at)
```

### Implementation Checklist

- [ ] Day 1: Read spec, extract requirements
- [ ] Day 2-3: Backend (models, serializers, ViewSets, services)
- [ ] Day 3: Create migrations, register URLs
- [ ] Day 3-4: Tests (≥90% coverage, isolation tests)
- [ ] Day 4-5: Frontend (types, service, pages)
- [ ] Day 5: Validation gates, completion report

---

## Week 3-5: Security & Access Control Module

### Module Overview

| Attribute | Value |
|-----------|-------|
| Module Name | `security_access_control` |
| Type | Foundation |
| Priority | P0 (CRITICAL) |
| Dependencies | Platform Management, Tenant Management |
| Spec Location | `docs/modules/01-foundation/security-access-control/` |
| Timeline | 10-12 days (complex - Policy Engine) |
| Risk | MEDIUM |

### Key Entities

```python
# From spec
- Role (name, permissions, tenant_id)
- Permission (action, resource_type, constraints)
- Policy (name, rules, priority, tenant_id)
- PolicyRule (effect, actions, resources, conditions)
- UserRole (user_id, role_id, tenant_id)
- SecurityEvent (event_type, severity, details)
```

### Critical Integration Points

1. **Policy Engine** - Must integrate with existing policy evaluation
2. **Session Management** - Identity snapshot in sessions
3. **Tenant Isolation** - All security entities tenant-scoped

### Implementation Checklist

- [ ] Day 1-2: Read spec, understand Policy Engine integration
- [ ] Day 3-5: Backend models and Policy Engine integration
- [ ] Day 6-7: ViewSets with authorization decorators
- [ ] Day 8-9: Tests (extensive authorization tests)
- [ ] Day 10-11: Frontend (role management UI)
- [ ] Day 12: Integration testing, validation gates

---

## Phase Completion Criteria

### Mandatory Checkpoints

- [ ] All 3 modules operational (backend + frontend)
- [ ] ≥90% test coverage per module
- [ ] All pre-commit hooks passing
- [ ] Tenant isolation tests passing
- [ ] Policy Engine integration verified
- [ ] OpenAPI schema generated
- [ ] TypeScript types generated
- [ ] All 3 completion reports created

### Validation Command Sequence

```bash
# Final phase validation
cd /Users/raghunathchava/Code/saraise

# 1. Pre-commit
pre-commit run --all-files

# 2. Backend tests with coverage
cd backend
pytest src/modules/platform_management/tests/ -v --cov
pytest src/modules/tenant_management/tests/ -v --cov
pytest src/modules/security_access_control/tests/ -v --cov

# 3. Frontend checks
cd ../frontend
npx tsc --noEmit
npx eslint src/modules --max-warnings 0
npm test

# 4. Generate schema
cd ../backend
python manage.py spectacular --file schema.yml

# 5. Generate types
cd ../frontend
npm run generate-types
```

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Policy Engine complexity | 30% | HIGH | Extra week allocated, reference existing implementation |
| Template pattern deviation | 10% | LOW | Strict code review, pre-commit hooks |
| Test coverage below 90% | 20% | MEDIUM | Write tests first, continuous coverage monitoring |

---

## Document Status

**Status:** READY FOR EXECUTION  
**Last Updated:** January 5, 2026  
**Next Phase:** Phase 8 (Workflow, Metadata, DMS, Integration)

---

