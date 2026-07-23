"""Transactional business services for the Regional module."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import (
    RegionalAuditRecord,
    RegionalConfiguration,
    RegionalConfigurationVersion,
    RegionalIdempotencyRecord,
    RegionalResource,
)

logger = logging.getLogger("saraise.regional")

CONFIGURATION_SCHEMA_VERSION = "1.0"
ALLOWED_ENVIRONMENTS = frozenset({"development", "self-hosted", "saas"})
DEFAULT_CONFIGURATION_DOCUMENT: dict[str, Any] = {
    "resource": {
        "name_min_length": 1,
        "name_max_length": 255,
        "name_default": "Regional resource",
        "description_default": "",
        "description_max_length": 2000,
        "default_active": True,
        "default_config": {},
        "allowed_config_keys": ["country_code", "jurisdiction_type", "compliance_tags"],
        "allowed_jurisdiction_types": ["country", "state", "province", "economic_zone"],
        "max_compliance_tags": 20,
        "max_config_bytes": 4096,
        "search_fields": ["name", "description"],
    },
    "workflow": {
        "activation_state": True,
        "deactivation_state": False,
        "require_delete_confirmation": True,
    },
    "api": {
        "default_page_size": 25,
        "max_page_size": 100,
        "allowed_filters": ["is_active", "name"],
        "allowed_ordering": [
            "name",
            "-name",
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
        ],
    },
    "health": {"cache_probe_ttl_seconds": 10},
    "rollout": {
        "enabled": True,
        "roles": ["tenant_admin"],
        "cohorts": ["all"],
    },
}

_SAFE_RESOURCE_CONFIG_KEYS = frozenset({"country_code", "jurisdiction_type", "compliance_tags"})
_SAFE_FILTERS = frozenset({"is_active", "name"})
_SAFE_ORDERING = frozenset(
    {"name", "-name", "created_at", "-created_at", "updated_at", "-updated_at"}
)
_SAFE_SEARCH_FIELDS = frozenset({"name", "description"})
_SAFE_JURISDICTIONS = frozenset({"country", "state", "province", "economic_zone"})
_SAFE_ROLES = frozenset({"tenant_admin", "tenant_user"})
_CONFIG_KEYS = {
    "resource": frozenset(DEFAULT_CONFIGURATION_DOCUMENT["resource"]),
    "workflow": frozenset(DEFAULT_CONFIGURATION_DOCUMENT["workflow"]),
    "api": frozenset(DEFAULT_CONFIGURATION_DOCUMENT["api"]),
    "health": frozenset(DEFAULT_CONFIGURATION_DOCUMENT["health"]),
    "rollout": frozenset(DEFAULT_CONFIGURATION_DOCUMENT["rollout"]),
}
_CORRELATION_PATTERN = re.compile(r"^[0-9a-fA-F-]{36}$")


def _as_uuid(value: Any, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field: "Must be a valid UUID."}) from exc


def _correlation_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if not isinstance(value, str) or not _CORRELATION_PATTERN.fullmatch(value.strip()):
        raise ValidationError({"correlation_id": "Must be a valid UUID."})
    return _as_uuid(value, "correlation_id")


def _actor(value: Any) -> str:
    normalized = str(value).strip()
    if not normalized or len(normalized) > 128:
        raise ValidationError({"actor_id": "A non-empty actor identifier of at most 128 characters is required."})
    return normalized


def _environment(value: Any) -> str:
    normalized = str(value).strip()
    if normalized not in ALLOWED_ENVIRONMENTS:
        raise ValidationError({"environment": f"Must be one of: {', '.join(sorted(ALLOWED_ENVIRONMENTS))}."})
    return normalized


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError({field: "Must be a JSON object."})
    return dict(value)


def _require_int(value: Any, field: str, lower: int, upper: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValidationError({field: f"Must be an integer from {lower} through {upper}."})
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError({field: "Must be a boolean."})
    return value


def _require_string(value: Any, field: str, maximum: int, *, allow_blank: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError({field: "Must be a string."})
    normalized = value.strip() if not allow_blank else value
    if (not allow_blank and not normalized) or len(normalized) > maximum:
        qualifier = "non-empty " if not allow_blank else ""
        raise ValidationError({field: f"Must be a {qualifier}string of at most {maximum} characters."})
    return normalized


def _require_string_list(
    value: Any,
    field: str,
    *,
    allowlist: frozenset[str],
    maximum_items: int,
    allow_empty: bool = False,
) -> list[str]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or (not allow_empty and not value)
        or len(value) > maximum_items
    ):
        raise ValidationError({field: f"Must contain between {0 if allow_empty else 1} and {maximum_items} values."})
    normalized: list[str] = []
    for item in value:
        candidate = _require_string(item, field, 64)
        if candidate not in allowlist:
            raise ValidationError({field: f"Unsupported value: {candidate}."})
        if candidate in normalized:
            raise ValidationError({field: "Duplicate values are not allowed."})
        normalized.append(candidate)
    return normalized


def validate_configuration_document(value: Any) -> dict[str, Any]:
    """Validate and normalize the complete configuration document."""

    document = _require_object(value, "document")
    expected_groups = set(_CONFIG_KEYS)
    if set(document) != expected_groups:
        missing = sorted(expected_groups - set(document))
        unknown = sorted(set(document) - expected_groups)
        raise ValidationError({"document": f"Configuration groups mismatch; missing={missing}, unknown={unknown}."})

    groups: dict[str, dict[str, Any]] = {}
    for group, expected_keys in _CONFIG_KEYS.items():
        group_value = _require_object(document[group], f"document.{group}")
        if set(group_value) != set(expected_keys):
            missing = sorted(set(expected_keys) - set(group_value))
            unknown = sorted(set(group_value) - set(expected_keys))
            raise ValidationError(
                {f"document.{group}": f"Fields mismatch; missing={missing}, unknown={unknown}."}
            )
        groups[group] = group_value

    resource = groups["resource"]
    resource["name_min_length"] = _require_int(
        resource["name_min_length"], "document.resource.name_min_length", 1, 64
    )
    resource["name_max_length"] = _require_int(
        resource["name_max_length"], "document.resource.name_max_length", 1, 512
    )
    if resource["name_min_length"] > resource["name_max_length"]:
        raise ValidationError({"document.resource.name_min_length": "Must not exceed name_max_length."})
    resource["name_default"] = _require_string(
        resource["name_default"],
        "document.resource.name_default",
        resource["name_max_length"],
    )
    if len(resource["name_default"]) < resource["name_min_length"]:
        raise ValidationError(
            {"document.resource.name_default": "Must satisfy name_min_length."}
        )
    resource["description_default"] = _require_string(
        resource["description_default"],
        "document.resource.description_default",
        2000,
        allow_blank=True,
    )
    resource["description_max_length"] = _require_int(
        resource["description_max_length"], "document.resource.description_max_length", 0, 10000
    )
    if len(resource["description_default"]) > resource["description_max_length"]:
        raise ValidationError(
            {"document.resource.description_default": "Must fit within description_max_length."}
        )
    resource["default_active"] = _require_bool(
        resource["default_active"], "document.resource.default_active"
    )
    resource["default_config"] = _require_object(
        resource["default_config"], "document.resource.default_config"
    )
    resource["allowed_config_keys"] = _require_string_list(
        resource["allowed_config_keys"],
        "document.resource.allowed_config_keys",
        allowlist=_SAFE_RESOURCE_CONFIG_KEYS,
        maximum_items=len(_SAFE_RESOURCE_CONFIG_KEYS),
        allow_empty=True,
    )
    resource["allowed_jurisdiction_types"] = _require_string_list(
        resource["allowed_jurisdiction_types"],
        "document.resource.allowed_jurisdiction_types",
        allowlist=_SAFE_JURISDICTIONS,
        maximum_items=len(_SAFE_JURISDICTIONS),
    )
    resource["max_compliance_tags"] = _require_int(
        resource["max_compliance_tags"], "document.resource.max_compliance_tags", 0, 100
    )
    resource["max_config_bytes"] = _require_int(
        resource["max_config_bytes"], "document.resource.max_config_bytes", 128, 65536
    )
    resource["search_fields"] = _require_string_list(
        resource["search_fields"],
        "document.resource.search_fields",
        allowlist=_SAFE_SEARCH_FIELDS,
        maximum_items=len(_SAFE_SEARCH_FIELDS),
    )
    default_config_unknown = set(resource["default_config"]) - set(
        resource["allowed_config_keys"]
    )
    if default_config_unknown:
        raise ValidationError(
            {
                "document.resource.default_config": (
                    "Contains fields not enabled by allowed_config_keys: "
                    f"{', '.join(sorted(default_config_unknown))}."
                )
            }
        )
    default_config_size = len(
        json.dumps(
            resource["default_config"], sort_keys=True, separators=(",", ":")
        ).encode()
    )
    if default_config_size > resource["max_config_bytes"]:
        raise ValidationError(
            {"document.resource.default_config": "Exceeds max_config_bytes."}
        )
    default_country = resource["default_config"].get("country_code")
    if default_country is not None and (
        not isinstance(default_country, str)
        or len(default_country.strip()) != 2
        or not default_country.strip().isalpha()
    ):
        raise ValidationError(
            {"document.resource.default_config.country_code": "Must be a two-letter country code."}
        )
    if default_country is not None:
        resource["default_config"]["country_code"] = default_country.strip().upper()
    default_jurisdiction = resource["default_config"].get("jurisdiction_type")
    if (
        default_jurisdiction is not None
        and default_jurisdiction not in resource["allowed_jurisdiction_types"]
    ):
        raise ValidationError(
            {
                "document.resource.default_config.jurisdiction_type": (
                    "Must be enabled by allowed_jurisdiction_types."
                )
            }
        )
    default_tags = resource["default_config"].get("compliance_tags")
    if default_tags is not None and (
        not isinstance(default_tags, list)
        or len(default_tags) > resource["max_compliance_tags"]
        or any(
            not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 64
            for tag in default_tags
        )
    ):
        raise ValidationError(
            {
                "document.resource.default_config.compliance_tags": (
                    "Must satisfy max_compliance_tags and text limits."
                )
            }
        )

    workflow = groups["workflow"]
    workflow["activation_state"] = _require_bool(
        workflow["activation_state"], "document.workflow.activation_state"
    )
    workflow["deactivation_state"] = _require_bool(
        workflow["deactivation_state"], "document.workflow.deactivation_state"
    )
    if workflow["activation_state"] == workflow["deactivation_state"]:
        raise ValidationError(
            {"document.workflow": "Activation and deactivation states must be different."}
        )
    workflow["require_delete_confirmation"] = _require_bool(
        workflow["require_delete_confirmation"],
        "document.workflow.require_delete_confirmation",
    )

    api = groups["api"]
    api["default_page_size"] = _require_int(
        api["default_page_size"], "document.api.default_page_size", 1, 200
    )
    api["max_page_size"] = _require_int(
        api["max_page_size"], "document.api.max_page_size", 1, 500
    )
    if api["default_page_size"] > api["max_page_size"]:
        raise ValidationError({"document.api.default_page_size": "Must not exceed max_page_size."})
    api["allowed_filters"] = _require_string_list(
        api["allowed_filters"],
        "document.api.allowed_filters",
        allowlist=_SAFE_FILTERS,
        maximum_items=len(_SAFE_FILTERS),
        allow_empty=True,
    )
    api["allowed_ordering"] = _require_string_list(
        api["allowed_ordering"],
        "document.api.allowed_ordering",
        allowlist=_SAFE_ORDERING,
        maximum_items=len(_SAFE_ORDERING),
    )

    health = groups["health"]
    health["cache_probe_ttl_seconds"] = _require_int(
        health["cache_probe_ttl_seconds"],
        "document.health.cache_probe_ttl_seconds",
        1,
        300,
    )

    rollout = groups["rollout"]
    rollout["enabled"] = _require_bool(rollout["enabled"], "document.rollout.enabled")
    rollout["roles"] = _require_string_list(
        rollout["roles"],
        "document.rollout.roles",
        allowlist=_SAFE_ROLES,
        maximum_items=len(_SAFE_ROLES),
    )
    cohorts = rollout["cohorts"]
    if (
        not isinstance(cohorts, list)
        or not cohorts
        or len(cohorts) > 50
        or any(not isinstance(item, str) or not item.strip() or len(item.strip()) > 64 for item in cohorts)
    ):
        raise ValidationError(
            {"document.rollout.cohorts": "Must contain 1 through 50 non-empty cohort identifiers."}
        )
    rollout["cohorts"] = list(dict.fromkeys(item.strip() for item in cohorts))
    return copy.deepcopy(groups)


def _merge_document(current: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(current))
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = {**dict(merged[key]), **dict(value)}
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _json_diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for group in sorted(set(before) | set(after)):
        old_group = before.get(group, {})
        new_group = after.get(group, {})
        keys = set(old_group if isinstance(old_group, Mapping) else {}) | set(
            new_group if isinstance(new_group, Mapping) else {}
        )
        for key in sorted(keys):
            old = old_group.get(key) if isinstance(old_group, Mapping) else old_group
            new = new_group.get(key) if isinstance(new_group, Mapping) else new_group
            if old != new:
                changes.append({"path": f"{group}.{key}", "before": old, "after": new})
    return changes


class RegionalConfigurationService:
    """Create, validate, version, import, export, and roll back configuration."""

    @staticmethod
    def _audit(
        *,
        tenant_id: uuid.UUID,
        actor_id: str,
        correlation_id: uuid.UUID,
        operation: str,
        entity_id: uuid.UUID,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> None:
        RegionalAuditRecord.objects.create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            operation=operation,
            entity_type="configuration",
            entity_id=entity_id,
            before_value=dict(before),
            after_value=dict(after),
        )

    @classmethod
    def get_or_create(
        cls,
        tenant_id: Any,
        environment: Any,
        *,
        actor_id: Any = "system",
        correlation_id: Any | None = None,
    ) -> RegionalConfiguration:
        tenant = _as_uuid(tenant_id, "tenant_id")
        env = _environment(environment)
        actor = _actor(actor_id)
        correlation = _correlation_uuid(correlation_id or str(uuid.uuid4()))
        with transaction.atomic():
            existing = RegionalConfiguration.objects.select_for_update().filter(
                tenant_id=tenant, environment=env
            ).first()
            if existing:
                return existing
            document = validate_configuration_document(DEFAULT_CONFIGURATION_DOCUMENT)
            current = RegionalConfiguration.objects.create(
                tenant_id=tenant,
                environment=env,
                version=1,
                document=document,
                updated_by=actor,
                correlation_id=correlation,
            )
            RegionalConfigurationVersion.objects.create(
                tenant_id=tenant,
                environment=env,
                version=1,
                document=document,
                operation="initialize",
                actor_id=actor,
                correlation_id=correlation,
            )
            cls._audit(
                tenant_id=tenant,
                actor_id=actor,
                correlation_id=correlation,
                operation="configuration.initialize",
                entity_id=current.id,
                before={},
                after=document,
            )
            return current

    @classmethod
    def preview(
        cls,
        tenant_id: Any,
        environment: Any,
        document: Any,
        *,
        partial: bool = False,
    ) -> dict[str, Any]:
        current = cls.get_or_create(tenant_id, environment)
        proposed = _require_object(document, "document")
        candidate = _merge_document(current.document, proposed) if partial else proposed
        validated = validate_configuration_document(candidate)
        return {"valid": True, "document": validated, "changes": _json_diff(current.document, validated)}

    @classmethod
    def update(
        cls,
        tenant_id: Any,
        environment: Any,
        document: Any,
        actor_id: Any,
        correlation_id: Any,
        *,
        partial: bool = False,
        operation: str = "update",
    ) -> RegionalConfiguration:
        tenant = _as_uuid(tenant_id, "tenant_id")
        env = _environment(environment)
        actor = _actor(actor_id)
        correlation = _correlation_uuid(correlation_id)
        with transaction.atomic():
            current = cls.get_or_create(
                tenant, env, actor_id=actor, correlation_id=correlation
            )
            current = RegionalConfiguration.objects.select_for_update().get(pk=current.pk)
            proposed = _require_object(document, "document")
            candidate = _merge_document(current.document, proposed) if partial else proposed
            validated = validate_configuration_document(candidate)
            if validated == current.document:
                return current
            before = copy.deepcopy(current.document)
            previous_version = current.version
            current.version += 1
            current.document = validated
            current.updated_by = actor
            current.correlation_id = correlation
            current.save()
            RegionalConfigurationVersion.objects.create(
                tenant_id=tenant,
                environment=env,
                version=current.version,
                document=validated,
                operation=operation,
                actor_id=actor,
                correlation_id=correlation,
                previous_version=previous_version,
            )
            cls._audit(
                tenant_id=tenant,
                actor_id=actor,
                correlation_id=correlation,
                operation=f"configuration.{operation}",
                entity_id=current.id,
                before=before,
                after=validated,
            )
            logger.info(
                "regional_configuration_changed",
                extra={
                    "tenant_id": str(tenant),
                    "actor_id": actor,
                    "correlation_id": str(correlation),
                    "operation": operation,
                    "configuration_version": current.version,
                    "outcome": "success",
                },
            )
            return current

    @classmethod
    def history(cls, tenant_id: Any, environment: Any) -> QuerySet[RegionalConfigurationVersion]:
        return RegionalConfigurationVersion.objects.filter(
            tenant_id=_as_uuid(tenant_id, "tenant_id"),
            environment=_environment(environment),
        ).order_by("-version")

    @classmethod
    def rollback(
        cls,
        tenant_id: Any,
        environment: Any,
        target_version: Any,
        actor_id: Any,
        correlation_id: Any,
    ) -> RegionalConfiguration:
        tenant = _as_uuid(tenant_id, "tenant_id")
        env = _environment(environment)
        version = _require_int(target_version, "version", 1, 2_147_483_647)
        target = RegionalConfigurationVersion.objects.filter(
            tenant_id=tenant, environment=env, version=version
        ).first()
        if target is None:
            raise ValidationError({"version": "Configuration version was not found for this tenant."})
        return cls.update(
            tenant,
            env,
            target.document,
            actor_id,
            correlation_id,
            operation="rollback",
        )

    @classmethod
    def import_document(
        cls,
        tenant_id: Any,
        environment: Any,
        document: Any,
        actor_id: Any,
        correlation_id: Any,
    ) -> RegionalConfiguration:
        return cls.update(
            tenant_id,
            environment,
            document,
            actor_id,
            correlation_id,
            operation="import",
        )

    @classmethod
    def export_document(cls, tenant_id: Any, environment: Any) -> dict[str, Any]:
        current = cls.get_or_create(tenant_id, environment)
        return {
            "schema_version": CONFIGURATION_SCHEMA_VERSION,
            "environment": current.environment,
            "version": current.version,
            "document": copy.deepcopy(current.document),
            "exported_at": timezone.now().isoformat(),
        }


def _resource_snapshot(resource: RegionalResource) -> dict[str, Any]:
    return {
        "id": str(resource.id),
        "name": resource.name,
        "description": resource.description,
        "is_active": resource.is_active,
        "config": copy.deepcopy(resource.config),
        "deleted_at": resource.deleted_at.isoformat() if resource.deleted_at else None,
    }


class RegionalService:
    """Service for governed Regional resource lifecycle operations."""

    @staticmethod
    def _configuration(tenant_id: Any, environment: Any) -> dict[str, Any]:
        return RegionalConfigurationService.get_or_create(tenant_id, environment).document

    @classmethod
    def ensure_rollout_access(
        cls,
        tenant_id: Any,
        environment: Any,
        actor_role: Any,
        cohort: Any,
    ) -> None:
        """Enforce the configured feature flag, role rollout, and cohort rollout."""

        document = cls._configuration(tenant_id, environment)
        rollout = document["rollout"]
        normalized_role = _require_string(actor_role, "actor_role", 64)
        normalized_cohort = _require_string(cohort, "cohort", 64)
        if (
            not rollout["enabled"]
            or normalized_role not in rollout["roles"]
            or (
                "all" not in rollout["cohorts"]
                and normalized_cohort not in rollout["cohorts"]
            )
        ):
            raise DjangoPermissionDenied(
                "The Regional capability is not enabled for this role and rollout cohort."
            )

    @staticmethod
    def _validate_resource(
        document: Mapping[str, Any],
        *,
        name: Any,
        description: Any,
        config: Any,
    ) -> tuple[str, str, dict[str, Any]]:
        resource_policy = document["resource"]
        normalized_name = _require_string(
            name,
            "name",
            int(resource_policy["name_max_length"]),
        )
        if len(normalized_name) < int(resource_policy["name_min_length"]):
            raise ValidationError(
                {"name": f"Must contain at least {resource_policy['name_min_length']} characters."}
            )
        normalized_description = _require_string(
            description,
            "description",
            int(resource_policy["description_max_length"]),
            allow_blank=True,
        )
        normalized_config = _require_object(config, "config")
        allowed_keys = set(resource_policy["allowed_config_keys"])
        unknown = set(normalized_config) - allowed_keys
        if unknown:
            raise ValidationError({"config": f"Unsupported fields: {', '.join(sorted(unknown))}."})
        encoded = json.dumps(normalized_config, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > int(resource_policy["max_config_bytes"]):
            raise ValidationError({"config": "Configuration exceeds the tenant's safe size limit."})
        if "country_code" in normalized_config:
            country = _require_string(normalized_config["country_code"], "config.country_code", 2).upper()
            if len(country) != 2 or not country.isalpha():
                raise ValidationError({"config.country_code": "Must be a two-letter country code."})
            normalized_config["country_code"] = country
        if "jurisdiction_type" in normalized_config:
            jurisdiction = _require_string(
                normalized_config["jurisdiction_type"], "config.jurisdiction_type", 64
            )
            if jurisdiction not in resource_policy["allowed_jurisdiction_types"]:
                raise ValidationError({"config.jurisdiction_type": "Not enabled by tenant configuration."})
            normalized_config["jurisdiction_type"] = jurisdiction
        if "compliance_tags" in normalized_config:
            tags = normalized_config["compliance_tags"]
            maximum = int(resource_policy["max_compliance_tags"])
            if (
                not isinstance(tags, list)
                or len(tags) > maximum
                or any(not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 64 for tag in tags)
            ):
                raise ValidationError(
                    {"config.compliance_tags": f"Must contain at most {maximum} bounded text tags."}
                )
            normalized_config["compliance_tags"] = list(dict.fromkeys(tag.strip() for tag in tags))
        return normalized_name, normalized_description, normalized_config

    @staticmethod
    def _audit(
        resource: RegionalResource,
        *,
        actor_id: str,
        correlation_id: uuid.UUID,
        operation: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> None:
        RegionalAuditRecord.objects.create(
            tenant_id=resource.tenant_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            operation=operation,
            entity_type="resource",
            entity_id=resource.id,
            before_value=dict(before),
            after_value=dict(after),
        )
        logger.info(
            "regional_resource_mutation",
            extra={
                "tenant_id": str(resource.tenant_id),
                "actor_id": actor_id,
                "resource_id": str(resource.id),
                "correlation_id": str(correlation_id),
                "operation": operation,
                "outcome": "success",
            },
        )

    def create_resource(
        self,
        tenant_id: Any,
        name: Any,
        description: Any | None,
        config: Any | None,
        created_by: Any,
        correlation_id: Any,
        idempotency_key: Any,
        environment: Any,
    ) -> RegionalResource:
        tenant = _as_uuid(tenant_id, "tenant_id")
        actor = _actor(created_by)
        correlation = _correlation_uuid(correlation_id)
        key = _require_string(idempotency_key, "idempotency_key", 255)
        policy = self._configuration(tenant, environment)
        normalized_name, normalized_description, normalized_config = self._validate_resource(
            policy,
            name=policy["resource"]["name_default"] if name is None else name,
            description=(
                policy["resource"]["description_default"] if description is None else description
            ),
            config=policy["resource"]["default_config"] if config is None else config,
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "name": normalized_name,
                    "description": normalized_description,
                    "config": normalized_config,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with transaction.atomic():
            replay, created = RegionalIdempotencyRecord.objects.get_or_create(
                tenant_id=tenant,
                operation="resource.create",
                idempotency_key=key,
                defaults={
                    "request_fingerprint": fingerprint,
                    "correlation_id": correlation,
                },
            )
            if not created:
                if replay.request_fingerprint != fingerprint:
                    raise ValidationError(
                        {"idempotency_key": "This key was already used with a different request."}
                    )
                if replay.resource_id is None:
                    raise ValidationError(
                        {"idempotency_key": "The original request has not completed; retry later."}
                    )
                return replay.resource
            resource = RegionalResource.objects.create(
                tenant_id=tenant,
                name=normalized_name,
                description=normalized_description,
                config=normalized_config,
                is_active=bool(policy["resource"]["default_active"]),
                created_by=actor,
            )
            replay.resource = resource
            replay.save(update_fields=["resource"])
            self._audit(
                resource,
                actor_id=actor,
                correlation_id=correlation,
                operation="resource.create",
                before={},
                after=_resource_snapshot(resource),
            )
            return resource

    def get_resource(self, resource_id: Any, tenant_id: Any) -> RegionalResource | None:
        return RegionalResource.objects.filter(
            id=_as_uuid(resource_id, "resource_id"),
            tenant_id=_as_uuid(tenant_id, "tenant_id"),
            deleted_at__isnull=True,
        ).first()

    def query_resources(
        self,
        tenant_id: Any,
        environment: Any,
        query: Mapping[str, Any],
    ) -> QuerySet[RegionalResource]:
        tenant = _as_uuid(tenant_id, "tenant_id")
        document = self._configuration(tenant, environment)
        allowed_query = set(document["api"]["allowed_filters"]) | {"search", "ordering", "page", "page_size"}
        unknown = set(query) - allowed_query
        if unknown:
            raise ValidationError({key: "Unknown or disabled query parameter." for key in sorted(unknown)})
        queryset = RegionalResource.objects.filter(tenant_id=tenant, deleted_at__isnull=True)
        if "is_active" in query:
            raw = str(query["is_active"]).lower()
            if raw not in {"true", "false"}:
                raise ValidationError({"is_active": "Must be true or false."})
            queryset = queryset.filter(is_active=raw == "true")
        if "name" in query:
            queryset = queryset.filter(name__icontains=_require_string(query["name"], "name", 512))
        search = str(query.get("search", "")).strip()
        if search:
            if len(search) > 256:
                raise ValidationError({"search": "Must not exceed 256 characters."})
            predicate = Q()
            for field in document["resource"]["search_fields"]:
                predicate |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(predicate)
        ordering = str(query.get("ordering", "-created_at"))
        if ordering not in document["api"]["allowed_ordering"]:
            raise ValidationError({"ordering": "Ordering is not enabled by tenant configuration."})
        return queryset.order_by(ordering, "id")

    def update_resource(
        self,
        resource_id: Any,
        tenant_id: Any,
        updates: Mapping[str, Any],
        actor_id: Any,
        correlation_id: Any,
        environment: Any,
    ) -> RegionalResource | None:
        actor = _actor(actor_id)
        correlation = _correlation_uuid(correlation_id)
        allowed = {"name", "description", "config"}
        unknown = set(updates) - allowed
        if unknown:
            raise ValidationError({key: "This field cannot be updated." for key in sorted(unknown)})
        with transaction.atomic():
            resource = RegionalResource.objects.select_for_update().filter(
                id=_as_uuid(resource_id, "resource_id"),
                tenant_id=_as_uuid(tenant_id, "tenant_id"),
                deleted_at__isnull=True,
            ).first()
            if resource is None:
                return None
            before = _resource_snapshot(resource)
            policy = self._configuration(resource.tenant_id, environment)
            name, description, config = self._validate_resource(
                policy,
                name=updates.get("name", resource.name),
                description=updates.get("description", resource.description),
                config=updates.get("config", resource.config),
            )
            resource.name = name
            resource.description = description
            resource.config = config
            resource.save()
            self._audit(
                resource,
                actor_id=actor,
                correlation_id=correlation,
                operation="resource.update",
                before=before,
                after=_resource_snapshot(resource),
            )
            return resource

    def delete_resource(
        self,
        resource_id: Any,
        tenant_id: Any,
        actor_id: Any,
        correlation_id: Any,
    ) -> bool:
        actor = _actor(actor_id)
        correlation = _correlation_uuid(correlation_id)
        with transaction.atomic():
            resource = RegionalResource.objects.select_for_update().filter(
                id=_as_uuid(resource_id, "resource_id"),
                tenant_id=_as_uuid(tenant_id, "tenant_id"),
                deleted_at__isnull=True,
            ).first()
            if resource is None:
                return False
            before = _resource_snapshot(resource)
            resource.deleted_at = timezone.now()
            resource.deleted_by = actor
            resource.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
            self._audit(
                resource,
                actor_id=actor,
                correlation_id=correlation,
                operation="resource.delete",
                before=before,
                after=_resource_snapshot(resource),
            )
            return True

    def restore_resource(
        self,
        resource_id: Any,
        tenant_id: Any,
        actor_id: Any,
        correlation_id: Any,
    ) -> RegionalResource | None:
        actor = _actor(actor_id)
        correlation = _correlation_uuid(correlation_id)
        with transaction.atomic():
            resource = RegionalResource.objects.select_for_update().filter(
                id=_as_uuid(resource_id, "resource_id"),
                tenant_id=_as_uuid(tenant_id, "tenant_id"),
                deleted_at__isnull=False,
            ).first()
            if resource is None:
                return None
            before = _resource_snapshot(resource)
            resource.deleted_at = None
            resource.deleted_by = ""
            resource.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
            self._audit(
                resource,
                actor_id=actor,
                correlation_id=correlation,
                operation="resource.restore",
                before=before,
                after=_resource_snapshot(resource),
            )
            return resource

    def _set_lifecycle_state(
        self,
        resource_id: Any,
        tenant_id: Any,
        actor_id: Any,
        correlation_id: Any,
        environment: Any,
        *,
        operation: str,
        policy_key: str,
    ) -> RegionalResource | None:
        actor = _actor(actor_id)
        correlation = _correlation_uuid(correlation_id)
        with transaction.atomic():
            resource = RegionalResource.objects.select_for_update().filter(
                id=_as_uuid(resource_id, "resource_id"),
                tenant_id=_as_uuid(tenant_id, "tenant_id"),
                deleted_at__isnull=True,
            ).first()
            if resource is None:
                return None
            before = _resource_snapshot(resource)
            document = self._configuration(resource.tenant_id, environment)
            resource.is_active = bool(document["workflow"][policy_key])
            resource.save(update_fields=["is_active", "updated_at"])
            self._audit(
                resource,
                actor_id=actor,
                correlation_id=correlation,
                operation=operation,
                before=before,
                after=_resource_snapshot(resource),
            )
            return resource

    def activate_resource(
        self,
        resource_id: Any,
        tenant_id: Any,
        actor_id: Any,
        correlation_id: Any,
        environment: Any,
    ) -> RegionalResource | None:
        return self._set_lifecycle_state(
            resource_id,
            tenant_id,
            actor_id,
            correlation_id,
            environment,
            operation="resource.activate",
            policy_key="activation_state",
        )

    def deactivate_resource(
        self,
        resource_id: Any,
        tenant_id: Any,
        actor_id: Any,
        correlation_id: Any,
        environment: Any,
    ) -> RegionalResource | None:
        return self._set_lifecycle_state(
            resource_id,
            tenant_id,
            actor_id,
            correlation_id,
            environment,
            operation="resource.deactivate",
            policy_key="deactivation_state",
        )
