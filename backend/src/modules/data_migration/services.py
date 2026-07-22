"""Tenant-safe business services for durable data migration.

HTTP views are intentionally thin clients of this module.  Every mutating
operation establishes the tenant boundary again, locks its aggregate, records
immutable evidence, and emits an outbox event in the same transaction.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence
from uuid import UUID
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.exceptions import NotFound

from src.core.async_jobs.models import AsyncJob
from src.core.async_jobs.services import enqueue
from src.core.middleware.correlation import get_correlation_id

from .adapters import SOURCE_ADAPTERS, TARGET_ADAPTERS
from .events import publish_event
from .models import (
    DataMigrationConfiguration,
    DataMigrationConfigurationAudit,
    ExternalConnection,
    MigrationChange,
    MigrationJob,
    MigrationJobVersion,
    MigrationMapping,
    MigrationRollback,
    MigrationRun,
    MigrationRunIssue,
    ValidationRule,
)
from .schemas import validate_rule_config, validate_source_config, validate_transform_config
from .state_machines import JOB_MACHINE, ROLLBACK_MACHINE, RUN_MACHINE

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PII_KEYS = frozenset({"password", "secret", "token", "authorization", "email", "phone", "ssn", "address"})


class MigrationServiceError(RuntimeError):
    """Stable service failure carrying a machine-readable error code."""

    def __init__(self, message: str, *, code: str = "DATA_MIGRATION_ERROR") -> None:
        super().__init__(message)
        self.code = code


class ConfigurationConflict(MigrationServiceError):
    def __init__(self) -> None:
        super().__init__("The migration definition changed; reload and compare before retrying.", code="VERSION_CONFLICT")


class CapabilityUnavailable(MigrationServiceError):
    def __init__(self, capability: str) -> None:
        super().__init__(f"Capability {capability!r} is not installed or available.", code="CAPABILITY_UNAVAILABLE")


@dataclass(frozen=True, slots=True)
class DefinitionValidationResult:
    valid: bool
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    rule_id: UUID
    field_name: str
    severity: str
    passed: bool
    code: str
    message: str
    row_number: int


@dataclass(frozen=True, slots=True)
class SourceProfile:
    fields: tuple[dict[str, object], ...]
    representative_values: tuple[dict[str, object], ...]
    row_estimate: int
    source_checksum: str
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PreviewResult:
    records: tuple[dict[str, object], ...]
    source_checksum: str
    truncated: bool


def _uuid(value: object, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise MigrationServiceError(f"{field} must be a canonical UUID", code="INVALID_ARGUMENT") from exc


def _text(value: object, field: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationServiceError(f"{field} is required", code="INVALID_ARGUMENT")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise MigrationServiceError(f"{field} must not exceed {maximum} characters", code="INVALID_ARGUMENT")
    return normalized


def _correlation(value: str | None = None) -> str:
    return _text(value or get_correlation_id() or str(uuid.uuid4()), "correlation_id", 128)


def _destination_allowlist(kind: str) -> set[str]:
    key = "DATA_MIGRATION_ALLOWED_HTTP_HOSTS" if kind == "http" else "DATA_MIGRATION_ALLOWED_DB_HOSTS"
    return {item.strip().lower() for item in os.environ.get(key, "").split(",") if item.strip()}


def _validated_external_hostaddr(host: str, *, kind: str = "database") -> str:
    """Return a DNS-pinned public address for an explicitly allow-listed host."""
    if not isinstance(host, str) or host != host.strip() or not host or any(token in host for token in ("/", ",", "\x00")):
        raise ValueError("External destination host is not canonical")
    normalized = host.lower()
    if normalized not in _destination_allowlist(kind):
        raise ValueError("External destination is not allow-listed")
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(normalized, None)}
    except (socket.gaierror, ValueError) as exc:
        raise ValueError("External destination could not be resolved") from exc
    if not addresses:
        raise ValueError("External destination could not be resolved")
    for address in addresses:
        if address.is_loopback or address.is_link_local or address.is_private or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise ValueError("External destination resolves to an internal or non-routable address")
    return str(min(addresses, key=lambda item: (item.version, int(item))))


def _validate_connection_destination(values: Mapping[str, object]) -> None:
    kind = str(values.get("kind", ""))
    if kind == "http":
        parsed = urlsplit(str(values.get("base_url", "")))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise MigrationServiceError("HTTP connections require a canonical HTTPS base URL without credentials.", code="DENIED_DESTINATION")
        _validated_external_hostaddr(parsed.hostname, kind="http")
    elif kind in {"postgresql", "mysql"}:
        _validated_external_hostaddr(str(values.get("host", "")), kind="database")
    else:
        raise MigrationServiceError("Unsupported external connection kind.", code="INVALID_CONNECTION")


def _job(tenant_id: UUID, job_id: object, *, lock: bool = False, include_deleted: bool = False) -> MigrationJob:
    query = MigrationJob.objects.for_tenant(tenant_id)
    if lock:
        query = query.select_for_update()
    if not include_deleted:
        query = query.filter(is_deleted=False)
    result = query.filter(pk=job_id).first()
    if result is None:
        raise NotFound("Migration job not found.")
    return result


def _safe_snapshot(job: MigrationJob) -> dict[str, object]:
    return {
        "schema_version": 1,
        "job_id": str(job.id),
        "tenant_id": str(job.tenant_id),
        "name": job.name,
        "description": job.description,
        "source_type": job.source_type,
        "source_artifact_id": str(job.source_artifact_id) if job.source_artifact_id else None,
        "source_config": job.source_config,
        "target_adapter": job.target_adapter,
        "target_entity": job.target_entity,
        "write_mode": job.write_mode,
        "lookup_fields": job.lookup_fields,
        "mappings": [
            {
                "source_field": item.source_field,
                "target_field": item.target_field,
                "position": item.position,
                "transform_type": item.transform_type,
                "transform_config": item.transform_config,
                "is_required": item.is_required,
                "origin": item.origin,
                "confidence": str(item.confidence) if item.confidence is not None else None,
            }
            for item in job.mappings.order_by("position", "id")
        ],
        "rules": [
            {
                "field_name": item.field_name,
                "rule_type": item.rule_type,
                "rule_config": item.rule_config,
                "error_message": item.error_message,
                "severity": item.severity,
                "position": item.position,
                "is_active": item.is_active,
            }
            for item in job.validation_rules.order_by("position", "id")
        ],
    }


def _snapshot_checksum(document: Mapping[str, object]) -> str:
    sanitized = {key: value for key, value in document.items() if key != "checksum"}
    return hashlib.sha256(json.dumps(sanitized, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _version(job: MigrationJob, actor_id: UUID, correlation_id: str, summary: str) -> MigrationJobVersion:
    snapshot = _safe_snapshot(job)
    return MigrationJobVersion.objects.create(
        tenant_id=job.tenant_id,
        job=job,
        version=job.configuration_version,
        snapshot=snapshot,
        change_summary=summary[:500],
        created_by=actor_id,
        correlation_id=correlation_id,
    )


def _redact(record: Mapping[str, object], limit: int = 12) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in list(record.items())[:limit]:
        lowered = key.lower()
        if any(marker in lowered for marker in PII_KEYS):
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 120:
            redacted[key] = value[:117] + "..."
        else:
            redacted[key] = value
    return redacted


def _configuration(tenant_id: UUID) -> DataMigrationConfiguration:
    with transaction.atomic():
        config, created = DataMigrationConfiguration.objects.get_or_create(
            tenant_id=tenant_id,
            defaults={"created_by": uuid.UUID(int=0)},
        )
        if created:
            DataMigrationConfigurationAudit.objects.create(
                tenant_id=tenant_id,
                configuration=config,
                version=1,
                before={},
                after=config.as_document(),
                changed_by=uuid.UUID(int=0),
                correlation_id=_correlation(),
            )
    return config


def _source_adapter(key: str) -> object:
    try:
        return SOURCE_ADAPTERS.get(key)
    except LookupError as exc:
        raise CapabilityUnavailable(key) from exc


def _target_adapter(key: str) -> object:
    try:
        return TARGET_ADAPTERS.get(key)
    except LookupError as exc:
        raise CapabilityUnavailable(key) from exc


def _enforce_runtime_policy(tenant: UUID, target_adapter: str) -> DataMigrationConfiguration:
    config = _configuration(tenant)
    if not config.enabled:
        raise CapabilityUnavailable("data_migration.core")
    cohort = int(hashlib.sha256(tenant.bytes).hexdigest()[:8], 16) % 100
    if cohort >= config.rollout_percentage:
        raise CapabilityUnavailable("data_migration.core.rollout")
    if target_adapter not in config.allowed_target_adapters:
        raise CapabilityUnavailable(target_adapter)
    return config


def _validate_source_reference(tenant: UUID, actor: UUID, source_type: str, source_config: Mapping[str, object], artifact_id: object | None) -> None:
    """Resolve every source reference through its owning service boundary."""
    if source_type in {"database", "api"}:
        connection_id = source_config.get("connection_id")
        if not ExternalConnection.objects.for_tenant(tenant).filter(pk=connection_id, is_active=True).exists():
            raise MigrationServiceError("Active source connection not found for tenant.", code="INVALID_SOURCE_REFERENCE")
    elif source_type in {"csv", "excel", "json", "xml"}:
        if artifact_id is None:
            raise MigrationServiceError("File sources require a DMS artifact version.", code="INVALID_SOURCE_REFERENCE")
        from src.modules.dms.services import VersionService

        try:
            VersionService().get_version(tenant, actor, _uuid(artifact_id, "source_artifact_id"))
        except Exception as exc:
            raise MigrationServiceError("Source artifact is unavailable to this tenant.", code="INVALID_SOURCE_REFERENCE") from exc


class ExternalConnectionService:
    """Manage safe references; credentials remain in the approved secret store."""

    @staticmethod
    @transaction.atomic
    def register(tenant_id: object, actor_id: object, payload: Mapping[str, object]) -> ExternalConnection:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        values = dict(payload)
        values.pop("tenant_id", None)
        if any(key in values for key in ("password", "token", "secret")):
            raise MigrationServiceError("Secret material is forbidden; provide credential_ref.", code="SECRET_MATERIAL_FORBIDDEN")
        _validate_connection_destination(values)
        connection = ExternalConnection(tenant_id=tenant, created_by=actor, **values)
        connection.full_clean()
        connection.save()
        return connection

    @staticmethod
    @transaction.atomic
    def update(tenant_id: object, connection_id: object, actor_id: object, payload: Mapping[str, object]) -> ExternalConnection:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        connection = ExternalConnection.objects.for_tenant(tenant).select_for_update().filter(pk=connection_id).first()
        if connection is None:
            raise NotFound("External connection not found.")
        immutable = {"id", "tenant_id", "created_by", "credential_ref"}
        if set(payload) & immutable:
            raise MigrationServiceError("Immutable connection fields cannot be updated.", code="IMMUTABLE_FIELD")
        for field, value in payload.items():
            setattr(connection, field, value)
        connection.updated_by = actor
        _validate_connection_destination({field.name: getattr(connection, field.name) for field in connection._meta.fields})
        connection.full_clean()
        connection.save()
        return connection

    @staticmethod
    @transaction.atomic
    def rotate_credential(tenant_id: object, connection_id: object, actor_id: object, credential_ref: str) -> ExternalConnection:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        connection = ExternalConnection.objects.for_tenant(tenant).select_for_update().filter(pk=connection_id).first()
        if connection is None:
            raise NotFound("External connection not found.")
        connection.credential_ref = _text(credential_ref, "credential_ref")
        connection.updated_by = actor
        connection.full_clean()
        connection.save(update_fields=("credential_ref", "updated_by", "updated_at"))
        return connection

    @staticmethod
    @transaction.atomic
    def deactivate(tenant_id: object, connection_id: object, actor_id: object) -> ExternalConnection:
        return ExternalConnectionService.update(tenant_id, connection_id, actor_id, {"is_active": False})

    @staticmethod
    def list_references(tenant_id: object) -> QuerySet[ExternalConnection]:
        return ExternalConnection.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(is_active=True).order_by("name")

    @staticmethod
    def test(tenant_id: object, connection_id: object, actor_id: object) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        _uuid(actor_id, "actor_id")
        connection = ExternalConnection.objects.for_tenant(tenant).filter(pk=connection_id, is_active=True).first()
        if connection is None:
            raise NotFound("Active external connection not found.")
        # Providers register a source adapter that performs the smallest verified read.
        key = "core.api" if connection.kind == "http" else "core.database"
        try:
            adapter = SOURCE_ADAPTERS.get(key)
        except LookupError as exc:
            raise CapabilityUnavailable(f"{key}.connection_test") from exc
        if not hasattr(adapter, "test_connection"):
            raise CapabilityUnavailable(f"{key}.connection_test")
        evidence = adapter.test_connection(connection)
        if not evidence or not evidence.get("verified"):
            raise MigrationServiceError("Connection test returned no verified evidence.", code="UNVERIFIED_CONNECTION")
        return dict(evidence)


class MigrationJobService:
    @staticmethod
    @transaction.atomic
    def create(tenant_id: object, actor_id: object, command: Mapping[str, object]) -> MigrationJob:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        values = dict(command)
        values.pop("tenant_id", None)
        source_type = _text(values.get("source_type"), "source_type", 20)
        values["source_config"] = validate_source_config(source_type, values.get("source_config", {}))
        _validate_source_reference(tenant, actor, source_type, values["source_config"], values.get("source_artifact_id"))
        _enforce_runtime_policy(tenant, _text(values.get("target_adapter"), "target_adapter", 100))
        job = MigrationJob(tenant_id=tenant, created_by=actor, **values)
        job.full_clean()
        job.save()
        correlation = _correlation()
        _version(job, actor, correlation, "Initial definition")
        publish_event(tenant, "data_migration.job.created", "migration_job", job.id, actor_id=actor, correlation_id=correlation, payload={"version": 1, "status": job.status})
        return job

    @staticmethod
    @transaction.atomic
    def update(tenant_id: object, job_id: object, actor_id: object, command: Mapping[str, object], expected_version: int) -> MigrationJob:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True)
        if job.configuration_version != expected_version:
            raise ConfigurationConflict()
        forbidden = {"id", "tenant_id", "created_by", "configuration_version", "status", "transition_history"}
        if set(command) & forbidden:
            raise MigrationServiceError("Server-managed job fields cannot be changed.", code="IMMUTABLE_FIELD")
        values = dict(command)
        source_type = str(values.get("source_type", job.source_type))
        source_config = values.get("source_config", job.source_config)
        values["source_config"] = validate_source_config(source_type, source_config)
        _validate_source_reference(tenant, actor, source_type, values["source_config"], values.get("source_artifact_id", job.source_artifact_id))
        _enforce_runtime_policy(tenant, str(values.get("target_adapter", job.target_adapter)))
        for field, value in values.items():
            setattr(job, field, value)
        job.updated_by = actor
        job.configuration_version += 1
        if job.status == "ready":
            job.status = "draft"
        job.full_clean()
        job.save()
        correlation = _correlation()
        _version(job, actor, correlation, "Definition updated")
        publish_event(tenant, "data_migration.job.updated", "migration_job", job.id, actor_id=actor, correlation_id=correlation, payload={"version": job.configuration_version, "status": job.status})
        return job

    @staticmethod
    @transaction.atomic
    def soft_delete(tenant_id: object, job_id: object, actor_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True)
        if job.runs.filter(status__in=("queued", "running")).exists():
            raise MigrationServiceError("A job with an active run cannot be deleted.", code="ACTIVE_RUN")
        job.is_deleted, job.deleted_at, job.updated_by = True, timezone.now(), actor
        job.save(update_fields=("is_deleted", "deleted_at", "updated_by", "updated_at"))
        publish_event(tenant, "data_migration.job.deleted", "migration_job", job.id, actor_id=actor)

    @staticmethod
    @transaction.atomic
    def restore_deleted(tenant_id: object, job_id: object, actor_id: object) -> MigrationJob:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True, include_deleted=True)
        job.is_deleted, job.deleted_at, job.status, job.updated_by = False, None, "draft", actor
        job.save(update_fields=("is_deleted", "deleted_at", "status", "updated_by", "updated_at"))
        publish_event(tenant, "data_migration.job.restored", "migration_job", job.id, actor_id=actor, payload={"status": "draft"})
        return job

    @staticmethod
    @transaction.atomic
    def validate_definition(tenant_id: object, job_id: object, actor_id: object) -> DefinitionValidationResult:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True)
        blockers: list[str] = []
        try:
            validate_source_config(job.source_type, job.source_config)
        except (ValueError, ValidationError, MigrationServiceError) as exc:
            blockers.append(str(exc))
        if not TARGET_ADAPTERS.contains(job.target_adapter):
            blockers.append("Target adapter is unavailable.")
        if not job.mappings.exists():
            blockers.append("At least one mapping is required.")
        if job.write_mode == "upsert" and not job.lookup_fields:
            blockers.append("Upsert requires lookup fields.")
        for rule in job.validation_rules.filter(is_active=True):
            try:
                validate_rule_config(rule.rule_type, rule.rule_config)
            except (ValueError, ValidationError) as exc:
                blockers.append(f"Rule {rule.position}: {exc}")
        if blockers:
            return DefinitionValidationResult(False, tuple(blockers))
        JOB_MACHINE.apply(job, "validate", transition_key=f"validate:{job.configuration_version}", context={"actor_id": str(actor)})
        return DefinitionValidationResult(True, ())

    @staticmethod
    @transaction.atomic
    def archive(tenant_id: object, job_id: object, actor_id: object, transition_key: str) -> MigrationJob:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True)
        result = JOB_MACHINE.apply(job, "archive", transition_key=_text(transition_key, "transition_key"), context={"actor_id": str(actor)})
        publish_event(tenant, "data_migration.job.archived", "migration_job", result.id, actor_id=actor, payload={"status": result.status})
        return result

    @staticmethod
    @transaction.atomic
    def restore_version(tenant_id: object, job_id: object, version: int, actor_id: object, expected_version: int) -> MigrationJob:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True, include_deleted=True)
        if job.configuration_version != expected_version:
            raise ConfigurationConflict()
        historic = MigrationJobVersion.objects.for_tenant(tenant).filter(job=job, version=version).first()
        if historic is None:
            raise NotFound("Migration job version not found.")
        snapshot = historic.snapshot
        for field in ("name", "description", "source_type", "source_artifact_id", "source_config", "target_adapter", "target_entity", "write_mode", "lookup_fields"):
            if field in snapshot:
                setattr(job, field, snapshot[field])
        job.configuration_version += 1
        job.status, job.is_deleted, job.deleted_at, job.updated_by = "draft", False, None, actor
        job.full_clean()
        job.save()
        _version(job, actor, _correlation(), f"Restored version {version}")
        return job

    @staticmethod
    def export_definition(tenant_id: object, job_id: object) -> dict[str, object]:
        job = _job(_uuid(tenant_id, "tenant_id"), job_id)
        snapshot = _safe_snapshot(job)
        document = {"schema_version": "2.0", "job": {key: snapshot[key] for key in ("name", "description", "source_type", "source_artifact_id", "source_config", "target_adapter", "target_entity", "write_mode", "lookup_fields")}, "mappings": snapshot["mappings"], "rules": snapshot["rules"]}
        document["checksum"] = _snapshot_checksum(document)
        return document

    @staticmethod
    @transaction.atomic
    def import_definition(tenant_id: object, actor_id: object, document: Mapping[str, object]) -> MigrationJob:
        supplied = dict(document)
        if supplied.get("schema_version") != "2.0" or supplied.get("checksum") != _snapshot_checksum(supplied):
            raise MigrationServiceError("Import document checksum or schema version is invalid.", code="INVALID_IMPORT")
        forbidden = {"tenant_id", "job_id", "created_by", "credential_ref", "runs", "changes"}
        if set(supplied) & forbidden:
            raise MigrationServiceError("Import document contains forbidden identity or execution fields.", code="INVALID_IMPORT")
        mappings = supplied.get("mappings", [])
        rules = supplied.get("rules", [])
        job = MigrationJobService.create(tenant_id, actor_id, supplied.get("job", {}))
        for item in mappings:
            MigrationMappingService.create(tenant_id, job.id, actor_id, item)
        for item in rules:
            ValidationRuleService.create(tenant_id, job.id, actor_id, item)
        return job


class MigrationMappingService:
    @staticmethod
    @transaction.atomic
    def create(tenant_id: object, job_id: object, actor_id: object, payload: Mapping[str, object]) -> MigrationMapping:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True)
        values = dict(payload)
        values.pop("tenant_id", None); values.pop("job", None)
        values["transform_config"] = validate_transform_config(str(values.get("transform_type", "identity")), values.get("transform_config", {}))
        mapping = MigrationMapping(tenant_id=tenant, job=job, created_by=actor, **values)
        mapping.full_clean(); mapping.save()
        _bump_definition(job, actor, "Mapping created")
        return mapping

    @staticmethod
    @transaction.atomic
    def update(tenant_id: object, mapping_id: object, actor_id: object, payload: Mapping[str, object]) -> MigrationMapping:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        mapping = MigrationMapping.objects.for_tenant(tenant).select_for_update().select_related("job").filter(pk=mapping_id, job__is_deleted=False).first()
        if mapping is None: raise NotFound("Mapping not found.")
        if set(payload) & {"id", "tenant_id", "job", "created_by"}: raise MigrationServiceError("Immutable mapping field.", code="IMMUTABLE_FIELD")
        for field, value in payload.items(): setattr(mapping, field, value)
        mapping.transform_config = validate_transform_config(mapping.transform_type, mapping.transform_config)
        mapping.updated_by = actor; mapping.full_clean(); mapping.save()
        _bump_definition(mapping.job, actor, "Mapping updated")
        return mapping

    @staticmethod
    @transaction.atomic
    def delete(tenant_id: object, mapping_id: object, actor_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        mapping = MigrationMapping.objects.for_tenant(tenant).select_for_update().select_related("job").filter(pk=mapping_id).first()
        if mapping is None: raise NotFound("Mapping not found.")
        job = mapping.job; mapping.delete(); _bump_definition(job, actor, "Mapping deleted")

    @staticmethod
    @transaction.atomic
    def reorder(tenant_id: object, job_id: object, actor_id: object, ordered_ids: Sequence[object]) -> list[MigrationMapping]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        job = _job(tenant, job_id, lock=True)
        rows = list(MigrationMapping.objects.for_tenant(tenant).select_for_update().filter(job=job))
        by_id = {str(row.id): row for row in rows}
        if len(ordered_ids) != len(rows) or set(map(str, ordered_ids)) != set(by_id):
            raise MigrationServiceError("Reorder must contain every mapping exactly once.", code="INVALID_ORDER")
        for position, identifier in enumerate(ordered_ids):
            row = by_id[str(identifier)]; row.position = position; row.updated_by = actor
        MigrationMapping.objects.bulk_update(rows, ("position", "updated_by", "updated_at"))
        _bump_definition(job, actor, "Mappings reordered")
        return sorted(rows, key=lambda item: item.position)

    @staticmethod
    def suggest_deterministic(tenant_id: object, job_id: object) -> list[dict[str, object]]:
        tenant = _uuid(tenant_id, "tenant_id"); job = _job(tenant, job_id)
        adapter = _target_adapter(job.target_adapter)
        schema = adapter.describe_schema(job.target_entity)
        profile = SourceInspectionService.preview(tenant, job.id, min(25, _configuration(tenant).preview_row_limit))
        source_fields = sorted({key for record in profile.records for key in record})
        targets = {str(item["name"]).lower(): item for item in schema.get("fields", [])}
        suggestions = []
        for source in source_fields:
            normalized = re.sub(r"[^a-z0-9]", "", source.lower())
            match = next((field for name, field in targets.items() if re.sub(r"[^a-z0-9]", "", name) == normalized), None)
            if match and not match.get("pii", False):
                suggestion_id = hashlib.sha256(f"{job.id}:{source}:{match['name']}".encode()).hexdigest()[:24]
                suggestions.append({"id": suggestion_id, "source_field": source, "target_field": match["name"], "confidence": "1.0000", "origin": "deterministic"})
        return suggestions

    @staticmethod
    def apply_suggestions(tenant_id: object, job_id: object, actor_id: object, suggestion_ids: Sequence[str]) -> list[MigrationMapping]:
        suggestions = {item["id"]: item for item in MigrationMappingService.suggest_deterministic(tenant_id, job_id)}
        if not set(suggestion_ids) <= set(suggestions): raise MigrationServiceError("Unknown or stale mapping suggestion.", code="INVALID_SUGGESTION")
        start = MigrationMapping.objects.for_tenant(_uuid(tenant_id, "tenant_id")).filter(job_id=job_id).count()
        return [MigrationMappingService.create(tenant_id, job_id, actor_id, {"source_field": suggestions[key]["source_field"], "target_field": suggestions[key]["target_field"], "position": start + index, "origin": "deterministic", "confidence": Decimal(str(suggestions[key]["confidence"]))}) for index, key in enumerate(suggestion_ids)]


def _bump_definition(job: MigrationJob, actor: UUID, summary: str) -> None:
    job.configuration_version += 1; job.updated_by = actor
    if job.status == "ready": job.status = "draft"
    job.save(update_fields=("configuration_version", "updated_by", "status", "updated_at"))
    _version(job, actor, _correlation(), summary)


class ValidationRuleService:
    @staticmethod
    @transaction.atomic
    def create(tenant_id: object, job_id: object, actor_id: object, payload: Mapping[str, object]) -> ValidationRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"); job = _job(tenant, job_id, lock=True)
        values = dict(payload); values.pop("tenant_id", None); values.pop("job", None)
        values["rule_config"] = validate_rule_config(str(values.get("rule_type")), values.get("rule_config", {}))
        rule = ValidationRule(tenant_id=tenant, job=job, created_by=actor, **values); rule.full_clean(); rule.save(); _bump_definition(job, actor, "Validation rule created"); return rule

    @staticmethod
    @transaction.atomic
    def update(tenant_id: object, rule_id: object, actor_id: object, payload: Mapping[str, object]) -> ValidationRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rule = ValidationRule.objects.for_tenant(tenant).select_for_update().select_related("job").filter(pk=rule_id).first()
        if rule is None: raise NotFound("Validation rule not found.")
        if set(payload) & {"id", "tenant_id", "job", "created_by"}: raise MigrationServiceError("Immutable rule field.", code="IMMUTABLE_FIELD")
        for field, value in payload.items(): setattr(rule, field, value)
        rule.rule_config = validate_rule_config(rule.rule_type, rule.rule_config); rule.updated_by = actor; rule.full_clean(); rule.save(); _bump_definition(rule.job, actor, "Validation rule updated"); return rule

    @staticmethod
    @transaction.atomic
    def delete(tenant_id: object, rule_id: object, actor_id: object) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        rule = ValidationRule.objects.for_tenant(tenant).select_for_update().select_related("job").filter(pk=rule_id).first()
        if rule is None: raise NotFound("Validation rule not found.")
        job = rule.job; rule.delete(); _bump_definition(job, actor, "Validation rule deleted")

    reorder = staticmethod(lambda tenant_id, job_id, actor_id, ordered_ids: _reorder_rules(tenant_id, job_id, actor_id, ordered_ids))

    @staticmethod
    def evaluate(tenant_id: object, job_id: object, mapped_record: Mapping[str, object], row_number: int) -> list[RuleOutcome]:
        tenant = _uuid(tenant_id, "tenant_id"); job = _job(tenant, job_id); outcomes: list[RuleOutcome] = []
        adapter = _target_adapter(job.target_adapter)
        for rule in job.validation_rules.filter(is_active=True).order_by("position"):
            config = validate_rule_config(rule.rule_type, rule.rule_config); value = mapped_record.get(rule.field_name); passed = True
            if rule.rule_type == "required": passed = value not in (None, "")
            elif rule.rule_type == "type":
                expected = config["type"]; passed = {"string": lambda: isinstance(value, str), "integer": lambda: isinstance(value, int) and not isinstance(value, bool), "number": lambda: isinstance(value, (int, float, Decimal)) and not isinstance(value, bool), "boolean": lambda: isinstance(value, bool)}.get(expected, lambda: False)()
            elif rule.rule_type == "range": passed = value is not None and (config.get("min") is None or value >= config["min"]) and (config.get("max") is None or value <= config["max"])
            elif rule.rule_type == "length": passed = value is not None and (config.get("min") is None or len(value) >= config["min"]) and (config.get("max") is None or len(value) <= config["max"])
            elif rule.rule_type == "regex": passed = isinstance(value, str) and re.fullmatch(config["pattern"], value) is not None
            elif rule.rule_type == "allowed_values": passed = value in config["values"]
            elif rule.rule_type in ("unique", "referential"): passed = bool(adapter.validate_reference(job.target_entity, rule.field_name, value, rule.rule_type, config))
            else: raise MigrationServiceError(f"Unknown validation rule {rule.rule_type!r}.", code="UNKNOWN_RULE")
            outcomes.append(RuleOutcome(rule.id, rule.field_name, rule.severity, passed, rule.rule_type.upper(), "" if passed else rule.error_message, row_number))
        return outcomes


@transaction.atomic
def _reorder_rules(tenant_id: object, job_id: object, actor_id: object, ordered_ids: Sequence[object]) -> list[ValidationRule]:
    tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"); job = _job(tenant, job_id, lock=True)
    rows = list(ValidationRule.objects.for_tenant(tenant).select_for_update().filter(job=job)); by_id = {str(row.id): row for row in rows}
    if len(ordered_ids) != len(rows) or set(map(str, ordered_ids)) != set(by_id): raise MigrationServiceError("Reorder must contain every rule exactly once.", code="INVALID_ORDER")
    for position, identifier in enumerate(ordered_ids): by_id[str(identifier)].position = position; by_id[str(identifier)].updated_by = actor
    ValidationRule.objects.bulk_update(rows, ("position", "updated_by", "updated_at")); _bump_definition(job, actor, "Validation rules reordered"); return sorted(rows, key=lambda item: item.position)


class SourceInspectionService:
    @staticmethod
    @transaction.atomic
    def request_inspection(tenant_id: object, job_id: object, actor_id: object, idempotency_key: str) -> AsyncJob:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"); job = _job(tenant, job_id)
        version = MigrationJobVersion.objects.for_tenant(tenant).get(job=job, version=job.configuration_version)
        return enqueue(tenant, actor, "data_migration.inspect", {"job_id": str(job.id), "job_version_id": str(version.id)}, f"data-migration:inspect:{_text(idempotency_key, 'idempotency_key')}")

    @staticmethod
    def inspect(tenant_id: object, job_id: object, job_version_id: object) -> SourceProfile:
        tenant = _uuid(tenant_id, "tenant_id"); job = _job(tenant, job_id)
        version = MigrationJobVersion.objects.for_tenant(tenant).filter(pk=job_version_id, job=job).first()
        if version is None: raise NotFound("Migration job version not found.")
        adapter = _source_adapter(f"core.{job.source_type}")
        profile = adapter.inspect(tenant, job.source_artifact_id, job.source_config, _configuration(tenant))
        if not profile or not profile.get("source_checksum"): raise MigrationServiceError("Inspection produced no verified source evidence.", code="UNVERIFIED_SOURCE")
        return SourceProfile(tuple(profile.get("fields", ())), tuple(_redact(item) for item in profile.get("representative_values", ())), int(profile.get("row_estimate", 0)), str(profile["source_checksum"]), tuple(profile.get("warnings", ())))

    @staticmethod
    def preview(tenant_id: object, job_id: object, limit: int) -> PreviewResult:
        tenant = _uuid(tenant_id, "tenant_id"); job = _job(tenant, job_id); configured = _configuration(tenant).preview_row_limit
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > min(100, configured): raise MigrationServiceError(f"Preview limit must be between 1 and {min(100, configured)}.", code="INVALID_LIMIT")
        adapter = _source_adapter(f"core.{job.source_type}"); iterator = adapter.iter_records(tenant, job.source_artifact_id, job.source_config, _configuration(tenant))
        records = []
        for record in iterator:
            records.append(_redact(record))
            if len(records) > limit: break
        visible = records[:limit]; checksum = hashlib.sha256(json.dumps(visible, sort_keys=True, default=str).encode()).hexdigest()
        return PreviewResult(tuple(visible), checksum, len(records) > limit)


class MigrationExecutionService:
    @staticmethod
    @transaction.atomic
    def request_run(tenant_id: object, job_id: object, actor_id: object, mode: str, idempotency_key: str) -> MigrationRun:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"); mode = _text(mode, "mode", 10)
        if mode not in ("dry_run", "commit"): raise MigrationServiceError("mode must be dry_run or commit", code="INVALID_MODE")
        job = _job(tenant, job_id, lock=True)
        if job.status != "ready": raise MigrationServiceError("Only ready jobs may run.", code="JOB_NOT_READY")
        key = _text(idempotency_key, "idempotency_key")
        existing = MigrationRun.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing:
            if existing.job_id != job.id or existing.mode != mode: raise MigrationServiceError("Idempotency key belongs to another run request.", code="IDEMPOTENCY_CONFLICT")
            return existing
        profile = SourceInspectionService.inspect(tenant, job.id, MigrationJobVersion.objects.for_tenant(tenant).get(job=job, version=job.configuration_version).id)
        async_job = enqueue(tenant, actor, "data_migration.execute", {"pending": True}, f"data-migration:run:{key}")
        version = MigrationJobVersion.objects.for_tenant(tenant).get(job=job, version=job.configuration_version)
        run = MigrationRun.objects.create(tenant_id=tenant, job=job, job_version=version, async_job_id=async_job.id, mode=mode, idempotency_key=key, source_checksum=profile.source_checksum, created_by=actor, correlation_id=async_job.correlation_id)
        async_job.payload = {"run_id": str(run.id)}; async_job.save(update_fields=("payload", "updated_at"))
        publish_event(tenant, "data_migration.run.queued", "migration_run", run.id, actor_id=actor, correlation_id=run.correlation_id, payload={"mode": mode, "status": "queued"})
        return run

    @staticmethod
    @transaction.atomic
    def cancel(tenant_id: object, run_id: object, actor_id: object, transition_key: str) -> MigrationRun:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        run = MigrationRun.objects.for_tenant(tenant).select_for_update().filter(pk=run_id).first()
        if run is None: raise NotFound("Migration run not found.")
        run.cancel_requested_at = timezone.now(); run.save(update_fields=("cancel_requested_at", "updated_at"))
        if run.status == "queued": run = RUN_MACHINE.apply(run, "cancel", transition_key=_text(transition_key, "transition_key"), context={"actor_id": str(actor)})
        return run

    @staticmethod
    def execute(tenant_id: object, run_id: object) -> MigrationRun:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            run = MigrationRun.objects.for_tenant(tenant).select_for_update().select_related("job").filter(pk=run_id).first()
            if run is None: raise NotFound("Migration run not found.")
            if run.status in ("succeeded", "partial", "failed", "cancelled", "rolled_back"): return run
            run = RUN_MACHINE.apply(run, "start", transition_key=f"start:{run.id}")
            run.started_at = timezone.now(); run.save(update_fields=("started_at", "updated_at"))
        job = run.job; source = _source_adapter(f"core.{job.source_type}"); target = _target_adapter(job.target_adapter); config = _configuration(tenant)
        batch: list[tuple[int, Mapping[str, object]]] = []
        try:
            for number, record in enumerate(source.iter_records(tenant, job.source_artifact_id, job.source_config, config), start=1):
                batch.append((number, record))
                if len(batch) >= config.batch_size: MigrationExecutionService._process_batch(tenant, run.id, batch, target); batch = []
                if MigrationRun.objects.for_tenant(tenant).filter(pk=run.id, cancel_requested_at__isnull=False).exists():
                    with transaction.atomic():
                        locked = MigrationRun.objects.for_tenant(tenant).select_for_update().get(pk=run.id); return RUN_MACHINE.apply(locked, "cancel", transition_key=f"cancel:worker:{run.id}")
            if batch: MigrationExecutionService._process_batch(tenant, run.id, batch, target)
            with transaction.atomic():
                run = MigrationRun.objects.for_tenant(tenant).select_for_update().get(pk=run.id)
                run.total_records = run.processed_records; run.save(update_fields=("total_records", "updated_at"))
                command = "succeed" if run.failed_records == 0 else "partial"; run = RUN_MACHINE.apply(run, command, transition_key=f"terminal:{run.id}")
                run.completed_at = timezone.now(); run.save(update_fields=("completed_at", "updated_at"))
            return run
        except Exception:
            with transaction.atomic():
                locked = MigrationRun.objects.for_tenant(tenant).select_for_update().get(pk=run.id)
                if locked.status in ("queued", "running"): locked = RUN_MACHINE.apply(locked, "fail", transition_key=f"failed:{run.id}")
                locked.completed_at = timezone.now(); locked.save(update_fields=("completed_at", "updated_at"))
            raise

    @staticmethod
    @transaction.atomic
    def _process_batch(tenant: UUID, run_id: UUID, batch: Sequence[tuple[int, Mapping[str, object]]], target: object) -> None:
        run = MigrationRun.objects.for_tenant(tenant).select_for_update().select_related("job").get(pk=run_id); job = run.job
        mappings = list(job.mappings.order_by("position"))
        for row_number, source_record in batch:
            mapped: dict[str, object] = {}
            try:
                for mapping in mappings: mapped[mapping.target_field] = _transform(source_record.get(mapping.source_field), mapping.transform_type, mapping.transform_config, source_record)
                outcomes = ValidationRuleService.evaluate(tenant, job.id, mapped, row_number)
                failures = [outcome for outcome in outcomes if not outcome.passed]
                for outcome in failures:
                    MigrationRunIssue.objects.create(tenant_id=tenant, run=run, row_number=row_number, field_name=outcome.field_name, stage="validation", severity=outcome.severity, code=outcome.code, message=outcome.message, redacted_sample=_redact(mapped))
                if any(outcome.severity == "error" for outcome in failures): run.failed_records += 1
                elif run.mode == "dry_run": run.succeeded_records += 1
                else:
                    evidence = target.write(tenant, job.target_entity, mapped, write_mode=job.write_mode, lookup_fields=job.lookup_fields, idempotency_key=f"{run.id}:{row_number}")
                    if not evidence or not evidence.get("record_id") or not evidence.get("after_checksum"): raise MigrationServiceError("Target adapter returned no durable write evidence.", code="UNVERIFIED_WRITE")
                    MigrationChange.objects.create(tenant_id=tenant, run=run, sequence=row_number, target_adapter=job.target_adapter, target_entity=job.target_entity, target_record_id=evidence["record_id"], operation=evidence["operation"], before_payload_encrypted=evidence.get("before_payload_encrypted", ""), after_checksum=evidence["after_checksum"], idempotency_key=f"{run.id}:{row_number}")
                    run.succeeded_records += 1
                if any(outcome.severity == "warning" for outcome in failures): run.warning_records += 1
            except Exception as exc:
                run.failed_records += 1
                MigrationRunIssue.objects.create(tenant_id=tenant, run=run, row_number=row_number, stage="target", severity="error", code=getattr(exc, "code", "ROW_FAILED"), message="Record processing failed; use the correlation ID for support.", redacted_sample=_redact(mapped))
            run.processed_records += 1
        run.total_records = max(run.total_records, run.processed_records); run.save(update_fields=("total_records", "processed_records", "succeeded_records", "failed_records", "warning_records", "updated_at"))


def _transform(value: object, kind: str, config: Mapping[str, object], record: Mapping[str, object]) -> object:
    validated = validate_transform_config(kind, config)
    if kind == "identity": return value
    if kind == "default": return validated["value"] if value in (None, "") else value
    if kind == "cast":
        target = validated["to"]
        if target == "string": return "" if value is None else str(value)
        if target == "integer": return int(value)
        if target == "number": return Decimal(str(value))
        if target == "boolean": return str(value).strip().lower() in validated.get("true_values", ["true", "1", "yes"])
    if kind == "lookup": return validated.get("values", {}).get(str(value), validated.get("default"))
    if kind == "concat": return str(validated.get("separator", "")).join(str(record.get(field, "")) for field in validated["fields"])
    if kind == "split": return str(value).split(str(validated["separator"]))[int(validated.get("index", 0))]
    if kind == "regex_replace": return re.sub(str(validated["pattern"]), str(validated.get("replacement", "")), str(value))
    if kind == "date_parse":
        from datetime import datetime
        return datetime.strptime(str(value), str(validated["format"])).isoformat()
    if kind == "boolean_map": return value in validated["true_values"] if value not in validated["false_values"] else False
    raise MigrationServiceError(f"Unknown transform {kind!r}.", code="UNKNOWN_TRANSFORM")


class RollbackService:
    @staticmethod
    @transaction.atomic
    def request(tenant_id: object, run_id: object, actor_id: object, idempotency_key: str) -> MigrationRollback:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"); key = _text(idempotency_key, "idempotency_key")
        existing = MigrationRollback.objects.for_tenant(tenant).filter(idempotency_key=key).first()
        if existing: return existing
        run = MigrationRun.objects.for_tenant(tenant).select_for_update().filter(pk=run_id).first()
        if run is None: raise NotFound("Migration run not found.")
        if run.mode != "commit" or run.status not in ("succeeded", "partial"): raise MigrationServiceError("Only successful committed runs can be rolled back.", code="ROLLBACK_NOT_ALLOWED")
        async_job = enqueue(tenant, actor, "data_migration.rollback", {"pending": True}, f"data-migration:rollback:{key}")
        rollback = MigrationRollback.objects.create(tenant_id=tenant, run=run, async_job_id=async_job.id, idempotency_key=key, records_total=run.changes.filter(reversed_at__isnull=True).count(), requested_by=actor, correlation_id=async_job.correlation_id)
        async_job.payload = {"rollback_id": str(rollback.id)}; async_job.save(update_fields=("payload", "updated_at"))
        publish_event(tenant, "data_migration.rollback.queued", "migration_rollback", rollback.id, actor_id=actor, correlation_id=rollback.correlation_id, payload={"status": "queued"})
        return rollback

    @staticmethod
    def execute(tenant_id: object, rollback_id: object) -> MigrationRollback:
        tenant = _uuid(tenant_id, "tenant_id")
        with transaction.atomic():
            rollback = MigrationRollback.objects.for_tenant(tenant).select_for_update().select_related("run").filter(pk=rollback_id).first()
            if rollback is None: raise NotFound("Rollback not found.")
            if rollback.status in ("succeeded", "failed"): return rollback
            rollback = ROLLBACK_MACHINE.apply(rollback, "start", transition_key=f"start:{rollback.id}"); rollback.started_at = timezone.now(); rollback.save(update_fields=("started_at", "updated_at"))
        target_cache: dict[str, object] = {}
        try:
            for change in MigrationChange.objects.for_tenant(tenant).filter(run=rollback.run, reversed_at__isnull=True).order_by("-sequence"):
                adapter = target_cache.setdefault(change.target_adapter, _target_adapter(change.target_adapter))
                result = adapter.reverse(tenant, change.target_entity, change.target_record_id, operation=change.operation, before_payload_encrypted=change.before_payload_encrypted, expected_checksum=change.after_checksum, idempotency_key=f"rollback:{rollback.id}:{change.sequence}")
                if not result or not result.get("verified"): raise MigrationServiceError("Rollback conflict: target record changed after migration.", code="ROLLBACK_CONFLICT")
                with transaction.atomic():
                    locked_change = MigrationChange.objects.for_tenant(tenant).select_for_update().get(pk=change.id)
                    if locked_change.reversed_at is None: locked_change.mark_reversed(timezone.now()); MigrationRollback.objects.for_tenant(tenant).filter(pk=rollback.id).update(records_reversed=models.F("records_reversed") + 1)
            with transaction.atomic():
                rollback = MigrationRollback.objects.for_tenant(tenant).select_for_update().select_related("run").get(pk=rollback.id); rollback = ROLLBACK_MACHINE.apply(rollback, "succeed", transition_key=f"terminal:{rollback.id}"); rollback.completed_at = timezone.now(); rollback.save(update_fields=("completed_at", "updated_at")); RUN_MACHINE.apply(rollback.run, "mark_rolled_back", transition_key=f"rollback:{rollback.id}")
            return rollback
        except Exception as exc:
            with transaction.atomic():
                rollback = MigrationRollback.objects.for_tenant(tenant).select_for_update().get(pk=rollback.id); rollback.records_failed = rollback.records_total - rollback.records_reversed; rollback.failure_summary = getattr(exc, "code", "ROLLBACK_FAILED"); rollback = ROLLBACK_MACHINE.apply(rollback, "fail", transition_key=f"failed:{rollback.id}"); rollback.completed_at = timezone.now(); rollback.save(update_fields=("records_failed", "failure_summary", "completed_at", "updated_at"))
            raise


class DataMigrationConfigurationService:
    """Versioned tenant runtime controls with immutable audit and rollback."""

    FIELDS = frozenset({"source_row_limit", "batch_size", "connect_timeout_seconds", "read_timeout_seconds", "retry_count", "issue_sample_limit", "preview_row_limit", "retention_days", "allowed_target_adapters", "enabled_roles", "rollout_percentage", "enabled"})

    @classmethod
    def get(cls, tenant_id: object) -> DataMigrationConfiguration:
        return _configuration(_uuid(tenant_id, "tenant_id"))

    @classmethod
    @transaction.atomic
    def update(cls, tenant_id: object, actor_id: object, payload: Mapping[str, object], expected_version: int, correlation_id: str | None = None) -> DataMigrationConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id"); _configuration(tenant)
        config = DataMigrationConfiguration.objects.for_tenant(tenant).select_for_update().get()
        if config.version != expected_version: raise ConfigurationConflict()
        unknown = set(payload) - cls.FIELDS
        if unknown: raise MigrationServiceError(f"Unknown configuration fields: {', '.join(sorted(unknown))}", code="INVALID_CONFIGURATION")
        before = config.as_document()
        for field, value in payload.items(): setattr(config, field, value)
        config.version += 1; config.updated_by = actor; config.full_clean(); config.save(); after = config.as_document(); correlation = _correlation(correlation_id)
        DataMigrationConfigurationAudit.objects.create(tenant_id=tenant, configuration=config, version=config.version, before=before, after=after, changed_by=actor, correlation_id=correlation)
        publish_event(tenant, "data_migration.configuration.changed", "data_migration_configuration", config.id, actor_id=actor, correlation_id=correlation, payload={"version": config.version, "from_version": expected_version})
        return config

    @classmethod
    def preview(cls, tenant_id: object, payload: Mapping[str, object]) -> dict[str, object]:
        config = cls.get(tenant_id); before = config.as_document(); proposed = {**before, **dict(payload)}
        candidate = DataMigrationConfiguration(
            tenant_id=config.tenant_id,
            created_by=config.created_by,
            **{key: proposed[key] for key in cls.FIELDS if key in proposed},
        )
        candidate.full_clean(validate_unique=False, validate_constraints=False)
        return {
            "from_version": config.version,
            "changes": [
                {"field": key, "before": before.get(key), "after": proposed.get(key)}
                for key in sorted(cls.FIELDS)
                if before.get(key) != proposed.get(key)
            ],
        }

    @classmethod
    def export(cls, tenant_id: object) -> dict[str, object]:
        document = {"schema_version": "1.0", "configuration": cls.get(tenant_id).as_document()}; document["checksum"] = _snapshot_checksum(document); return document

    @classmethod
    def import_document(cls, tenant_id: object, actor_id: object, document: Mapping[str, object], expected_version: int) -> DataMigrationConfiguration:
        if document.get("schema_version") != "1.0" or document.get("checksum") != _snapshot_checksum(document): raise MigrationServiceError("Invalid configuration document.", code="INVALID_IMPORT")
        return cls.update(tenant_id, actor_id, document.get("configuration", {}), expected_version)

    @classmethod
    def restore(cls, tenant_id: object, actor_id: object, version: int, expected_version: int) -> DataMigrationConfiguration:
        tenant = _uuid(tenant_id, "tenant_id"); audit = DataMigrationConfigurationAudit.objects.for_tenant(tenant).filter(version=version).first()
        if audit is None: raise NotFound("Configuration version not found.")
        return cls.update(tenant, actor_id, audit.after, expected_version)


# Django F is imported late to keep the core service imports readable.
from django.db import models  # noqa: E402


__all__ = [
    "CapabilityUnavailable", "ConfigurationConflict", "DataMigrationConfigurationService",
    "DefinitionValidationResult", "ExternalConnectionService", "MigrationExecutionService",
    "MigrationJobService", "MigrationMappingService", "MigrationServiceError", "PreviewResult",
    "RollbackService", "RuleOutcome", "SourceInspectionService", "SourceProfile", "ValidationRuleService",
]
