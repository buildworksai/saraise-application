"""Non-leaking liveness and readiness probes for the MDM domain."""

from __future__ import annotations

import logging
import uuid
from typing import Final

from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from src.core.api import SuccessEnvelopeRenderer
from src.core.observability import get_correlation_id

logger = logging.getLogger("saraise.master_data_management")

DOMAIN_TABLES: Final[tuple[str, ...]] = (
    "mdm_entity_types",
    "mdm_entities",
    "mdm_entity_versions",
    "mdm_quality_rules",
    "mdm_quality_rule_versions",
    "mdm_quality_issues",
    "mdm_matching_rules",
    "mdm_matching_rule_versions",
    "mdm_match_candidates",
    "mdm_merge_history",
    "mdm_merge_reversals",
    "mdm_merge_participants",
    "mdm_configurations",
    "mdm_configuration_versions",
)
DURABILITY_TABLES: Final[tuple[str, ...]] = ("async_jobs", "async_job_outbox_events")


def _health_correlation_id(request: object) -> str:
    """Return one correlation identifier shared by a probe's log and payload."""

    request_value = getattr(request, "correlation_id", "")
    return str(request_value or get_correlation_id() or uuid.uuid4())


@api_view(["GET"])
@permission_classes([AllowAny])
@renderer_classes([SuccessEnvelopeRenderer])
def live(request: object) -> Response:
    """Report process liveness without touching tenant data."""

    correlation_id = _health_correlation_id(request)
    logger.info(
        "MDM liveness probe succeeded",
        extra={
            "event": "mdm.health.live",
            "resource_type": "health",
            "operation": "live",
            "outcome": "succeeded",
            "correlation_id": correlation_id,
        },
    )
    return Response(
        {
            "module": "master_data_management",
            "status": "live",
            "correlation_id": correlation_id,
        }
    )


def _readiness_components() -> dict[str, dict[str, object]]:
    components: dict[str, dict[str, object]] = {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    components["database"] = {"ready": True, "code": "DATABASE_READY"}

    existing = set(connection.introspection.table_names())
    missing_domain = sorted(set(DOMAIN_TABLES) - existing)
    missing_durable = sorted(set(DURABILITY_TABLES) - existing)
    components["domain_schema"] = {
        "ready": not missing_domain,
        "code": "DOMAIN_SCHEMA_READY" if not missing_domain else "DOMAIN_SCHEMA_INCOMPLETE",
        "missing": missing_domain,
    }
    components["durable_execution"] = {
        "ready": not missing_durable,
        "code": "DURABLE_EXECUTION_READY" if not missing_durable else "DURABLE_EXECUTION_UNAVAILABLE",
        "missing": missing_durable,
    }

    if connection.vendor == "postgresql" and not missing_domain:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                WHERE relname = ANY(%s)
                """,
                [list(DOMAIN_TABLES)],
            )
            flags = {name: (enabled, forced) for name, enabled, forced in cursor.fetchall()}
        invalid = sorted(name for name in DOMAIN_TABLES if flags.get(name) != (True, True))
        components["row_level_security"] = {
            "ready": not invalid,
            "code": "RLS_ENFORCED" if not invalid else "RLS_NOT_ENFORCED",
            "tables": invalid,
        }
    else:
        # SQLite is an explicitly non-production test backend.  Reporting that
        # RLS is not applicable is truthful; it is never reported as enforced.
        components["row_level_security"] = {
            "ready": connection.vendor != "postgresql",
            "code": "RLS_NOT_APPLICABLE" if connection.vendor != "postgresql" else "RLS_SCHEMA_UNAVAILABLE",
        }
    return components


@api_view(["GET"])
@permission_classes([AllowAny])
@renderer_classes([SuccessEnvelopeRenderer])
def ready(request: object) -> Response:
    """Verify the real domain schema and durable execution dependencies."""

    correlation_id = _health_correlation_id(request)
    try:
        components = _readiness_components()
        is_ready = all(bool(component.get("ready")) for component in components.values())
    except Exception:
        logger.exception(
            "MDM readiness probe failed",
            extra={
                "event": "mdm.health.ready",
                "resource_type": "health",
                "operation": "ready",
                "outcome": "failed",
                "error_code": "READINESS_PROBE_FAILED",
                "correlation_id": correlation_id,
            },
        )
        return Response(
            {
                "module": "master_data_management",
                "status": "not_ready",
                "components": {"probe": {"ready": False, "code": "READINESS_PROBE_FAILED"}},
                "correlation_id": correlation_id,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.log(
        logging.INFO if is_ready else logging.WARNING,
        "MDM readiness probe completed",
        extra={
            "event": "mdm.health.ready",
            "resource_type": "health",
            "operation": "ready",
            "outcome": "succeeded" if is_ready else "not_ready",
            "correlation_id": correlation_id,
        },
    )
    return Response(
        {
            "module": "master_data_management",
            "status": "ready" if is_ready else "not_ready",
            "components": components,
            "correlation_id": correlation_id,
        },
        status=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


# The old name remains an import alias only; it is no longer routed as v1.
health_check = ready

__all__ = ["DOMAIN_TABLES", "DURABILITY_TABLES", "health_check", "live", "ready"]
