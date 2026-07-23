"""Transactional business rules for tenant API-management state."""

from __future__ import annotations

import copy
import logging
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import (
    ApiManagementAuditRecord,
    ApiManagementConfiguration,
    ApiManagementConfigurationVersion,
    ApiManagementResource,
    ApiManagementResourceVersion,
)

logger = logging.getLogger(__name__)
PORTABLE_SCHEMA_VERSION = 2

# These are platform storage/security ceilings, not tenant business policy. They
# prevent a tenant configuration from exhausting shared runtime or storage.
PLATFORM_HARD_CEILINGS: dict[str, int] = {
    "environment_length": 64,
    "environment_count": 64,
    "list_items": 512,
    "list_item_length": 1024,
    "resource_name_length": 512,
    "resource_description_length": 100_000,
    "page_size": 1_000,
    "confirmation_length": 4_096,
    "health_cache_ttl_seconds": 3_600,
    "ui_rows": 100,
    "rollout_buckets": 10_000,
    "quota_cost": 1_000,
    "navigation_order": 10_000,
    "history_page_size": 250,
    "history_page_number": 1_000_000,
    "configuration_version_reason_length": 64,
    "resource_version_reason_length": 64,
    "audit_target_type_length": 32,
    "audit_action_length": 64,
    "evidence_identity_length": 255,
}
PLATFORM_VALIDATION_LIMIT_CEILINGS: dict[str, int] = {
    "list_max_items": PLATFORM_HARD_CEILINGS["list_items"],
    "list_item_max_length": PLATFORM_HARD_CEILINGS["list_item_length"],
    "resource_name_minimum_floor": PLATFORM_HARD_CEILINGS["resource_name_length"],
    "resource_name_minimum_ceiling": PLATFORM_HARD_CEILINGS["resource_name_length"],
    "resource_name_maximum_floor": PLATFORM_HARD_CEILINGS["resource_name_length"],
    "resource_name_maximum_ceiling": PLATFORM_HARD_CEILINGS["resource_name_length"],
    "resource_description_max_length": PLATFORM_HARD_CEILINGS["resource_description_length"],
    "page_size_minimum": PLATFORM_HARD_CEILINGS["page_size"],
    "page_size_maximum": PLATFORM_HARD_CEILINGS["page_size"],
    "deletion_confirmation_max_length": PLATFORM_HARD_CEILINGS["confirmation_length"],
    "health_cache_ttl_minimum": PLATFORM_HARD_CEILINGS["health_cache_ttl_seconds"],
    "health_cache_ttl_maximum": PLATFORM_HARD_CEILINGS["health_cache_ttl_seconds"],
    "table_skeleton_rows_minimum": PLATFORM_HARD_CEILINGS["ui_rows"],
    "table_skeleton_rows_maximum": PLATFORM_HARD_CEILINGS["ui_rows"],
    "form_description_rows_minimum": PLATFORM_HARD_CEILINGS["ui_rows"],
    "form_description_rows_maximum": PLATFORM_HARD_CEILINGS["ui_rows"],
    "rollout_percentage_minimum": 100,
    "rollout_percentage_maximum": 100,
    "configuration_history_page_size": PLATFORM_HARD_CEILINGS["history_page_size"],
    "configuration_history_max_page_size": PLATFORM_HARD_CEILINGS["history_page_size"],
    "configuration_history_max_page": PLATFORM_HARD_CEILINGS["history_page_number"],
    "configuration_version_reason_max_length": PLATFORM_HARD_CEILINGS["configuration_version_reason_length"],
    "resource_version_reason_max_length": PLATFORM_HARD_CEILINGS["resource_version_reason_length"],
    "audit_target_type_max_length": PLATFORM_HARD_CEILINGS["audit_target_type_length"],
    "audit_action_max_length": PLATFORM_HARD_CEILINGS["audit_action_length"],
}

# Bootstrap values are copied once into tenant-owned, versioned configuration.
# Every runtime decision reads the persisted document after bootstrap.
DEFAULT_CONFIGURATION: dict[str, Any] = {
    "environment": "production",
    "environment_registry": ["development", "staging", "production"],
    "resource_name_min_length": 1,
    "resource_name_max_length": 255,
    "resource_description_default": "",
    "resource_config_default": {},
    "resource_initially_active": True,
    "writable_fields": ["name", "description", "config"],
    "filter_fields": ["is_active"],
    "search_fields": ["name", "description"],
    "ordering_fields": ["name", "created_at", "updated_at"],
    "default_ordering": "-created_at",
    "page_size": 25,
    "max_page_size": 100,
    "deletion_confirmation_message": "Archive this API resource? It can be restored later.",
    "activation_enabled": True,
    "deactivation_enabled": True,
    "health_cache_ttl_seconds": 10,
    "table_skeleton_rows": 5,
    "form_description_rows": 4,
    "feature_enabled": True,
    "rollout_percentage": 100,
    "rollout_roles": [],
    "rollout_cohorts": [],
    "allowed_resource_config_keys": [],
    "validation_limits": {
        "list_max_items": 64,
        "list_item_max_length": 128,
        "resource_name_minimum_floor": 1,
        "resource_name_minimum_ceiling": 128,
        "resource_name_maximum_floor": 1,
        "resource_name_maximum_ceiling": 255,
        "resource_description_max_length": 4_000,
        "page_size_minimum": 1,
        "page_size_maximum": 100,
        "deletion_confirmation_max_length": 512,
        "health_cache_ttl_minimum": 1,
        "health_cache_ttl_maximum": 300,
        "table_skeleton_rows_minimum": 1,
        "table_skeleton_rows_maximum": 20,
        "form_description_rows_minimum": 2,
        "form_description_rows_maximum": 20,
        "rollout_percentage_minimum": 0,
        "rollout_percentage_maximum": 100,
        "configuration_history_page_size": 25,
        "configuration_history_max_page_size": 100,
        "configuration_history_max_page": 10_000,
        "configuration_version_reason_max_length": 64,
        "resource_version_reason_max_length": 64,
        "audit_target_type_max_length": 32,
        "audit_action_max_length": 64,
    },
    "configuration_version_reasons": ["bootstrap", "update", "rollback", "import"],
    "resource_version_reasons": [
        "create",
        "update",
        "archive",
        "restore",
        "activate",
        "deactivate",
        "rollback",
        "migration_backfill",
    ],
    "audit_target_types": ["configuration", "resource"],
    "audit_actions": [
        "bootstrap",
        "update",
        "rollback",
        "import",
        "create",
        "archive",
        "restore",
        "activate",
        "deactivate",
    ],
    "rollout_strategy": "tenant_uuid_modulo",
    "rollout_bucket_count": 100,
    "quota_cost": 1,
    "navigation": {
        "resources_list": {"order": 340},
        "resources_create": {"order": 341},
        "resources_detail": {"order": 342},
        "configuration": {"order": 343},
    },
}

CONFIGURATION_KEYS = frozenset(DEFAULT_CONFIGURATION)
RESOURCE_FIELD_REGISTRY = {
    "writable_fields": frozenset(DEFAULT_CONFIGURATION["writable_fields"]),
    "filter_fields": frozenset(DEFAULT_CONFIGURATION["filter_fields"]),
    "search_fields": frozenset(DEFAULT_CONFIGURATION["search_fields"]),
    "ordering_fields": frozenset(DEFAULT_CONFIGURATION["ordering_fields"]),
}
ROLLOUT_STRATEGIES = frozenset({"tenant_uuid_modulo"})
REQUIRED_CONFIGURATION_VERSION_REASONS = frozenset({"bootstrap", "update", "rollback", "import"})
REQUIRED_RESOURCE_VERSION_REASONS = frozenset(
    {"create", "update", "archive", "restore", "activate", "deactivate", "rollback"}
)
REQUIRED_AUDIT_TARGET_TYPES = frozenset({"configuration", "resource"})
REQUIRED_AUDIT_ACTIONS = REQUIRED_CONFIGURATION_VERSION_REASONS | REQUIRED_RESOURCE_VERSION_REASONS
_ENVIRONMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


class ConfigurationValidationError(ValueError):
    """A configuration document failed server-side validation."""

    def __init__(self, errors: Mapping[str, str]):
        super().__init__("Configuration document is invalid.")
        self.errors = dict(errors)


class IdempotencyConflictError(ValueError):
    """An idempotency key was reused for a different operation."""


def _uuid(value: object, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{field} must be a valid UUID.") from exc


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    normalized = value.strip()
    if len(normalized) > PLATFORM_HARD_CEILINGS["evidence_identity_length"]:
        raise ValueError(f"{field} exceeds its safe storage limit.")
    return normalized


def _string_list(
    value: object,
    field: str,
    *,
    allowed: frozenset[str] | None,
    maximum_items: int,
    maximum_item_length: int,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ConfigurationValidationError({field: f"Must be a list with at most {maximum_items} items."})
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > maximum_item_length:
            raise ConfigurationValidationError(
                {field: f"Each value must be a non-blank string of at most {maximum_item_length} characters."}
            )
        candidate = item.strip()
        if allowed is not None and candidate not in allowed:
            raise ConfigurationValidationError({field: f"Unsupported value: {candidate}."})
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ConfigurationValidationError({field: f"Must be an integer from {minimum} to {maximum}."})
    return value


def _environment(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigurationValidationError({"environment": "Must be a string."})
    normalized = value.strip().lower()
    if len(normalized) > PLATFORM_HARD_CEILINGS["environment_length"] or not _ENVIRONMENT_PATTERN.fullmatch(normalized):
        raise ConfigurationValidationError(
            {"environment": "Must be a lowercase environment identifier using letters, digits, and hyphens."}
        )
    return normalized


def runtime_environment() -> str:
    """Return the deployment-selected runtime policy environment."""

    return _environment(os.environ.get("API_MANAGEMENT_RUNTIME_ENVIRONMENT", "production"))


def _validation_limits(value: object) -> dict[str, int]:
    defaults = DEFAULT_CONFIGURATION["validation_limits"]
    if not isinstance(value, Mapping) or set(value) != set(defaults):
        raise ConfigurationValidationError({"validation_limits": "Must contain the complete governed limit set."})
    limits: dict[str, int] = {}
    for key, maximum in PLATFORM_VALIDATION_LIMIT_CEILINGS.items():
        limits[key] = _bounded_int(value[key], f"validation_limits.{key}", 0 if "rollout" in key else 1, maximum)
    for prefix in (
        "resource_name_minimum",
        "resource_name_maximum",
        "page_size",
        "health_cache_ttl",
        "table_skeleton_rows",
        "form_description_rows",
        "rollout_percentage",
        "configuration_history",
    ):
        low_key = f"{prefix}_floor" if prefix.startswith("resource_name") else f"{prefix}_minimum"
        high_key = f"{prefix}_ceiling" if prefix.startswith("resource_name") else f"{prefix}_maximum"
        if prefix == "configuration_history":
            low_key, high_key = "configuration_history_page_size", "configuration_history_max_page_size"
        if limits[low_key] > limits[high_key]:
            raise ConfigurationValidationError({"validation_limits": f"{low_key} cannot exceed {high_key}."})
    if limits["rollout_percentage_maximum"] == 0:
        raise ConfigurationValidationError(
            {"validation_limits.rollout_percentage_maximum": "Must be greater than zero."}
        )
    if limits["rollout_percentage_minimum"] != 0:
        raise ConfigurationValidationError(
            {
                "validation_limits.rollout_percentage_minimum": (
                    "Must remain zero so disabling the feature has a valid fail-closed state."
                )
            }
        )
    return limits


def validate_configuration_document(document: object, *, expected_environment: object | None = None) -> dict[str, Any]:
    """Return a normalized complete document or reject it before persistence."""

    if not isinstance(document, Mapping):
        raise ConfigurationValidationError({"document": "Must be an object."})
    unknown = set(document) - CONFIGURATION_KEYS
    missing = CONFIGURATION_KEYS - set(document)
    if unknown or missing:
        errors = {key: "Unknown configuration field." for key in sorted(unknown)}
        errors.update({key: "Configuration field is required." for key in sorted(missing)})
        raise ConfigurationValidationError(errors)

    normalized = copy.deepcopy(dict(document))
    normalized["environment"] = _environment(normalized["environment"])
    if expected_environment is not None and normalized["environment"] != _environment(expected_environment):
        raise ConfigurationValidationError({"environment": "Must match the selected environment."})
    limits = _validation_limits(normalized["validation_limits"])
    normalized["validation_limits"] = limits
    registry = _string_list(
        normalized["environment_registry"],
        "environment_registry",
        allowed=None,
        maximum_items=PLATFORM_HARD_CEILINGS["environment_count"],
        maximum_item_length=PLATFORM_HARD_CEILINGS["environment_length"],
    )
    if any(_environment(item) != item for item in registry) or normalized["environment"] not in registry:
        raise ConfigurationValidationError(
            {"environment_registry": "Must contain valid identifiers and the selected environment."}
        )
    normalized["environment_registry"] = registry
    minimum = _bounded_int(
        normalized["resource_name_min_length"],
        "resource_name_min_length",
        limits["resource_name_minimum_floor"],
        limits["resource_name_minimum_ceiling"],
    )
    maximum = _bounded_int(
        normalized["resource_name_max_length"],
        "resource_name_max_length",
        limits["resource_name_maximum_floor"],
        limits["resource_name_maximum_ceiling"],
    )
    if minimum > maximum:
        raise ConfigurationValidationError({"resource_name_min_length": "Cannot exceed resource_name_max_length."})
    description = normalized["resource_description_default"]
    if not isinstance(description, str) or len(description) > limits["resource_description_max_length"]:
        raise ConfigurationValidationError(
            {"resource_description_default": "Exceeds the configured description length limit."}
        )
    string_list_kwargs = {
        "allowed": None,
        "maximum_items": limits["list_max_items"],
        "maximum_item_length": limits["list_item_max_length"],
    }
    evidence_lists = (
        (
            "configuration_version_reasons",
            limits["configuration_version_reason_max_length"],
            REQUIRED_CONFIGURATION_VERSION_REASONS,
        ),
        (
            "resource_version_reasons",
            limits["resource_version_reason_max_length"],
            REQUIRED_RESOURCE_VERSION_REASONS,
        ),
        (
            "audit_target_types",
            limits["audit_target_type_max_length"],
            REQUIRED_AUDIT_TARGET_TYPES,
        ),
        (
            "audit_actions",
            limits["audit_action_max_length"],
            REQUIRED_AUDIT_ACTIONS,
        ),
    )
    for evidence_field, maximum_item_length, required_values in evidence_lists:
        normalized[evidence_field] = _string_list(
            normalized[evidence_field],
            evidence_field,
            allowed=None,
            maximum_items=limits["list_max_items"],
            maximum_item_length=maximum_item_length,
        )
        missing_evidence_values = required_values - set(normalized[evidence_field])
        if missing_evidence_values:
            raise ConfigurationValidationError(
                {
                    evidence_field: (
                        "Cannot remove operation values required by the module engine: "
                        f"{', '.join(sorted(missing_evidence_values))}."
                    )
                }
            )
    allowed_keys = _string_list(
        normalized["allowed_resource_config_keys"], "allowed_resource_config_keys", **string_list_kwargs
    )
    default_resource_config = normalized["resource_config_default"]
    if not isinstance(default_resource_config, dict):
        raise ConfigurationValidationError({"resource_config_default": "Must be an object."})
    disallowed_default_keys = set(default_resource_config) - set(allowed_keys)
    if disallowed_default_keys:
        raise ConfigurationValidationError(
            {"resource_config_default": "Contains keys absent from allowed_resource_config_keys."}
        )
    for field in (
        "resource_initially_active",
        "activation_enabled",
        "deactivation_enabled",
        "feature_enabled",
    ):
        if not isinstance(normalized[field], bool):
            raise ConfigurationValidationError({field: "Must be a boolean."})
    normalized["writable_fields"] = _string_list(
        normalized["writable_fields"],
        "writable_fields",
        allowed=RESOURCE_FIELD_REGISTRY["writable_fields"],
        maximum_items=limits["list_max_items"],
        maximum_item_length=limits["list_item_max_length"],
    )
    normalized["filter_fields"] = _string_list(
        normalized["filter_fields"],
        "filter_fields",
        allowed=RESOURCE_FIELD_REGISTRY["filter_fields"],
        maximum_items=limits["list_max_items"],
        maximum_item_length=limits["list_item_max_length"],
    )
    normalized["search_fields"] = _string_list(
        normalized["search_fields"],
        "search_fields",
        allowed=RESOURCE_FIELD_REGISTRY["search_fields"],
        maximum_items=limits["list_max_items"],
        maximum_item_length=limits["list_item_max_length"],
    )
    normalized["ordering_fields"] = _string_list(
        normalized["ordering_fields"],
        "ordering_fields",
        allowed=RESOURCE_FIELD_REGISTRY["ordering_fields"],
        maximum_items=limits["list_max_items"],
        maximum_item_length=limits["list_item_max_length"],
    )
    default_ordering = normalized["default_ordering"]
    if not isinstance(default_ordering, str) or default_ordering.lstrip("-") not in normalized["ordering_fields"]:
        raise ConfigurationValidationError(
            {"default_ordering": "Must select an enabled ordering field, optionally prefixed with '-'."}
        )
    page_size = _bounded_int(
        normalized["page_size"], "page_size", limits["page_size_minimum"], limits["page_size_maximum"]
    )
    max_page_size = _bounded_int(
        normalized["max_page_size"], "max_page_size", limits["page_size_minimum"], limits["page_size_maximum"]
    )
    if page_size > max_page_size:
        raise ConfigurationValidationError({"page_size": "Cannot exceed max_page_size."})
    confirmation = normalized["deletion_confirmation_message"]
    if (
        not isinstance(confirmation, str)
        or not confirmation.strip()
        or len(confirmation) > limits["deletion_confirmation_max_length"]
    ):
        raise ConfigurationValidationError(
            {"deletion_confirmation_message": "Must be non-blank and within the configured length limit."}
        )
    normalized["deletion_confirmation_message"] = confirmation.strip()
    _bounded_int(
        normalized["health_cache_ttl_seconds"],
        "health_cache_ttl_seconds",
        limits["health_cache_ttl_minimum"],
        limits["health_cache_ttl_maximum"],
    )
    _bounded_int(
        normalized["table_skeleton_rows"],
        "table_skeleton_rows",
        limits["table_skeleton_rows_minimum"],
        limits["table_skeleton_rows_maximum"],
    )
    _bounded_int(
        normalized["form_description_rows"],
        "form_description_rows",
        limits["form_description_rows_minimum"],
        limits["form_description_rows_maximum"],
    )
    rollout = _bounded_int(
        normalized["rollout_percentage"],
        "rollout_percentage",
        limits["rollout_percentage_minimum"],
        limits["rollout_percentage_maximum"],
    )
    if not normalized["feature_enabled"] and rollout != 0:
        raise ConfigurationValidationError({"rollout_percentage": "Must be zero while feature_enabled is false."})
    if not normalized["feature_enabled"] and (normalized["activation_enabled"] or normalized["deactivation_enabled"]):
        raise ConfigurationValidationError(
            {"activation_enabled": "Lifecycle transitions must be disabled while the feature is disabled."}
        )
    normalized["rollout_roles"] = _string_list(normalized["rollout_roles"], "rollout_roles", **string_list_kwargs)
    normalized["rollout_cohorts"] = _string_list(normalized["rollout_cohorts"], "rollout_cohorts", **string_list_kwargs)
    if rollout == limits["rollout_percentage_maximum"] and (
        normalized["rollout_roles"] or normalized["rollout_cohorts"]
    ):
        raise ConfigurationValidationError(
            {"rollout_roles": "Role and cohort targeting must be empty for a full configured rollout."}
        )
    normalized["allowed_resource_config_keys"] = allowed_keys
    if normalized["rollout_strategy"] not in ROLLOUT_STRATEGIES:
        raise ConfigurationValidationError({"rollout_strategy": "Unsupported rollout strategy."})
    normalized["rollout_bucket_count"] = _bounded_int(
        normalized["rollout_bucket_count"], "rollout_bucket_count", 1, PLATFORM_HARD_CEILINGS["rollout_buckets"]
    )
    normalized["quota_cost"] = _bounded_int(
        normalized["quota_cost"], "quota_cost", 1, PLATFORM_HARD_CEILINGS["quota_cost"]
    )
    navigation = normalized["navigation"]
    if not isinstance(navigation, Mapping) or set(navigation) != set(DEFAULT_CONFIGURATION["navigation"]):
        raise ConfigurationValidationError({"navigation": "Must contain every module navigation target."})
    normalized_navigation: dict[str, dict[str, int]] = {}
    for target, metadata in navigation.items():
        if not isinstance(metadata, Mapping) or set(metadata) != {"order"}:
            raise ConfigurationValidationError({"navigation": f"{target} must contain only order."})
        normalized_navigation[target] = {
            "order": _bounded_int(
                metadata["order"], f"navigation.{target}.order", 0, PLATFORM_HARD_CEILINGS["navigation_order"]
            )
        }
    normalized["navigation"] = normalized_navigation
    return normalized


def _resource_value(resource: ApiManagementResource) -> dict[str, Any]:
    return {
        "id": str(resource.id),
        "name": resource.name,
        "description": resource.description,
        "is_active": resource.is_active,
        "config": copy.deepcopy(resource.config),
        "version": resource.version,
        "deleted_at": resource.deleted_at.isoformat() if resource.deleted_at else None,
        "deleted_by": resource.deleted_by,
    }


def _validate_evidence_value(
    policy: Mapping[str, Any],
    *,
    value: str,
    allowlist_field: str,
    maximum_length_field: str,
) -> str:
    """Fail closed when immutable evidence metadata violates tenant policy."""

    limits = policy.get("validation_limits")
    allowlist = policy.get(allowlist_field)
    if (
        not isinstance(limits, Mapping)
        or not isinstance(allowlist, list)
        or value not in allowlist
        or not isinstance(limits.get(maximum_length_field), int)
        or len(value) > limits[maximum_length_field]
    ):
        raise ConfigurationValidationError(
            {allowlist_field: f"Immutable evidence value {value!r} is not permitted by configuration."}
        )
    return value


def _record_audit(
    policy: Mapping[str, Any],
    *,
    tenant_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
    action: str,
    actor_id: str,
    correlation_id: str,
    idempotency_key: uuid.UUID,
    before_value: dict[str, Any] | None,
    after_value: dict[str, Any] | None,
    version: int,
) -> ApiManagementAuditRecord:
    _validate_evidence_value(
        policy,
        value=target_type,
        allowlist_field="audit_target_types",
        maximum_length_field="audit_target_type_max_length",
    )
    _validate_evidence_value(
        policy,
        value=action,
        allowlist_field="audit_actions",
        maximum_length_field="audit_action_max_length",
    )
    return ApiManagementAuditRecord.objects.create(
        tenant_id=tenant_id,
        target_type=target_type,
        target_id=target_id,
        action=action,
        actor_id=actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        before_value=before_value,
        after_value=after_value,
        version=version,
    )


def _record_resource_version(
    resource: ApiManagementResource,
    *,
    policy: Mapping[str, Any],
    actor_id: str,
    correlation_id: str,
    idempotency_key: uuid.UUID,
    reason: str,
    source_version: int | None = None,
) -> ApiManagementResourceVersion:
    _validate_evidence_value(
        policy,
        value=reason,
        allowlist_field="resource_version_reasons",
        maximum_length_field="resource_version_reason_max_length",
    )
    return ApiManagementResourceVersion.objects.create(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        version=resource.version,
        snapshot=_resource_value(resource),
        actor_id=actor_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        reason=reason,
        source_version=source_version,
    )


class ApiManagementService:
    """Tenant-scoped, audited and idempotent module operations."""

    @staticmethod
    def default_configuration(environment: object = "production") -> dict[str, Any]:
        selected = _environment(environment)
        document = copy.deepcopy(DEFAULT_CONFIGURATION)
        document["environment"] = selected
        if selected not in document["environment_registry"]:
            document["environment_registry"].append(selected)
        return document

    @staticmethod
    def quota_cost_for_access(tenant_id: object, environment: object) -> int:
        """Resolve quota policy without allowing malformed or missing state to disable enforcement."""

        try:
            tenant = _uuid(tenant_id, "tenant_id")
            selected_environment = _environment(environment)
            configuration = (
                ApiManagementConfiguration.objects.filter(
                    tenant_id=tenant,
                    environment=selected_environment,
                )
                .only("document")
                .first()
            )
            candidate = (
                configuration.document
                if configuration is not None
                else ApiManagementService.default_configuration(selected_environment)
            )
            document = validate_configuration_document(
                candidate,
                expected_environment=selected_environment,
            )
            return document["quota_cost"]
        except (ConfigurationValidationError, ValueError, TypeError):
            return PLATFORM_HARD_CEILINGS["quota_cost"]

    @staticmethod
    def _ensure_registered_environment(tenant_id: uuid.UUID, environment: str) -> None:
        configurations = list(
            ApiManagementConfiguration.objects.filter(tenant_id=tenant_id).values(
                "environment",
                "document",
            )
        )
        if not configurations:
            registered = set(DEFAULT_CONFIGURATION["environment_registry"])
        else:
            registered = {str(item["environment"]) for item in configurations}
            for item in configurations:
                document = item["document"]
                validated = validate_configuration_document(
                    document,
                    expected_environment=item["environment"],
                )
                registered.update(validated["environment_registry"])
        if environment not in registered:
            raise ConfigurationValidationError(
                {
                    "environment": (
                        "Environment is not registered. Add it to an existing governed "
                        "configuration before creating its isolated configuration."
                    )
                }
            )

    @staticmethod
    def _context(
        tenant_id: object,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
    ) -> tuple[uuid.UUID, str, str, uuid.UUID]:
        return (
            _uuid(tenant_id, "tenant_id"),
            _required_text(actor_id, "actor_id"),
            _required_text(correlation_id, "correlation_id"),
            _uuid(idempotency_key, "idempotency_key"),
        )

    @staticmethod
    def _bootstrap_configuration(
        tenant_id: uuid.UUID,
        environment: str,
        actor_id: str,
        correlation_id: str,
    ) -> ApiManagementConfiguration:
        ApiManagementService._ensure_registered_environment(tenant_id, environment)
        configuration = ApiManagementConfiguration.objects.filter(tenant_id=tenant_id, environment=environment).first()
        if configuration is not None:
            return configuration
        document = validate_configuration_document(
            ApiManagementService.default_configuration(environment), expected_environment=environment
        )
        bootstrap_key = uuid.uuid4()
        try:
            with transaction.atomic():
                configuration = ApiManagementConfiguration.objects.create(
                    tenant_id=tenant_id,
                    environment=environment,
                    document=document,
                    version=1,
                    updated_by=actor_id,
                )
                _validate_evidence_value(
                    document,
                    value="bootstrap",
                    allowlist_field="configuration_version_reasons",
                    maximum_length_field="configuration_version_reason_max_length",
                )
                ApiManagementConfigurationVersion.objects.create(
                    tenant_id=tenant_id,
                    environment=environment,
                    version=1,
                    document=document,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    idempotency_key=bootstrap_key,
                    reason="bootstrap",
                )
                _record_audit(
                    document,
                    tenant_id=tenant_id,
                    target_type="configuration",
                    target_id=configuration.id,
                    action="bootstrap",
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                    idempotency_key=bootstrap_key,
                    before_value=None,
                    after_value=document,
                    version=1,
                )
            return configuration
        except IntegrityError:
            existing = ApiManagementConfiguration.objects.filter(tenant_id=tenant_id, environment=environment).first()
            if existing is None:
                raise
            return existing

    @transaction.atomic
    def get_configuration(
        self,
        tenant_id: object,
        *,
        environment: object = "production",
        actor_id: object,
        correlation_id: object,
    ) -> ApiManagementConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _required_text(actor_id, "actor_id")
        correlation = _required_text(correlation_id, "correlation_id")
        selected_environment = _environment(environment)
        return self._bootstrap_configuration(tenant, selected_environment, actor, correlation)

    def preview_configuration(
        self, tenant_id: object, document: object, *, environment: object = "production"
    ) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        selected_environment = _environment(environment)
        self._ensure_registered_environment(tenant, selected_environment)
        normalized = validate_configuration_document(document, expected_environment=selected_environment)
        current = ApiManagementConfiguration.objects.filter(tenant_id=tenant, environment=selected_environment).first()
        before = current.document if current else self.default_configuration(selected_environment)
        changes = [
            {"field": key, "before": copy.deepcopy(before.get(key)), "after": copy.deepcopy(normalized[key])}
            for key in sorted(CONFIGURATION_KEYS)
            if before.get(key) != normalized[key]
        ]
        return {"valid": True, "normalized_document": normalized, "changes": changes}

    @transaction.atomic
    def update_configuration(
        self,
        tenant_id: object,
        document: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        environment: object = "production",
        reason: str = "update",
    ) -> ApiManagementConfiguration:
        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        selected_environment = _environment(environment)
        normalized = validate_configuration_document(document, expected_environment=selected_environment)
        replay = ApiManagementConfigurationVersion.objects.filter(
            tenant_id=tenant, environment=selected_environment, idempotency_key=key
        ).first()
        if replay is not None:
            if replay.document != normalized or replay.reason != reason:
                raise IdempotencyConflictError("Idempotency key was already used for another configuration mutation.")
            current = ApiManagementConfiguration.objects.get(tenant_id=tenant, environment=selected_environment)
            if current.version != replay.version:
                raise IdempotencyConflictError("The original configuration response is no longer current.")
            return current

        configuration = self._bootstrap_configuration(tenant, selected_environment, actor, correlation)
        configuration = ApiManagementConfiguration.objects.select_for_update().get(pk=configuration.pk)
        before = copy.deepcopy(configuration.document)
        next_version = configuration.version + 1
        configuration.document = normalized
        configuration.version = next_version
        configuration.updated_by = actor
        configuration.save(update_fields=["document", "version", "updated_by", "updated_at"])
        _validate_evidence_value(
            normalized,
            value=reason,
            allowlist_field="configuration_version_reasons",
            maximum_length_field="configuration_version_reason_max_length",
        )
        ApiManagementConfigurationVersion.objects.create(
            tenant_id=tenant,
            environment=selected_environment,
            version=next_version,
            document=normalized,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason=reason,
        )
        _record_audit(
            normalized,
            tenant_id=tenant,
            target_type="configuration",
            target_id=configuration.id,
            action=reason,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            before_value=before,
            after_value=normalized,
            version=next_version,
        )
        return configuration

    def configuration_history(
        self,
        tenant_id: object,
        *,
        environment: object = "production",
        page: object = 1,
        page_size: object | None = None,
        actor_id: object,
        correlation_id: object,
    ) -> tuple[QuerySet[ApiManagementConfigurationVersion], int, int, int]:
        tenant = _uuid(tenant_id, "tenant_id")
        selected_environment = _environment(environment)
        configuration = self.get_configuration(
            tenant,
            environment=selected_environment,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        limits = configuration.document["validation_limits"]
        resolved_page = _bounded_int(
            page,
            "page",
            1,
            limits["configuration_history_max_page"],
        )
        requested_size = limits["configuration_history_page_size"] if page_size is None else page_size
        resolved_size = _bounded_int(
            requested_size,
            "page_size",
            1,
            limits["configuration_history_max_page_size"],
        )
        queryset = ApiManagementConfigurationVersion.objects.filter(
            tenant_id=tenant, environment=selected_environment
        ).order_by("-version", "-created_at", "-id")
        count = queryset.count()
        start = (resolved_page - 1) * resolved_size
        return queryset[slice(start, start + resolved_size)], count, resolved_page, resolved_size

    def rollback_configuration(
        self,
        tenant_id: object,
        version: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        environment: object = "production",
    ) -> ApiManagementConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        selected_environment = _environment(environment)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer.")
        snapshot = ApiManagementConfigurationVersion.objects.filter(
            tenant_id=tenant, environment=selected_environment, version=version
        ).first()
        if snapshot is None:
            raise LookupError("Configuration version was not found.")
        return self.update_configuration(
            tenant,
            snapshot.document,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            environment=selected_environment,
            reason="rollback",
        )

    def export_configuration(
        self,
        tenant_id: object,
        *,
        environment: object = "production",
        actor_id: object,
        correlation_id: object,
    ) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        configuration = self.get_configuration(
            tenant,
            environment=environment,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        return {
            "module": "api_management",
            "schema_version": PORTABLE_SCHEMA_VERSION,
            "version": configuration.version,
            "environment": configuration.environment,
            "document": copy.deepcopy(configuration.document),
        }

    def import_configuration(
        self,
        tenant_id: object,
        portable_document: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        environment: object = "production",
    ) -> ApiManagementConfiguration:
        if not isinstance(portable_document, Mapping):
            raise ConfigurationValidationError({"document": "Import must be an object."})
        if "document" in portable_document:
            if portable_document.get("module") not in (None, "api_management"):
                raise ConfigurationValidationError({"module": "Import belongs to another module."})
            if portable_document.get("schema_version") not in (None, PORTABLE_SCHEMA_VERSION):
                raise ConfigurationValidationError({"schema_version": "Unsupported import schema version."})
            document = portable_document["document"]
        else:
            document = portable_document
        if not isinstance(document, Mapping):
            raise ConfigurationValidationError({"document": "Imported configuration document must be an object."})
        selected_environment = _environment(environment)
        promoted_document = copy.deepcopy(dict(document))
        promoted_document["environment"] = selected_environment
        registry = promoted_document.get("environment_registry")
        if isinstance(registry, list) and selected_environment not in registry:
            promoted_document["environment_registry"] = [*registry, selected_environment]
        return self.update_configuration(
            tenant_id,
            promoted_document,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            environment=selected_environment,
            reason="import",
        )

    def configuration_schema(
        self,
        tenant_id: object,
        *,
        environment: object = "production",
        actor_id: object,
        correlation_id: object,
    ) -> dict[str, Any]:
        """Return schema metadata derived from the selected governed document."""

        tenant = _uuid(tenant_id, "tenant_id")
        selected_environment = _environment(environment)
        configuration = self.get_configuration(
            tenant,
            environment=selected_environment,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        document = validate_configuration_document(configuration.document, expected_environment=selected_environment)
        limits = document["validation_limits"]

        def field(
            label: str,
            help_text: str,
            field_type: str,
            **metadata: Any,
        ) -> dict[str, Any]:
            return {"label": label, "help_text": help_text, "type": field_type, **metadata}

        fields = {
            "environment": field(
                "Environment",
                "Selects an isolated configuration and version history for this deployment environment.",
                "select",
                options=document["environment_registry"],
            ),
            "resource_name_min_length": field(
                "Minimum resource name length",
                "Rejects shorter resource names during create and update.",
                "integer",
                min_value=limits["resource_name_minimum_floor"],
                max_value=limits["resource_name_minimum_ceiling"],
                unit="characters",
            ),
            "resource_name_max_length": field(
                "Maximum resource name length",
                "Rejects longer resource names before the platform storage ceiling is reached.",
                "integer",
                min_value=limits["resource_name_maximum_floor"],
                max_value=limits["resource_name_maximum_ceiling"],
                unit="characters",
            ),
            "resource_description_default": field(
                "Default resource description",
                "Supplies the description when a create request omits one; future creates only.",
                "string",
                max_length=limits["resource_description_max_length"],
            ),
            "resource_config_default": field(
                "Default resource configuration",
                "Supplies a JSON object when a create request omits config; keys must be enabled below.",
                "json_object",
            ),
            "resource_initially_active": field(
                "Create resources active",
                "Controls the initial lifecycle state of newly created resources.",
                "boolean",
            ),
            "page_size": field(
                "Default page size",
                "Controls the default number of resources returned per page.",
                "integer",
                min_value=limits["page_size_minimum"],
                max_value=limits["page_size_maximum"],
                unit="rows",
            ),
            "max_page_size": field(
                "Maximum page size",
                "Caps client-requested resource page sizes.",
                "integer",
                min_value=limits["page_size_minimum"],
                max_value=limits["page_size_maximum"],
                unit="rows",
            ),
            "health_cache_ttl_seconds": field(
                "Health cache TTL",
                "Controls how long a successful dependency probe remains cached; lower values increase probe load.",
                "integer",
                min_value=limits["health_cache_ttl_minimum"],
                max_value=limits["health_cache_ttl_maximum"],
                unit="seconds",
            ),
            "table_skeleton_rows": field(
                "Table skeleton rows",
                "Controls placeholder rows while resource tables load; this affects perceived layout stability only.",
                "integer",
                min_value=limits["table_skeleton_rows_minimum"],
                max_value=limits["table_skeleton_rows_maximum"],
                unit="rows",
            ),
            "form_description_rows": field(
                "Description form rows",
                "Controls the initial description editor height without limiting description content.",
                "integer",
                min_value=limits["form_description_rows_minimum"],
                max_value=limits["form_description_rows_maximum"],
                unit="rows",
            ),
            "rollout_percentage": field(
                "Rollout percentage",
                "Enables a deterministic share of tenants in addition to explicitly targeted roles and cohorts.",
                "integer",
                min_value=limits["rollout_percentage_minimum"],
                max_value=limits["rollout_percentage_maximum"],
                unit="percent",
            ),
            "feature_enabled": field(
                "API management enabled",
                "Disables all resource operations when off; lifecycle controls and rollout "
                "are reset by dependency rules.",
                "boolean",
            ),
            "rollout_roles": field(
                "Targeted roles",
                "Comma-separated tenant roles enabled independently of the percentage rollout.",
                "string_list",
                max_length=limits["list_item_max_length"],
                max_items=limits["list_max_items"],
            ),
            "rollout_cohorts": field(
                "Targeted cohorts",
                "Comma-separated tenant cohorts enabled independently of the percentage rollout.",
                "string_list",
                max_length=limits["list_item_max_length"],
                max_items=limits["list_max_items"],
            ),
            "writable_fields": field(
                "Writable resource fields",
                "Allow-list of resource fields accepted during update.",
                "multi_select",
                options=sorted(RESOURCE_FIELD_REGISTRY["writable_fields"]),
            ),
            "filter_fields": field(
                "Filter fields",
                "Allow-list of resource fields accepted as exact filters.",
                "multi_select",
                options=sorted(RESOURCE_FIELD_REGISTRY["filter_fields"]),
            ),
            "search_fields": field(
                "Search fields",
                "Allow-list of resource fields included in text search.",
                "multi_select",
                options=sorted(RESOURCE_FIELD_REGISTRY["search_fields"]),
            ),
            "ordering_fields": field(
                "Ordering fields",
                "Allow-list of resource fields accepted for sorting.",
                "multi_select",
                options=sorted(RESOURCE_FIELD_REGISTRY["ordering_fields"]),
            ),
            "default_ordering": field(
                "Default ordering",
                "Ordering applied when a resource-list request does not select one.",
                "select",
                options=[
                    option
                    for ordering_field in document["ordering_fields"]
                    for option in (ordering_field, f"-{ordering_field}")
                ],
            ),
            "allowed_resource_config_keys": field(
                "Allowed resource config keys",
                "Allow-list of JSON keys accepted in resource configuration objects.",
                "string_list",
                max_length=limits["list_item_max_length"],
                max_items=limits["list_max_items"],
            ),
            "deletion_confirmation_message": field(
                "Deletion confirmation",
                "Message shown before archival; resources remain recoverable.",
                "string",
                max_length=limits["deletion_confirmation_max_length"],
            ),
            "activation_enabled": field(
                "Activation enabled",
                "Allows operators to activate inactive resources while the module feature is enabled.",
                "boolean",
            ),
            "deactivation_enabled": field(
                "Deactivation enabled",
                "Allows operators to deactivate active resources while the module feature is enabled.",
                "boolean",
            ),
            "rollout_strategy": field(
                "Rollout strategy",
                "Selects the versioned deterministic audience allocation strategy.",
                "select",
                options=sorted(ROLLOUT_STRATEGIES),
            ),
            "rollout_bucket_count": field(
                "Rollout bucket count",
                "Controls deterministic allocation granularity; changing it can move tenants between buckets.",
                "integer",
                min_value=1,
                max_value=PLATFORM_HARD_CEILINGS["rollout_buckets"],
                unit="buckets",
            ),
            "quota_cost": field(
                "Quota cost",
                "Quota units charged by the access decision pipeline for each module request.",
                "integer",
                min_value=1,
                max_value=PLATFORM_HARD_CEILINGS["quota_cost"],
                unit="units",
            ),
            "configuration_version_reasons": field(
                "Configuration version reasons",
                "Governed allow-list for immutable configuration-version evidence; "
                "engine-required values cannot be removed.",
                "string_list",
                max_length=limits["configuration_version_reason_max_length"],
                max_items=limits["list_max_items"],
            ),
            "resource_version_reasons": field(
                "Resource version reasons",
                "Governed allow-list for immutable resource-version evidence; "
                "engine-required values cannot be removed.",
                "string_list",
                max_length=limits["resource_version_reason_max_length"],
                max_items=limits["list_max_items"],
            ),
            "audit_target_types": field(
                "Audit target types",
                "Governed allow-list for immutable audit target categories; engine-required values cannot be removed.",
                "string_list",
                max_length=limits["audit_target_type_max_length"],
                max_items=limits["list_max_items"],
            ),
            "audit_actions": field(
                "Audit actions",
                "Governed allow-list for immutable audit actions; engine-required values cannot be removed.",
                "string_list",
                max_length=limits["audit_action_max_length"],
                max_items=limits["list_max_items"],
            ),
        }
        for limit_name, platform_maximum in PLATFORM_VALIDATION_LIMIT_CEILINGS.items():
            fields[f"validation_limits.{limit_name}"] = field(
                limit_name.replace("_", " ").title(),
                "Tenant-tunable validation guard rail; the platform ceiling remains enforced independently.",
                "integer",
                min_value=0 if "rollout_percentage" in limit_name else 1,
                max_value=platform_maximum,
            )
        fields["environment_registry"] = field(
            "Environment registry",
            "Tenant-managed environment identifiers available for isolated configuration versions.",
            "string_list",
            max_length=PLATFORM_HARD_CEILINGS["environment_length"],
            max_items=PLATFORM_HARD_CEILINGS["environment_count"],
        )
        for navigation_target in document["navigation"]:
            fields[f"navigation.{navigation_target}.order"] = field(
                f"{navigation_target.replace('_', ' ').title()} navigation order",
                "Controls this page's position in tenant navigation without a source deployment.",
                "integer",
                min_value=0,
                max_value=PLATFORM_HARD_CEILINGS["navigation_order"],
            )
        environments = sorted(
            set(document["environment_registry"])
            | set(ApiManagementConfiguration.objects.filter(tenant_id=tenant).values_list("environment", flat=True))
        )
        return {
            "schema_version": 2,
            "environment": selected_environment,
            "environments": environments,
            "fields": fields,
            "dependencies": [
                {
                    "source_field": "feature_enabled",
                    "operator": "equals",
                    "value": False,
                    "target_fields": ["rollout_percentage"],
                    "effect": {"kind": "set", "value": limits["rollout_percentage_minimum"]},
                },
                {
                    "source_field": "feature_enabled",
                    "operator": "equals",
                    "value": False,
                    "target_fields": [
                        "activation_enabled",
                        "deactivation_enabled",
                    ],
                    "effect": {"kind": "set", "value": False},
                },
                {
                    "source_field": "feature_enabled",
                    "operator": "equals",
                    "value": False,
                    "target_fields": [
                        "rollout_percentage",
                        "activation_enabled",
                        "deactivation_enabled",
                    ],
                    "effect": {"kind": "disable"},
                },
                {
                    "source_field": "rollout_percentage",
                    "operator": "equals",
                    "value": limits["rollout_percentage_maximum"],
                    "target_fields": ["rollout_roles", "rollout_cohorts"],
                    "effect": {"kind": "clear"},
                },
                {
                    "source_field": "rollout_percentage",
                    "operator": "equals",
                    "value": limits["rollout_percentage_maximum"],
                    "target_fields": ["rollout_roles", "rollout_cohorts"],
                    "effect": {"kind": "disable"},
                },
            ],
            "navigation": copy.deepcopy(document["navigation"]),
            "platform_hard_ceilings": copy.deepcopy(PLATFORM_HARD_CEILINGS),
        }

    def _configuration_for_resource(
        self,
        tenant_id: uuid.UUID,
        environment: str,
        actor_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        configuration = self._bootstrap_configuration(tenant_id, environment, actor_id, correlation_id)
        return validate_configuration_document(configuration.document, expected_environment=environment)

    @staticmethod
    def _ensure_feature_available(
        policy: Mapping[str, Any],
        tenant_id: uuid.UUID,
        *,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
    ) -> None:
        """Apply the configured tenant/role/cohort phased rollout."""

        if not policy["feature_enabled"]:
            raise PermissionError("API management is disabled by tenant configuration.")
        targeted = bool(set(audience_roles) & set(policy["rollout_roles"])) or bool(
            set(audience_cohorts) & set(policy["rollout_cohorts"])
        )
        if policy["rollout_strategy"] != "tenant_uuid_modulo":
            raise PermissionError("Configured rollout strategy is unavailable.")
        bucket_count = policy["rollout_bucket_count"]
        maximum_percentage = policy["validation_limits"]["rollout_percentage_maximum"]
        enabled_buckets = policy["rollout_percentage"] * bucket_count // maximum_percentage
        percentage_enabled = tenant_id.int % bucket_count < enabled_buckets
        if not targeted and not percentage_enabled:
            raise PermissionError("API management is not enabled for this rollout audience.")

    @staticmethod
    def _validate_resource_values(
        policy: Mapping[str, Any],
        *,
        name: object,
        description: object,
        config: object,
    ) -> tuple[str, str, dict[str, Any]]:
        if not isinstance(name, str):
            raise ValueError("name must be a string.")
        normalized_name = name.strip()
        if not policy["resource_name_min_length"] <= len(normalized_name) <= policy["resource_name_max_length"]:
            raise ValueError("name violates the configured length limits.")
        if not isinstance(description, str):
            raise ValueError("description must be a string.")
        if len(description) > policy["validation_limits"]["resource_description_max_length"]:
            raise ValueError("description exceeds the configured length limit.")
        if not isinstance(config, dict):
            raise ValueError("config must be an object.")
        disallowed = set(config) - set(policy["allowed_resource_config_keys"])
        if disallowed:
            raise ValueError("config contains keys not enabled by tenant configuration.")
        return normalized_name, description, copy.deepcopy(config)

    @transaction.atomic
    def create_resource(
        self,
        tenant_id: object,
        name: object,
        description: object | None = None,
        config: object | None = None,
        created_by: object | None = None,
        *,
        actor_id: object | None = None,
        correlation_id: object,
        idempotency_key: object,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
        environment: object = "production",
    ) -> ApiManagementResource:
        actor_value = actor_id if actor_id is not None else created_by
        tenant, actor, correlation, key = self._context(tenant_id, actor_value, correlation_id, idempotency_key)
        selected_environment = _environment(environment)
        policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
        self._ensure_feature_available(
            policy,
            tenant,
            audience_roles=audience_roles,
            audience_cohorts=audience_cohorts,
        )
        resolved_description = policy["resource_description_default"] if description is None else description
        resolved_config = policy["resource_config_default"] if config is None else config
        normalized_name, normalized_description, normalized_config = self._validate_resource_values(
            policy,
            name=name,
            description=resolved_description,
            config=resolved_config,
        )
        existing = ApiManagementResource.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        expected = {
            "name": normalized_name,
            "description": normalized_description,
            "config": normalized_config,
            "is_active": policy["resource_initially_active"],
        }
        if existing is not None:
            actual = {field: getattr(existing, field) for field in expected}
            if actual != expected:
                raise IdempotencyConflictError("Idempotency key was already used for another resource request.")
            return existing
        resource = ApiManagementResource.objects.create(
            tenant_id=tenant,
            name=normalized_name,
            description=normalized_description,
            config=normalized_config,
            is_active=policy["resource_initially_active"],
            created_by=actor,
            idempotency_key=key,
        )
        _record_resource_version(
            resource,
            policy=policy,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason="create",
        )
        _record_audit(
            policy,
            tenant_id=tenant,
            target_type="resource",
            target_id=resource.id,
            action="create",
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            before_value=None,
            after_value=_resource_value(resource),
            version=resource.version,
        )
        logger.info(
            "api_management resource created",
            extra={"tenant_id": str(tenant), "resource_id": str(resource.id), "correlation_id": correlation},
        )
        return resource

    def get_resource(
        self, resource_id: object, tenant_id: object, *, include_deleted: bool = False
    ) -> ApiManagementResource | None:
        tenant = _uuid(tenant_id, "tenant_id")
        resource = _uuid(resource_id, "resource_id")
        queryset = ApiManagementResource.objects.filter(id=resource, tenant_id=tenant)
        if not include_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)
        return queryset.first()

    def query_resources(
        self,
        tenant_id: object,
        query: Mapping[str, str],
        *,
        actor_id: object,
        correlation_id: object,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
        environment: object = "production",
    ) -> QuerySet[ApiManagementResource]:
        """Apply only tenant-configured filtering, search and ordering."""

        tenant = _uuid(tenant_id, "tenant_id")
        actor = _required_text(actor_id, "actor_id")
        correlation = _required_text(correlation_id, "correlation_id")
        selected_environment = _environment(environment)
        policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
        self._ensure_feature_available(
            policy,
            tenant,
            audience_roles=audience_roles,
            audience_cohorts=audience_cohorts,
        )
        common = {"page", "page_size", "search", "ordering", *policy["filter_fields"]}
        unknown = set(query) - common
        if unknown:
            raise ValueError(f"Unsupported query parameter: {sorted(unknown)[0]}.")
        queryset = ApiManagementResource.objects.filter(tenant_id=tenant, deleted_at__isnull=True)
        if "is_active" in query:
            if "is_active" not in policy["filter_fields"]:
                raise ValueError("is_active filtering is disabled by tenant configuration.")
            value = query["is_active"].lower()
            if value not in {"true", "false"}:
                raise ValueError("is_active must be true or false.")
            queryset = queryset.filter(is_active=value == "true")
        search = query.get("search", "").strip()
        if search:
            from django.db.models import Q

            if not policy["search_fields"]:
                raise ValueError("Search is disabled by tenant configuration.")
            predicate = Q()
            for field in policy["search_fields"]:
                predicate |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(predicate)
        ordering = query.get("ordering", policy["default_ordering"])
        fields = ordering.split(",")
        if any(not field or field.lstrip("-") not in policy["ordering_fields"] for field in fields):
            raise ValueError("ordering contains a field disabled by tenant configuration.")
        return queryset.order_by(*fields, "-id")

    def resource_history(
        self,
        resource_id: object,
        tenant_id: object,
        *,
        actor_id: object,
        correlation_id: object,
        page: object = 1,
        page_size: object | None = None,
    ) -> tuple[QuerySet[ApiManagementResourceVersion], int, int, int]:
        tenant = _uuid(tenant_id, "tenant_id")
        resource_uuid = _uuid(resource_id, "resource_id")
        actor = _required_text(actor_id, "actor_id")
        correlation = _required_text(correlation_id, "correlation_id")
        environment = runtime_environment()
        policy = self._configuration_for_resource(tenant, environment, actor, correlation)
        limits = policy["validation_limits"]
        resolved_page = _bounded_int(page, "page", 1, limits["configuration_history_max_page"])
        requested_size = limits["configuration_history_page_size"] if page_size is None else page_size
        resolved_size = _bounded_int(
            requested_size,
            "page_size",
            1,
            limits["configuration_history_max_page_size"],
        )
        queryset = ApiManagementResourceVersion.objects.filter(
            tenant_id=tenant,
            resource_id=resource_uuid,
        ).order_by("-version", "-created_at", "-id")
        count = queryset.count()
        start = (resolved_page - 1) * resolved_size
        return queryset[slice(start, start + resolved_size)], count, resolved_page, resolved_size

    @transaction.atomic
    def update_resource(
        self,
        resource_id: object,
        tenant_id: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        updates: Mapping[str, Any] | None = None,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
        environment: object = "production",
        **legacy_updates: Any,
    ) -> ApiManagementResource | None:
        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        values = dict(updates or legacy_updates)
        replay = ApiManagementAuditRecord.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if replay is not None:
            if replay.action != "update" or replay.target_id != _uuid(resource_id, "resource_id"):
                raise IdempotencyConflictError("Idempotency key was already used for another mutation.")
            return self.get_resource(resource_id, tenant)
        resource = (
            ApiManagementResource.objects.select_for_update()
            .filter(id=_uuid(resource_id, "resource_id"), tenant_id=tenant, deleted_at__isnull=True)
            .first()
        )
        if resource is None:
            return None
        selected_environment = _environment(environment)
        policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
        self._ensure_feature_available(
            policy,
            tenant,
            audience_roles=audience_roles,
            audience_cohorts=audience_cohorts,
        )
        allowed = set(policy["writable_fields"])
        unknown = set(values) - allowed
        if unknown:
            raise ValueError("Request contains fields that are not writable under tenant configuration.")
        candidate_name = values.get("name", resource.name)
        candidate_description = values.get("description", resource.description)
        candidate_config = values.get("config", resource.config)
        name, description, config = self._validate_resource_values(
            policy, name=candidate_name, description=candidate_description, config=candidate_config
        )
        before = _resource_value(resource)
        resource.name = name
        resource.description = description
        resource.config = config
        resource.version += 1
        resource.save(update_fields=["name", "description", "config", "version", "updated_at"])
        _record_resource_version(
            resource,
            policy=policy,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason="update",
        )
        _record_audit(
            policy,
            tenant_id=tenant,
            target_type="resource",
            target_id=resource.id,
            action="update",
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            before_value=before,
            after_value=_resource_value(resource),
            version=resource.version,
        )
        return resource

    @transaction.atomic
    def delete_resource(
        self,
        resource_id: object,
        tenant_id: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
        environment: object = "production",
    ) -> bool:
        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        replay = ApiManagementAuditRecord.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if replay is not None:
            if replay.action != "archive" or replay.target_id != _uuid(resource_id, "resource_id"):
                raise IdempotencyConflictError("Idempotency key was already used for another mutation.")
            return True
        resource = (
            ApiManagementResource.objects.select_for_update()
            .filter(id=_uuid(resource_id, "resource_id"), tenant_id=tenant, deleted_at__isnull=True)
            .first()
        )
        if resource is None:
            return False
        selected_environment = _environment(environment)
        policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
        self._ensure_feature_available(
            policy,
            tenant,
            audience_roles=audience_roles,
            audience_cohorts=audience_cohorts,
        )
        before = _resource_value(resource)
        resource.deleted_at = timezone.now()
        resource.deleted_by = actor
        resource.version += 1
        resource.save(update_fields=["deleted_at", "deleted_by", "version", "updated_at"])
        _record_resource_version(
            resource,
            policy=policy,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason="archive",
        )
        _record_audit(
            policy,
            tenant_id=tenant,
            target_type="resource",
            target_id=resource.id,
            action="archive",
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            before_value=before,
            after_value=_resource_value(resource),
            version=resource.version,
        )
        return True

    @transaction.atomic
    def restore_resource(
        self,
        resource_id: object,
        tenant_id: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
        environment: object = "production",
    ) -> ApiManagementResource | None:
        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        replay = ApiManagementAuditRecord.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if replay is not None:
            if replay.action != "restore" or replay.target_id != _uuid(resource_id, "resource_id"):
                raise IdempotencyConflictError("Idempotency key was already used for another mutation.")
            return self.get_resource(resource_id, tenant)
        resource = (
            ApiManagementResource.objects.select_for_update()
            .filter(id=_uuid(resource_id, "resource_id"), tenant_id=tenant, deleted_at__isnull=False)
            .first()
        )
        if resource is None:
            return None
        selected_environment = _environment(environment)
        policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
        self._ensure_feature_available(
            policy,
            tenant,
            audience_roles=audience_roles,
            audience_cohorts=audience_cohorts,
        )
        before = _resource_value(resource)
        resource.deleted_at = None
        resource.deleted_by = ""
        resource.version += 1
        resource.save(update_fields=["deleted_at", "deleted_by", "version", "updated_at"])
        _record_resource_version(
            resource,
            policy=policy,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason="restore",
        )
        _record_audit(
            policy,
            tenant_id=tenant,
            target_type="resource",
            target_id=resource.id,
            action="restore",
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            before_value=before,
            after_value=_resource_value(resource),
            version=resource.version,
        )
        return resource

    def _transition_resource(
        self,
        resource_id: object,
        tenant_id: object,
        *,
        target_active: bool,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
        environment: object = "production",
    ) -> ApiManagementResource | None:
        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        action = "activate" if target_active else "deactivate"
        with transaction.atomic():
            replay = ApiManagementAuditRecord.objects.filter(tenant_id=tenant, idempotency_key=key).first()
            if replay is not None:
                if replay.action != action or replay.target_id != _uuid(resource_id, "resource_id"):
                    raise IdempotencyConflictError("Idempotency key was already used for another mutation.")
                return self.get_resource(resource_id, tenant)
            resource = (
                ApiManagementResource.objects.select_for_update()
                .filter(id=_uuid(resource_id, "resource_id"), tenant_id=tenant, deleted_at__isnull=True)
                .first()
            )
            if resource is None:
                return None
            selected_environment = _environment(environment)
            policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
            self._ensure_feature_available(
                policy,
                tenant,
                audience_roles=audience_roles,
                audience_cohorts=audience_cohorts,
            )
            enabled_field = "activation_enabled" if target_active else "deactivation_enabled"
            if not policy[enabled_field]:
                raise PermissionError(f"{action} is disabled by tenant configuration.")
            before = _resource_value(resource)
            if resource.is_active != target_active:
                resource.is_active = target_active
                resource.version += 1
                resource.save(update_fields=["is_active", "version", "updated_at"])
                _record_resource_version(
                    resource,
                    policy=policy,
                    actor_id=actor,
                    correlation_id=correlation,
                    idempotency_key=key,
                    reason=action,
                )
            _record_audit(
                policy,
                tenant_id=tenant,
                target_type="resource",
                target_id=resource.id,
                action=action,
                actor_id=actor,
                correlation_id=correlation,
                idempotency_key=key,
                before_value=before,
                after_value=_resource_value(resource),
                version=resource.version,
            )
            return resource

    @transaction.atomic
    def rollback_resource(
        self,
        resource_id: object,
        tenant_id: object,
        version: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
        environment: object = "production",
        audience_roles: Sequence[str] = (),
        audience_cohorts: Sequence[str] = (),
    ) -> ApiManagementResource | None:
        """Restore a prior immutable resource snapshot as a new version."""

        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        resource_uuid = _uuid(resource_id, "resource_id")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer.")
        replay_version = ApiManagementResourceVersion.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if replay_version is not None:
            if (
                replay_version.reason != "rollback"
                or replay_version.resource_id != resource_uuid
                or replay_version.source_version != version
            ):
                raise IdempotencyConflictError("Idempotency key was already used for another mutation.")
            current = self.get_resource(resource_uuid, tenant, include_deleted=True)
            if current is None or current.version != replay_version.version:
                raise IdempotencyConflictError("The original resource rollback response is no longer current.")
            return current
        replay_audit = ApiManagementAuditRecord.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if replay_audit is not None:
            raise IdempotencyConflictError("Idempotency key was already used for another mutation.")
        snapshot = ApiManagementResourceVersion.objects.filter(
            tenant_id=tenant, resource_id=resource_uuid, version=version
        ).first()
        if snapshot is None:
            raise LookupError("Resource version was not found.")
        resource = ApiManagementResource.objects.select_for_update().filter(tenant_id=tenant, id=resource_uuid).first()
        if resource is None:
            return None
        selected_environment = _environment(environment)
        policy = self._configuration_for_resource(tenant, selected_environment, actor, correlation)
        self._ensure_feature_available(
            policy,
            tenant,
            audience_roles=audience_roles,
            audience_cohorts=audience_cohorts,
        )
        before = _resource_value(resource)
        state = snapshot.snapshot
        required_snapshot_fields = {
            "name",
            "description",
            "config",
            "is_active",
            "deleted_at",
            "deleted_by",
        }
        if not isinstance(state, Mapping) or not required_snapshot_fields.issubset(state):
            raise RuntimeError("Immutable resource version is structurally invalid.")
        snapshot_name = state["name"]
        snapshot_description = state["description"]
        snapshot_config = state["config"]
        snapshot_active = state["is_active"]
        snapshot_deleted_by = state["deleted_by"]
        if (
            not isinstance(snapshot_name, str)
            or not snapshot_name.strip()
            or len(snapshot_name) > PLATFORM_HARD_CEILINGS["resource_name_length"]
            or not isinstance(snapshot_description, str)
            or len(snapshot_description) > PLATFORM_HARD_CEILINGS["resource_description_length"]
            or not isinstance(snapshot_config, dict)
            or not isinstance(snapshot_active, bool)
            or not isinstance(snapshot_deleted_by, str)
            or len(snapshot_deleted_by) > PLATFORM_HARD_CEILINGS["evidence_identity_length"]
        ):
            raise RuntimeError("Immutable resource version violates platform storage constraints.")
        deleted_at = state.get("deleted_at")
        parsed_deleted_at = parse_datetime(deleted_at) if isinstance(deleted_at, str) else None
        if deleted_at is not None and parsed_deleted_at is None:
            raise RuntimeError("Immutable resource version contains an invalid deletion timestamp.")
        resource.name = snapshot_name
        resource.description = snapshot_description
        resource.config = copy.deepcopy(snapshot_config)
        resource.is_active = snapshot_active
        resource.deleted_at = parsed_deleted_at
        resource.deleted_by = snapshot_deleted_by
        resource.version += 1
        resource.save(
            update_fields=[
                "name",
                "description",
                "config",
                "is_active",
                "deleted_at",
                "deleted_by",
                "version",
                "updated_at",
            ]
        )
        _record_resource_version(
            resource,
            policy=policy,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason="rollback",
            source_version=version,
        )
        _record_audit(
            policy,
            tenant_id=tenant,
            target_type="resource",
            target_id=resource.id,
            action="rollback",
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            before_value=before,
            after_value=_resource_value(resource),
            version=resource.version,
        )
        return resource

    def activate_resource(self, resource_id: object, tenant_id: object, **context: Any) -> ApiManagementResource | None:
        return self._transition_resource(resource_id, tenant_id, target_active=True, **context)

    def deactivate_resource(
        self, resource_id: object, tenant_id: object, **context: Any
    ) -> ApiManagementResource | None:
        return self._transition_resource(resource_id, tenant_id, target_active=False, **context)


__all__ = [
    "ApiManagementService",
    "CONFIGURATION_KEYS",
    "ConfigurationValidationError",
    "DEFAULT_CONFIGURATION",
    "IdempotencyConflictError",
    "validate_configuration_document",
]
