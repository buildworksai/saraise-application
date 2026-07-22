"""Sanitized, bounded liveness and readiness proof."""

from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace

import pytest
from django.utils import timezone

from src.core.health import HealthCheckResult

from .. import health
from ..integrations import IntegrationRegistry, set_integration_registry

pytestmark = pytest.mark.django_db


def test_liveness_is_process_only() -> None:
    result = health.liveness_probe()
    assert result.healthy is True
    assert result.details == {"code": "live"}


def test_database_and_outbox_readiness_execute_real_queries() -> None:
    database = health.database_rls_probe()
    outbox = health.outbox_probe()
    assert database.healthy is True
    assert database.details["code"] == "ready"
    assert outbox.healthy is True
    assert outbox.details["code"] == "ready"


def test_optional_unconfigured_integrations_are_degraded_not_fabricated_healthy() -> None:
    set_integration_registry(IntegrationRegistry())
    report = health.get_module_health()

    assert report.status == "degraded"
    assert report.status_code == 200
    assert report.components["database_rls"]["status"] == "healthy"
    assert report.components["async_outbox"]["status"] == "healthy"
    for dependency in health.DEPENDENCIES:
        assert report.components[dependency]["status"] == "degraded"
        assert report.components[dependency]["configured"] is False


def test_required_failure_returns_503_but_optional_failure_does_not(monkeypatch: pytest.MonkeyPatch) -> None:
    unavailable = HealthCheckResult(False, "unavailable", timezone.now(), {"code": "dependency_unavailable"})
    ready = HealthCheckResult(True, "ready", timezone.now(), {"code": "ready"})
    monkeypatch.setattr(health, "database_rls_probe", lambda tenant_id=None: unavailable)
    monkeypatch.setattr(health, "outbox_probe", lambda: ready)
    set_integration_registry(IntegrationRegistry())

    report = health.get_module_health(uuid.uuid4())

    assert report.status == "unavailable"
    assert report.status_code == 503
    assert report.components["database_rls"] == {
        "status": "unavailable",
        "code": "dependency_unavailable",
        "required": True,
    }


def test_database_probe_suppresses_raw_exception_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> list[str]:
        raise RuntimeError("postgresql://secret@private-host/internal")

    monkeypatch.setattr(health.connection.introspection, "table_names", fail)
    result = health.database_rls_probe()
    serialized = json.dumps({"message": result.message, "details": result.details})

    assert result.healthy is False
    assert result.details == {"code": "dependency_unavailable"}
    assert "secret" not in serialized
    assert "private-host" not in serialized


def test_bounded_call_times_out_without_waiting_for_wedged_probe() -> None:
    started = time.monotonic()

    success, value = health._bounded_call(lambda: time.sleep(0.2), timeout_seconds=0.01)

    assert success is False
    assert value is None
    assert time.monotonic() - started < 0.1


def test_live_and_ready_helpers_return_sanitized_documents(monkeypatch: pytest.MonkeyPatch) -> None:
    request = SimpleNamespace(tenant_id=uuid.uuid4())
    live = health.live_health(request)  # type: ignore[arg-type]
    monkeypatch.setattr(
        health,
        "get_module_health",
        lambda tenant_id=None: health.ModuleHealthReport(
            "unavailable",
            {"database_rls": {"status": "unavailable", "code": "dependency_unavailable", "required": True}},
        ),
    )
    ready = health.ready_health(request)  # type: ignore[arg-type]

    assert live.status_code == 200
    assert json.loads(live.content)["live"] is True
    assert ready.status_code == 503
    payload = json.loads(ready.content)
    assert payload["ready"] is False
    assert "error" not in payload
