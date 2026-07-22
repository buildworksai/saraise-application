from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.utils import timezone

from src.core.health import HealthCheckResult, HealthRegistry
from src.modules.compliance_management import health


pytestmark = pytest.mark.django_db


def test_storage_probe_verifies_complete_migrated_schema():
    result = health.storage_probe()
    assert result.healthy is True
    assert result.details == {"database": "available", "schema": "available"}
    assert timezone.now() - result.checked_at < timedelta(seconds=2)


def test_missing_table_is_unhealthy(monkeypatch):
    original = health._required_tables
    monkeypatch.setattr(health, "_required_tables", lambda: original() + ("missing_compliance_table",))
    result = health.storage_probe()
    assert result.healthy is False
    assert result.details["schema"] == "unavailable"


def test_database_timeout_is_unhealthy_without_exception_text(monkeypatch):
    def timeout(cursor, tables):
        del cursor, tables
        raise TimeoutError("postgresql://secret-user:secret-password@internal")

    monkeypatch.setattr(health, "_sqlite_tables_exist", timeout)
    result = health.storage_probe()
    assert result.healthy is False
    serialized = json.dumps({"message": result.message, "details": result.details})
    assert "secret" not in serialized
    assert "postgresql" not in serialized


def test_unexpected_exception_is_unhealthy(monkeypatch):
    monkeypatch.setattr(health, "_required_tables", lambda: (_ for _ in ()).throw(RuntimeError("private")))
    result = health.storage_probe()
    assert result.healthy is False
    assert result.message == "compliance storage is unavailable"


def test_health_route_exposes_no_tenant_counts_or_exception(monkeypatch):
    monkeypatch.setattr(
        health,
        "storage_probe",
        lambda: HealthCheckResult(False, "compliance storage is unavailable", details={"schema": "unavailable"}),
    )
    response = health.health_check(RequestFactory().get("/health/module"))
    payload = json.loads(response.content)
    assert response.status_code == 503
    assert set(payload) == {"status", "module", "checked_at", "checks"}
    assert "error" not in payload


def test_registry_rejects_stale_probe_result():
    now = timezone.now()
    registry = HealthRegistry(clock=lambda: now)
    registry.register(
        health.HEALTH_PROBE_NAME,
        lambda: HealthCheckResult(True, checked_at=now - timedelta(seconds=31)),
        staleness_limit=30,
    )
    report = registry.check_readiness()
    assert report.ready is False
    assert report.components[health.HEALTH_PROBE_NAME]["stale"] is True
