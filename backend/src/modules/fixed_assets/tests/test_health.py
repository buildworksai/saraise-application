"""Health-check coverage for fixed assets."""

from __future__ import annotations

from types import SimpleNamespace

from src.modules.fixed_assets import health


class _Cursor:
    def __init__(self, *, rows=(), one=(1,), fail=False):
        self.rows = list(rows)
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

    def fetchall(self):
        return self.rows


class _Introspection:
    def __init__(self, tables, *, fail=False):
        self._tables = tables
        self._fail = fail

    def table_names(self):
        if self._fail:
            raise RuntimeError("private introspection failure")
        return list(self._tables)


class _Connection:
    def __init__(self, *, vendor="sqlite", tables=(), rows=(), one=(1,), fail=False):
        self.vendor = vendor
        self.introspection = _Introspection(tables, fail=fail)
        self.rows = rows
        self.one = one
        self.fail = fail

    def cursor(self):
        return _Cursor(rows=self.rows, one=self.one, fail=self.fail)


def test_database_rls_readiness_reports_schema_rls_and_database_failures(monkeypatch):
    monkeypatch.setattr(health, "connection", _Connection(tables=set()))
    assert health.database_rls_readiness().code == "SCHEMA_MISSING"

    monkeypatch.setattr(health, "connection", _Connection(tables=health.DOMAIN_TABLES))
    assert health.database_rls_readiness().code == "RLS_UNSUPPORTED"

    incomplete_rows = [(table, True, False) for table in health.DOMAIN_TABLES]
    monkeypatch.setattr(
        health,
        "connection",
        _Connection(vendor="postgresql", tables=health.DOMAIN_TABLES, rows=incomplete_rows),
    )
    assert health.database_rls_readiness().code == "RLS_MISSING"

    monkeypatch.setattr(health, "connection", _Connection(fail=True))
    assert health.database_rls_readiness().code == "DATABASE_UNAVAILABLE"


def test_database_rls_readiness_reports_ready_when_tables_are_forced_and_policied(monkeypatch):
    class Cursor(_Cursor):
        call_count = 0

        def fetchall(self):
            self.call_count += 1
            if self.call_count == 1:
                return [(table, True, True) for table in health.DOMAIN_TABLES]
            return [
                (table, "tenant_id = current_setting('app.tenant_id')", "tenant_id = current_setting('app.tenant_id')")
                for table in health.DOMAIN_TABLES
            ]

    class Connection(_Connection):
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(health, "connection", Connection(vendor="postgresql", tables=health.DOMAIN_TABLES))

    assert health.database_rls_readiness() == health.ReadinessCheck("database_rls", "healthy", "READY")


def test_async_job_readiness_reports_schema_persistence_and_ready(monkeypatch):
    monkeypatch.setattr(health, "connection", _Connection(tables=set()))
    assert health.async_job_readiness().code == "ASYNC_SCHEMA_MISSING"

    monkeypatch.setattr(health, "connection", _Connection(tables=health.ASYNC_TABLES, fail=True))
    assert health.async_job_readiness().code == "ASYNC_PERSISTENCE_UNAVAILABLE"

    monkeypatch.setattr(health, "connection", _Connection(tables=health.ASYNC_TABLES))
    assert health.async_job_readiness().code == "READY"


def test_accounting_adapter_readiness_handles_missing_unconfigured_default_and_ready(monkeypatch):
    monkeypatch.setattr("src.modules.fixed_assets.integrations.extension_registry.accounting_port", lambda: None)
    assert health.accounting_adapter_readiness().status == "degraded"

    unconfigured = SimpleNamespace(is_configured=lambda: False)
    monkeypatch.setattr(
        "src.modules.fixed_assets.integrations.extension_registry.accounting_port", lambda: unconfigured
    )
    assert health.accounting_adapter_readiness().code == "CAPABILITY_UNAVAILABLE"

    configured = SimpleNamespace(is_configured=lambda: True)
    monkeypatch.setattr("src.modules.fixed_assets.integrations.extension_registry.accounting_port", lambda: configured)
    assert health.accounting_adapter_readiness().code == "READY"


def test_module_health_and_compatibility_view_report_status_without_detail_leaks(monkeypatch):
    monkeypatch.setattr(
        health, "database_rls_readiness", lambda: health.ReadinessCheck("database_rls", "healthy", "READY")
    )
    monkeypatch.setattr(health, "async_job_readiness", lambda: health.ReadinessCheck("async_jobs", "healthy", "READY"))
    monkeypatch.setattr(
        health,
        "accounting_adapter_readiness",
        lambda: health.ReadinessCheck("accounting_adapter", "degraded", "CAPABILITY_UNAVAILABLE"),
    )

    report = health.get_module_health()

    assert report.status == "degraded"
    assert report.status_code == 200
    assert report.payload["checks"][2]["code"] == "CAPABILITY_UNAVAILABLE"

    monkeypatch.setattr(health, "connection", _Connection(one=(0,)))
    response = health.health_check(SimpleNamespace())

    assert response.status_code == 503
    assert b"fixed_assets" in response.content
