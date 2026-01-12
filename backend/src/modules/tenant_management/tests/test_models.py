"""
Tenant Management Model Tests
"""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from ..models import Tenant, TenantHealthScore, TenantModule, TenantResourceUsage, TenantSettings


@pytest.mark.django_db
class TestTenantModel:
    """Test Tenant model."""

    def test_create_tenant(self):
        """Test: Create tenant with required fields."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        assert tenant.id is not None
        assert tenant.name == "Test Tenant"
        assert tenant.slug == "test-tenant"
        assert tenant.status == Tenant.TenantStatus.TRIAL

    def test_tenant_str(self):
        """Test: Tenant string representation."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        assert str(tenant) == "Test Tenant (test-tenant)"

    def test_tenant_is_trial(self):
        """Test: Tenant trial status check."""
        tenant = Tenant.objects.create(
            name="Test Tenant",
            slug="test-tenant",
            status=Tenant.TenantStatus.TRIAL,
            trial_ends_at=timezone.now() + timedelta(days=14),
        )
        assert tenant.is_trial is True

    def test_tenant_is_active(self):
        """Test: Tenant active status check."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", status=Tenant.TenantStatus.ACTIVE)
        assert tenant.is_active is True

    def test_tenant_slug_validation(self):
        """Test: Slug must be unique."""
        Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        # Try to create another with same slug
        with pytest.raises(Exception):  # IntegrityError or ValidationError
            Tenant.objects.create(name="Another Tenant", slug="test-tenant")


@pytest.mark.django_db
class TestTenantModuleModel:
    """Test TenantModule model."""

    def test_create_tenant_module(self):
        """Test: Create tenant module."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        module = TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=True)
        assert module.id is not None
        assert module.tenant == tenant
        assert module.module_name == "crm"
        assert module.is_enabled is True

    def test_tenant_module_unique_together(self):
        """Test: Tenant and module_name must be unique together."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm")
        # Try to create duplicate
        with pytest.raises(Exception):  # IntegrityError
            TenantModule.objects.create(tenant=tenant, module_name="crm")


@pytest.mark.django_db
class TestTenantResourceUsageModel:
    """Test TenantResourceUsage model."""

    def test_create_resource_usage(self):
        """Test: Create resource usage record."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        usage = TenantResourceUsage.objects.create(
            tenant=tenant,
            date=date.today(),
            active_users=10,
            api_calls=1000,
            storage_used_gb=5.5,
        )
        assert usage.id is not None
        assert usage.active_users == 10
        assert usage.api_calls == 1000
        assert float(usage.storage_used_gb) == 5.5

    def test_resource_usage_unique_together(self):
        """Test: Tenant and date must be unique together."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        TenantResourceUsage.objects.create(tenant=tenant, date=date.today(), active_users=10)
        # Try to create duplicate
        with pytest.raises(Exception):  # IntegrityError
            TenantResourceUsage.objects.create(tenant=tenant, date=date.today(), active_users=20)


@pytest.mark.django_db
class TestTenantSettingsModel:
    """Test TenantSettings model."""

    def test_create_tenant_setting(self):
        """Test: Create tenant setting."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        setting = TenantSettings.objects.create(
            tenant=tenant,
            category="email",
            key="smtp_host",
            value={"host": "smtp.example.com"},
        )
        assert setting.id is not None
        assert setting.category == "email"
        assert setting.key == "smtp_host"

    def test_tenant_settings_unique_together(self):
        """Test: Tenant, category, and key must be unique together."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        TenantSettings.objects.create(
            tenant=tenant,
            category="email",
            key="smtp_host",
            value={"host": "smtp.example.com"},
        )
        # Try to create duplicate
        with pytest.raises(Exception):  # IntegrityError
            TenantSettings.objects.create(
                tenant=tenant,
                category="email",
                key="smtp_host",
                value={"host": "smtp.other.com"},
            )


@pytest.mark.django_db
class TestTenantHealthScoreModel:
    """Test TenantHealthScore model."""

    def test_create_health_score(self):
        """Test: Create health score."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        health_score = TenantHealthScore.objects.create(
            tenant=tenant,
            date=date.today(),
            overall_score=85,
            usage_score=90,
            performance_score=80,
            error_score=85,
            engagement_score=90,
        )
        assert health_score.id is not None
        assert health_score.overall_score == 85
        assert health_score.churn_risk is None  # Not set in this test

    def test_health_score_unique_together(self):
        """Test: Tenant and date must be unique together."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant")
        TenantHealthScore.objects.create(tenant=tenant, date=date.today(), overall_score=85)
        # Try to create duplicate
        with pytest.raises(Exception):  # IntegrityError
            TenantHealthScore.objects.create(tenant=tenant, date=date.today(), overall_score=90)
