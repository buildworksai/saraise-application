"""Readiness/liveness contract tests."""

import json
from datetime import timedelta

import pytest
from django.test import RequestFactory
from django.urls import resolve
from django.utils import timezone

from src.core.health import HealthCheckResult, HealthRegistry, health, health_live, health_ready, health_registry


@pytest.fixture(autouse=True)
def clean_global_health_registry():
    health_registry.clear()
    yield
    health_registry.clear()


def test_zero_critical_probes_returns_503_but_liveness_is_healthy() -> None:
    request = RequestFactory().get("/health/ready/")

    readiness = health_ready(request)
    legacy = health(request)
    liveness = health_live(request)

    assert readiness.status_code == 503
    assert legacy.status_code == 503
    assert json.loads(readiness.content)["reason"] == "no critical health probes registered"
    assert liveness.status_code == 200
    assert json.loads(liveness.content) == {"status": "alive"}


def test_failed_critical_probe_returns_503_while_liveness_stays_independent() -> None:
    health_registry.register("database", lambda: (False, "database unavailable"), staleness_limit=5)
    request = RequestFactory().get("/health/ready/")

    readiness = health_ready(request)
    liveness = health_live(request)

    assert readiness.status_code == 503
    assert json.loads(readiness.content)["components"]["database"]["status"] == "unhealthy"
    assert liveness.status_code == 200


def test_root_health_routes_resolve_to_the_named_views() -> None:
    assert resolve("/health/").func is health
    assert resolve("/health/live/").func is health_live
    assert resolve("/health/ready/").func is health_ready


def test_stale_critical_probe_returns_503() -> None:
    now = timezone.now()
    registry = HealthRegistry(clock=lambda: now)
    registry.register(
        "license-server",
        lambda: HealthCheckResult(healthy=True, checked_at=now - timedelta(seconds=31)),
        staleness_limit=30,
    )

    report = registry.check_readiness()

    assert report.status_code == 503
    assert report.components["license-server"]["stale"] is True
    assert report.components["license-server"]["status"] == "unhealthy"


def test_all_fresh_critical_probes_return_ready() -> None:
    now = timezone.now()
    registry = HealthRegistry(clock=lambda: now)
    registry.register("database", lambda: True, staleness_limit=5)
    registry.register(
        "registry",
        lambda: {"healthy": True, "checked_at": now.isoformat(), "details": {"region": "primary"}},
        staleness_limit=5,
    )

    report = registry.check_readiness()

    assert report.status_code == 200
    assert report.as_dict()["status"] == "ready"
    assert report.components["registry"]["details"] == {"region": "primary"}


def test_probe_exception_is_a_failed_readiness_result() -> None:
    registry = HealthRegistry()

    @registry.register("cache", staleness_limit=5)
    def failing_probe() -> bool:
        raise ConnectionError("cache offline")

    report = registry.check_readiness()

    assert report.status_code == 503
    assert report.components["cache"]["message"] == "probe raised ConnectionError"


def test_noncritical_probe_does_not_satisfy_fail_closed_readiness() -> None:
    registry = HealthRegistry()
    registry.register("diagnostics", lambda: True, critical=False, staleness_limit=5)

    report = registry.check_readiness()

    assert report.status_code == 503
    assert report.components == {}


def test_duplicate_registration_requires_explicit_replace() -> None:
    registry = HealthRegistry()
    registry.register("database", lambda: True)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("database", lambda: False)
    registry.register("database", lambda: False, replace=True)
    assert registry.check_readiness().status_code == 503


def test_registry_lifecycle_and_probe_result_alias() -> None:
    registry = HealthRegistry()
    checked_at = timezone.now()
    result = HealthCheckResult(healthy=True, checked_at=checked_at)
    assert result.last_checked_at == checked_at

    registry.register("database", lambda: result)
    assert registry.unregister("missing") is False
    assert registry.unregister("database") is True
    registry.register("database", lambda: result)
    registry.clear()
    assert registry.check_readiness().status_code == 503


@pytest.mark.parametrize("staleness_limit", [0, -1, True, "thirty"])
def test_invalid_staleness_configuration_is_rejected(staleness_limit) -> None:
    registry = HealthRegistry()
    with pytest.raises(ValueError, match="staleness_limit"):
        registry.register("database", lambda: True, staleness_limit=staleness_limit)


def test_future_and_naive_probe_timestamps_are_handled_safely() -> None:
    now = timezone.now()
    registry = HealthRegistry(clock=lambda: now)
    registry.register(
        "future",
        lambda: HealthCheckResult(healthy=True, checked_at=now + timedelta(minutes=1)),
        staleness_limit=30,
    )
    report = registry.check_readiness()
    assert report.components["future"]["stale"] is True
    assert report.components["future"]["message"] == "probe timestamp is in the future"

    naive_registry = HealthRegistry(clock=lambda: now.replace(tzinfo=None))
    naive_registry.register("naive", lambda: True, staleness_limit=30)
    assert naive_registry.check_readiness().status_code == 200


def test_invalid_probe_contract_becomes_failed_readiness() -> None:
    registry = HealthRegistry()
    registry.register("bad-probe", lambda: None)
    report = registry.check_readiness()
    assert report.status_code == 503
    assert report.components["bad-probe"]["message"] == "probe raised TypeError"
