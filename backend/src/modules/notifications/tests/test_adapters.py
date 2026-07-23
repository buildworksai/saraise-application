from __future__ import annotations

import uuid

import pytest
from django.core import mail
from django.test import override_settings

from src.core.api.results import CapabilityUnavailable
from src.modules.notifications import adapters
from src.modules.notifications.adapters import (
    AdapterAlreadyRegistered,
    AdapterDescriptor,
    AdapterHealth,
    AdapterNotRegistered,
    AdapterRegistry,
    DeliveryCommand,
    DeliveryResult,
    DjangoEmailAdapter,
    EndpointVerificationCommand,
    InAppAdapter,
    UnavailableAdapter,
    VerificationResult,
    validate_action_url,
)


def command(**changes: object) -> DeliveryCommand:
    values: dict[str, object] = {
        "tenant_id": uuid.uuid4(),
        "delivery_id": uuid.uuid4(),
        "idempotency_token": "delivery-token",
        "recipient": "person@example.com",
        "subject": "Subject",
        "body": "Body",
        "configuration": {"from_email": "sender@example.com"},
        "correlation_id": uuid.uuid4(),
    }
    values.update(changes)
    return DeliveryCommand(**values)  # type: ignore[arg-type]


def verification(**changes: object) -> EndpointVerificationCommand:
    values: dict[str, object] = {
        "tenant_id": uuid.uuid4(),
        "endpoint_id": uuid.uuid4(),
        "address": "person@example.com",
        "correlation_id": uuid.uuid4(),
        "configuration": {},
    }
    values.update(changes)
    return EndpointVerificationCommand(**values)  # type: ignore[arg-type]


def test_delivery_command_normalizes_and_freezes_values():
    value = command(channel=" EMAIL ", recipient_type=" USER ", extension_metadata={"extensions.crm": {"id": 1}})
    assert value.channel == "email"
    assert value.recipient_type == "user"
    assert value.recipient_address == "person@example.com"
    with pytest.raises(TypeError):
        value.configuration["changed"] = True  # type: ignore[index]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tenant_id": "bad"}, "UUID"),
        ({"correlation_id": "bad"}, "correlation_id"),
        ({"channel": "fax"}, "not supported"),
        ({"recipient_type": "x" * 21}, "recipient_type"),
        ({"recipient": ""}, "recipient"),
        ({"content_type": "image/png"}, "content_type"),
        ({"extension_metadata": {"crm": {}}}, "extensions"),
        ({"extension_metadata": {"extensions.crm": "bad"}}, "object"),
    ],
)
def test_delivery_command_rejects_invalid_contract(changes, message):
    with pytest.raises((TypeError, ValueError), match=message):
        command(**changes)


def test_results_require_real_evidence_and_coherent_states():
    accepted = DeliveryResult(True, provider_message_id="provider-1", evidence={"accepted": True})
    assert accepted.acknowledged is True
    with pytest.raises(ValueError, match="evidence"):
        DeliveryResult(True)
    with pytest.raises(ValueError, match="cannot be retryable"):
        DeliveryResult(True, retryable=True, evidence={"accepted": True})
    with pytest.raises(ValueError, match="error_code"):
        DeliveryResult(False)
    with pytest.raises(ValueError, match="255"):
        DeliveryResult(False, provider_message_id="x" * 256, error_code="FAILED")
    assert VerificationResult(False, "invalid").error_code == "invalid"
    assert VerificationResult(True, "verified", {"proof": True}).error_code == ""
    with pytest.raises(ValueError, match="evidence"):
        VerificationResult(True, "verified")


def test_adapter_health_is_sanitized():
    ready = AdapterHealth(True, "ready", "ready", {"circuit_state": "closed"})
    assert ready.details["circuit_state"] == "closed"
    with pytest.raises(ValueError, match="status"):
        AdapterHealth(True, "unknown", "ready")
    with pytest.raises(ValueError, match="non-public"):
        AdapterHealth(True, "ready", "ready", {"credential": "secret"})


def test_descriptor_and_registry_lifecycle_reject_collisions():
    registry = AdapterRegistry()
    adapter = UnavailableAdapter("vendor.sms", "sms")
    descriptor = AdapterDescriptor("vendor.sms", "sms", owner="paid.sms")
    assert registry.register(descriptor, adapter) is adapter
    assert registry.get(" VENDOR.SMS ") is adapter
    assert registry.descriptor("vendor.sms") == descriptor
    assert registry.descriptors() == (descriptor,)
    with pytest.raises(AdapterAlreadyRegistered):
        registry.register(descriptor, adapter)
    with pytest.raises(ValueError, match="identity"):
        AdapterRegistry().register(AdapterDescriptor("other", "sms"), adapter)
    assert registry.unregister("vendor.sms") is adapter
    assert registry.unregister("vendor.sms") is None
    with pytest.raises(AdapterNotRegistered):
        registry.get("vendor.sms")


@pytest.mark.parametrize("key", ["", "UPPER", "1bad", "bad key", "x" * 101])
def test_descriptor_rejects_invalid_keys(key):
    with pytest.raises(ValueError):
        AdapterDescriptor(key, "sms")


def test_in_app_adapter_requires_durable_evidence():
    expected_id = uuid.uuid4()
    value = InAppAdapter(lambda sent: {"delivery_id": str(sent.delivery_id), "notification_id": str(expected_id)}).send(command())
    assert value.accepted is True
    assert value.provider_message_id == str(expected_id)
    assert value.confirmation_supported is False
    with pytest.raises(RuntimeError, match="durable"):
        InAppAdapter(lambda sent: {}).send(command())
    with pytest.raises(ValueError, match="another channel"):
        InAppAdapter(lambda sent: {"delivery_id": str(sent.delivery_id)}).send(command(channel="email"))
    with pytest.raises(CapabilityUnavailable):
        InAppAdapter().verify_endpoint(verification())


def test_unavailable_adapter_fails_explicitly_for_every_operation():
    adapter = UnavailableAdapter("sms.test", "sms")
    health = adapter.health(uuid.uuid4(), {})
    assert health.healthy is False and health.code == "adapter_unavailable"
    with pytest.raises(CapabilityUnavailable):
        adapter.send(command())
    with pytest.raises(CapabilityUnavailable):
        adapter.verify_endpoint(verification())


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="sender@example.com",
)
def test_django_email_adapter_sends_only_on_backend_acknowledgement():
    result = DjangoEmailAdapter().send(command(content_type="text/html"))
    assert result.accepted is True
    assert result.provider_message_id.endswith("@saraise.local")
    assert result.confirmation_supported is False
    assert len(mail.outbox) == 1
    assert mail.outbox[0].alternatives
    assert mail.outbox[0].extra_headers["X-Correlation-ID"]


def test_django_email_adapter_rejects_invalid_inputs(monkeypatch, settings):
    adapter = DjangoEmailAdapter()
    with pytest.raises(ValueError, match="another channel"):
        adapter.send(command(channel="sms"))
    with pytest.raises(ValueError, match="recipient"):
        adapter.send(command(recipient="not-an-email"))
    with pytest.raises(CapabilityUnavailable, match="sender"):
        adapter.send(command(configuration={"from_email": "invalid"}))
    settings.DEFAULT_FROM_EMAIL = "sender@example.com"
    monkeypatch.setattr(adapters.EmailMultiAlternatives, "send", lambda self, fail_silently: 0)
    with pytest.raises(CapabilityUnavailable, match="acknowledge"):
        adapter.send(command(configuration={}))


def test_django_email_health_and_verification(settings):
    adapter = DjangoEmailAdapter()
    assert adapter.health(uuid.uuid4(), {"enabled": False}).status == "disabled"
    settings.EMAIL_BACKEND = ""
    assert adapter.health(uuid.uuid4(), {"enabled": True}).code == "email_backend_missing"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    assert adapter.health(uuid.uuid4(), {"enabled": True}).healthy is True
    with pytest.raises(ValueError, match="invalid"):
        adapter.verify_endpoint(verification(address="bad"))
    with pytest.raises(ValueError, match="only email"):
        adapter.verify_endpoint(verification(kind="push"))
    result = adapter.verify_endpoint(verification(kind="email"))
    assert result.verified and result.evidence["backend"] == "configured"


@pytest.mark.parametrize(
    "url",
    ["//evil.example/path", "http://good.example", "https://evil.example", "/\\evil", "/bad\npath", "x" * 501],
)
def test_action_url_policy_rejects_unsafe_destinations(url):
    with pytest.raises(ValueError):
        validate_action_url(url, frozenset({"good.example"}))


def test_action_url_policy_accepts_empty_internal_and_allowlisted_https():
    assert validate_action_url("") == ""
    assert validate_action_url("/notifications/1") == "/notifications/1"
    assert validate_action_url("https://GOOD.example/path", frozenset({"good.example"})) == "https://GOOD.example/path"


def test_resilient_client_factory_validates_bounds(monkeypatch):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, allowlist, **kwargs):
            captured["allowlist"] = allowlist
            captured.update(kwargs)

    monkeypatch.setattr(adapters, "ResilientHttpClient", FakeClient)
    configuration = {
        "allowed_hosts": ["provider.example"],
        "base_url": "https://provider.example",
        "timeout_seconds": 5,
        "retry": {"max_attempts": 3, "base_seconds": 1},
        "circuit": {"failure_threshold": 4, "reset_seconds": 60},
    }
    client = adapters.resilient_http_client("provider", configuration)
    assert isinstance(client, FakeClient)
    assert captured["max_retries"] == 2
    assert captured["failure_threshold"] == 4


@pytest.mark.parametrize(
    "change",
    [
        {"allowed_hosts": []},
        {"timeout_seconds": 0},
        {"retry": None},
        {"retry": {"max_attempts": 0, "base_seconds": 1}},
        {"retry": {"max_attempts": 1, "base_seconds": -1}},
        {"circuit": {"failure_threshold": 0, "reset_seconds": 1}},
        {"circuit": {"failure_threshold": 1, "reset_seconds": 0}},
    ],
)
def test_resilient_client_factory_rejects_unsafe_configuration(change):
    configuration = {
        "allowed_hosts": ["provider.example"],
        "timeout_seconds": 5,
        "retry": {"max_attempts": 3, "base_seconds": 1},
        "circuit": {"failure_threshold": 4, "reset_seconds": 60},
    }
    configuration.update(change)
    expected = CapabilityUnavailable if not configuration.get("allowed_hosts") else ValueError
    with pytest.raises(expected):
        adapters.resilient_http_client("provider", configuration)
