"""Fail-closed health coverage for backup recovery readiness."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from src.modules.backup_recovery import health


@contextmanager
def _tenant_context(tenant_id):
    yield tenant_id


class _Cursor:
    def __init__(self, *, rows=None, fail=False):
        self.rows = rows or []
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
        return (1,)

    def fetchall(self):
        return self.rows


class _Introspection:
    def __init__(self, tables):
        self._tables = tables

    def table_names(self):
        return list(self._tables)


class _Connection:
    def __init__(self, *, vendor="sqlite", tables=(), rows=(), fail=False):
        self.vendor = vendor
        self.introspection = _Introspection(tables)
        self._rows = rows
        self._fail = fail

    def cursor(self):
        return _Cursor(rows=self._rows, fail=self._fail)


class _ValuesList:
    def __init__(self, value):
        self._value = value

    def first(self):
        return self._value


class _Query:
    def __init__(self, *, exists=False, first=None, iterable=None, fail=False):
        self._exists = exists
        self._first = first
        self._iterable = iterable or []
        self._fail = fail

    def __iter__(self):
        if self._fail:
            raise RuntimeError("private query failure")
        return iter(self._iterable)

    def order_by(self, *args):
        return self

    def values_list(self, *args, **kwargs):
        if self._fail:
            raise RuntimeError("private query failure")
        return _ValuesList(self._first)

    def exists(self):
        if self._fail:
            raise RuntimeError("private query failure")
        return self._exists


class _Manager:
    def __init__(self, query):
        self._query = query

    def filter(self, *args, **kwargs):
        return self._query


def _catalog_tables() -> set[str]:
    return {
        health.BackupStorageTarget._meta.db_table,
        health.BackupRetentionPolicy._meta.db_table,
        health.BackupSchedule._meta.db_table,
        health.BackupJob._meta.db_table,
        health.BackupArchive._meta.db_table,
        health.BackupVerification._meta.db_table,
        health.AsyncJob._meta.db_table,
        health.OutboxEvent._meta.db_table,
    }


def test_dependency_includes_detail_only_when_present():
    assert health._dependency("database", True) == {
        "key": "database",
        "status": "healthy",
        "critical": True,
    }
    assert health._dependency("database", False, detail="Schema unavailable.") == {
        "key": "database",
        "status": "unavailable",
        "critical": True,
        "detail": "Schema unavailable.",
    }


def test_health_fails_closed_when_database_and_async_probes_raise(monkeypatch):
    tenant_id = uuid.uuid4()
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(health, "connection", _Connection(fail=True))
    monkeypatch.setattr(health.OutboxEvent, "objects", _Manager(_Query(fail=True)))
    monkeypatch.setattr(health.BackupSchedule, "objects", _Manager(_Query(fail=True)))

    result = health.check_module_health(tenant_id)

    assert result["status"] == "unavailable"
    assert result["ready"] is False
    assert result["database"]["detail"] == "Database schema is unavailable."
    assert result["async_jobs"]["detail"] == "Durable async-job schema is unavailable."
    assert result["outbox"]["detail"] == "Transactional outbox is unavailable."
    assert "private" not in str(result)


def test_health_reports_postgresql_rls_failure_without_exposing_sql(monkeypatch):
    tenant_id = uuid.uuid4()
    catalog_tables = _catalog_tables()
    incomplete_rls_rows = [(health.BackupStorageTarget._meta.db_table, True, False)]
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(
        health,
        "connection",
        _Connection(vendor="postgresql", tables=catalog_tables, rows=incomplete_rls_rows),
    )
    monkeypatch.setattr(health.BackupStorageTarget, "objects", _Manager(_Query(iterable=[])))
    monkeypatch.setattr(health.OutboxEvent, "objects", _Manager(_Query(first=None)))
    monkeypatch.setattr(health.BackupSchedule, "objects", _Manager(_Query(exists=False)))
    monkeypatch.setattr(health.AsyncJob, "objects", _Manager(_Query(first=None)))

    result = health.check_module_health(tenant_id)

    assert result["status"] == "unavailable"
    assert result["ready"] is False
    assert result["database"]["detail"] == "Row-level security is not enabled and forced."
    assert "SELECT" not in str(result)


def test_health_distinguishes_adapter_degradation_from_critical_scheduler_failure(monkeypatch):
    tenant_id = uuid.uuid4()
    now = timezone.now()
    catalog_tables = _catalog_tables()
    target = SimpleNamespace(adapter_key="s3", is_default=True)
    degraded_adapter = SimpleNamespace(
        health=lambda: SimpleNamespace(healthy=False, message="Timeout budget exhausted.")
    )

    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(health, "connection", _Connection(tables=catalog_tables))
    monkeypatch.setattr(health.BackupStorageTarget, "objects", _Manager(_Query(iterable=[target])))
    monkeypatch.setattr(health.OutboxEvent, "objects", _Manager(_Query(first=now - timedelta(seconds=301))))
    monkeypatch.setattr(health.BackupSchedule, "objects", _Manager(_Query(exists=True)))
    monkeypatch.setattr(health.AsyncJob, "objects", _Manager(_Query(first=None)))
    monkeypatch.setattr(health, "_adapter_for", lambda storage_target: degraded_adapter)

    result = health.check_module_health(tenant_id)

    assert result["status"] == "unavailable"
    assert result["ready"] is False
    assert result["adapters"] == [
        {
            "key": "s3",
            "status": "degraded",
            "critical": True,
            "detail": "Timeout budget exhausted.",
        }
    ]
    assert result["oldest_pending_outbox_seconds"] >= 300
    assert result["scheduler"]["detail"] == "No recent due-schedule scan is recorded."


def test_health_reports_healthy_when_catalog_async_outbox_and_scheduler_are_ready(monkeypatch):
    tenant_id = uuid.uuid4()
    catalog_tables = _catalog_tables()
    monkeypatch.setattr(health, "tenant_context", _tenant_context)
    monkeypatch.setattr(health, "connection", _Connection(tables=catalog_tables))
    monkeypatch.setattr(health.BackupStorageTarget, "objects", _Manager(_Query(iterable=[])))
    monkeypatch.setattr(health.OutboxEvent, "objects", _Manager(_Query(first=None)))
    monkeypatch.setattr(health.BackupSchedule, "objects", _Manager(_Query(exists=False)))
    monkeypatch.setattr(health.AsyncJob, "objects", _Manager(_Query(first=None)))

    result = health.check_module_health(tenant_id)

    assert result["status"] == "healthy"
    assert result["ready"] is True
    assert result["database"]["status"] == "healthy"
    assert result["async_jobs"]["status"] == "healthy"
    assert result["outbox"]["detail"] == "Oldest pending event is 0 seconds old."
    assert result["scheduler"]["detail"] == "No scan is required because no schedule is active."
