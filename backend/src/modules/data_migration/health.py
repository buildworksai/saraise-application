"""Non-sensitive liveness and dependency readiness for data migration."""

from __future__ import annotations

import uuid
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin
from src.core.async_jobs.models import AsyncJob, OutboxEvent, OutboxStatus

ComponentCheck = Callable[[], bool]


def _database_ready() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def _cache_ready() -> bool:
    key = f"health:data-migration:{uuid.uuid4()}"
    try:
        cache.set(key, "ready", timeout=10)
        return cache.get(key) == "ready"
    finally:
        cache.delete(key)


def _async_jobs_ready() -> bool:
    # Evaluating a bounded query proves the durable-job table is accessible;
    # the result itself is deliberately neither interpreted nor disclosed.
    list(AsyncJob.objects.order_by().values_list("id", flat=True)[:1])
    return True


def _outbox_ready() -> bool:
    threshold = int(getattr(settings, "DATA_MIGRATION_OUTBOX_BACKLOG_LIMIT", 1000))
    if threshold < 1 or threshold > 100_000:
        return False
    pending = list(
        OutboxEvent.objects.filter(status__in=(OutboxStatus.PENDING, OutboxStatus.DISPATCHING))
        .order_by()
        .values_list("id", flat=True)[: threshold + 1]
    )
    return len(pending) <= threshold


def readiness(checks: dict[str, ComponentCheck] | None = None) -> tuple[dict[str, Any], int]:
    """Run stable component checks without returning provider exception details."""

    checks = checks or {
        "database": _database_ready,
        "cache": _cache_ready,
        "async_jobs": _async_jobs_ready,
        "outbox": _outbox_ready,
    }
    components: dict[str, str] = {}
    for name, check in checks.items():
        try:
            components[name] = "READY" if check() else "DEGRADED"
        except Exception:  # Health boundaries intentionally redact dependency failures.
            components[name] = "UNAVAILABLE"
    healthy = all(value == "READY" for value in components.values())
    return {
        "status": "ready" if healthy else "not_ready",
        "module": "data_migration",
        "components": components,
    }, 200 if healthy else 503


class LivenessView(GovernedAPIViewMixin, APIView):
    """Process-only liveness; dependencies cannot make a live process appear dead."""

    authentication_classes: tuple[type, ...] = ()
    permission_classes = (AllowAny,)

    def get(self, request: Request) -> Response:
        del request
        return Response({"status": "alive", "module": "data_migration"})


class ReadinessView(GovernedAPIViewMixin, APIView):
    authentication_classes: tuple[type, ...] = ()
    permission_classes = (AllowAny,)

    def get(self, request: Request) -> Response:
        del request
        body, status_code = readiness()
        return Response(body, status=status_code)


# Deprecated compatibility symbol; v2 routes only expose separate live/ready views.
health_check = ReadinessView.as_view()


__all__ = ["LivenessView", "ReadinessView", "health_check", "readiness"]
