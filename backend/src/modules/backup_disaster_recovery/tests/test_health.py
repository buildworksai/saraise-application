from __future__ import annotations

import time
from datetime import timedelta
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.health import HealthCheckResult, HealthRegistry
from src.modules.backup_disaster_recovery.adapter_registry import (
    register_storage_adapter,
    unregister_storage_adapter,
)
from src.modules.backup_disaster_recovery.health import (
    adapter_registry_probe,
    circuit_state_probe,
    durable_dispatch_probe,
    module_readiness,
    register_health_probes,
    storage_provider_probe,
)


class _Adapter:
    def __init__(self, result=None, *, delay=0.0):
        self.result = result or HealthCheckResult(True)
        self.delay = delay
        self.circuit_state = "closed"

    def health(self):
        time.sleep(self.delay)
        return self.result

    def validate_artifact(self, *args, **kwargs):
        raise NotImplementedError

    def restore(self, *args, **kwargs):
        raise NotImplementedError

    def verify_restore(self, *args, **kwargs):
        raise NotImplementedError


def _register(adapter):
    key = f"health-{uuid4()}"
    register_storage_adapter(key, adapter)
    return key


def test_missing_configured_adapter_fails_closed() -> None:
    with override_settings(BDR_STORAGE_ADAPTER_KEY=f"missing-{uuid4()}"):
        assert adapter_registry_probe().healthy is False
        assert storage_provider_probe().healthy is False


def test_provider_probe_is_healthy_and_sanitizes_details() -> None:
    adapter = _Adapter(
        HealthCheckResult(
            True,
            details={"adapter": "safe", "circuit_state": "closed", "credential": "do-not-expose"},
        )
    )
    key = _register(adapter)
    try:
        with override_settings(BDR_STORAGE_ADAPTER_KEY=key):
            result = storage_provider_probe()
        assert result.healthy is True
        assert result.details == {"adapter": key, "circuit_state": "closed"}
    finally:
        unregister_storage_adapter(key)


def test_provider_timeout_and_stale_result_fail_closed() -> None:
    timeout_key = _register(_Adapter(delay=0.05))
    stale_key = _register(_Adapter(HealthCheckResult(True, checked_at=timezone.now() - timedelta(minutes=5))))
    try:
        with override_settings(BDR_STORAGE_ADAPTER_KEY=timeout_key, BDR_HEALTH_PROBE_TIMEOUT_SECONDS=0.001):
            timeout = storage_provider_probe()
        assert timeout.healthy is False
        assert "timed out" in timeout.message

        with override_settings(BDR_STORAGE_ADAPTER_KEY=stale_key, BDR_HEALTH_PROBE_STALE_SECONDS=30):
            stale = storage_provider_probe()
        assert stale.healthy is False
        assert "stale" in stale.message
    finally:
        unregister_storage_adapter(timeout_key)
        unregister_storage_adapter(stale_key)


def test_open_circuit_is_explicitly_unhealthy() -> None:
    adapter = _Adapter()
    adapter.circuit_state = "open"
    key = _register(adapter)
    try:
        with override_settings(BDR_STORAGE_ADAPTER_KEY=key):
            result = circuit_state_probe()
        assert result.healthy is False
        assert result.details == {"adapter": key, "circuit_state": "open"}
    finally:
        unregister_storage_adapter(key)


@pytest.mark.django_db
def test_durable_dispatch_probe_detects_queue_lag() -> None:
    job = enqueue(uuid4(), uuid4(), "test.health.command", {}, f"health-{uuid4()}")
    OutboxEvent.objects.filter(aggregate_id=job.id).update(available_at=timezone.now() - timedelta(minutes=10))
    with override_settings(BDR_OUTBOX_MAX_LAG_SECONDS=30):
        result = durable_dispatch_probe()
    assert result.healthy is False
    assert result.details == {"lag_within_threshold": False}


def test_health_registry_registration_is_duplicate_safe() -> None:
    registry = HealthRegistry()
    register_health_probes(registry)
    with pytest.raises(ValueError, match="already registered"):
        register_health_probes(registry)


def test_module_readiness_returns_503_for_critical_provider_failure(monkeypatch) -> None:
    healthy = HealthCheckResult(True)
    monkeypatch.setattr(
        "src.modules.backup_disaster_recovery.health.adapter_registry_probe",
        lambda: healthy,
    )
    monkeypatch.setattr(
        "src.modules.backup_disaster_recovery.health.storage_provider_probe",
        lambda: HealthCheckResult(False, "provider unavailable"),
    )
    monkeypatch.setattr(
        "src.modules.backup_disaster_recovery.health.durable_dispatch_probe",
        lambda: healthy,
    )
    monkeypatch.setattr("src.modules.backup_disaster_recovery.health.circuit_state_probe", lambda: healthy)
    monkeypatch.setattr("src.modules.backup_disaster_recovery.health.exercise_freshness_probe", lambda: healthy)

    payload, status = module_readiness()
    assert status == 503
    assert payload["status"] == "not_ready"
    assert "exception" not in str(payload).lower()
