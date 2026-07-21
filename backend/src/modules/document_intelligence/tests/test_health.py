"""Sanitized readiness aggregation for healthy and degraded dependencies."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from src.core.health import HealthCheckResult
from src.modules.document_intelligence import health
from src.modules.document_intelligence.adapters import DependencyHealth, RegisteredProviderResolver

from .factories import DeterministicOCRAdapter


@pytest.mark.django_db
def test_database_and_async_schema_probes_are_real_and_non_counting() -> None:
    database = health.database_readiness_probe()
    asynchronous = health.async_readiness_probe()
    assert database.healthy is True
    assert database.details == {"code": "ready"}
    assert asynchronous.healthy is True
    assert asynchronous.details == {"code": "ready"}
    assert "count" not in database.details
    assert "count" not in asynchronous.details


def test_dms_probe_marks_stale_and_circuit_state_without_raw_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = DependencyHealth(
        False,
        "private-upstream-failure-code",
        timezone.now() - timedelta(minutes=5),
        "open",
    )
    gateway = type("Gateway", (), {"health": lambda self: stale})()
    monkeypatch.setattr(health, "get_dms_gateway", lambda: gateway)

    result = health.dms_readiness_probe()

    assert result.healthy is False
    assert result.message == "dependency_unavailable"
    assert result.details == {"code": "stale", "required": True, "circuit_state": "open"}


def test_provider_probe_reports_healthy_degraded_unavailable_stale_and_circuit_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver = RegisteredProviderResolver()
    primary = DeterministicOCRAdapter()
    secondary = DeterministicOCRAdapter()
    resolver.register_ocr("primary", primary)
    resolver.register_ocr("secondary", secondary)
    monkeypatch.setattr(health, "get_provider_resolver", lambda: resolver)

    assert health.provider_readiness_probe().details["status"] == "healthy"

    secondary.health = lambda: DependencyHealth(False, "timeout", timezone.now())  # type: ignore[method-assign]
    degraded = health.provider_readiness_probe()
    assert degraded.healthy is True
    assert degraded.details == {"code": "partial_provider_failure", "status": "degraded"}

    primary.health = lambda: DependencyHealth(False, "breaker", timezone.now(), "open")  # type: ignore[method-assign]
    unavailable = health.provider_readiness_probe()
    assert unavailable.healthy is False
    assert unavailable.details == {"code": "circuit_open", "status": "unavailable"}

    primary.health = lambda: DependencyHealth(  # type: ignore[method-assign]
        True, "ready", timezone.now() - timedelta(minutes=2)
    )
    secondary.health = lambda: DependencyHealth(  # type: ignore[method-assign]
        True, "ready", timezone.now() - timedelta(minutes=2)
    )
    stale = health.provider_readiness_probe()
    assert stale.healthy is False
    assert stale.details["status"] == "unavailable"


def _probe(healthy: bool, code: str, *, status: str | None = None) -> HealthCheckResult:
    details = {"code": code}
    if status:
        details["status"] = status
    return HealthCheckResult(healthy, code, timezone.now(), details)


def test_module_report_distinguishes_degraded_from_critical_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health, "database_readiness_probe", lambda: _probe(True, "ready"))
    monkeypatch.setattr(health, "async_readiness_probe", lambda: _probe(True, "ready"))
    monkeypatch.setattr(health, "dms_readiness_probe", lambda: _probe(True, "ready"))
    monkeypatch.setattr(
        health,
        "provider_readiness_probe",
        lambda: _probe(True, "partial_provider_failure", status="degraded"),
    )
    degraded = health.get_module_health()
    assert degraded.status == "degraded"
    assert degraded.status_code == 200
    assert degraded.payload["status"] == "degraded"
    assert degraded.payload["ready"] is True
    providers = next(item for item in degraded.payload["dependencies"] if item["name"] == "providers")
    assert providers["status"] == "degraded"

    monkeypatch.setattr(health, "dms_readiness_probe", lambda: _probe(False, "unavailable"))
    unavailable = health.get_module_health()
    assert unavailable.status == "unavailable"
    assert unavailable.status_code == 503


def test_health_payload_never_contains_counts_urls_credentials_or_exception_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "https://user:password@example.test/private?signature=secret"
    monkeypatch.setattr(health, "database_readiness_probe", lambda: _probe(False, "dependency_unavailable"))
    monkeypatch.setattr(health, "async_readiness_probe", lambda: _probe(True, "ready"))
    monkeypatch.setattr(health, "dms_readiness_probe", lambda: _probe(True, "ready"))
    monkeypatch.setattr(health, "provider_readiness_probe", lambda: _probe(True, "ready", status="healthy"))
    report = health.get_module_health()
    rendered = str(report.payload)
    assert secret not in rendered
    assert "password" not in rendered
    assert "row_count" not in rendered
    assert set(report.payload) == {"status", "live", "ready", "checked_at", "dependencies"}
