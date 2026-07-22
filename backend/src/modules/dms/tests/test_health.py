"""Truthful, non-leaking DMS readiness evidence."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.utils import timezone

from src.core.health import HealthCheckResult
from src.modules.dms import health
from src.modules.dms.health import (
    DOMAIN_TABLES,
    database_readiness_probe,
    get_module_health,
    outbox_readiness_probe,
    register_health_probes,
    storage_readiness_probe,
)
from src.modules.dms.storage import StorageHealth

pytest_plugins = ["src.core.testing"]


class _Cursor:
    def __init__(self, results: list[list[tuple[object, ...]]]) -> None:
        self.results = iter(results)
        self.current: list[tuple[object, ...]] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *args: object) -> None:
        del args

    def execute(self, sql: str, params: object) -> None:
        del sql, params
        self.current = next(self.results)

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.current


class _Connection:
    vendor = "postgresql"

    def __init__(self, *, tables: set[str], query_results: list[list[tuple[object, ...]]]) -> None:
        self.introspection = SimpleNamespace(table_names=lambda: list(tables))
        self._query_results = query_results

    def cursor(self) -> _Cursor:
        return _Cursor(self._query_results)


def test_database_probe_verifies_canonical_tables_and_forced_read_write_rls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forced = [(table, True, True) for table in DOMAIN_TABLES]
    policies = [(table, True, True) for table in DOMAIN_TABLES]
    monkeypatch.setattr(
        health,
        "connection",
        _Connection(tables=set(DOMAIN_TABLES), query_results=[forced, policies]),
    )
    result = database_readiness_probe()
    assert result.healthy is True
    assert result.details["code"] == "ready"
    assert result.details["latency_ms"] >= 0


@pytest.mark.parametrize(
    ("tables", "forced", "policies", "expected_code"),
    [
        (set(DOMAIN_TABLES[:-1]), [], [], "schema_missing"),
        (set(DOMAIN_TABLES), [], [(table, True, True) for table in DOMAIN_TABLES], "rls_missing"),
        (set(DOMAIN_TABLES), [(table, True, True) for table in DOMAIN_TABLES], [], "rls_missing"),
    ],
)
def test_database_probe_fails_for_missing_schema_or_rls(
    monkeypatch: pytest.MonkeyPatch,
    tables: set[str],
    forced: list[tuple[object, ...]],
    policies: list[tuple[object, ...]],
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        health,
        "connection",
        _Connection(tables=tables, query_results=[forced, policies]),
    )
    result = database_readiness_probe()
    assert result.healthy is False
    assert result.details["code"] == expected_code


def test_database_probe_sanitizes_driver_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    failing = SimpleNamespace(
        introspection=SimpleNamespace(table_names=lambda: (_ for _ in ()).throw(RuntimeError("password=secret"))),
        vendor="postgresql",
    )
    monkeypatch.setattr(health, "connection", failing)
    result = database_readiness_probe()
    assert result.healthy is False
    assert result.details["code"] == "dependency_unavailable"
    assert "secret" not in result.message


@pytest.mark.parametrize(
    ("storage_health", "healthy", "code"),
    [
        (StorageHealth(True, "healthy", 1.25, "ready"), True, "ready"),
        (StorageHealth(True, "degraded", 2.5, "cleanup_failed", cleanup_ok=False), True, "cleanup_failed"),
        (StorageHealth(False, "unhealthy", 3.75, "dependency_unavailable"), False, "dependency_unavailable"),
    ],
)
def test_storage_roundtrip_and_cleanup_status_are_preserved_without_evidence_leakage(
    monkeypatch: pytest.MonkeyPatch,
    storage_health: StorageHealth,
    healthy: bool,
    code: str,
) -> None:
    adapter = SimpleNamespace(health_probe=lambda: storage_health)
    monkeypatch.setattr(health, "get_document_storage", lambda: adapter)
    result = storage_readiness_probe()
    assert result.healthy is healthy
    assert result.details["code"] == code
    assert result.details["latency_ms"] == storage_health.latency_ms


def test_storage_exception_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> object:
        raise RuntimeError("s3://secret-bucket?credential=private")

    monkeypatch.setattr(health, "get_document_storage", fail)
    result = storage_readiness_probe()
    assert result.healthy is False
    assert result.details["code"] == "dependency_unavailable"
    assert result.details["latency_ms"] >= 0
    assert "secret" not in result.message


class _OutboxFilter:
    def __init__(self, *, stale: bool) -> None:
        self.stale = stale
        self.kwargs: dict[str, object] = {}

    def filter(self, **kwargs: object) -> _OutboxFilter:
        self.kwargs = kwargs
        return self

    def exists(self) -> bool:
        return self.stale


@pytest.mark.parametrize(("stale", "healthy"), [(False, True), (True, False)])
def test_outbox_probe_is_dms_scoped_and_detects_stale_pending_events(
    monkeypatch: pytest.MonkeyPatch,
    stale: bool,
    healthy: bool,
) -> None:
    manager = _OutboxFilter(stale=stale)
    table_name = health.OutboxEvent._meta.db_table
    monkeypatch.setattr(
        health,
        "connection",
        SimpleNamespace(introspection=SimpleNamespace(table_names=lambda: [table_name])),
    )
    fake_outbox = SimpleNamespace(_meta=SimpleNamespace(db_table=table_name), objects=manager)
    monkeypatch.setattr(health, "OutboxEvent", fake_outbox)
    result = outbox_readiness_probe()
    assert result.healthy is healthy
    assert manager.kwargs["event_type__startswith"] == "dms."
    assert "tenant" not in str(result.details).lower()


def test_module_payload_exposes_status_latency_and_no_exception_or_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = HealthCheckResult(True, "raw internal detail", timezone.now(), {"code": "ready", "latency_ms": 1.0})
    monkeypatch.setattr(health, "database_readiness_probe", lambda: ready)
    monkeypatch.setattr(health, "storage_readiness_probe", lambda: ready)
    monkeypatch.setattr(health, "outbox_readiness_probe", lambda: ready)
    report = get_module_health()
    rendered = str(report.payload).lower()
    assert report.status == "healthy"
    assert report.status_code == 200
    assert "raw internal detail" not in rendered
    assert "exception" not in rendered
    assert "count" not in rendered


def test_storage_cleanup_failure_is_degraded_not_fabricated_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = HealthCheckResult(True, "ready", timezone.now(), {"code": "ready"})
    degraded = HealthCheckResult(True, "cleanup degraded", timezone.now(), {"code": "cleanup_failed"})
    monkeypatch.setattr(health, "database_readiness_probe", lambda: ready)
    monkeypatch.setattr(health, "storage_readiness_probe", lambda: degraded)
    monkeypatch.setattr(health, "outbox_readiness_probe", lambda: ready)
    report = get_module_health()
    assert report.status == "degraded"
    assert report.status_code == 200
    assert report.payload["checks"]["storage"]["status"] == "degraded"


def test_required_storage_failure_makes_readiness_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    ready = HealthCheckResult(True, "ready", timezone.now(), {"code": "ready"})
    unavailable = HealthCheckResult(False, "unavailable", timezone.now(), {"code": "dependency_unavailable"})
    monkeypatch.setattr(health, "database_readiness_probe", lambda: ready)
    monkeypatch.setattr(health, "storage_readiness_probe", lambda: unavailable)
    monkeypatch.setattr(health, "outbox_readiness_probe", lambda: ready)
    report = get_module_health()
    assert report.status == "unhealthy"
    assert report.status_code == 503
    assert report.payload["checks"]["storage"]["status"] == "unhealthy"


def test_registers_all_three_probes_as_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []
    registry = SimpleNamespace(register=lambda *args, **kwargs: calls.append((*args, kwargs)))
    monkeypatch.setattr(health, "health_registry", registry)
    register_health_probes()
    assert {call[0] for call in calls} == {"dms.database_rls", "dms.storage", "dms.outbox"}
    assert all(call[-1]["critical"] is True for call in calls)
