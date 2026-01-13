import uuid

import pytest

from src.modules.platform_management.models import FeatureFlag, PlatformMetrics, PlatformSetting
from src.modules.platform_management.services import AnalyticsService, PlatformManagementService


@pytest.mark.django_db
class TestPlatformManagementService:
    """Test cases for Platform Management Service."""

    def test_get_setting_tenant_specific(self):
        """Test: Get tenant-specific setting."""
        tenant_id = uuid.uuid4()
        PlatformSetting.objects.create(tenant_id=tenant_id, key="tenant_setting", value="tenant_value")

        result = PlatformManagementService.get_setting("tenant_setting", tenant_id)
        assert result == "tenant_value"

    def test_get_setting_platform_wide(self):
        """Test: Get platform-wide setting."""
        PlatformSetting.objects.create(tenant_id=None, key="platform_setting", value="platform_value")

        result = PlatformManagementService.get_setting("platform_setting")
        assert result == "platform_value"

    def test_get_setting_fallback_to_platform(self):
        """Test: Fallback to platform-wide when tenant-specific not found."""
        PlatformSetting.objects.create(tenant_id=None, key="fallback_setting", value="platform_value")

        tenant_id = uuid.uuid4()
        result = PlatformManagementService.get_setting("fallback_setting", tenant_id)
        assert result == "platform_value"

    def test_get_setting_not_found(self):
        """Test: Return default when setting not found."""
        result = PlatformManagementService.get_setting("nonexistent", default="default_value")
        assert result == "default_value"

    def test_get_setting_string_tenant_id(self):
        """Test: Handle string tenant_id."""
        tenant_id = uuid.uuid4()
        PlatformSetting.objects.create(tenant_id=tenant_id, key="string_tenant_setting", value="string_value")

        result = PlatformManagementService.get_setting("string_tenant_setting", str(tenant_id))
        assert result == "string_value"

    def test_get_setting_invalid_tenant_id(self):
        """Test: Invalid tenant_id returns default."""
        result = PlatformManagementService.get_setting(
            "missing_setting",
            tenant_id="not-a-uuid",
            default="default_value",
        )
        assert result == "default_value"

    def test_is_feature_enabled_tenant_specific(self):
        """Test: Check tenant-specific feature flag."""
        tenant_id = uuid.uuid4()
        FeatureFlag.objects.create(tenant_id=tenant_id, name="tenant_feature", enabled=True)

        result = PlatformManagementService.is_feature_enabled("tenant_feature", tenant_id)
        assert result is True

    def test_is_feature_enabled_platform_wide(self):
        """Test: Check platform-wide feature flag."""
        FeatureFlag.objects.create(tenant_id=None, name="platform_feature", enabled=True)

        result = PlatformManagementService.is_feature_enabled("platform_feature")
        assert result is True

    def test_is_feature_enabled_disabled(self):
        """Test: Feature flag disabled."""
        FeatureFlag.objects.create(tenant_id=None, name="disabled_feature", enabled=False)

        result = PlatformManagementService.is_feature_enabled("disabled_feature")
        assert result is False

    def test_is_feature_enabled_rollout_percentage(self):
        """Test: Feature flag with rollout percentage."""
        FeatureFlag.objects.create(tenant_id=None, name="rollout_feature", enabled=True, rollout_percentage=50)

        # Test with user_id (should use hash-based rollout)
        user_id = uuid.uuid4()
        result = PlatformManagementService.is_feature_enabled("rollout_feature", user_id=user_id)
        # Result depends on hash, so just verify it doesn't crash
        assert isinstance(result, bool)

    def test_is_feature_enabled_invalid_tenant_id(self):
        """Test: Invalid tenant_id returns False."""
        result = PlatformManagementService.is_feature_enabled(
            "missing_feature",
            tenant_id="invalid-uuid",
        )
        assert result is False

    def test_log_audit_event(self):
        """Test: Log audit event."""
        actor_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        event = PlatformManagementService.log_audit_event(
            action="test.action",
            actor_id=actor_id,
            resource_type="TestResource",
            resource_id=resource_id,
            tenant_id=tenant_id,
            details={"key": "value"},
            ip_address="127.0.0.1",
        )

        assert event.action == "test.action"
        assert event.actor_id == actor_id
        assert event.resource_type == "TestResource"
        assert event.resource_id == resource_id
        assert event.tenant_id == tenant_id
        assert event.details == {"key": "value"}
        assert event.ip_address == "127.0.0.1"

    def test_log_audit_event_string_ids(self):
        """Test: Log audit event with string IDs."""
        actor_id = uuid.uuid4()
        resource_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        event = PlatformManagementService.log_audit_event(
            action="test.action",
            actor_id=str(actor_id),
            resource_type="TestResource",
            resource_id=str(resource_id),
            tenant_id=str(tenant_id),
        )

        assert event.actor_id == actor_id
        assert event.resource_id == resource_id
        assert event.tenant_id == tenant_id


@pytest.mark.django_db
class TestAnalyticsService:
    """Test cases for Analytics Service."""

    def test_get_metrics_complete(self):
        service = AnalyticsService()
        metrics = service.get_metrics(PlatformMetrics.MetricType.COMPLETE, "30d")
        assert "api_metrics" in metrics
        assert "tenant_metrics" in metrics

    def test_get_metrics_api(self):
        service = AnalyticsService()
        metrics = service.get_metrics(PlatformMetrics.MetricType.API, "7d")
        assert "total_requests" in metrics

    def test_save_metrics(self):
        service = AnalyticsService()
        metric = service.save_metrics(
            metric_type=PlatformMetrics.MetricType.API,
            time_range="7d",
        )
        assert metric.metric_type == PlatformMetrics.MetricType.API
