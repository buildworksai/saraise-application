from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.core.health import HealthCheckResult
from src.modules.sales_management import health
from src.modules.sales_management.integrations import Capability

pytestmark = pytest.mark.django_db


def result(healthy=True, code="READY", age=timedelta()):
    return HealthCheckResult(healthy, "sanitized", timezone.now() - age, {"code": code})


def test_liveness_is_process_only_and_sanitized():
    probe = health.liveness_probe()
    assert probe.healthy and probe.details == {"code": "LIVE"}


def test_required_dependency_failure_returns_unavailable_without_exception(monkeypatch):
    monkeypatch.setattr(health, "database_rls_probe", lambda tenant=None: result(False, "DEPENDENCY_UNAVAILABLE"))
    monkeypatch.setattr(health, "outbox_probe", lambda: result())
    report = health.get_module_health()
    assert report.status == "unavailable" and report.status_code == 503
    assert "exception" not in str(report.as_dict()).lower()


def test_stale_probe_is_unavailable(monkeypatch):
    monkeypatch.setattr(health, "database_rls_probe", lambda tenant=None: result(age=timedelta(seconds=31)))
    monkeypatch.setattr(health, "outbox_probe", lambda: result())
    report = health.get_module_health()
    assert report.components["database_rls"]["reason_code"] == "STALE_PROBE"


def test_optional_integrations_degrade_but_do_not_fail_readiness(monkeypatch):
    monkeypatch.setattr(health, "database_rls_probe", lambda tenant=None: result())
    monkeypatch.setattr(health, "outbox_probe", lambda: result())
    report = health.get_module_health()
    assert report.status == "degraded" and report.ready
    for capability in Capability:
        assert report.components[capability.value]["required"] is False


def test_database_probe_does_not_leak_raw_error(monkeypatch):
    def explode():
        raise RuntimeError("postgres://secret-user:secret-password@private-host")

    monkeypatch.setattr(health.connection.introspection, "table_names", explode)
    probe = health.database_rls_probe()
    assert not probe.healthy and probe.details == {"code": "DEPENDENCY_UNAVAILABLE"}
    assert "secret" not in probe.message
