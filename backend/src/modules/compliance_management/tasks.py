"""Durable compliance command handlers and tenant-bound worker entry points."""

from __future__ import annotations

import uuid
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from django.contrib.auth import get_user_model

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import register_handler
from src.core.tenancy import tenant_context_worker

IMPORT_FRAMEWORK_COMMAND = "compliance_management.import_framework"
IMPORT_REQUIREMENTS_COMMAND = "compliance_management.import_requirements"
EXPORT_WORKSPACE_COMMAND = "compliance_management.export_workspace"
COLLECT_EVIDENCE_COMMAND = "compliance_management.collect_evidence"
COMMANDS = (
    IMPORT_FRAMEWORK_COMMAND,
    IMPORT_REQUIREMENTS_COMMAND,
    EXPORT_WORKSPACE_COMMAND,
    COLLECT_EVIDENCE_COMMAND,
)


class ComplianceJobPayloadError(ValueError):
    """Raised when a durable job contains an invalid command payload."""


class ComplianceJobCapabilityUnavailable(RuntimeError):
    """Raised instead of fabricating an async result for an absent capability."""

    code = "CAPABILITY_UNAVAILABLE"


def _uuid(value: object, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ComplianceJobPayloadError(f"{field_name} must be a valid UUID") from exc


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ComplianceJobPayloadError(f"{field_name} must be an object")
    return {str(key): item for key, item in value.items()}


def _rows(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ComplianceJobPayloadError("rows must be an array")
    return [_mapping(row, f"rows[{index}]") for index, row in enumerate(value)]


def _actor(actor_id: object) -> object:
    """Resolve the durable actor identity; deleted actors fail explicitly."""

    user_model = get_user_model()
    try:
        return user_model._default_manager.get(pk=actor_id)
    except (user_model.DoesNotExist, ValueError, TypeError) as exc:
        raise ComplianceJobPayloadError("job actor no longer exists") from exc


def _result_identity(value: object) -> dict[str, Any]:
    entity_id = getattr(value, "id", None)
    if entity_id is None:
        raise RuntimeError("compliance service returned an invalid persisted result")
    result: dict[str, Any] = {"id": str(entity_id)}
    status = getattr(value, "status", None)
    if isinstance(status, str):
        result["status"] = status
    return result


def _json_value(value: object) -> Any:
    if isinstance(value, (uuid.UUID, date, datetime)):
        return value.isoformat() if not isinstance(value, uuid.UUID) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return value


def _export_rows(model: object, tenant_id: uuid.UUID, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    manager = getattr(model, "objects")
    queryset = manager.for_tenant(tenant_id).order_by("id").values(*fields)
    return [{key: _json_value(value) for key, value in row.items()} for row in queryset]


def _export_workspace(tenant_id: uuid.UUID, job_id: uuid.UUID, options: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic, complete tenant workspace document.

    Soft-deleted and immutable historical records are intentionally retained so
    extension removal or license expiry can never make OSS-owned data unreadable.
    """

    from .models import (
        ComplianceActivity,
        ComplianceAssessment,
        ComplianceConfigurationRevision,
        ComplianceEvidence,
        ComplianceFramework,
        CompliancePolicy,
        CompliancePolicyVersion,
        ComplianceRequirement,
        EvidenceRequirementLink,
        RequirementPolicyMapping,
    )

    if options and set(options) - {"include_activity"}:
        raise ComplianceJobPayloadError("workspace export options contain unsupported fields")
    include_activity = options.get("include_activity", True)
    if not isinstance(include_activity, bool):
        raise ComplianceJobPayloadError("include_activity must be a boolean")

    document: dict[str, Any] = {
        "schema": "saraise.compliance.workspace",
        "schema_version": "1.0.0",
        "export_id": str(job_id),
        "frameworks": _export_rows(
            ComplianceFramework,
            tenant_id,
            ("id", "code", "name", "version", "category", "description", "source_kind", "source_package", "source_version", "status", "transition_history", "created_at", "updated_at", "deleted_at"),
        ),
        "requirements": _export_rows(
            ComplianceRequirement,
            tenant_id,
            ("id", "framework_id", "code", "title", "description", "section", "guidance", "applicability", "applicability_rationale", "status", "sort_order", "tags", "transition_history", "created_at", "updated_at", "deleted_at"),
        ),
        "policies": _export_rows(
            CompliancePolicy,
            tenant_id,
            ("id", "code", "title", "summary", "category", "owner_id", "review_frequency_days", "effective_date", "expiry_date", "next_review_date", "status", "current_version", "transition_history", "created_at", "updated_at", "deleted_at"),
        ),
        "policy_versions": _export_rows(
            CompliancePolicyVersion,
            tenant_id,
            ("id", "policy_id", "version", "content", "content_sha256", "change_summary", "created_by_id", "created_at", "approved_by_id", "approved_at", "published_by_id", "published_at"),
        ),
        "mappings": _export_rows(
            RequirementPolicyMapping,
            tenant_id,
            ("id", "requirement_id", "policy_id", "policy_version_id", "coverage", "rationale", "mapped_at", "created_at", "updated_at", "deleted_at"),
        ),
        "assessments": _export_rows(
            ComplianceAssessment,
            tenant_id,
            ("id", "requirement_id", "mapping_id", "status", "assessor_id", "assessed_at", "due_date", "notes", "source", "created_at"),
        ),
        "evidence": _export_rows(
            ComplianceEvidence,
            tenant_id,
            ("id", "name", "description", "evidence_type", "reference_kind", "document_id", "external_uri", "text_reference", "sha256", "classification", "collection_method", "valid_from", "valid_until", "collected_by_id", "collected_at", "created_at", "updated_at", "deleted_at"),
        ),
        "evidence_links": _export_rows(
            EvidenceRequirementLink,
            tenant_id,
            ("id", "evidence_id", "requirement_id", "relevance", "notes", "created_by_id", "created_at"),
        ),
        "configuration_revisions": _export_rows(
            ComplianceConfigurationRevision,
            tenant_id,
            ("id", "environment", "version", "status", "policy_code_prefix", "default_review_frequency_days", "expiry_warning_days", "evidence_warning_days", "minimum_assessment_note_length", "allow_external_evidence_urls", "bulk_import_row_limit", "regulation_categories", "rollout", "created_by_id", "created_at", "activated_by_id", "activated_at", "transition_history"),
        ),
    }
    if include_activity:
        document["activity"] = _export_rows(
            ComplianceActivity,
            tenant_id,
            ("id", "entity_type", "entity_id", "action", "actor_id", "correlation_id", "before", "after", "reason", "occurred_at"),
        )
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "artifact": document,
        "content_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "media_type": "application/vnd.saraise.compliance-workspace+json",
    }


@tenant_context_worker
def import_framework_worker(
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    actor_id: object,
    package: Mapping[str, Any],
    correlation_id: str,
) -> dict[str, Any]:
    from .services import FrameworkService

    framework = FrameworkService.import_framework(
        tenant_id,
        _actor(actor_id),
        dict(package),
        str(job_id),
        correlation_id,
    )
    return _result_identity(framework)


@tenant_context_worker
def import_requirements_worker(
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    actor_id: object,
    framework_id: uuid.UUID,
    rows: list[dict[str, Any]],
    correlation_id: str,
) -> dict[str, Any]:
    from .services import RequirementService

    imported = RequirementService.bulk_import(
        tenant_id,
        _actor(actor_id),
        framework_id,
        rows,
        str(job_id),
        correlation_id,
    )
    if isinstance(imported, Mapping):
        result = dict(imported)
        if not result:
            raise RuntimeError("requirement import returned no durable outcome")
        return result
    if isinstance(imported, Sequence) and not isinstance(imported, (str, bytes, bytearray)):
        return {"requirement_ids": [str(getattr(item, "id")) for item in imported]}
    raise RuntimeError("requirement import returned an invalid durable outcome")


@tenant_context_worker
def export_workspace_worker(
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    actor_id: object,
    correlation_id: str,
    options: Mapping[str, Any],
) -> dict[str, Any]:
    del actor_id, correlation_id
    return _export_workspace(tenant_id, job_id, options)


@tenant_context_worker
def collect_evidence_worker(
    *,
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    actor_id: object,
    correlation_id: str,
    extension_id: str,
    request_data: Mapping[str, Any],
) -> dict[str, Any]:
    from .extension_contracts import EvidenceCollectionRequest, extension_registry

    request = EvidenceCollectionRequest(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        actor_id=str(getattr(_actor(actor_id), "pk")),
        idempotency_key=str(job_id),
        parameters=dict(request_data),
    )
    result = extension_registry.collect_evidence(extension_id, request)
    return result.as_dict()


def _assert_job(job: AsyncJob, command: str) -> None:
    if not isinstance(job, AsyncJob) or job.command != command:
        raise ComplianceJobPayloadError(f"handler requires durable command {command}")


@register_handler(IMPORT_FRAMEWORK_COMMAND)
def import_framework_handler(job: AsyncJob) -> dict[str, Any]:
    _assert_job(job, IMPORT_FRAMEWORK_COMMAND)
    return import_framework_worker(
        tenant_id=job.tenant_id,
        job_id=job.id,
        actor_id=job.actor_id,
        package=_mapping(job.payload.get("package"), "package"),
        correlation_id=job.correlation_id,
    )


@register_handler(IMPORT_REQUIREMENTS_COMMAND)
def import_requirements_handler(job: AsyncJob) -> dict[str, Any]:
    _assert_job(job, IMPORT_REQUIREMENTS_COMMAND)
    return import_requirements_worker(
        tenant_id=job.tenant_id,
        job_id=job.id,
        actor_id=job.actor_id,
        framework_id=_uuid(job.payload.get("framework_id"), "framework_id"),
        rows=_rows(job.payload.get("rows")),
        correlation_id=job.correlation_id,
    )


@register_handler(EXPORT_WORKSPACE_COMMAND)
def export_workspace_handler(job: AsyncJob) -> dict[str, Any]:
    _assert_job(job, EXPORT_WORKSPACE_COMMAND)
    return export_workspace_worker(
        tenant_id=job.tenant_id,
        job_id=job.id,
        actor_id=job.actor_id,
        correlation_id=job.correlation_id,
        options=_mapping(job.payload.get("options", {}), "options"),
    )


@register_handler(COLLECT_EVIDENCE_COMMAND)
def collect_evidence_handler(job: AsyncJob) -> dict[str, Any]:
    _assert_job(job, COLLECT_EVIDENCE_COMMAND)
    extension_id = job.payload.get("extension_id")
    if not isinstance(extension_id, str) or not extension_id.strip():
        raise ComplianceJobPayloadError("extension_id must be a nonblank namespaced identifier")
    return collect_evidence_worker(
        tenant_id=job.tenant_id,
        job_id=job.id,
        actor_id=job.actor_id,
        correlation_id=job.correlation_id,
        extension_id=extension_id.strip(),
        request_data=_mapping(job.payload.get("request", {}), "request"),
    )


__all__ = [
    "COLLECT_EVIDENCE_COMMAND",
    "COMMANDS",
    "EXPORT_WORKSPACE_COMMAND",
    "IMPORT_FRAMEWORK_COMMAND",
    "IMPORT_REQUIREMENTS_COMMAND",
    "collect_evidence_handler",
    "collect_evidence_worker",
    "export_workspace_handler",
    "export_workspace_worker",
    "import_framework_handler",
    "import_framework_worker",
    "import_requirements_handler",
    "import_requirements_worker",
]
