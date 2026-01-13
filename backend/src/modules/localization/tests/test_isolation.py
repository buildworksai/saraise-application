"""
Tenant Isolation Tests for Localization module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.localization.models import (
    CurrencyConfig,
    Language,
    LocaleConfig,
    RegionalSettings,
    Translation,
)
from src.core.auth_utils import get_user_tenant_id

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestTranslationTenantIsolation:
    """Tenant isolation tests for Translation model."""

    def test_user_cannot_list_other_tenant_translations(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's translations in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create language
        language = Language.objects.create(
            code="en",
            name="English",
            native_name="English",
        )

        # Create translations
        translation_a = Translation.objects.create(
            tenant_id=tenant_a_id,
            language=language,
            key="common.save",
            value="Save (Tenant A)",
        )

        translation_b = Translation.objects.create(
            tenant_id=tenant_b_id,
            language=language,
            key="common.save",
            value="Save (Tenant B)",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/localization/translations/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        translation_ids = [t["id"] for t in data]

        # User A should see tenant A's translation, but NOT tenant B's translation
        assert translation_a.id in translation_ids
        assert translation_b.id not in translation_ids


@pytest.mark.django_db
class TestLocaleConfigTenantIsolation:
    """Tenant isolation tests for LocaleConfig model."""

    def test_user_cannot_list_other_tenant_locale_configs(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's locale configs in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create language
        language = Language.objects.create(
            code="en",
            name="English",
            native_name="English",
        )

        # Create locale configs
        config_a = LocaleConfig.objects.create(
            tenant_id=tenant_a_id,
            default_language=language,
            timezone="America/New_York",
        )

        config_b = LocaleConfig.objects.create(
            tenant_id=tenant_b_id,
            default_language=language,
            timezone="Europe/London",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/localization/locale-configs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        config_ids = [c["id"] for c in data]

        # User A should see tenant A's config, but NOT tenant B's config
        assert config_a.id in config_ids
        assert config_b.id not in config_ids


@pytest.mark.django_db
class TestCurrencyConfigTenantIsolation:
    """Tenant isolation tests for CurrencyConfig model."""

    def test_user_cannot_list_other_tenant_currency_configs(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's currency configs in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create currency configs
        config_a = CurrencyConfig.objects.create(
            tenant_id=tenant_a_id,
            default_currency="USD",
        )

        config_b = CurrencyConfig.objects.create(
            tenant_id=tenant_b_id,
            default_currency="EUR",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/localization/currency-configs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        config_ids = [c["id"] for c in data]

        # User A should see tenant A's config, but NOT tenant B's config
        assert config_a.id in config_ids
        assert config_b.id not in config_ids


@pytest.mark.django_db
class TestRegionalSettingsTenantIsolation:
    """Tenant isolation tests for RegionalSettings model."""

    def test_user_cannot_list_other_tenant_regional_settings(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's regional settings in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create regional settings
        settings_a = RegionalSettings.objects.create(
            tenant_id=tenant_a_id,
            country_code="US",
        )

        settings_b = RegionalSettings.objects.create(
            tenant_id=tenant_b_id,
            country_code="GB",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/localization/regional-settings/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        settings_ids = [s["id"] for s in data]

        # User A should see tenant A's settings, but NOT tenant B's settings
        assert settings_a.id in settings_ids
        assert settings_b.id not in settings_ids
