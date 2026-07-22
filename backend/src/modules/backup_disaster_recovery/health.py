"""Sanitized, authoritative readiness probes for disaster recovery."""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import TypeVar
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.health import HealthCheckResult, HealthRegistry, health_registry

from .adapter_registry import (
    AdapterNotRegistered,
    execute_provider_call,
    get_storage_adapter,
    list_storage_adapters,
    provider_circuit_state,
)
from .permissions import HEALTH_READ

T = TypeVar("T")

PROBE_PREFIX = "backup_disaster_recovery"


class ModuleReadinessCheckSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.ChoiceField(choices=("healthy", "unhealthy"))
    message = serializers.CharField(allow_blank=True)
    checked_at = serializers.DateTimeField()
    details = serializers.DictField(child=serializers.JSONField())


class ModuleReadinessResponseSerializer(serializers.Serializer[dict[str, object]]):
    status = serializers.ChoiceField(choices=("ready", "not_ready"))
    module = serializers.CharField()
    checks = serializers.DictField(child=ModuleReadinessCheckSerializer())


def _configuration_document(tenant_id: UUID | None) -> Mapping[str, object]:
    from .services import DEFAULT_CONFIGURATION_DOCUMENT, get_configuration

    return get_configuration(tenant_id).document if tenant_id is not None else DEFAULT_CONFIGURATION_DOCUMENT


def _section(tenant_id: UUID | None, key: str) -> Mapping[str, object]:
    value = _configuration_document(tenant_id).get(key)
    if not isinstance(value, Mapping):
        return {}
    return value


def _configured_adapter_key(tenant_id: UUID | None = None) -> str:
    providers = _section(tenant_id, "providers")
    value = providers.get("storage_adapter_key")
    if tenant_id is None and hasattr(settings, "BDR_STORAGE_ADAPTER_KEY"):
        value = getattr(settings, "BDR_STORAGE_ADAPTER_KEY")
    if not isinstance(value, str) or not value.strip():
        return ""
    return value.strip().lower()


def _positive_health_value(
    tenant_id: UUID | None,
    key: str,
    *,
    legacy_setting: str | None = None,
    maximum_key: str | None = None,
) -> float | None:
    health = _section(tenant_id, "health")
    value = health.get(key)
    if tenant_id is None and legacy_setting and hasattr(settings, legacy_setting):
        value = getattr(settings, legacy_setting)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    maximum = health.get(maximum_key) if maximum_key else None
    if parsed <= 0 or (maximum is not None and isinstance(maximum, (int, float)) and parsed > float(maximum)):
        return None
    return parsed


def adapter_registry_probe(tenant_id: UUID | None = None) -> HealthCheckResult:
    checked_at = timezone.now()
    configured = _configured_adapter_key(tenant_id)
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


def storage_provider_probe(tenant_id: UUID | None = None) -> HealthCheckResult:
    checked_at = timezone.now()
    key = _configured_adapter_key(tenant_id)
    try:
        adapter = get_storage_adapter(key)
    except (AdapterNotRegistered, ValueError, TypeError):
        return HealthCheckResult(False, "configured storage provider is unavailable", checked_at)
    timeout = _positive_health_value(
        tenant_id,
        "probe_timeout_seconds",
        legacy_setting="BDR_HEALTH_PROBE_TIMEOUT_SECONDS",
        maximum_key="probe_timeout_max_seconds",
    )
    if timeout is None:
        return HealthCheckResult(False, "storage provider probe timeout is misconfigured", checked_at)
    completed, raw_result = _bounded_call(
        lambda: execute_provider_call(
            tenant_id,
            f"storage-adapter.{key}.health",
            adapter.health,
        ),
        timeout,
    )
    if not completed or not isinstance(raw_result, HealthCheckResult):
        return HealthCheckResult(False, "storage provider probe timed out or failed", checked_at)
    maximum_age = _positive_health_value(
        tenant_id,
        "provider_stale_seconds",
        legacy_setting="BDR_HEALTH_PROBE_STALE_SECONDS",
    )
    probe_checked_at = raw_result.checked_at
    if timezone.is_naive(probe_checked_at):
        probe_checked_at = timezone.make_aware(probe_checked_at)
    evaluated_at = timezone.now()
    stale = (
        maximum_age is None
        or probe_checked_at > evaluated_at
        or evaluated_at - probe_checked_at > timedelta(seconds=maximum_age or 0)
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


def durable_dispatch_probe(tenant_id: UUID | None = None) -> HealthCheckResult:
    """Check the durable outbox table and reject overdue undispatched work."""
    checked_at = timezone.now()
    maximum_lag = _positive_health_value(
        tenant_id,
        "outbox_max_lag_seconds",
        legacy_setting="BDR_OUTBOX_MAX_LAG_SECONDS",
    )
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


def circuit_state_probe(tenant_id: UUID | None = None) -> HealthCheckResult:
    checked_at = timezone.now()
    key = _configured_adapter_key(tenant_id)
    try:
        adapter = get_storage_adapter(key)
    except (AdapterNotRegistered, ValueError, TypeError):
        return HealthCheckResult(False, "configured storage provider is unavailable", checked_at)
    adapter_state = getattr(adapter, "circuit_state", None)
    try:
        state = (
            adapter_state
            if adapter_state == "open"
            else provider_circuit_state(tenant_id, f"storage-adapter.{key}.health")
        )
    except (TypeError, ValueError):
        state = "unknown"
    healthy = state != "open"
    return HealthCheckResult(
        healthy,
        "" if healthy else "storage provider circuit is open",
        checked_at,
        details={"adapter": key, "circuit_state": state},
    )


def exercise_freshness_probe(tenant_id: UUID | None = None) -> HealthCheckResult:
    """Consume a tenant-safe aggregate supplied by the scheduled readiness job."""
    checked_at = timezone.now()
    observed = getattr(settings, "BDR_EXERCISE_FRESHNESS_CHECKED_AT", None)
    maximum_age = _positive_health_value(
        tenant_id,
        "exercise_freshness_seconds",
        legacy_setting="BDR_EXERCISE_FRESHNESS_MAX_AGE_SECONDS",
    )
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
    registry_limit = _positive_health_value(None, "registry_staleness_seconds")
    exercise_limit = _positive_health_value(None, "exercise_registry_staleness_seconds")
    if registry_limit is None or exercise_limit is None:
        raise ValueError("health probe registry staleness configuration is unavailable")
    registry.register(
        f"{PROBE_PREFIX}.adapter_registry",
        adapter_registry_probe,
        critical=True,
        staleness_limit=registry_limit,
    )
    registry.register(
        f"{PROBE_PREFIX}.storage_provider",
        storage_provider_probe,
        critical=True,
        staleness_limit=registry_limit,
    )
    registry.register(
        f"{PROBE_PREFIX}.durable_dispatch",
        durable_dispatch_probe,
        critical=True,
        staleness_limit=registry_limit,
    )
    registry.register(
        f"{PROBE_PREFIX}.circuit_state",
        circuit_state_probe,
        critical=False,
        staleness_limit=registry_limit,
    )
    registry.register(
        f"{PROBE_PREFIX}.exercise_freshness",
        exercise_freshness_probe,
        critical=False,
        staleness_limit=exercise_limit,
    )


def module_readiness(tenant_id: UUID | None = None) -> tuple[dict[str, object], int]:
    """Return module-local readiness without exposing raw exceptions or counts."""

    def invoke(probe: Callable[..., HealthCheckResult]) -> HealthCheckResult:
        return probe() if tenant_id is None else probe(tenant_id)

    checks: dict[str, HealthCheckResult] = {
        "adapter_registry": invoke(adapter_registry_probe),
        "storage_provider": invoke(storage_provider_probe),
        "durable_dispatch": invoke(durable_dispatch_probe),
        "circuit_state": invoke(circuit_state_probe),
        "exercise_freshness": invoke(exercise_freshness_probe),
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


class BDRHealthView(GovernedAPIViewMixin, APIView):  # type: ignore[misc]
    """Authenticated, tenant-scoped readiness with explicit access policy."""

    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = HEALTH_READ.permission
    required_entitlement = HEALTH_READ.entitlement
    quota_resource = HEALTH_READ.quota_resource

    def perform_authentication(self, request: Request) -> None:
        super().perform_authentication(request)
        user = getattr(request, "user", None)
        if user is None or not bool(getattr(user, "is_authenticated", False)):
            return
        try:
            raw_tenant_id = getattr(user.profile, "tenant_id", None)
        except (AttributeError, ObjectDoesNotExist):
            return
        try:
            if raw_tenant_id:
                tenant_id = raw_tenant_id if isinstance(raw_tenant_id, UUID) else UUID(str(raw_tenant_id))
                request.tenant_id = tenant_id  # type: ignore[attr-defined]
                self.quota_cost = HEALTH_READ.quota_cost_for(tenant_id)
        except (AttributeError, TypeError, ValueError):
            return

    def get(self, request: Request) -> Response:
        tenant_id = getattr(request, "tenant_id", None)
        if not isinstance(tenant_id, UUID):
            return Response(
                {"status": "not_ready", "module": "backup-disaster-recovery"},
                status=503,
            )
        payload, status_code = module_readiness(tenant_id)
        serializer = ModuleReadinessResponseSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status_code)


health_check = BDRHealthView.as_view()


__all__ = [
    "adapter_registry_probe",
    "BDRHealthView",
    "circuit_state_probe",
    "durable_dispatch_probe",
    "exercise_freshness_probe",
    "health_check",
    "module_readiness",
    "ModuleReadinessCheckSerializer",
    "ModuleReadinessResponseSerializer",
    "register_health_probes",
    "storage_provider_probe",
]
