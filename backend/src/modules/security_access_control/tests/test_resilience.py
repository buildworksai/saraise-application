"""Fail-closed policy dependency behavior and bounded outbound attempts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.modules.security_access_control.services import AccessEvaluationService

pytest_plugins = ["src.core.testing.factories"]
pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("timeout"),
        ConnectionError("unavailable"),
        RuntimeError("circuit open"),
        ValueError("SSRF target rejected"),
    ],
)
def test_timeout_transport_circuit_and_ssrf_failure_deny_in_one_attempt(
    tenant_a, tenant_a_user, monkeypatch, failure
) -> None:
    client = Mock()
    client.post.side_effect = failure
    monkeypatch.setattr("src.modules.security_access_control.services.get_policy_http_client", lambda: client)
    decision = AccessEvaluationService.evaluate_remote(
        tenant_a.id,
        tenant_a_user,
        "security.roles:read",
        request=SimpleNamespace(correlation_id="corr-resilience"),
    )
    assert not decision.allowed and decision.reason_codes == ("ENGINE_UNAVAILABLE",)
    assert client.post.call_count == 1


def test_breaker_recovery_requires_fresh_authoritative_allow(tenant_a, tenant_a_user, monkeypatch) -> None:
    client = Mock()
    client.post.side_effect = [
        RuntimeError("circuit open"),
        SimpleNamespace(
            status_code=200,
            json=lambda: {
                "decision": "allow",
                "reason_codes": ["ALLOW"],
                "applied_policies": ["recovered-policy"],
            },
        ),
    ]
    monkeypatch.setattr("src.modules.security_access_control.services.get_policy_http_client", lambda: client)
    denied = AccessEvaluationService.evaluate_remote(tenant_a.id, tenant_a_user, "security.roles:read")
    recovered = AccessEvaluationService.evaluate_remote(tenant_a.id, tenant_a_user, "security.roles:read")
    assert not denied.allowed
    assert recovered.allowed and recovered.applied_policies == ("recovered-policy",)
    assert client.post.call_count == 2


def test_malformed_success_payload_never_becomes_allow(tenant_a, tenant_a_user, monkeypatch) -> None:
    client = Mock()
    client.post.return_value = SimpleNamespace(
        status_code=200,
        json=lambda: {"decision": "allow", "reason_codes": "ALLOW", "applied_policies": []},
    )
    monkeypatch.setattr("src.modules.security_access_control.services.get_policy_http_client", lambda: client)
    decision = AccessEvaluationService.evaluate_remote(tenant_a.id, tenant_a_user, "security.roles:read")
    assert not decision.allowed and decision.reason_codes == ("INVALID_POLICY_RESPONSE",)
