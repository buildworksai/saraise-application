"""Readiness behavior, dependency degradation, and redaction tests."""

from __future__ import annotations

import uuid

import pytest
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.api.results import OperationResult

from .. import health
from ..health import HealthCheck

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_access_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test policy allows declared capability",
            tenant_id=uuid.UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def _replace_probes(monkeypatch: pytest.MonkeyPatch, *, broker=True, adapters=True, circuits=True, database=True):
    monkeypatch.setattr(
        health,
        "database_probe",
        lambda: HealthCheck(database, "DATABASE_READY" if database else "DATABASE_UNAVAILABLE", True, {}),
    )
    monkeypatch.setattr(
        health,
        "outbox_persistence_probe",
        lambda tenant_id: HealthCheck(True, "OUTBOX_WRITABLE", True, {}),
    )
    monkeypatch.setattr(
        health,
        "broker_acknowledgement_probe",
        lambda tenant_id: HealthCheck(
            broker,
            "BROKER_ACK_CURRENT" if broker else "BROKER_ACK_STATE_UNAVAILABLE",
            True,
            {"within_dispatch_slo": broker},
        ),
    )
    monkeypatch.setattr(
        health,
        "adapter_registry_probe",
        lambda: HealthCheck(
            adapters,
            "ADAPTERS_REGISTERED" if adapters else "CONNECTOR_ADAPTER_UNAVAILABLE",
            False,
            {},
        ),
    )
    monkeypatch.setattr(
        health,
        "dependency_circuit_probe",
        lambda: HealthCheck(
            circuits,
            "DEPENDENCY_CIRCUITS_CLOSED" if circuits else "DEPENDENCY_CIRCUIT_UNAVAILABLE",
            False,
            {},
        ),
    )


def test_module_health_is_healthy_only_when_every_check_is_proven(monkeypatch, tenant_a) -> None:
    _replace_probes(monkeypatch)
    payload, status_code = health.module_health(tenant_a.id)
    assert status_code == status.HTTP_200_OK
    assert payload["status"] == "healthy"
    assert [item["name"] for item in payload["checks"]] == [
        "database",
        "outbox",
        "broker",
        "adapters",
        "dependency_circuits",
    ]
    assert all(item["status"] == "healthy" for item in payload["checks"])


@pytest.mark.parametrize("failed_probe", ["adapters", "circuits"])
def test_noncritical_connector_dependency_failure_is_degraded(monkeypatch, tenant_a, failed_probe) -> None:
    _replace_probes(
        monkeypatch,
        adapters=failed_probe != "adapters",
        circuits=failed_probe != "circuits",
    )
    payload, status_code = health.module_health(tenant_a.id)
    assert status_code == status.HTTP_200_OK
    assert payload["status"] == "degraded"
    failed = next(item for item in payload["checks"] if item["status"] == "degraded")
    assert failed["critical"] is False


@pytest.mark.parametrize("failed_probe", ["database", "broker"])
def test_critical_dependency_failure_is_unavailable(monkeypatch, tenant_a, failed_probe) -> None:
    _replace_probes(
        monkeypatch,
        database=failed_probe != "database",
        broker=failed_probe != "broker",
    )
    payload, status_code = health.module_health(tenant_a.id)
    assert status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert payload["status"] == "unavailable"
    failed = next(item for item in payload["checks"] if item["status"] == "unavailable")
    assert failed["critical"] is True


def test_circuit_open_is_reported_without_dependency_details(monkeypatch) -> None:
    class Adapter:
        @staticmethod
        def health():
            return OperationResult.succeeded(
                {"status": "unavailable"},
                evidence={"circuit_state": "open", "authorization": "must-not-leak"},
            )

    monkeypatch.setattr(health, "_registry_functions", lambda: ((lambda: ("adapter",)), lambda key: Adapter()))
    result = health.dependency_circuit_probe()
    assert result.healthy is False
    assert result.code == "DEPENDENCY_CIRCUIT_UNAVAILABLE"
    assert "authorization" not in repr(result.details).lower()


def test_database_probe_redacts_raw_exception(monkeypatch) -> None:
    def fail():
        raise RuntimeError("postgres://admin:secret@example.test/private")

    monkeypatch.setattr(health.connection, "cursor", fail)
    result = health.database_probe()
    assert result.healthy is False
    assert result.details == {}
    assert "secret" not in repr(result.as_dict()).lower()


def test_governed_health_endpoint_envelopes_sanitized_checks(monkeypatch, tenant_a_client) -> None:
    _replace_probes(monkeypatch)
    response = tenant_a_client.get("/api/v2/integration-platform/health/")
    assert response.status_code == status.HTTP_200_OK
    document = response.json()
    assert document["data"]["status"] == "healthy"
    assert document["meta"]["correlation_id"]
    assert "count" not in repr(document["data"]).lower()


def test_unauthenticated_health_is_401(api_client) -> None:
    response = api_client.get("/api/v2/integration-platform/health/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
