"""
Tenant Isolation Tests for Platform Management

CRITICAL: These tests verify that tenants cannot access each other's data.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
import uuid

from ..models import PlatformSetting, FeatureFlag

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from src.core.user_models import UserProfile
    from unittest.mock import patch
    
    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username='user_a',
        email='usera@example.com',
        password='testpass123',
    )
    # Create UserProfile with tenant_id (skip tenant validation for tests)
    # Mock the clean method to skip tenant existence check
    with patch.object(UserProfile, 'clean'):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'tenant_id': tenant_id,
                'tenant_role': 'tenant_admin'
            }
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = 'tenant_admin'
            profile.save()
    # Force reload profile
    user = User.objects.get(pk=user.pk)
    return user


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from src.core.user_models import UserProfile
    from unittest.mock import patch
    
    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username='user_b',
        email='userb@example.com',
        password='testpass123',
    )
    # Create UserProfile with tenant_id (skip tenant validation for tests)
    with patch.object(UserProfile, 'clean'):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'tenant_id': tenant_id,
                'tenant_role': 'tenant_admin'
            }
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = 'tenant_admin'
            profile.save()
    # Force reload profile
    user = User.objects.get(pk=user.pk)
    return user


@pytest.mark.django_db
class TestTenantIsolation:
    """
    CRITICAL: Tenant isolation tests.
    These tests verify that tenants cannot access each other's data.
    """

    def test_user_cannot_list_other_tenant_settings(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User sees only their tenant's settings in list."""
        from src.core.auth_utils import get_user_tenant_id
        
        tenant_a_id_str = get_user_tenant_id(tenant_a_user)
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)
        tenant_a_id = uuid.UUID(tenant_a_id_str) if tenant_a_id_str else None
        tenant_b_id = uuid.UUID(tenant_b_id_str) if tenant_b_id_str else None

        # Create setting for tenant A
        setting_a = PlatformSetting.objects.create(
            tenant_id=tenant_a_id,
            key='tenant_a_setting',
            value='a_value'
        )

        # Create setting for tenant B
        setting_b = PlatformSetting.objects.create(
            tenant_id=tenant_b_id,
            key='tenant_b_setting',
            value='b_value'
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get('/api/v1/platform/settings/')

        assert response.status_code == status.HTTP_200_OK
        # DRF returns list directly, not paginated
        data = response.data if isinstance(response.data, list) else response.data.get('results', [])
        keys = [s['key'] for s in data]
        setting_ids = [s['id'] for s in data]
        # User A should see platform-wide + tenant A settings, but NOT tenant B settings
        assert 'tenant_a_setting' in keys
        assert str(setting_a.id) in setting_ids
        # Tenant B's setting should NOT be visible
        assert 'tenant_b_setting' not in keys
        assert str(setting_b.id) not in setting_ids

    def test_user_cannot_access_other_tenant_setting(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot GET other tenant's setting by ID."""
        from src.core.auth_utils import get_user_tenant_id
        
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)
        tenant_b_id = uuid.UUID(tenant_b_id_str) if tenant_b_id_str else None

        # Create setting for tenant B
        other_setting = PlatformSetting.objects.create(
            tenant_id=tenant_b_id,
            key='other_setting',
            value='other_value'
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)
        
        # Verify tenant IDs are different
        tenant_a_id_str = get_user_tenant_id(tenant_a_user)
        assert tenant_a_id_str is not None, "tenant_a_user should have tenant_id"
        assert tenant_a_id_str != tenant_b_id_str, "Tenant IDs should be different"

        response = api_client.get(
            f'/api/v1/platform/settings/{other_setting.id}/'
        )

        # MUST return 404 (not 403) to hide existence
        assert response.status_code == status.HTTP_404_NOT_FOUND, f"Expected 404, got {response.status_code}. Response: {response.data if hasattr(response, 'data') else 'No data'}"

    def test_user_cannot_update_other_tenant_setting(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot PUT to other tenant's setting."""
        from src.core.auth_utils import get_user_tenant_id
        
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)
        tenant_b_id = uuid.UUID(tenant_b_id_str) if tenant_b_id_str else None

        # Create setting for tenant B
        other_setting = PlatformSetting.objects.create(
            tenant_id=tenant_b_id,
            key='other_setting',
            value='original_value'
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.put(
            f'/api/v1/platform/settings/{other_setting.id}/',
            {'key': 'other_setting', 'value': 'hacked_value'},
            format='json'
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify data unchanged
        other_setting.refresh_from_db()
        assert other_setting.value == 'original_value'

    def test_user_cannot_delete_other_tenant_setting(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: User cannot DELETE other tenant's setting."""
        from src.core.auth_utils import get_user_tenant_id
        
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)
        tenant_b_id = uuid.UUID(tenant_b_id_str) if tenant_b_id_str else None

        # Create setting for tenant B
        other_setting = PlatformSetting.objects.create(
            tenant_id=tenant_b_id,
            key='other_setting',
            value='other_value'
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.delete(
            f'/api/v1/platform/settings/{other_setting.id}/'
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify setting still exists
        assert PlatformSetting.objects.filter(id=other_setting.id).exists()

    def test_feature_flag_tenant_isolation(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        """Test: Feature flags are tenant-isolated."""
        from src.core.auth_utils import get_user_tenant_id
        
        tenant_b_id_str = get_user_tenant_id(tenant_b_user)
        tenant_b_id = uuid.UUID(tenant_b_id_str) if tenant_b_id_str else None

        # Create flag for tenant B
        other_flag = FeatureFlag.objects.create(
            tenant_id=tenant_b_id,
            name='other_feature',
            enabled=True
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to toggle other tenant's flag
        response = api_client.post(
            f'/api/v1/platform/feature-flags/{other_flag.id}/toggle/'
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify flag unchanged
        other_flag.refresh_from_db()
        assert other_flag.enabled is True

