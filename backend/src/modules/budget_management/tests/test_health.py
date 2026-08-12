"""Health-check coverage for budget management."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

from src.modules.budget_management import health


class _Cursor:
    def __init__(self, *, one=(1,), fail=False):
        self.one = one
        self.fail = fail

    def __enter__(self):
        if self.fail:
            raise RuntimeError("private database failure")
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("private query failure")

    def fetchone(self):
        return self.one


class _Connection:
    def __init__(self, *, vendor="sqlite", one=(1,), fail=False):
        self.vendor = vendor
        self.one = one
        self.fail = fail

    def cursor(self):
        return _Cursor(one=self.one, fail=self.fail)


@contextmanager
def _atomic():
    yield


def _integrations(accounting=None, workflow=None, notification=None):
    return SimpleNamespace(accounting=accounting, workflow=workflow, notification=notification)


def test_adapter_state_normalizes_absent_configured_unknown_and_failures():
    assert health._adapter_state(None) == "not_configured"
    assert health._adapter_state(SimpleNamespace()) == "configured"
    assert health._adapter_state(SimpleNamespace(health_state=lambda: "OPEN")) == "open"
    assert health._adapter_state(SimpleNamespace(health_state=lambda: "surprising")) == "unknown"
    assert (
        health._adapter_state(SimpleNamespace(health_state=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
        == "unknown"
    )


def test_check_health_reports_database_tenant_rls_and_job_failures(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "connection", _Connection(fail=True))
    monkeypatch.setattr(health, "get_current_tenant_id", lambda: uuid.uuid4())
    monkeypatch.setattr(health.transaction, "atomic", _atomic)
    monkeypatch.setattr(
        health, "enqueue", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("private queue error"))
    )
    monkeypatch.setattr(health, "get_integrations", lambda: _integrations())

    result = health.check_health(tenant_id)

    assert result.status == "unhealthy"
    assert result.dependencies["database"] == "unhealthy"
    assert result.dependencies["tenant_context"] == "unhealthy"
    assert result.dependencies["durable_jobs"] == "unhealthy"
    assert result.dependencies["accounting"] == "not_configured"
    assert "private queue error" not in str(result)


def test_check_health_reports_postgresql_rls_probe_and_optional_adapter_degradation(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "connection", _Connection(vendor="postgresql", one=(False,)))
    monkeypatch.setattr(health, "get_current_tenant_id", lambda: tenant_id)
    monkeypatch.setattr(health.transaction, "atomic", _atomic)
    monkeypatch.setattr(health.transaction, "set_rollback", lambda value: None)
    monkeypatch.setattr(health, "enqueue", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        health,
        "get_integrations",
        lambda: _integrations(
            accounting=SimpleNamespace(health_state=lambda: "closed"),
            workflow=SimpleNamespace(health_state=lambda: "half_open"),
            notification=SimpleNamespace(health_state=lambda: "configured"),
        ),
    )

    result = health.check_health(tenant_id)

    assert result.status == "unhealthy"
    assert result.dependencies["rls"] == "unhealthy"
    assert result.dependencies["workflow"] == "half_open"


def test_check_health_reports_healthy_for_ready_sqlite_dependencies(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "connection", _Connection())
    monkeypatch.setattr(health, "get_current_tenant_id", lambda: tenant_id)
    monkeypatch.setattr(health.transaction, "atomic", _atomic)
    monkeypatch.setattr(health.transaction, "set_rollback", lambda value: None)
    monkeypatch.setattr(health, "enqueue", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        health,
        "get_integrations",
        lambda: _integrations(
            accounting=SimpleNamespace(health_state=lambda: "closed"),
            workflow=SimpleNamespace(health_state=lambda: "configured"),
            notification=SimpleNamespace(health_state=lambda: "closed"),
        ),
    )

    result = health.check_health(tenant_id)

    assert result.status == "healthy"
    assert result.dependencies["database"] == "healthy"
    assert result.dependencies["tenant_context"] == "healthy"
    assert result.dependencies["rls"] == "not_applicable"
    assert result.dependencies["durable_jobs"] == "healthy"


def test_module_health_and_view_handle_valid_and_missing_tenant(monkeypatch):
    tenant_id = uuid.uuid4()
    result = health.HealthResult("degraded", "budget_management", "now", {"accounting": "open"})
    monkeypatch.setattr(health, "check_health", lambda tenant: result)

    assert health.get_module_health(tenant_id) == {
        "status": "degraded",
        "checked_at": "now",
        "dependencies": {"accounting": "open"},
    }

    response = health.health_check(SimpleNamespace(tenant_id=str(tenant_id)))
    assert response.status_code == 200
    assert b"budget_management" in response.content

    missing = health.health_check(SimpleNamespace(tenant_id=None))
    assert missing.status_code == 503
    assert b"tenant_context" in missing.content
