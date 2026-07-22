"""Transactional business services for process mining.

Controllers only validate transport data and delegate here.  Every public
method accepts the authoritative tenant UUID first and every lookup uses the
canonical ``for_tenant`` queryset boundary.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import uuid
from copy import deepcopy
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from django.core.files import File
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max, Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from src.core.api.results import CapabilityUnavailable, OperationFailed
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.middleware.correlation import get_correlation_id

from .adapters import (
    BottleneckAlgorithm,
    CanonicalEvent,
    ConformanceAlgorithm,
    ExportFormatter,
    MiningAlgorithm,
    canonical_events,
    registry,
)
from .models import (
    AnalysisStatus,
    BottleneckAnalysis,
    BottleneckFinding,
    ConformanceCaseMetric,
    ConformanceCheck,
    ConformanceDeviation,
    EventExportJob,
    ExportArtifactDeletion,
    ExportFormat,
    ExportStatus,
    MiningAlgorithmName,
    ModelSourceKind,
    ProcessDiscoveryJob,
    ProcessEvent,
    ProcessEventRetentionTombstone,
    ProcessMiningConfiguration,
    ProcessMiningConfigurationAudit,
    ProcessMiningConfigurationVersion,
    ProcessModel,
    ProcessModelReferenceAssignment,
    ProcessModelVersion,
    ProcessVariant,
    validate_graph,
)
from .state_machines import configured_state_machine

logger = logging.getLogger("saraise.process_mining")

# These are persisted as each tenant's versioned starting document. Runtime
# behavior always reads the tenant record; editing source is never required.
DEFAULT_CONFIGURATION: dict[str, object] = {
    "environment": "default",
    "max_batch_events": 10_000,
    "max_export_events": 1_000_000,
    "max_export_bytes": 524_288_000,
    "max_conformance_events": 100_000,
    "text_max_length": 255,
    "attributes_max_bytes": 65_536,
    "forbidden_attribute_keys": ["password", "secret", "token", "authorization", "api_key", "credential"],
    "source_module_max_length": 100,
    "max_event_age_days": 730,
    "future_clock_skew_seconds": -120,
    "bulk_insert_batch_size": 1_000,
    "event_query_max_days": 366,
    "retention_days": 365,
    "retention_min_days": 30,
    "export_projection_bytes_per_event": 512,
    "export_iterator_chunk_size": 1_000,
    "checksum_chunk_bytes": 1_048_576,
    "export_expiry_days": 7,
    "discovery_min_events": 100,
    "discovery_min_cases": 10,
    "alpha_max_activities": 50,
    "heuristic_default_threshold": 0.8,
    "inductive_default_threshold": 0.2,
    "default_discovery_algorithm": "inductive_miner",
    "algorithm_threshold_step": 0.01,
    "algorithm_threshold_min": 0.0,
    "algorithm_threshold_max": 1.0,
    "low_fitness_threshold": 0.5,
    "bottleneck_reuse_minutes": 60,
    "bottleneck_min_cases": 50,
    "bottleneck_critical_ratio": 10.0,
    "bottleneck_high_ratio": 5.0,
    "bottleneck_medium_ratio": 2.0,
    "tail_duration_percentile": 0.95,
    "resource_concentration_threshold": 0.5,
    "variant_grouping_percentage": 1.0,
    "outbox_freshness_seconds": 300,
    "analysis_transitions": {
        "queued": ["running", "cancelled"], "running": ["completed", "failed", "timed_out", "cancelled"],
        "failed": ["queued"], "timed_out": ["queued"], "completed": [], "cancelled": [],
    },
    "analysis_terminal_states": ["completed", "cancelled"],
    "export_transitions": {
        "queued": ["running", "cancelled"], "running": ["completed", "failed", "timed_out", "cancelled"],
        "failed": ["queued"], "timed_out": ["queued"], "completed": ["expired"], "expired": [], "cancelled": [],
    },
    "export_terminal_states": ["cancelled", "expired"],
    "default_time_window_days": 30,
    "list_page_size": 25,
    "detail_page_size": 100,
    "polling_interval_ms": 5_000,
    "visual_zoom_min": 0.6,
    "visual_zoom_max": 1.8,
    "visual_zoom_step": 0.2,
    "visual_edge_width_min": 1.0,
    "visual_edge_width_max": 8.0,
    "visual_frequency_divisor": 10.0,
    "visual_duration_divisor": 60.0,
    "visual_canvas_width": 900,
    "visual_canvas_height": 600,
    "visual_node_width": 110,
    "visual_node_height": 50,
    "visual_layout_columns": 4,
    "visual_horizontal_gap": 210,
    "visual_vertical_gap": 150,
    "visual_layout_padding": 90,
    "download_timeout_ms": 30_000,
    "download_retry_attempts": 3,
    "download_retry_base_ms": 250,
    "download_circuit_failure_threshold": 5,
    "download_circuit_reset_ms": 30_000,
    "enabled": True,
    "rollout_roles": [],
    "rollout_cohorts": [],
}

INTEGER_LIMITS = {
    "max_batch_events": (1, 100_000), "max_export_events": (1, 10_000_000),
    "max_export_bytes": (1_048_576, 5_368_709_120), "max_conformance_events": (1, 1_000_000),
    "text_max_length": (32, 4_096), "attributes_max_bytes": (1_024, 1_048_576),
    "source_module_max_length": (16, 512), "max_event_age_days": (1, 3_650),
    "future_clock_skew_seconds": (-3_600, 86_400), "bulk_insert_batch_size": (1, 10_000),
    "event_query_max_days": (1, 3_650), "retention_days": (1, 3_650), "retention_min_days": (1, 365),
    "export_projection_bytes_per_event": (1, 65_536), "export_iterator_chunk_size": (1, 10_000),
    "checksum_chunk_bytes": (4_096, 16_777_216), "export_expiry_days": (1, 365),
    "discovery_min_events": (1, 1_000_000), "discovery_min_cases": (1, 100_000),
    "alpha_max_activities": (2, 10_000), "bottleneck_reuse_minutes": (0, 10_080),
    "bottleneck_min_cases": (1, 100_000), "outbox_freshness_seconds": (1, 86_400),
    "default_time_window_days": (1, 3_650), "list_page_size": (1, 100), "detail_page_size": (1, 100),
    "polling_interval_ms": (1_000, 300_000), "download_timeout_ms": (1_000, 300_000),
    "visual_canvas_width": (320, 10_000), "visual_canvas_height": (240, 10_000),
    "visual_node_width": (20, 1_000), "visual_node_height": (20, 1_000), "visual_layout_columns": (1, 100),
    "visual_horizontal_gap": (20, 2_000), "visual_vertical_gap": (20, 2_000), "visual_layout_padding": (0, 1_000),
    "download_retry_attempts": (0, 10), "download_retry_base_ms": (10, 60_000),
    "download_circuit_failure_threshold": (1, 100), "download_circuit_reset_ms": (1_000, 600_000),
}
FLOAT_LIMITS = {
    "heuristic_default_threshold": (0.0, 1.0), "inductive_default_threshold": (0.0, 1.0),
    "algorithm_threshold_step": (0.0001, 1.0),
    "algorithm_threshold_min": (0.0, 1.0), "algorithm_threshold_max": (0.0, 1.0),
    "low_fitness_threshold": (0.0, 1.0), "bottleneck_critical_ratio": (1.0, 1000.0),
    "bottleneck_high_ratio": (1.0, 1000.0), "bottleneck_medium_ratio": (1.0, 1000.0),
    "tail_duration_percentile": (0.5, 0.9999), "resource_concentration_threshold": (0.0, 1.0),
    "variant_grouping_percentage": (0.0, 100.0), "visual_zoom_min": (0.1, 10.0),
    "visual_zoom_max": (0.1, 10.0), "visual_zoom_step": (0.01, 2.0),
    "visual_edge_width_min": (0.1, 100.0), "visual_edge_width_max": (0.1, 100.0),
    "visual_frequency_divisor": (0.01, 1_000_000.0), "visual_duration_divisor": (0.01, 1_000_000.0),
}


@dataclass(frozen=True, slots=True)
class IngestRowEvidence:
    index: int
    status: str
    event_id: UUID | None = None
    code: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class IngestResult:
    accepted: int
    rejected: int
    duplicates: int
    rows: tuple[IngestRowEvidence, ...]


def _tenant(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"tenant_id": "A valid tenant UUID is required."}) from exc


def _actor(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"actor_id": "A valid actor UUID is required."}) from exc


def _correlation_id(value: str | None = None) -> str:
    correlation_id = value or get_correlation_id()
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        # This marker is deliberately stable and visible; it never invents an
        # unrelated trace identifier when middleware context is absent.
        return "missing-context"
    if len(correlation_id) > 128:
        raise ValidationError({"correlation_id": "Must not exceed 128 characters."})
    return correlation_id.strip()


class ProcessMiningConfigurationService:
    """Validate, version, audit, preview, import/export, and roll back tenant policy."""

    @staticmethod
    def validate_document(document: object) -> dict[str, object]:
        if not isinstance(document, dict):
            raise ValidationError({"document": "Configuration must be an object."})
        missing = set(DEFAULT_CONFIGURATION) - set(document)
        unknown = set(document) - set(DEFAULT_CONFIGURATION)
        if missing or unknown:
            detail: dict[str, object] = {}
            if missing:
                detail["missing"] = sorted(missing)
            if unknown:
                detail["unknown"] = sorted(unknown)
            raise ValidationError({"document": detail})
        normalized = deepcopy(document)
        for field, (minimum, maximum) in INTEGER_LIMITS.items():
            value = normalized[field]
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValidationError({field: f"Must be an integer from {minimum} through {maximum}."})
        for field, (minimum, maximum) in FLOAT_LIMITS.items():
            value = normalized[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= float(value) <= maximum:
                raise ValidationError({field: f"Must be a number from {minimum} through {maximum}."})
            normalized[field] = float(value)
        if normalized["retention_days"] < normalized["retention_min_days"]:
            raise ValidationError({"retention_days": "Must be at least retention_min_days."})
        if normalized["algorithm_threshold_min"] >= normalized["algorithm_threshold_max"]:
            raise ValidationError({"algorithm_threshold_max": "Must exceed algorithm_threshold_min."})
        for name in ("heuristic_default_threshold", "inductive_default_threshold"):
            if not normalized["algorithm_threshold_min"] <= normalized[name] <= normalized["algorithm_threshold_max"]:
                raise ValidationError({name: "Must fall inside the configured algorithm threshold range."})
        if not (
            normalized["bottleneck_critical_ratio"] > normalized["bottleneck_high_ratio"]
            > normalized["bottleneck_medium_ratio"]
        ):
            raise ValidationError({"bottleneck_critical_ratio": "Severity ratios must be strictly descending."})
        if normalized["visual_zoom_min"] >= normalized["visual_zoom_max"]:
            raise ValidationError({"visual_zoom_max": "Must exceed visual_zoom_min."})
        if normalized["visual_edge_width_min"] >= normalized["visual_edge_width_max"]:
            raise ValidationError({"visual_edge_width_max": "Must exceed visual_edge_width_min."})
        keys = normalized["forbidden_attribute_keys"]
        if not isinstance(keys, list) or not keys or len(keys) > 100 or not all(
            isinstance(item, str) and item.strip() and len(item) <= 64 for item in keys
        ):
            raise ValidationError({"forbidden_attribute_keys": "Requires 1-100 nonempty keys up to 64 characters."})
        normalized["forbidden_attribute_keys"] = sorted({item.strip().lower() for item in keys})
        if normalized["environment"] not in {"default", "development", "self-hosted", "saas"}:
            raise ValidationError({"environment": "Unsupported environment."})
        if normalized["default_discovery_algorithm"] not in MiningAlgorithmName.values:
            raise ValidationError({"default_discovery_algorithm": "Unsupported mining algorithm."})
        if not isinstance(normalized["enabled"], bool):
            raise ValidationError({"enabled": "Must be a boolean."})
        for field in ("rollout_roles", "rollout_cohorts", "analysis_terminal_states", "export_terminal_states"):
            value = normalized[field]
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                raise ValidationError({field: "Must be a list of nonempty strings."})
        analysis_states = {"queued", "running", "completed", "failed", "timed_out", "cancelled"}
        export_states = analysis_states | {"expired"}
        self_validate_workflow(normalized["analysis_transitions"], analysis_states, "analysis_transitions")
        self_validate_workflow(normalized["export_transitions"], export_states, "export_transitions")
        if not set(normalized["analysis_terminal_states"]).issubset(analysis_states):
            raise ValidationError({"analysis_terminal_states": "Contains an unsupported state."})
        if not set(normalized["export_terminal_states"]).issubset(export_states):
            raise ValidationError({"export_terminal_states": "Contains an unsupported state."})
        for workflow_field, terminal_field in (
            ("analysis_transitions", "analysis_terminal_states"),
            ("export_transitions", "export_terminal_states"),
        ):
            if any(normalized[workflow_field][state] for state in normalized[terminal_field]):
                raise ValidationError({terminal_field: "Terminal states cannot declare outgoing transitions."})
        return normalized

    def get_configuration(self, tenant_id: UUID, actor_id: UUID | None = None, correlation_id: str | None = None) -> ProcessMiningConfiguration:
        tenant_id = _tenant(tenant_id)
        existing = ProcessMiningConfiguration.objects.for_tenant(tenant_id).first()
        if existing is not None:
            # Corrupt persisted policy must fail closed rather than silently use defaults.
            self.validate_document(existing.document)
            return existing
        actor = _actor(actor_id or UUID(int=0))
        correlation = _correlation_id(correlation_id)
        document = self.validate_document(deepcopy(DEFAULT_CONFIGURATION))
        with transaction.atomic():
            configuration, created = ProcessMiningConfiguration.objects.get_or_create(
                tenant_id=tenant_id,
                defaults={"document": document, "version": 1, "updated_by": actor},
            )
            if created:
                self._record(configuration, actor, correlation, {}, document, "initialize", "default")
        return configuration

    def resolve(self, tenant_id: UUID) -> dict[str, object]:
        return deepcopy(self.get_configuration(tenant_id).document)

    def preview(self, tenant_id: UUID, document: object) -> dict[str, object]:
        current = self.get_configuration(tenant_id)
        normalized = self.validate_document(document)
        changed = {
            key: {"from": current.document[key], "to": normalized[key]}
            for key in normalized
            if current.document[key] != normalized[key]
        }
        return {"valid": True, "current_version": current.version, "changes": changed, "document": normalized}

    def update(self, tenant_id: UUID, actor_id: UUID, correlation_id: str, document: object, *, source: str = "api", action: str = "update") -> ProcessMiningConfiguration:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        correlation = _correlation_id(correlation_id)
        normalized = self.validate_document(document)
        with transaction.atomic():
            current = ProcessMiningConfiguration.objects.select_for_update().for_tenant(tenant_id).first()
            if current is None:
                current = self.get_configuration(tenant_id, actor_id, correlation)
            previous = deepcopy(current.document)
            if previous == normalized:
                return current
            current.document = normalized
            current.version += 1
            current.updated_by = actor_id
            current.save(update_fields=["document", "version", "updated_by", "updated_at"])
            self._record(current, actor_id, correlation, previous, normalized, action, source)
        return current

    def history(self, tenant_id: UUID) -> QuerySet[ProcessMiningConfigurationVersion]:
        configuration = self.get_configuration(tenant_id)
        return ProcessMiningConfigurationVersion.objects.for_tenant(configuration.tenant_id).filter(
            configuration=configuration
        ).order_by("-version", "-created_at")

    def rollback(self, tenant_id: UUID, actor_id: UUID, correlation_id: str, version: int) -> ProcessMiningConfiguration:
        configuration = self.get_configuration(tenant_id, actor_id, correlation_id)
        snapshot = ProcessMiningConfigurationVersion.objects.for_tenant(configuration.tenant_id).filter(
            configuration=configuration, version=version
        ).first()
        if snapshot is None:
            raise NotFound("Configuration version was not found.")
        return self.update(tenant_id, actor_id, correlation_id, snapshot.document, source=f"rollback:{version}", action="rollback")

    def export_document(self, tenant_id: UUID) -> dict[str, object]:
        configuration = self.get_configuration(tenant_id)
        return {"schema_version": "1.0", "module": "process_mining", "version": configuration.version, "document": deepcopy(configuration.document)}

    def import_document(self, tenant_id: UUID, actor_id: UUID, correlation_id: str, payload: object) -> ProcessMiningConfiguration:
        if not isinstance(payload, dict) or payload.get("schema_version") != "1.0" or payload.get("module") != "process_mining":
            raise ValidationError({"configuration": "Expected a process_mining configuration document with schema_version 1.0."})
        return self.update(tenant_id, actor_id, correlation_id, payload.get("document"), source="import", action="import")

    @staticmethod
    def _record(configuration: ProcessMiningConfiguration, actor_id: UUID, correlation_id: str, previous: dict[str, object], current: dict[str, object], action: str, source: str) -> None:
        common = {"tenant_id": configuration.tenant_id, "created_by": actor_id, "configuration": configuration, "version": configuration.version, "correlation_id": correlation_id}
        ProcessMiningConfigurationVersion.objects.create(**common, document=deepcopy(current), source=source)
        ProcessMiningConfigurationAudit.objects.create(**common, action=action, previous_document=deepcopy(previous), current_document=deepcopy(current))


def self_validate_workflow(value: object, states: set[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != states:
        raise ValidationError({field: "Must define every supported state exactly once."})
    if not all(isinstance(targets, list) and set(targets).issubset(states) for targets in value.values()):
        raise ValidationError({field: "Contains an unsupported transition target."})


def _configuration(tenant_id: UUID) -> dict[str, object]:
    return ProcessMiningConfigurationService().resolve(tenant_id)


def _workflow_machine(tenant_id: UUID, workflow_kind: str):
    """Build the command engine from the tenant's validated, versioned policy."""
    configuration = _configuration(tenant_id)
    if workflow_kind == "export":
        return configured_state_machine(
            name="process_mining.export",
            model=EventExportJob,
            states=ExportStatus.values,
            workflow=configuration["export_transitions"],
            terminal_states=configuration["export_terminal_states"],
        )
    models = {
        "discovery": ProcessDiscoveryJob,
        "conformance": ConformanceCheck,
        "bottleneck": BottleneckAnalysis,
    }
    model = models.get(workflow_kind)
    if model is None:
        raise ValidationError({"workflow": "Unsupported process-mining workflow."})
    return configured_state_machine(
        name=f"process_mining.{workflow_kind}",
        model=model,
        states=AnalysisStatus.values,
        workflow=configuration["analysis_transitions"],
        terminal_states=configuration["analysis_terminal_states"],
    )


def _required_text(value: object, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({field: "This field is required."})
    normalized = value.strip()
    if len(normalized) > limit:
        raise ValidationError({field: f"Must not exceed {limit} characters."})
    return normalized


def _aware_datetime(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError({field: "A valid ISO-8601 datetime is required."}) from exc
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValidationError({field: "A timezone-aware datetime is required."})
    return value


def _audit(actor_id: UUID, reason: str) -> dict[str, str]:
    return {
        "actor_id": str(actor_id),
        "reason": reason,
        "correlation_id": _correlation_id(),
    }


def _publish(tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, payload: Mapping[str, object]) -> OutboxEvent:
    safe_payload = dict(payload)
    safe_payload.setdefault("correlation_id", _correlation_id())
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=safe_payload,
    )


def _enqueue_or_unavailable(
    tenant_id: UUID,
    actor_id: UUID,
    command: str,
    payload: dict[str, object],
    idempotency_key: str,
) -> AsyncJob:
    try:
        return enqueue(tenant_id, actor_id, command, payload, idempotency_key)
    except Exception as exc:
        logger.exception("process_mining.queue_unavailable", extra={"event_name": "process_mining.queue_unavailable", "tenant_id": str(tenant_id), "command": command, "correlation_id": _correlation_id()})
        raise CapabilityUnavailable(capability="durable_job_dispatch", message="Durable processing is temporarily unavailable.") from exc


def _get(model: type[Any], tenant_id: UUID, identifier: UUID | str, *, active: bool = False) -> Any:
    filters: dict[str, object] = {"pk": identifier}
    if active and any(field.name == "is_deleted" for field in model._meta.fields):
        filters["is_deleted"] = False
    value = model.objects.for_tenant(tenant_id).filter(**filters).first()
    if value is None:
        raise NotFound()
    return value


def _canonical_hash(
    tenant_id: UUID,
    process_name: str,
    case_id: str,
    activity: str,
    occurred_at: datetime,
    source_module: str,
    source_event_id: str,
) -> str:
    parts = (
        str(tenant_id),
        process_name,
        case_id,
        activity,
        occurred_at.astimezone(datetime_timezone.utc).isoformat(timespec="microseconds"),
        source_module,
        source_event_id,
    )
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()


def _safe_attributes(value: object, configuration: Mapping[str, object]) -> dict[str, object]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError({"attributes": "Attributes must be an object."})
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    maximum = int(configuration["attributes_max_bytes"])
    if len(encoded.encode("utf-8")) > maximum:
        raise ValidationError({"attributes": f"Attributes must not exceed {maximum} bytes."})
    forbidden = set(configuration["forbidden_attribute_keys"])
    if any(str(key).lower() in forbidden for key in value):
        raise ValidationError({"attributes": "Credential-like attribute keys are forbidden."})
    return value


class EventLogService:
    def ingest_events(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        source_module: str,
        process_name: str,
        events: Sequence[Mapping[str, object]],
    ) -> IngestResult:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        configuration = _configuration(tenant_id)
        text_limit = int(configuration["text_max_length"])
        source_module = _required_text(source_module, "source_module", int(configuration["source_module_max_length"]))
        process_name = _required_text(process_name, "process_name", text_limit)
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)) or not events:
            raise ValidationError({"events": "A nonempty event array is required."})
        max_batch_events = int(configuration["max_batch_events"])
        if len(events) > max_batch_events:
            raise ValidationError({"events": f"A batch may contain at most {max_batch_events} events."})
        source = registry.get("process_mining.canonical")
        if not source.validate_source(source_module):
            raise ValidationError({"source_module": "The source is not registered."})
        now = timezone.now()
        cutoff = now - timedelta(days=int(configuration["max_event_age_days"]))
        future_cutoff = now + timedelta(seconds=int(configuration["future_clock_skew_seconds"]))
        valid: list[tuple[int, ProcessEvent]] = []
        evidence: list[IngestRowEvidence] = []
        seen_hashes: set[str] = set()
        seen_sources: set[str] = set()
        for index, raw in enumerate(events):
            try:
                mapped = source.map_event(raw)
                case_id = _required_text(mapped.get("case_id"), "case_id", text_limit)
                activity = _required_text(mapped.get("activity"), "activity", text_limit)
                occurred_at = _aware_datetime(mapped.get("occurred_at"), "occurred_at")
                if occurred_at < cutoff:
                    raise ValidationError({"occurred_at": "Events older than two years are rejected."})
                if occurred_at > future_cutoff:
                    raise ValidationError({"occurred_at": "Event exceeds the configured future clock skew."})
                source_event_id = str(mapped.get("source_event_id") or "").strip()
                resource = str(mapped.get("resource") or "").strip()
                event_hash = _canonical_hash(tenant_id, process_name, case_id, activity, occurred_at, source_module, source_event_id)
                if event_hash in seen_hashes or (source_event_id and source_event_id in seen_sources):
                    evidence.append(IngestRowEvidence(index, "duplicate", code="DUPLICATE_IN_BATCH", message="Duplicate event identity in this batch."))
                    continue
                seen_hashes.add(event_hash)
                if source_event_id:
                    seen_sources.add(source_event_id)
                valid.append(
                    (
                        index,
                        ProcessEvent(
                            tenant_id=tenant_id,
                            created_by=actor_id,
                            process_name=process_name,
                            source_module=source_module,
                            source_event_id=source_event_id or None,
                            case_id=case_id,
                            activity=activity,
                            occurred_at=occurred_at,
                            resource=resource or None,
                            attributes=_safe_attributes(mapped.get("attributes"), configuration),
                            event_hash=event_hash,
                        ),
                    )
                )
            except (ValidationError, ValueError, TypeError) as exc:
                evidence.append(IngestRowEvidence(index, "rejected", code="INVALID_EVENT", message=str(exc)))
        hashes = [event.event_hash for _, event in valid]
        existing_hashes = set(
            ProcessEvent.objects.for_tenant(tenant_id).filter(event_hash__in=hashes).values_list("event_hash", flat=True)
        )
        source_ids = [event.source_event_id for _, event in valid if event.source_event_id]
        existing_sources = set(
            ProcessEvent.objects.for_tenant(tenant_id)
            .filter(source_module=source_module, source_event_id__in=source_ids)
            .values_list("source_event_id", flat=True)
        )
        inserts: list[ProcessEvent] = []
        for index, event in valid:
            if event.event_hash in existing_hashes or (event.source_event_id and event.source_event_id in existing_sources):
                evidence.append(IngestRowEvidence(index, "duplicate", code="ALREADY_INGESTED", message="Event identity already exists."))
            else:
                inserts.append(event)
        with transaction.atomic():
            ProcessEvent.objects.bulk_create(
                inserts, ignore_conflicts=True, batch_size=int(configuration["bulk_insert_batch_size"])
            )
            for event in inserts:
                persisted = ProcessEvent.objects.for_tenant(tenant_id).filter(event_hash=event.event_hash).only("id").first()
                evidence.append(IngestRowEvidence(next(index for index, candidate in valid if candidate is event), "accepted", persisted.id if persisted else None))
            aggregate_id = inserts[0].id if inserts else uuid.uuid5(uuid.NAMESPACE_URL, f"process-events:{tenant_id}:{process_name}")
            _publish(tenant_id, "process_event_batch", aggregate_id, "process.events.ingested", {"process_name": process_name, "source_module": source_module, "accepted": len(inserts), "rejected": sum(item.status == "rejected" for item in evidence), "duplicates": sum(item.status == "duplicate" for item in evidence)})
        ordered = tuple(sorted(evidence, key=lambda item: item.index))
        result = IngestResult(sum(item.status == "accepted" for item in ordered), sum(item.status == "rejected" for item in ordered), sum(item.status == "duplicate" for item in ordered), ordered)
        logger.info("process.events.ingested", extra={"event_name": "process.events.ingested", "tenant_id": str(tenant_id), "actor_id": str(actor_id), "accepted": result.accepted, "rejected": result.rejected, "duplicates": result.duplicates, "correlation_id": _correlation_id()})
        return result

    def query_events(self, tenant_id: UUID, filters: Mapping[str, object]) -> QuerySet[ProcessEvent]:
        tenant_id = _tenant(tenant_id)
        configuration = _configuration(tenant_id)
        process_name = _required_text(filters.get("process_name"), "process_name", int(configuration["text_max_length"]))
        start = _aware_datetime(filters.get("start"), "start")
        end = _aware_datetime(filters.get("end"), "end")
        if end <= start:
            raise ValidationError({"end": "End must follow start."})
        maximum_days = int(configuration["event_query_max_days"])
        if end - start > timedelta(days=maximum_days):
            raise ValidationError({"end": f"Event queries are bounded to {maximum_days} days."})
        queryset = ProcessEvent.objects.for_tenant(tenant_id).filter(process_name=process_name, occurred_at__gte=start, occurred_at__lte=end)
        for field in ("case_id", "activity", "resource", "source_module"):
            if filters.get(field):
                queryset = queryset.filter(**{field: filters[field]})
        ordering = str(filters.get("ordering") or "occurred_at")
        if ordering not in {"occurred_at", "-occurred_at"}:
            raise ValidationError({"ordering": "Only occurred_at ordering is supported."})
        return queryset.order_by(ordering, "id")

    def get_event(self, tenant_id: UUID, event_id: UUID) -> ProcessEvent:
        return _get(ProcessEvent, _tenant(tenant_id), event_id)

    def purge_expired_events(self, tenant_id: UUID, retention_days: int | None = None, actor_id: UUID | None = None) -> int:
        tenant_id = _tenant(tenant_id)
        actor_id = _actor(actor_id or uuid.UUID(int=0))
        configuration = _configuration(tenant_id)
        retention_days = int(configuration["retention_days"] if retention_days is None else retention_days)
        minimum = int(configuration["retention_min_days"])
        if retention_days < minimum:
            raise ValidationError({"retention_days": f"Retention must be at least {minimum} days."})
        cutoff = timezone.now() - timedelta(days=retention_days)
        with transaction.atomic():
            queryset = ProcessEvent.objects.for_tenant(tenant_id).filter(occurred_at__lt=cutoff)
            count = queryset.count()
            tombstone, _created = ProcessEventRetentionTombstone.objects.get_or_create(
                tenant_id=tenant_id,
                cutoff=cutoff,
                defaults={"created_by": actor_id, "event_count": count, "reason": "configured retention authorization", "correlation_id": _correlation_id()},
            )
            _publish(tenant_id, "process_event_retention", tombstone.id, "process.events.retention_authorized", {"count": count, "cutoff": cutoff.isoformat(), "actor_id": str(actor_id)})
        return count


def _filter_events(tenant_id: UUID, process_name: str, event_filter: Mapping[str, object]) -> QuerySet[ProcessEvent]:
    queryset = ProcessEvent.objects.for_tenant(tenant_id).filter(process_name=process_name)
    if event_filter.get("start"):
        queryset = queryset.filter(occurred_at__gte=_aware_datetime(event_filter["start"], "start"))
    if event_filter.get("end"):
        queryset = queryset.filter(occurred_at__lte=_aware_datetime(event_filter["end"], "end"))
    for field in ("case_id", "activity", "resource", "source_module"):
        if event_filter.get(field):
            queryset = queryset.filter(**{field: event_filter[field]})
    return queryset.order_by("case_id", "occurred_at", "source_event_id", "activity", "id")


def _ordered(queryset: QuerySet[Any], filters: Mapping[str, object], allowed: set[str], default: str) -> QuerySet[Any]:
    ordering = str(filters.get("ordering") or default)
    if ordering.lstrip("-") not in allowed:
        raise ValidationError({"ordering": "Unsupported ordering field."})
    return queryset.order_by(ordering, "id")


class ProcessMiningQueryService:
    """Tenant query policy; controllers never encode filtering/state rules."""

    @staticmethod
    def find(queryset: QuerySet[Any], resource_id: UUID | str) -> Any | None:
        return queryset.filter(pk=resource_id).first()

    @staticmethod
    def exists(queryset: QuerySet[Any], resource_id: UUID | str) -> bool:
        return queryset.filter(pk=resource_id).exists()

    @staticmethod
    def model_versions(tenant_id: UUID, process_model_id: UUID | str) -> QuerySet[ProcessModelVersion]:
        return ProcessModelVersion.objects.for_tenant(_tenant(tenant_id)).filter(
            process_model_id=process_model_id
        ).order_by("-version", "-id")

    @staticmethod
    def configurations(tenant_id: UUID) -> QuerySet[ProcessMiningConfiguration]:
        return ProcessMiningConfiguration.objects.for_tenant(_tenant(tenant_id)).order_by("id")

    @staticmethod
    def exports(tenant_id: UUID, filters: Mapping[str, object]) -> QuerySet[EventExportJob]:
        queryset = EventExportJob.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False)
        for field in ("process_name", "format", "status"):
            if filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters.get("created_after"):
            queryset = queryset.filter(created_at__gte=filters["created_after"])
        if filters.get("created_before"):
            queryset = queryset.filter(created_at__lte=filters["created_before"])
        return _ordered(queryset, filters, {"created_at", "completed_at"}, "-created_at")

    @staticmethod
    def discoveries(tenant_id: UUID, filters: Mapping[str, object]) -> QuerySet[ProcessDiscoveryJob]:
        queryset = ProcessDiscoveryJob.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False)
        for field in ("process_name", "algorithm", "status"):
            if filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return _ordered(queryset, filters, {"created_at", "completed_at"}, "-created_at")

    @staticmethod
    def models(tenant_id: UUID, filters: Mapping[str, object]) -> QuerySet[ProcessModel]:
        queryset = ProcessModel.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False)
        for field in ("process_name", "source_kind"):
            if filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters.get("has_reference") is not None:
            expected = str(filters["has_reference"]).lower() in {"1", "true"}
            referenced = ProcessModelReferenceAssignment.objects.for_tenant(_tenant(tenant_id)).values("process_model_id")
            queryset = queryset.filter(id__in=referenced) if expected else queryset.exclude(id__in=referenced)
        search = str(filters.get("search") or "").strip()
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return queryset.order_by("name", "id")

    @staticmethod
    def conformance(tenant_id: UUID, filters: Mapping[str, object]) -> QuerySet[ConformanceCheck]:
        queryset = ConformanceCheck.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False)
        for field in ("process_model_version", "status"):
            if filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters.get("fitness_min") not in (None, ""):
            queryset = queryset.filter(fitness__gte=filters["fitness_min"])
        if filters.get("fitness_max") not in (None, ""):
            queryset = queryset.filter(fitness__lte=filters["fitness_max"])
        return _ordered(queryset, filters, {"created_at", "completed_at", "fitness"}, "-created_at")

    @staticmethod
    def bottlenecks(tenant_id: UUID, filters: Mapping[str, object]) -> QuerySet[BottleneckAnalysis]:
        queryset = BottleneckAnalysis.objects.for_tenant(_tenant(tenant_id)).filter(is_deleted=False)
        for field in ("process_name", "status"):
            if filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return _ordered(queryset, filters, {"created_at", "completed_at", "time_range_start"}, "-created_at")


class ExportService:
    def request_export(self, tenant_id: UUID, actor_id: UUID, process_name: str, format: str, event_filter: Mapping[str, object], idempotency_key: str) -> EventExportJob:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        configuration = _configuration(tenant_id)
        limit = int(configuration["text_max_length"])
        process_name, idempotency_key = _required_text(process_name, "process_name", limit), _required_text(idempotency_key, "idempotency_key", limit)
        if format not in ExportFormat.values:
            raise ValidationError({"format": "Supported formats are xes, csv, and json."})
        existing = EventExportJob.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        count = _filter_events(tenant_id, process_name, event_filter).count()
        projected = count * int(configuration["export_projection_bytes_per_event"])
        if count > int(configuration["max_export_events"]) or projected > int(configuration["max_export_bytes"]):
            raise OperationFailed(error_code="EXPORT_TOO_LARGE", message="The requested export exceeds the safe limit.", detail={"projected_rows": count, "projected_bytes": projected}, http_status=413)
        with transaction.atomic():
            record = EventExportJob.objects.create(tenant_id=tenant_id, created_by=actor_id, process_name=process_name, format=format, event_filter=dict(event_filter), idempotency_key=idempotency_key)
            job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.export_event_log", {"export_id": str(record.id)}, f"process_mining.export:{idempotency_key}")
            record.async_job_id = job.id
            record.save(update_fields=["async_job_id", "updated_at"])
            _publish(tenant_id, "event_export", record.id, "process.export.requested", {"export_id": str(record.id), "format": format, "projected_rows": count})
        return record

    def run_export(self, tenant_id: UUID, export_id: UUID, async_job_id: UUID) -> EventExportJob:
        tenant_id = _tenant(tenant_id)
        record = _get(EventExportJob, tenant_id, export_id, active=True)
        if record.status == ExportStatus.COMPLETED:
            return record
        if record.async_job_id != async_job_id:
            raise NotFound()
        actor_id = record.created_by
        configuration = _configuration(tenant_id)
        record = _workflow_machine(tenant_id, "export").apply(record, "start", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:start", metadata=_audit(actor_id, "Export worker started"))
        formatter = registry.get(record.format)
        if not isinstance(formatter, ExportFormatter):
            raise CapabilityUnavailable(capability=f"export:{record.format}")
        events = _filter_events(tenant_id, record.process_name, record.event_filter).iterator(
            chunk_size=int(configuration["export_iterator_chunk_size"])
        )
        key = f"process_mining/{tenant_id}/{record.id}.{formatter.extension}"
        stored_key = ""
        chunk_size = int(configuration["checksum_chunk_bytes"])
        try:
            with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8", newline="", suffix=f".{formatter.extension}") as temporary:
                count = formatter.write(canonical_events(events), temporary)
                temporary.flush()
                size = Path(temporary.name).stat().st_size
                digest = hashlib.sha256()
                with open(temporary.name, "rb") as source:
                    for chunk in iter(lambda: source.read(chunk_size), b""):
                        digest.update(chunk)
                temporary.seek(0)
                stored_key = default_storage.save(key, File(temporary, name=Path(key).name))
            with default_storage.open(stored_key, "rb") as stored:
                verified = hashlib.sha256()
                for chunk in iter(lambda: stored.read(chunk_size), b""):
                    verified.update(chunk)
            if verified.hexdigest() != digest.hexdigest():
                default_storage.delete(stored_key)
                raise IOError("stored export checksum mismatch")
            now = timezone.now()
            with transaction.atomic():
                EventExportJob.objects.for_tenant(tenant_id).filter(pk=record.id).update(artifact_key=stored_key, content_type=formatter.content_type, row_count=count, byte_size=size, sha256=digest.hexdigest(), expires_at=now + timedelta(days=int(configuration["export_expiry_days"])), completed_at=now, error_code="", error_message="")
                record = EventExportJob.objects.for_tenant(tenant_id).get(pk=record.id)
                record = _workflow_machine(tenant_id, "export").apply(record, "complete", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:complete", metadata=_audit(actor_id, "Export artifact verified"))
                _publish(tenant_id, "event_export", record.id, "process.export.completed", {"export_id": str(record.id), "format": record.format, "row_count": count, "byte_size": size, "sha256": digest.hexdigest()})
            return record
        except Exception as exc:
            if stored_key and default_storage.exists(stored_key):
                default_storage.delete(stored_key)
            EventExportJob.objects.for_tenant(tenant_id).filter(pk=record.id).update(error_code="EXPORT_STORAGE_FAILED", error_message="Export storage is unavailable.")
            fresh = EventExportJob.objects.for_tenant(tenant_id).get(pk=record.id)
            if fresh.status == ExportStatus.RUNNING:
                _workflow_machine(tenant_id, "export").apply(fresh, "fail", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:fail", metadata=_audit(actor_id, "Export failed"))
            _publish(tenant_id, "event_export", record.id, "process.export.failed", {"export_id": str(record.id), "error_code": "EXPORT_STORAGE_FAILED"})
            raise CapabilityUnavailable(capability="export_storage", message="The export could not be stored.") from exc

    def open_download(self, tenant_id: UUID, export_id: UUID) -> tuple[EventExportJob, Any]:
        record = _get(EventExportJob, _tenant(tenant_id), export_id, active=True)
        chunk_size = int(_configuration(record.tenant_id)["checksum_chunk_bytes"])
        if record.status != ExportStatus.COMPLETED or not record.artifact_key or not default_storage.exists(record.artifact_key):
            raise CapabilityUnavailable(capability="export_artifact", message="The export artifact is not available.")
        stream = default_storage.open(record.artifact_key, "rb")
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
        if digest.hexdigest() != record.sha256:
            stream.close()
            raise OperationFailed(error_code="ARTIFACT_INTEGRITY_FAILED", message="Export verification failed.", http_status=503)
        stream.seek(0)
        return record, stream

    def _transition(self, tenant_id: UUID, export_id: UUID, actor_id: UUID, command: str, transition_key: str, reason: str = "") -> EventExportJob:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(EventExportJob, tenant_id, export_id, active=True)
        updated = _workflow_machine(tenant_id, "export").apply(record, command, tenant_id=tenant_id, transition_key=_required_text(transition_key, "transition_key", int(_configuration(tenant_id)["text_max_length"])), metadata=_audit(actor_id, reason or f"Export {command}"))
        _publish(tenant_id, "event_export", updated.id, f"process.export.{updated.status}", {"export_id": str(updated.id)})
        return updated

    def cancel_export(self, tenant_id: UUID, export_id: UUID, actor_id: UUID, transition_key: str, reason: str = "") -> EventExportJob:
        return self._transition(tenant_id, export_id, actor_id, "cancel", transition_key, reason)

    def retry_export(self, tenant_id: UUID, export_id: UUID, actor_id: UUID, transition_key: str, idempotency_key: str) -> EventExportJob:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = self._transition(tenant_id, export_id, actor_id, "retry", transition_key)
        with transaction.atomic():
            job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.export_event_log", {"export_id": str(record.id)}, _required_text(idempotency_key, "idempotency_key", int(_configuration(tenant_id)["text_max_length"])))
            record.async_job_id = job.id
            record.save(update_fields=["async_job_id", "updated_at"])
        return record

    def expire_export(self, tenant_id: UUID, export_id: UUID, actor_id: UUID, transition_key: str) -> EventExportJob:
        record = self._transition(tenant_id, export_id, actor_id, "expire", transition_key)
        if record.artifact_key:
            default_storage.delete(record.artifact_key)
        return record

    def delete_export(self, tenant_id: UUID, export_id: UUID, actor_id: UUID) -> None:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(EventExportJob, tenant_id, export_id, active=True)
        if record.status not in set(_configuration(tenant_id)["export_terminal_states"]):
            raise ValidationError({"status": "Only terminal export metadata can be deleted."})
        artifact_key = record.artifact_key
        with transaction.atomic():
            EventExportJob.objects.for_tenant(tenant_id).filter(pk=record.id).update(is_deleted=True, deleted_at=timezone.now())
            if artifact_key:
                deletion, _created = ExportArtifactDeletion.objects.get_or_create(
                    tenant_id=tenant_id,
                    export_job=record,
                    defaults={"created_by": actor_id, "artifact_key": artifact_key, "correlation_id": _correlation_id()},
                )
                _publish(tenant_id, "export_artifact_deletion", deletion.id, "process.export.artifact_deletion_requested", {"export_id": str(record.id), "artifact_key": artifact_key})
        if artifact_key:
            try:
                default_storage.delete(artifact_key)
            except Exception as exc:
                logger.exception("process.export.artifact_deletion_deferred", extra={"event_name": "process.export.artifact_deletion_deferred", "tenant_id": str(tenant_id), "export_id": str(record.id), "correlation_id": _correlation_id()})
                raise CapabilityUnavailable(capability="export_artifact_deletion", message="Deletion is durably queued for reconciliation.") from exc


class ProcessModelService:
    def create_imported_model(self, tenant_id: UUID, actor_id: UUID, name: str, process_name: str, description: str, model_data: Mapping[str, object]) -> ProcessModel:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        limit = int(_configuration(tenant_id)["text_max_length"])
        validate_graph(model_data)
        with transaction.atomic():
            model = ProcessModel.objects.create(tenant_id=tenant_id, created_by=actor_id, name=_required_text(name, "name", limit), process_name=_required_text(process_name, "process_name", limit), description=str(description or "").strip(), source_kind=ModelSourceKind.IMPORTED)
            self.create_version(tenant_id, model.id, actor_id, model_data, algorithm=None, parameters={}, discovery_job=None)
        return model

    def create_version(self, tenant_id: UUID, model_id: UUID, actor_id: UUID, model_data: Mapping[str, object], *, algorithm: str | None, parameters: Mapping[str, object], discovery_job: ProcessDiscoveryJob | None, event_count: int = 0, case_count: int = 0, activity_count: int = 0, avg_case_duration_seconds: Decimal | None = None) -> ProcessModelVersion:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        validate_graph(model_data)
        with transaction.atomic():
            model = ProcessModel.objects.for_tenant(tenant_id).select_for_update().filter(pk=model_id, is_deleted=False).first()
            if model is None:
                raise NotFound()
            if discovery_job and discovery_job.tenant_id != tenant_id:
                raise NotFound()
            version_number = model.versions.filter(tenant_id=tenant_id).aggregate(value=Max("version"))["value"] or 0
            version = ProcessModelVersion.objects.create(tenant_id=tenant_id, created_by=actor_id, process_model=model, version=version_number + 1, discovery_job=discovery_job, algorithm=algorithm, parameters=dict(parameters), model_data=dict(model_data), event_count=event_count, case_count=case_count, activity_count=activity_count, avg_case_duration_seconds=avg_case_duration_seconds, published_at=timezone.now())
            model.current_version_number = version.version
            model.save(update_fields=["current_version_number", "updated_at"])
        return version

    def update_model_metadata(self, tenant_id: UUID, model_id: UUID, actor_id: UUID, name: str, description: str) -> ProcessModel:
        tenant_id, _actor_id = _tenant(tenant_id), _actor(actor_id)
        limit = int(_configuration(tenant_id)["text_max_length"])
        model = _get(ProcessModel, tenant_id, model_id, active=True)
        model.name = _required_text(name, "name", limit)
        model.description = str(description or "").strip()
        model.save(update_fields=["name", "description", "updated_at"])
        return model

    def soft_delete_model(self, tenant_id: UUID, model_id: UUID, actor_id: UUID) -> None:
        tenant_id, _actor_id = _tenant(tenant_id), _actor(actor_id)
        model = _get(ProcessModel, tenant_id, model_id, active=True)
        if ConformanceCheck.objects.for_tenant(tenant_id).filter(process_model_version__process_model=model, status__in=[AnalysisStatus.QUEUED, AnalysisStatus.RUNNING], is_deleted=False).exists():
            raise ValidationError({"model": "Active analyses still reference this model."})
        ProcessModel.objects.for_tenant(tenant_id).filter(pk=model.id).update(is_deleted=True, deleted_at=timezone.now())

    def set_reference_version(self, tenant_id: UUID, model_id: UUID, version_id: UUID, actor_id: UUID, transition_key: str, reason: str = "", correlation_id: str | None = None) -> ProcessModelVersion:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        transition_key = _required_text(transition_key, "transition_key", int(_configuration(tenant_id)["text_max_length"]))
        with transaction.atomic():
            model = ProcessModel.objects.for_tenant(tenant_id).select_for_update().filter(pk=model_id, is_deleted=False).first()
            version = ProcessModelVersion.objects.for_tenant(tenant_id).filter(pk=version_id, process_model_id=model_id).first()
            if model is None or version is None:
                raise NotFound()
            ProcessModelReferenceAssignment.objects.create(
                tenant_id=tenant_id, created_by=actor_id, process_model=model, process_model_version=version,
                transition_key=transition_key, reason=str(reason or "").strip(), correlation_id=_correlation_id(correlation_id),
            )
            _publish(tenant_id, "process_model", model.id, "process.model.reference_changed", {"model_id": str(model.id), "version_id": str(version.id), "transition_key": transition_key, "actor_id": str(actor_id)})
        return version

    def get_process_overview(self, tenant_id: UUID, filters: Mapping[str, object]) -> list[dict[str, object]]:
        tenant_id = _tenant(tenant_id)
        events = ProcessEvent.objects.for_tenant(tenant_id)
        if filters.get("process_name"):
            events = events.filter(process_name=filters["process_name"])
        if filters.get("source_module"):
            events = events.filter(source_module=filters["source_module"])
        search = str(filters.get("search") or "").strip()
        if search:
            events = events.filter(process_name__icontains=search)
        rows = list(events.values("process_name").annotate(event_count=Count("id"), case_count=Count("case_id", distinct=True), last_activity=Max("occurred_at")).order_by("process_name"))
        for row in rows:
            model = ProcessModel.objects.for_tenant(tenant_id).filter(process_name=row["process_name"], is_deleted=False).order_by("-created_at").first()
            discovery = ProcessDiscoveryJob.objects.for_tenant(tenant_id).filter(process_name=row["process_name"], is_deleted=False).order_by("-created_at").first()
            has_reference = bool(model and ProcessModelReferenceAssignment.objects.for_tenant(tenant_id).filter(process_model=model).exists())
            row.update({"has_reference": has_reference, "model_id": model.id if model else None, "last_discovery": discovery.created_at if discovery else None})
        if filters.get("has_reference") is not None:
            expected = str(filters["has_reference"]).lower() in {"true", "1"}
            rows = [row for row in rows if row["has_reference"] is expected]
        order = str(filters.get("ordering") or "process_name")
        mappings = {"cases": "case_count", "events": "event_count", "last_activity": "last_activity", "last_discovery": "last_discovery", "process_name": "process_name"}
        descending = order.startswith("-")
        key = mappings.get(order.lstrip("-"))
        if key is None:
            raise ValidationError({"ordering": "Unsupported process ordering."})
        rows.sort(key=lambda row: (row.get(key) is not None, row.get(key)), reverse=descending)
        return rows


class ProcessDiscoveryService:
    def request_discovery(self, tenant_id: UUID, actor_id: UUID, process_name: str, algorithm: str, parameters: Mapping[str, object], idempotency_key: str) -> ProcessDiscoveryJob:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        configuration = _configuration(tenant_id)
        limit = int(configuration["text_max_length"])
        process_name, idempotency_key = _required_text(process_name, "process_name", limit), _required_text(idempotency_key, "idempotency_key", limit)
        existing = ProcessDiscoveryJob.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        if algorithm not in MiningAlgorithmName.values:
            raise ValidationError({"algorithm": "Unsupported mining algorithm."})
        adapter = registry.get(algorithm)
        if not isinstance(adapter, MiningAlgorithm):
            raise CapabilityUnavailable(capability=f"discovery:{algorithm}")
        queryset = ProcessEvent.objects.for_tenant(tenant_id).filter(process_name=process_name)
        counts = queryset.aggregate(events=Count("id"), cases=Count("case_id", distinct=True), activities=Count("activity", distinct=True))
        min_events, min_cases = int(configuration["discovery_min_events"]), int(configuration["discovery_min_cases"])
        if counts["events"] < min_events or counts["cases"] < min_cases:
            raise ValidationError({"process_name": f"Discovery requires at least {min_events} events across {min_cases} cases."})
        alpha_max = int(configuration["alpha_max_activities"])
        if algorithm == MiningAlgorithmName.ALPHA and counts["activities"] > alpha_max:
            raise ValidationError({"algorithm": f"Alpha miner supports at most {alpha_max} activities."})
        normalized = dict(parameters)
        threshold_name, default = ("dependency_threshold", configuration["heuristic_default_threshold"]) if algorithm == MiningAlgorithmName.HEURISTIC else ("noise_threshold", configuration["inductive_default_threshold"])
        if algorithm in {MiningAlgorithmName.HEURISTIC, MiningAlgorithmName.INDUCTIVE}:
            threshold = float(normalized.get(threshold_name, default))
            minimum, maximum = float(configuration["algorithm_threshold_min"]), float(configuration["algorithm_threshold_max"])
            if not minimum <= threshold <= maximum:
                raise ValidationError({threshold_name: f"Must be between {minimum} and {maximum}."})
            normalized[threshold_name] = threshold
        with transaction.atomic():
            record = ProcessDiscoveryJob.objects.create(tenant_id=tenant_id, created_by=actor_id, process_name=process_name, algorithm=algorithm, parameters=normalized, idempotency_key=idempotency_key, event_count=counts["events"], case_count=counts["cases"], activity_count=counts["activities"])
            job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.discover_process", {"discovery_id": str(record.id)}, f"process_mining.discovery:{idempotency_key}")
            record.async_job_id = job.id
            record.save(update_fields=["async_job_id", "updated_at"])
            _publish(tenant_id, "process_discovery", record.id, "process.discovery.requested", {"discovery_id": str(record.id), "algorithm": algorithm})
        return record

    def run_discovery(self, tenant_id: UUID, discovery_id: UUID, async_job_id: UUID) -> ProcessDiscoveryJob:
        tenant_id = _tenant(tenant_id)
        record = _get(ProcessDiscoveryJob, tenant_id, discovery_id, active=True)
        if record.status == AnalysisStatus.COMPLETED:
            return record
        if record.async_job_id != async_job_id:
            raise NotFound()
        record = _workflow_machine(tenant_id, "discovery").apply(record, "start", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:start", metadata=_audit(record.created_by, "Discovery worker started"))
        _publish(tenant_id, "process_discovery", record.id, "process.discovery.started", {"discovery_id": str(record.id), "algorithm": record.algorithm})
        try:
            rows = list(ProcessEvent.objects.for_tenant(tenant_id).filter(process_name=record.process_name).order_by("case_id", "occurred_at", "source_event_id", "activity", "id"))
            algorithm = registry.get(record.algorithm)
            if not isinstance(algorithm, MiningAlgorithm):
                raise CapabilityUnavailable(capability=f"discovery:{record.algorithm}")
            graph = algorithm.discover(canonical_events(rows), record.parameters)
            model_service = ProcessModelService()
            with transaction.atomic():
                model = ProcessModel.objects.for_tenant(tenant_id).filter(process_name=record.process_name, source_kind=ModelSourceKind.DISCOVERED, is_deleted=False).order_by("created_at").first()
                if model is None:
                    model = ProcessModel.objects.create(tenant_id=tenant_id, created_by=record.created_by, name=record.process_name, process_name=record.process_name, source_kind=ModelSourceKind.DISCOVERED)
                durations = []
                traces: dict[str, list[ProcessEvent]] = defaultdict(list)
                for row in rows:
                    traces[row.case_id].append(row)
                for trace in traces.values():
                    durations.append(max(0, (trace[-1].occurred_at - trace[0].occurred_at).total_seconds()))
                model_service.create_version(tenant_id, model.id, record.created_by, graph, algorithm=record.algorithm, parameters=record.parameters, discovery_job=record, event_count=len(rows), case_count=len(traces), activity_count=len({row.activity for row in rows}), avg_case_duration_seconds=Decimal(str(round(sum(durations) / len(durations), 2))) if durations else None)
                ProcessDiscoveryJob.objects.for_tenant(tenant_id).filter(pk=record.id).update(event_count=len(rows), case_count=len(traces), activity_count=len({row.activity for row in rows}), completed_at=timezone.now(), error_code="", error_message="")
                record = ProcessDiscoveryJob.objects.for_tenant(tenant_id).get(pk=record.id)
                record = _workflow_machine(tenant_id, "discovery").apply(record, "complete", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:complete", metadata=_audit(record.created_by, "Discovery model published"))
                _publish(tenant_id, "process_discovery", record.id, "process.discovery.completed", {"discovery_id": str(record.id), "algorithm": record.algorithm, "event_count": record.event_count, "case_count": record.case_count})
            return record
        except Exception as exc:
            ProcessDiscoveryJob.objects.for_tenant(tenant_id).filter(pk=record.id).update(error_code="DISCOVERY_FAILED", error_message="The discovery algorithm could not complete.", completed_at=timezone.now())
            fresh = ProcessDiscoveryJob.objects.for_tenant(tenant_id).get(pk=record.id)
            if fresh.status == AnalysisStatus.RUNNING:
                _workflow_machine(tenant_id, "discovery").apply(fresh, "fail", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:fail", metadata=_audit(fresh.created_by, "Discovery failed"))
            _publish(tenant_id, "process_discovery", record.id, "process.discovery.failed", {"discovery_id": str(record.id), "error_code": "DISCOVERY_FAILED"})
            raise OperationFailed(error_code="DISCOVERY_FAILED", message="Process discovery failed.") from exc

    def get_discovered_model(self, tenant_id: UUID, discovery_id: UUID) -> ProcessModelVersion:
        record = _get(ProcessDiscoveryJob, _tenant(tenant_id), discovery_id, active=True)
        if record.status != AnalysisStatus.COMPLETED:
            raise ValidationError({"status": "The discovery has not completed."})
        version = ProcessModelVersion.objects.for_tenant(record.tenant_id).filter(discovery_job=record).first()
        if version is None:
            raise NotFound()
        return version

    def _transition(self, tenant_id: UUID, discovery_id: UUID, actor_id: UUID, command: str, transition_key: str, reason: str = "") -> ProcessDiscoveryJob:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(ProcessDiscoveryJob, tenant_id, discovery_id, active=True)
        return _workflow_machine(tenant_id, "discovery").apply(record, command, tenant_id=tenant_id, transition_key=_required_text(transition_key, "transition_key", int(_configuration(tenant_id)["text_max_length"])), metadata=_audit(actor_id, reason or f"Discovery {command}"))

    def cancel_discovery(self, tenant_id: UUID, discovery_id: UUID, actor_id: UUID, transition_key: str, reason: str = "") -> ProcessDiscoveryJob:
        return self._transition(tenant_id, discovery_id, actor_id, "cancel", transition_key, reason)

    def retry_discovery(self, tenant_id: UUID, discovery_id: UUID, actor_id: UUID, transition_key: str, idempotency_key: str) -> ProcessDiscoveryJob:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = self._transition(tenant_id, discovery_id, actor_id, "retry", transition_key)
        job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.discover_process", {"discovery_id": str(record.id)}, _required_text(idempotency_key, "idempotency_key", int(_configuration(tenant_id)["text_max_length"])))
        record.async_job_id = job.id
        record.save(update_fields=["async_job_id", "updated_at"])
        return record

    def delete_discovery(self, tenant_id: UUID, discovery_id: UUID, actor_id: UUID) -> None:
        tenant_id, _actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(ProcessDiscoveryJob, tenant_id, discovery_id, active=True)
        if record.status not in set(_configuration(tenant_id)["analysis_terminal_states"]):
            raise ValidationError({"status": "Only terminal discovery jobs can be deleted."})
        ProcessDiscoveryJob.objects.for_tenant(tenant_id).filter(pk=record.id).update(is_deleted=True, deleted_at=timezone.now())


def _traces(rows: Iterable[ProcessEvent]) -> dict[str, list[CanonicalEvent]]:
    grouped: dict[str, list[CanonicalEvent]] = defaultdict(list)
    for event in canonical_events(rows):
        grouped[event.case_id].append(event)
    return grouped


class ConformanceService:
    def request_check(self, tenant_id: UUID, actor_id: UUID, model_version_id: UUID, event_filter: Mapping[str, object], idempotency_key: str) -> ConformanceCheck:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        configuration = _configuration(tenant_id)
        idempotency_key = _required_text(idempotency_key, "idempotency_key", int(configuration["text_max_length"]))
        existing = ConformanceCheck.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        version = _get(ProcessModelVersion, tenant_id, model_version_id)
        count = _filter_events(tenant_id, version.process_model.process_name, event_filter).count()
        maximum = int(configuration["max_conformance_events"])
        if count > maximum:
            raise ValidationError({"event_filter": f"Conformance is limited to {maximum} events."})
        if count == 0:
            raise ValidationError({"event_filter": "No events match this filter."})
        with transaction.atomic():
            record = ConformanceCheck.objects.create(tenant_id=tenant_id, created_by=actor_id, process_model_version=version, event_filter=dict(event_filter), idempotency_key=idempotency_key)
            job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.check_conformance", {"check_id": str(record.id)}, f"process_mining.conformance:{idempotency_key}")
            record.async_job_id = job.id
            record.save(update_fields=["async_job_id", "updated_at"])
        return record

    def run_check(self, tenant_id: UUID, check_id: UUID, async_job_id: UUID) -> ConformanceCheck:
        tenant_id = _tenant(tenant_id)
        configuration = _configuration(tenant_id)
        record = _get(ConformanceCheck, tenant_id, check_id, active=True)
        if record.status == AnalysisStatus.COMPLETED:
            return record
        if record.async_job_id != async_job_id:
            raise NotFound()
        record = _workflow_machine(tenant_id, "conformance").apply(record, "start", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:start", metadata=_audit(record.created_by, "Conformance worker started"))
        try:
            version = record.process_model_version
            rows = _filter_events(tenant_id, version.process_model.process_name, record.event_filter)
            algorithm = registry.get("process_mining.token_replay")
            if not isinstance(algorithm, ConformanceAlgorithm):
                raise CapabilityUnavailable(capability="conformance:token_replay")
            result = algorithm.evaluate(version.model_data, _traces(rows))
            conformant = sum(item.is_conformant for item in result.cases)
            with transaction.atomic():
                ConformanceCaseMetric.objects.bulk_create([ConformanceCaseMetric(tenant_id=tenant_id, created_by=record.created_by, conformance_check=record, case_id=item.case_id, fitness=item.fitness, is_conformant=item.is_conformant, deviation_count=item.deviation_count, trace_length=item.trace_length) for item in result.cases], ignore_conflicts=True)
                ConformanceDeviation.objects.bulk_create([ConformanceDeviation(tenant_id=tenant_id, created_by=record.created_by, conformance_check=record, case_id=item.case_id, deviation_type=item.deviation_type, expected=item.expected, actual=item.actual, position=item.position, description=item.description) for item in result.deviations], ignore_conflicts=True)
                ConformanceCheck.objects.for_tenant(tenant_id).filter(pk=record.id).update(fitness=result.fitness, precision=result.precision, generalization=result.generalization, total_cases=len(result.cases), conformant_cases=conformant, deviating_cases=len(result.cases) - conformant, completed_at=timezone.now(), error_code="", error_message="")
                record = ConformanceCheck.objects.for_tenant(tenant_id).get(pk=record.id)
                record = _workflow_machine(tenant_id, "conformance").apply(record, "complete", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:complete", metadata=_audit(record.created_by, "Conformance evidence persisted"))
                _publish(tenant_id, "conformance_check", record.id, "process.conformance.completed", {"check_id": str(record.id), "fitness": str(record.fitness), "total_cases": record.total_cases})
                if record.fitness is not None and record.fitness < Decimal(str(configuration["low_fitness_threshold"])):
                    _publish(tenant_id, "conformance_check", record.id, "process.conformance.low_fitness", {"check_id": str(record.id), "fitness": str(record.fitness), "notification_contract": "notification.requested.v1"})
            return record
        except Exception as exc:
            ConformanceCheck.objects.for_tenant(tenant_id).filter(pk=record.id).update(error_code="CONFORMANCE_FAILED", error_message="Conformance evaluation could not complete.", completed_at=timezone.now())
            fresh = ConformanceCheck.objects.for_tenant(tenant_id).get(pk=record.id)
            if fresh.status == AnalysisStatus.RUNNING:
                _workflow_machine(tenant_id, "conformance").apply(fresh, "fail", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:fail", metadata=_audit(fresh.created_by, "Conformance failed"))
            raise OperationFailed(error_code="CONFORMANCE_FAILED", message="Conformance evaluation failed.") from exc

    def list_deviations(self, tenant_id: UUID, check_id: UUID, filters: Mapping[str, object]) -> QuerySet[ConformanceDeviation]:
        check = _get(ConformanceCheck, _tenant(tenant_id), check_id, active=True)
        queryset = ConformanceDeviation.objects.for_tenant(check.tenant_id).filter(conformance_check=check)
        for field in ("deviation_type", "case_id", "position"):
            if filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return queryset.order_by("case_id", "position", "id")

    def get_fitness(self, tenant_id: UUID, check_id: UUID) -> tuple[ConformanceCheck, QuerySet[ConformanceCaseMetric]]:
        check = _get(ConformanceCheck, _tenant(tenant_id), check_id, active=True)
        return check, ConformanceCaseMetric.objects.for_tenant(check.tenant_id).filter(conformance_check=check).order_by("fitness", "case_id")

    def _transition(self, tenant_id: UUID, check_id: UUID, actor_id: UUID, command: str, transition_key: str, reason: str = "") -> ConformanceCheck:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(ConformanceCheck, tenant_id, check_id, active=True)
        return _workflow_machine(tenant_id, "conformance").apply(record, command, tenant_id=tenant_id, transition_key=_required_text(transition_key, "transition_key", int(_configuration(tenant_id)["text_max_length"])), metadata=_audit(actor_id, reason or f"Conformance {command}"))

    def cancel_check(self, tenant_id: UUID, check_id: UUID, actor_id: UUID, transition_key: str, reason: str = "") -> ConformanceCheck:
        return self._transition(tenant_id, check_id, actor_id, "cancel", transition_key, reason)

    def retry_check(self, tenant_id: UUID, check_id: UUID, actor_id: UUID, transition_key: str, idempotency_key: str) -> ConformanceCheck:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = self._transition(tenant_id, check_id, actor_id, "retry", transition_key)
        job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.check_conformance", {"check_id": str(record.id)}, _required_text(idempotency_key, "idempotency_key", int(_configuration(tenant_id)["text_max_length"])))
        record.async_job_id = job.id
        record.save(update_fields=["async_job_id", "updated_at"])
        return record

    def delete_check(self, tenant_id: UUID, check_id: UUID, actor_id: UUID) -> None:
        tenant_id, _actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(ConformanceCheck, tenant_id, check_id, active=True)
        if record.status not in set(_configuration(tenant_id)["analysis_terminal_states"]):
            raise ValidationError({"status": "Only terminal checks can be deleted."})
        ConformanceCheck.objects.for_tenant(tenant_id).filter(pk=record.id).update(is_deleted=True, deleted_at=timezone.now())


class BottleneckService:
    def request_analysis(self, tenant_id: UUID, actor_id: UUID, process_name: str, time_range: tuple[datetime, datetime], idempotency_key: str) -> BottleneckAnalysis:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        configuration = _configuration(tenant_id)
        limit = int(configuration["text_max_length"])
        process_name, idempotency_key = _required_text(process_name, "process_name", limit), _required_text(idempotency_key, "idempotency_key", limit)
        start, end = (_aware_datetime(time_range[0], "time_range_start"), _aware_datetime(time_range[1], "time_range_end"))
        if end <= start:
            raise ValidationError({"time_range_end": "End must follow start."})
        exact = BottleneckAnalysis.objects.for_tenant(tenant_id).filter(process_name=process_name, time_range_start=start, time_range_end=end, status=AnalysisStatus.COMPLETED, completed_at__gte=timezone.now() - timedelta(minutes=int(configuration["bottleneck_reuse_minutes"])), is_deleted=False).order_by("-completed_at").first()
        if exact:
            return exact
        existing = BottleneckAnalysis.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        events = ProcessEvent.objects.for_tenant(tenant_id).filter(process_name=process_name, occurred_at__gte=start, occurred_at__lte=end)
        minimum_cases = int(configuration["bottleneck_min_cases"])
        if events.values("case_id").distinct().count() < minimum_cases:
            raise ValidationError({"process_name": f"Bottleneck analysis requires at least {minimum_cases} cases."})
        with transaction.atomic():
            record = BottleneckAnalysis.objects.create(tenant_id=tenant_id, created_by=actor_id, process_name=process_name, time_range_start=start, time_range_end=end, idempotency_key=idempotency_key)
            job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.analyze_bottlenecks", {"analysis_id": str(record.id)}, f"process_mining.bottleneck:{idempotency_key}")
            record.async_job_id = job.id
            record.save(update_fields=["async_job_id", "updated_at"])
        return record

    def run_analysis(self, tenant_id: UUID, analysis_id: UUID, async_job_id: UUID) -> BottleneckAnalysis:
        tenant_id = _tenant(tenant_id)
        configuration = _configuration(tenant_id)
        record = _get(BottleneckAnalysis, tenant_id, analysis_id, active=True)
        if record.status == AnalysisStatus.COMPLETED:
            return record
        if record.async_job_id != async_job_id:
            raise NotFound()
        record = _workflow_machine(tenant_id, "bottleneck").apply(record, "start", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:start", metadata=_audit(record.created_by, "Bottleneck worker started"))
        try:
            rows = ProcessEvent.objects.for_tenant(tenant_id).filter(process_name=record.process_name, occurred_at__gte=record.time_range_start, occurred_at__lte=record.time_range_end).order_by("case_id", "occurred_at", "source_event_id", "activity", "id")
            algorithm = registry.get("process_mining.transition_duration")
            if not isinstance(algorithm, BottleneckAlgorithm):
                raise CapabilityUnavailable(capability="bottleneck:transition_duration")
            result = algorithm.analyze(_traces(rows), (record.time_range_start, record.time_range_end), configuration)
            with transaction.atomic():
                BottleneckFinding.objects.bulk_create([BottleneckFinding(tenant_id=tenant_id, created_by=record.created_by, analysis=record, **dict(item)) for item in result.findings], ignore_conflicts=True)
                ProcessVariant.objects.bulk_create([ProcessVariant(tenant_id=tenant_id, created_by=record.created_by, analysis=record, **dict(item)) for item in result.variants], ignore_conflicts=True)
                BottleneckAnalysis.objects.for_tenant(tenant_id).filter(pk=record.id).update(total_cases=result.total_cases, total_variants=len(result.variants), avg_case_duration_seconds=result.average_case_duration_seconds, completed_at=timezone.now(), error_code="", error_message="")
                record = BottleneckAnalysis.objects.for_tenant(tenant_id).get(pk=record.id)
                record = _workflow_machine(tenant_id, "bottleneck").apply(record, "complete", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:complete", metadata=_audit(record.created_by, "Bottleneck evidence persisted"))
                critical = sum(item.get("severity") == "critical" for item in result.findings)
                if result.findings:
                    _publish(tenant_id, "bottleneck_analysis", record.id, "process.bottleneck.detected", {"analysis_id": str(record.id), "finding_count": len(result.findings), "critical_count": critical})
                _publish(tenant_id, "bottleneck_analysis", record.id, "process.variant.analysis_completed", {"analysis_id": str(record.id), "variant_count": len(result.variants)})
            return record
        except Exception as exc:
            BottleneckAnalysis.objects.for_tenant(tenant_id).filter(pk=record.id).update(error_code="BOTTLENECK_FAILED", error_message="Bottleneck analysis could not complete.", completed_at=timezone.now())
            fresh = BottleneckAnalysis.objects.for_tenant(tenant_id).get(pk=record.id)
            if fresh.status == AnalysisStatus.RUNNING:
                _workflow_machine(tenant_id, "bottleneck").apply(fresh, "fail", tenant_id=tenant_id, transition_key=f"worker:{async_job_id}:fail", metadata=_audit(fresh.created_by, "Bottleneck analysis failed"))
            raise OperationFailed(error_code="BOTTLENECK_FAILED", message="Bottleneck analysis failed.") from exc

    def get_variants(self, tenant_id: UUID, analysis_id: UUID, filters: Mapping[str, object]) -> QuerySet[ProcessVariant]:
        analysis = _get(BottleneckAnalysis, _tenant(tenant_id), analysis_id, active=True)
        queryset = ProcessVariant.objects.for_tenant(analysis.tenant_id).filter(analysis=analysis)
        if filters.get("is_happy_path") is not None:
            queryset = queryset.filter(is_happy_path=str(filters["is_happy_path"]).lower() in {"1", "true"})
        if filters.get("is_grouped_other") is not None:
            queryset = queryset.filter(is_grouped_other=str(filters["is_grouped_other"]).lower() in {"1", "true"})
        ordering = str(filters.get("ordering") or "-case_count")
        if ordering.lstrip("-") not in {"case_count", "percentage", "avg_duration_seconds"}:
            raise ValidationError({"ordering": "Unsupported variant ordering."})
        return queryset.order_by(ordering, "id")

    def get_findings(self, tenant_id: UUID, analysis_id: UUID, filters: Mapping[str, object]) -> QuerySet[BottleneckFinding]:
        analysis = _get(BottleneckAnalysis, _tenant(tenant_id), analysis_id, active=True)
        queryset = BottleneckFinding.objects.for_tenant(analysis.tenant_id).filter(analysis=analysis)
        if filters.get("severity"):
            queryset = queryset.filter(severity=filters["severity"])
        if filters.get("resource"):
            queryset = queryset.filter(resource_bottleneck=filters["resource"])
        ordering = str(filters.get("ordering") or "rank")
        if ordering.lstrip("-") not in {"rank"}:
            raise ValidationError({"ordering": "Only rank ordering is supported."})
        return queryset.order_by(ordering, "id")

    def _transition(self, tenant_id: UUID, analysis_id: UUID, actor_id: UUID, command: str, transition_key: str, reason: str = "") -> BottleneckAnalysis:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(BottleneckAnalysis, tenant_id, analysis_id, active=True)
        return _workflow_machine(tenant_id, "bottleneck").apply(record, command, tenant_id=tenant_id, transition_key=_required_text(transition_key, "transition_key", int(_configuration(tenant_id)["text_max_length"])), metadata=_audit(actor_id, reason or f"Bottleneck {command}"))

    def cancel_analysis(self, tenant_id: UUID, analysis_id: UUID, actor_id: UUID, transition_key: str, reason: str = "") -> BottleneckAnalysis:
        return self._transition(tenant_id, analysis_id, actor_id, "cancel", transition_key, reason)

    def retry_analysis(self, tenant_id: UUID, analysis_id: UUID, actor_id: UUID, transition_key: str, idempotency_key: str) -> BottleneckAnalysis:
        tenant_id, actor_id = _tenant(tenant_id), _actor(actor_id)
        record = self._transition(tenant_id, analysis_id, actor_id, "retry", transition_key)
        job = _enqueue_or_unavailable(tenant_id, actor_id, "process_mining.analyze_bottlenecks", {"analysis_id": str(record.id)}, _required_text(idempotency_key, "idempotency_key", int(_configuration(tenant_id)["text_max_length"])))
        record.async_job_id = job.id
        record.save(update_fields=["async_job_id", "updated_at"])
        return record

    def delete_analysis(self, tenant_id: UUID, analysis_id: UUID, actor_id: UUID) -> None:
        tenant_id, _actor_id = _tenant(tenant_id), _actor(actor_id)
        record = _get(BottleneckAnalysis, tenant_id, analysis_id, active=True)
        if record.status not in set(_configuration(tenant_id)["analysis_terminal_states"]):
            raise ValidationError({"status": "Only terminal analyses can be deleted."})
        BottleneckAnalysis.objects.for_tenant(tenant_id).filter(pk=record.id).update(is_deleted=True, deleted_at=timezone.now())


__all__ = [
    "BottleneckService", "ConformanceService", "EventLogService", "ExportService",
    "IngestResult", "IngestRowEvidence", "ProcessDiscoveryService",
    "ProcessMiningConfigurationService", "ProcessMiningQueryService", "ProcessModelService",
]
