from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.db import connection
from django.test import override_settings
from rest_framework.permissions import AllowAny
from rest_framework.test import APIRequestFactory

from src.core.resilience import CircuitState, DependencyConnectionError
from src.modules.security_access_control import health


def test_health_endpoint_is_public_and_returns_sanitized_ready_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "_database_check", lambda: health.ComponentResult(True, "ready"))
    monkeypatch.setattr(health, "_schema_check", lambda: health.ComponentResult(True, "ready"))
    monkeypatch.setattr(health, "_rls_check", lambda: health.ComponentResult(True, "ready"))
    monkeypatch.setattr(health, "_permission_catalog_check", lambda: health.ComponentResult(True, "ready"))
    monkeypatch.setattr(health, "_local_evaluator_check", lambda: health.ComponentResult(True, "ready"))

    request = APIRequestFactory().get("/api/v2/security-access-control/health/")
    response = health.check_security_module_health(request)

    assert response.status_code == 200
    assert response.data["status"] == "ready"
    assert response.data["ready"] is True
    assert response.data["correlation_id"].startswith("req_")
    assert set(response.data["components"]) == {
        "database",
        "schema",
        "row_level_security",
        "permission_catalog",
        "policy_evaluator",
    }
    assert AllowAny in health.check_security_module_health.cls.permission_classes
    serialized = repr(response.data).lower()
    assert "password" not in serialized and "host" not in serialized and "traceback" not in serialized


def test_database_failure_is_503_and_does_not_expose_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenCursor:
        def __enter__(self):
            raise RuntimeError("postgresql://admin:secret@private.internal/security")

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(connection, "cursor", lambda: BrokenCursor())
    result = health._database_check()
    payload, status_code = health.module_readiness(
        correlation_id="req_test",
        checks={"database": lambda: result},
    )

    assert status_code == 503
    assert payload["components"]["database"] == {
        "status": "unavailable",
        "code": "dependency_unavailable",
    }
    assert "secret" not in repr(payload)


def test_schema_check_requires_every_security_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection.introspection, "table_names", lambda: list(health.EXPECTED_TABLES[:-1]))
    assert health._schema_check() == health.ComponentResult(False, "schema_missing")

    monkeypatch.setattr(connection.introspection, "table_names", lambda: list(health.EXPECTED_TABLES))
    assert health._schema_check() == health.ComponentResult(True, "ready")


def test_rls_missing_fails_postgresql_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    class Cursor:
        call = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def execute(self, _sql: str, _params: object) -> None:
            self.call += 1

        def fetchall(self):
            if self.call == 1:
                return [(table, True, True) for table in health.TENANT_TABLES]
            return [(table, "tenant predicate", None) for table in health.TENANT_TABLES]

    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(connection, "cursor", lambda: Cursor())
    assert health._rls_check() == health.ComponentResult(False, "rls_missing")


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="https://policy.example.test")
def test_remote_dependency_open_circuit_fails_without_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.modules.security_access_control import services

    class Client:
        get_called = False

        def get_breaker(self, dependency: str):
            assert dependency == health.POLICY_DEPENDENCY
            return SimpleNamespace(state=CircuitState.OPEN)

        def get(self, *_args: object, **_kwargs: object):
            self.get_called = True
            raise AssertionError("an open circuit must not perform a health request")

    client = Client()
    monkeypatch.setattr(services, "get_policy_http_client", lambda: client, raising=False)
    result = health._remote_policy_check("req_policy")

    assert result == health.ComponentResult(False, "circuit_open", "open")
    assert client.get_called is False


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="https://policy.example.test")
def test_remote_dependency_transport_failure_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.modules.security_access_control import services

    class Client:
        def get_breaker(self, _dependency: str):
            return SimpleNamespace(state=CircuitState.CLOSED)

        def get(self, url: str, *, dependency: str, **_kwargs: object):
            raise DependencyConnectionError(
                "credential=do-not-expose",
                dependency=dependency,
                url=url,
            )

    monkeypatch.setattr(services, "get_policy_http_client", lambda: Client(), raising=False)
    result = health._remote_policy_check("req_policy")

    assert result == health.ComponentResult(False, "dependency_unavailable", "unknown")
    assert "credential" not in repr(result)


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="https://policy.example.test")
def test_remote_health_probe_uses_shared_client_and_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.modules.security_access_control import services

    observed: dict[str, object] = {}

    class Client:
        def get_breaker(self, _dependency: str):
            return SimpleNamespace(state=CircuitState.CLOSED)

        def get(self, url: str, *, dependency: str, **kwargs: object):
            observed.update(url=url, dependency=dependency, **kwargs)
            return SimpleNamespace(status_code=204)

    monkeypatch.setattr(services, "get_policy_http_client", lambda: Client(), raising=False)
    result = health._remote_policy_check("req_policy")

    assert result == health.ComponentResult(True, "ready", "closed")
    assert observed["url"] == "https://policy.example.test/health/ready"
    assert observed["dependency"] == "policy-engine"
    assert observed["correlation_id"] == "req_policy"


@override_settings(SARAISE_MODE="invalid")
def test_unknown_mode_fails_closed() -> None:
    payload, status_code = health.module_readiness(
        correlation_id="req_mode",
        checks={"database": lambda: health.ComponentResult(True, "ready")},
    )
    assert status_code == 503
    assert payload["components"]["policy_evaluator"]["code"] == "mode_invalid"


def test_component_serializes_circuit_state() -> None:
    assert health.ComponentResult(False, "circuit_open", "open").as_dict() == {
        "status": "unavailable",
        "code": "circuit_open",
        "circuit_state": "open",
    }


def test_database_schema_and_catalog_success_and_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    class Cursor:
        value = (1,)

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def execute(self, _sql: str) -> None:
            return None

        def fetchone(self):
            return self.value

    cursor = Cursor()
    monkeypatch.setattr(connection, "cursor", lambda: cursor)
    assert health._database_check() == health.ComponentResult(True, "ready")
    cursor.value = (0,)
    assert health._database_check() == health.ComponentResult(False, "query_failed")

    monkeypatch.setattr(connection.introspection, "table_names", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert health._schema_check() == health.ComponentResult(False, "dependency_unavailable")

    cursor.value = None
    assert health._permission_catalog_check() == health.ComponentResult(True, "ready")
    monkeypatch.setattr(connection, "cursor", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert health._permission_catalog_check() == health.ComponentResult(False, "catalog_unavailable")


def test_rls_not_applicable_success_and_dependency_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connection, "vendor", "sqlite")
    assert health._rls_check() == health.ComponentResult(True, "not_applicable")

    class Cursor:
        call = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def execute(self, _sql: str, _params: object) -> None:
            self.call += 1

        def fetchall(self):
            if self.call == 1:
                return [(table, True, True) for table in health.TENANT_TABLES]
            return [(table, "using", "check") for table in health.TENANT_TABLES]

    monkeypatch.setattr(connection, "vendor", "postgresql")
    monkeypatch.setattr(connection, "cursor", lambda: Cursor())
    assert health._rls_check() == health.ComponentResult(True, "ready")
    monkeypatch.setattr(connection, "cursor", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert health._rls_check() == health.ComponentResult(False, "dependency_unavailable")


@override_settings(SARAISE_POLICY_ENGINE_URL="")
def test_remote_dependency_requires_configuration() -> None:
    assert health._remote_policy_check("req") == health.ComponentResult(False, "configuration_missing", "unknown")


def test_local_evaluator_registration_is_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.modules.security_access_control import services

    class Evaluator:
        def evaluate_local(self) -> None:
            return None

    monkeypatch.setattr(services, "AccessEvaluationService", Evaluator, raising=False)
    assert health._local_evaluator_check() == health.ComponentResult(True, "ready")
    monkeypatch.setattr(services, "AccessEvaluationService", object)
    assert health._local_evaluator_check() == health.ComponentResult(False, "evaluator_unavailable")


@override_settings(SARAISE_MODE="saas", SARAISE_POLICY_ENGINE_URL="https://policy.example.test")
def test_remote_non_success_circuit_exception_and_unexpected_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.resilience import CircuitBreakerError
    from src.modules.security_access_control import services

    class Client:
        failure: Exception | None = None

        def get_breaker(self, _dependency: str):
            return SimpleNamespace(state=CircuitState.CLOSED)

        def get(self, *_args: object, **_kwargs: object):
            if self.failure:
                raise self.failure
            return SimpleNamespace(status_code=503)

    client = Client()
    monkeypatch.setattr(services, "get_policy_http_client", lambda: client, raising=False)
    assert health._remote_policy_check("req") == health.ComponentResult(False, "dependency_unavailable", "closed")
    client.failure = CircuitBreakerError("policy-engine", 0)
    assert health._remote_policy_check("req") == health.ComponentResult(False, "circuit_open", "open")
    client.failure = RuntimeError("private details")
    assert health._remote_policy_check("req") == health.ComponentResult(False, "dependency_unavailable", "unknown")


@override_settings(SARAISE_MODE="saas")
def test_module_readiness_uses_remote_policy_component(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "_remote_policy_check", lambda _correlation: health.ComponentResult(True, "ready"))
    payload, status_code = health.module_readiness(
        correlation_id="req_saas",
        checks={"database": lambda: health.ComponentResult(True, "ready")},
    )
    assert status_code == 200
    assert payload["components"]["policy_dependency"]["status"] == "ready"
