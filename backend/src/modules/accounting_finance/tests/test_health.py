from __future__ import annotations

from uuid import uuid4

import pytest
from rest_framework.test import APIRequestFactory

from src.modules.accounting_finance import health


def _all_ready(monkeypatch) -> None:
    monkeypatch.setattr(health, "_database_access", lambda: True)
    monkeypatch.setattr(health, "_schema_and_migrations", lambda: True)
    monkeypatch.setattr(health, "_rls_enforced", lambda: True)
    monkeypatch.setattr(health, "handlers_ready", lambda: True)
    monkeypatch.setattr(health, "_mdm_capability", lambda: True)
    monkeypatch.setattr(health, "_circuits_closed", lambda: True)


@pytest.mark.django_db
def test_readiness_is_healthy_only_when_every_check_passes(monkeypatch) -> None:
    _all_ready(monkeypatch)
    report = health.get_module_health()
    assert report.ready is True
    assert report.version == "2.0.0"
    assert {check.name for check in report.checks} == {
        "database",
        "migrations",
        "row_level_security",
        "async_handlers",
        "party_directory",
        "configured_circuits",
    }
    assert all(check.latency_ms >= 0 for check in report.checks)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("probe", "code"),
    [
        ("_database_access", "DATABASE_UNAVAILABLE"),
        ("_schema_and_migrations", "MIGRATIONS_MISSING"),
        ("_rls_enforced", "RLS_NOT_ENFORCED"),
        ("handlers_ready", "HANDLERS_MISSING"),
        ("_mdm_capability", "MDM_CAPABILITY_UNAVAILABLE"),
        ("_circuits_closed", "CIRCUIT_OPEN"),
    ],
)
def test_each_missing_readiness_dependency_fails_closed(monkeypatch, probe, code) -> None:
    _all_ready(monkeypatch)
    monkeypatch.setattr(health, probe, lambda: False)
    report = health.get_module_health()
    assert report.ready is False
    assert code in {check.code for check in report.checks}


@pytest.mark.django_db
def test_database_exception_is_redacted(monkeypatch) -> None:
    _all_ready(monkeypatch)

    def fail():
        raise RuntimeError("postgres://user:secret@private-host/accounting")

    monkeypatch.setattr(health, "_database_access", fail)
    payload = health.get_module_health().as_dict()
    rendered = str(payload)
    assert "secret" not in rendered
    assert "private-host" not in rendered
    assert "DATABASE_UNAVAILABLE" in rendered


@pytest.mark.django_db
def test_ready_endpoint_returns_503_without_exception_text(monkeypatch) -> None:
    def fail():
        raise RuntimeError("token=super-secret")

    monkeypatch.setattr(health, "get_module_health", fail)
    response = health.ready(APIRequestFactory().get("/api/v2/accounting-finance/health/"))
    assert response.status_code == 503
    assert response.data["checks"][0]["code"] == "READINESS_PROBE_FAILED"
    assert "super-secret" not in str(response.data)


@pytest.mark.django_db
def test_open_configured_circuit_makes_readiness_fail(monkeypatch) -> None:
    monkeypatch.setattr(health.extension_registry, "circuit_states", lambda: {"tax.regional": "open"})
    assert health._circuits_closed() is False
    monkeypatch.setattr(health.extension_registry, "circuit_states", lambda: {})
    assert health._circuits_closed() is True


@pytest.mark.django_db
def test_required_mdm_capability_is_not_fabricated(monkeypatch) -> None:
    monkeypatch.setattr(health.extension_registry, "_party", None)
    assert health._mdm_capability() is False
    monkeypatch.setattr(health.extension_registry, "_party", object())
    assert health._mdm_capability() is True


@pytest.mark.django_db
def test_registry_probe_contains_only_bounded_operational_metadata(monkeypatch) -> None:
    _all_ready(monkeypatch)
    result = health.accounting_readiness_probe()
    assert result.healthy is True
    assert result.details["module"] == "accounting_finance"
    serialized = str(result.details)
    assert str(uuid4()) not in serialized
    for forbidden in ("database_name", "row_count", "provider_url", "credentials"):
        assert forbidden not in serialized
