"""Correlation and sensitive-data exclusion across durable security evidence."""

from __future__ import annotations

import io
import json
import logging
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured

from src.core.async_jobs.models import OutboxEvent
from src.core.observability.logging import JSONFormatter, ObservabilityContextFilter
from src.modules.security_access_control.models import SecurityAuditLog
from src.modules.security_access_control.observability import enforce_security_json_logging
from src.modules.security_access_control.serializers import SecurityAuditLogSerializer
from src.modules.security_access_control.services import AccessEvaluationService, AuditService

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


def test_correlation_links_audit_and_outbox_and_redacts_nested_sensitive_values(tenant_a) -> None:
    correlation = f"corr-{uuid.uuid4()}"
    secret = "never-persist-this-value"
    event, audit = AuditService.append_with_outbox(
        tenant_a.id,
        action="security.role.changed",
        actor_type="user",
        actor_id=uuid.uuid4(),
        resource_type="role",
        resource_id=uuid.uuid4(),
        decision=None,
        reason_codes=("CONFIGURATION_CHANGED",),
        details={
            "password": secret,
            "authorization": f"Bearer {secret}",
            "session_id": secret,
            "subject_email": secret,
            "row_attributes": {"ssn": secret},
            "mask_input": secret,
            "safe": "retained",
        },
        ip_address=None,
        user_agent="",
        correlation_id=correlation,
    )
    audit.refresh_from_db()
    event = OutboxEvent.objects.get(pk=event.pk)
    assert audit.correlation_id == correlation
    assert audit.outbox_event_id == event.id
    assert event.payload["correlation_id"] == correlation
    assert secret not in str(audit.details)
    assert secret not in str(event.payload)
    assert audit.details["safe"] == "retained"


def test_remote_dependency_log_and_request_propagate_correlation_without_secrets(
    tenant_a, tenant_a_user, monkeypatch, caplog
) -> None:
    client = Mock()
    client.post.side_effect = TimeoutError("bounded timeout")
    monkeypatch.setattr("src.modules.security_access_control.services.get_policy_http_client", lambda: client)
    request = SimpleNamespace(correlation_id="corr-remote-observe")
    with caplog.at_level(logging.WARNING, logger="saraise.security_access_control"):
        decision = AccessEvaluationService.evaluate_remote(
            tenant_a.id,
            tenant_a_user,
            "security.roles:read",
            resource_context={"record_id": str(uuid.uuid4())},
            request=request,
        )
    assert not decision.allowed
    kwargs = client.post.call_args.kwargs
    assert kwargs["correlation_id"] == "corr-remote-observe"
    assert kwargs["json"]["context"]["correlation_id"] == "corr-remote-observe"
    assert "authorization" not in str(kwargs).lower()
    rendered = " ".join(record.getMessage() for record in caplog.records)
    assert "security.policy_dependency.degraded" in rendered
    assert "bounded timeout" not in rendered


def test_audit_query_remains_tenant_scoped_for_observability(tenant_a, tenant_b) -> None:
    common = dict(
        action="security.access.decided",
        actor_id=uuid.uuid4(),
        resource_type="access_decision",
        correlation_id="same-correlation",
    )
    own = SecurityAuditLog.objects.create(tenant_id=tenant_a.id, **common)
    SecurityAuditLog.objects.create(tenant_id=tenant_b.id, **common)
    assert list(SecurityAuditLog.objects.for_tenant(tenant_a.id)) == [own]


def test_public_audit_representation_excludes_tenant_actor_network_and_outbox_plumbing(tenant_a) -> None:
    audit = SecurityAuditLog.objects.create(
        tenant_id=tenant_a.id,
        action="security.profile.changed",
        actor_id=uuid.uuid4(),
        resource_type="security_profile",
        correlation_id="corr-public-audit",
        ip_address="192.0.2.10",
        user_agent="sensitive operational client fingerprint",
        outbox_event_id=uuid.uuid4(),
    )

    representation = SecurityAuditLogSerializer(audit).data

    assert set(representation).isdisjoint({"tenant_id", "actor_id", "ip_address", "user_agent", "outbox_event_id"})
    assert representation["correlation_id"] == "corr-public-audit"


def test_security_logger_contract_serializes_structured_correlation_and_security_fields() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(ObservabilityContextFilter())
    logger = logging.Logger("saraise.security_access_control.contract-test")
    logger.propagate = False
    logger.addHandler(handler)

    enforce_security_json_logging(logger).warning(
        "security.policy.denied",
        extra={
            "correlation_id": "corr-json-contract",
            "tenant_id": "tenant-contract",
            "reason_codes": ["DENY_DEFAULT"],
            "permission_code": "security.roles:read",
        },
    )

    payload = json.loads(stream.getvalue())
    assert payload["correlation_id"] == "corr-json-contract"
    assert payload["tenant_id"] == "tenant-contract"
    assert payload["reason_codes"] == ["DENY_DEFAULT"]
    assert payload["permission_code"] == "security.roles:read"


def test_security_logger_contract_rejects_plain_text_or_context_free_handlers() -> None:
    logger = logging.Logger("saraise.security_access_control.invalid-contract")
    logger.propagate = False
    logger.addHandler(logging.StreamHandler())
    with pytest.raises(ImproperlyConfigured, match="JSONFormatter"):
        enforce_security_json_logging(logger)

    logger.handlers[0].setFormatter(JSONFormatter())
    with pytest.raises(ImproperlyConfigured, match="ObservabilityContextFilter"):
        enforce_security_json_logging(logger)
