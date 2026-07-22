"""Sanitized readiness probes for schema, RLS, jobs, adapters, and storage."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus
from src.core.health import HealthCheckResult, health_registry

from .adapters import registry
from .services import DEFAULT_CONFIGURATION, ProcessMiningConfigurationService

DOMAIN_TABLES = (
    "process_mining_events", "process_mining_export_jobs", "process_mining_discovery_jobs",
    "process_mining_models", "process_mining_model_versions", "process_mining_conformance_checks",
    "process_mining_conformance_deviations", "process_mining_conformance_case_metrics",
    "process_mining_bottleneck_analyses", "process_mining_bottleneck_findings", "process_mining_variants",
)
GOVERNANCE_TABLES = (
    "process_mining_configurations", "process_mining_configuration_versions",
    "process_mining_configuration_audits", "process_mining_model_reference_assignments",
    "process_mining_event_retention_tombstones", "process_mining_export_artifact_deletions",
)
ASYNC_TABLES = ("async_jobs", "async_job_outbox_events", "async_job_transitions")


@dataclass(frozen=True, slots=True)
class ModuleHealthReport:
    status: str
    payload: Mapping[str, object]

    @property
    def status_code(self) -> int:
        return 503 if self.status == "unavailable" else 200


def _result(healthy: bool, message: str, code: str) -> HealthCheckResult:
    return HealthCheckResult(healthy, message, timezone.now(), {"code": code})


def database_readiness_probe() -> HealthCheckResult:
    try:
        tables = set(connection.introspection.table_names())
        protected_tables = DOMAIN_TABLES + GOVERNANCE_TABLES
        if not set(protected_tables).issubset(tables):
            return _result(False, "domain_schema_unavailable", "schema_missing")
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT tablename FROM pg_policies WHERE schemaname = current_schema() AND tablename = ANY(%s)", [list(protected_tables)])
                protected = {row[0] for row in cursor.fetchall()}
            if protected != set(protected_tables):
                return _result(False, "rls_policy_unavailable", "rls_missing")
        return _result(True, "ready", "ready")
    except Exception:
        return _result(False, "database_unavailable", "dependency_unavailable")


def async_readiness_probe(freshness_seconds: int | None = None) -> HealthCheckResult:
    try:
        if not set(ASYNC_TABLES).issubset(set(connection.introspection.table_names())):
            return _result(False, "async_schema_unavailable", "schema_missing")
        configured_seconds = int(DEFAULT_CONFIGURATION["outbox_freshness_seconds"] if freshness_seconds is None else freshness_seconds)
        stale = OutboxEvent.objects.filter(status=OutboxStatus.PENDING, created_at__lt=timezone.now() - timedelta(seconds=configured_seconds)).exists()
        return _result(not stale, "ready" if not stale else "outbox_stale", "ready" if not stale else "outbox_stale")
    except Exception:
        return _result(False, "async_unavailable", "dependency_unavailable")


def adapter_readiness_probe() -> HealthCheckResult:
    try:
        capabilities = registry.catalog()
        mining = [item for item in capabilities if "discovery" in item.capabilities]
        return _result(bool(mining), "ready" if mining else "algorithm_unavailable", "ready" if mining else "not_registered")
    except Exception:
        return _result(False, "adapter_registry_unavailable", "registry_unavailable")


def storage_readiness_probe() -> HealthCheckResult:
    key = f"process_mining/health/{uuid.uuid4()}.probe"
    try:
        stored = default_storage.save(key, ContentFile(b"process-mining-ready"))
        with default_storage.open(stored, "rb") as handle:
            ready = handle.read(64) == b"process-mining-ready"
        default_storage.delete(stored)
        return _result(ready, "ready" if ready else "roundtrip_failed", "ready" if ready else "roundtrip_failed")
    except Exception:
        return _result(False, "storage_unavailable", "dependency_unavailable")


def get_module_health(tenant_id: uuid.UUID | None = None) -> ModuleHealthReport:
    configuration = ProcessMiningConfigurationService().resolve(tenant_id) if tenant_id else DEFAULT_CONFIGURATION
    probes = {
        "database_rls": database_readiness_probe(),
        "async_outbox": async_readiness_probe(int(configuration["outbox_freshness_seconds"])),
        "algorithms": adapter_readiness_probe(),
        "export_storage": storage_readiness_probe(),
    }
    unavailable = any(not value.healthy for value in probes.values())
    status = "unavailable" if unavailable else "healthy"
    return ModuleHealthReport(status, {"status": status, "live": True, "ready": not unavailable, "checked_at": timezone.now().isoformat(), "dependencies": [{"name": name, "status": "healthy" if value.healthy else "unavailable", "code": str(value.details.get("code", "unknown")), "checked_at": value.checked_at.isoformat()} for name, value in probes.items()]})


def register_health_probes() -> None:
    health_registry.register("process_mining.database_rls", database_readiness_probe, critical=True)
    health_registry.register("process_mining.async_outbox", async_readiness_probe, critical=True)
    health_registry.register("process_mining.algorithms", adapter_readiness_probe, critical=True)
    health_registry.register("process_mining.export_storage", storage_readiness_probe, critical=True)


__all__ = ["ModuleHealthReport", "adapter_readiness_probe", "async_readiness_probe", "database_readiness_probe", "get_module_health", "register_health_probes", "storage_readiness_probe"]
