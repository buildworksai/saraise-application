"""Readiness behavior, dependency degradation, and redaction tests."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.exceptions import PermissionDenied

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


@contextmanager
def _atomic():
    yield


def test_bounded_call_reports_success_exception_and_timeout(monkeypatch) -> None:
    completed, value = health._bounded_call(lambda: "ok")
    assert (completed, value) == (True, "ok")

    completed, value = health._bounded_call(lambda: (_ for _ in ()).throw(RuntimeError("secret failure")))
    assert (completed, value) == (False, None)

    class NeverFinishes:
        def __init__(self, *args, **kwargs):
            self._alive = True

        def start(self):
            return None

        def join(self, timeout):
            return None

        def is_alive(self):
            return True

    monkeypatch.setattr(health.threading, "Thread", NeverFinishes)
    completed, value = health._bounded_call(lambda: "never", timeout_seconds=0)
    assert (completed, value) == (False, None)


def test_outbox_persistence_probe_rolls_back_and_sanitizes_failures(monkeypatch, tenant_a) -> None:
    class EventObjects:
        def __init__(self, pk):
            self.pk = pk

        def create(self, **kwargs):
            assert kwargs["tenant_id"] == tenant_a.id
            return SimpleNamespace(pk=self.pk)

    monkeypatch.setattr(health.transaction, "atomic", _atomic)
    monkeypatch.setattr(health.transaction, "set_rollback", lambda value: None)
    monkeypatch.setattr(health.OutboxEvent, "objects", EventObjects(pk="event-1"))
    assert health.outbox_persistence_probe(tenant_a.id).code == "OUTBOX_WRITABLE"

    monkeypatch.setattr(health.OutboxEvent, "objects", EventObjects(pk=None))
    assert health.outbox_persistence_probe(tenant_a.id).code == "OUTBOX_UNAVAILABLE"


def test_broker_probe_reports_current_overdue_and_unavailable_states(monkeypatch, tenant_a) -> None:
    class Query:
        def __init__(self, exists):
            self._exists = exists

        def exists(self):
            if isinstance(self._exists, Exception):
                raise self._exists
            return self._exists

    class OutboxObjects:
        def __init__(self, exists):
            self.exists = exists

        def filter(self, **kwargs):
            assert kwargs["tenant_id"] == tenant_a.id
            return Query(self.exists)

    monkeypatch.setattr(health, "runtime_configuration", lambda tenant_id: health.DEFAULT_CONFIGURATION)
    monkeypatch.setattr(health.OutboxEvent, "objects", OutboxObjects(False))
    assert health.broker_acknowledgement_probe(tenant_a.id).code == "BROKER_ACK_CURRENT"

    monkeypatch.setattr(health.OutboxEvent, "objects", OutboxObjects(True))
    assert health.broker_acknowledgement_probe(tenant_a.id).code == "BROKER_ACK_OVERDUE"

    monkeypatch.setattr(health.OutboxEvent, "objects", OutboxObjects(RuntimeError("private broker state")))
    result = health.broker_acknowledgement_probe(tenant_a.id)
    assert result.code == "BROKER_ACK_STATE_UNAVAILABLE"
    assert "private broker" not in repr(result.as_dict()).lower()


def test_adapter_registry_probe_reports_registered_missing_and_unavailable(monkeypatch) -> None:
    class ConnectorValues:
        def __init__(self, required):
            self.required = required

        def values_list(self, *args, **kwargs):
            return self.required

    class ConnectorObjects:
        def __init__(self, required):
            self.required = required

        def filter(self, **kwargs):
            return ConnectorValues(self.required)

    monkeypatch.setattr(health, "_registry_functions", lambda: (lambda: ("smtp", "webhook"), lambda key: object()))
    monkeypatch.setattr(health.Connector, "objects", ConnectorObjects(["smtp"]))
    assert health.adapter_registry_probe().code == "ADAPTERS_REGISTERED"

    monkeypatch.setattr(health.Connector, "objects", ConnectorObjects(["missing"]))
    assert health.adapter_registry_probe().code == "CONNECTOR_ADAPTER_UNAVAILABLE"

    monkeypatch.setattr(health, "_registry_functions", lambda: (_ for _ in ()).throw(RuntimeError("registry secret")))
    result = health.adapter_registry_probe()
    assert result.code == "ADAPTER_REGISTRY_UNAVAILABLE"
    assert "registry secret" not in repr(result.as_dict()).lower()


def test_dependency_circuit_probe_reports_no_adapters_operation_results_and_object_health(monkeypatch) -> None:
    monkeypatch.setattr(health, "_registry_functions", lambda: (lambda: (), lambda key: object()))
    assert health.dependency_circuit_probe().code == "DEPENDENCY_CIRCUIT_UNAVAILABLE"

    class HealthyAdapter:
        def health(self):
            return SimpleNamespace(healthy=True, circuit_state="closed")

    monkeypatch.setattr(health, "_registry_functions", lambda: (lambda: ("healthy",), lambda key: HealthyAdapter()))
    assert health.dependency_circuit_probe().code == "DEPENDENCY_CIRCUITS_CLOSED"

    class FailedOperationAdapter:
        def health(self):
            return OperationResult.failed("down", evidence={"circuit_state": "closed"})

    monkeypatch.setattr(
        health, "_registry_functions", lambda: (lambda: ("failed",), lambda key: FailedOperationAdapter())
    )
    assert health.dependency_circuit_probe().code == "DEPENDENCY_CIRCUIT_UNAVAILABLE"


def test_health_view_binds_tenant_when_available_and_fails_closed_when_missing(monkeypatch, tenant_a) -> None:
    request = SimpleNamespace(tenant_id=tenant_a.id)
    view = health.IntegrationPlatformHealthView()
    monkeypatch.setattr(health, "_tenant_from_request", lambda request: tenant_a.id)
    monkeypatch.setattr(health.APIView, "perform_authentication", lambda self, request: None)
    view.perform_authentication(request)
    assert request.tenant_id == tenant_a.id

    monkeypatch.setattr(
        health, "_tenant_from_request", lambda request: (_ for _ in ()).throw(PermissionDenied("missing"))
    )
    request_without_tenant = SimpleNamespace()
    view.perform_authentication(request_without_tenant)
    assert not hasattr(request_without_tenant, "tenant_id")
