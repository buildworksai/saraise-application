"""Sanitized, authoritative readiness probes for disaster recovery."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TypeVar

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from src.core.health import HealthCheckResult, HealthRegistry, health_registry

from .adapter_registry import AdapterNotRegistered, get_storage_adapter, list_storage_adapters

T = TypeVar("T")

PROBE_PREFIX = "backup_disaster_recovery"


def _configured_adapter_key() -> str:
    value = getattr(settings, "BDR_STORAGE_ADAPTER_KEY", "local-filesystem")
    if not isinstance(value, str) or not value.strip():
        return ""
    return value.strip().lower()


def _positive_setting(name: str, default: float, *, maximum: float | None = None) -> float | None:
    try:
        value = float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return None
    if value <= 0 or (maximum is not None and value > maximum):
        return None
    return value


def adapter_registry_probe() -> HealthCheckResult:
    checked_at = timezone.now()
    configured = _configured_adapter_key()
    try:
        registered = list_storage_adapters()
        if not configured or configured not in registered:
            return HealthCheckResult(False, "configured storage adapter is unavailable", checked_at)
        get_storage_adapter(configured)
    except (AdapterNotRegistered, ValueError, TypeError):
        return HealthCheckResult(False, "storage adapter registry is unavailable", checked_at)
    return HealthCheckResult(True, checked_at=checked_at, details={"adapter": configured})


def _bounded_call(function: Callable[[], T], timeout_seconds: float) -> tuple[bool, T | None]:
    """Run a probe in a daemon thread so a wedged SDK cannot block readiness."""
    outcomes: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcomes.put_nowait((True, function()))
        except Exception as exc:
            outcomes.put_nowait((False, exc))

    worker = threading.Thread(target=invoke, name="bdr-provider-health", daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        return False, None
    try:
        successful, value = outcomes.get_nowait()
    except queue.Empty:
        return False, None
    return (successful, value if successful else None)  # type: ignore[return-value]


def storage_provider_probe() -> HealthCheckResult:
    checked_at = timezone.now()
    key = _configured_adapter_key()
    try:
        adapter = get_storage_adapter(key)
    except (AdapterNotRegistered, ValueError, TypeError):
        return HealthCheckResult(False, "configured storage provider is unavailable", checked_at)
    timeout = _positive_setting("BDR_HEALTH_PROBE_TIMEOUT_SECONDS", 2.0, maximum=10.0)
    if timeout is None:
        return HealthCheckResult(False, "storage provider probe timeout is misconfigured", checked_at)
    completed, raw_result = _bounded_call(adapter.health, timeout)
    if not completed or not isinstance(raw_result, HealthCheckResult):
        return HealthCheckResult(False, "storage provider probe timed out or failed", checked_at)
    maximum_age = _positive_setting("BDR_HEALTH_PROBE_STALE_SECONDS", 30.0)
    probe_checked_at = raw_result.checked_at
    if timezone.is_naive(probe_checked_at):
        probe_checked_at = timezone.make_aware(probe_checked_at)
    stale = (
        maximum_age is None
        or probe_checked_at > checked_at + timedelta(seconds=1)
        or checked_at - probe_checked_at > timedelta(seconds=maximum_age or 0)
    )
    circuit_state = raw_result.details.get("circuit_state", "unknown")
    if circuit_state not in {"closed", "open", "half_open"}:
        circuit_state = "unknown"
    details = {"adapter": key, "circuit_state": circuit_state}
    return HealthCheckResult(
        healthy=raw_result.healthy and not stale,
        message=(
            "storage provider probe result is stale"
            if stale
            else "" if raw_result.healthy else "storage provider is unavailable"
        ),
        checked_at=probe_checked_at,
        details=details,
    )


def durable_dispatch_probe() -> HealthCheckResult:
    """Check the durable outbox table and reject overdue undispatched work."""
    checked_at = timezone.now()
    maximum_lag = _positive_setting("BDR_OUTBOX_MAX_LAG_SECONDS", 60.0)
    if maximum_lag is None:
        return HealthCheckResult(False, "outbox lag threshold is misconfigured", checked_at)
    try:
        from src.core.async_jobs.models import OutboxEvent, OutboxStatus

        oldest = (
            OutboxEvent.objects.filter(
                status__in=(OutboxStatus.PENDING, OutboxStatus.DISPATCHING),
                available_at__lte=checked_at,
            )
            .order_by("available_at")
            .values_list("available_at", flat=True)
            .first()
        )
    except Exception:
        return HealthCheckResult(False, "durable job dispatch state is unavailable", checked_at)
    lag = 0.0 if oldest is None else max(0.0, (checked_at - oldest).total_seconds())
    healthy = lag <= maximum_lag
    return HealthCheckResult(
        healthy,
        "" if healthy else "durable job dispatch is outside its lag threshold",
        checked_at,
        details={"lag_within_threshold": healthy},
    )


def circuit_state_probe() -> HealthCheckResult:
    checked_at = timezone.now()
    key = _configured_adapter_key()
    try:
        adapter = get_storage_adapter(key)
    except (AdapterNotRegistered, ValueError, TypeError):
        return HealthCheckResult(False, "configured storage provider is unavailable", checked_at)
    state = getattr(adapter, "circuit_state", "unknown")
    healthy = state != "open"
    return HealthCheckResult(
        healthy,
        "" if healthy else "storage provider circuit is open",
        checked_at,
        details={"adapter": key, "circuit_state": state},
    )


def exercise_freshness_probe() -> HealthCheckResult:
    """Consume a tenant-safe aggregate supplied by the scheduled readiness job."""
    checked_at = timezone.now()
    observed = getattr(settings, "BDR_EXERCISE_FRESHNESS_CHECKED_AT", None)
    maximum_age = _positive_setting("BDR_EXERCISE_FRESHNESS_MAX_AGE_SECONDS", 86400.0)
    if not isinstance(observed, datetime) or maximum_age is None:
        return HealthCheckResult(False, "exercise freshness aggregate is unavailable", checked_at)
    if timezone.is_naive(observed):
        observed = timezone.make_aware(observed)
    fresh = checked_at - observed <= timedelta(seconds=maximum_age)
    return HealthCheckResult(
        fresh,
        "" if fresh else "exercise freshness aggregate is stale",
        observed,
    )


def register_health_probes(registry: HealthRegistry = health_registry) -> None:
    """Register module probes without replacement."""
    registry.register(f"{PROBE_PREFIX}.adapter_registry", adapter_registry_probe, critical=True, staleness_limit=30)
    registry.register(f"{PROBE_PREFIX}.storage_provider", storage_provider_probe, critical=True, staleness_limit=30)
    registry.register(f"{PROBE_PREFIX}.durable_dispatch", durable_dispatch_probe, critical=True, staleness_limit=30)
    registry.register(f"{PROBE_PREFIX}.circuit_state", circuit_state_probe, critical=False, staleness_limit=30)
    registry.register(
        f"{PROBE_PREFIX}.exercise_freshness",
        exercise_freshness_probe,
        critical=False,
        staleness_limit=86400,
    )


def module_readiness() -> tuple[dict[str, object], int]:
    """Return module-local readiness without exposing raw exceptions or counts."""
    checks: dict[str, HealthCheckResult] = {
        "adapter_registry": adapter_registry_probe(),
        "storage_provider": storage_provider_probe(),
        "durable_dispatch": durable_dispatch_probe(),
        "circuit_state": circuit_state_probe(),
        "exercise_freshness": exercise_freshness_probe(),
    }
    critical = ("adapter_registry", "storage_provider", "durable_dispatch")
    ready = all(checks[name].healthy for name in critical)
    payload: dict[str, object] = {
        "status": "ready" if ready else "not_ready",
        "module": "backup-disaster-recovery",
        "checks": {
            name: {
                "status": "healthy" if result.healthy else "unhealthy",
                "message": result.message,
                "checked_at": result.checked_at.isoformat(),
                "details": dict(result.details),
            }
            for name, result in checks.items()
        },
    }
    return payload, 200 if ready else 503


@require_GET
def health_check(request: HttpRequest) -> JsonResponse:
    del request
    payload, status_code = module_readiness()
    return JsonResponse(payload, status=status_code)


__all__ = [
    "adapter_registry_probe",
    "circuit_state_probe",
    "durable_dispatch_probe",
    "exercise_freshness_probe",
    "health_check",
    "module_readiness",
    "register_health_probes",
    "storage_provider_probe",
]
