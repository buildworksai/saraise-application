"""Sanitized readiness checks for Integration Platform dependencies."""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import TypeVar
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin
from src.core.api.results import OperationResult
from src.core.async_jobs.models import OutboxEvent, OutboxStatus

from . import __version__
from .api import CanonicalSessionAuthentication, _tenant_from_request
from .models import Connector
from .permissions import HEALTH_ACTIONS
from .configuration import DEFAULT_CONFIGURATION, setting
from .services import runtime_configuration

_HEALTH_DEFAULTS = DEFAULT_CONFIGURATION["health"]
assert isinstance(_HEALTH_DEFAULTS, Mapping)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """One non-sensitive readiness result."""

    healthy: bool
    code: str
    critical: bool
    details: Mapping[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "healthy" if self.healthy else "unavailable",
            "code": self.code,
            "critical": self.critical,
            "details": dict(self.details),
        }


def _bounded_call(
    operation: Callable[[], T],
    timeout_seconds: float = float(_HEALTH_DEFAULTS["probe_timeout_seconds"]),
) -> tuple[bool, T | None]:
    """Prevent a provider health implementation from wedging readiness."""

    results: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            results.put_nowait((True, operation()))
        except Exception:
            results.put_nowait((False, None))

    worker = threading.Thread(target=invoke, name="integration-platform-health", daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        return False, None
    try:
        succeeded, value = results.get_nowait()
    except queue.Empty:
        return False, None
    return succeeded, value if succeeded else None  # type: ignore[return-value]


def database_probe() -> HealthCheck:
    """Verify the configured database accepts a bounded round trip."""

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            healthy = cursor.fetchone() == (1,)
    except Exception:
        healthy = False
    return HealthCheck(healthy, "DATABASE_READY" if healthy else "DATABASE_UNAVAILABLE", True, {})


def outbox_persistence_probe(tenant_id: UUID) -> HealthCheck:
    """Prove an outbox row can be persisted while rolling the probe back."""

    healthy = False
    try:
        with transaction.atomic():
            event = OutboxEvent.objects.create(
                tenant_id=tenant_id,
                aggregate_type="integration_platform_health_probe",
                aggregate_id=uuid.uuid4(),
                event_type="integration_platform.health.probe",
                payload={"probe": True},
            )
            healthy = event.pk is not None
            transaction.set_rollback(True)
    except Exception:
        healthy = False
    return HealthCheck(healthy, "OUTBOX_WRITABLE" if healthy else "OUTBOX_UNAVAILABLE", True, {})


def broker_acknowledgement_probe(tenant_id: UUID) -> HealthCheck:
    """Use durable dispatcher state, which changes only after broker ACK."""

    acknowledgement_seconds = int(
        setting(runtime_configuration(tenant_id), "health.broker_acknowledgement_seconds")
    )
    threshold = timezone.now() - timedelta(seconds=acknowledgement_seconds)
    try:
        overdue = OutboxEvent.objects.filter(
            tenant_id=tenant_id,
            status__in=(OutboxStatus.PENDING, OutboxStatus.DISPATCHING),
            available_at__lte=threshold,
        ).exists()
    except Exception:
        return HealthCheck(False, "BROKER_ACK_STATE_UNAVAILABLE", True, {})
    return HealthCheck(
        not overdue,
        "BROKER_ACK_CURRENT" if not overdue else "BROKER_ACK_OVERDUE",
        True,
        {"within_dispatch_slo": not overdue},
    )


def _registry_functions() -> tuple[Callable[[], Iterable[str]], Callable[[str], object]]:
    """Resolve the public adapter registry API without importing paid modules."""

    from . import adapter_registry as registry_module

    list_function = getattr(registry_module, "list_adapters", None)
    get_function = getattr(registry_module, "get_adapter", None)
    if callable(list_function) and callable(get_function):
        return list_function, get_function

    registry = getattr(registry_module, "connector_adapter_registry", None)
    if registry is None:
        registry = getattr(registry_module, "registry", None)
    if registry is None:
        raise RuntimeError("adapter registry unavailable")
    list_function = getattr(registry, "keys", None) or getattr(registry, "list_adapters", None)
    get_function = getattr(registry, "get", None) or getattr(registry, "get_adapter", None)
    if not callable(list_function) and callable(getattr(registry, "catalog", None)):

        def catalog_keys() -> tuple[str, ...]:
            return tuple(descriptor.key for descriptor in registry.catalog())

        list_function = catalog_keys
    if not callable(list_function) or not callable(get_function):
        raise RuntimeError("adapter registry contract unavailable")
    return list_function, get_function


def adapter_registry_probe() -> HealthCheck:
    """Verify every active connector has a registered adapter."""

    try:
        list_adapters, _ = _registry_functions()
        registered = {str(key) for key in list_adapters()}
        required = set(Connector.objects.filter(is_active=True).values_list("adapter_key", flat=True))
    except Exception:
        return HealthCheck(False, "ADAPTER_REGISTRY_UNAVAILABLE", False, {})
    missing = required.difference(registered)
    return HealthCheck(
        not missing,
        "ADAPTERS_REGISTERED" if not missing else "CONNECTOR_ADAPTER_UNAVAILABLE",
        False,
        {"all_active_connectors_registered": not missing},
    )


def dependency_circuit_probe() -> HealthCheck:
    """Probe registered adapter health and report only circuit availability."""

    try:
        list_adapters, get_adapter = _registry_functions()
        keys = tuple(str(key) for key in list_adapters())
    except Exception:
        return HealthCheck(False, "CIRCUIT_STATE_UNAVAILABLE", False, {})

    all_healthy = True
    any_adapter = False
    for key in keys:
        any_adapter = True
        try:
            adapter = get_adapter(key)
            completed, result = _bounded_call(adapter.health)
        except Exception:
            completed, result = False, None
        if not completed:
            all_healthy = False
            continue
        if isinstance(result, OperationResult):
            if result.status != "succeeded":
                all_healthy = False
                continue
            circuit_state = result.evidence.get("circuit_state")
        else:
            healthy = bool(getattr(result, "healthy", False))
            circuit_state = getattr(result, "circuit_state", None)
            if not healthy:
                all_healthy = False
        if circuit_state == "open":
            all_healthy = False

    # No adapters is not a healthy operational connector surface.
    healthy = any_adapter and all_healthy
    return HealthCheck(
        healthy,
        "DEPENDENCY_CIRCUITS_CLOSED" if healthy else "DEPENDENCY_CIRCUIT_UNAVAILABLE",
        False,
        {"registered_adapters_available": healthy},
    )


def module_health(tenant_id: UUID) -> tuple[dict[str, object], int]:
    """Run real tenant-safe checks without counts or raw exception text."""

    checks = {
        "database": database_probe(),
        "outbox_persistence": outbox_persistence_probe(tenant_id),
        "broker_dispatch_acknowledgement": broker_acknowledgement_probe(tenant_id),
        "adapter_registration": adapter_registry_probe(),
        "dependency_circuits": dependency_circuit_probe(),
    }
    failed = any(check.critical and not check.healthy for check in checks.values())
    degraded = any(not check.critical and not check.healthy for check in checks.values())
    overall = "unavailable" if failed else "degraded" if degraded else "healthy"
    wire_names = {
        "database": "database",
        "outbox_persistence": "outbox",
        "broker_dispatch_acknowledgement": "broker",
        "adapter_registration": "adapters",
        "dependency_circuits": "dependency_circuits",
    }
    return (
        {
            "status": overall,
            "module": "integration-platform",
            "version": __version__,
            "checked_at": timezone.now().isoformat(),
            "checks": [
                {
                    "name": wire_names[name],
                    "status": ("healthy" if check.healthy else "unavailable" if check.critical else "degraded"),
                    "detail": check.code,
                    "critical": check.critical,
                    "evidence": dict(check.details),
                }
                for name, check in checks.items()
            ],
        },
        status.HTTP_503_SERVICE_UNAVAILABLE if failed else status.HTTP_200_OK,
    )


class IntegrationPlatformHealthView(GovernedAPIViewMixin, APIView):
    """Authenticated, governed module readiness endpoint."""

    authentication_classes = (CanonicalSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_permission = HEALTH_ACTIONS["get"].permission
    required_entitlement = HEALTH_ACTIONS["get"].entitlement
    quota_resource = HEALTH_ACTIONS["get"].quota_resource
    quota_cost = HEALTH_ACTIONS["get"].quota_cost

    def perform_authentication(self, request: Request) -> None:
        super().perform_authentication(request)
        try:
            request.tenant_id = _tenant_from_request(request)  # type: ignore[attr-defined]
        except PermissionDenied:
            # RequiresAccess performs the fail-closed denial.
            return

    def get(self, request: Request) -> Response:
        payload, status_code = module_health(_tenant_from_request(request))
        return Response(payload, status=status_code)


__all__ = [
    "HealthCheck",
    "IntegrationPlatformHealthView",
    "adapter_registry_probe",
    "broker_acknowledgement_probe",
    "database_probe",
    "dependency_circuit_probe",
    "module_health",
    "outbox_persistence_probe",
]
