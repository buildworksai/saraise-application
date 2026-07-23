"""Failure-mode and sanitization tests for module readiness."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.modules.customization_framework import health

pytestmark = pytest.mark.django_db


def test_database_failure_is_critical_and_does_not_leak_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "postgres://admin:secret@private-host/customization"

    class BrokenCursor:
        def __enter__(self):
            raise RuntimeError(secret)

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(health.connection, "cursor", lambda: BrokenCursor())
    report = health.get_module_health()
    assert report.status == "unavailable"
    assert report.status_code == 503
    assert report.payload["checks"]["database"]["code"] == "dependency_unavailable"
    assert secret not in str(report.payload)


def test_missing_domain_table_reports_only_a_stable_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health.connection,
        "introspection",
        SimpleNamespace(table_names=lambda: list(health.DOMAIN_TABLES[:-1])),
    )
    ok, code = health._schema_check()
    assert (ok, code) == (False, "schema_missing")


def test_absent_or_invalid_rls_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class CatalogCursor:
        rows: list[tuple[object, ...]] = []

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, *args: object) -> None:
            del args

        def fetchall(self):
            rows, self.rows = self.rows, []
            return rows

    cursor = CatalogCursor()
    fake_connection = SimpleNamespace(vendor="postgresql", cursor=lambda: cursor)
    monkeypatch.setattr(health, "connection", fake_connection)
    assert health._rls_check() == (False, "rls_missing")

    cursor.rows = [(table, True, False) for table in health.DOMAIN_TABLES]
    assert health._rls_check() == (False, "rls_missing")


def test_non_postgresql_backend_cannot_claim_rls_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health,
        "connection",
        SimpleNamespace(vendor="sqlite"),
    )
    assert health._rls_check() == (False, "rls_unverifiable")


def test_valid_forced_rls_and_typed_policies_are_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    class CatalogCursor:
        call = 0

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, *args: object) -> None:
            del args

        def fetchall(self):
            self.call += 1
            if self.call == 1:
                return [(table, True, True) for table in health.DOMAIN_TABLES]
            return [(table, "tenant predicate", "tenant check") for table in health.DOMAIN_TABLES]

    monkeypatch.setattr(
        health,
        "connection",
        SimpleNamespace(vendor="postgresql", cursor=lambda: CatalogCursor()),
    )
    assert health._rls_check() == (True, "ready")


def test_async_tables_are_conditional_and_fail_closed_when_enabled(
    settings: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.CUSTOMIZATION_ASYNC_IMPACT_ENABLED = False
    assert health._async_check() == (True, "disabled")
    settings.CUSTOMIZATION_ASYNC_IMPACT_ENABLED = True
    monkeypatch.setattr(
        health.connection,
        "introspection",
        SimpleNamespace(table_names=lambda: []),
    )
    assert health._async_check() == (False, "schema_missing")


def test_missing_state_machine_registration_is_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health.state_machine_registry, "names", lambda: ())
    assert health._state_machine_check() == (False, "registration_missing")


def test_critical_dependency_or_open_breaker_state_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """A future remote registry/breaker adapter must fail through a stable check result."""

    monkeypatch.setattr(health, "_database_check", lambda: (True, "ready"))
    monkeypatch.setattr(health, "_schema_check", lambda: (True, "ready"))
    monkeypatch.setattr(health, "_rls_check", lambda: (True, "ready"))
    monkeypatch.setattr(health, "_state_machine_check", lambda: (False, "circuit_open"))
    monkeypatch.setattr(health, "_async_check", lambda: (True, "disabled"))
    report = health.get_module_health()
    assert report.status_code == 503
    assert report.payload["checks"]["state_machines"] == {
        "status": "unavailable",
        "code": "circuit_open",
    }
    assert "exception" not in str(report.payload).lower()
