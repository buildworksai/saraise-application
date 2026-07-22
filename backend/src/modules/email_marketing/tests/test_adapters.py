"""Executable contracts for delivery adapters and extension registries."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.modules.email_marketing import adapters


def _message() -> adapters.DeliveryMessage:
    return adapters.DeliveryMessage(
        recipient="Customer@EXAMPLE.COM",
        from_email="sender@EXAMPLE.COM",
        from_name="SARAISE",
        reply_to=None,
        rendered=adapters.RenderedEmail("Subject", "<p>Hello</p>", "Hello"),
    )


def test_manual_resolver_returns_typed_candidates_without_touching_crm() -> None:
    result = adapters.InlineAudienceResolver().resolve(
        uuid.uuid4(),
        {
            "schema_version": 1,
            "resolver": "manual",
            "recipients": [
                {
                    "email": "Person@EXAMPLE.COM",
                    "recipient_key": "contact-1",
                    "personalization": {"first_name": "Ada"},
                }
            ],
        },
    )
    assert result.resolver_key == "manual"
    assert result.candidates[0].email == "Person@example.com"
    assert result.candidates[0].personalization_data == {"first_name": "Ada"}
    assert result.evidence == {"source": "manual", "candidate_count": 1}


@pytest.mark.parametrize(
    "definition",
    [
        {},
        {"schema_version": 2, "recipients": []},
        {"schema_version": 1, "recipients": "not-an-array"},
        {"schema_version": 1, "recipients": [{"email": "invalid"}]},
    ],
)
def test_manual_resolver_fails_closed_for_invalid_definitions(definition: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        adapters.InlineAudienceResolver().resolve(uuid.uuid4(), definition)


def test_renderer_escapes_variables_sanitizes_html_and_rejects_missing_values() -> None:
    renderer = adapters.DjangoTemplateEmailRenderer()
    rendered = renderer.render(
        {
            "subject": "Hello {{ first_name }}",
            "body_html": '<p onclick="steal()">{{ content }}</p><script>secret()</script>',
            "body_text": "Hello {{ first_name }}",
        },
        {"first_name": "Ada", "content": "<strong>not markup</strong>"},
    )
    assert rendered.subject == "Hello Ada"
    assert "onclick" not in rendered.html
    assert "script" not in rendered.html
    assert "secret" not in rendered.html
    assert "&lt;strong&gt;not markup&lt;/strong&gt;" in rendered.html
    with pytest.raises(adapters.RenderingError, match="unresolved"):
        renderer.render({"subject": "Hi {{ missing }}", "body_text": "Body"}, {})


def test_registry_rejects_collisions_and_incompatible_spi() -> None:
    registry: adapters.ExtensionRegistry[object] = adapters.ExtensionRegistry("test")
    first = SimpleNamespace(schema_version="1.0")
    registry.register("provider", first)
    assert registry.get("provider") is first
    registry.register("provider", first)
    with pytest.raises(adapters.AdapterAlreadyRegistered):
        registry.register("provider", SimpleNamespace(schema_version="1.0"))
    with pytest.raises(ValueError, match="schema_version"):
        registry.register("future", SimpleNamespace(schema_version="2.0"))


def test_simulated_django_backend_never_returns_provider_success(settings) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    gateway = adapters.DjangoEmailDeliveryGateway()
    result = gateway.submit(_message(), "attempt-1", str(uuid.uuid4()))
    assert result.successful is False
    assert result.code == "simulated_backend"
    assert gateway.health().available is False


def test_real_backend_acknowledgement_creates_allowlisted_receipt(monkeypatch, settings) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    observed: dict[str, object] = {}

    class FakeEmail:
        def __init__(self, **kwargs: object) -> None:
            observed.update(kwargs)

        def attach_alternative(self, body: str, content_type: str) -> None:
            observed["alternative_type"] = content_type

        def send(self, fail_silently: bool) -> int:
            observed["fail_silently"] = fail_silently
            return 1

    monkeypatch.setattr(adapters, "get_connection", lambda **kwargs: object())
    monkeypatch.setattr(adapters, "EmailMultiAlternatives", FakeEmail)
    result = adapters.DjangoEmailDeliveryGateway().submit(_message(), "attempt-2", str(uuid.uuid4()))
    receipt = result.unwrap()
    assert result.code == "transport_accepted"
    assert receipt.acknowledgement == "transport_accepted"
    assert receipt.evidence == {"backend": settings.EMAIL_BACKEND, "messages_accepted": 1}
    assert observed["to"] == ["Customer@example.com"]
    assert "password" not in repr(receipt.evidence).lower()


def test_ambiguous_timeout_is_not_retried(monkeypatch, settings) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    calls = 0

    class TimedOutEmail:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def attach_alternative(self, body: str, content_type: str) -> None:
            del body, content_type

        def send(self, fail_silently: bool) -> int:
            nonlocal calls
            calls += 1
            raise TimeoutError("recipient@example.com secret provider response")

    monkeypatch.setattr(adapters, "get_connection", lambda **kwargs: object())
    monkeypatch.setattr(adapters, "EmailMultiAlternatives", TimedOutEmail)
    result = adapters.DjangoEmailDeliveryGateway().submit(_message(), "attempt-3", str(uuid.uuid4()))
    assert result.successful is False
    assert result.code == "transport_timeout"
    assert result.ambiguous is True
    assert result.retryable is False
    assert calls == 1


def test_lookup_explicitly_reports_unsupported_reconciliation(settings) -> None:
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    result = adapters.DjangoEmailDeliveryGateway().lookup("<provider-message@example.com>")
    assert result.successful is False
    assert result.code == "lookup_unsupported"
    assert result.ambiguous is True
