import uuid
from types import SimpleNamespace

import pytest

from src.core.tenancy import tenant_context
from src.modules.multi_company import health


class _Query:
    def __init__(self, *, exists=False, first=None, values=()):
        self._exists = exists
        self._first = first
        self._values = values

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args):
        return self

    def first(self):
        return self._first

    def exists(self):
        return self._exists

    def values_list(self, *_args, **_kwargs):
        return self._values


class _TenantManager:
    def __init__(self, query):
        self.query = query

    def for_tenant(self, _tenant_id):
        return self.query


class _Adapter:
    def __init__(self, state=None, *, raises=False):
        self.state = state
        self.raises = raises

    def health_state(self):
        if self.raises:
            raise RuntimeError("dependency failed")
        return self.state


def _install_common_health_dependencies(monkeypatch, tenant_id, *, stale=False, outbox=False, config=True):
    monkeypatch.setattr(
        health.Company,
        "objects",
        _TenantManager(_Query(exists=False)),
    )
    monkeypatch.setattr(
        health.MultiCompanyConfigurationVersion,
        "objects",
        _TenantManager(
            _Query(
                first=SimpleNamespace(settings={"job_timeout_seconds": 60, "job_max_retries": 2}) if config else None
            )
        ),
    )
    monkeypatch.setattr(
        health.MigrationRecorder.Migration,
        "objects",
        _Query(values=("0001_initial", "0002_something")),
    )
    monkeypatch.setattr(health, "enqueue", lambda *args, **kwargs: SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(health, "get_handler", lambda command: object())
    monkeypatch.setattr(
        health.AsyncJob,
        "objects",
        _TenantManager(_Query(exists=stale)),
    )
    monkeypatch.setattr(
        health.OutboxEvent,
        "objects",
        _TenantManager(_Query(exists=outbox)),
    )
    monkeypatch.setattr(
        health.integrations,
        "ledger",
        _Adapter("closed"),
    )
    monkeypatch.setattr(
        health.integrations,
        "exchange_rates",
        _Adapter("configured"),
    )
    monkeypatch.setattr(health.integrations, "workflow", _Adapter("closed"))
    monkeypatch.setattr(health.integrations, "notifications", _Adapter("configured"))
    monkeypatch.setattr(health.integrations, "reports", _Adapter("closed"))
    return tenant_id


@pytest.mark.django_db
def test_module_health_reports_healthy_without_sensitive_counts(monkeypatch):
    tenant_id = uuid.uuid4()
    _install_common_health_dependencies(monkeypatch, tenant_id)

    with tenant_context(tenant_id):
        result = health.get_module_health(tenant_id)

    assert result["status"] == "healthy"
    assert result["checks"] == {
        "database": "ready",
        "tenant_isolation": "ready",
        "rls": "not_applicable",
        "migrations": "ready",
        "job_persistence": "ready",
        "job_dispatch": "ready",
        "stale_jobs": "ready",
        "outbox": "ready",
        "ledger": "closed",
        "exchange_rates": "configured",
        "workflow": "closed",
        "notifications": "configured",
        "reports": "closed",
    }
    assert set(result) == {"status", "checked_at", "checks"}


@pytest.mark.django_db
def test_module_health_distinguishes_optional_backlog_from_critical_failure(monkeypatch):
    tenant_id = uuid.uuid4()
    _install_common_health_dependencies(monkeypatch, tenant_id, stale=True, outbox=True)
    monkeypatch.setattr(health.integrations, "workflow", _Adapter("open"))

    with tenant_context(tenant_id):
        result = health.get_module_health(tenant_id)

    assert result["status"] == "degraded"
    assert result["checks"]["stale_jobs"] == "detected"
    assert result["checks"]["outbox"] == "backlog"
    assert result["checks"]["workflow"] == "open"


@pytest.mark.django_db
def test_module_health_fails_closed_for_tenant_mismatch_missing_config_and_required_dependency(monkeypatch):
    tenant_id = uuid.uuid4()
    other_tenant_id = uuid.uuid4()
    _install_common_health_dependencies(monkeypatch, tenant_id, config=False)
    monkeypatch.setattr(health.integrations, "ledger", _Adapter("open"))
    monkeypatch.setattr(health.integrations, "exchange_rates", _Adapter("garbage"))

    with tenant_context(other_tenant_id):
        result = health.get_module_health(tenant_id)

    assert result["status"] == "unhealthy"
    assert result["checks"]["tenant_isolation"] == "unavailable"
    assert result["checks"]["stale_jobs"] == "configuration_unavailable"
    assert result["checks"]["ledger"] == "open"
    assert result["checks"]["exchange_rates"] == "unknown"


def test_dependency_state_handles_unconfigured_configured_unknown_and_exceptions():
    assert health._dependency_state(None) == "not_configured"
    assert health._dependency_state(SimpleNamespace()) == "configured"
    assert health._dependency_state(_Adapter("half_open")) == "half_open"
    assert health._dependency_state(_Adapter("unsupported")) == "unknown"
    assert health._dependency_state(_Adapter(raises=True)) == "unknown"


def test_active_stale_job_seconds_validates_configuration(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(
        health.MultiCompanyConfigurationVersion,
        "objects",
        _TenantManager(_Query(first=SimpleNamespace(settings={"job_timeout_seconds": 30, "job_max_retries": 3}))),
    )
    assert health._active_stale_job_seconds(tenant_id) == 120

    for settings in (
        {"job_timeout_seconds": 0, "job_max_retries": 3},
        {"job_timeout_seconds": 30, "job_max_retries": -1},
        {"job_timeout_seconds": "30", "job_max_retries": 3},
    ):
        monkeypatch.setattr(
            health.MultiCompanyConfigurationVersion,
            "objects",
            _TenantManager(_Query(first=SimpleNamespace(settings=settings))),
        )
        assert health._active_stale_job_seconds(tenant_id) is None


@pytest.mark.django_db
def test_module_health_reports_required_probe_failures_without_exception_details(monkeypatch):
    tenant_id = uuid.uuid4()
    _install_common_health_dependencies(monkeypatch, tenant_id)

    class BadCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args, **_kwargs):
            return None

        def fetchone(self):
            return ("bad",)

    monkeypatch.setattr(health.connection, "cursor", lambda: BadCursor())
    monkeypatch.setattr(health.MigrationRecorder.Migration, "objects", _Query(values=()))
    monkeypatch.setattr(
        health,
        "enqueue",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("queue storage leaked detail")),
    )
    monkeypatch.setattr(
        health,
        "get_handler",
        lambda _command: (_ for _ in ()).throw(RuntimeError("handler leaked detail")),
    )

    with tenant_context(tenant_id):
        result = health.get_module_health(tenant_id)

    assert result["status"] == "unhealthy"
    assert result["checks"]["database"] == "unavailable"
    assert result["checks"]["migrations"] == "unavailable"
    assert result["checks"]["job_persistence"] == "unavailable"
    assert result["checks"]["job_dispatch"] == "unavailable"
    assert "queue storage leaked detail" not in str(result)
