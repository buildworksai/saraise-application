"""Transactional business services for authoritative master data.

The service layer is the only write authority for this module.  Every public
entry point installs a typed tenant context, explicitly scopes ORM queries,
validates same-tenant relationships, and persists its audit event in the same
transaction as the domain mutation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher
from typing import Final
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q, QuerySet
from django.db.models.functions import TruncDate
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from src.core.api import OperationFailed
from src.core.async_jobs.models import AsyncJob, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.observability import get_correlation_id
from src.core.state_machine import StateMachineError
from src.core.tenancy import tenant_context

from .events import publish_domain_event
from .models import (
    DataQualityIssue,
    DataQualityRule,
    DataQualityRuleVersion,
    MasterDataConfiguration,
    MasterDataConfigurationVersion,
    MasterDataEntity,
    MasterDataVersion,
    MasterEntityType,
    MatchCandidate,
    MatchingRule,
    MatchingRuleVersion,
    MergeHistory,
    MergeParticipant,
    MergeReversal,
)
from .state_machines import CANDIDATE_MACHINE, ENTITY_MACHINE, ISSUE_MACHINE

logger = logging.getLogger("saraise.master_data_management")

QUALITY_SCAN_COMMAND: Final = "master_data_management.quality_scan"
DEDUPLICATION_SCAN_COMMAND: Final = "master_data_management.deduplication_scan"
PATH_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
TYPE_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ALLOWED_SCHEMA_KEYS: Final = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "const",
        "default",
        "format",
        "pattern",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "uniqueItems",
        "multipleOf",
        "anyOf",
        "oneOf",
        "allOf",
    }
)
PROTECTED_ENTITY_FIELDS: Final = frozenset(
    {
        "id",
        "tenant_id",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "quality_score",
        "quality_evaluated_at",
        "golden_record",
        "golden_record_id",
        "is_golden",
        "version",
        "status",
        "transition_history",
        "is_deleted",
        "deleted_at",
    }
)


class MDMDomainError(OperationFailed):
    """Stable public business failure raised by MDM services."""

    def __init__(self, code: str, message: str, *, detail: object | None = None, http_status: int = 422) -> None:
        super().__init__(error_code=code, message=message, detail=detail, http_status=http_status)


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    field_path: str
    code: str
    message: str
    dimension: str = "conformity"
    severity: str = "error"
    rule_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    evaluated: bool
    findings: tuple[ValidationFinding, ...]


@dataclass(frozen=True, slots=True)
class QualityReport:
    entity_id: UUID
    evaluated: bool
    score: Decimal | None
    dimension_scores: Mapping[str, Decimal | None]
    issue_count: int
    findings: tuple[ValidationFinding, ...]


@dataclass(frozen=True, slots=True)
class MatchResult:
    rule_id: UUID
    left_entity_id: UUID
    right_entity_id: UUID
    confidence: Decimal
    field_scores: Mapping[str, Decimal]
    evidence: Mapping[str, object]
    outcome: str


@dataclass(frozen=True, slots=True)
class MergePreview:
    entity_ids: tuple[UUID, ...]
    survivor_id: UUID
    golden_values: Mapping[str, object]
    provenance: Mapping[str, UUID]
    source_versions: Mapping[str, int]
    conflicts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MergeReversalConflict:
    entity_id: UUID | None
    code: str
    expected_version: int | None
    current_version: int | None
    message: str


@dataclass(frozen=True, slots=True)
class MergeReversalPreview:
    merge_id: UUID
    can_reverse: bool
    conflicts: tuple[MergeReversalConflict, ...]
    participant_versions: Mapping[str, int]


def _quality_rule_snapshot(rule: DataQualityRule) -> dict[str, object]:
    return {
        "entity_type_id": str(rule.entity_type_id),
        "name": rule.name,
        "field_path": rule.field_path,
        "rule_type": rule.rule_type,
        "configuration": rule.configuration,
        "dimension": rule.dimension,
        "severity": rule.severity,
        "weight": str(rule.weight),
        "is_active": rule.is_active,
        "is_deleted": rule.is_deleted,
    }


def _matching_rule_snapshot(rule: MatchingRule) -> dict[str, object]:
    return {
        "entity_type_id": str(rule.entity_type_id),
        "name": rule.name,
        "algorithm": rule.algorithm,
        "field_weights": rule.field_weights,
        "blocking_fields": rule.blocking_fields,
        "review_threshold": str(rule.review_threshold),
        "auto_confirm_threshold": str(rule.auto_confirm_threshold),
        "is_active": rule.is_active,
        "is_deleted": rule.is_deleted,
    }


def _rule_document(kind: str, rule_id: UUID, version_number: int, snapshot: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema": f"saraise.master-data-management.{kind}",
        "document_version": 1,
        "rule_id": str(rule_id),
        "version_number": version_number,
        "snapshot": deepcopy(dict(snapshot)),
    }


def _imported_rule_snapshot(
    tenant_id: UUID,
    document: object,
    *,
    kind: str,
    expected_rule_id: UUID,
) -> dict[str, object]:
    maximum = int(_configuration_section(tenant_id, "schema_policy")["max_payload_bytes"])
    value = _object(document, "document", maximum_bytes=maximum)
    expected = {"schema", "document_version", "rule_id", "version_number", "snapshot"}
    if set(value) != expected:
        raise MDMDomainError(
            "INVALID_RULE_DOCUMENT",
            "Rule document fields do not match the portable contract.",
            detail={"missing": sorted(expected - set(value)), "unknown": sorted(set(value) - expected)},
        )
    if value["schema"] != f"saraise.master-data-management.{kind}" or value["document_version"] != 1:
        raise MDMDomainError("INVALID_RULE_DOCUMENT", "Rule document schema or version is unsupported.")
    if _uuid(value["rule_id"], "rule_id") != expected_rule_id:
        raise MDMDomainError("INVALID_RULE_DOCUMENT", "Rule document belongs to a different rule.")
    if not isinstance(value["version_number"], int) or value["version_number"] < 1:
        raise MDMDomainError("INVALID_RULE_DOCUMENT", "version_number must be a positive integer.")
    return _object(value["snapshot"], "snapshot", maximum_bytes=maximum)


def _record_quality_rule_version(
    rule: DataQualityRule,
    actor_id: UUID,
    *,
    reason: str,
) -> DataQualityRuleVersion:
    latest = (
        DataQualityRuleVersion.objects.for_tenant(rule.tenant_id)
        .filter(rule=rule)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first()
    )
    return DataQualityRuleVersion.objects.create(
        tenant_id=rule.tenant_id,
        rule=rule,
        version_number=(latest or 0) + 1,
        snapshot=_quality_rule_snapshot(rule),
        changed_by=actor_id,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
        change_reason=reason,
    )


def _record_matching_rule_version(
    rule: MatchingRule,
    actor_id: UUID,
    *,
    reason: str,
) -> MatchingRuleVersion:
    latest = (
        MatchingRuleVersion.objects.for_tenant(rule.tenant_id)
        .filter(rule=rule)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first()
    )
    return MatchingRuleVersion.objects.create(
        tenant_id=rule.tenant_id,
        rule=rule,
        version_number=(latest or 0) + 1,
        snapshot=_matching_rule_snapshot(rule),
        changed_by=actor_id,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
        change_reason=reason,
    )


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise MDMDomainError("INVALID_UUID", f"{field} must be a valid UUID.", detail={field: "Invalid UUID."}) from exc


def _text(value: object, field: str, *, maximum: int, blank: bool = False) -> str:
    if not isinstance(value, str):
        raise MDMDomainError("VALIDATION_ERROR", f"{field} must be a string.", detail={field: "Must be a string."})
    normalized = value.strip()
    if not normalized and not blank:
        raise MDMDomainError("VALIDATION_ERROR", f"{field} is required.", detail={field: "This field is required."})
    if len(normalized) > maximum:
        raise MDMDomainError(
            "VALIDATION_ERROR", f"{field} exceeds its maximum length.", detail={field: f"Maximum {maximum} characters."}
        )
    return normalized


def _object(value: object, field: str, *, maximum_bytes: int = 10_485_760) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise MDMDomainError("VALIDATION_ERROR", f"{field} must be an object.", detail={field: "Must be an object."})
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise MDMDomainError("VALIDATION_ERROR", f"{field} must contain valid JSON.") from exc
    if len(encoded.encode()) > maximum_bytes:
        raise MDMDomainError(
            "PAYLOAD_TOO_LARGE",
            f"{field} exceeds the configured payload limit.",
            http_status=413,
        )
    return decoded


def _paths(
    value: Sequence[object],
    field: str,
    *,
    pattern: re.Pattern[str] = PATH_RE,
) -> list[str]:
    if isinstance(value, (str, bytes)):
        raise MDMDomainError("VALIDATION_ERROR", f"{field} must be an array of field paths.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not pattern.fullmatch(item):
            raise MDMDomainError("VALIDATION_ERROR", f"{field} contains an invalid field path.")
        if item in result:
            raise MDMDomainError("VALIDATION_ERROR", f"{field} contains duplicate field paths.")
        result.append(item)
    return result


def _schema_keywords(
    schema: object,
    allowed_keywords: frozenset[str],
    path: str = "$",
) -> None:
    if not isinstance(schema, Mapping):
        raise MDMDomainError("INVALID_SCHEMA", f"Schema node {path} must be an object.")
    unknown = set(schema) - allowed_keywords
    if unknown:
        raise MDMDomainError(
            "UNSUPPORTED_SCHEMA_KEYWORD",
            "The schema uses unsupported keywords.",
            detail={"path": path, "keywords": sorted(str(item) for item in unknown)},
        )
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise MDMDomainError("INVALID_SCHEMA", f"{path}.properties must be an object.")
    for key, subschema in properties.items():
        if not isinstance(key, str) or not key:
            raise MDMDomainError("INVALID_SCHEMA", f"{path}.properties keys must be non-empty strings.")
        _schema_keywords(subschema, allowed_keywords, f"{path}.properties.{key}")
    items = schema.get("items")
    if items is not None:
        _schema_keywords(items, allowed_keywords, f"{path}.items")
    for combinator in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(combinator, [])
        if not isinstance(variants, list):
            raise MDMDomainError("INVALID_SCHEMA", f"{path}.{combinator} must be an array.")
        for index, variant in enumerate(variants):
            _schema_keywords(variant, allowed_keywords, f"{path}.{combinator}[{index}]")


def _validate_schema(
    schema: object,
    *,
    allowed_keywords: frozenset[str],
    maximum_bytes: int,
) -> dict[str, object]:
    normalized = _object(schema, "json_schema", maximum_bytes=maximum_bytes)
    _schema_keywords(normalized, allowed_keywords)
    if normalized.get("type") != "object":
        raise MDMDomainError("INVALID_SCHEMA", "The root JSON schema type must be object.")
    try:
        Draft202012Validator.check_schema(normalized)
    except SchemaError as exc:
        raise MDMDomainError("INVALID_SCHEMA", "The JSON schema is invalid.", detail={"path": list(exc.path)}) from exc
    return normalized


def _get_path(data: Mapping[str, object], path: str) -> tuple[bool, object | None]:
    current: object = data
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set_path(data: dict[str, object], path: str, value: object) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def _changed_paths(before: Mapping[str, object], after: Mapping[str, object], prefix: str = "data") -> list[str]:
    changed: list[str] = []
    for key in sorted(set(before) | set(after)):
        left, right = before.get(key), after.get(key)
        path = f"{prefix}.{key}"
        if isinstance(left, Mapping) and isinstance(right, Mapping):
            changed.extend(_changed_paths(left, right, path))
        elif left != right:
            changed.append(path)
    return changed


def _fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _existing_receipt(tenant_id: UUID, event_type: str, key: str, fingerprint: str) -> UUID | None:
    event = (
        OutboxEvent.objects.for_tenant(tenant_id)
        .filter(event_type=event_type, payload__causation_id=key)
        .order_by("created_at")
        .first()
    )
    if event is None:
        return None
    stored = event.payload.get("payload", {}).get("request_fingerprint") if isinstance(event.payload, dict) else None
    if stored is not None and stored != fingerprint:
        raise MDMDomainError(
            "IDEMPOTENCY_CONFLICT", "The idempotency key was already used for different input.", http_status=409
        )
    return event.aggregate_id


def _emit(
    tenant_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: UUID,
    *,
    idempotency_key: str | None = None,
    payload: Mapping[str, object] | None = None,
) -> OutboxEvent:
    values = dict(payload or {})
    return publish_domain_event(
        tenant_id,
        event_type,
        aggregate_type,
        aggregate_id,
        actor_id=actor_id,
        payload=values,
        correlation_id=get_correlation_id(),
        causation_id=idempotency_key,
    )


def _enqueue_checked(
    tenant_id: UUID,
    actor_id: UUID,
    command: str,
    payload: dict[str, object],
    idempotency_key: str,
) -> AsyncJob:
    job = enqueue(tenant_id, actor_id, command, payload, idempotency_key)
    if job.command != command or job.payload != payload:
        raise MDMDomainError(
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key was already used for a different durable command.",
            http_status=409,
        )
    return job


def _clean(instance: object) -> None:
    try:
        instance.full_clean()  # type: ignore[attr-defined]
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
        raise MDMDomainError("VALIDATION_ERROR", "Domain validation failed.", detail=detail) from exc


def _save_version(
    entity: MasterDataEntity,
    actor_id: UUID,
    *,
    changed_fields: Sequence[str],
    reason: str,
) -> MasterDataVersion:
    return MasterDataVersion.objects.create(
        tenant_id=entity.tenant_id,
        entity=entity,
        version_number=entity.version,
        entity_type_key=entity.entity_type.key,
        entity_code=entity.entity_code,
        entity_name=entity.entity_name,
        data_snapshot=entity.data,
        status_snapshot=entity.status,
        quality_score_snapshot=entity.quality_score,
        changed_fields=list(changed_fields),
        change_reason=reason,
        changed_by=actor_id,
        correlation_id=get_correlation_id() or str(uuid.uuid4()),
    )


def _log(
    operation: str, tenant_id: UUID, actor_id: UUID | None, resource: object, started: float, outcome: str
) -> None:
    logger.info(
        "MDM operation %s",
        operation,
        extra={
            "event": f"mdm.operation.{operation}",
            "correlation_id": get_correlation_id(),
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id) if actor_id else None,
            "resource_type": type(resource).__name__,
            "resource_id": str(getattr(resource, "pk", "")),
            "operation": operation,
            "outcome": outcome,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        },
    )


BUILTIN_TYPES: Final[tuple[dict[str, object], ...]] = (
    {
        "key": "customer",
        "display_name": "Customer",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {"type": "string", "format": "email"},
            "phone": {"type": "string"},
            "tax_id": {"type": "string"},
        },
        "sensitive": ["tax_id"],
    },
    {
        "key": "supplier",
        "display_name": "Vendor",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {"type": "string", "format": "email"},
            "tax_id": {"type": "string"},
            "bank_account": {"type": "string"},
        },
        "sensitive": ["tax_id", "bank_account"],
    },
    {
        "key": "product",
        "display_name": "Product",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "description": {"type": "string"},
            "category": {"type": "string"},
        },
        "sensitive": [],
    },
    {
        "key": "employee",
        "display_name": "Employee",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "email": {"type": "string", "format": "email"},
            "department": {"type": "string"},
            "national_id": {"type": "string"},
        },
        "sensitive": ["national_id"],
    },
    {
        "key": "location",
        "display_name": "Location",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "address": {"type": "string"},
            "country": {"type": "string"},
        },
        "sensitive": [],
    },
    {
        "key": "account",
        "display_name": "Account",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "account_number": {"type": "string"},
            "currency": {"type": "string"},
        },
        "sensitive": ["account_number"],
    },
    {
        "key": "material",
        "display_name": "Material",
        "required": ["name"],
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "specification": {"type": "string"},
            "unit": {"type": "string"},
        },
        "sensitive": [],
    },
)


DEFAULT_CONFIGURATION: Final[dict[str, object]] = {
    "environment": "default",
    "schema_policy": {
        "entity_type_key_pattern": r"^[a-z][a-z0-9_]{1,63}$",
        "entity_type_key_max_length": 64,
        "field_path_pattern": r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$",
        "allowed_json_schema_keywords": sorted(ALLOWED_SCHEMA_KEYS),
        "max_payload_bytes": 262_144,
        "builtin_entity_types": list(BUILTIN_TYPES),
    },
    "lifecycle": {
        "allow_physical_delete": False,
        "merged_entities_editable": False,
    },
    "workflows": {
        "entity": {
            "states": ["active", "pending_review", "merged", "archived"],
            "transitions": [
                {"from": "active", "to": "pending_review", "command": "request_review"},
                {"from": "pending_review", "to": "active", "command": "approve"},
                {"from": "active", "to": "merged", "command": "merge"},
                {"from": "pending_review", "to": "merged", "command": "merge"},
                {"from": "active", "to": "archived", "command": "archive"},
                {"from": "pending_review", "to": "archived", "command": "archive"},
                {"from": "archived", "to": "active", "command": "restore"},
                {"from": "merged", "to": "active", "command": "reverse_merge"},
            ],
        },
        "quality_issue": {
            "states": ["open", "in_review", "resolved", "waived"],
            "terminal_states": ["resolved", "waived"],
            "transitions": [
                {"from": "open", "to": "in_review", "command": "assign"},
                {"from": "open", "to": "resolved", "command": "resolve"},
                {"from": "in_review", "to": "resolved", "command": "resolve"},
                {"from": "open", "to": "waived", "command": "waive"},
                {"from": "in_review", "to": "waived", "command": "waive"},
            ],
        },
        "match_candidate": {
            "states": ["pending", "confirmed", "rejected", "merged"],
            "terminal_states": ["rejected", "merged"],
            "transitions": [
                {"from": "pending", "to": "confirmed", "command": "confirm"},
                {"from": "pending", "to": "rejected", "command": "reject"},
                {"from": "confirmed", "to": "merged", "command": "merge"},
            ],
        },
        "merge": {
            "states": ["applied", "reversed"],
            "transitions": [{"from": "applied", "to": "reversed", "command": "reverse"}],
        },
    },
    "limits": {
        "display_name_max": 120,
        "description_max": 10_000,
        "owner_module_max": 100,
        "entity_code_max": 100,
        "entity_name_max": 255,
        "source_system_max": 100,
        "source_record_id_max": 255,
        "resolution_max": 10_000,
        "reason_max": 10_000,
        "deduplication_scan_max_entities": 10_000,
        "merge_min_entities": 2,
        "list_page_size": 25,
        "selector_page_size": 100,
    },
    "quality": {
        "missing_values": [None, "", []],
        "rule_schemas": {
            "required": {"required": [], "allowed": [], "at_least_one": []},
            "format": {"required": ["pattern"], "allowed": ["pattern"], "at_least_one": []},
            "range": {
                "required": [],
                "allowed": ["minimum", "maximum"],
                "at_least_one": ["minimum", "maximum"],
            },
            "uniqueness": {"required": [], "allowed": [], "at_least_one": []},
            "referential": {
                "required": ["entity_type_key"],
                "allowed": ["entity_type_key", "target_field"],
                "at_least_one": [],
            },
            "timeliness": {
                "required": [],
                "allowed": ["max_age_days"],
                "at_least_one": [],
            },
        },
        "referential_target_field_default": "entity_code",
        "timeliness_max_age_days_default": 0,
        "no_rules_evaluated": False,
        "no_rules_score": None,
        "no_rules_issue_count": 0,
        "score_scale": 100,
        "score_decimal_places": 2,
        "auto_resolve_passing": True,
        "defaults": {
            "rule_type": "required",
            "dimension": "completeness",
            "severity": "error",
            "weight": "1.0000",
        },
    },
    "matching": {
        "algorithms": ["exact", "normalized", "fuzzy", "phonetic"],
        "soundex_mapping": {
            "B": "1",
            "F": "1",
            "P": "1",
            "V": "1",
            "C": "2",
            "G": "2",
            "J": "2",
            "K": "2",
            "Q": "2",
            "S": "2",
            "X": "2",
            "Z": "2",
            "D": "3",
            "T": "3",
            "L": "4",
            "M": "5",
            "N": "5",
            "R": "6",
        },
        "soundex_output_length": 4,
        "weight_sum": "1.0000",
        "weight_tolerance": "0.0001",
        "threshold_min": "0",
        "threshold_max": "1",
        "missing_value_score": "0",
        "outcomes": {
            "auto_confirm": "auto_confirm",
            "review": "review",
            "no_match": "no_match",
        },
        "strategy_version": 1,
        "scan_statuses": ["active", "pending_review"],
        "skip_incomplete_blocking_keys": True,
        "auto_confirm_enabled": True,
        "review_decisions": ["confirm", "reject"],
        "defaults": {
            "algorithm": "normalized",
            "review_threshold": "0.7000",
            "auto_confirm_threshold": "0.9500",
        },
    },
    "merge": {
        "allowed_statuses": ["active", "pending_review"],
        "survivorship_order": ["quality_score:desc", "updated_at:desc", "id:asc"],
        "reversal_expected_version_increment": 1,
    },
    "dashboard": {
        "score_buckets": [
            {"label": "Excellent", "minimum": 90, "maximum": 100},
            {"label": "Good", "minimum": 70, "maximum": 90},
            {"label": "Needs attention", "minimum": 0, "maximum": 70},
        ],
        "trend_window_days": 30,
        "recent_activity_limit": 10,
        "minimum_bar_percent": 2,
    },
    "operational": {
        "health_check_interval_seconds": 60,
        "job_poll_interval_ms": 2_000,
        "job_poll_statuses": ["queued", "running", "retrying"],
    },
    "ui": {
        "sidebar_order": 240,
        "skeleton_cards": 5,
        "quality_issue_default_status": "open",
        "list_page_size": 25,
        "status_tokens": {
            "danger": "destructive",
            "success": "success",
            "warning": "warning",
        },
    },
    "entity_defaults": {"source_system": "manual"},
    "feature_rollout": {
        "enabled": True,
        "modes": ["development", "self-hosted", "saas"],
        "roles": [],
        "cohorts": [],
        "percentage": 100,
    },
}


class ConfigurationService:
    """Authoritative, tenant-safe configuration engine."""

    REQUIRED_SECTIONS: Final = frozenset(DEFAULT_CONFIGURATION)

    @staticmethod
    def defaults() -> dict[str, object]:
        return deepcopy(DEFAULT_CONFIGURATION)

    @classmethod
    def validate_document(cls, value: object) -> dict[str, object]:
        document = _object(value, "document")
        missing = cls.REQUIRED_SECTIONS - set(document)
        unknown = set(document) - cls.REQUIRED_SECTIONS
        if missing or unknown:
            raise MDMDomainError(
                "INVALID_CONFIGURATION",
                "The configuration document has an invalid top-level schema.",
                detail={"missing": sorted(missing), "unknown": sorted(unknown)},
            )
        environment = document.get("environment")
        if not isinstance(environment, str) or not environment.strip() or len(environment) > 64:
            raise MDMDomainError("INVALID_CONFIGURATION", "environment must be a non-empty identifier.")

        def section(name: str) -> dict[str, object]:
            raw = document.get(name)
            if not isinstance(raw, dict):
                raise MDMDomainError(
                    "INVALID_CONFIGURATION",
                    f"{name} must be an object.",
                    detail={name: "Must be an object."},
                )
            return raw

        def bounded_integer(
            values: Mapping[str, object],
            name: str,
            *,
            minimum: int,
            maximum: int,
        ) -> int:
            raw = values.get(name)
            if isinstance(raw, bool) or not isinstance(raw, int) or not minimum <= raw <= maximum:
                raise MDMDomainError(
                    "INVALID_CONFIGURATION",
                    f"{name} is outside its safe bounds.",
                    detail={name: f"Must be an integer from {minimum} to {maximum}."},
                )
            return raw

        schema_policy = section("schema_policy")
        for pattern_key in ("entity_type_key_pattern", "field_path_pattern"):
            pattern = schema_policy.get(pattern_key)
            if not isinstance(pattern, str) or len(pattern) > 512:
                raise MDMDomainError("INVALID_CONFIGURATION", f"{pattern_key} must be a safe regex string.")
            try:
                re.compile(pattern)
            except re.error as exc:
                raise MDMDomainError("INVALID_CONFIGURATION", f"{pattern_key} is not a valid regex.") from exc
        bounded_integer(schema_policy, "entity_type_key_max_length", minimum=2, maximum=64)
        bounded_integer(schema_policy, "max_payload_bytes", minimum=1_024, maximum=10_485_760)
        keywords = schema_policy.get("allowed_json_schema_keywords")
        if not isinstance(keywords, list) or not keywords or any(not isinstance(item, str) for item in keywords):
            raise MDMDomainError(
                "INVALID_CONFIGURATION", "allowed_json_schema_keywords must be a non-empty string list."
            )
        if not set(keywords).issubset(ALLOWED_SCHEMA_KEYS):
            raise MDMDomainError(
                "INVALID_CONFIGURATION", "The schema keyword allow-list contains unsupported capabilities."
            )
        builtins = schema_policy.get("builtin_entity_types")
        if not isinstance(builtins, list) or any(not isinstance(item, dict) for item in builtins):
            raise MDMDomainError("INVALID_CONFIGURATION", "builtin_entity_types must be an object list.")

        limits = section("limits")
        limit_bounds = {
            "display_name_max": (1, 120),
            "description_max": (1, 1_000_000),
            "owner_module_max": (1, 100),
            "entity_code_max": (1, 100),
            "entity_name_max": (1, 255),
            "source_system_max": (1, 100),
            "source_record_id_max": (1, 255),
            "resolution_max": (1, 1_000_000),
            "reason_max": (1, 1_000_000),
            "deduplication_scan_max_entities": (1, 1_000_000),
            "merge_min_entities": (2, 100),
            "list_page_size": (1, 500),
            "selector_page_size": (1, 500),
        }
        for key, (minimum, maximum) in limit_bounds.items():
            bounded_integer(limits, key, minimum=minimum, maximum=maximum)

        quality = section("quality")
        score_scale = bounded_integer(quality, "score_scale", minimum=1, maximum=100)
        bounded_integer(quality, "score_decimal_places", minimum=0, maximum=6)
        if not isinstance(quality.get("missing_values"), list):
            raise MDMDomainError("INVALID_CONFIGURATION", "quality.missing_values must be an array.")
        if quality.get("no_rules_score") is not None:
            score = Decimal(str(quality["no_rules_score"]))
            if score < 0 or score > score_scale:
                raise MDMDomainError("INVALID_CONFIGURATION", "quality.no_rules_score is outside the score scale.")
        if not isinstance(quality.get("rule_schemas"), dict):
            raise MDMDomainError("INVALID_CONFIGURATION", "quality.rule_schemas must be an object.")
        for key in ("auto_resolve_passing", "no_rules_evaluated"):
            if not isinstance(quality.get(key), bool):
                raise MDMDomainError("INVALID_CONFIGURATION", f"quality.{key} must be boolean.")
        bounded_integer(quality, "no_rules_issue_count", minimum=0, maximum=1_000_000)
        bounded_integer(quality, "timeliness_max_age_days_default", minimum=0, maximum=36_500)

        matching = section("matching")
        algorithms = matching.get("algorithms")
        if not isinstance(algorithms, list) or not algorithms or any(not isinstance(item, str) for item in algorithms):
            raise MDMDomainError("INVALID_CONFIGURATION", "matching.algorithms must be a non-empty allow-list.")
        threshold_min = Decimal(str(matching.get("threshold_min")))
        threshold_max = Decimal(str(matching.get("threshold_max")))
        if threshold_min < 0 or threshold_max > 1 or threshold_min >= threshold_max:
            raise MDMDomainError("INVALID_CONFIGURATION", "Matching threshold bounds must satisfy 0 <= min < max <= 1.")
        if Decimal(str(matching.get("weight_tolerance"))) <= 0:
            raise MDMDomainError("INVALID_CONFIGURATION", "matching.weight_tolerance must be positive.")
        bounded_integer(matching, "soundex_output_length", minimum=1, maximum=32)
        bounded_integer(matching, "strategy_version", minimum=1, maximum=1_000_000)
        if not isinstance(matching.get("review_decisions"), list) or not matching["review_decisions"]:
            raise MDMDomainError("INVALID_CONFIGURATION", "matching.review_decisions must be a non-empty allow-list.")
        soundex_mapping = matching.get("soundex_mapping")
        if not isinstance(soundex_mapping, dict) or any(
            not isinstance(key, str)
            or len(key) != 1
            or not key.isascii()
            or not key.isalpha()
            or not isinstance(code, str)
            or len(code) != 1
            or not code.isdigit()
            for key, code in soundex_mapping.items()
        ):
            raise MDMDomainError("INVALID_CONFIGURATION", "matching.soundex_mapping is invalid.")
        for key in ("auto_confirm_enabled", "skip_incomplete_blocking_keys"):
            if not isinstance(matching.get(key), bool):
                raise MDMDomainError("INVALID_CONFIGURATION", f"matching.{key} must be boolean.")
        outcomes = matching.get("outcomes")
        if (
            not isinstance(outcomes, dict)
            or set(outcomes) != {"auto_confirm", "review", "no_match"}
            or any(not isinstance(item, str) or not item for item in outcomes.values())
            or len(set(outcomes.values())) != len(outcomes)
        ):
            raise MDMDomainError("INVALID_CONFIGURATION", "matching.outcomes must define three unique outcomes.")

        dashboard = section("dashboard")
        buckets = dashboard.get("score_buckets")
        if not isinstance(buckets, list) or not buckets:
            raise MDMDomainError("INVALID_CONFIGURATION", "dashboard.score_buckets must be non-empty.")
        previous_minimum: Decimal | None = None
        for bucket in buckets:
            if not isinstance(bucket, dict):
                raise MDMDomainError("INVALID_CONFIGURATION", "Each dashboard score bucket must be an object.")
            minimum = Decimal(str(bucket.get("minimum")))
            maximum = Decimal(str(bucket.get("maximum")))
            if minimum < 0 or maximum > score_scale or minimum >= maximum:
                raise MDMDomainError("INVALID_CONFIGURATION", "Dashboard score bucket bounds are invalid.")
            if previous_minimum is not None and maximum != previous_minimum:
                raise MDMDomainError("INVALID_CONFIGURATION", "Dashboard score buckets must be contiguous.")
            previous_minimum = minimum
        bounded_integer(dashboard, "trend_window_days", minimum=1, maximum=3_650)
        bounded_integer(dashboard, "recent_activity_limit", minimum=1, maximum=1_000)
        bounded_integer(dashboard, "minimum_bar_percent", minimum=0, maximum=100)

        operational = section("operational")
        bounded_integer(operational, "health_check_interval_seconds", minimum=5, maximum=3_600)
        bounded_integer(operational, "job_poll_interval_ms", minimum=250, maximum=60_000)
        if not isinstance(operational.get("job_poll_statuses"), list):
            raise MDMDomainError("INVALID_CONFIGURATION", "operational.job_poll_statuses must be an array.")
        valid_job_statuses = {"queued", "running", "retrying", "succeeded", "failed", "cancelled", "timed_out"}
        if not set(operational["job_poll_statuses"]).issubset(valid_job_statuses):
            raise MDMDomainError("INVALID_CONFIGURATION", "operational.job_poll_statuses contains an invalid status.")

        rollout = section("feature_rollout")
        bounded_integer(rollout, "percentage", minimum=0, maximum=100)
        if not isinstance(rollout.get("enabled"), bool):
            raise MDMDomainError("INVALID_CONFIGURATION", "feature_rollout.enabled must be boolean.")
        for key in ("modes", "roles", "cohorts"):
            if not isinstance(rollout.get(key), list) or any(not isinstance(item, str) for item in rollout[key]):
                raise MDMDomainError("INVALID_CONFIGURATION", f"feature_rollout.{key} must be a string list.")

        lifecycle = section("lifecycle")
        for key in ("allow_physical_delete", "merged_entities_editable"):
            if not isinstance(lifecycle.get(key), bool):
                raise MDMDomainError("INVALID_CONFIGURATION", f"lifecycle.{key} must be boolean.")

        workflows = section("workflows")
        for workflow_name in ("entity", "quality_issue", "match_candidate", "merge"):
            workflow = workflows.get(workflow_name)
            if not isinstance(workflow, dict):
                raise MDMDomainError("INVALID_CONFIGURATION", f"workflows.{workflow_name} must be an object.")
            states = workflow.get("states")
            transitions = workflow.get("transitions")
            terminal_states = workflow.get("terminal_states", [])
            if (
                not isinstance(states, list)
                or not states
                or len(states) != len(set(states))
                or any(not isinstance(item, str) or not item for item in states)
                or not isinstance(transitions, list)
                or not isinstance(terminal_states, list)
                or not set(terminal_states).issubset(set(states))
            ):
                raise MDMDomainError("INVALID_CONFIGURATION", f"workflows.{workflow_name} is invalid.")
            seen: set[tuple[str, str, str]] = set()
            for transition in transitions:
                if not isinstance(transition, dict):
                    raise MDMDomainError(
                        "INVALID_CONFIGURATION", f"workflows.{workflow_name} has an invalid transition."
                    )
                identity = (
                    str(transition.get("from", "")),
                    str(transition.get("to", "")),
                    str(transition.get("command", "")),
                )
                if (
                    set(transition) != {"from", "to", "command"}
                    or identity[0] not in states
                    or identity[1] not in states
                    or not identity[2]
                    or identity in seen
                ):
                    raise MDMDomainError(
                        "INVALID_CONFIGURATION", f"workflows.{workflow_name} has an invalid transition."
                    )
                seen.add(identity)

        ui = section("ui")
        bounded_integer(ui, "sidebar_order", minimum=0, maximum=10_000)
        bounded_integer(ui, "skeleton_cards", minimum=1, maximum=50)
        bounded_integer(ui, "list_page_size", minimum=1, maximum=500)
        issue_statuses = workflows["quality_issue"]["states"]
        if (
            not isinstance(ui.get("quality_issue_default_status"), str)
            or ui["quality_issue_default_status"] not in issue_statuses
        ):
            raise MDMDomainError(
                "INVALID_CONFIGURATION",
                "ui.quality_issue_default_status must be an allowed quality-issue workflow state.",
            )
        status_tokens = ui.get("status_tokens")
        if (
            not isinstance(status_tokens, dict)
            or set(status_tokens) != {"danger", "success", "warning"}
            or any(
                not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value) is None
                for value in status_tokens.values()
            )
        ):
            raise MDMDomainError(
                "INVALID_CONFIGURATION",
                "ui.status_tokens must use semantic design-token identifiers.",
            )

        merge = section("merge")
        entity_states = set(workflows["entity"]["states"])
        allowed_statuses = merge.get("allowed_statuses")
        if (
            not isinstance(allowed_statuses, list)
            or not allowed_statuses
            or not set(allowed_statuses).issubset(entity_states)
        ):
            raise MDMDomainError("INVALID_CONFIGURATION", "merge.allowed_statuses is invalid.")
        survivorship = merge.get("survivorship_order")
        allowed_survivorship = {
            "quality_score:asc",
            "quality_score:desc",
            "updated_at:asc",
            "updated_at:desc",
            "id:asc",
        }
        if (
            not isinstance(survivorship, list)
            or not survivorship
            or len(survivorship) != len(set(survivorship))
            or not set(survivorship).issubset(allowed_survivorship)
            or survivorship[-1] != "id:asc"
        ):
            raise MDMDomainError(
                "INVALID_CONFIGURATION",
                "merge.survivorship_order must end with deterministic id:asc.",
            )
        bounded_integer(
            merge,
            "reversal_expected_version_increment",
            minimum=1,
            maximum=100,
        )
        scan_statuses = matching.get("scan_statuses")
        if not isinstance(scan_statuses, list) or not scan_statuses or not set(scan_statuses).issubset(entity_states):
            raise MDMDomainError("INVALID_CONFIGURATION", "matching.scan_statuses is invalid.")

        entity_defaults = section("entity_defaults")
        source_system = entity_defaults.get("source_system")
        if (
            not isinstance(source_system, str)
            or not source_system.strip()
            or len(source_system) > int(limits["source_system_max"])
        ):
            raise MDMDomainError("INVALID_CONFIGURATION", "entity_defaults.source_system is invalid.")
        return document

    @classmethod
    def get_effective(cls, tenant_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            current = MasterDataConfiguration.objects.for_tenant(tenant).first()
            return cls.validate_document(current.document) if current is not None else cls.defaults()

    @classmethod
    def ensure_defaults(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
    ) -> MasterDataConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            current = MasterDataConfiguration.objects.for_tenant(tenant).first()
        if current is not None:
            return current
        return cls.write(
            tenant,
            actor_id,
            document=cls.defaults(),
            idempotency_key="system:initialize-default-configuration:v1",
            reason="Initialize the governed default MDM configuration.",
            expected_version=0,
            change_type="initialize",
        )

    @classmethod
    def preview(cls, tenant_id: UUID, document: object) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        proposed = cls.validate_document(document)
        current = cls.get_effective(tenant)
        changes = [
            {"path": path, "before": before, "after": after} for path, before, after in cls._diff(current, proposed)
        ]
        return {"valid": True, "document": proposed, "changes": changes}

    @classmethod
    def _diff(
        cls,
        before: object,
        after: object,
        prefix: str = "",
    ) -> list[tuple[str, object, object]]:
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            changes: list[tuple[str, object, object]] = []
            for key in sorted(set(before) | set(after)):
                path = f"{prefix}.{key}" if prefix else str(key)
                changes.extend(cls._diff(before.get(key), after.get(key), path))
            return changes
        if before == after:
            return []
        return [(prefix, before, after)]

    @classmethod
    def write(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        document: object,
        idempotency_key: str,
        reason: str,
        expected_version: int | None = None,
        change_type: str = "update",
    ) -> MasterDataConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        normalized = cls.validate_document(document)
        key = _text(idempotency_key, "idempotency_key", maximum=255)
        reason_value = _text(reason, "reason", maximum=500)
        correlation_id = get_correlation_id() or str(uuid.uuid4())
        with tenant_context(tenant), transaction.atomic():
            prior_audit = (
                MasterDataConfigurationVersion.objects.for_tenant(tenant)
                .filter(idempotency_key=key)
                .select_related("configuration")
                .first()
            )
            if prior_audit is not None:
                if prior_audit.new_value != normalized:
                    raise MDMDomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was already used for another configuration.",
                        http_status=409,
                    )
                return prior_audit.configuration
            current = MasterDataConfiguration.objects.for_tenant(tenant).select_for_update().first()
            if current is None:
                if expected_version not in (None, 0):
                    raise MDMDomainError(
                        "CONFIGURATION_VERSION_CONFLICT", "Configuration does not exist.", http_status=409
                    )
                current = MasterDataConfiguration.objects.create(
                    tenant_id=tenant,
                    document=normalized,
                    version=1,
                    created_by=actor,
                    updated_by=actor,
                )
                previous: dict[str, object] = {}
            else:
                if expected_version is not None and current.version != expected_version:
                    raise MDMDomainError(
                        "CONFIGURATION_VERSION_CONFLICT",
                        "Configuration changed after it was loaded.",
                        http_status=409,
                    )
                previous = deepcopy(current.document)
                current.document = normalized
                current.version += 1
                current.updated_by = actor
                current.save(update_fields=["document", "version", "updated_by", "updated_at"])
            MasterDataConfigurationVersion.objects.create(
                tenant_id=tenant,
                configuration=current,
                version=current.version,
                prior_value=previous,
                new_value=normalized,
                actor_id=actor,
                correlation_id=correlation_id,
                idempotency_key=key,
                change_type=change_type,
                reason=reason_value,
            )
            _emit(
                tenant,
                "mdm.configuration.changed",
                "master_data_configuration",
                current.id,
                actor,
                idempotency_key=key,
                payload={
                    "version": current.version,
                    "change_type": change_type,
                    "request_fingerprint": _fingerprint(normalized),
                },
            )
            return current

    @classmethod
    def rollback(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        version: int,
        idempotency_key: str,
        reason: str,
    ) -> MasterDataConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            target = MasterDataConfigurationVersion.objects.for_tenant(tenant).filter(version=version).first()
            if target is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Configuration version not found.", http_status=404)
            current = MasterDataConfiguration.objects.for_tenant(tenant).first()
            expected = current.version if current is not None else None
            return cls.write(
                tenant,
                actor_id,
                document=target.new_value,
                idempotency_key=idempotency_key,
                reason=reason,
                expected_version=expected,
                change_type="rollback",
            )


def _configuration_section(tenant_id: UUID, name: str) -> dict[str, object]:
    section = ConfigurationService.get_effective(tenant_id).get(name)
    if not isinstance(section, dict):
        raise MDMDomainError(
            "CONFIGURATION_UNAVAILABLE",
            f"The required {name} policy is unavailable.",
            http_status=503,
        )
    return section


class EntityTypeService:
    @staticmethod
    def create_type(
        tenant_id: UUID,
        actor_id: UUID,
        *,
        key: str,
        display_name: str,
        description: str = "",
        json_schema: Mapping[str, object],
        required_fields: Sequence[object] = (),
        sensitive_fields: Sequence[object] = (),
        searchable_fields: Sequence[object] = (),
        owner_module: str = "master_data_management",
        idempotency_key: str,
        is_system: bool = False,
        metadata: Mapping[str, object] | None = None,
    ) -> MasterEntityType:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        schema_policy = _configuration_section(tenant, "schema_policy")
        limits = _configuration_section(tenant, "limits")
        maximum_bytes = int(schema_policy["max_payload_bytes"])
        path_pattern = re.compile(str(schema_policy["field_path_pattern"]))
        normalized_key = _text(
            key,
            "key",
            maximum=int(schema_policy["entity_type_key_max_length"]),
        )
        if not re.fullmatch(str(schema_policy["entity_type_key_pattern"]), normalized_key):
            raise MDMDomainError("INVALID_ENTITY_TYPE_KEY", "key must be a lowercase snake-case identifier.")
        values = {
            "key": normalized_key,
            "display_name": _text(display_name, "display_name", maximum=int(limits["display_name_max"])),
            "description": _text(
                description,
                "description",
                maximum=int(limits["description_max"]),
                blank=True,
            ),
            "json_schema": _validate_schema(
                json_schema,
                allowed_keywords=frozenset(
                    str(item) for item in schema_policy["allowed_json_schema_keywords"]  # type: ignore[union-attr]
                ),
                maximum_bytes=maximum_bytes,
            ),
            "required_fields": _paths(required_fields, "required_fields", pattern=path_pattern),
            "sensitive_fields": _paths(sensitive_fields, "sensitive_fields", pattern=path_pattern),
            "searchable_fields": _paths(searchable_fields, "searchable_fields", pattern=path_pattern),
            "owner_module": _text(owner_module, "owner_module", maximum=int(limits["owner_module_max"])),
            "metadata": _object(metadata or {}, "metadata", maximum_bytes=maximum_bytes),
        }
        fingerprint = _fingerprint(values)
        started = time.monotonic()
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.entity_type.created", idempotency_key, fingerprint)
            if receipt:
                return MasterEntityType.objects.for_tenant(tenant).get(pk=receipt)
            if MasterEntityType.objects.for_tenant(tenant).filter(key=normalized_key).exists():
                raise MDMDomainError(
                    "ENTITY_TYPE_KEY_EXISTS", "An entity type with this key already exists.", http_status=409
                )
            entity_type = MasterEntityType(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                is_system=is_system,
                **values,
            )
            _clean(entity_type)
            entity_type.save()
            _emit(
                tenant,
                "mdm.entity_type.created",
                "master_entity_type",
                entity_type.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "entity_type_key": entity_type.key,
                    "schema_version": entity_type.schema_version,
                    "request_fingerprint": fingerprint,
                },
            )
        _log("entity_type.create", tenant, actor, entity_type, started, "succeeded")
        return entity_type

    @staticmethod
    def update_type(
        tenant_id: UUID,
        actor_id: UUID,
        type_id: UUID,
        *,
        expected_schema_version: int,
        changes: Mapping[str, object],
        idempotency_key: str,
    ) -> MasterEntityType:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(type_id, "type_id"),
        )
        schema_policy = _configuration_section(tenant, "schema_policy")
        limits = _configuration_section(tenant, "limits")
        maximum_bytes = int(schema_policy["max_payload_bytes"])
        path_pattern = re.compile(str(schema_policy["field_path_pattern"]))
        allowed = {
            "display_name",
            "description",
            "json_schema",
            "required_fields",
            "sensitive_fields",
            "searchable_fields",
            "metadata",
            "is_active",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise MDMDomainError(
                "VALIDATION_ERROR",
                "Unsupported entity type changes.",
                detail={key: "Unknown field." for key in sorted(unknown)},
            )
        started = time.monotonic()
        fingerprint = _fingerprint(
            {"type_id": str(identifier), "expected_schema_version": expected_schema_version, "changes": dict(changes)}
        )
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.entity_type.updated", idempotency_key, fingerprint)
            if receipt:
                return MasterEntityType.objects.for_tenant(tenant).get(pk=receipt)
            entity_type = (
                MasterEntityType.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if entity_type is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity type not found.", http_status=404)
            if entity_type.schema_version != expected_schema_version:
                raise MDMDomainError("SCHEMA_VERSION_CONFLICT", "Entity type schema version changed.", http_status=409)
            before = {name: getattr(entity_type, name) for name in allowed}
            for name, value in changes.items():
                if name == "json_schema":
                    value = _validate_schema(
                        value,
                        allowed_keywords=frozenset(
                            str(item)
                            for item in schema_policy["allowed_json_schema_keywords"]  # type: ignore[union-attr]
                        ),
                        maximum_bytes=maximum_bytes,
                    )
                elif name in {"required_fields", "sensitive_fields", "searchable_fields"}:
                    value = _paths(value, name, pattern=path_pattern)  # type: ignore[arg-type]
                elif name == "metadata":
                    value = _object(value, name, maximum_bytes=maximum_bytes)
                elif name in {"display_name", "description"}:
                    value = _text(
                        value,
                        name,
                        maximum=int(limits["display_name_max" if name == "display_name" else "description_max"]),
                        blank=name == "description",
                    )
                setattr(entity_type, name, value)
            schema_fields = {"json_schema", "required_fields", "sensitive_fields", "searchable_fields"}
            if schema_fields.intersection(changes):
                entity_type.schema_version += 1
            entity_type.updated_by = actor
            _clean(entity_type)
            entity_type.save()
            changed = sorted(name for name in changes if before[name] != getattr(entity_type, name))
            _emit(
                tenant,
                "mdm.entity_type.updated",
                "master_entity_type",
                entity_type.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "changed_fields": changed,
                    "schema_version": entity_type.schema_version,
                    "request_fingerprint": fingerprint,
                },
            )
        _log("entity_type.update", tenant, actor, entity_type, started, "succeeded")
        return entity_type

    @staticmethod
    def deactivate_type(
        tenant_id: UUID, actor_id: UUID, type_id: UUID, *, reason: str, idempotency_key: str
    ) -> MasterEntityType:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(type_id, "type_id"),
        )
        reason_value = _text(
            reason,
            "reason",
            maximum=int(_configuration_section(tenant, "limits")["reason_max"]),
        )
        fingerprint = _fingerprint({"type_id": str(identifier), "reason": reason_value})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.entity_type.deactivated", idempotency_key, fingerprint)
            if receipt:
                return MasterEntityType.objects.for_tenant(tenant).get(pk=receipt)
            entity_type = (
                MasterEntityType.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if entity_type is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity type not found.", http_status=404)
            if entity_type.is_system:
                # Built-ins are deactivated, never deleted; the guard is only against deletion.
                entity_type.is_active = False
            else:
                entity_type.is_active = False
            entity_type.updated_by = actor
            entity_type.save(update_fields=["is_active", "updated_by", "updated_at"])
            _emit(
                tenant,
                "mdm.entity_type.deactivated",
                "master_entity_type",
                entity_type.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "status": "inactive",
                    "reason_code": "STEWARD_DEACTIVATED",
                    "request_fingerprint": fingerprint,
                },
            )
            return entity_type

    @classmethod
    def seed_builtin_types(cls, tenant_id: UUID, actor_id: UUID) -> tuple[MasterEntityType, ...]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        definitions = _configuration_section(tenant, "schema_policy").get("builtin_entity_types")
        if not isinstance(definitions, list):
            raise MDMDomainError(
                "CONFIGURATION_UNAVAILABLE",
                "Built-in entity type definitions are unavailable.",
                http_status=503,
            )
        seeded: list[MasterEntityType] = []
        with tenant_context(tenant):
            for definition in definitions:
                if not isinstance(definition, Mapping):
                    raise MDMDomainError(
                        "INVALID_CONFIGURATION",
                        "A built-in entity type definition must be an object.",
                    )
                key = str(definition["key"])
                existing = MasterEntityType.objects.for_tenant(tenant).filter(key=key).first()
                if existing:
                    seeded.append(existing)
                    continue
                properties = definition["properties"]
                required = definition["required"]
                seeded.append(
                    cls.create_type(
                        tenant,
                        actor,
                        key=key,
                        display_name=str(definition["display_name"]),
                        description=f"Built-in {key} master record.",
                        json_schema={
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        },
                        required_fields=required,  # type: ignore[arg-type]
                        sensitive_fields=definition["sensitive"],  # type: ignore[arg-type]
                        searchable_fields=["name"],
                        owner_module="master_data_management",
                        idempotency_key=f"seed-builtin:{key}",
                        is_system=True,
                        metadata={"template_version": 1},
                    )
                )
        return tuple(seeded)


class DataQualityService:
    @staticmethod
    def validate_payload(tenant_id: UUID, entity_type_id: UUID, data: Mapping[str, object]) -> ValidationReport:
        tenant, identifier = _uuid(tenant_id, "tenant_id"), _uuid(entity_type_id, "entity_type_id")
        schema_policy = _configuration_section(tenant, "schema_policy")
        quality_policy = _configuration_section(tenant, "quality")
        payload = _object(
            data,
            "data",
            maximum_bytes=int(schema_policy["max_payload_bytes"]),
        )
        missing_values = quality_policy["missing_values"]
        findings: list[ValidationFinding] = []
        with tenant_context(tenant):
            entity_type = (
                MasterEntityType.objects.for_tenant(tenant)
                .filter(pk=identifier, is_deleted=False, is_active=True)
                .first()
            )
            if entity_type is None:
                raise MDMDomainError("ENTITY_TYPE_UNAVAILABLE", "Entity type is missing or inactive.", http_status=422)
            validator = Draft202012Validator(entity_type.json_schema, format_checker=FormatChecker())
            for error in sorted(
                validator.iter_errors(payload), key=lambda item: tuple(str(part) for part in item.path)
            ):
                path = ".".join(str(part) for part in error.absolute_path)
                findings.append(ValidationFinding(path, "SCHEMA_VALIDATION", error.message))
            for path in entity_type.required_fields:
                exists, value = _get_path(payload, path)
                if not exists or value in missing_values:  # type: ignore[operator]
                    if not any(item.field_path == path and item.code == "REQUIRED" for item in findings):
                        findings.append(
                            ValidationFinding(path, "REQUIRED", "A required value is missing.", "completeness", "error")
                        )
        return ValidationReport(not findings, True, tuple(findings))

    @staticmethod
    def _rule_finding(tenant_id: UUID, entity: MasterDataEntity, rule: DataQualityRule) -> ValidationFinding | None:
        quality_policy = _configuration_section(tenant_id, "quality")
        missing_values = quality_policy["missing_values"]
        exists, value = _get_path(entity.data, rule.field_path) if rule.field_path else (True, entity.data)
        config = rule.configuration
        failed = False
        code = f"QUALITY_{rule.rule_type.upper()}"
        if rule.rule_type == "required":
            failed = not exists or value in missing_values  # type: ignore[operator]
        elif rule.rule_type == "format":
            pattern = config.get("pattern")
            failed = (
                not exists
                or not isinstance(value, str)
                or not isinstance(pattern, str)
                or re.fullmatch(pattern, value) is None
            )
        elif rule.rule_type == "range":
            try:
                numeric = Decimal(str(value))
                failed = (
                    not exists
                    or ("minimum" in config and numeric < Decimal(str(config["minimum"])))
                    or ("maximum" in config and numeric > Decimal(str(config["maximum"])))
                )
            except Exception:
                failed = True
        elif rule.rule_type == "uniqueness":
            if not exists:
                failed = False
            else:
                nested: dict[str, object] = {}
                _set_path(nested, rule.field_path, value)
                failed = (
                    MasterDataEntity.objects.for_tenant(tenant_id)
                    .filter(
                        entity_type=entity.entity_type,
                        is_deleted=False,
                        data__contains=nested,
                    )
                    .exclude(pk=entity.pk)
                    .exists()
                )
        elif rule.rule_type == "referential":
            target_key = config.get("entity_type_key")
            target_field = config.get(
                "target_field",
                quality_policy["referential_target_field_default"],
            )
            query = {str(target_field): value, "entity_type__key": target_key, "is_deleted": False}
            failed = not exists or not MasterDataEntity.objects.for_tenant(tenant_id).filter(**query).exists()
        elif rule.rule_type == "timeliness":
            max_age = int(
                config.get(
                    "max_age_days",
                    quality_policy["timeliness_max_age_days_default"],
                )
            )
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                failed = timezone.is_naive(parsed) or parsed < timezone.now() - timedelta(days=max_age)
            except (TypeError, ValueError):
                failed = True
        if not failed:
            return None
        return ValidationFinding(
            rule.field_path, code, f"Quality rule '{rule.name}' failed.", rule.dimension, rule.severity, rule.id
        )

    @classmethod
    def evaluate_entity(
        cls, tenant_id: UUID, actor_id: UUID, entity_id: UUID, *, idempotency_key: str
    ) -> QualityReport:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_id, "entity_id"),
        )
        quality_policy = _configuration_section(tenant, "quality")
        fingerprint = _fingerprint({"entity_id": str(identifier), "operation": "quality_score"})
        started = time.monotonic()
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(
                tenant,
                "mdm.entity.quality_scored",
                idempotency_key,
                fingerprint,
            )
            if receipt:
                event = (
                    OutboxEvent.objects.for_tenant(tenant)
                    .filter(
                        event_type="mdm.entity.quality_scored",
                        payload__causation_id=idempotency_key,
                    )
                    .order_by("created_at")
                    .first()
                )
                if event is None:  # Defensive: receipt and event are the same row.
                    raise MDMDomainError(
                        "IDEMPOTENCY_RECEIPT_MISSING",
                        "The quality evaluation receipt is unavailable.",
                        http_status=503,
                    )
                stored = event.payload.get("payload", {})
                raw_dimensions = stored.get("dimension_counts", {})
                dimensions = (
                    {str(name): Decimal(str(value)) for name, value in raw_dimensions.items()}
                    if isinstance(raw_dimensions, Mapping)
                    else {}
                )
                raw_findings = stored.get("finding_summaries", [])
                findings = (
                    tuple(
                        ValidationFinding(
                            field_path=str(item.get("field_path", "")),
                            code=str(item.get("code", "VALIDATION_FAILED")),
                            message=str(item.get("message", "Quality rule failed.")),
                            dimension=str(item.get("dimension", "conformity")),
                            severity=str(item.get("severity", "error")),
                            rule_id=_uuid(item["rule_id"], "rule_id") if item.get("rule_id") else None,
                        )
                        for item in raw_findings
                        if isinstance(item, Mapping)
                    )
                    if isinstance(raw_findings, Sequence)
                    else ()
                )
                return QualityReport(
                    receipt,
                    bool(stored.get("evaluated", True)),
                    Decimal(str(stored["quality_score"])) if stored.get("quality_score") is not None else None,
                    dimensions,
                    int(stored.get("issue_count", 0)),
                    findings,
                )
            entity = (
                MasterDataEntity.objects.for_tenant(tenant)
                .select_for_update()
                .select_related("entity_type")
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if entity is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity not found.", http_status=404)
            rules = list(
                DataQualityRule.objects.for_tenant(tenant)
                .filter(entity_type=entity.entity_type, is_active=True, is_deleted=False)
                .order_by("id")
            )
            if not rules:
                evaluated_without_rules = bool(quality_policy["no_rules_evaluated"])
                configured_score = quality_policy["no_rules_score"]
                no_rules_score = Decimal(str(configured_score)) if configured_score is not None else None
                no_rules_issue_count = int(quality_policy["no_rules_issue_count"])
                _emit(
                    tenant,
                    "mdm.entity.quality_scored",
                    "master_data_entity",
                    entity.id,
                    actor,
                    idempotency_key=idempotency_key,
                    payload={
                        "quality_score": no_rules_score,
                        "evaluated": evaluated_without_rules,
                        "issue_count": no_rules_issue_count,
                        "dimension_counts": {},
                        "finding_summaries": [],
                        "entity_type_id": entity.entity_type_id,
                        "request_fingerprint": fingerprint,
                    },
                )
                return QualityReport(
                    entity.id,
                    evaluated_without_rules,
                    no_rules_score,
                    {},
                    no_rules_issue_count,
                    (),
                )
            findings = [finding for rule in rules if (finding := cls._rule_finding(tenant, entity, rule)) is not None]
            failed_ids = {finding.rule_id for finding in findings}
            dimension_weight: dict[str, Decimal] = defaultdict(Decimal)
            dimension_passed: dict[str, Decimal] = defaultdict(Decimal)
            total_weight = Decimal("0")
            passed_weight = Decimal("0")
            for rule in rules:
                weight = Decimal(rule.weight)
                total_weight += weight
                dimension_weight[rule.dimension] += weight
                if rule.id not in failed_ids:
                    passed_weight += weight
                    dimension_passed[rule.dimension] += weight
            scale = Decimal(str(quality_policy["score_scale"]))
            quantum = Decimal(1).scaleb(-int(quality_policy["score_decimal_places"]))
            score = ((passed_weight / total_weight) * scale).quantize(quantum, rounding=ROUND_HALF_UP)
            dimensions = {
                name: ((dimension_passed[name] / weight) * scale).quantize(quantum, rounding=ROUND_HALF_UP)
                for name, weight in sorted(dimension_weight.items())
            }
            active_issue_keys: set[tuple[UUID, str]] = set()
            for finding in findings:
                if finding.rule_id is None:
                    continue
                active_issue_keys.add((finding.rule_id, finding.field_path))
                issue = (
                    DataQualityIssue.objects.for_tenant(tenant)
                    .filter(
                        entity=entity,
                        rule_id=finding.rule_id,
                        field_path=finding.field_path,
                        status__in=("open", "in_review"),
                    )
                    .first()
                )
                if issue is None:
                    issue = DataQualityIssue.objects.create(
                        tenant_id=tenant,
                        entity=entity,
                        rule_id=finding.rule_id,
                        field_path=finding.field_path,
                        dimension=finding.dimension,
                        severity=finding.severity,
                        message=finding.message,
                        evidence={"code": finding.code},
                        created_by=actor,
                        updated_by=actor,
                    )
                    _emit(
                        tenant,
                        "mdm.quality_issue.opened",
                        "data_quality_issue",
                        issue.id,
                        actor,
                        payload={"entity_type_id": entity.entity_type_id, "status": issue.status},
                    )
                else:
                    issue.message = finding.message
                    issue.severity = finding.severity
                    issue.updated_by = actor
                    issue.save(update_fields=["message", "severity", "updated_by", "updated_at"])
            if bool(quality_policy["auto_resolve_passing"]):
                stale = DataQualityIssue.objects.for_tenant(tenant).filter(
                    entity=entity, status__in=("open", "in_review")
                )
                for issue in stale:
                    if issue.rule_id is not None and (issue.rule_id, issue.field_path) not in active_issue_keys:
                        issue = ISSUE_MACHINE.apply(
                            issue,
                            "resolve",
                            tenant_id=tenant,
                            transition_key=f"quality-pass:{idempotency_key}:{issue.id}",
                            context={
                                "actor_id": actor,
                                "resolution": "Automatically resolved after a passing evaluation.",
                                "resolved_at": timezone.now(),
                            },
                            metadata={"actor_id": str(actor), "correlation_id": get_correlation_id()},
                        )
            entity.quality_score = score
            entity.quality_evaluated_at = timezone.now()
            entity.updated_by = actor
            entity.save(update_fields=["quality_score", "quality_evaluated_at", "updated_by", "updated_at"])
            _emit(
                tenant,
                "mdm.entity.quality_scored",
                "master_data_entity",
                entity.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "quality_score": score,
                    "evaluated": True,
                    "issue_count": len(findings),
                    "dimension_counts": {key: str(value) for key, value in dimensions.items()},
                    "finding_summaries": [asdict(finding) for finding in findings],
                    "entity_type_id": entity.entity_type_id,
                    "request_fingerprint": fingerprint,
                },
            )
        _log("entity.quality_score", tenant, actor, entity, started, "succeeded")
        return QualityReport(entity.id, True, score, dimensions, len(findings), tuple(findings))

    @staticmethod
    def enqueue_quality_scan(
        tenant_id: UUID, actor_id: UUID, *, entity_type_id: UUID, idempotency_key: str
    ) -> AsyncJob:
        tenant, actor, entity_type = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_type_id, "entity_type_id"),
        )
        with tenant_context(tenant):
            if not MasterEntityType.objects.for_tenant(tenant).filter(pk=entity_type, is_deleted=False).exists():
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity type not found.", http_status=404)
            return _enqueue_checked(
                tenant,
                actor,
                QUALITY_SCAN_COMMAND,
                {"entity_type_id": str(entity_type)},
                f"mdm:quality:{idempotency_key}",
            )

    @classmethod
    def execute_quality_scan(
        cls, tenant_id: UUID, actor_id: UUID, *, entity_type_id: UUID, job_id: UUID
    ) -> dict[str, object]:
        """Evaluate every live entity of a type for one durable job delivery."""

        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        type_id, durable_job = _uuid(entity_type_id, "entity_type_id"), _uuid(job_id, "job_id")
        with tenant_context(tenant):
            if (
                not MasterEntityType.objects.for_tenant(tenant)
                .filter(
                    pk=type_id,
                    is_deleted=False,
                )
                .exists()
            ):
                raise MDMDomainError(
                    "RESOURCE_NOT_FOUND",
                    "Entity type not found.",
                    http_status=404,
                )
            entity_ids = list(
                MasterDataEntity.objects.for_tenant(tenant)
                .filter(entity_type_id=type_id, is_deleted=False)
                .order_by("id")
                .values_list("id", flat=True)
            )
        evaluated = 0
        not_evaluated = 0
        issue_count = 0
        for entity_id in entity_ids:
            report = cls.evaluate_entity(
                tenant,
                actor,
                entity_id,
                idempotency_key=f"job:{durable_job}:entity:{entity_id}",
            )
            if report.evaluated:
                evaluated += 1
                issue_count += report.issue_count
            else:
                not_evaluated += 1
        return {
            "job_id": str(durable_job),
            "entity_type_id": str(type_id),
            "entity_count": len(entity_ids),
            "evaluated_count": evaluated,
            "not_evaluated_count": not_evaluated,
            "issue_count": issue_count,
        }

    @staticmethod
    def assign_issue(
        tenant_id: UUID, actor_id: UUID, issue_id: UUID, assignee_id: UUID, *, transition_key: str
    ) -> DataQualityIssue:
        return DataQualityService._transition_issue(
            tenant_id, actor_id, issue_id, "assign", transition_key, assignee_id=assignee_id
        )

    @staticmethod
    def resolve_issue(
        tenant_id: UUID, actor_id: UUID, issue_id: UUID, *, resolution: str, transition_key: str
    ) -> DataQualityIssue:
        return DataQualityService._transition_issue(
            tenant_id, actor_id, issue_id, "resolve", transition_key, resolution=resolution
        )

    @staticmethod
    def waive_issue(
        tenant_id: UUID, actor_id: UUID, issue_id: UUID, *, resolution: str, transition_key: str
    ) -> DataQualityIssue:
        return DataQualityService._transition_issue(
            tenant_id, actor_id, issue_id, "waive", transition_key, resolution=resolution
        )

    @staticmethod
    def _transition_issue(
        tenant_id: UUID,
        actor_id: UUID,
        issue_id: UUID,
        command: str,
        transition_key: str,
        *,
        assignee_id: UUID | None = None,
        resolution: str | None = None,
    ) -> DataQualityIssue:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(issue_id, "issue_id"),
        )
        event = {
            "assign": "mdm.quality_issue.assigned",
            "resolve": "mdm.quality_issue.resolved",
            "waive": "mdm.quality_issue.waived",
        }[command]
        fingerprint = _fingerprint(
            {
                "issue_id": str(identifier),
                "command": command,
                "assignee_id": str(assignee_id) if assignee_id else None,
                "resolution": resolution,
            }
        )
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, event, transition_key, fingerprint)
            if receipt:
                return DataQualityIssue.objects.for_tenant(tenant).get(pk=receipt)
            issue = DataQualityIssue.objects.for_tenant(tenant).select_for_update().filter(pk=identifier).first()
            if issue is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Quality issue not found.", http_status=404)
            if resolution is not None:
                resolution = _text(
                    resolution,
                    "resolution",
                    maximum=int(_configuration_section(tenant, "limits")["resolution_max"]),
                )
            try:
                context: dict[str, object] = {"actor_id": actor}
                if assignee_id is not None:
                    context["assignee_id"] = _uuid(assignee_id, "assignee_id")
                if resolution is not None:
                    context["resolution"] = resolution
                    context["resolved_at"] = timezone.now()
                issue = ISSUE_MACHINE.apply(
                    issue,
                    command,
                    tenant_id=tenant,
                    transition_key=transition_key,
                    context=context,
                    metadata={"actor_id": str(actor), "correlation_id": get_correlation_id()},
                )
            except StateMachineError as exc:
                raise MDMDomainError(
                    "ILLEGAL_TRANSITION", "The quality issue transition is not allowed.", http_status=409
                ) from exc
            _emit(
                tenant,
                event,
                "data_quality_issue",
                issue.id,
                actor,
                idempotency_key=transition_key,
                payload={"status": issue.status, "request_fingerprint": fingerprint},
            )
            return issue


class MasterEntityService:
    @staticmethod
    def create_entity(
        tenant_id: UUID,
        actor_id: UUID,
        *,
        entity_type_id: UUID,
        entity_code: str,
        entity_name: str,
        data: Mapping[str, object],
        source_system: str | None = None,
        source_record_id: str = "",
        idempotency_key: str,
    ) -> MasterDataEntity:
        tenant, actor, type_id = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_type_id, "entity_type_id"),
        )
        limits = _configuration_section(tenant, "limits")
        schema_policy = _configuration_section(tenant, "schema_policy")
        entity_defaults = _configuration_section(tenant, "entity_defaults")
        payload = _object(
            data,
            "data",
            maximum_bytes=int(schema_policy["max_payload_bytes"]),
        )
        report = DataQualityService.validate_payload(tenant, type_id, payload)
        if not report.valid:
            raise MDMDomainError(
                "ENTITY_SCHEMA_INVALID",
                "Entity data does not satisfy its schema.",
                detail={"findings": [asdict(finding) for finding in report.findings]},
            )
        values = {
            "entity_type_id": str(type_id),
            "entity_code": _text(entity_code, "entity_code", maximum=int(limits["entity_code_max"])),
            "entity_name": _text(entity_name, "entity_name", maximum=int(limits["entity_name_max"])),
            "data": payload,
            "source_system": _text(
                source_system if source_system is not None else entity_defaults["source_system"],
                "source_system",
                maximum=int(limits["source_system_max"]),
            ),
            "source_record_id": _text(
                source_record_id,
                "source_record_id",
                maximum=int(limits["source_record_id_max"]),
                blank=True,
            ),
        }
        fingerprint = _fingerprint(values)
        started = time.monotonic()
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.entity.created", idempotency_key, fingerprint)
            if receipt:
                return MasterDataEntity.objects.for_tenant(tenant).select_related("entity_type").get(pk=receipt)
            entity_type = (
                MasterEntityType.objects.for_tenant(tenant).filter(pk=type_id, is_active=True, is_deleted=False).first()
            )
            if entity_type is None:
                raise MDMDomainError("ENTITY_TYPE_UNAVAILABLE", "Entity type is missing or inactive.")
            entity = MasterDataEntity(
                tenant_id=tenant,
                entity_type=entity_type,
                entity_code=values["entity_code"],
                entity_name=values["entity_name"],
                data=payload,
                source_system=values["source_system"],
                source_record_id=values["source_record_id"],
                created_by=actor,
                updated_by=actor,
                status="active",
                version=1,
            )
            _clean(entity)
            try:
                entity.save()
            except IntegrityError as exc:
                raise MDMDomainError(
                    "ENTITY_CODE_EXISTS", "An active entity already uses this type and code.", http_status=409
                ) from exc
            _save_version(entity, actor, changed_fields=["entity_code", "entity_name", "data"], reason="Entity created")
            _emit(
                tenant,
                "mdm.entity.created",
                "master_data_entity",
                entity.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "entity_type_id": entity.entity_type_id,
                    "version": entity.version,
                    "changed_fields": ["entity_code", "entity_name", "data"],
                    "request_fingerprint": fingerprint,
                },
            )
            DataQualityService.evaluate_entity(tenant, actor, entity.id, idempotency_key=f"{idempotency_key}:quality")
            entity.refresh_from_db()
        _log("entity.create", tenant, actor, entity, started, "succeeded")
        return entity

    @staticmethod
    def update_entity(
        tenant_id: UUID,
        actor_id: UUID,
        entity_id: UUID,
        *,
        expected_version: int,
        changes: Mapping[str, object],
        reason: str,
        idempotency_key: str,
    ) -> MasterDataEntity:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_id, "entity_id"),
        )
        limits = _configuration_section(tenant, "limits")
        schema_policy = _configuration_section(tenant, "schema_policy")
        lifecycle = _configuration_section(tenant, "lifecycle")
        unknown = set(changes) - {"entity_code", "entity_name", "data", "source_system", "source_record_id"}
        protected = set(changes) & PROTECTED_ENTITY_FIELDS
        if unknown or protected:
            fields = unknown | protected
            raise MDMDomainError(
                "VALIDATION_ERROR",
                "Unsupported entity changes.",
                detail={key: "Field is not writable." for key in sorted(fields)},
            )
        _text(reason, "reason", maximum=int(limits["reason_max"]))
        fingerprint = _fingerprint(
            {
                "entity_id": str(identifier),
                "expected_version": expected_version,
                "changes": dict(changes),
                "reason": reason,
            }
        )
        started = time.monotonic()
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.entity.updated", idempotency_key, fingerprint)
            if receipt:
                return MasterDataEntity.objects.for_tenant(tenant).select_related("entity_type").get(pk=receipt)
            entity = (
                MasterDataEntity.objects.for_tenant(tenant)
                .select_for_update()
                .select_related("entity_type")
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if entity is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity not found.", http_status=404)
            if entity.version != expected_version:
                raise MDMDomainError("VERSION_CONFLICT", "Entity version changed.", http_status=409)
            if entity.status == "merged" and not bool(lifecycle["merged_entities_editable"]):
                raise MDMDomainError(
                    "MERGED_ENTITY_IMMUTABLE", "Merged source records cannot be edited.", http_status=409
                )
            old_data = dict(entity.data)
            changed_fields: list[str] = []
            for name, value in changes.items():
                if name == "data":
                    value = _object(
                        value,
                        "data",
                        maximum_bytes=int(schema_policy["max_payload_bytes"]),
                    )
                    report = DataQualityService.validate_payload(tenant, entity.entity_type_id, value)
                    if not report.valid:
                        raise MDMDomainError(
                            "ENTITY_SCHEMA_INVALID",
                            "Entity data does not satisfy its schema.",
                            detail={"findings": [asdict(finding) for finding in report.findings]},
                        )
                    changed_fields.extend(_changed_paths(old_data, value))
                else:
                    maximum = int(
                        limits[
                            {
                                "entity_code": "entity_code_max",
                                "entity_name": "entity_name_max",
                                "source_system": "source_system_max",
                                "source_record_id": "source_record_id_max",
                            }[name]
                        ]
                    )
                    value = _text(value, name, maximum=maximum, blank=name == "source_record_id")
                    if getattr(entity, name) != value:
                        changed_fields.append(name)
                setattr(entity, name, value)
            entity.version += 1
            entity.updated_by = actor
            _clean(entity)
            entity.save()
            _save_version(entity, actor, changed_fields=sorted(set(changed_fields)), reason=reason)
            _emit(
                tenant,
                "mdm.entity.updated",
                "master_data_entity",
                entity.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "entity_type_id": entity.entity_type_id,
                    "version": entity.version,
                    "changed_fields": sorted(set(changed_fields)),
                    "request_fingerprint": fingerprint,
                },
            )
            DataQualityService.evaluate_entity(tenant, actor, entity.id, idempotency_key=f"{idempotency_key}:quality")
            entity.refresh_from_db()
        _log("entity.update", tenant, actor, entity, started, "succeeded")
        return entity

    @staticmethod
    def archive_entity(
        tenant_id: UUID, actor_id: UUID, entity_id: UUID, *, expected_version: int, reason: str, idempotency_key: str
    ) -> MasterDataEntity:
        return MasterEntityService._lifecycle(
            tenant_id, actor_id, entity_id, "archive", expected_version, reason, idempotency_key
        )

    @staticmethod
    def restore_entity(
        tenant_id: UUID, actor_id: UUID, entity_id: UUID, *, expected_version: int, reason: str, idempotency_key: str
    ) -> MasterDataEntity:
        return MasterEntityService._lifecycle(
            tenant_id, actor_id, entity_id, "restore", expected_version, reason, idempotency_key
        )

    @staticmethod
    def _lifecycle(
        tenant_id: UUID, actor_id: UUID, entity_id: UUID, command: str, expected_version: int, reason: str, key: str
    ) -> MasterDataEntity:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_id, "entity_id"),
        )
        reason_value = _text(
            reason,
            "reason",
            maximum=int(_configuration_section(tenant, "limits")["reason_max"]),
        )
        event = "mdm.entity.archived" if command == "archive" else "mdm.entity.restored"
        fingerprint = _fingerprint(
            {
                "entity_id": str(identifier),
                "command": command,
                "expected_version": expected_version,
                "reason": reason_value,
            }
        )
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, event, key, fingerprint)
            if receipt:
                return MasterDataEntity.objects.for_tenant(tenant).select_related("entity_type").get(pk=receipt)
            entity = (
                MasterDataEntity.objects.for_tenant(tenant)
                .select_for_update()
                .select_related("entity_type")
                .filter(pk=identifier)
                .first()
            )
            if entity is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity not found.", http_status=404)
            if entity.version != expected_version:
                raise MDMDomainError("VERSION_CONFLICT", "Entity version changed.", http_status=409)
            if (
                command == "restore"
                and MasterDataEntity.objects.for_tenant(tenant)
                .filter(entity_type=entity.entity_type, entity_code=entity.entity_code, is_deleted=False)
                .exclude(pk=entity.pk)
                .exists()
            ):
                raise MDMDomainError(
                    "RESTORE_CODE_CONFLICT", "Another active entity now uses this business key.", http_status=409
                )
            if command == "archive":
                DataQualityService.evaluate_entity(
                    tenant,
                    actor,
                    entity.id,
                    idempotency_key=f"{key}:quality",
                )
                entity.refresh_from_db()
            try:
                entity = ENTITY_MACHINE.apply(
                    entity,
                    command,
                    tenant_id=tenant,
                    transition_key=key,
                    context={"actor_id": actor, "deleted_at": timezone.now()},
                    metadata={"actor_id": str(actor), "reason": reason, "correlation_id": get_correlation_id()},
                )
            except StateMachineError as exc:
                raise MDMDomainError(
                    "ILLEGAL_TRANSITION", "The entity lifecycle transition is not allowed.", http_status=409
                ) from exc
            entity.version += 1
            entity.updated_by = actor
            if command == "archive":
                entity.is_deleted = True
                entity.deleted_at = timezone.now()
            else:
                entity.is_deleted = False
                entity.deleted_at = None
            entity.save(update_fields=["version", "updated_by", "is_deleted", "deleted_at", "updated_at"])
            _save_version(entity, actor, changed_fields=["status", "is_deleted", "deleted_at"], reason=reason)
            _emit(
                tenant,
                event,
                "master_data_entity",
                entity.id,
                actor,
                idempotency_key=key,
                payload={
                    "status": entity.status,
                    "version": entity.version,
                    "entity_type_id": entity.entity_type_id,
                    "request_fingerprint": fingerprint,
                },
            )
            if command == "restore":
                DataQualityService.evaluate_entity(
                    tenant,
                    actor,
                    entity.id,
                    idempotency_key=f"{key}:quality",
                )
                entity.refresh_from_db()
            return entity

    @staticmethod
    def rollback_to_version(
        tenant_id: UUID,
        actor_id: UUID,
        entity_id: UUID,
        version_number: int,
        *,
        expected_version: int,
        reason: str,
        idempotency_key: str,
    ) -> MasterDataEntity:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_id, "entity_id"),
        )
        reason_value = _text(
            reason,
            "reason",
            maximum=int(_configuration_section(tenant, "limits")["reason_max"]),
        )
        fingerprint = _fingerprint(
            {
                "entity_id": str(identifier),
                "version_number": version_number,
                "expected_version": expected_version,
                "reason": reason_value,
            }
        )
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.entity.rolled_back", idempotency_key, fingerprint)
            if receipt:
                return MasterDataEntity.objects.for_tenant(tenant).select_related("entity_type").get(pk=receipt)
            entity = (
                MasterDataEntity.objects.for_tenant(tenant)
                .select_for_update()
                .select_related("entity_type")
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if entity is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity not found.", http_status=404)
            if entity.version != expected_version:
                raise MDMDomainError("VERSION_CONFLICT", "Entity version changed.", http_status=409)
            version = (
                MasterDataVersion.objects.for_tenant(tenant)
                .filter(entity=entity, version_number=version_number)
                .first()
            )
            if version is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity version not found.", http_status=404)
            entity.entity_code = version.entity_code
            entity.entity_name = version.entity_name
            entity.data = version.data_snapshot
            entity.version += 1
            entity.updated_by = actor
            _clean(entity)
            entity.save()
            _save_version(entity, actor, changed_fields=["entity_code", "entity_name", "data"], reason=reason_value)
            _emit(
                tenant,
                "mdm.entity.rolled_back",
                "master_data_entity",
                entity.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "version": entity.version,
                    "changed_fields": ["entity_code", "entity_name", "data"],
                    "entity_type_id": entity.entity_type_id,
                    "request_fingerprint": fingerprint,
                },
            )
            DataQualityService.evaluate_entity(tenant, actor, entity.id, idempotency_key=f"{idempotency_key}:quality")
            entity.refresh_from_db()
            return entity

    @staticmethod
    def resolve_by_code(
        tenant_id: UUID, entity_type_key: str, entity_code: str, *, golden_only: bool = True
    ) -> MasterDataEntity:
        tenant = _uuid(tenant_id, "tenant_id")
        with tenant_context(tenant):
            queryset = MasterDataEntity.objects.for_tenant(tenant).filter(
                entity_type__key=entity_type_key, entity_code=entity_code, is_deleted=False
            )
            if golden_only:
                queryset = queryset.filter(Q(is_golden=True) | Q(golden_record__isnull=True)).exclude(status="merged")
            entity = queryset.select_related("entity_type", "golden_record").first()
            if entity is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Master entity not found.", http_status=404)
            return entity


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).casefold().strip()
    return " ".join("".join(character if character.isalnum() else " " for character in text).split())


def _soundex(value: object, policy: Mapping[str, object]) -> str:
    normalized = "".join(
        character for character in unicodedata.normalize("NFKD", str(value)).upper() if "A" <= character <= "Z"
    )
    if not normalized:
        return ""
    raw_mapping = policy.get("soundex_mapping")
    if not isinstance(raw_mapping, Mapping):
        raise MDMDomainError("CONFIGURATION_UNAVAILABLE", "Soundex mapping is unavailable.", http_status=503)
    mapping = {str(key): str(code) for key, code in raw_mapping.items()}
    output_length = int(policy["soundex_output_length"])
    output = [normalized[0]]
    previous = mapping.get(normalized[0], "")
    for character in normalized[1:]:
        code = mapping.get(character, "")
        if code and code != previous:
            output.append(code)
        previous = code
    return ("".join(output) + ("0" * output_length))[:output_length]


class MatchingService:
    @staticmethod
    def _validate_rule(
        tenant_id: UUID,
        algorithm: str,
        field_weights: Mapping[str, object],
        blocking_fields: Sequence[object],
        review_threshold: object,
        auto_confirm_threshold: object,
    ) -> tuple[dict[str, str], list[str], Decimal, Decimal]:
        matching = _configuration_section(tenant_id, "matching")
        schema_policy = _configuration_section(tenant_id, "schema_policy")
        if algorithm not in matching["algorithms"]:  # type: ignore[operator]
            raise MDMDomainError("UNSUPPORTED_MATCHING_ALGORITHM", "Unsupported deterministic matching algorithm.")
        if not isinstance(field_weights, Mapping):
            raise MDMDomainError("VALIDATION_ERROR", "field_weights must be an object.")
        if not isinstance(blocking_fields, Sequence) or isinstance(blocking_fields, (str, bytes)):
            raise MDMDomainError("VALIDATION_ERROR", "blocking_fields must be an array.")
        weights: dict[str, Decimal] = {}
        for path, weight in field_weights.items():
            if not isinstance(path, str) or not re.fullmatch(
                str(schema_policy["field_path_pattern"]),
                path,
            ):
                raise MDMDomainError("VALIDATION_ERROR", "field_weights contains an invalid field path.")
            try:
                decimal = Decimal(str(weight))
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise MDMDomainError("VALIDATION_ERROR", "Matching weights must be decimal values.") from exc
            if decimal <= 0:
                raise MDMDomainError("VALIDATION_ERROR", "Matching weights must be positive.")
            weights[path] = decimal
        weight_sum = Decimal(str(matching["weight_sum"]))
        tolerance = Decimal(str(matching["weight_tolerance"]))
        if not weights or abs(sum(weights.values()) - weight_sum) > tolerance:
            raise MDMDomainError("INVALID_MATCH_WEIGHTS", "Matching field weights violate the configured sum.")
        try:
            review, auto = Decimal(str(review_threshold)), Decimal(str(auto_confirm_threshold))
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise MDMDomainError("INVALID_MATCH_THRESHOLDS", "Matching thresholds must be decimal values.") from exc
        minimum = Decimal(str(matching["threshold_min"]))
        maximum = Decimal(str(matching["threshold_max"]))
        if not minimum <= review <= auto <= maximum:
            raise MDMDomainError("INVALID_MATCH_THRESHOLDS", "Matching thresholds violate configured safe bounds.")
        return (
            {key: str(value) for key, value in weights.items()},
            _paths(
                blocking_fields,
                "blocking_fields",
                pattern=re.compile(str(schema_policy["field_path_pattern"])),
            ),
            review,
            auto,
        )

    @classmethod
    def create_rule(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        entity_type_id: UUID,
        name: str,
        algorithm: str,
        field_weights: Mapping[str, object],
        blocking_fields: Sequence[object],
        review_threshold: object,
        auto_confirm_threshold: object,
        is_active: bool = True,
        idempotency_key: str,
    ) -> MatchingRule:
        if not isinstance(is_active, bool):
            raise MDMDomainError("VALIDATION_ERROR", "is_active must be a boolean.")
        tenant, actor, type_id = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_type_id, "entity_type_id"),
        )
        weights, blocks, review, auto = cls._validate_rule(
            tenant,
            algorithm,
            field_weights,
            blocking_fields,
            review_threshold,
            auto_confirm_threshold,
        )
        fingerprint = _fingerprint(
            {
                "entity_type_id": str(type_id),
                "name": name,
                "algorithm": algorithm,
                "field_weights": weights,
                "blocking_fields": blocks,
                "review_threshold": str(review),
                "auto_confirm_threshold": str(auto),
                "is_active": is_active,
            }
        )
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.matching_rule.created", idempotency_key, fingerprint)
            if receipt:
                return MatchingRule.objects.for_tenant(tenant).get(pk=receipt)
            entity_type = MasterEntityType.objects.for_tenant(tenant).filter(pk=type_id, is_deleted=False).first()
            if entity_type is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity type not found.", http_status=404)
            rule = MatchingRule(
                tenant_id=tenant,
                entity_type=entity_type,
                name=_text(
                    name,
                    "name",
                    maximum=int(_configuration_section(tenant, "limits")["display_name_max"]),
                ),
                algorithm=algorithm,
                field_weights=weights,
                blocking_fields=blocks,
                review_threshold=review,
                auto_confirm_threshold=auto,
                is_active=is_active,
                created_by=actor,
                updated_by=actor,
            )
            _clean(rule)
            rule.save()
            _record_matching_rule_version(rule, actor, reason="Matching rule created.")
            _emit(
                tenant,
                "mdm.matching_rule.created",
                "matching_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={"matching_rule_id": rule.id, "entity_type_id": type_id, "request_fingerprint": fingerprint},
            )
            return rule

    @classmethod
    def update_rule(
        cls, tenant_id: UUID, actor_id: UUID, rule_id: UUID, *, changes: Mapping[str, object], idempotency_key: str
    ) -> MatchingRule:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(rule_id, "rule_id"),
        )
        allowed = {
            "name",
            "algorithm",
            "field_weights",
            "blocking_fields",
            "review_threshold",
            "auto_confirm_threshold",
            "is_active",
        }
        if set(changes) - allowed:
            raise MDMDomainError("VALIDATION_ERROR", "Unsupported matching rule changes.")
        fingerprint = _fingerprint({"rule_id": str(identifier), "changes": dict(changes)})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.matching_rule.updated", idempotency_key, fingerprint)
            if receipt:
                return MatchingRule.objects.for_tenant(tenant).get(pk=receipt)
            rule = (
                MatchingRule.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Matching rule not found.", http_status=404)
            values = {
                "algorithm": changes.get("algorithm", rule.algorithm),
                "field_weights": changes.get("field_weights", rule.field_weights),
                "blocking_fields": changes.get("blocking_fields", rule.blocking_fields),
                "review_threshold": changes.get("review_threshold", rule.review_threshold),
                "auto_confirm_threshold": changes.get("auto_confirm_threshold", rule.auto_confirm_threshold),
            }
            weights, blocks, review, auto = cls._validate_rule(tenant, **values)  # type: ignore[arg-type]
            for field in ("name", "is_active"):
                if field in changes:
                    setattr(rule, field, changes[field])
            rule.algorithm, rule.field_weights, rule.blocking_fields = str(values["algorithm"]), weights, blocks
            rule.review_threshold, rule.auto_confirm_threshold, rule.updated_by = review, auto, actor
            _clean(rule)
            rule.save()
            _record_matching_rule_version(
                rule,
                actor,
                reason=f"Matching rule updated: {', '.join(sorted(changes))}.",
            )
            _emit(
                tenant,
                "mdm.matching_rule.updated",
                "matching_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "matching_rule_id": rule.id,
                    "entity_type_id": rule.entity_type_id,
                    "changed_fields": sorted(changes),
                    "request_fingerprint": fingerprint,
                },
            )
            return rule

    @staticmethod
    def deactivate_rule(tenant_id: UUID, actor_id: UUID, rule_id: UUID, *, idempotency_key: str) -> MatchingRule:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(rule_id, "rule_id"),
        )
        fingerprint = _fingerprint({"rule_id": str(identifier), "operation": "deactivate"})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(
                tenant,
                "mdm.matching_rule.deactivated",
                idempotency_key,
                fingerprint,
            )
            if receipt:
                return MatchingRule.objects.for_tenant(tenant).get(pk=receipt)
            rule = (
                MatchingRule.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Matching rule not found.", http_status=404)
            rule.is_active, rule.is_deleted, rule.deleted_at, rule.updated_by = False, True, timezone.now(), actor
            rule.save(update_fields=["is_active", "is_deleted", "deleted_at", "updated_by", "updated_at"])
            _record_matching_rule_version(rule, actor, reason="Matching rule deactivated.")
            _emit(
                tenant,
                "mdm.matching_rule.deactivated",
                "matching_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={"status": "inactive", "matching_rule_id": rule.id, "request_fingerprint": fingerprint},
            )
            return rule

    @staticmethod
    def version_history(tenant_id: UUID, rule_id: UUID) -> QuerySet[MatchingRuleVersion]:
        tenant, identifier = _uuid(tenant_id, "tenant_id"), _uuid(rule_id, "rule_id")
        with tenant_context(tenant):
            if not MatchingRule.objects.for_tenant(tenant).filter(pk=identifier).exists():
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Matching rule not found.", http_status=404)
            return MatchingRuleVersion.objects.for_tenant(tenant).filter(rule_id=identifier).order_by("-version_number")

    @classmethod
    def export_document(cls, tenant_id: UUID, rule_id: UUID) -> dict[str, object]:
        versions = cls.version_history(tenant_id, rule_id)
        latest = versions.first()
        if latest is None:
            raise MDMDomainError("CONFIGURATION_UNAVAILABLE", "Matching rule has no version evidence.", http_status=503)
        return _rule_document("matching-rule", latest.rule_id, latest.version_number, latest.snapshot)

    @classmethod
    def import_document(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        rule_id: UUID,
        *,
        document: object,
        reason: str,
        idempotency_key: str,
    ) -> MatchingRule:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(rule_id, "rule_id"),
        )
        snapshot = _imported_rule_snapshot(tenant, document, kind="matching-rule", expected_rule_id=identifier)
        expected = {
            "entity_type_id",
            "name",
            "algorithm",
            "field_weights",
            "blocking_fields",
            "review_threshold",
            "auto_confirm_threshold",
            "is_active",
            "is_deleted",
        }
        if set(snapshot) != expected:
            raise MDMDomainError("INVALID_RULE_DOCUMENT", "Matching rule snapshot fields are invalid.")
        fingerprint = _fingerprint({"rule_id": str(identifier), "snapshot": snapshot})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.matching_rule.updated", idempotency_key, fingerprint)
            if receipt:
                return MatchingRule.objects.for_tenant(tenant).get(pk=receipt)
            rule = MatchingRule.objects.for_tenant(tenant).select_for_update().filter(pk=identifier).first()
            if rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Matching rule not found.", http_status=404)
            if _uuid(snapshot["entity_type_id"], "entity_type_id") != rule.entity_type_id:
                raise MDMDomainError("INVALID_RULE_DOCUMENT", "A rule import cannot change its entity type.")
            weights, blocks, review, auto = cls._validate_rule(
                tenant,
                str(snapshot["algorithm"]),
                snapshot["field_weights"],  # type: ignore[arg-type]
                snapshot["blocking_fields"],  # type: ignore[arg-type]
                snapshot["review_threshold"],
                snapshot["auto_confirm_threshold"],
            )
            if not isinstance(snapshot["is_active"], bool) or not isinstance(snapshot["is_deleted"], bool):
                raise MDMDomainError("INVALID_RULE_DOCUMENT", "Rule state flags must be booleans.")
            rule.name = _text(
                snapshot["name"],
                "name",
                maximum=int(_configuration_section(tenant, "limits")["display_name_max"]),
            )
            rule.algorithm = str(snapshot["algorithm"])
            rule.field_weights, rule.blocking_fields = weights, blocks
            rule.review_threshold, rule.auto_confirm_threshold = review, auto
            rule.is_deleted = bool(snapshot["is_deleted"])
            rule.is_active = bool(snapshot["is_active"]) and not rule.is_deleted
            rule.deleted_at = timezone.now() if rule.is_deleted else None
            rule.updated_by = actor
            _clean(rule)
            rule.save()
            _record_matching_rule_version(rule, actor, reason=_text(reason, "reason", maximum=255))
            _emit(
                tenant,
                "mdm.matching_rule.updated",
                "matching_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "matching_rule_id": rule.id,
                    "entity_type_id": rule.entity_type_id,
                    "changed_fields": sorted(expected - {"entity_type_id"}),
                    "request_fingerprint": fingerprint,
                },
            )
            return rule

    @classmethod
    def rollback(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        rule_id: UUID,
        *,
        version_number: int,
        reason: str,
        idempotency_key: str,
    ) -> MatchingRule:
        version = cls.version_history(tenant_id, rule_id).filter(version_number=version_number).first()
        if version is None:
            raise MDMDomainError("RESOURCE_NOT_FOUND", "Matching rule version not found.", http_status=404)
        return cls.import_document(
            tenant_id,
            actor_id,
            rule_id,
            document=_rule_document("matching-rule", version.rule_id, version.version_number, version.snapshot),
            reason=reason,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def preview_pair(tenant_id: UUID, left_entity_id: UUID, right_entity_id: UUID, *, rule_id: UUID) -> MatchResult:
        tenant, left_id, right_id, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(left_entity_id, "left_entity_id"),
            _uuid(right_entity_id, "right_entity_id"),
            _uuid(rule_id, "rule_id"),
        )
        matching = _configuration_section(tenant, "matching")
        if left_id == right_id:
            raise MDMDomainError("INVALID_ENTITY_PAIR", "Two different entities are required.")
        with tenant_context(tenant):
            entities = {
                entity.id: entity
                for entity in MasterDataEntity.objects.for_tenant(tenant).filter(
                    pk__in=(left_id, right_id), is_deleted=False
                )
            }
            rule = (
                MatchingRule.objects.for_tenant(tenant).filter(pk=identifier, is_active=True, is_deleted=False).first()
            )
            if len(entities) != 2 or rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Matching rule or entity not found.", http_status=404)
            left, right = entities[left_id], entities[right_id]
            if left.entity_type_id != rule.entity_type_id or right.entity_type_id != rule.entity_type_id:
                raise MDMDomainError("MATCH_TYPE_MISMATCH", "Both entities must use the matching rule's type.")
            field_scores: dict[str, Decimal] = {}
            weighted = Decimal("0")
            present_weight = Decimal("0")
            for path, raw_weight in sorted(rule.field_weights.items()):
                weight = Decimal(str(raw_weight))
                left_exists, left_value = _get_path(left.data, path)
                right_exists, right_value = _get_path(right.data, path)
                if not left_exists or not right_exists or left_value in (None, "") or right_value in (None, ""):
                    score = Decimal(str(matching["missing_value_score"]))
                elif rule.algorithm == "exact":
                    score = Decimal("1") if left_value == right_value else Decimal("0")
                elif rule.algorithm == "normalized":
                    score = Decimal("1") if _normalize(left_value) == _normalize(right_value) else Decimal("0")
                elif rule.algorithm == "phonetic":
                    left_soundex = _soundex(left_value, matching)
                    score = (
                        Decimal("1")
                        if left_soundex and left_soundex == _soundex(right_value, matching)
                        else Decimal("0")
                    )
                else:
                    score = Decimal(
                        str(SequenceMatcher(None, _normalize(left_value), _normalize(right_value)).ratio())
                    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                field_scores[path] = score
                weighted += score * weight
                present_weight += weight
            confidence = (weighted / present_weight if present_weight else Decimal("0")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            outcomes = matching["outcomes"]
            if not isinstance(outcomes, Mapping):
                raise MDMDomainError("CONFIGURATION_UNAVAILABLE", "Matching outcomes are unavailable.", http_status=503)
            outcome = (
                str(outcomes["auto_confirm"])
                if confidence >= rule.auto_confirm_threshold
                else str(outcomes["review"]) if confidence >= rule.review_threshold else str(outcomes["no_match"])
            )
            return MatchResult(
                rule.id,
                left.id,
                right.id,
                confidence,
                field_scores,
                {
                    "algorithm": rule.algorithm,
                    "strategy_version": int(matching["strategy_version"]),
                },
                outcome,
            )

    @staticmethod
    def enqueue_deduplication_scan(
        tenant_id: UUID,
        actor_id: UUID,
        *,
        entity_type_id: UUID,
        rule_ids: Sequence[UUID],
        idempotency_key: str,
    ) -> AsyncJob:
        tenant, actor, type_id = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_type_id, "entity_type_id"),
        )
        rules = [_uuid(item, "rule_ids") for item in rule_ids]
        with tenant_context(tenant):
            found = set(
                MatchingRule.objects.for_tenant(tenant)
                .filter(pk__in=rules, entity_type_id=type_id, is_active=True, is_deleted=False)
                .values_list("id", flat=True)
            )
            if found != set(rules):
                raise MDMDomainError(
                    "RESOURCE_NOT_FOUND", "One or more matching rules are unavailable.", http_status=404
                )
            return _enqueue_checked(
                tenant,
                actor,
                DEDUPLICATION_SCAN_COMMAND,
                {"entity_type_id": str(type_id), "rule_ids": [str(item) for item in rules]},
                f"mdm:match:{idempotency_key}",
            )

    @classmethod
    def execute_deduplication_scan(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        entity_type_id: UUID,
        rule_ids: Sequence[UUID],
        job_id: UUID,
    ) -> dict[str, object]:
        """Generate deterministic candidates using blocking before comparison."""

        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        type_id, durable_job = _uuid(entity_type_id, "entity_type_id"), _uuid(job_id, "job_id")
        matching = _configuration_section(tenant, "matching")
        limits = _configuration_section(tenant, "limits")
        outcomes = matching["outcomes"]
        if not isinstance(outcomes, Mapping):
            raise MDMDomainError(
                "CONFIGURATION_UNAVAILABLE",
                "Matching outcomes are unavailable.",
                http_status=503,
            )
        identifiers = [_uuid(item, "rule_ids") for item in rule_ids]
        with tenant_context(tenant):
            rules = list(
                MatchingRule.objects.for_tenant(tenant)
                .filter(pk__in=identifiers, entity_type_id=type_id, is_active=True, is_deleted=False)
                .order_by("id")
            )
            if {rule.id for rule in rules} != set(identifiers):
                raise MDMDomainError(
                    "RESOURCE_NOT_FOUND", "One or more matching rules are unavailable.", http_status=404
                )
            entities = list(
                MasterDataEntity.objects.for_tenant(tenant)
                .filter(
                    entity_type_id=type_id,
                    is_deleted=False,
                    status__in=matching["scan_statuses"],
                )
                .order_by("id")
            )
        if len(entities) > int(limits["deduplication_scan_max_entities"]):
            raise MDMDomainError(
                "SCAN_SCOPE_TOO_LARGE",
                "The deterministic scan scope exceeds the safe batch limit; add blocking fields.",
                http_status=422,
            )

        created = 0
        reused = 0
        compared = 0
        for rule in rules:
            blocks: dict[tuple[str, ...], list[MasterDataEntity]] = defaultdict(list)
            for entity in entities:
                key = tuple(
                    _normalize(_get_path(entity.data, path)[1]) if _get_path(entity.data, path)[0] else ""
                    for path in rule.blocking_fields
                )
                if (
                    bool(matching["skip_incomplete_blocking_keys"])
                    and rule.blocking_fields
                    and any(not value for value in key)
                ):
                    continue
                blocks[key].append(entity)
            for members in blocks.values():
                for left_index, left in enumerate(members):
                    for right in members[left_index + 1 :]:
                        compared += 1
                        result = cls.preview_pair(tenant, left.id, right.id, rule_id=rule.id)
                        if result.outcome == str(outcomes["no_match"]):
                            continue
                        left_id, right_id = sorted((left.id, right.id), key=str)
                        with tenant_context(tenant), transaction.atomic():
                            candidate = (
                                MatchCandidate.objects.for_tenant(tenant)
                                .filter(
                                    matching_rule=rule,
                                    left_entity_id=left_id,
                                    right_entity_id=right_id,
                                )
                                .first()
                            )
                            if candidate is None:
                                candidate = MatchCandidate.objects.create(
                                    tenant_id=tenant,
                                    matching_rule=rule,
                                    left_entity_id=left_id,
                                    right_entity_id=right_id,
                                    confidence=result.confidence,
                                    field_scores={path: str(score) for path, score in result.field_scores.items()},
                                    evidence=dict(result.evidence),
                                    created_by=actor,
                                    updated_by=actor,
                                )
                                created += 1
                                _emit(
                                    tenant,
                                    "mdm.match_candidate.created",
                                    "match_candidate",
                                    candidate.id,
                                    actor,
                                    idempotency_key=f"job:{durable_job}:candidate:{candidate.id}",
                                    payload={
                                        "candidate_id": candidate.id,
                                        "matching_rule_id": rule.id,
                                        "confidence": candidate.confidence,
                                        "status": candidate.status,
                                    },
                                )
                                if bool(matching["auto_confirm_enabled"]) and result.outcome == str(
                                    outcomes["auto_confirm"]
                                ):
                                    candidate = CANDIDATE_MACHINE.apply(
                                        candidate,
                                        "confirm",
                                        tenant_id=tenant,
                                        transition_key=f"job:{durable_job}:auto-confirm:{candidate.id}",
                                        context={
                                            "actor_id": actor,
                                            "reviewed_at": timezone.now(),
                                            "note": "Deterministically auto-confirmed at the configured threshold.",
                                        },
                                        metadata={
                                            "actor_id": str(actor),
                                            "job_id": str(durable_job),
                                            "correlation_id": get_correlation_id() or str(uuid.uuid4()),
                                        },
                                    )
                            else:
                                reused += 1
        return {
            "job_id": str(durable_job),
            "entity_type_id": str(type_id),
            "entity_count": len(entities),
            "rule_count": len(rules),
            "compared_pair_count": compared,
            "created_candidate_count": created,
            "reused_candidate_count": reused,
        }

    @staticmethod
    def review_candidate(
        tenant_id: UUID, actor_id: UUID, candidate_id: UUID, *, decision: str, note: str, transition_key: str
    ) -> MatchCandidate:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(candidate_id, "candidate_id"),
        )
        matching = _configuration_section(tenant, "matching")
        if decision not in matching["review_decisions"]:  # type: ignore[operator]
            raise MDMDomainError("INVALID_MATCH_DECISION", "Decision is not enabled by matching policy.")
        review_note = _text(
            note,
            "note",
            maximum=int(_configuration_section(tenant, "limits")["reason_max"]),
            blank=True,
        )
        fingerprint = _fingerprint({"candidate_id": str(identifier), "decision": decision, "note": review_note})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.match_candidate.reviewed", transition_key, fingerprint)
            if receipt:
                return MatchCandidate.objects.for_tenant(tenant).get(pk=receipt)
            candidate = MatchCandidate.objects.for_tenant(tenant).select_for_update().filter(pk=identifier).first()
            if candidate is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Match candidate not found.", http_status=404)
            reviewed_at = timezone.now()
            try:
                candidate = CANDIDATE_MACHINE.apply(
                    candidate,
                    decision,
                    tenant_id=tenant,
                    transition_key=transition_key,
                    context={"actor_id": actor, "reviewed_at": reviewed_at, "note": review_note},
                    metadata={"actor_id": str(actor), "correlation_id": get_correlation_id()},
                )
            except StateMachineError as exc:
                raise MDMDomainError(
                    "ILLEGAL_TRANSITION", "The match review transition is not allowed.", http_status=409
                ) from exc
            _emit(
                tenant,
                "mdm.match_candidate.reviewed",
                "match_candidate",
                candidate.id,
                actor,
                idempotency_key=transition_key,
                payload={
                    "decision": decision,
                    "status": candidate.status,
                    "confidence": candidate.confidence,
                    "candidate_id": candidate.id,
                    "request_fingerprint": fingerprint,
                },
            )
            return candidate


class QualityRuleService:
    @staticmethod
    def _configuration(
        tenant_id: UUID,
        rule_type: str,
        configuration: Mapping[str, object],
        field_path: str,
    ) -> dict[str, object]:
        quality = _configuration_section(tenant_id, "quality")
        schema_policy = _configuration_section(tenant_id, "schema_policy")
        config = _object(
            configuration,
            "configuration",
            maximum_bytes=int(schema_policy["max_payload_bytes"]),
        )
        schemas = quality["rule_schemas"]
        rule_schema = schemas.get(rule_type) if isinstance(schemas, Mapping) else None
        if not isinstance(rule_schema, Mapping):
            raise MDMDomainError("INVALID_RULE_TYPE", "Unsupported quality rule type.")
        required = rule_schema.get("required", [])
        allowed = rule_schema.get("allowed", [])
        at_least_one = rule_schema.get("at_least_one", [])
        if not isinstance(required, list) or not isinstance(allowed, list) or not isinstance(at_least_one, list):
            raise MDMDomainError("CONFIGURATION_UNAVAILABLE", "Quality rule schema is invalid.", http_status=503)
        missing = set(required) - set(config)
        unknown = set(config) - set(allowed)
        if missing or unknown or (at_least_one and not (set(at_least_one) & set(config))):
            raise MDMDomainError(
                "INVALID_RULE_CONFIGURATION",
                "Quality rule configuration violates its configured schema.",
                detail={"missing": sorted(missing), "unknown": sorted(unknown)},
            )
        if rule_type == "format":
            pattern = config.get("pattern")
            try:
                re.compile(str(pattern))
            except re.error as exc:
                raise MDMDomainError("INVALID_RULE_CONFIGURATION", "Format pattern is invalid.") from exc
        elif rule_type == "referential" and not isinstance(config.get("entity_type_key"), str):
            raise MDMDomainError("INVALID_RULE_CONFIGURATION", "Referential rules require entity_type_key.")
        elif (
            rule_type == "timeliness"
            and "max_age_days" in config
            and (not isinstance(config.get("max_age_days"), int) or int(config["max_age_days"]) < 0)
        ):
            raise MDMDomainError("INVALID_RULE_CONFIGURATION", "Timeliness rules require non-negative max_age_days.")
        if rule_type != "uniqueness" and not field_path and rule_type != "required":
            raise MDMDomainError("VALIDATION_ERROR", "field_path is required for this rule type.")
        return config

    @classmethod
    def create_rule(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        entity_type_id: UUID,
        name: str,
        field_path: str,
        rule_type: str,
        configuration: Mapping[str, object],
        dimension: str,
        severity: str,
        weight: object,
        is_active: bool = True,
        idempotency_key: str,
    ) -> DataQualityRule:
        if not isinstance(is_active, bool):
            raise MDMDomainError("VALIDATION_ERROR", "is_active must be a boolean.")
        tenant, actor, type_id = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(entity_type_id, "entity_type_id"),
        )
        schema_policy = _configuration_section(tenant, "schema_policy")
        path = _text(field_path, "field_path", maximum=255, blank=True)
        if path and not re.fullmatch(str(schema_policy["field_path_pattern"]), path):
            raise MDMDomainError("VALIDATION_ERROR", "field_path is invalid.")
        config = cls._configuration(tenant, rule_type, configuration, path)
        fingerprint = _fingerprint(
            {
                "entity_type_id": str(type_id),
                "name": name,
                "field_path": path,
                "rule_type": rule_type,
                "configuration": config,
                "dimension": dimension,
                "severity": severity,
                "weight": str(weight),
                "is_active": is_active,
            }
        )
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.quality_rule.created", idempotency_key, fingerprint)
            if receipt:
                return DataQualityRule.objects.for_tenant(tenant).get(pk=receipt)
            entity_type = MasterEntityType.objects.for_tenant(tenant).filter(pk=type_id, is_deleted=False).first()
            if entity_type is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Entity type not found.", http_status=404)
            rule = DataQualityRule(
                tenant_id=tenant,
                entity_type=entity_type,
                name=_text(
                    name,
                    "name",
                    maximum=int(_configuration_section(tenant, "limits")["display_name_max"]),
                ),
                field_path=path,
                rule_type=rule_type,
                configuration=config,
                dimension=dimension,
                severity=severity,
                weight=Decimal(str(weight)),
                is_active=is_active,
                created_by=actor,
                updated_by=actor,
            )
            _clean(rule)
            rule.save()
            _record_quality_rule_version(rule, actor, reason="Quality rule created.")
            _emit(
                tenant,
                "mdm.quality_rule.created",
                "data_quality_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={"entity_type_id": type_id, "request_fingerprint": fingerprint},
            )
            return rule

    @classmethod
    def update_rule(
        cls, tenant_id: UUID, actor_id: UUID, rule_id: UUID, *, changes: Mapping[str, object], idempotency_key: str
    ) -> DataQualityRule:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(rule_id, "rule_id"),
        )
        allowed = {"name", "field_path", "rule_type", "configuration", "dimension", "severity", "weight", "is_active"}
        if set(changes) - allowed:
            raise MDMDomainError("VALIDATION_ERROR", "Unsupported quality rule changes.")
        fingerprint = _fingerprint({"rule_id": str(identifier), "changes": dict(changes)})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.quality_rule.updated", idempotency_key, fingerprint)
            if receipt:
                return DataQualityRule.objects.for_tenant(tenant).get(pk=receipt)
            rule = (
                DataQualityRule.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Quality rule not found.", http_status=404)
            rule_type = str(changes.get("rule_type", rule.rule_type))
            path = str(changes.get("field_path", rule.field_path))
            config = cls._configuration(
                tenant,
                rule_type,
                changes.get("configuration", rule.configuration),  # type: ignore[arg-type]
                path,
            )
            for name, value in changes.items():
                setattr(rule, name, Decimal(str(value)) if name == "weight" else value)
            rule.configuration, rule.updated_by = config, actor
            _clean(rule)
            rule.save()
            _record_quality_rule_version(
                rule,
                actor,
                reason=f"Quality rule updated: {', '.join(sorted(changes))}.",
            )
            _emit(
                tenant,
                "mdm.quality_rule.updated",
                "data_quality_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "entity_type_id": rule.entity_type_id,
                    "changed_fields": sorted(changes),
                    "request_fingerprint": fingerprint,
                },
            )
            return rule

    @staticmethod
    def deactivate_rule(tenant_id: UUID, actor_id: UUID, rule_id: UUID, *, idempotency_key: str) -> DataQualityRule:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(rule_id, "rule_id"),
        )
        fingerprint = _fingerprint({"rule_id": str(identifier), "operation": "deactivate"})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(
                tenant,
                "mdm.quality_rule.deactivated",
                idempotency_key,
                fingerprint,
            )
            if receipt:
                return DataQualityRule.objects.for_tenant(tenant).get(pk=receipt)
            rule = (
                DataQualityRule.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk=identifier, is_deleted=False)
                .first()
            )
            if rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Quality rule not found.", http_status=404)
            rule.is_active, rule.is_deleted, rule.deleted_at, rule.updated_by = False, True, timezone.now(), actor
            rule.save(update_fields=["is_active", "is_deleted", "deleted_at", "updated_by", "updated_at"])
            _record_quality_rule_version(rule, actor, reason="Quality rule deactivated.")
            _emit(
                tenant,
                "mdm.quality_rule.deactivated",
                "data_quality_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={"status": "inactive", "request_fingerprint": fingerprint},
            )
            return rule

    @staticmethod
    def version_history(tenant_id: UUID, rule_id: UUID) -> QuerySet[DataQualityRuleVersion]:
        tenant, identifier = _uuid(tenant_id, "tenant_id"), _uuid(rule_id, "rule_id")
        with tenant_context(tenant):
            if not DataQualityRule.objects.for_tenant(tenant).filter(pk=identifier).exists():
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Quality rule not found.", http_status=404)
            return DataQualityRuleVersion.objects.for_tenant(tenant).filter(rule_id=identifier).order_by("-version_number")

    @classmethod
    def export_document(cls, tenant_id: UUID, rule_id: UUID) -> dict[str, object]:
        latest = cls.version_history(tenant_id, rule_id).first()
        if latest is None:
            raise MDMDomainError("CONFIGURATION_UNAVAILABLE", "Quality rule has no version evidence.", http_status=503)
        return _rule_document("quality-rule", latest.rule_id, latest.version_number, latest.snapshot)

    @classmethod
    def import_document(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        rule_id: UUID,
        *,
        document: object,
        reason: str,
        idempotency_key: str,
    ) -> DataQualityRule:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(rule_id, "rule_id"),
        )
        snapshot = _imported_rule_snapshot(tenant, document, kind="quality-rule", expected_rule_id=identifier)
        expected = {
            "entity_type_id",
            "name",
            "field_path",
            "rule_type",
            "configuration",
            "dimension",
            "severity",
            "weight",
            "is_active",
            "is_deleted",
        }
        if set(snapshot) != expected:
            raise MDMDomainError("INVALID_RULE_DOCUMENT", "Quality rule snapshot fields are invalid.")
        fingerprint = _fingerprint({"rule_id": str(identifier), "snapshot": snapshot})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.quality_rule.updated", idempotency_key, fingerprint)
            if receipt:
                return DataQualityRule.objects.for_tenant(tenant).get(pk=receipt)
            rule = DataQualityRule.objects.for_tenant(tenant).select_for_update().filter(pk=identifier).first()
            if rule is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Quality rule not found.", http_status=404)
            if _uuid(snapshot["entity_type_id"], "entity_type_id") != rule.entity_type_id:
                raise MDMDomainError("INVALID_RULE_DOCUMENT", "A rule import cannot change its entity type.")
            path = _text(snapshot["field_path"], "field_path", maximum=255, blank=True)
            schema_policy = _configuration_section(tenant, "schema_policy")
            if path and not re.fullmatch(str(schema_policy["field_path_pattern"]), path):
                raise MDMDomainError("INVALID_RULE_DOCUMENT", "field_path violates the tenant policy.")
            rule_type = str(snapshot["rule_type"])
            configuration = cls._configuration(
                tenant,
                rule_type,
                snapshot["configuration"],  # type: ignore[arg-type]
                path,
            )
            if not isinstance(snapshot["is_active"], bool) or not isinstance(snapshot["is_deleted"], bool):
                raise MDMDomainError("INVALID_RULE_DOCUMENT", "Rule state flags must be booleans.")
            rule.name = _text(
                snapshot["name"],
                "name",
                maximum=int(_configuration_section(tenant, "limits")["display_name_max"]),
            )
            rule.field_path, rule.rule_type, rule.configuration = path, rule_type, configuration
            rule.dimension, rule.severity = str(snapshot["dimension"]), str(snapshot["severity"])
            try:
                rule.weight = Decimal(str(snapshot["weight"]))
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise MDMDomainError("INVALID_RULE_DOCUMENT", "weight must be a decimal value.") from exc
            rule.is_deleted = bool(snapshot["is_deleted"])
            rule.is_active = bool(snapshot["is_active"]) and not rule.is_deleted
            rule.deleted_at = timezone.now() if rule.is_deleted else None
            rule.updated_by = actor
            _clean(rule)
            rule.save()
            _record_quality_rule_version(rule, actor, reason=_text(reason, "reason", maximum=255))
            _emit(
                tenant,
                "mdm.quality_rule.updated",
                "data_quality_rule",
                rule.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "entity_type_id": rule.entity_type_id,
                    "changed_fields": sorted(expected - {"entity_type_id"}),
                    "request_fingerprint": fingerprint,
                },
            )
            return rule

    @classmethod
    def rollback(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        rule_id: UUID,
        *,
        version_number: int,
        reason: str,
        idempotency_key: str,
    ) -> DataQualityRule:
        version = cls.version_history(tenant_id, rule_id).filter(version_number=version_number).first()
        if version is None:
            raise MDMDomainError("RESOURCE_NOT_FOUND", "Quality rule version not found.", http_status=404)
        return cls.import_document(
            tenant_id,
            actor_id,
            rule_id,
            document=_rule_document("quality-rule", version.rule_id, version.version_number, version.snapshot),
            reason=reason,
            idempotency_key=idempotency_key,
        )


def _entity_snapshot(entity: MasterDataEntity) -> dict[str, object]:
    return {
        "entity_code": entity.entity_code,
        "entity_name": entity.entity_name,
        "data": entity.data,
        "source_system": entity.source_system,
        "source_record_id": entity.source_record_id,
        "status": entity.status,
        "quality_score": str(entity.quality_score),
        "quality_evaluated_at": entity.quality_evaluated_at.isoformat() if entity.quality_evaluated_at else None,
        "golden_record_id": str(entity.golden_record_id) if entity.golden_record_id else None,
        "is_golden": entity.is_golden,
        "version": entity.version,
        "is_deleted": entity.is_deleted,
        "deleted_at": entity.deleted_at.isoformat() if entity.deleted_at else None,
    }


class MergeService:
    @staticmethod
    def _as_reversed(history: MergeHistory, reversal: MergeReversal) -> MergeHistory:
        """Expose derived state without persisting changes to merge evidence."""

        history.status = "reversed"
        history.reversed_by = reversal.reversed_by
        history.reversed_at = reversal.created_at
        history.reversal_reason = reversal.reason
        return history

    @staticmethod
    def _reversal_preview(
        tenant: UUID,
        history: MergeHistory,
        *,
        lock_participants: bool,
    ) -> MergeReversalPreview:
        existing = MergeReversal.objects.for_tenant(tenant).filter(merge_history=history).first()
        if existing is not None:
            return MergeReversalPreview(
                merge_id=history.id,
                can_reverse=False,
                conflicts=(
                    MergeReversalConflict(
                        entity_id=None,
                        code="MERGE_ALREADY_REVERSED",
                        expected_version=None,
                        current_version=None,
                        message="This merge already has immutable reversal evidence.",
                    ),
                ),
                participant_versions=dict(existing.participant_versions),
            )
        participants = list(
            MergeParticipant.objects.for_tenant(tenant).filter(merge_history=history).order_by("source_entity_id")
        )
        if not participants:
            raise MDMDomainError(
                "MERGE_REVERSAL_EVIDENCE_UNAVAILABLE",
                "Reversal preview is unavailable because participant evidence is missing.",
                http_status=503,
            )
        entity_query = MasterDataEntity.objects.for_tenant(tenant).filter(
            pk__in=[participant.source_entity_id for participant in participants]
        )
        if lock_participants:
            entity_query = entity_query.select_for_update()
        current = {entity.id: entity for entity in entity_query.order_by("id")}
        configuration = ConfigurationService.get_effective(tenant)
        increment = int(configuration["merge"]["reversal_expected_version_increment"])  # type: ignore[index]
        versions: dict[str, int] = {}
        conflicts: list[MergeReversalConflict] = []
        for participant in participants:
            expected = participant.source_version + increment
            entity = current.get(participant.source_entity_id)
            if entity is None:
                conflicts.append(
                    MergeReversalConflict(
                        entity_id=participant.source_entity_id,
                        code="MERGE_PARTICIPANT_MISSING",
                        expected_version=expected,
                        current_version=None,
                        message="The merge participant no longer exists.",
                    )
                )
                continue
            versions[str(entity.id)] = entity.version
            if entity.version != expected:
                conflicts.append(
                    MergeReversalConflict(
                        entity_id=entity.id,
                        code="MERGE_PARTICIPANT_VERSION_CONFLICT",
                        expected_version=expected,
                        current_version=entity.version,
                        message="The merge participant changed after the merge.",
                    )
                )
        return MergeReversalPreview(
            merge_id=history.id,
            can_reverse=not conflicts,
            conflicts=tuple(conflicts),
            participant_versions=versions,
        )

    @classmethod
    def preview_reversal(
        cls,
        tenant_id: UUID,
        merge_id: UUID,
    ) -> MergeReversalPreview:
        tenant, identifier = _uuid(tenant_id, "tenant_id"), _uuid(merge_id, "merge_id")
        with tenant_context(tenant), transaction.atomic():
            history = MergeHistory.objects.for_tenant(tenant).select_for_update().filter(pk=identifier).first()
            if history is None:
                raise MDMDomainError(
                    "RESOURCE_NOT_FOUND",
                    "Merge history not found.",
                    http_status=404,
                )
            return cls._reversal_preview(tenant, history, lock_participants=True)

    @staticmethod
    def preview_merge(
        tenant_id: UUID, actor_id: UUID, *, entity_ids: Sequence[UUID], survivorship_overrides: Mapping[str, UUID]
    ) -> MergePreview:
        tenant = _uuid(tenant_id, "tenant_id")
        _uuid(actor_id, "actor_id")
        limits = _configuration_section(tenant, "limits")
        merge_policy = _configuration_section(tenant, "merge")
        identifiers = tuple(sorted({_uuid(item, "entity_ids") for item in entity_ids}, key=str))
        if len(identifiers) < int(limits["merge_min_entities"]):
            raise MDMDomainError(
                "MERGE_REQUIRES_MULTIPLE_ENTITIES",
                "The merge does not satisfy the configured minimum participant count.",
            )
        with tenant_context(tenant):
            records = list(
                MasterDataEntity.objects.for_tenant(tenant)
                .filter(pk__in=identifiers, is_deleted=False)
                .select_related("entity_type")
            )
            if len(records) != len(identifiers):
                raise MDMDomainError(
                    "RESOURCE_NOT_FOUND", "One or more merge entities were not found.", http_status=404
                )
            if len({record.entity_type_id for record in records}) != 1:
                raise MDMDomainError("MERGE_TYPE_MISMATCH", "All merge entities must share one entity type.")
            allowed_statuses = merge_policy["allowed_statuses"]
            if any(record.status not in allowed_statuses for record in records):  # type: ignore[operator]
                raise MDMDomainError(
                    "MERGE_STATUS_INVALID", "A record state is not enabled for merge.", http_status=409
                )
            by_id = {record.id: record for record in records}
            overrides = {
                path: _uuid(source, f"survivorship_overrides.{path}") for path, source in survivorship_overrides.items()
            }
            if any(source not in by_id for source in overrides.values()):
                raise MDMDomainError(
                    "INVALID_SURVIVORSHIP_SOURCE", "A survivorship override references an entity outside the merge."
                )
            survivor_order = merge_policy["survivorship_order"]
            if not isinstance(survivor_order, list):
                raise MDMDomainError("CONFIGURATION_UNAVAILABLE", "Survivorship order is unavailable.", http_status=503)

            def survivor_key(record: MasterDataEntity) -> tuple[object, ...]:
                values: list[object] = []
                for expression in survivor_order:
                    field, direction = str(expression).split(":", 1)
                    if field == "quality_score":
                        value: object = Decimal(record.quality_score)
                    elif field == "updated_at":
                        value = Decimal(str(record.updated_at.timestamp()))
                    else:
                        value = str(record.id)
                    if direction == "desc" and isinstance(value, Decimal):
                        value = -value
                    values.append(value)
                return tuple(values)

            survivor = sorted(records, key=survivor_key)[0]
            golden: dict[str, object] = {
                "entity_code": survivor.entity_code,
                "entity_name": survivor.entity_name,
                "data": {},
            }
            provenance: dict[str, UUID] = {"entity_code": survivor.id, "entity_name": survivor.id}
            data_paths = sorted({path for record in records for path in _flatten_paths(record.data)})
            for path in data_paths:
                if path in overrides:
                    source = by_id[overrides[path]]
                else:
                    candidates = [record for record in records if _get_path(record.data, path)[0]]
                    source = sorted(candidates, key=survivor_key)[0]
                exists, value = _get_path(source.data, path)
                if exists:
                    _set_path(golden["data"], path, value)  # type: ignore[arg-type]
                    provenance[f"data.{path}"] = source.id
            return MergePreview(
                identifiers, survivor.id, golden, provenance, {str(record.id): record.version for record in records}, ()
            )

    @classmethod
    def merge_entities(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        *,
        entity_ids: Sequence[UUID],
        survivorship_overrides: Mapping[str, UUID],
        reason: str,
        idempotency_key: str,
    ) -> MergeHistory:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        reason_value = _text(
            reason,
            "reason",
            maximum=int(_configuration_section(tenant, "limits")["reason_max"]),
        )
        identifiers = tuple(sorted({_uuid(item, "entity_ids") for item in entity_ids}, key=str))
        overrides = {
            path: str(_uuid(source, f"survivorship_overrides.{path}"))
            for path, source in sorted(survivorship_overrides.items())
        }
        fingerprint = _fingerprint(
            {
                "entity_ids": [str(item) for item in identifiers],
                "survivorship_overrides": overrides,
                "reason": reason_value,
            }
        )
        with tenant_context(tenant):
            receipt = _existing_receipt(
                tenant,
                "mdm.entities.merged",
                idempotency_key,
                fingerprint,
            )
            if receipt:
                return MergeHistory.objects.for_tenant(tenant).get(pk=receipt)
        preview = cls.preview_merge(tenant, actor, entity_ids=entity_ids, survivorship_overrides=survivorship_overrides)
        with tenant_context(tenant), transaction.atomic():
            records = list(
                MasterDataEntity.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk__in=preview.entity_ids)
                .select_related("entity_type")
                .order_by("id")
            )
            if {str(record.id): record.version for record in records} != dict(preview.source_versions):
                raise MDMDomainError("MERGE_PREVIEW_STALE", "A source changed after merge preview.", http_status=409)
            survivor = next(record for record in records if record.id == preview.survivor_id)
            snapshots = {record.id: _entity_snapshot(record) for record in records}
            before = snapshots[survivor.id]
            survivor.entity_code = str(preview.golden_values["entity_code"])
            survivor.entity_name = str(preview.golden_values["entity_name"])
            survivor.data = preview.golden_values["data"]
            survivor.is_golden = True
            survivor.version += 1
            survivor.updated_by = actor
            after = _entity_snapshot(survivor)
            history = MergeHistory.objects.create(
                tenant_id=tenant,
                golden_record=survivor,
                status="applied",
                survivorship_policy={path: str(source) for path, source in preview.provenance.items()},
                golden_snapshot_before=before,
                golden_snapshot_after=after,
                reason=reason_value,
                merged_by=actor,
                idempotency_key=idempotency_key,
                correlation_id=get_correlation_id() or str(uuid.uuid4()),
            )
            for record in records:
                role = "survivor" if record.id == survivor.id else "merged_source"
                MergeParticipant.objects.create(
                    tenant_id=tenant,
                    merge_history=history,
                    source_entity=record,
                    source_version=int(snapshots[record.id]["version"]),
                    source_snapshot=snapshots[record.id],
                    role=role,
                )
            survivor.save()
            _save_version(survivor, actor, changed_fields=list(preview.provenance), reason=reason_value)
            for source in records:
                if source.id == survivor.id:
                    continue
                source = ENTITY_MACHINE.apply(
                    source,
                    "merge",
                    tenant_id=tenant,
                    transition_key=f"{idempotency_key}:{source.id}",
                    context={"actor_id": actor, "golden_record_id": survivor.id},
                    metadata={
                        "actor_id": str(actor),
                        "merge_id": str(history.id),
                        "correlation_id": get_correlation_id(),
                    },
                )
                source.version = preview.source_versions[str(source.id)] + 1
                source.updated_by = actor
                source.save(update_fields=["version", "updated_by", "updated_at"])
                _save_version(source, actor, changed_fields=["status", "golden_record"], reason=reason_value)
            candidates = MatchCandidate.objects.for_tenant(tenant).filter(
                left_entity_id__in=preview.entity_ids,
                right_entity_id__in=preview.entity_ids,
                status="confirmed",
            )
            for candidate in candidates:
                CANDIDATE_MACHINE.apply(
                    candidate,
                    "merge",
                    tenant_id=tenant,
                    transition_key=f"{idempotency_key}:candidate:{candidate.id}",
                    context={"actor_id": actor, "merge_history_id": history.id},
                    metadata={
                        "actor_id": str(actor),
                        "merge_id": str(history.id),
                        "correlation_id": get_correlation_id(),
                    },
                )
            _emit(
                tenant,
                "mdm.entities.merged",
                "merge_history",
                history.id,
                actor,
                idempotency_key=idempotency_key,
                payload={
                    "merge_id": history.id,
                    "golden_record_id": survivor.id,
                    "source_entity_ids": list(preview.entity_ids),
                    "status": history.status,
                    "request_fingerprint": fingerprint,
                },
            )
            return history

    @classmethod
    def reverse_merge(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        merge_id: UUID,
        *,
        reason: str,
        transition_key: str,
    ) -> MergeHistory:
        tenant, actor, identifier = (
            _uuid(tenant_id, "tenant_id"),
            _uuid(actor_id, "actor_id"),
            _uuid(merge_id, "merge_id"),
        )
        reason_value = _text(
            reason,
            "reason",
            maximum=int(_configuration_section(tenant, "limits")["reason_max"]),
        )
        fingerprint = _fingerprint({"merge_id": str(identifier), "reason": reason_value})
        with tenant_context(tenant), transaction.atomic():
            receipt = _existing_receipt(tenant, "mdm.merge.reversed", transition_key, fingerprint)
            if receipt:
                replay = MergeHistory.objects.for_tenant(tenant).get(pk=receipt)
                reversal = MergeReversal.objects.for_tenant(tenant).filter(merge_history=replay).first()
                if reversal is None:
                    raise MDMDomainError(
                        "MERGE_REVERSAL_EVIDENCE_UNAVAILABLE",
                        "The reversal receipt has no immutable reversal evidence.",
                        http_status=503,
                    )
                return cls._as_reversed(replay, reversal)
            history = MergeHistory.objects.for_tenant(tenant).select_for_update().filter(pk=identifier).first()
            if history is None:
                raise MDMDomainError("RESOURCE_NOT_FOUND", "Merge history not found.", http_status=404)
            reversal_preview = cls._reversal_preview(tenant, history, lock_participants=True)
            if not reversal_preview.can_reverse:
                raise MDMDomainError(
                    "MERGE_REVERSAL_CONFLICT",
                    "The merge cannot be reversed safely.",
                    detail={
                        "conflicts": [asdict(conflict) for conflict in reversal_preview.conflicts],
                    },
                    http_status=409,
                )
            participants = list(
                MergeParticipant.objects.for_tenant(tenant)
                .filter(merge_history=history)
                .select_related("source_entity")
                .order_by("source_entity_id")
            )
            locked = {
                record.id: record
                for record in MasterDataEntity.objects.for_tenant(tenant)
                .select_for_update()
                .filter(pk__in=[participant.source_entity_id for participant in participants])
                .select_related("entity_type")
            }
            for participant in participants:
                entity = locked[participant.source_entity_id]
                snapshot = participant.source_snapshot
                if entity.status == "merged":
                    entity = ENTITY_MACHINE.apply(
                        entity,
                        "reverse_merge",
                        tenant_id=tenant,
                        transition_key=f"{transition_key}:{entity.id}",
                        context={"actor_id": actor},
                        metadata={
                            "actor_id": str(actor),
                            "merge_id": str(history.id),
                            "correlation_id": get_correlation_id(),
                        },
                    )
                entity.entity_code = snapshot["entity_code"]
                entity.entity_name = snapshot["entity_name"]
                entity.data = snapshot["data"]
                entity.source_system = snapshot["source_system"]
                entity.source_record_id = snapshot["source_record_id"]
                entity.quality_score = Decimal(str(snapshot["quality_score"]))
                entity.quality_evaluated_at = (
                    datetime.fromisoformat(snapshot["quality_evaluated_at"])
                    if snapshot.get("quality_evaluated_at")
                    else None
                )
                entity.golden_record_id = (
                    UUID(snapshot["golden_record_id"]) if snapshot.get("golden_record_id") else None
                )
                entity.is_golden = bool(snapshot["is_golden"])
                entity.is_deleted = bool(snapshot["is_deleted"])
                entity.deleted_at = (
                    datetime.fromisoformat(snapshot["deleted_at"]) if snapshot.get("deleted_at") else None
                )
                entity.version += 1
                entity.updated_by = actor
                entity.save()
                _save_version(
                    entity, actor, changed_fields=["status", "golden_record", "is_golden", "data"], reason=reason_value
                )
            reversal = MergeReversal.objects.create(
                tenant_id=tenant,
                merge_history=history,
                reversed_by=actor,
                reason=reason_value,
                correlation_id=get_correlation_id() or str(uuid.uuid4()),
                transition_key=transition_key,
                participant_versions=dict(reversal_preview.participant_versions),
            )
            _emit(
                tenant,
                "mdm.merge.reversed",
                "merge_history",
                history.id,
                actor,
                idempotency_key=transition_key,
                payload={
                    "merge_id": history.id,
                    "golden_record_id": history.golden_record_id,
                    "status": "reversed",
                    "request_fingerprint": fingerprint,
                },
            )
            return cls._as_reversed(history, reversal)


def _flatten_paths(value: Mapping[str, object], prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, Mapping):
            paths.extend(_flatten_paths(item, path))
        else:
            paths.append(path)
    return tuple(paths)


class DashboardService:
    @staticmethod
    def get_summary(tenant_id: UUID, *, entity_type_id: UUID | None = None) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        dashboard = _configuration_section(tenant, "dashboard")
        quality_policy = _configuration_section(tenant, "quality")
        with tenant_context(tenant):
            entities = MasterDataEntity.objects.for_tenant(tenant).filter(is_deleted=False)
            issues = DataQualityIssue.objects.for_tenant(tenant)
            candidates = MatchCandidate.objects.for_tenant(tenant)
            if entity_type_id is not None:
                type_id = _uuid(entity_type_id, "entity_type_id")
                entities = entities.filter(entity_type_id=type_id)
                issues = issues.filter(entity__entity_type_id=type_id)
                candidates = candidates.filter(left_entity__entity_type_id=type_id)
            status_counts = {
                row["status"]: row["total"] for row in entities.values("status").annotate(total=Count("id"))
            }
            configured_buckets = dashboard["score_buckets"]
            if not isinstance(configured_buckets, list):
                raise MDMDomainError(
                    "CONFIGURATION_UNAVAILABLE",
                    "Dashboard score buckets are unavailable.",
                    http_status=503,
                )
            score_buckets: list[dict[str, object]] = []
            score_scale = Decimal(str(quality_policy["score_scale"]))
            for bucket in configured_buckets:
                if not isinstance(bucket, Mapping):
                    raise MDMDomainError(
                        "CONFIGURATION_UNAVAILABLE",
                        "A dashboard score bucket is invalid.",
                        http_status=503,
                    )
                minimum = Decimal(str(bucket["minimum"]))
                maximum = Decimal(str(bucket["maximum"]))
                score_query: dict[str, object] = {
                    "quality_score__gte": minimum,
                    "quality_evaluated_at__isnull": False,
                }
                score_query["quality_score__lte" if maximum >= score_scale else "quality_score__lt"] = maximum
                score_buckets.append(
                    {
                        "label": str(bucket["label"]),
                        "minimum": minimum,
                        "maximum": maximum,
                        "count": entities.filter(**score_query).count(),
                    }
                )
            score_buckets.append(
                {
                    "label": "Not evaluated",
                    "minimum": Decimal("0"),
                    "maximum": Decimal("0"),
                    "count": entities.filter(quality_evaluated_at__isnull=True).count(),
                }
            )
            trend_since = timezone.now() - timedelta(days=int(dashboard["trend_window_days"]))
            quality_trend = list(
                entities.filter(quality_evaluated_at__gte=trend_since)
                .annotate(day=TruncDate("quality_evaluated_at"))
                .values("day")
                .annotate(score=Avg("quality_score"), evaluated_count=Count("id"))
                .order_by("day")
            )
            quality_trend = [
                {
                    "date": row["day"],
                    "score": row["score"],
                    "evaluated_count": row["evaluated_count"],
                }
                for row in quality_trend
            ]
            events = OutboxEvent.objects.for_tenant(tenant).filter(
                event_type__startswith="mdm.",
                aggregate_type="master_data_entity",
            )
            recent = []
            recent_events = list(events.order_by("-created_at")[: int(dashboard["recent_activity_limit"])])
            recent_entities = {
                entity.id: entity
                for entity in MasterDataEntity.objects.for_tenant(tenant).filter(
                    pk__in=[event.aggregate_id for event in recent_events]
                )
            }
            for event in recent_events:
                entity = recent_entities.get(event.aggregate_id)
                if entity is None:
                    continue
                envelope = event.payload if isinstance(event.payload, Mapping) else {}
                recent.append(
                    {
                        "event": event.event_type,
                        "aggregate_id": event.aggregate_id,
                        "entity_name": entity.entity_name,
                        "label": entity.entity_name,
                        "occurred_at": envelope.get("occurred_at", event.created_at),
                        "actor_id": envelope.get("actor_id"),
                        "correlation_id": envelope.get("correlation_id", ""),
                    }
                )
            evaluated = entities.filter(quality_evaluated_at__isnull=False)
            entity_count = entities.count()
            quality_distribution = {
                re.sub(r"[^a-z0-9]+", "_", str(bucket["label"]).casefold()).strip("_"): bucket["count"]
                for bucket in score_buckets
            }
            return {
                "entity_count": entity_count,
                "entity_status_counts": status_counts,
                "quality_distribution": quality_distribution,
                "total_entities": entity_count,
                "active_entities": status_counts.get("active", 0),
                "pending_review_entities": status_counts.get("pending_review", 0),
                "merged_entities": status_counts.get("merged", 0),
                "archived_entities": status_counts.get("archived", 0),
                "quality_evaluated_entities": evaluated.count(),
                "average_quality_score": evaluated.aggregate(value=Avg("quality_score"))["value"],
                "score_distribution": score_buckets,
                "quality_trend": quality_trend,
                "open_issues": issues.filter(status__in=("open", "in_review")).count(),
                "critical_issues": issues.filter(status__in=("open", "in_review"), severity="critical").count(),
                "pending_matches": candidates.filter(status="pending").count(),
                "recent_activity": recent,
            }


# Backward import compatibility points at the real service; no v1 behavior is retained.
MasterDataService = MasterEntityService

__all__ = [
    "DEDUPLICATION_SCAN_COMMAND",
    "QUALITY_SCAN_COMMAND",
    "DashboardService",
    "DataQualityService",
    "EntityTypeService",
    "MDMDomainError",
    "MasterDataService",
    "MasterEntityService",
    "MatchResult",
    "MatchingService",
    "MergePreview",
    "MergeService",
    "QualityReport",
    "QualityRuleService",
    "ValidationFinding",
    "ValidationReport",
]
