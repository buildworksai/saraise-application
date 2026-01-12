"""
Platform Management Model Tests
"""

import uuid

import pytest

from ..models import FeatureFlag, PlatformAuditEvent, PlatformSetting, SystemHealth


@pytest.mark.django_db
class TestPlatformSettingModel:
    """Unit tests for PlatformSetting model."""

    def test_create_setting_with_valid_data(self):
        """PlatformSetting can be created with valid data."""
        setting = PlatformSetting.objects.create(
            tenant_id=None, key="test_setting", value="test_value", category="general"  # Platform-wide
        )
        assert setting.id is not None
        assert setting.key == "test_setting"
        assert setting.value == "test_value"

    def test_create_setting_with_tenant_id(self):
        """PlatformSetting can be created with tenant_id."""
        tenant_id = uuid.uuid4()
        setting = PlatformSetting.objects.create(tenant_id=tenant_id, key="tenant_setting", value="tenant_value")
        assert setting.tenant_id == tenant_id

    def test_setting_key_normalization(self):
        """Setting key is normalized to lowercase."""
        setting = PlatformSetting.objects.create(tenant_id=None, key="UPPER_CASE_KEY", value="value")
        # Note: Normalization happens in serializer, not model
        assert setting.key == "UPPER_CASE_KEY"  # Model stores as-is

    def test_secret_value_stored(self):
        """Secret values are stored correctly."""
        setting = PlatformSetting.objects.create(tenant_id=None, key="secret_key", value="super_secret", is_secret=True)
        assert setting.is_secret is True
        assert setting.value == "super_secret"  # Value stored, masked in serializer


@pytest.mark.django_db
class TestFeatureFlagModel:
    """Unit tests for FeatureFlag model."""

    def test_create_feature_flag(self):
        """FeatureFlag can be created."""
        flag = FeatureFlag.objects.create(tenant_id=None, name="test_feature", enabled=True, rollout_percentage=50)
        assert flag.id is not None
        assert flag.enabled is True
        assert flag.rollout_percentage == 50

    def test_feature_flag_rollout_percentage_range(self):
        """Rollout percentage must be 0-100 (enforced in serializer)."""
        # Model allows any integer, validation in serializer
        flag = FeatureFlag.objects.create(
            tenant_id=None, name="test", rollout_percentage=150  # Model allows, serializer validates
        )
        assert flag.rollout_percentage == 150


@pytest.mark.django_db
class TestSystemHealthModel:
    """Unit tests for SystemHealth model."""

    def test_create_health_record(self):
        """SystemHealth can be created."""
        health = SystemHealth.objects.create(service_name="database", status="healthy", response_time_ms=10)
        assert health.id is not None
        assert health.status == "healthy"
        assert health.response_time_ms == 10

    def test_health_status_choices(self):
        """Health status uses valid choices."""
        health = SystemHealth.objects.create(service_name="api", status="degraded")
        assert health.status == "degraded"


@pytest.mark.django_db
class TestPlatformAuditEventModel:
    """Unit tests for PlatformAuditEvent model."""

    def test_create_audit_event(self):
        """PlatformAuditEvent can be created."""
        actor_id = uuid.uuid4()
        event = PlatformAuditEvent.objects.create(
            action="platform.setting.created",
            actor_type="user",
            actor_id=actor_id,
            resource_type="PlatformSetting",
            details={"key": "test"},
        )
        assert event.id is not None
        assert event.action == "platform.setting.created"

    def test_audit_event_immutable(self):
        """Audit events cannot be updated."""
        actor_id = uuid.uuid4()
        event = PlatformAuditEvent.objects.create(
            action="platform.setting.created", actor_type="user", actor_id=actor_id, resource_type="PlatformSetting"
        )

        # Try to update
        with pytest.raises(ValueError, match="immutable"):
            event.action = "platform.setting.updated"
            event.save()

    def test_audit_event_cannot_delete(self):
        """Audit events cannot be deleted."""
        actor_id = uuid.uuid4()
        event = PlatformAuditEvent.objects.create(
            action="platform.setting.created", actor_type="user", actor_id=actor_id, resource_type="PlatformSetting"
        )

        # Try to delete
        with pytest.raises(ValueError, match="immutable"):
            event.delete()
