"""
Service tests for Notifications module.
"""

import uuid
import pytest

from src.modules.notifications.models import Notification, NotificationDelivery, NotificationEndpoint, NotificationPreference
from src.modules.notifications.services import (
    NotificationConfigurationService, NotificationDispatchService, NotificationEndpointService,
    NotificationInboxService, NotificationPreferenceService, NotificationService,
    NotificationServiceError, NotificationTemplateService,
)


def _template(tenant, actor, code="notice.test"):
    template = NotificationTemplateService.create_template(
        tenant, actor,
        {"code": code, "name": "Notice", "category": "workflow", "channel": "in_app", "locale": "en", "subject_template": "Hello {{ name }}", "body_template": "Body {{ name }}", "variables_schema": {"name": {"type": "string", "required": True}}, "content_type": "text/plain"},
        f"create:{code}",
    )
    NotificationTemplateService.activate(tenant, template.id, template.initial_version.id, actor, f"activate:{code}")
    return template


@pytest.mark.django_db
class TestNotificationService:
    """Test NotificationService."""

    def test_create_notification(self):
        """Test creating a notification via service."""
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()
        notification = NotificationService.create_notification(
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            title="Test Notification",
            message="Test message",
        )

        assert notification.title == "Test Notification"
        assert notification.tenant_id == tenant_id
        assert notification.user_id == user_id


@pytest.mark.django_db
def test_configuration_update_audit_export_and_rollback():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    config = NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    changed = dict(config.document)
    changed["batch_size"] = 25
    updated = NotificationConfigurationService.update(tenant, "development", actor, changed, "Bound bulk work")
    assert updated.active_version == 2
    assert NotificationConfigurationService.history(tenant, "development").count() == 2
    exported = NotificationConfigurationService.export_document(tenant, "development")
    assert exported["schema_version"] == 1
    rolled_back = NotificationConfigurationService.rollback(tenant, "development", 1, actor, "Restore safe baseline")
    assert rolled_back.active_version == 3
    assert rolled_back.document["batch_size"] == 100


def test_configuration_validation_reports_dependency_and_bound_errors():
    tenant = uuid.uuid4()
    document = NotificationConfigurationService.safe_default()
    document["batch_size"] = 0
    document["backoff"] = {"base_seconds": 100, "maximum_seconds": 60}
    errors = NotificationConfigurationService.validate_document(tenant, document)
    assert "batch_size" in errors
    assert "backoff.maximum_seconds" in errors


@pytest.mark.django_db
def test_template_version_preview_and_full_lifecycle_are_immutable():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    template = _template(tenant, actor)
    missing = NotificationTemplateService.preview(tenant, template.id, None, {})
    assert missing["valid"] is False and missing["missing_variables"] == ["name"]
    rendered = NotificationTemplateService.preview(tenant, template.id, None, {"name": "Ada", "unused": "x"})
    assert rendered["body"] == "Body Ada" and rendered["unused_variables"] == ["unused"]
    version = NotificationTemplateService.create_version(tenant, template.id, actor, {"body_template": "Changed {{ name }}"})
    assert version.version == 2
    NotificationTemplateService.rollback(tenant, template.id, version.id, actor, "rollback:2")
    archived = NotificationTemplateService.archive(tenant, template.id, actor, "archive:1")
    assert archived.status == "archived"
    restored = NotificationTemplateService.restore(tenant, template.id, actor, "restore:1")
    assert restored.status == "draft" and restored.active_version is None
    with pytest.raises(NotificationServiceError):
        NotificationTemplateService.create_template(tenant, actor, {"code": "bad", "name": "Bad", "category": "general", "channel": "email", "locale": "xx_invalid", "body_template": "{{ user.name }}", "variables_schema": {}}, "bad")


@pytest.mark.django_db
def test_inbox_transitions_bulk_count_and_recipient_boundary():
    tenant, user = uuid.uuid4(), uuid.uuid4()
    first = NotificationService.create_notification(tenant, user, "First", "Message")
    second = NotificationService.create_notification(tenant, user, "Second", "Message")
    read = NotificationInboxService.mark_read(tenant, user, first.id, "read:1")
    assert read.status == "read" and read.read_at is not None
    assert NotificationInboxService.mark_read(tenant, user, first.id, "read:1").transition_history == read.transition_history
    unread = NotificationInboxService.mark_unread(tenant, user, first.id, "unread:1")
    assert unread.status == "unread" and unread.read_at is None
    assert NotificationInboxService.unread_count(tenant, user) == 2
    assert NotificationInboxService.mark_all_read(tenant, user, "all:1") == 2
    assert NotificationInboxService.unread_count(tenant, user) == 0
    archived = NotificationInboxService.archive(tenant, user, second.id, "archive:2")
    assert archived.status == "archived"
    with pytest.raises(Notification.DoesNotExist):
        NotificationInboxService.get_for_user(tenant, uuid.uuid4(), first.id)


@pytest.mark.django_db
def test_preference_defaults_mandatory_validation_replace_and_reset():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    effective = NotificationPreferenceService.get_effective(tenant, user, "email", "general")
    assert effective["enabled"] is True and effective["is_default"] is True
    stored = NotificationPreferenceService.upsert(tenant, user, actor, {"channel": "email", "category": "general", "enabled": False, "digest_mode": "daily", "quiet_hours_start": "22:00", "quiet_hours_end": "06:00", "timezone": "UTC"})
    assert stored.enabled is False and stored.digest_mode == "daily"
    replaced = NotificationPreferenceService.bulk_replace(tenant, user, actor, [{"channel": "in_app", "category": "workflow", "enabled": True, "digest_mode": "hourly", "timezone": "Asia/Kolkata"}])
    assert len(replaced) == 1 and NotificationPreference.objects.for_tenant(tenant).filter(user_id=user).count() == 1
    assert len(NotificationPreferenceService.reset(tenant, user, actor)) == 5
    with pytest.raises(NotificationServiceError):
        NotificationPreferenceService.upsert(tenant, user, actor, {"channel": "email", "category": "password_reset", "enabled": False})
    with pytest.raises(NotificationServiceError):
        NotificationPreferenceService.upsert(tenant, user, actor, {"channel": "email", "category": "general", "timezone": "Mars/Olympus"})


@pytest.mark.django_db
def test_push_endpoint_is_encrypted_deduplicated_mutable_and_revocable():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = {"kind": "push", "device_type": "web", "address": "opaque-device-token", "display_name": "Browser"}
    endpoint = NotificationEndpointService.register(tenant, user, actor, payload)
    assert endpoint.address_ciphertext != payload["address"]
    assert NotificationEndpointService.register(tenant, user, actor, payload).id == endpoint.id
    updated = NotificationEndpointService.update(tenant, endpoint.id, actor, {"display_name": "Work browser", "is_active": True})
    assert updated.display_name == "Work browser"
    revoked = NotificationEndpointService.revoke(tenant, endpoint.id, actor)
    assert revoked.is_active is False
    assert NotificationEndpointService.list_for_user(tenant, user).count() == 1
    with pytest.raises(NotificationEndpoint.DoesNotExist):
        NotificationEndpointService.update(uuid.uuid4(), endpoint.id, actor, {"display_name": "Cross tenant"})


@pytest.mark.django_db
def test_dispatch_preview_suppression_urgent_guard_bulk_bound_and_cancel_replay():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    config = NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    template = _template(tenant, actor, "dispatch.test")
    request = {"template_id": template.id, "recipient_type": "user", "recipient_user_id": user, "context": {"name": "Ada"}, "environment": "development"}
    with pytest.raises(NotificationServiceError, match="urgent"):
        NotificationDispatchService.preview_dispatch(tenant, actor, {**request, "priority": 1})
    preview = NotificationDispatchService.preview_dispatch(tenant, actor, request)
    assert preview["will_dispatch"] is True and preview["body"] == "Body Ada"
    queued = NotificationDispatchService.enqueue(tenant, actor, request, "queue:cancel").object
    cancelled = NotificationDispatchService.cancel(tenant, queued.id, actor, "cancel:1")
    assert cancelled.status == "cancelled"
    assert NotificationDispatchService.cancel(tenant, queued.id, actor, "cancel:1").status == "cancelled"
    changed = dict(config.document); changed["batch_size"] = 1
    NotificationConfigurationService.update(tenant, "development", actor, changed, "Tight batch")
    with pytest.raises(NotificationServiceError, match="Batch"):
        NotificationDispatchService.enqueue_bulk(tenant, actor, [request, request], "bulk")
    disabled = dict(changed); disabled["channels"] = {**changed["channels"], "in_app": {**changed["channels"]["in_app"], "enabled": False}}
    NotificationConfigurationService.update(tenant, "development", actor, disabled, "Disable channel")
    skipped = NotificationDispatchService.enqueue(tenant, actor, request, "skip:1").object
    assert isinstance(skipped, NotificationDelivery) and skipped.status == "skipped"


@pytest.mark.django_db
def test_feature_flag_targets_and_configuration_dry_run_are_deterministic():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    config = NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    document = dict(config.document)
    document["feature_flags"] = {"new_flow": {"enabled": True, "tenant_ids": [str(tenant)], "roles": ["operator"], "cohorts": ["beta"]}}
    NotificationConfigurationService.update(tenant, "development", actor, document, "Target beta operators")
    assert NotificationConfigurationService.effective_feature_flags(tenant, {"environment": "development", "roles": ["operator"], "cohorts": ["beta"]})["new_flow"] is True
    assert NotificationConfigurationService.effective_feature_flags(tenant, {"environment": "development", "roles": ["viewer"], "cohorts": ["beta"]})["new_flow"] is False
    dry = NotificationConfigurationService.import_document(tenant, "development", actor, {"configuration": document}, True)
    assert dry["valid"] is True and dry["would_write"] is False and dry["document"] == document
