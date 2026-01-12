"""
Tenant Management Service Tests
"""

from datetime import date, timedelta

import pytest

from ..models import Tenant, TenantModule
from ..services import TenantManagementService


@pytest.mark.django_db
class TestTenantManagementService:
    """Test TenantManagementService business logic."""

    def test_create_tenant(self):
        """Test: Create tenant with service."""
        tenant = TenantManagementService.create_tenant(
            name="Service Test Tenant",
            slug="service-test-tenant",
            created_by="test-user-id",
        )
        assert tenant.id is not None
        assert tenant.name == "Service Test Tenant"
        assert tenant.created_by == "test-user-id"

    def test_activate_tenant(self):
        """Test: Activate tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", status=Tenant.TenantStatus.TRIAL)
        activated = TenantManagementService.activate_tenant(tenant.id)
        assert activated.status == Tenant.TenantStatus.ACTIVE

    def test_suspend_tenant(self):
        """Test: Suspend tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", status=Tenant.TenantStatus.ACTIVE)
        suspended = TenantManagementService.suspend_tenant(tenant.id)
        assert suspended.status == Tenant.TenantStatus.SUSPENDED

    def test_cancel_tenant(self):
        """Test: Cancel tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", status=Tenant.TenantStatus.ACTIVE)
        cancelled = TenantManagementService.cancel_tenant(tenant.id)
        assert cancelled.status == Tenant.TenantStatus.CANCELLED

    def test_archive_tenant(self):
        """Test: Archive tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", status=Tenant.TenantStatus.ACTIVE)
        archived = TenantManagementService.archive_tenant(tenant.id)
        assert archived.status == Tenant.TenantStatus.ARCHIVED

    def test_install_module(self):
        """Test: Install module for tenant."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        module = TenantManagementService.install_module(
            tenant_id=tenant.id,
            module_name="crm",
            installed_by="test-user-id",
            version="1.0.0",
        )
        assert module.module_name == "crm"
        assert module.is_enabled is True
        assert module.version == "1.0.0"

    def test_enable_disable_module(self):
        """Test: Enable and disable module."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=False)

        enabled = TenantManagementService.enable_module(tenant.id, "crm")
        assert enabled.is_enabled is True

        disabled = TenantManagementService.disable_module(tenant.id, "crm")
        assert disabled.is_enabled is False

    def test_uninstall_module(self):
        """Test: Uninstall module."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=True)
        TenantManagementService.uninstall_module(tenant.id, "crm")
        assert not TenantModule.objects.filter(tenant=tenant, module_name="crm").exists()

    def test_record_resource_usage(self):
        """Test: Record resource usage."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        usage = TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today(),
            active_users=10,
            api_calls=1000,
            storage_used_gb=5.5,
        )
        assert usage.active_users == 10
        assert usage.api_calls == 1000
        assert float(usage.storage_used_gb) == 5.5

    def test_get_resource_usage_summary(self):
        """Test: Get resource usage summary."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today(), active_users=10, api_calls=1000
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today() - timedelta(days=1),
            active_users=8,
            api_calls=800,
        )

        summary = TenantManagementService.get_resource_usage_summary(tenant.id, days=30)
        assert summary["tenant_id"] == tenant.id
        assert summary["total_api_calls"] == 1800
        assert summary["avg_api_calls_per_day"] == 900

    def test_set_get_tenant_setting(self):
        """Test: Set and get tenant setting."""
        from ..models import TenantSettings

        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        # Create setting directly (set_tenant_setting was removed for architectural reasons)
        TenantSettings.objects.create(
            tenant=tenant,
            category="email",
            key="smtp_host",
            value={"host": "smtp.example.com"},
            updated_by="test-user-id",
        )

        value = TenantManagementService.get_tenant_setting(tenant_id=tenant.id, category="email", key="smtp_host")
        assert value == {"host": "smtp.example.com"}

    def test_calculate_health_score(self):
        """Test: Calculate health score."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", max_users=20)
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today(),
            active_users=15,
            api_calls=5000,
            avg_response_time_ms=150.0,
            error_count=5,
        )

        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.overall_score is not None
        assert 0 <= health_score.overall_score <= 100
        assert health_score.usage_score is not None
        assert health_score.performance_score is not None

    def test_get_tenant_summary(self):
        """Test: Get tenant summary."""
        tenant = Tenant.objects.create(name="Test Tenant", slug="test-tenant", subdomain="test-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=True)
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today(), active_users=10, api_calls=1000
        )
        TenantManagementService.calculate_health_score(tenant.id)

        summary = TenantManagementService.get_tenant_summary(tenant.id)
        assert summary["tenant"]["id"] == tenant.id
        assert summary["modules"]["enabled"] == 1
        assert summary["resource_usage"] is not None
        assert summary["health"] is not None
