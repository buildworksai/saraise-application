"""Sanitized liveness and tenant-specific readiness for notifications."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.auth_utils import get_user_tenant_id
from src.core.tenancy import get_current_tenant_id, tenant_context

from .adapters import AdapterNotRegistered, adapter_registry
from .tasks import COMMANDS, register_async_handlers

MODULE_NAME: Final[str] = "notifications"


@dataclass(frozen=True, slots=True)
class ComponentStatus:
    healthy: bool
    code: str
    status: str = "ready"
    details: Mapping[str, object] | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status if self.healthy else "unavailable",
            "code": self.code,
        }
        if self.details:
            payload["details"] = dict(self.details)
        return payload


def liveness() -> dict[str, object]:
    """Prove only that the Django process can execute Python."""

    return {"module": MODULE_NAME, "status": "live", "live": True, "checked_at": timezone.now().isoformat()}


def _database_status(tenant_id: UUID) -> ComponentStatus:
    try:
        with tenant_context(tenant_id):
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
                if row != (1,):
                    return ComponentStatus(False, "database_probe_invalid")
                if connection.vendor == "postgresql":
                    cursor.execute("SELECT current_setting('app.tenant_id', true)")
                    context_row = cursor.fetchone()
                    if not context_row or context_row[0] != str(tenant_id):
                        return ComponentStatus(False, "rls_context_unavailable")
        return ComponentStatus(
            True,
            "ready",
            details={"rls_context": "verified" if connection.vendor == "postgresql" else "not_applicable"},
        )
    except Exception:
        return ComponentStatus(False, "database_unavailable")


def _outbox_status(tenant_id: UUID) -> ComponentStatus:
    try:
        pending = OutboxEvent.objects.for_tenant(tenant_id).filter(status=OutboxStatus.PENDING)
        oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
        age = max(0, int((timezone.now() - oldest).total_seconds())) if oldest else 0
        return ComponentStatus(
            True,
            "ready",
            details={"pending": pending.count(), "oldest_age_seconds": age},
        )
    except Exception:
        return ComponentStatus(False, "outbox_unavailable")


def _handlers_status() -> ComponentStatus:
    try:
        register_async_handlers()
        from src.core.async_jobs.services import get_handler

        for command in COMMANDS:
            get_handler(command)
        return ComponentStatus(True, "ready", details={"registered": len(COMMANDS)})
    except Exception:
        return ComponentStatus(False, "handlers_unavailable")


def _configuration(tenant_id: UUID) -> tuple[ComponentStatus, Mapping[str, object] | None]:
    try:
        model = apps.get_model("notifications", "NotificationConfiguration")
        environment = str(getattr(settings, "SARAISE_ENVIRONMENT", "development")).strip().lower()
        configuration = model.objects.for_tenant(tenant_id).filter(environment=environment).first()
        if configuration is None or not isinstance(configuration.document, Mapping):
            return ComponentStatus(False, "configuration_missing"), None
        document = dict(configuration.document)
        from .services import NotificationConfigurationService

        errors = NotificationConfigurationService.validate_document(tenant_id, document)
        if errors:
            return ComponentStatus(
                False,
                "configuration_invalid",
                details={"validation_error_count": len(errors)},
            ), None
        return ComponentStatus(
            True,
            "ready",
            details={"environment": environment, "active_version": configuration.active_version},
        ), document
    except Exception:
        return ComponentStatus(False, "configuration_unavailable"), None


def _adapter_statuses(
    tenant_id: UUID,
    document: Mapping[str, object] | None,
) -> tuple[ComponentStatus, dict[str, object]]:
    if document is None:
        return ComponentStatus(False, "configuration_missing"), {}
    channels = document.get("channels")
    if not isinstance(channels, Mapping) or not channels:
        return ComponentStatus(False, "channel_configuration_missing"), {}
    output: dict[str, object] = {}
    healthy = True
    for channel in sorted(channels):
        raw = channels[channel]
        if not isinstance(channel, str) or not isinstance(raw, Mapping):
            healthy = False
            output[str(channel)] = {"status": "unavailable", "code": "channel_configuration_invalid"}
            continue
        enabled = raw.get("enabled")
        if not isinstance(enabled, bool):
            healthy = False
            output[channel] = {"status": "unavailable", "code": "channel_configuration_invalid"}
            continue
        if enabled is False:
            output[channel] = {"status": "disabled", "code": "disabled"}
            continue
        key = raw.get("adapter_key")
        if not isinstance(key, str) or not key.strip():
            healthy = False
            output[channel] = {"status": "unavailable", "code": "adapter_key_missing"}
            continue
        try:
            adapter = adapter_registry.get(key)
            if adapter.channel != channel:
                raise ValueError("adapter channel mismatch")
            result = adapter.health(tenant_id, raw)
            output[channel] = result.__dict__ if hasattr(result, "__dict__") else {
                "status": result.status,
                "code": result.code,
                "details": dict(result.details),
            }
            healthy = healthy and result.healthy
        except AdapterNotRegistered:
            healthy = False
            output[channel] = {"status": "unavailable", "code": "adapter_unavailable"}
        except Exception:
            healthy = False
            output[channel] = {"status": "unavailable", "code": "adapter_health_failed"}
    return ComponentStatus(healthy, "ready" if healthy else "required_adapter_unavailable"), output


def readiness(tenant_id: UUID | str | None) -> tuple[dict[str, object], int]:
    """Check critical dependencies without exposing exceptions or tenant data."""

    try:
        canonical_tenant = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    except (TypeError, ValueError, AttributeError):
        payload = {
            "module": MODULE_NAME,
            "status": "not_ready",
            "ready": False,
            "code": "tenant_context_missing",
            "components": {},
        }
        return payload, 503

    with tenant_context(canonical_tenant):
        database = _database_status(canonical_tenant)
        outbox = _outbox_status(canonical_tenant)
        handlers = _handlers_status()
        configuration, document = _configuration(canonical_tenant)
        adapters, adapter_details = _adapter_statuses(canonical_tenant, document)
    ready = all(component.healthy for component in (database, outbox, handlers, configuration, adapters))
    components = {
        "database": database.as_dict(),
        "outbox": outbox.as_dict(),
        "handlers": handlers.as_dict(),
        "configuration": configuration.as_dict(),
        "adapters": {
            **adapters.as_dict(),
            "details": adapter_details,
        },
    }
    payload = {
        "module": MODULE_NAME,
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "code": "ready" if ready else "dependency_unavailable",
        "components": components,
        "queue_backlog": int((outbox.details or {}).get("pending", 0)),
        "oldest_queued_age_seconds": int((outbox.details or {}).get("oldest_age_seconds", 0)),
    }
    try:
        delivery_model = apps.get_model("notifications", "NotificationDelivery")
        last_success = delivery_model.objects.for_tenant(canonical_tenant).filter(status__in=("sent", "delivered")).order_by("-sent_at").values_list("sent_at", flat=True).first()
        payload["last_successful_delivery_at"] = last_success.isoformat() if last_success else None
    except Exception:
        payload["last_successful_delivery_at"] = None
    return payload, 200 if ready else 503


def _request_tenant(request: object) -> UUID | None:
    direct = getattr(request, "tenant_id", None) or get_current_tenant_id()
    if direct is None:
        direct = get_user_tenant_id(getattr(request, "user", None))
    try:
        return direct if isinstance(direct, UUID) else UUID(str(direct))
    except (TypeError, ValueError, AttributeError):
        return None


def liveness_check(request: object) -> JsonResponse:
    del request
    return JsonResponse(liveness(), status=200)


def readiness_check(request: object) -> JsonResponse:
    payload, status = readiness(_request_tenant(request))
    return JsonResponse(payload, status=status)


# Compatibility for the old module URL while the canonical API exposes the
# explicit /health/live/ and /health/ready/ paths.
health_check = readiness_check


__all__ = [
    "ComponentStatus",
    "health_check",
    "liveness",
    "liveness_check",
    "readiness",
    "readiness_check",
]
