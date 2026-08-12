"""
Service tests for Notifications module.
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime as dt_datetime
from datetime import time as dt_time
from datetime import timedelta
from datetime import timezone as dt_timezone
from types import SimpleNamespace

import pytest
from django.utils import timezone

from src.modules.notifications.adapters import DeliveryResult, VerificationResult
from src.modules.notifications.models import (
    Notification,
    NotificationDelivery,
    NotificationDeliveryAttempt,
    NotificationEndpoint,
    NotificationPreference,
)
from src.modules.notifications.services import (
    CapabilityUnavailable,
    NotificationConfigurationService,
    NotificationDispatchService,
    NotificationEndpointService,
    NotificationInboxService,
    NotificationPreferenceService,
    NotificationProviderCallbackService,
    NotificationService,
    NotificationServiceError,
    NotificationTemplateService,
    _correlation_uuid,
    _json_size,
    _required_text,
    _schema_variables,
    _validate_public_webhook,
    _validate_url,
    identity_uuid,
    render_template,
    validate_template,
)


def _template(tenant, actor, code="notice.test", channel="in_app"):
    template = NotificationTemplateService.create_template(
        tenant,
        actor,
        {
            "code": code,
            "name": "Notice",
            "category": "workflow",
            "channel": channel,
            "locale": "en",
            "subject_template": "Hello {{ name }}",
            "body_template": "Body {{ name }}",
            "variables_schema": {"name": {"type": "string", "required": True}},
            "content_type": "text/plain",
        },
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
    version = NotificationTemplateService.create_version(
        tenant, template.id, actor, {"body_template": "Changed {{ name }}"}
    )
    assert version.version == 2
    NotificationTemplateService.rollback(tenant, template.id, version.id, actor, "rollback:2")
    archived = NotificationTemplateService.archive(tenant, template.id, actor, "archive:1")
    assert archived.status == "archived"
    restored = NotificationTemplateService.restore(tenant, template.id, actor, "restore:1")
    assert restored.status == "draft" and restored.active_version is None
    with pytest.raises(NotificationServiceError):
        NotificationTemplateService.create_template(
            tenant,
            actor,
            {
                "code": "bad",
                "name": "Bad",
                "category": "general",
                "channel": "email",
                "locale": "xx_invalid",
                "body_template": "{{ user.name }}",
                "variables_schema": {},
            },
            "bad",
        )


@pytest.mark.django_db
def test_inbox_transitions_bulk_count_and_recipient_boundary():
    tenant, user = uuid.uuid4(), uuid.uuid4()
    first = NotificationService.create_notification(tenant, user, "First", "Message")
    second = NotificationService.create_notification(tenant, user, "Second", "Message")
    read = NotificationInboxService.mark_read(tenant, user, first.id, "read:1")
    assert read.status == "read" and read.read_at is not None
    assert (
        NotificationInboxService.mark_read(tenant, user, first.id, "read:1").transition_history
        == read.transition_history
    )
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
    stored = NotificationPreferenceService.upsert(
        tenant,
        user,
        actor,
        {
            "channel": "email",
            "category": "general",
            "enabled": False,
            "digest_mode": "daily",
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "06:00",
            "timezone": "UTC",
        },
    )
    assert stored.enabled is False and stored.digest_mode == "daily"
    replaced = NotificationPreferenceService.bulk_replace(
        tenant,
        user,
        actor,
        [
            {
                "channel": "in_app",
                "category": "workflow",
                "enabled": True,
                "digest_mode": "hourly",
                "timezone": "Asia/Kolkata",
            }
        ],
    )
    assert len(replaced) == 1 and NotificationPreference.objects.for_tenant(tenant).filter(user_id=user).count() == 1
    assert len(NotificationPreferenceService.reset(tenant, user, actor)) == 5
    with pytest.raises(NotificationServiceError):
        NotificationPreferenceService.upsert(
            tenant, user, actor, {"channel": "email", "category": "password_reset", "enabled": False}
        )
    with pytest.raises(NotificationServiceError):
        NotificationPreferenceService.upsert(
            tenant, user, actor, {"channel": "email", "category": "general", "timezone": "Mars/Olympus"}
        )


@pytest.mark.django_db
def test_push_endpoint_is_encrypted_deduplicated_mutable_and_revocable():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = {"kind": "push", "device_type": "web", "address": "opaque-device-token", "display_name": "Browser"}
    endpoint = NotificationEndpointService.register(tenant, user, actor, payload)
    assert endpoint.address_ciphertext != payload["address"]
    assert NotificationEndpointService.register(tenant, user, actor, payload).id == endpoint.id
    updated = NotificationEndpointService.update(
        tenant, endpoint.id, actor, {"display_name": "Work browser", "is_active": True}
    )
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
    request = {
        "template_id": template.id,
        "recipient_type": "user",
        "recipient_user_id": user,
        "context": {"name": "Ada"},
        "environment": "development",
    }
    with pytest.raises(NotificationServiceError, match="urgent"):
        NotificationDispatchService.preview_dispatch(tenant, actor, {**request, "priority": 1})
    preview = NotificationDispatchService.preview_dispatch(tenant, actor, request)
    assert preview["will_dispatch"] is True and preview["body"] == "Body Ada"
    queued = NotificationDispatchService.enqueue(tenant, actor, request, "queue:cancel").object
    cancelled = NotificationDispatchService.cancel(tenant, queued.id, actor, "cancel:1")
    assert cancelled.status == "cancelled"
    assert NotificationDispatchService.cancel(tenant, queued.id, actor, "cancel:1").status == "cancelled"
    changed = dict(config.document)
    changed["batch_size"] = 1
    NotificationConfigurationService.update(tenant, "development", actor, changed, "Tight batch")
    with pytest.raises(NotificationServiceError, match="Batch"):
        NotificationDispatchService.enqueue_bulk(tenant, actor, [request, request], "bulk")
    disabled = dict(changed)
    disabled["channels"] = {**changed["channels"], "in_app": {**changed["channels"]["in_app"], "enabled": False}}
    NotificationConfigurationService.update(tenant, "development", actor, disabled, "Disable channel")
    skipped = NotificationDispatchService.enqueue(tenant, actor, request, "skip:1").object
    assert isinstance(skipped, NotificationDelivery) and skipped.status == "skipped"


@pytest.mark.django_db
def test_feature_flag_targets_and_configuration_dry_run_are_deterministic():
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    config = NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    document = dict(config.document)
    document["feature_flags"] = {
        "new_flow": {"enabled": True, "tenant_ids": [str(tenant)], "roles": ["operator"], "cohorts": ["beta"]}
    }
    NotificationConfigurationService.update(tenant, "development", actor, document, "Target beta operators")
    assert (
        NotificationConfigurationService.effective_feature_flags(
            tenant, {"environment": "development", "roles": ["operator"], "cohorts": ["beta"]}
        )["new_flow"]
        is True
    )
    assert (
        NotificationConfigurationService.effective_feature_flags(
            tenant, {"environment": "development", "roles": ["viewer"], "cohorts": ["beta"]}
        )["new_flow"]
        is False
    )
    dry = NotificationConfigurationService.import_document(
        tenant, "development", actor, {"configuration": document}, True
    )
    assert dry["valid"] is True and dry["would_write"] is False and dry["document"] == document


@pytest.mark.django_db
def test_execute_delivery_records_attempts_inbox_and_terminal_replay(monkeypatch):
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    template = _template(tenant, actor, "execute.success")
    queued = NotificationDispatchService.enqueue(
        tenant,
        actor,
        {
            "template_id": template.id,
            "recipient_type": "user",
            "recipient_user_id": user,
            "context": {"name": "Ada"},
            "environment": "development",
        },
        "execute-success",
    ).object

    class Adapter:
        key = "fake-in-app"

        def send(self, command):
            assert command.recipient == str(user)
            return DeliveryResult(
                accepted=True,
                provider_message_id="msg-1",
                confirmation_supported=False,
                evidence={"accepted_at": "now"},
            )

    monkeypatch.setattr("src.modules.notifications.adapters.get_adapter", lambda key: Adapter())

    delivered = NotificationDispatchService.execute_delivery(tenant, queued.id)
    replay = NotificationDispatchService.execute_delivery(tenant, queued.id)

    assert delivered.status == "delivered"
    assert replay.id == delivered.id
    assert NotificationDeliveryAttempt.objects.filter(tenant_id=tenant, delivery=queued).count() == 1
    assert Notification.objects.for_tenant(tenant).filter(user_id=user, delivery=queued).exists()


@pytest.mark.django_db
def test_execute_delivery_retry_failure_manual_retry_and_confirmation_guards(monkeypatch):
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    template = _template(tenant, actor, "execute.retry")
    queued = NotificationDispatchService.enqueue(
        tenant,
        actor,
        {
            "template_id": template.id,
            "recipient_type": "user",
            "recipient_user_id": user,
            "context": {"name": "Ada"},
            "environment": "development",
        },
        "execute-retry",
    ).object

    class Adapter:
        key = "fake-in-app"

        def send(self, command):
            assert command.recipient == str(user)
            return DeliveryResult(accepted=False, retryable=True, error_code="TEMPORARY_PROVIDER_FAILURE")

    monkeypatch.setattr("src.modules.notifications.adapters.get_adapter", lambda key: Adapter())

    retry_wait = NotificationDispatchService.execute_delivery(tenant, queued.id)
    retry_wait.refresh_from_db()
    assert retry_wait.status == "retry_wait", retry_wait.status
    retried = NotificationDispatchService.retry(tenant, retry_wait.id, actor, "manual-retry")

    assert retry_wait.status == "retry_wait"
    assert retry_wait.failure_code == "TEMPORARY_PROVIDER_FAILURE"
    assert retried.status == "queued"
    with pytest.raises(NotificationServiceError) as exc:
        NotificationDispatchService.confirm_delivery(
            tenant,
            retry_wait.id,
            {"provider_message_id": "wrong", "signature_verified": True},
            "confirm-invalid",
        )
    assert exc.value.code == "INVALID_CONFIRMATION"


@pytest.mark.django_db
def test_configuration_rejects_inline_channel_secret_and_invalid_rollout_target():
    tenant = uuid.uuid4()
    document = NotificationConfigurationService.safe_default()
    document["channels"]["webhook"]["token"] = "inline-secret"  # type: ignore[index]
    document["feature_flags"] = {"bad flag": {"enabled": True, "tenant_ids": [], "roles": [], "cohorts": []}}

    errors = NotificationConfigurationService.validate_document(tenant, document)

    assert errors["channels.webhook.unknown"] == "contains unknown channel settings"
    assert errors["channels.webhook.token"] == "inline credentials are forbidden"
    assert errors["feature_flags.bad flag"] == "must be a closed rollout object"


@pytest.mark.django_db
def test_preferences_bulk_replace_rejects_duplicates_without_deleting_existing_rows():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    original = NotificationPreferenceService.upsert(
        tenant,
        user,
        actor,
        {"channel": "email", "category": "workflow", "enabled": True, "digest_mode": "daily"},
    )

    with pytest.raises(NotificationServiceError, match="duplicates"):
        NotificationPreferenceService.bulk_replace(
            tenant,
            user,
            actor,
            [
                {"channel": "email", "category": "workflow", "enabled": True},
                {"channel": "email", "category": "workflow", "enabled": False},
            ],
        )

    original.refresh_from_db()
    assert original.enabled is True
    assert NotificationPreference.objects.for_tenant(tenant).filter(user_id=original.user_id).count() == 1


@pytest.mark.django_db
def test_endpoint_update_rejects_unapproved_secret_ref_without_mutating_row():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    endpoint = NotificationEndpointService.register(
        tenant,
        user,
        actor,
        {"kind": "push", "device_type": "web", "address": "device-token", "display_name": "Browser"},
    )

    with pytest.raises(NotificationServiceError) as caught:
        NotificationEndpointService.update(
            tenant,
            endpoint.id,
            actor,
            {"display_name": "Changed", "secret_ref": "file:///tmp/token"},  # pragma: allowlist secret
        )

    endpoint.refresh_from_db()
    assert caught.value.code == "VALIDATION_ERROR"
    assert endpoint.display_name == "Browser"
    assert endpoint.secret_ref == ""


def test_core_validation_helpers_reject_unsafe_or_ambiguous_inputs(monkeypatch):
    tenant = uuid.uuid4()

    assert identity_uuid(tenant, "operator-1") == identity_uuid(tenant, "operator-1")
    with pytest.raises(NotificationServiceError, match="actor"):
        identity_uuid(tenant, "   ")
    with pytest.raises(NotificationServiceError, match="required"):
        _required_text("", "transition_key")
    with pytest.raises(NotificationServiceError, match="exceeds"):
        _required_text("abcd", "code", 3)
    with pytest.raises(NotificationServiceError, match="JSON"):
        _json_size({"bad": object()})

    monkeypatch.setattr("src.modules.notifications.services.get_correlation_id", lambda: "not-a-uuid")
    assert _correlation_uuid() == uuid.uuid5(uuid.NAMESPACE_URL, "not-a-uuid")

    with pytest.raises(NotificationServiceError, match="variables_schema"):
        _schema_variables([])
    with pytest.raises(NotificationServiceError, match="simple identifiers"):
        _schema_variables({"bad-name!": {"type": "string"}})
    with pytest.raises(NotificationServiceError, match="unknown properties"):
        _schema_variables({"name": {"type": "string", "x": True}})
    with pytest.raises(NotificationServiceError, match="unsupported type"):
        _schema_variables({"name": {"type": "date"}})

    schema = {"name": {"type": "string", "required": True}}
    with pytest.raises(NotificationServiceError) as unsafe:
        validate_template("Hello {{ user.name }}", schema, field_name="body_template")
    assert unsafe.value.code == "UNSAFE_TEMPLATE"
    with pytest.raises(NotificationServiceError) as syntax:
        validate_template("Hello {{ name", schema, field_name="body_template")
    assert syntax.value.code == "INVALID_TEMPLATE"
    with pytest.raises(NotificationServiceError) as undeclared:
        validate_template("Hello {{ other }}", schema, field_name="body_template")
    assert undeclared.value.code == "UNDECLARED_VARIABLE"

    rendered, missing, unused = render_template("Hello {{ name }}", schema, {"extra": "ignored"})
    assert rendered == "Hello {{ name }}"
    assert missing == ["name"]
    assert unused == ["extra"]
    with pytest.raises(NotificationServiceError, match="context"):
        render_template("Hello {{ name }}", schema, [])
    with pytest.raises(NotificationServiceError, match="scalar"):
        render_template("Hello {{ name }}", schema, {"name": {"nested": True}})


def test_url_and_webhook_validation_enforces_allowlists_and_public_resolution(monkeypatch):
    assert _validate_url("/notifications/1", []) == "/notifications/1"
    assert _validate_url("https://hooks.example.test/path", ["hooks.example.test"]) == "https://hooks.example.test/path"

    with pytest.raises(NotificationServiceError, match="URL"):
        _validate_url("http://hooks.example.test/path", ["hooks.example.test"])
    with pytest.raises(NotificationServiceError, match="allowlisted"):
        _validate_url("https://evil.example.test/path", ["hooks.example.test"])

    monkeypatch.setattr(
        "src.modules.notifications.services.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))],
    )
    assert _validate_public_webhook("https://hooks.example.test/callback", ["hooks.example.test"])

    monkeypatch.setattr(
        "src.modules.notifications.services.socket.getaddrinfo",
        lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    with pytest.raises(NotificationServiceError) as private:
        _validate_public_webhook("https://hooks.example.test/callback", ["hooks.example.test"])
    assert private.value.code == "ENDPOINT_PRIVATE_ADDRESS"


@pytest.mark.django_db
def test_template_preview_unsaved_and_endpoint_verification_surface_real_adapter_results(monkeypatch):
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)

    preview = NotificationTemplateService.preview_unsaved(
        tenant,
        {
            "subject_template": "Hello {{ name }}",
            "body_template": "Body {{ name }}",
            "variables_schema": {"name": {"type": "string", "required": True}},
            "content_type": "text/plain",
        },
        {"extra": "ignored"},
    )
    assert preview["valid"] is False
    assert preview["persisted"] is False
    assert preview["missing_variables"] == ["name"]
    assert preview["unused_variables"] == ["extra"]

    endpoint = NotificationEndpointService.register(
        tenant,
        user,
        actor,
        {"kind": "push", "device_type": "web", "address": "device-token", "display_name": "Browser"},
    )

    class Adapter:
        def __init__(self, verified: bool) -> None:
            self.verified = verified
            self.commands = []

        def verify_endpoint(self, command):
            self.commands.append(command)
            if not self.verified:
                return VerificationResult(False, "PROVIDER_REJECTED")
            return VerificationResult(True, "VERIFIED", {"checked": True})

    accepted = Adapter(True)
    monkeypatch.setattr("src.modules.notifications.adapters.get_adapter", lambda key: accepted)
    verified = NotificationEndpointService.verify(tenant, endpoint.id, actor)
    assert verified.last_verified_at is not None
    assert accepted.commands[0].endpoint_id == endpoint.id

    endpoint.last_verified_at = None
    endpoint.save(update_fields=["last_verified_at", "updated_at"])
    rejected = Adapter(False)
    monkeypatch.setattr("src.modules.notifications.adapters.get_adapter", lambda key: rejected)
    with pytest.raises(CapabilityUnavailable) as unavailable:
        NotificationEndpointService.verify(tenant, endpoint.id, actor)
    assert "PROVIDER_REJECTED" in str(unavailable.value)


@pytest.mark.django_db
def test_provider_callback_accepts_signed_events_and_replays_idempotently(settings):
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    endpoint = NotificationEndpoint.objects.create(
        tenant_id=tenant,
        user_id=user,
        kind="webhook",
        device_type="",
        address_ciphertext="encrypted",
        fingerprint="callback-fingerprint",
        display_name="Provider callback",
        secret_ref="vault://notifications/callback",  # pragma: allowlist secret
        created_by=actor,
    )
    template = _template(tenant, actor, "callback.accept")
    template.refresh_from_db()
    delivery = NotificationDelivery.objects.create(
        tenant_id=tenant,
        template_version=template.active_version,
        job_id=uuid.uuid4(),
        idempotency_key="callback-delivery",
        recipient_type="user",
        recipient_user_id=user,
        recipient_ciphertext="",
        recipient_fingerprint="fingerprint",
        recipient_display="****",
        channel="in_app",
        category="workflow",
        priority=5,
        status="sent",
        context_data={"name": "Ada"},
        rendered_subject="Hello Ada",
        rendered_body="Body Ada",
        max_attempts=3,
        provider_message_id="provider-1",
        created_by=actor,
        correlation_id=uuid.uuid4(),
        sent_at=timezone.now(),
    )
    settings.NOTIFICATION_CALLBACK_ENDPOINTS = {
        "provider-a": {"tenant_id": str(tenant), "endpoint_id": str(endpoint.id)}
    }
    settings.NOTIFICATION_PROVIDER_CALLBACK_SECRETS = {"vault://notifications/callback": "callback-secret"}
    body = json.dumps(
        {
            "delivery_id": str(delivery.id),
            "event_type": "delivered",
            "occurred_at": timezone.now().isoformat(),
            "provider_message_id": "provider-1",
        }
    ).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new("callback-secret".encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    headers = {
        "X-Notification-Timestamp": timestamp,
        "X-Notification-Signature": f"sha256={signature}",
        "X-Notification-Event-ID": "evt-1",
    }

    accepted = NotificationProviderCallbackService.accept("provider-a", headers, body)
    replayed = NotificationProviderCallbackService.accept("provider-a", headers, body)

    assert accepted["accepted"] is True
    assert accepted["replayed"] is False
    assert replayed["replayed"] is True


@pytest.mark.django_db
def test_provider_callback_rejects_missing_secret_bad_signature_and_invalid_body(settings):
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    endpoint = NotificationEndpoint.objects.create(
        tenant_id=tenant,
        user_id=user,
        kind="webhook",
        device_type="",
        address_ciphertext="encrypted",
        fingerprint="callback-fingerprint-invalid",
        display_name="Provider callback",
        secret_ref="vault://notifications/missing",  # pragma: allowlist secret
        created_by=actor,
    )
    settings.NOTIFICATION_CALLBACK_ENDPOINTS = {
        "missing-secret": {"tenant_id": str(tenant), "endpoint_id": str(endpoint.id)}
    }
    settings.NOTIFICATION_PROVIDER_CALLBACK_SECRETS = {}

    with pytest.raises(CapabilityUnavailable):
        NotificationProviderCallbackService.accept(
            "missing-secret",
            {
                "X-Notification-Timestamp": str(int(time.time())),
                "X-Notification-Signature": "sha256=bad",
                "X-Notification-Event-ID": "evt-missing-secret",
            },
            b"{}",
        )

    settings.NOTIFICATION_PROVIDER_CALLBACK_SECRETS = {"vault://notifications/missing": "callback-secret"}
    with pytest.raises(NotificationServiceError) as invalid_timestamp:
        NotificationProviderCallbackService.accept(
            "missing-secret",
            {
                "X-Notification-Timestamp": "not-an-int",
                "X-Notification-Signature": "sha256=bad",
                "X-Notification-Event-ID": "evt-bad-timestamp",
            },
            b"{}",
        )
    assert invalid_timestamp.value.code == "INVALID_CALLBACK_TIMESTAMP"

    expired_timestamp = str(int(time.time()) - 10_000)
    with pytest.raises(NotificationServiceError) as expired:
        NotificationProviderCallbackService.accept(
            "missing-secret",
            {
                "X-Notification-Timestamp": expired_timestamp,
                "X-Notification-Signature": "sha256=bad",
                "X-Notification-Event-ID": "evt-expired",
            },
            b"{}",
        )
    assert expired.value.code == "CALLBACK_TIMESTAMP_EXPIRED"

    timestamp = str(int(time.time()))
    with pytest.raises(NotificationServiceError) as signature:
        NotificationProviderCallbackService.accept(
            "missing-secret",
            {
                "X-Notification-Timestamp": timestamp,
                "X-Notification-Signature": "sha256=bad",
                "X-Notification-Event-ID": "evt-bad-signature",
            },
            b"not-json",
        )
    assert signature.value.code == "INVALID_SIGNATURE"


@pytest.mark.django_db
def test_process_due_requeues_pending_and_retry_wait_deliveries(monkeypatch):
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    template = _template(tenant, actor, "process.due")
    request = {
        "template_id": template.id,
        "recipient_type": "user",
        "recipient_user_id": user,
        "context": {"name": "Ada"},
        "environment": "development",
    }
    pending = NotificationDispatchService.enqueue(tenant, actor, request, "process-due-pending").object
    pending.status = "pending"
    pending.scheduled_at = timezone.now() - timedelta(minutes=1)
    pending.job_id = None
    pending.save(update_fields=["status", "scheduled_at", "job_id", "updated_at"])

    retry_wait = NotificationDispatchService.enqueue(tenant, actor, request, "process-due-retry").object
    retry_wait.status = "retry_wait"
    retry_wait.next_attempt_at = timezone.now() - timedelta(minutes=1)
    retry_wait.failure_code = "ADAPTER_TIMEOUT"
    retry_wait.transition_history = [
        {
            "transition_key": "worker-retry:job:1",
            "command": "retry",
            "from_state": "sending",
            "to_state": "retry_wait",
            "occurred_at": timezone.now().isoformat(),
            "metadata": {},
        }
    ]
    retry_wait.save(update_fields=["status", "next_attempt_at", "failure_code", "transition_history", "updated_at"])

    results = NotificationDispatchService.process_due(tenant, 999)

    assert [result.status for result in results] == ["queued", "queued"]
    pending.refresh_from_db()
    retry_wait.refresh_from_db()
    assert pending.job_id is not None
    assert retry_wait.failure_code == ""


@pytest.mark.django_db
def test_configuration_validation_reports_closed_shape_rollout_and_secret_errors():
    tenant = uuid.uuid4()
    document = NotificationConfigurationService.safe_default()
    document["batch_size"] = 0
    document["backoff"] = {"base_seconds": 600, "maximum_seconds": 60}
    document["channels"]["email"]["credential_ref"] = "plain-secret"
    document["channels"]["sms"]["retry"] = {"max_attempts": 3}
    document["allowed_webhook_hosts"] = ["valid.example", "bad/path"]
    document["preferences"]["mandatory_categories"] = ["workflow"]
    document["feature_flags"] = {"rollout": {"enabled": True, "tenant_ids": ["tenant-1"], "roles": [], "cohorts": []}}
    document["digest_schedules"]["daily_time"] = "25:00"
    document["quiet_hours"] = {"start": "09:00", "end": None, "timezone": "Mars/Base"}

    errors = NotificationConfigurationService.validate_document(tenant, document)

    assert errors["batch_size"] == "must be between 1 and 500"
    assert errors["backoff.maximum_seconds"] == "must not be less than base_seconds"
    assert errors["channels.email.credential_ref"] == "must use an approved secret-manager URI"
    assert errors["channels.sms.retry"] == "must declare max_attempts, base_seconds, and maximum_seconds"
    assert errors["allowed_webhook_hosts"] == "must be a hostname list"
    assert errors["preferences.mandatory_categories"] == "must include the platform security categories"
    assert errors["digest_schedules.daily_time"] == "must be HH:MM"
    assert errors["quiet_hours"] == "start and end must both be set or null"
    assert errors["quiet_hours.timezone"] == "must be an IANA timezone"

    assert NotificationConfigurationService.validate_document(tenant, ["not", "mapping"]) == {
        "document": "must be an object"
    }


@pytest.mark.django_db
def test_dispatch_preview_enforces_configuration_channel_preference_and_context_limits():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    template = _template(tenant, actor, "dispatch.policy", channel="email")

    with pytest.raises(NotificationServiceError) as missing_config:
        NotificationDispatchService.preview_dispatch(
            tenant,
            actor,
            {
                "template_id": template.id,
                "recipient_type": "user",
                "recipient_user_id": user,
                "context": {"name": "Ada"},
                "environment": "development",
            },
        )
    assert missing_config.value.code == "CONFIGURATION_MISSING"

    config = NotificationConfigurationService.get_or_create_default(tenant, "development", actor)
    config.document["channels"]["email"]["enabled"] = False
    config.save(update_fields=["document", "updated_at"])
    disabled = NotificationDispatchService.preview_dispatch(
        tenant,
        actor,
        {
            "template_id": template.id,
            "recipient_type": "user",
            "recipient_user_id": user,
            "context": {"name": "Ada"},
            "environment": "development",
        },
    )
    assert disabled == {"will_dispatch": False, "reason": "channel_disabled", "channel": "email"}

    config.document["channels"]["email"]["enabled"] = True
    config.document["limits"]["context_bytes"] = 16384
    config.save(update_fields=["document", "updated_at"])
    NotificationPreferenceService.bulk_replace(
        tenant,
        user,
        actor,
        [
            {
                "channel": "email",
                "category": "workflow",
                "enabled": False,
                "digest_mode": "immediate",
                "timezone": "UTC",
            }
        ],
    )
    preference_disabled = NotificationDispatchService.preview_dispatch(
        tenant,
        actor,
        {
            "template_id": template.id,
            "recipient_type": "user",
            "recipient_user_id": user,
            "context": {"name": "Ada"},
            "environment": "development",
        },
    )
    assert preference_disabled["reason"] == "preference_disabled"

    with pytest.raises(NotificationServiceError) as invalid_recipient:
        NotificationDispatchService.preview_dispatch(
            tenant,
            actor,
            {
                "template_id": template.id,
                "recipient_type": "fax",
                "context": {"name": "Ada"},
                "environment": "development",
            },
        )
    assert invalid_recipient.value.code == "VALIDATION_ERROR"

    with pytest.raises(NotificationServiceError) as urgent:
        NotificationDispatchService.preview_dispatch(
            tenant,
            actor,
            {
                "template_id": template.id,
                "recipient_type": "email",
                "recipient_address": "ops@example.com",
                "priority": 1,
                "context": {"name": "Ada"},
                "environment": "development",
            },
        )
    assert urgent.value.code == "URGENT_PERMISSION_REQUIRED"

    config.document["limits"]["context_bytes"] = 16_384
    config.save(update_fields=["document", "updated_at"])
    with pytest.raises(NotificationServiceError) as too_large:
        NotificationDispatchService.preview_dispatch(
            tenant,
            actor,
            {
                "template_id": template.id,
                "recipient_type": "email",
                "recipient_address": "ops@example.com",
                "context": {"name": "Ada", "payload": "x" * 20_000},
                "environment": "development",
            },
        )
    assert too_large.value.code == "CONTEXT_TOO_LARGE"


def test_dispatch_policy_schedule_handles_quiet_hours_and_digest_modes():
    configuration = SimpleNamespace(
        document={
            "quiet_hours": {"start": "22:00", "end": "06:00", "timezone": "UTC"},
            "digest_schedules": {"hourly_minute": 15, "daily_time": "09:30", "weekly_day": 2},
        }
    )
    quiet_until, quiet_reason = NotificationDispatchService._policy_schedule(
        configuration,
        {"digest_mode": "immediate", "timezone": "UTC"},
        dt_datetime(2026, 1, 2, 23, 30, tzinfo=dt_timezone.utc),
    )
    assert quiet_reason == "quiet_hours"
    assert quiet_until == dt_datetime(2026, 1, 3, 6, 0, tzinfo=dt_timezone.utc)

    hourly_at, hourly_reason = NotificationDispatchService._policy_schedule(
        configuration,
        {"digest_mode": "hourly", "timezone": "UTC"},
        dt_datetime(2026, 1, 2, 10, 16, tzinfo=dt_timezone.utc),
    )
    assert hourly_reason == "digest_hourly"
    assert hourly_at == dt_datetime(2026, 1, 2, 11, 15, tzinfo=dt_timezone.utc)

    daily_at, daily_reason = NotificationDispatchService._policy_schedule(
        configuration,
        {"digest_mode": "daily", "timezone": "UTC", "quiet_hours_start": None, "quiet_hours_end": None},
        dt_datetime(2026, 1, 2, 10, 16, tzinfo=dt_timezone.utc),
    )
    assert daily_reason == "digest_daily"
    assert daily_at == dt_datetime(2026, 1, 3, 9, 30, tzinfo=dt_timezone.utc)

    weekly_at, weekly_reason = NotificationDispatchService._policy_schedule(
        configuration,
        {
            "digest_mode": "weekly",
            "timezone": "UTC",
            "quiet_hours_start": dt_time(1, 0),
            "quiet_hours_end": dt_time(2, 0),
        },
        dt_datetime(2026, 1, 2, 10, 16, tzinfo=dt_timezone.utc),
    )
    assert weekly_reason == "digest_weekly"
    assert weekly_at == dt_datetime(2026, 1, 7, 9, 30, tzinfo=dt_timezone.utc)


@pytest.mark.django_db
def test_endpoint_secret_rotation_is_tenant_bound_and_secret_manager_only():
    tenant, actor, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    endpoint = NotificationEndpointService.register(
        tenant,
        user,
        actor,
        {"kind": "push", "device_type": "web", "address": "device-token", "display_name": "Browser"},
    )

    with pytest.raises(NotificationServiceError) as invalid:
        NotificationEndpointService.rotate_secret_ref(
            tenant, endpoint.id, actor, "secret://not-approved"
        )  # pragma: allowlist secret
    assert invalid.value.code == "VALIDATION_ERROR"

    rotated = NotificationEndpointService.rotate_secret_ref(
        tenant, endpoint.id, actor, "vault://notifications/push/device-token"  # pragma: allowlist secret
    )
    assert rotated.secret_ref == "vault://notifications/push/device-token"  # pragma: allowlist secret

    with pytest.raises(NotificationEndpoint.DoesNotExist):
        NotificationEndpointService.rotate_secret_ref(
            uuid.uuid4(), endpoint.id, actor, "vault://notifications/push/foreign"
        )
