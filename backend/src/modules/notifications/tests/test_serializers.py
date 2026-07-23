"""Boundary and normalization tests for notification API serializers."""

from uuid import uuid4

import pytest

from src.modules.notifications.serializers import (
    BulkDispatchSerializer,
    ConfigurationRollbackSerializer,
    ConfigurationWriteSerializer,
    DispatchCreateSerializer,
    DispatchPreviewSerializer,
    EndpointSecretRotationSerializer,
    PreferenceUpsertSerializer,
    TemplateCreateSerializer,
    TemplateRollbackSerializer,
    TemplateTransitionSerializer,
)


def _template_payload(**overrides):
    payload = {
        "code": "invoice.ready",
        "name": "Invoice ready",
        "category": "billing",
        "channel": "email",
        "locale": "en-US",
        "subject_template": "Invoice {{ invoice_number }}",
        "body_template": "Your invoice is ready.",
        "variables_schema": {"invoice_number": {"type": "string"}},
        "content_type": "text/plain",
    }
    payload.update(overrides)
    return payload


def _dispatch_payload(**overrides):
    payload = {
        "template_id": str(uuid4()),
        "recipient": {"type": "email", "address": "person@example.test"},
        "environment": "development",
    }
    payload.update(overrides)
    return payload


def test_template_create_applies_defaults_and_accepts_bcp47_locale():
    serializer = TemplateCreateSerializer(data=_template_payload())
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["locale"] == "en-US"
    assert serializer.validated_data["content_type"] == "text/plain"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", "Invoice.Ready"),
        ("category", "billing invoices"),
        ("channel", "fax"),
        ("locale", "english-US"),
        ("content_type", "text/xml"),
    ],
)
def test_template_create_rejects_invalid_contract_values(field, value):
    serializer = TemplateCreateSerializer(data=_template_payload(**{field: value}))
    assert not serializer.is_valid()
    assert field in serializer.errors


@pytest.mark.parametrize("serializer_class", [TemplateTransitionSerializer, TemplateRollbackSerializer])
def test_template_state_change_requires_target_version(serializer_class):
    serializer = serializer_class(data={"transition_key": "state-change-1"})
    assert not serializer.is_valid()
    assert "version" in serializer.errors


@pytest.mark.parametrize("serializer_class", [DispatchCreateSerializer, DispatchPreviewSerializer])
def test_dispatch_normalizes_nested_direct_recipient(serializer_class):
    data = _dispatch_payload()
    if serializer_class is DispatchCreateSerializer:
        data["idempotency_key"] = "dispatch-1"
    serializer = serializer_class(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["recipient_type"] == "email"
    assert serializer.validated_data["recipient"] == "person@example.test"


@pytest.mark.parametrize(
    "recipient",
    [
        {"type": "email"},
        {"type": "phone", "address": ""},
        {"type": "user"},
        {"type": "push_endpoint"},
        {"type": "carrier_pigeon", "address": "somewhere"},
    ],
)
def test_dispatch_rejects_incomplete_or_unknown_recipient(recipient):
    serializer = DispatchPreviewSerializer(data=_dispatch_payload(recipient=recipient))
    assert not serializer.is_valid()
    assert set(serializer.errors) & {"recipient", "recipient_user_id"}


def test_dispatch_rejects_priority_outside_safe_bounds():
    serializer = DispatchPreviewSerializer(data=_dispatch_payload(priority=11))
    assert not serializer.is_valid()
    assert "priority" in serializer.errors


def test_bulk_dispatch_accepts_compatibility_alias_and_normalizes_it():
    serializer = BulkDispatchSerializer(
        data={"deliveries": [_dispatch_payload()], "idempotency_key": "bulk-1"}
    )
    assert serializer.is_valid(), serializer.errors
    assert len(serializer.validated_data["requests"]) == 1
    assert "deliveries" not in serializer.validated_data


@pytest.mark.parametrize("payload", [{}, {"requests": []}, {"deliveries": []}])
def test_bulk_dispatch_requires_at_least_one_request(payload):
    serializer = BulkDispatchSerializer(data={**payload, "idempotency_key": "bulk-empty"})
    assert not serializer.is_valid()


@pytest.mark.parametrize(
    "payload",
    [
        {"channel": "email", "category": "general", "quiet_hours_start": "22:00"},
        {"channel": "email", "category": "general", "timezone": "Mars/Olympus_Mons"},
    ],
)
def test_preference_rejects_incomplete_quiet_hours_and_invalid_timezone(payload):
    serializer = PreferenceUpsertSerializer(data=payload)
    assert not serializer.is_valid()


@pytest.mark.parametrize(
    ("secret_ref", "valid"),
    [
        ("vault://notifications/prod/webhook", True),
        ("aws-secrets://notifications/webhook", True),
        ("https://secrets.example.test/value", False),
        ("plaintext-secret", False),
    ],
)
def test_endpoint_secret_rotation_enforces_approved_secret_managers(secret_ref, valid):
    serializer = EndpointSecretRotationSerializer(data={"secret_ref": secret_ref})
    assert serializer.is_valid() is valid


def test_configuration_write_normalizes_change_summary_alias():
    serializer = ConfigurationWriteSerializer(
        data={"document": {}, "change_summary": "Enable email"},
        context={"tenant_id": uuid4()},
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["reason"] == "Enable email"
    assert "change_summary" not in serializer.validated_data


def test_configuration_write_requires_auditable_reason():
    serializer = ConfigurationWriteSerializer(
        data={"document": {}}, context={"tenant_id": uuid4()}
    )
    assert not serializer.is_valid()
    assert "change_summary" in serializer.errors


def test_configuration_rollback_normalizes_canonical_aliases():
    serializer = ConfigurationRollbackSerializer(
        data={"target_version": 2, "change_summary": "Restore stable delivery policy"}
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["version"] == 2
    assert serializer.validated_data["reason"] == "Restore stable delivery policy"


@pytest.mark.parametrize(
    "payload",
    [
        {"target_version": 2},
        {"change_summary": "No target"},
        {"target_version": 0, "change_summary": "Invalid version"},
    ],
)
def test_configuration_rollback_requires_positive_target_and_reason(payload):
    serializer = ConfigurationRollbackSerializer(data=payload)
    assert not serializer.is_valid()
