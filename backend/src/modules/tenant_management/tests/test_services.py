"""
Tenant Management Service Tests
"""

from datetime import date, timedelta

import pytest

from src.modules.tenant_management.models import Tenant, TenantModule
from src.modules.tenant_management.services import TenantManagementService


@pytest.mark.django_db
class TestTenantManagementService:
    """Test TenantManagementService business logic."""

    # ⚠️ ARCHITECTURAL NOTE: Lifecycle operations removed from service
    # These operations MUST be performed via Control Plane services.
    # Tests for lifecycle operations are removed per architectural compliance.
    #
    # Removed tests:
    # - test_create_tenant → Use Control Plane
    # - test_activate_tenant → Use Control Plane
    # - test_suspend_tenant → Use Control Plane
    # - test_cancel_tenant → Use Control Plane
    # - test_archive_tenant → Use Control Plane
    # - test_install_module → Use Control Plane
    # - test_enable_disable_module → Use Control Plane
    # - test_uninstall_module → Use Control Plane

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
        from src.modules.tenant_management.models import TenantSettings

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

    def test_get_tenant_setting_returns_default_for_missing_tenant_or_setting(self):
        tenant = Tenant.objects.create(name="Settings Tenant", slug="settings-tenant", subdomain="settings")

        assert TenantManagementService.get_tenant_setting(
            tenant.id, "email", "missing", default={"enabled": False}
        ) == {"enabled": False}
        assert (
            TenantManagementService.get_tenant_setting("00000000-0000-0000-0000-000000000000", "email", "host", "x")
            == "x"
        )

    @pytest.mark.parametrize(
        ("active_users", "api_calls", "response_time", "errors", "expected_reason"),
        (
            (0, 0, 1500.0, 75, "high_error_rate"),
            (0, 0, 1500.0, 0, "slow_performance"),
            (0, 0, None, 0, "no_active_users"),
        ),
    )
    def test_calculate_health_score_records_at_risk_reasons(
        self, active_users, api_calls, response_time, errors, expected_reason
    ):
        tenant = Tenant.objects.create(name="Risk Tenant", slug=f"risk-{expected_reason}", subdomain=expected_reason)
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today(),
            active_users=active_users,
            api_calls=api_calls,
            avg_response_time_ms=response_time,
            error_count=errors,
        )

        health_score = TenantManagementService.calculate_health_score(tenant.id)

        assert expected_reason in health_score.at_risk_reasons

    def test_record_resource_usage_defaults_when_only_required_args_given(self):
        """Test: all optional args default correctly (kills mutants on default kwargs)."""
        tenant = Tenant.objects.create(name="Default Tenant", slug="default-tenant", subdomain="default-tenant")
        usage = TenantManagementService.record_resource_usage(tenant_id=tenant.id, date=date.today())
        assert usage.active_users == 0
        assert usage.api_calls == 0
        assert float(usage.storage_used_gb) == 0.0
        assert float(usage.bandwidth_used_gb) == 0.0
        assert usage.email_sent == 0
        assert usage.sms_sent == 0
        assert usage.avg_response_time_ms is None
        assert usage.error_count == 0
        assert usage.slow_query_count == 0

    def test_record_resource_usage_updates_existing_record_for_same_date(self):
        """update_or_create must UPDATE, not duplicate, when called twice for same tenant+date."""
        tenant = Tenant.objects.create(name="Update Tenant", slug="update-tenant", subdomain="update-tenant")
        today = date.today()
        TenantManagementService.record_resource_usage(tenant_id=tenant.id, date=today, active_users=1, api_calls=10)
        second = TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=today, active_users=99, api_calls=999
        )
        assert second.active_users == 99
        assert second.api_calls == 999
        assert tenant.resource_usage.filter(date=today).count() == 1

    def test_get_resource_usage_summary_with_no_records_returns_zero_defaults(self):
        """Aggregates on an empty queryset must fall back to 0 / None, not raise or return None-as-int."""
        tenant = Tenant.objects.create(name="Empty Tenant", slug="empty-tenant", subdomain="empty-tenant")
        summary = TenantManagementService.get_resource_usage_summary(tenant.id, days=30)
        assert summary["total_api_calls"] == 0
        assert summary["avg_api_calls_per_day"] == 0
        assert summary["max_storage_gb"] == 0
        assert summary["avg_active_users"] == 0
        assert summary["total_errors"] == 0
        assert summary["avg_response_time_ms"] is None
        assert summary["tenant_name"] == "Empty Tenant"
        assert summary["period_days"] == 30

    def test_get_resource_usage_summary_excludes_records_outside_window(self):
        """date__gte filter must exclude usage older than the requested window (kills > / >= mutants)."""
        tenant = Tenant.objects.create(name="Window Tenant", slug="window-tenant", subdomain="window-tenant")
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today() - timedelta(days=10), active_users=5, api_calls=500
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today() - timedelta(days=1), active_users=5, api_calls=500
        )
        summary = TenantManagementService.get_resource_usage_summary(tenant.id, days=5)
        assert summary["total_api_calls"] == 500

    def test_get_resource_usage_summary_default_days_is_thirty(self):
        """Default days=30 must actually be used when the caller omits it."""
        tenant = Tenant.objects.create(name="Default Days Tenant", slug="default-days", subdomain="default-days")
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today() - timedelta(days=29), active_users=1, api_calls=1
        )
        summary = TenantManagementService.get_resource_usage_summary(tenant.id)
        assert summary["period_days"] == 30
        assert summary["total_api_calls"] == 1

    def test_get_tenant_setting_returns_value_not_default_when_found(self):
        from src.modules.tenant_management.models import TenantSettings

        tenant = Tenant.objects.create(name="Found Tenant", slug="found-tenant", subdomain="found-tenant")
        TenantSettings.objects.create(
            tenant=tenant, category="sms", key="provider", value={"name": "twilio"}, updated_by="u1"
        )
        value = TenantManagementService.get_tenant_setting(tenant.id, "sms", "provider", default="nope")
        assert value == {"name": "twilio"}

    def test_get_tenant_setting_default_arg_is_none(self):
        """When default is omitted, missing setting must return exactly None (not some other falsy value)."""
        tenant = Tenant.objects.create(name="None Default Tenant", slug="none-default", subdomain="none-default")
        assert TenantManagementService.get_tenant_setting(tenant.id, "cat", "key") is None

    def test_calculate_health_score_with_no_usage_records_uses_all_defaults(self):
        """No resource usage at all: usage is None, every component score stays the 50 default."""
        tenant = Tenant.objects.create(name="No Usage Tenant", slug="no-usage-tenant", subdomain="no-usage-tenant")
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.usage_score == 50
        assert health_score.performance_score == 50
        assert health_score.error_score == 50
        assert health_score.engagement_score == 50
        assert health_score.overall_score == 50
        assert health_score.churn_risk == 50
        assert health_score.at_risk_reasons == []

    def test_calculate_health_score_falls_back_to_latest_usage_when_target_date_missing(self):
        """If no usage exists for target_date, must fall back to the most recent usage record."""
        tenant = Tenant.objects.create(name="Fallback Tenant", slug="fallback-tenant", subdomain="fallback-tenant")
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today() - timedelta(days=3),
            active_users=5,
            api_calls=100,
            error_count=0,
        )
        health_score = TenantManagementService.calculate_health_score(
            tenant.id, target_date=date.today() - timedelta(days=1)
        )
        # error_count=0 on the fallback record must drive error_score to 100, proving fallback was used.
        assert health_score.error_score == 100

    def test_calculate_health_score_usage_score_clamped_at_100_when_over_max_users(self):
        """active_users far beyond max_users must clamp usage_score to 100, not exceed it."""
        tenant = Tenant.objects.create(
            name="Overcap Tenant", slug="overcap-tenant", subdomain="overcap-tenant", max_users=5
        )
        TenantManagementService.record_resource_usage(tenant_id=tenant.id, date=date.today(), active_users=50)
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.usage_score == 100

    def test_calculate_health_score_usage_score_exact_ratio(self):
        """active_users exactly half of max_users must give usage_score == 50."""
        tenant = Tenant.objects.create(
            name="HalfCap Tenant", slug="halfcap-tenant", subdomain="halfcap-tenant", max_users=10
        )
        TenantManagementService.record_resource_usage(tenant_id=tenant.id, date=date.today(), active_users=5)
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.usage_score == 50

    @pytest.mark.parametrize(
        ("response_time_ms", "expected_performance_score"),
        (
            (99.0, 100),
            (100.0, 80),
            (499.0, 80),
            (500.0, 60),
            (999.0, 60),
            (1000.0, 40),
            (5000.0, 40),
        ),
    )
    def test_calculate_health_score_performance_score_boundaries(self, response_time_ms, expected_performance_score):
        tenant = Tenant.objects.create(
            name="Perf Tenant",
            slug=f"perf-{int(response_time_ms)}",
            subdomain=f"perf-{int(response_time_ms)}",
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today(), active_users=1, avg_response_time_ms=response_time_ms
        )
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.performance_score == expected_performance_score

    @pytest.mark.parametrize(
        ("error_count", "expected_error_score"),
        (
            (0, 100),
            (1, 80),
            (9, 80),
            (10, 60),
            (49, 60),
            (50, 40),
            (500, 40),
        ),
    )
    def test_calculate_health_score_error_score_boundaries(self, error_count, expected_error_score):
        tenant = Tenant.objects.create(
            name="Error Tenant", slug=f"error-{error_count}", subdomain=f"error-{error_count}"
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today(), active_users=1, error_count=error_count
        )
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.error_score == expected_error_score

    @pytest.mark.parametrize(
        ("api_calls", "expected_engagement_score"),
        (
            (0, 50),  # api_calls not > 0 -> stays default
            (5000, 50),
            (10000, 100),
            (50000, 100),
        ),
    )
    def test_calculate_health_score_engagement_score_boundaries(self, api_calls, expected_engagement_score):
        tenant = Tenant.objects.create(
            name="Engage Tenant", slug=f"engage-{api_calls}", subdomain=f"engage-{api_calls}"
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today(), active_users=1, api_calls=api_calls
        )
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.engagement_score == expected_engagement_score

    def test_calculate_health_score_overall_score_weighted_average_exact(self):
        """Pin the exact weighted-average formula: 0.3/0.3/0.2/0.2 over usage/perf/error/engagement."""
        tenant = Tenant.objects.create(
            name="Weighted Tenant", slug="weighted-tenant", subdomain="weighted-tenant", max_users=10
        )
        # active_users=10 -> usage_score=100; response<100 -> performance=100;
        # error_count=0 -> error_score=100; api_calls=10000 -> engagement=100
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today(),
            active_users=10,
            api_calls=10000,
            avg_response_time_ms=50.0,
            error_count=0,
        )
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.usage_score == 100
        assert health_score.performance_score == 100
        assert health_score.error_score == 100
        assert health_score.engagement_score == 100
        # 100*0.3 + 100*0.3 + 100*0.2 + 100*0.2 = 100
        assert health_score.overall_score == 100
        assert health_score.churn_risk == 0

    def test_calculate_health_score_low_health_triggers_low_health_score_reason(self):
        """overall_score < 50 must append 'low_health_score' to at_risk_reasons."""
        tenant = Tenant.objects.create(
            name="LowHealth Tenant", slug="lowhealth-tenant", subdomain="lowhealth-tenant", max_users=1000
        )
        # active_users small relative to max_users -> low usage_score; slow response -> low performance;
        # many errors -> low error_score; api_calls small -> low engagement.
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today(),
            active_users=1,
            api_calls=1,
            avg_response_time_ms=5000.0,
            error_count=500,
        )
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.overall_score < 50
        assert "low_health_score" in health_score.at_risk_reasons

    def test_calculate_health_score_healthy_tenant_has_no_at_risk_reasons(self):
        """A fully healthy tenant must not accumulate any at_risk_reasons."""
        tenant = Tenant.objects.create(
            name="Healthy Tenant", slug="healthy-tenant", subdomain="healthy-tenant", max_users=10
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id,
            date=date.today(),
            active_users=10,
            api_calls=10000,
            avg_response_time_ms=50.0,
            error_count=0,
        )
        health_score = TenantManagementService.calculate_health_score(tenant.id)
        assert health_score.at_risk_reasons == []

    def test_calculate_health_score_updates_existing_record_for_same_date(self):
        """update_or_create on TenantHealthScore must overwrite, not duplicate, for the same date."""
        tenant = Tenant.objects.create(name="Recalc Tenant", slug="recalc-tenant", subdomain="recalc-tenant")
        today = date.today()
        TenantManagementService.record_resource_usage(tenant_id=tenant.id, date=today, active_users=1, error_count=0)
        first = TenantManagementService.calculate_health_score(tenant.id, target_date=today)
        assert first.error_score == 100

        TenantManagementService.record_resource_usage(tenant_id=tenant.id, date=today, active_users=1, error_count=100)
        second = TenantManagementService.calculate_health_score(tenant.id, target_date=today)
        assert second.error_score == 40
        assert tenant.health_scores.filter(date=today).count() == 1

    def test_get_tenant_summary_with_no_usage_or_health_returns_none_sections(self):
        """A brand new tenant with no usage/health records must yield None sections, not raise."""
        tenant = Tenant.objects.create(name="Fresh Tenant", slug="fresh-tenant", subdomain="fresh-tenant")
        summary = TenantManagementService.get_tenant_summary(tenant.id)
        assert summary["resource_usage"] is None
        assert summary["health"] is None
        assert summary["modules"]["enabled"] == 0
        assert summary["modules"]["total"] == 0
        assert summary["tenant"]["status"] == tenant.status
        assert summary["tenant"]["slug"] == tenant.slug
        assert summary["tenant"]["subscription_plan_id"] == tenant.subscription_plan_id

    def test_get_tenant_summary_reports_disabled_modules_in_total_but_not_enabled(self):
        tenant = Tenant.objects.create(name="Modules Tenant", slug="modules-tenant", subdomain="modules-tenant")
        TenantModule.objects.create(tenant=tenant, module_name="crm", is_enabled=True)
        TenantModule.objects.create(tenant=tenant, module_name="inventory", is_enabled=False)
        summary = TenantManagementService.get_tenant_summary(tenant.id)
        assert summary["modules"]["enabled"] == 1
        assert summary["modules"]["total"] == 2

    def test_get_tenant_summary_uses_latest_usage_and_health_by_date(self):
        """Must select the most recent usage/health record (order_by('-date').first()), not the oldest."""
        tenant = Tenant.objects.create(name="Latest Tenant", slug="latest-tenant", subdomain="latest-tenant")
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today() - timedelta(days=1), active_users=1, api_calls=1
        )
        TenantManagementService.record_resource_usage(
            tenant_id=tenant.id, date=date.today(), active_users=42, api_calls=4242
        )
        TenantManagementService.calculate_health_score(tenant.id, target_date=date.today() - timedelta(days=1))
        TenantManagementService.calculate_health_score(tenant.id, target_date=date.today())

        summary = TenantManagementService.get_tenant_summary(tenant.id)
        assert summary["resource_usage"]["active_users"] == 42
        assert summary["resource_usage"]["api_calls_today"] == 4242
