"""Transactional domain services for the tenant-safe metadata kernel.

The service layer is the only supported mutation boundary.  API views and
extensions deliberately receive no privileged ORM shortcut.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError

from src.core.async_jobs.models import OutboxEvent

from .models import (
    DynamicResource,
    DynamicResourceVersion,
    EntityDefinition,
    EntitySchemaVersion,
    FieldDefinition,
    MetadataConfigurationAudit,
    MetadataModelingConfiguration,
    NamingSequence,
)

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

FORMAT_VERSION = "1.0"
BUILTIN_FIELD_TYPES = frozenset({"text", "number", "date", "boolean", "select", "reference", "json"})
ALLOWED_ORDERINGS = {
    "name",
    "-name",
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "record_key",
    "-record_key",
    "display_name",
    "-display_name",
}


class ConflictError(APIException):
    """Optimistic-lock or idempotency conflict."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource changed since it was read."
    default_code = "STALE_WRITE"


class ServiceUnavailableError(APIException):
    """Explicit dependency/capability failure; never fabricated as success."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The required capability is temporarily unavailable."
    default_code = "CAPABILITY_UNAVAILABLE"


def _canonical_json(value: JSONValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _schema_hash(schema: dict[str, JSONValue]) -> str:
    return hashlib.sha256(_canonical_json(schema).encode("utf-8")).hexdigest()


def _clean_id(value: uuid.UUID | str, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({field_name: [{"code": "INVALID_UUID", "message": "Must be a UUID."}]}) from exc


def _require_text(value: object, field_name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({field_name: [{"code": "REQUIRED", "message": "This field is required."}]})
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValidationError(
            {field_name: [{"code": "MAX_LENGTH", "message": f"Must not exceed {max_length} characters."}]}
        )
    return normalized


def _event(
    tenant_id: uuid.UUID,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    *,
    actor_id: uuid.UUID,
    correlation_id: str,
    version: int,
    changed_fields: list[str] | None = None,
    idempotency_key: str = "",
) -> OutboxEvent:
    payload: dict[str, JSONValue] = {
        "tenant_id": str(tenant_id),
        "actor_id": str(actor_id),
        "correlation_id": correlation_id,
        "version": version,
        "changed_fields": changed_fields or [],
    }
    if idempotency_key:
        payload["idempotency_key"] = idempotency_key
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
    )


def _prior_result(
    tenant_id: uuid.UUID,
    event_type: str,
    idempotency_key: str,
    model: type[EntityDefinition] | type[DynamicResource] | type[EntitySchemaVersion],
):
    if not idempotency_key:
        raise ValidationError(
            {"idempotency_key": [{"code": "REQUIRED", "message": "Idempotency-Key is required."}]}
        )
    event = (
        OutboxEvent.objects.for_tenant(tenant_id)
        .filter(event_type=event_type, payload__idempotency_key=idempotency_key)
        .order_by("created_at")
        .first()
    )
    if event is None:
        return None
    result = model.objects.for_tenant(tenant_id).filter(pk=event.aggregate_id).first()
    if result is None:
        raise ConflictError("The idempotency key belongs to an unavailable prior result.")
    return result


def _validate_naming(strategy: str, config: object) -> dict[str, JSONValue]:
    if strategy not in {"uuid", "field", "sequence"}:
        raise ValidationError({"naming_strategy": [{"code": "INVALID_CHOICE", "message": "Unsupported strategy."}]})
    if not isinstance(config, dict):
        raise ValidationError({"naming_config": [{"code": "INVALID_OBJECT", "message": "Must be an object."}]})
    allowed = {
        "uuid": frozenset(),
        "field": frozenset({"field_key"}),
        "sequence": frozenset({"sequence_key", "prefix_template", "padding", "reset_period"}),
    }[strategy]
    unknown = set(config) - allowed
    if unknown:
        raise ValidationError(
            {"naming_config": [{"code": "UNKNOWN_KEYS", "message": f"Unsupported keys: {', '.join(sorted(unknown))}."}]}
        )
    normalized = copy.deepcopy(config)
    if strategy == "field":
        normalized["field_key"] = _require_text(config.get("field_key"), "field_key", 100)
    if strategy == "sequence":
        template = str(config.get("prefix_template", "{#####}"))
        numeric_tokens = re.findall(r"\{#+\}", template)
        invalid_tokens = re.findall(r"\{[^}]+\}", re.sub(r"\{(?:YYYY|MM|#+)\}", "", template))
        if len(numeric_tokens) != 1 or invalid_tokens or len(template) > 120:
            raise ValidationError(
                {"naming_config": [{"code": "INVALID_TEMPLATE", "message": "Use YYYY, MM and exactly one # token."}]}
            )
        padding = int(config.get("padding", len(numeric_tokens[0]) - 2))
        if not 1 <= padding <= 12:
            raise ValidationError({"naming_config": [{"code": "OUT_OF_RANGE", "message": "Padding must be 1-12."}]})
        reset_period = str(config.get("reset_period", "never"))
        if reset_period not in {"never", "yearly", "monthly"}:
            raise ValidationError({"naming_config": [{"code": "INVALID_CHOICE", "message": "Invalid reset period."}]})
        normalized.update(
            {
                "sequence_key": str(config.get("sequence_key", "default")),
                "prefix_template": template,
                "padding": padding,
                "reset_period": reset_period,
            }
        )
    return normalized


def _normalize_field(raw: object, order: int) -> dict[str, JSONValue]:
    if not isinstance(raw, dict):
        raise ValidationError({"fields": [{"code": "INVALID_OBJECT", "message": "Every field must be an object."}]})
    allowed = {
        "name",
        "key",
        "field_type",
        "is_required",
        "is_read_only",
        "is_searchable",
        "default_value",
        "validation_rules",
        "options",
        "reference_entity_code",
        "help_text",
        "placeholder",
        "order",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValidationError(
            {"fields": [{"code": "UNKNOWN_KEYS", "message": f"Unsupported field keys: {', '.join(sorted(unknown))}."}]}
        )
    field_type = str(raw.get("field_type", ""))
    if field_type not in BUILTIN_FIELD_TYPES:
        raise ValidationError({"field_type": [{"code": "INVALID_CHOICE", "message": "Unsupported field type."}]})
    key = _require_text(raw.get("key"), "key", 100)
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        raise ValidationError({"key": [{"code": "INVALID_KEY", "message": "Use lowercase letters, digits and underscores."}]})
    rules = raw.get("validation_rules", {})
    options = raw.get("options", [])
    if not isinstance(rules, dict):
        raise ValidationError({"validation_rules": [{"code": "INVALID_OBJECT", "message": "Must be an object."}]})
    if not isinstance(options, list):
        raise ValidationError({"options": [{"code": "INVALID_ARRAY", "message": "Must be an array."}]})
    supported_rules = {
        "text": {"min_length", "max_length", "regex"},
        "number": {"minimum", "maximum", "integer_only", "decimal_places"},
        "date": {"minimum", "maximum"},
        "boolean": set(),
        "select": {"allow_blank"},
        "reference": {"target_status"},
        "json": {"type", "required", "properties", "items", "enum"},
    }[field_type]
    unsupported_rules = set(rules) - supported_rules
    if unsupported_rules:
        raise ValidationError(
            {"validation_rules": [{"code": "UNKNOWN_KEYS", "message": f"Unsupported rules: {', '.join(sorted(unsupported_rules))}."}]}
        )
    if field_type == "select":
        if not options or any(not isinstance(item, str) for item in options) or len(options) != len(set(options)):
            raise ValidationError({"options": [{"code": "INVALID_OPTIONS", "message": "Select options must be unique strings."}]})
    elif options:
        raise ValidationError({"options": [{"code": "NOT_APPLICABLE", "message": "Only select fields accept options."}]})
    reference_code = raw.get("reference_entity_code")
    if field_type == "reference" and not reference_code:
        raise ValidationError(
            {"reference_entity_code": [{"code": "REQUIRED", "message": "Reference target is required."}]}
        )
    if field_type != "reference" and reference_code:
        raise ValidationError(
            {"reference_entity_code": [{"code": "NOT_APPLICABLE", "message": "Only reference fields accept a target."}]}
        )
    field_order = raw.get("order", order)
    if isinstance(field_order, bool) or not isinstance(field_order, int) or field_order < 0:
        raise ValidationError({"order": [{"code": "INVALID_ORDER", "message": "Order must be a non-negative integer."}]})
    normalized: dict[str, JSONValue] = {
        "name": _require_text(raw.get("name"), "name", 160),
        "key": key,
        "field_type": field_type,
        "is_required": bool(raw.get("is_required", False)),
        "is_read_only": bool(raw.get("is_read_only", False)),
        "is_searchable": bool(raw.get("is_searchable", False)),
        "default_value": copy.deepcopy(raw.get("default_value")),
        "validation_rules": copy.deepcopy(rules),
        "options": copy.deepcopy(options),
        "reference_entity_code": str(reference_code or ""),
        "help_text": str(raw.get("help_text", "")),
        "placeholder": str(raw.get("placeholder", "")),
        "order": field_order,
    }
    # Validate configured defaults through the same authority as record data.
    if normalized["default_value"] is not None:
        _validate_value(None, normalized, normalized["default_value"], tenant_id=None)
    return normalized


def _normalize_fields(fields: object) -> list[dict[str, JSONValue]]:
    if not isinstance(fields, list) or not fields:
        raise ValidationError({"fields": [{"code": "REQUIRED", "message": "At least one field is required."}]})
    normalized = [_normalize_field(raw, index) for index, raw in enumerate(fields)]
    keys = [str(field["key"]) for field in normalized]
    orders = [int(field["order"]) for field in normalized]
    if len(keys) != len(set(keys)):
        raise ValidationError({"fields": [{"code": "DUPLICATE_KEY", "message": "Field keys must be unique."}]})
    if len(orders) != len(set(orders)):
        raise ValidationError({"fields": [{"code": "DUPLICATE_ORDER", "message": "Field orders must be unique."}]})
    return sorted(normalized, key=lambda item: int(item["order"]))


def _json_schema_matches(value: JSONValue, rules: dict[str, JSONValue]) -> bool:
    expected = rules.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "null": type(None),
    }
    if expected and expected in types and (isinstance(value, bool) and expected in {"number", "integer"}):
        return False
    if expected and expected in types and not isinstance(value, types[expected]):
        return False
    enum = rules.get("enum")
    if isinstance(enum, list) and value not in enum:
        return False
    if isinstance(value, dict):
        required = rules.get("required", [])
        if isinstance(required, list) and any(key not in value for key in required):
            return False
        properties = rules.get("properties", {})
        if isinstance(properties, dict):
            for key, child_rules in properties.items():
                if key in value and isinstance(child_rules, dict) and not _json_schema_matches(value[key], child_rules):
                    return False
    if isinstance(value, list) and isinstance(rules.get("items"), dict):
        return all(_json_schema_matches(item, rules["items"]) for item in value)
    return True


def _validate_value(
    field: FieldDefinition | None,
    descriptor: dict[str, JSONValue],
    value: JSONValue,
    *,
    tenant_id: uuid.UUID | None,
) -> JSONValue:
    field_type = str(descriptor["field_type"])
    rules_value = descriptor.get("validation_rules", {})
    rules = rules_value if isinstance(rules_value, dict) else {}
    code = str(descriptor["key"])
    if field_type == "text":
        if not isinstance(value, str):
            raise ValueError("TYPE_TEXT")
        minimum = rules.get("min_length")
        maximum = rules.get("max_length")
        if isinstance(minimum, int) and len(value) < minimum:
            raise ValueError("MIN_LENGTH")
        if isinstance(maximum, int) and len(value) > maximum:
            raise ValueError("MAX_LENGTH")
        pattern = rules.get("regex")
        if isinstance(pattern, str):
            if len(pattern) > 256 or len(value) > 10_000:
                raise ValueError("REGEX_LIMIT")
            try:
                if re.fullmatch(pattern, value) is None:
                    raise ValueError("REGEX_MISMATCH")
            except re.error as exc:
                raise ValueError("INVALID_REGEX") from exc
        return value
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError("TYPE_NUMBER")
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("TYPE_NUMBER") from exc
        if not number.is_finite():
            raise ValueError("NON_FINITE")
        if rules.get("integer_only") and number != number.to_integral_value():
            raise ValueError("INTEGER_ONLY")
        if rules.get("minimum") is not None and number < Decimal(str(rules["minimum"])):
            raise ValueError("MINIMUM")
        if rules.get("maximum") is not None and number > Decimal(str(rules["maximum"])):
            raise ValueError("MAXIMUM")
        places = rules.get("decimal_places")
        if isinstance(places, int) and max(0, -number.as_tuple().exponent) > places:
            raise ValueError("DECIMAL_PLACES")
        return int(number) if number == number.to_integral_value() else float(number)
    if field_type == "date":
        if not isinstance(value, str):
            raise ValueError("TYPE_DATE")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("INVALID_DATE") from exc
        if parsed.isoformat() != value:
            raise ValueError("INVALID_DATE")
        if rules.get("minimum") and parsed < date.fromisoformat(str(rules["minimum"])):
            raise ValueError("MINIMUM")
        if rules.get("maximum") and parsed > date.fromisoformat(str(rules["maximum"])):
            raise ValueError("MAXIMUM")
        return value
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("TYPE_BOOLEAN")
        return value
    if field_type == "select":
        options = descriptor.get("options", [])
        if value == "" and rules.get("allow_blank"):
            return value
        if not isinstance(options, list) or value not in options:
            raise ValueError("INVALID_OPTION")
        return value
    if field_type == "reference":
        if tenant_id is None:  # default validation has no persisted reference context
            if not isinstance(value, str):
                raise ValueError("TYPE_REFERENCE")
            return value
        target_code = str(descriptor.get("reference_entity_code", ""))
        try:
            target_id = uuid.UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("REFERENCE_NOT_FOUND") from exc
        exists = DynamicResource.objects.for_tenant(tenant_id).filter(
            pk=target_id,
            entity_definition__code=target_code,
            entity_definition__status="published",
            deleted_at__isnull=True,
        ).exists()
        if not exists:
            raise ValueError("REFERENCE_NOT_FOUND")
        return str(target_id)
    if field_type == "json":
        if not _json_schema_matches(value, rules):
            raise ValueError("INVALID_JSON_SCHEMA")
        return copy.deepcopy(value)
    raise ValueError(f"UNSUPPORTED_TYPE_{code}")


class EntityDefinitionService:
    """Definition identity, lifecycle and portable-document commands."""

    @staticmethod
    def list_definitions(
        tenant_id: uuid.UUID,
        *,
        status: str | None = None,
        owner_module: str | None = None,
        origin: str | None = None,
        search: str | None = None,
        ordering: str | None = None,
    ) -> QuerySet[EntityDefinition]:
        queryset = EntityDefinition.objects.for_tenant(tenant_id).select_related("active_version")
        if status:
            queryset = queryset.filter(status=status)
        if owner_module:
            queryset = queryset.filter(owner_module=owner_module)
        if origin:
            queryset = queryset.filter(origin=origin)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return queryset.order_by(ordering if ordering in ALLOWED_ORDERINGS else "name")

    @staticmethod
    def get_definition(tenant_id: uuid.UUID, definition_id: uuid.UUID | str) -> EntityDefinition:
        try:
            return EntityDefinition.objects.for_tenant(tenant_id).select_related("active_version").get(pk=definition_id)
        except (EntityDefinition.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound("Entity definition not found.") from exc

    @classmethod
    @transaction.atomic
    def create_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        payload: dict[str, JSONValue],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> EntityDefinition:
        prior = _prior_result(tenant_id, "metadata_modeling.schema.created.v1", idempotency_key, EntityDefinition)
        if prior is not None:
            return prior
        if not MetadataModelingConfiguration.objects.for_tenant(tenant_id).filter(environment="production").exists():
            MetadataConfigurationService.update_configuration(
                tenant_id,
                actor_id,
                "production",
                {},
                expected_version=None,
                correlation_id=correlation_id,
            )
        allowed = {
            "name",
            "plural_name",
            "code",
            "description",
            "owner_module",
            "icon",
            "origin",
            "is_submittable",
            "track_changes",
            "naming_strategy",
            "naming_config",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValidationError({key: [{"code": "READ_ONLY", "message": "Field is not writable."}] for key in unknown})
        strategy = str(payload.get("naming_strategy", "uuid"))
        naming_config = _validate_naming(strategy, payload.get("naming_config", {}))
        try:
            entity = EntityDefinition.objects.create(
                tenant_id=tenant_id,
                name=_require_text(payload.get("name"), "name", 160),
                plural_name=_require_text(payload.get("plural_name", payload.get("name")), "plural_name", 160),
                code=_require_text(payload.get("code"), "code", 100),
                description=str(payload.get("description", "")),
                owner_module=str(payload.get("owner_module", "metadata_modeling")),
                icon=str(payload.get("icon", "")),
                origin=str(payload.get("origin", "custom")),
                is_submittable=bool(payload.get("is_submittable", False)),
                track_changes=bool(payload.get("track_changes", True)),
                naming_strategy=strategy,
                naming_config=naming_config,
                created_by=actor_id,
                updated_by=actor_id,
            )
        except IntegrityError as exc:
            raise ValidationError({"code": [{"code": "NOT_UNIQUE", "message": "Code already exists."}]}) from exc
        _event(
            tenant_id,
            "entity_definition",
            entity.id,
            "metadata_modeling.schema.created.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=entity.lock_version,
            changed_fields=sorted(allowed & set(payload)),
            idempotency_key=idempotency_key,
        )
        return entity

    @classmethod
    @transaction.atomic
    def update_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        payload: dict[str, JSONValue],
        *,
        expected_lock_version: int,
        correlation_id: str,
    ) -> EntityDefinition:
        entity = cls.get_definition(tenant_id, definition_id)
        if entity.lock_version != expected_lock_version:
            raise ConflictError()
        mutable = {
            "name",
            "plural_name",
            "code",
            "description",
            "icon",
            "is_submittable",
            "track_changes",
            "naming_strategy",
            "naming_config",
        }
        unknown = set(payload) - mutable
        if unknown:
            raise ValidationError({key: [{"code": "READ_ONLY", "message": "Field is not writable."}] for key in unknown})
        if entity.status != "draft" and "code" in payload and payload["code"] != entity.code:
            raise ValidationError({"code": [{"code": "IMMUTABLE", "message": "Code is immutable after publication."}]})
        strategy = str(payload.get("naming_strategy", entity.naming_strategy))
        config = payload.get("naming_config", entity.naming_config)
        _validate_naming(strategy, config)
        for key, value in payload.items():
            setattr(entity, key, value)
        entity.naming_strategy = strategy
        entity.naming_config = _validate_naming(strategy, config)
        entity.updated_by = actor_id
        entity.lock_version += 1
        entity.full_clean(exclude=("active_version",))
        entity.save()
        return entity

    @classmethod
    @transaction.atomic
    def archive_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> EntityDefinition:
        entity = cls.get_definition(tenant_id, definition_id)
        if entity.status == "archived":
            return entity
        entity.status = "archived"
        entity.archived_at = timezone.now()
        entity.archived_by = actor_id
        entity.updated_by = actor_id
        entity.lock_version += 1
        entity.save()
        _event(
            tenant_id,
            "entity_definition",
            entity.id,
            "metadata_modeling.schema.archived.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=entity.lock_version,
            idempotency_key=idempotency_key,
        )
        return entity

    @classmethod
    @transaction.atomic
    def restore_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> EntityDefinition:
        entity = cls.get_definition(tenant_id, definition_id)
        if entity.status != "archived":
            raise ValidationError({"status": [{"code": "INVALID_TRANSITION", "message": "Only archived definitions restore."}]})
        entity.status = "published" if entity.active_version_id else "draft"
        entity.archived_at = None
        entity.archived_by = None
        entity.updated_by = actor_id
        entity.lock_version += 1
        entity.save()
        return entity

    @classmethod
    @transaction.atomic
    def clone_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        code: str,
        name: str,
        *,
        correlation_id: str,
    ) -> EntityDefinition:
        source = cls.get_definition(tenant_id, definition_id)
        clone = cls.create_definition(
            tenant_id,
            actor_id,
            {
                "name": name,
                "plural_name": name,
                "code": code,
                "description": source.description,
                "is_submittable": source.is_submittable,
                "track_changes": source.track_changes,
                "naming_strategy": source.naming_strategy,
                "naming_config": source.naming_config,
            },
            idempotency_key=f"clone:{definition_id}:{code}",
            correlation_id=correlation_id,
        )
        if source.active_version_id:
            SchemaVersionService.create_candidate(
                tenant_id,
                actor_id,
                clone.id,
                source.active_version.schema.get("fields", []),
                based_on_version_id=None,
                change_summary=f"Cloned from {source.code}",
                correlation_id=correlation_id,
            )
        return clone

    @classmethod
    def preview_definition(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        candidate_schema: dict[str, JSONValue],
        sample_data: dict[str, JSONValue] | None = None,
    ) -> dict[str, JSONValue]:
        cls.get_definition(tenant_id, definition_id)
        fields = _normalize_fields(candidate_schema.get("fields", []))
        errors: dict[str, JSONValue] = {}
        if sample_data is not None:
            errors = DynamicResourceService.validate_descriptors(tenant_id, fields, sample_data)[1]
        error_list: list[JSONValue] = [
            {"field": key, "code": str(item.get("code", "INVALID")), "message": str(item.get("message", "Invalid value."))}
            for key, items in errors.items()
            if isinstance(items, list)
            for item in items
            if isinstance(item, dict)
        ]
        report: dict[str, JSONValue] = {
            "valid": not errors,
            "compatibility": "compatible",
            "resource_count": 0,
            "incompatible_resource_count": 0,
            "errors": error_list,
            "warnings": [],
        }
        return {
            "normalized_schema": {"fields": fields},
            "form_descriptor": fields,
            "sample_validation": report,
            "impact": report,
        }

    @classmethod
    def preview_unpersisted(
        cls,
        tenant_id: uuid.UUID,
        candidate_schema: dict[str, JSONValue],
        sample_data: dict[str, JSONValue] | None = None,
    ) -> dict[str, JSONValue]:
        fields = _normalize_fields(candidate_schema.get("fields", []))
        errors = DynamicResourceService.validate_descriptors(tenant_id, fields, sample_data)[1] if sample_data else {}
        error_list: list[JSONValue] = [
            {"field": key, "code": str(item.get("code", "INVALID")), "message": str(item.get("message", "Invalid value."))}
            for key, items in errors.items() if isinstance(items, list)
            for item in items if isinstance(item, dict)
        ]
        report: dict[str, JSONValue] = {
            "valid": not errors, "compatibility": "compatible", "resource_count": 0,
            "incompatible_resource_count": 0, "errors": error_list, "warnings": [],
        }
        return {
            "normalized_schema": {"fields": fields}, "form_descriptor": fields,
            "sample_validation": report, "impact": report,
        }

    @classmethod
    def export_definition(cls, tenant_id: uuid.UUID, definition_id: uuid.UUID) -> dict[str, JSONValue]:
        entity = cls.get_definition(tenant_id, definition_id)
        schema = entity.active_version.schema if entity.active_version_id else {"fields": []}
        body: dict[str, JSONValue] = {
            "format_version": FORMAT_VERSION,
            "entity": {
                "name": entity.name,
                "plural_name": entity.plural_name,
                "code": entity.code,
                "description": entity.description,
                "owner_module": entity.owner_module,
                "icon": entity.icon,
                "origin": entity.origin,
                "is_submittable": entity.is_submittable,
                "track_changes": entity.track_changes,
                "naming_strategy": entity.naming_strategy,
                "naming_config": entity.naming_config,
            },
            "schema": schema,
        }
        return {**body, "checksum": _schema_hash(body)}

    @classmethod
    @transaction.atomic
    def import_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        document: dict[str, JSONValue],
        *,
        mode: str,
        idempotency_key: str,
        correlation_id: str,
    ):
        if mode not in {"create", "new_version", "validate_only"}:
            raise ValidationError({"mode": [{"code": "INVALID_CHOICE", "message": "Unsupported import mode."}]})
        checksum = document.get("checksum")
        body = {key: value for key, value in document.items() if key != "checksum"}
        if document.get("format_version") != FORMAT_VERSION:
            raise ValidationError({"format_version": [{"code": "UNSUPPORTED_VERSION", "message": "Unsupported format."}]})
        if checksum != _schema_hash(body):
            raise ValidationError({"checksum": [{"code": "CHECKSUM_MISMATCH", "message": "Document checksum is invalid."}]})
        entity_payload = document.get("entity")
        schema = document.get("schema")
        if not isinstance(entity_payload, dict) or not isinstance(schema, dict):
            raise ValidationError({"document": [{"code": "MALFORMED_DOCUMENT", "message": "Entity and schema are required."}]})
        fields = _normalize_fields(schema.get("fields", []))
        if mode == "validate_only":
            return {
                "valid": True,
                "checksum_valid": True,
                "normalized_document": document,
                "report": {
                    "valid": True,
                    "compatibility": "compatible",
                    "resource_count": 0,
                    "incompatible_resource_count": 0,
                    "errors": [],
                    "warnings": [],
                },
            }
        if mode == "create":
            entity = cls.create_definition(
                tenant_id,
                actor_id,
                entity_payload,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
            )
        else:
            entity = EntityDefinition.objects.for_tenant(tenant_id).filter(code=entity_payload.get("code")).first()
            if entity is None:
                raise NotFound("Target definition not found.")
        return SchemaVersionService.create_candidate(
            tenant_id,
            actor_id,
            entity.id,
            fields,
            based_on_version_id=entity.active_version_id,
            change_summary="Imported schema",
            correlation_id=correlation_id,
        )

    @classmethod
    @transaction.atomic
    def delete_draft_definition(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        *,
        correlation_id: str,
    ) -> None:
        entity = cls.get_definition(tenant_id, definition_id)
        if entity.versions.filter(status__in=("published", "superseded")).exists() or entity.resources.exists():
            raise ValidationError({"status": [{"code": "DELETE_FORBIDDEN", "message": "Published or used definitions archive."}]})
        entity.delete()


class SchemaVersionService:
    """Immutable candidate, publication, diff and rollback services."""

    @staticmethod
    def list_versions(tenant_id: uuid.UUID, definition_id: uuid.UUID) -> QuerySet[EntitySchemaVersion]:
        EntityDefinitionService.get_definition(tenant_id, definition_id)
        return EntitySchemaVersion.objects.for_tenant(tenant_id).filter(entity_definition_id=definition_id).order_by("-version")

    @staticmethod
    def get_version(
        tenant_id: uuid.UUID, definition_id: uuid.UUID, version_id: uuid.UUID | str
    ) -> EntitySchemaVersion:
        try:
            return EntitySchemaVersion.objects.for_tenant(tenant_id).get(
                pk=version_id, entity_definition_id=definition_id
            )
        except (EntitySchemaVersion.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound("Schema version not found.") from exc

    @classmethod
    @transaction.atomic
    def create_candidate(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        fields: object,
        *,
        based_on_version_id: uuid.UUID | None,
        change_summary: str,
        correlation_id: str,
    ) -> EntitySchemaVersion:
        entity = EntityDefinitionService.get_definition(tenant_id, definition_id)
        normalized = _normalize_fields(fields)
        schema: dict[str, JSONValue] = {"fields": normalized}
        based_on = None
        if based_on_version_id:
            based_on = cls.get_version(tenant_id, definition_id, based_on_version_id)
        latest = cls.list_versions(tenant_id, definition_id).select_for_update().first()
        compatibility = cls._compatibility(based_on.schema if based_on else None, schema)
        version = EntitySchemaVersion.objects.create(
            tenant_id=tenant_id,
            entity_definition=entity,
            version=(latest.version + 1 if latest else 1),
            status="candidate",
            schema=schema,
            schema_hash=_schema_hash(schema),
            change_summary=change_summary,
            compatibility=compatibility,
            validation_report={},
            based_on_version=based_on,
            created_by=actor_id,
        )
        for descriptor in normalized:
            FieldDefinition.objects.create(
                tenant_id=tenant_id,
                schema_version=version,
                **descriptor,
            )
        return version

    @staticmethod
    def _compatibility(old: dict[str, JSONValue] | None, new: dict[str, JSONValue]) -> str:
        if old is None:
            return "compatible"
        old_fields = {str(item["key"]): item for item in old.get("fields", []) if isinstance(item, dict)}
        new_fields = {str(item["key"]): item for item in new.get("fields", []) if isinstance(item, dict)}
        for key, descriptor in old_fields.items():
            replacement = new_fields.get(key)
            if replacement is None or replacement.get("field_type") != descriptor.get("field_type"):
                return "breaking"
            if not descriptor.get("is_required") and replacement.get("is_required"):
                return "requires_backfill"
        return "compatible"

    @classmethod
    def validate_candidate(
        cls, tenant_id: uuid.UUID, definition_id: uuid.UUID, version_id: uuid.UUID, *, sample_limit: int = 100
    ) -> dict[str, JSONValue]:
        if not 1 <= sample_limit <= 1000:
            raise ValidationError({"sample_limit": [{"code": "OUT_OF_RANGE", "message": "Must be 1-1000."}]})
        version = cls.get_version(tenant_id, definition_id, version_id)
        errors: list[JSONValue] = []
        resources = DynamicResource.objects.for_tenant(tenant_id).filter(
            entity_definition_id=definition_id, deleted_at__isnull=True
        )[:sample_limit]
        for resource in resources:
            _, field_errors = DynamicResourceService.validate_descriptors(
                tenant_id, version.schema.get("fields", []), resource.data, apply_defaults=False
            )
            if field_errors:
                errors.append({"resource_id": str(resource.id), "fields": field_errors})
        report: dict[str, JSONValue] = {
            "valid": not errors,
            "compatibility": version.compatibility,
            "resources_scanned": len(resources),
            "incompatible_resources": len(errors),
            "resource_count": len(resources),
            "incompatible_resource_count": len(errors),
            "errors": errors,
            "warnings": [],
        }
        EntitySchemaVersion.objects.for_tenant(tenant_id).filter(pk=version.pk).update(validation_report=report)
        version.validation_report = report
        return report

    @classmethod
    def diff_versions(
        cls,
        tenant_id: uuid.UUID,
        definition_id: uuid.UUID,
        from_version_id: uuid.UUID,
        to_version_id: uuid.UUID,
    ) -> dict[str, JSONValue]:
        old = cls.get_version(tenant_id, definition_id, from_version_id)
        new = cls.get_version(tenant_id, definition_id, to_version_id)
        old_fields = {str(item["key"]): item for item in old.schema.get("fields", []) if isinstance(item, dict)}
        new_fields = {str(item["key"]): item for item in new.schema.get("fields", []) if isinstance(item, dict)}
        added = sorted(set(new_fields) - set(old_fields))
        removed = sorted(set(old_fields) - set(new_fields))
        changed = sorted(key for key in set(old_fields) & set(new_fields) if old_fields[key] != new_fields[key])
        changes: list[JSONValue] = [
            {"key": key, "kind": "added", "after": new_fields[key]} for key in added
        ] + [
            {"key": key, "kind": "removed", "before": old_fields[key]} for key in removed
        ] + [
            {"key": key, "kind": "changed", "before": old_fields[key], "after": new_fields[key]} for key in changed
        ]
        return {
            "from_version": old.version,
            "to_version": new.version,
            "added": added,
            "removed": removed,
            "changed": changed,
            "changes": changes,
            "compatibility": cls._compatibility(old.schema, new.schema),
        }

    @classmethod
    @transaction.atomic
    def publish_candidate(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        version_id: uuid.UUID,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> EntitySchemaVersion:
        version = cls.get_version(tenant_id, definition_id, version_id)
        if version.status == "published":
            return version
        if version.status != "candidate":
            raise ValidationError({"status": [{"code": "INVALID_TRANSITION", "message": "Only candidates publish."}]})
        report = cls.validate_candidate(tenant_id, definition_id, version_id)
        if report["incompatible_resources"]:
            raise ValidationError({"schema": [{"code": "INCOMPATIBLE_RESOURCES", "message": "Existing records are invalid."}]})
        now = timezone.now()
        EntitySchemaVersion.objects.for_tenant(tenant_id).filter(
            entity_definition_id=definition_id, status="published"
        ).update(status="superseded", published_at=None, published_by=None)
        EntitySchemaVersion.objects.for_tenant(tenant_id).filter(pk=version.pk).update(
            status="published", published_at=now, published_by=actor_id
        )
        version.status = "published"
        version.published_at = now
        version.published_by = actor_id
        entity = EntityDefinitionService.get_definition(tenant_id, definition_id)
        entity.active_version = version
        entity.status = "published"
        entity.updated_by = actor_id
        entity.lock_version += 1
        entity.save()
        _event(
            tenant_id,
            "entity_schema_version",
            version.id,
            "metadata_modeling.schema.published.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=version.version,
            idempotency_key=idempotency_key,
        )
        return version

    @classmethod
    @transaction.atomic
    def reject_candidate(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        version_id: uuid.UUID,
        reason: str,
        *,
        correlation_id: str,
    ) -> EntitySchemaVersion:
        version = cls.get_version(tenant_id, definition_id, version_id)
        if version.status != "candidate":
            raise ValidationError({"status": [{"code": "INVALID_TRANSITION", "message": "Only candidates reject."}]})
        report = dict(version.validation_report)
        report["rejection_reason"] = _require_text(reason, "reason", 2000)
        EntitySchemaVersion.objects.for_tenant(tenant_id).filter(pk=version.pk).update(
            status="rejected", validation_report=report
        )
        version.status = "rejected"
        version.validation_report = report
        return version

    @classmethod
    @transaction.atomic
    def rollback_to_version(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        definition_id: uuid.UUID,
        source_version_id: uuid.UUID,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> EntitySchemaVersion:
        source = cls.get_version(tenant_id, definition_id, source_version_id)
        candidate = cls.create_candidate(
            tenant_id,
            actor_id,
            definition_id,
            source.schema.get("fields", []),
            based_on_version_id=source.id,
            change_summary=f"Rollback to version {source.version}",
            correlation_id=correlation_id,
        )
        result = cls.publish_candidate(
            tenant_id,
            actor_id,
            definition_id,
            candidate.id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )
        _event(
            tenant_id,
            "entity_schema_version",
            result.id,
            "metadata_modeling.schema.rolled_back.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=result.version,
            idempotency_key=idempotency_key,
        )
        return result


class NamingService:
    """Authoritative record-key allocation and sequence reset."""

    @staticmethod
    def preview_record_key(tenant_id: uuid.UUID, entity: EntityDefinition, data: dict[str, JSONValue]) -> str:
        if entity.tenant_id != tenant_id:
            raise NotFound("Entity definition not found.")
        if entity.naming_strategy == "uuid":
            return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
        if entity.naming_strategy == "field":
            key = entity.naming_config.get("field_key")
            value = data.get(key) if isinstance(key, str) else None
            if value in (None, ""):
                raise ValidationError({str(key): [{"code": "REQUIRED_FOR_NAMING", "message": "Naming field is required."}]})
            return str(value)
        config = _validate_naming("sequence", entity.naming_config)
        template = str(config["prefix_template"])
        preview_value = 1
        sequence = NamingSequence.objects.for_tenant(tenant_id).filter(
            entity_definition=entity, sequence_key=config["sequence_key"], is_active=True
        ).first()
        if sequence:
            preview_value = sequence.next_value
        return NamingService._render(template, preview_value)

    @staticmethod
    @transaction.atomic
    def allocate_record_key(tenant_id: uuid.UUID, entity: EntityDefinition, data: dict[str, JSONValue]) -> str:
        if entity.naming_strategy == "uuid":
            return str(uuid.uuid4())
        if entity.naming_strategy == "field":
            return NamingService.preview_record_key(tenant_id, entity, data)
        config = _validate_naming("sequence", entity.naming_config)
        sequence_key = str(config["sequence_key"])
        period_key = ""
        now = timezone.now()
        if config["reset_period"] == "yearly":
            period_key = now.strftime("%Y")
        elif config["reset_period"] == "monthly":
            period_key = now.strftime("%Y-%m")
        sequence, _ = NamingSequence.objects.for_tenant(tenant_id).select_for_update().get_or_create(
            tenant_id=tenant_id,
            entity_definition=entity,
            sequence_key=sequence_key,
            period_key=period_key,
            defaults={
                "prefix_template": config["prefix_template"],
                "padding": config["padding"],
                "reset_period": config["reset_period"],
                "is_active": True,
            },
        )
        if not sequence.is_active:
            raise ServiceUnavailableError("The configured naming sequence is inactive.")
        value = sequence.next_value
        sequence.next_value += 1
        sequence.save(update_fields=("next_value", "updated_at"))
        return NamingService._render(sequence.prefix_template, value)

    @staticmethod
    def _render(template: str, value: int) -> str:
        now = timezone.now()
        result = template.replace("{YYYY}", now.strftime("%Y")).replace("{MM}", now.strftime("%m"))
        token = re.search(r"\{(#+)\}", result)
        if token is None:
            raise ValidationError({"prefix_template": [{"code": "INVALID_TEMPLATE", "message": "Numeric token missing."}]})
        return result.replace(token.group(0), str(value).zfill(len(token.group(1))))

    @staticmethod
    @transaction.atomic
    def reset_sequence(
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        sequence_id: uuid.UUID,
        next_value: int,
        *,
        correlation_id: str,
    ) -> NamingSequence:
        if isinstance(next_value, bool) or not 1 <= next_value <= 9_999_999_999_999:
            raise ValidationError({"next_value": [{"code": "OUT_OF_RANGE", "message": "Must be a positive safe integer."}]})
        try:
            sequence = NamingSequence.objects.for_tenant(tenant_id).select_for_update().get(pk=sequence_id)
        except NamingSequence.DoesNotExist as exc:
            raise NotFound("Naming sequence not found.") from exc
        sequence.next_value = next_value
        sequence.save(update_fields=("next_value", "updated_at"))
        return sequence


class DynamicResourceService:
    """Validated dynamic record lifecycle with append-only history."""

    @staticmethod
    def list_resources(
        tenant_id: uuid.UUID,
        *,
        entity_id: uuid.UUID | None = None,
        entity_code: str | None = None,
        state: str | None = None,
        search: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        ordering: str | None = None,
    ) -> QuerySet[DynamicResource]:
        queryset = DynamicResource.objects.for_tenant(tenant_id).filter(deleted_at__isnull=True).select_related(
            "entity_definition", "schema_version"
        )
        if entity_id:
            queryset = queryset.filter(entity_definition_id=entity_id)
        if entity_code:
            queryset = queryset.filter(entity_definition__code=entity_code)
        if state:
            queryset = queryset.filter(state=state)
        if search:
            queryset = queryset.filter(Q(record_key__icontains=search) | Q(display_name__icontains=search))
        if created_after:
            queryset = queryset.filter(created_at__gte=created_after)
        if created_before:
            queryset = queryset.filter(created_at__lte=created_before)
        return queryset.order_by(ordering if ordering in ALLOWED_ORDERINGS else "-created_at")

    @staticmethod
    def get_resource(tenant_id: uuid.UUID, resource_id: uuid.UUID | str, *, include_deleted: bool = False) -> DynamicResource:
        manager = getattr(DynamicResource, "all_objects", DynamicResource.objects) if include_deleted else DynamicResource.objects
        try:
            queryset = manager.for_tenant(tenant_id)
            if not include_deleted:
                queryset = queryset.filter(deleted_at__isnull=True)
            return queryset.select_related("entity_definition", "schema_version").get(pk=resource_id)
        except (DynamicResource.DoesNotExist, ValueError, TypeError) as exc:
            raise NotFound("Dynamic resource not found.") from exc

    @staticmethod
    def validate_descriptors(
        tenant_id: uuid.UUID,
        descriptors: object,
        data: object,
        *,
        apply_defaults: bool = True,
    ) -> tuple[dict[str, JSONValue], dict[str, JSONValue]]:
        if not isinstance(data, dict):
            return {}, {"data": [{"code": "INVALID_OBJECT", "message": "Data must be an object."}]}
        if not isinstance(descriptors, list):
            return {}, {"schema": [{"code": "INVALID_SCHEMA", "message": "Schema fields are invalid."}]}
        fields = {str(item.get("key")): item for item in descriptors if isinstance(item, dict)}
        errors: dict[str, JSONValue] = {}
        cleaned: dict[str, JSONValue] = {}
        for unknown in sorted(set(data) - set(fields)):
            errors[unknown] = [{"code": "UNKNOWN_FIELD", "message": "Field is not defined by this schema."}]
        for key, descriptor in fields.items():
            present = key in data
            value = data.get(key)
            if not present and apply_defaults and descriptor.get("default_value") is not None:
                value = copy.deepcopy(descriptor["default_value"])
                present = True
            if not present or value is None or (value == "" and descriptor.get("is_required")):
                if descriptor.get("is_required"):
                    errors[key] = [{"code": "REQUIRED", "message": "This field is required."}]
                elif present:
                    cleaned[key] = None
                continue
            try:
                cleaned[key] = _validate_value(None, descriptor, value, tenant_id=tenant_id)
            except ValueError as exc:
                errors[key] = [{"code": str(exc), "message": "Value does not satisfy the field contract."}]
        return cleaned, errors

    @classmethod
    def validate_data(
        cls,
        tenant_id: uuid.UUID,
        entity: EntityDefinition,
        schema_version: EntitySchemaVersion,
        data: dict[str, JSONValue],
        *,
        existing_resource: DynamicResource | None = None,
        apply_defaults: bool = True,
    ) -> dict[str, JSONValue]:
        if entity.tenant_id != tenant_id or schema_version.tenant_id != tenant_id or schema_version.entity_definition_id != entity.id:
            raise NotFound("Schema not found.")
        cleaned, errors = cls.validate_descriptors(
            tenant_id, schema_version.schema.get("fields", []), data, apply_defaults=apply_defaults
        )
        if errors:
            raise ValidationError(errors)
        return cleaned

    @classmethod
    @transaction.atomic
    def create_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        entity_id: uuid.UUID,
        data: dict[str, JSONValue],
        *,
        display_name: str | None = None,
        idempotency_key: str,
        correlation_id: str,
    ) -> DynamicResource:
        prior = _prior_result(tenant_id, "metadata_modeling.resource.created.v1", idempotency_key, DynamicResource)
        if prior is not None:
            return prior
        entity = EntityDefinitionService.get_definition(tenant_id, entity_id)
        if entity.status != "published" or entity.active_version_id is None:
            raise ValidationError({"entity_definition": [{"code": "NOT_PUBLISHED", "message": "Schema is not published."}]})
        cleaned = cls.validate_data(tenant_id, entity, entity.active_version, data)
        record_key = NamingService.allocate_record_key(tenant_id, entity, cleaned)
        resource = DynamicResource.objects.create(
            tenant_id=tenant_id,
            entity_definition=entity,
            schema_version=entity.active_version,
            record_key=record_key,
            display_name=(display_name or record_key)[:255],
            data=cleaned,
            created_by=actor_id,
            updated_by=actor_id,
        )
        cls._snapshot(resource, "create", actor_id, correlation_id, sorted(cleaned))
        _event(
            tenant_id,
            "dynamic_resource",
            resource.id,
            "metadata_modeling.resource.created.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=resource.lock_version,
            changed_fields=sorted(cleaned),
            idempotency_key=idempotency_key,
        )
        return resource

    @classmethod
    @transaction.atomic
    def create_legacy_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        entity_id: uuid.UUID,
        data: dict[str, JSONValue],
        *,
        correlation_id: str,
    ) -> DynamicResource:
        """Migrate an applied-v1 draft record into the real versioned model.

        This exists only for the mounted v1 compatibility route. It still
        validates, snapshots and emits a durable event transactionally.
        """
        entity = EntityDefinitionService.get_definition(tenant_id, entity_id)
        if entity.active_version_id:
            schema_version = entity.active_version
            cleaned = cls.validate_data(tenant_id, entity, schema_version, data)
        else:
            schema_version = EntitySchemaVersion.objects.for_tenant(tenant_id).filter(
                entity_definition=entity
            ).order_by("-version").first()
            if schema_version is None:
                raise ValidationError({"schema": [{"code": "SCHEMA_REQUIRED", "message": "Define fields before records."}]})
            descriptors = [
                {
                    "name": field.name,
                    "key": field.key,
                    "field_type": field.field_type,
                    "is_required": field.is_required,
                    "default_value": field.default_value,
                    "validation_rules": field.validation_rules,
                    "options": field.options,
                    "reference_entity_code": field.reference_entity_code or "",
                }
                for field in schema_version.fields.order_by("order")
            ]
            cleaned, errors = cls.validate_descriptors(tenant_id, descriptors, data)
            if errors:
                raise ValidationError(errors)
        record_key = str(uuid.uuid4())
        resource = DynamicResource.objects.create(
            tenant_id=tenant_id,
            entity_definition=entity,
            schema_version=schema_version,
            record_key=record_key,
            display_name=record_key,
            data=cleaned,
            created_by=actor_id,
            updated_by=actor_id,
        )
        cls._snapshot(resource, "create", actor_id, correlation_id, sorted(cleaned))
        _event(
            tenant_id,
            "dynamic_resource",
            resource.id,
            "metadata_modeling.resource.created.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=resource.lock_version,
            changed_fields=sorted(cleaned),
            idempotency_key=f"legacy:{resource.id}",
        )
        return resource

    @classmethod
    @transaction.atomic
    def replace_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        data: dict[str, JSONValue],
        *,
        expected_lock_version: int,
        correlation_id: str,
    ) -> DynamicResource:
        resource = cls.get_resource(tenant_id, resource_id)
        return cls._update(resource, actor_id, data, expected_lock_version, correlation_id, replace=True)

    @classmethod
    @transaction.atomic
    def patch_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        changes: dict[str, JSONValue],
        *,
        expected_lock_version: int,
        correlation_id: str,
    ) -> DynamicResource:
        resource = cls.get_resource(tenant_id, resource_id)
        merged = {**resource.data, **changes}
        return cls._update(resource, actor_id, merged, expected_lock_version, correlation_id, replace=False)

    @classmethod
    def _update(
        cls,
        resource: DynamicResource,
        actor_id: uuid.UUID,
        data: dict[str, JSONValue],
        expected_lock_version: int,
        correlation_id: str,
        *,
        replace: bool,
    ) -> DynamicResource:
        if resource.lock_version != expected_lock_version:
            raise ConflictError()
        if resource.state != "draft":
            raise ValidationError({"state": [{"code": "IMMUTABLE", "message": "Submitted records are immutable."}]})
        cleaned = cls.validate_data(
            resource.tenant_id,
            resource.entity_definition,
            resource.schema_version,
            data,
            existing_resource=resource,
            apply_defaults=False,
        )
        changed = sorted(key for key in set(resource.data) | set(cleaned) if resource.data.get(key) != cleaned.get(key))
        resource.data = cleaned
        resource.updated_by = actor_id
        resource.lock_version += 1
        resource.save()
        cls._snapshot(resource, "update", actor_id, correlation_id, changed)
        _event(
            resource.tenant_id,
            "dynamic_resource",
            resource.id,
            "metadata_modeling.resource.updated.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=resource.lock_version,
            changed_fields=changed,
        )
        return resource

    @classmethod
    @transaction.atomic
    def soft_delete_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        *,
        expected_lock_version: int,
        correlation_id: str,
    ) -> DynamicResource:
        resource = cls.get_resource(tenant_id, resource_id)
        if resource.lock_version != expected_lock_version:
            raise ConflictError()
        if resource.state != "draft":
            raise ValidationError({"state": [{"code": "DELETE_FORBIDDEN", "message": "Only drafts can be deleted."}]})
        resource.deleted_at = timezone.now()
        resource.deleted_by = actor_id
        resource.updated_by = actor_id
        resource.lock_version += 1
        resource.save()
        cls._snapshot(resource, "delete", actor_id, correlation_id, [])
        _event(
            tenant_id,
            "dynamic_resource",
            resource.id,
            "metadata_modeling.resource.deleted.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=resource.lock_version,
        )
        return resource

    @classmethod
    @transaction.atomic
    def restore_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        *,
        correlation_id: str,
    ) -> DynamicResource:
        resource = cls.get_resource(tenant_id, resource_id, include_deleted=True)
        if resource.deleted_at is None:
            return resource
        resource.deleted_at = None
        resource.deleted_by = None
        resource.updated_by = actor_id
        resource.lock_version += 1
        resource.save()
        cls._snapshot(resource, "restore", actor_id, correlation_id, [])
        return resource

    @classmethod
    def duplicate_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        *,
        correlation_id: str,
    ) -> DynamicResource:
        source = cls.get_resource(tenant_id, resource_id)
        return cls.create_resource(
            tenant_id,
            actor_id,
            source.entity_definition_id,
            source.data,
            display_name=f"Copy of {source.display_name}",
            idempotency_key=f"duplicate:{source.id}:{uuid.uuid4()}",
            correlation_id=correlation_id,
        )

    @classmethod
    @transaction.atomic
    def submit_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        *,
        expected_lock_version: int,
        idempotency_key: str,
        correlation_id: str,
    ) -> DynamicResource:
        resource = cls.get_resource(tenant_id, resource_id)
        if not resource.entity_definition.is_submittable:
            raise ValidationError({"state": [{"code": "NOT_SUBMITTABLE", "message": "Entity is not submittable."}]})
        if resource.state == "submitted":
            return resource
        if resource.state != "draft":
            raise ValidationError({"state": [{"code": "INVALID_TRANSITION", "message": "Only drafts submit."}]})
        if resource.lock_version != expected_lock_version:
            raise ConflictError()
        resource.state = "submitted"
        resource.submitted_at = timezone.now()
        resource.submitted_by = actor_id
        resource.updated_by = actor_id
        resource.lock_version += 1
        resource.save()
        cls._snapshot(resource, "submit", actor_id, correlation_id, [])
        _event(
            tenant_id,
            "dynamic_resource",
            resource.id,
            "metadata_modeling.resource.submitted.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=resource.lock_version,
            idempotency_key=idempotency_key,
        )
        return resource

    @classmethod
    @transaction.atomic
    def cancel_resource(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        resource_id: uuid.UUID,
        reason: str,
        *,
        expected_lock_version: int,
        idempotency_key: str,
        correlation_id: str,
    ) -> DynamicResource:
        resource = cls.get_resource(tenant_id, resource_id)
        if resource.state == "cancelled":
            return resource
        if resource.state != "submitted":
            raise ValidationError({"state": [{"code": "INVALID_TRANSITION", "message": "Only submitted records cancel."}]})
        if resource.lock_version != expected_lock_version:
            raise ConflictError()
        _require_text(reason, "reason", 2000)
        resource.state = "cancelled"
        resource.cancelled_at = timezone.now()
        resource.cancelled_by = actor_id
        resource.updated_by = actor_id
        resource.lock_version += 1
        resource.save()
        cls._snapshot(resource, "cancel", actor_id, correlation_id, [])
        _event(
            tenant_id,
            "dynamic_resource",
            resource.id,
            "metadata_modeling.resource.cancelled.v1",
            actor_id=actor_id,
            correlation_id=correlation_id,
            version=resource.lock_version,
            idempotency_key=idempotency_key,
        )
        return resource

    @staticmethod
    def list_resource_versions(tenant_id: uuid.UUID, resource_id: uuid.UUID) -> QuerySet[DynamicResourceVersion]:
        DynamicResourceService.get_resource(tenant_id, resource_id, include_deleted=True)
        return DynamicResourceVersion.objects.for_tenant(tenant_id).filter(resource_id=resource_id).order_by("-version")

    @staticmethod
    def _snapshot(
        resource: DynamicResource,
        operation: str,
        actor_id: uuid.UUID,
        correlation_id: str,
        changed_fields: list[str],
    ) -> DynamicResourceVersion:
        latest = DynamicResourceVersion.objects.for_tenant(resource.tenant_id).filter(resource=resource).order_by("-version").first()
        return DynamicResourceVersion.objects.create(
            tenant_id=resource.tenant_id,
            resource=resource,
            version=(latest.version + 1 if latest else 1),
            schema_version=resource.schema_version,
            state=resource.state,
            record_key=resource.record_key,
            display_name=resource.display_name,
            data=copy.deepcopy(resource.data),
            changed_fields=changed_fields,
            operation=operation,
            changed_by=actor_id,
            correlation_id=correlation_id,
        )


class MetadataService:
    """Compatibility facade for v1 callers; new integrations use tenant-first services."""

    def validate_data(self, *args, **kwargs):
        if len(args) >= 3 and isinstance(args[0], uuid.UUID):
            return DynamicResourceService.validate_data(*args, **kwargs)
        if len(args) != 2:
            raise TypeError("validate_data expects (entity, data) or (tenant_id, entity, schema_version, data)")
        entity, data = args
        if entity.active_version_id:
            try:
                return DynamicResourceService.validate_data(entity.tenant_id, entity, entity.active_version, data)
            except ValidationError as exc:
                raise DjangoValidationError(exc.detail) from exc
        # Legacy draft schemas are supported only for migration-era v1 callers.
        descriptors = []
        for field in entity.fields.order_by("order"):
            descriptors.append(
                {
                    "name": field.name,
                    "key": field.key,
                    "field_type": field.field_type,
                    "is_required": field.is_required,
                    "default_value": field.default_value,
                    "validation_rules": field.validation_rules,
                    "options": field.options,
                    "reference_entity_code": getattr(field, "reference_entity_code", ""),
                }
            )
        cleaned, errors = DynamicResourceService.validate_descriptors(entity.tenant_id, descriptors, data)
        if errors:
            readable = {key: [str(item.get("message", item)) for item in value] for key, value in errors.items()}
            raise DjangoValidationError(readable)
        # Preserve the legacy contract which normalized numeric values to float.
        for descriptor in descriptors:
            key = descriptor["key"]
            if descriptor["field_type"] == "number" and key in cleaned:
                cleaned[key] = float(cleaned[key])
        return cleaned


class MetadataConfigurationService:
    """RBAC/API-facing versioned runtime configuration authority."""

    FIELDS = (
        "synchronous_validation_limit",
        "max_fields_per_schema",
        "max_schema_bytes",
        "max_record_data_bytes",
        "max_regex_length",
        "default_page_size",
        "max_page_size",
        "allowed_field_types",
        "feature_flags",
        "rollout",
    )

    @classmethod
    def _document(cls, config: MetadataModelingConfiguration) -> dict[str, JSONValue]:
        return {
            "format_version": FORMAT_VERSION,
            "environment": config.environment,
            "version": config.version,
            **{field: copy.deepcopy(getattr(config, field)) for field in cls.FIELDS},
        }

    @classmethod
    def get_configuration(cls, tenant_id: uuid.UUID, environment: str) -> MetadataModelingConfiguration:
        environment = _require_text(environment, "environment", 32)
        config = MetadataModelingConfiguration.objects.for_tenant(tenant_id).filter(environment=environment).first()
        if config is None:
            raise NotFound("Metadata-modeling configuration not found for this environment.")
        return config

    @classmethod
    def ensure_configuration(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        environment: str,
        *,
        correlation_id: str,
    ) -> MetadataModelingConfiguration:
        """Return an environment configuration, provisioning audited defaults once.

        Configuration screens must be usable for a new environment without a
        deployment or an undocumented bootstrap command.  Provisioning is
        idempotent and uses the same validation/audit path as an explicit update.
        """
        existing = MetadataModelingConfiguration.objects.for_tenant(tenant_id).filter(
            environment=environment
        ).first()
        if existing is not None:
            return existing
        return cls.update_configuration(
            tenant_id,
            actor_id,
            environment,
            {},
            expected_version=None,
            correlation_id=correlation_id,
            operation="provision",
        )

    @classmethod
    def preview_configuration(
        cls, tenant_id: uuid.UUID, environment: str, payload: dict[str, JSONValue]
    ) -> dict[str, JSONValue]:
        current = MetadataModelingConfiguration.objects.for_tenant(tenant_id).filter(environment=environment).first()
        before = cls._document(current) if current else {}
        if current:
            candidate = copy.copy(current)
            candidate.version += 1
        else:
            candidate = MetadataModelingConfiguration(
                tenant_id=tenant_id,
                environment=environment,
                version=1,
                created_by=uuid.UUID(int=0),
                updated_by=uuid.UUID(int=0),
            )
        unknown = set(payload) - set(cls.FIELDS)
        if unknown:
            raise ValidationError({key: [{"code": "UNKNOWN_FIELD", "message": "Configuration key is unsupported."}] for key in unknown})
        for field, value in payload.items():
            setattr(candidate, field, copy.deepcopy(value))
        try:
            candidate.full_clean(validate_unique=False)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict) from exc
        after = cls._document(candidate)
        changed = sorted(key for key in cls.FIELDS if before.get(key) != after.get(key))
        diff: list[JSONValue] = [
            {"path": key, "before": before.get(key), "after": after.get(key)} for key in changed
        ]
        effective_values: dict[str, JSONValue] = {
            field: copy.deepcopy(after[field]) for field in cls.FIELDS
        }
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "diff": diff,
            "effective_values": effective_values,
            "before": before,
            "after": after,
            "changed_fields": changed,
        }

    @classmethod
    @transaction.atomic
    def update_configuration(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        environment: str,
        payload: dict[str, JSONValue],
        *,
        expected_version: int | None,
        correlation_id: str,
        operation: str = "update",
    ) -> MetadataModelingConfiguration:
        current = MetadataModelingConfiguration.objects.for_tenant(tenant_id).select_for_update().filter(
            environment=environment
        ).first()
        if current and expected_version is not None and current.version != expected_version:
            raise ConflictError("Configuration has changed since it was loaded.")
        preview = cls.preview_configuration(tenant_id, environment, payload)
        before = preview["before"]
        if current is None:
            current = MetadataModelingConfiguration(
                tenant_id=tenant_id,
                environment=environment,
                version=1,
                created_by=actor_id,
                updated_by=actor_id,
            )
            audit_operation = "create" if operation == "update" else operation
        else:
            current.version += 1
            current.updated_by = actor_id
            audit_operation = operation
        for field in cls.FIELDS:
            if field in payload:
                setattr(current, field, copy.deepcopy(payload[field]))
        current.full_clean(validate_unique=False)
        current.save()
        after = cls._document(current)
        MetadataConfigurationAudit.objects.create(
            tenant_id=tenant_id,
            configuration=current,
            version=current.version,
            operation=audit_operation,
            before=before,
            after=after,
            changed_by=actor_id,
            correlation_id=correlation_id,
        )
        return current

    @classmethod
    def list_history(
        cls, tenant_id: uuid.UUID, environment: str
    ) -> QuerySet[MetadataConfigurationAudit]:
        config = cls.get_configuration(tenant_id, environment)
        return MetadataConfigurationAudit.objects.for_tenant(tenant_id).filter(configuration=config).order_by("-version")

    @classmethod
    @transaction.atomic
    def rollback_configuration(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        environment: str,
        source_version: int,
        *,
        correlation_id: str,
    ) -> MetadataModelingConfiguration:
        config = cls.get_configuration(tenant_id, environment)
        try:
            audit = MetadataConfigurationAudit.objects.for_tenant(tenant_id).get(
                configuration=config, version=source_version
            )
        except MetadataConfigurationAudit.DoesNotExist as exc:
            raise NotFound("Configuration version not found.") from exc
        payload = {field: copy.deepcopy(audit.after[field]) for field in cls.FIELDS}
        return cls.update_configuration(
            tenant_id,
            actor_id,
            environment,
            payload,
            expected_version=config.version,
            correlation_id=correlation_id,
            operation="rollback",
        )

    @classmethod
    def export_configuration(cls, tenant_id: uuid.UUID, environment: str) -> dict[str, JSONValue]:
        config = cls.get_configuration(tenant_id, environment)
        document: dict[str, JSONValue] = {
            "format_version": FORMAT_VERSION,
            "environment": config.environment,
            "values": {field: copy.deepcopy(getattr(config, field)) for field in cls.FIELDS},
        }
        return {**document, "checksum": _schema_hash(document)}

    @classmethod
    def import_configuration(
        cls,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        document: dict[str, JSONValue],
        *,
        correlation_id: str,
    ) -> MetadataModelingConfiguration:
        checksum = document.get("checksum")
        body = {key: value for key, value in document.items() if key != "checksum"}
        if body.get("format_version") != FORMAT_VERSION or checksum != _schema_hash(body):
            raise ValidationError({"document": [{"code": "CHECKSUM_MISMATCH", "message": "Configuration document is invalid."}]})
        environment = str(body.get("environment", ""))
        values = body.get("values")
        if not isinstance(values, dict):
            raise ValidationError({"document": [{"code": "MALFORMED_DOCUMENT", "message": "Configuration values are required."}]})
        payload = {field: values[field] for field in cls.FIELDS if field in values}
        current = MetadataModelingConfiguration.objects.for_tenant(tenant_id).filter(environment=environment).first()
        return cls.update_configuration(
            tenant_id,
            actor_id,
            environment,
            payload,
            expected_version=current.version if current else None,
            correlation_id=correlation_id,
            operation="import",
        )
