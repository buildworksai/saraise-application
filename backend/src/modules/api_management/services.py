"""Transactional business rules for tenant API-management state."""

from __future__ import annotations

import copy
import logging
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from .models import (
    ApiManagementAuditRecord,
    ApiManagementConfiguration,
    ApiManagementConfigurationVersion,
    ApiManagementResource,
)

logger = logging.getLogger(__name__)

# Bootstrap values are copied once into tenant-owned, versioned configuration.
# Every runtime decision below reads the persisted document instead of these
# constants. The upper bounds in validation are non-configurable safety caps.
DEFAULT_CONFIGURATION: dict[str, Any] = {
    "environment": "production",
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
}

CONFIGURATION_KEYS = frozenset(DEFAULT_CONFIGURATION)
WRITABLE_RESOURCE_FIELDS = frozenset({"name", "description", "config"})
FILTER_FIELD_ALLOWLIST = frozenset({"is_active"})
SEARCH_FIELD_ALLOWLIST = frozenset({"name", "description"})
ORDERING_FIELD_ALLOWLIST = frozenset({"name", "created_at", "updated_at"})


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
    if len(normalized) > 255:
        raise ValueError(f"{field} exceeds its safe storage limit.")
    return normalized


def _string_list(
    value: object,
    field: str,
    *,
    allowed: frozenset[str] | None = None,
    maximum_items: int = 64,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ConfigurationValidationError({field: f"Must be a list with at most {maximum_items} items."})
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 128:
            raise ConfigurationValidationError(
                {field: "Each value must be a non-blank string of at most 128 characters."}
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


def validate_configuration_document(document: object) -> dict[str, Any]:
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
    if normalized["environment"] not in {"development", "staging", "production"}:
        raise ConfigurationValidationError({"environment": "Must be development, staging, or production."})
    minimum = _bounded_int(normalized["resource_name_min_length"], "resource_name_min_length", 1, 128)
    maximum = _bounded_int(normalized["resource_name_max_length"], "resource_name_max_length", 1, 255)
    if minimum > maximum:
        raise ConfigurationValidationError({"resource_name_min_length": "Cannot exceed resource_name_max_length."})
    description = normalized["resource_description_default"]
    if not isinstance(description, str) or len(description) > 4000:
        raise ConfigurationValidationError(
            {"resource_description_default": "Must be a string of at most 4000 characters."}
        )
    allowed_keys = _string_list(normalized["allowed_resource_config_keys"], "allowed_resource_config_keys")
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
        normalized["writable_fields"], "writable_fields", allowed=WRITABLE_RESOURCE_FIELDS
    )
    normalized["filter_fields"] = _string_list(
        normalized["filter_fields"], "filter_fields", allowed=FILTER_FIELD_ALLOWLIST
    )
    normalized["search_fields"] = _string_list(
        normalized["search_fields"], "search_fields", allowed=SEARCH_FIELD_ALLOWLIST
    )
    normalized["ordering_fields"] = _string_list(
        normalized["ordering_fields"], "ordering_fields", allowed=ORDERING_FIELD_ALLOWLIST
    )
    default_ordering = normalized["default_ordering"]
    if not isinstance(default_ordering, str) or default_ordering.lstrip("-") not in normalized["ordering_fields"]:
        raise ConfigurationValidationError(
            {"default_ordering": "Must select an enabled ordering field, optionally prefixed with '-'."}
        )
    page_size = _bounded_int(normalized["page_size"], "page_size", 1, 100)
    max_page_size = _bounded_int(normalized["max_page_size"], "max_page_size", 1, 100)
    if page_size > max_page_size:
        raise ConfigurationValidationError({"page_size": "Cannot exceed max_page_size."})
    confirmation = normalized["deletion_confirmation_message"]
    if not isinstance(confirmation, str) or not confirmation.strip() or len(confirmation) > 512:
        raise ConfigurationValidationError(
            {"deletion_confirmation_message": "Must be a non-blank string of at most 512 characters."}
        )
    normalized["deletion_confirmation_message"] = confirmation.strip()
    _bounded_int(normalized["health_cache_ttl_seconds"], "health_cache_ttl_seconds", 1, 300)
    _bounded_int(normalized["table_skeleton_rows"], "table_skeleton_rows", 1, 20)
    _bounded_int(normalized["form_description_rows"], "form_description_rows", 2, 20)
    rollout = _bounded_int(normalized["rollout_percentage"], "rollout_percentage", 0, 100)
    if not normalized["feature_enabled"] and rollout != 0:
        raise ConfigurationValidationError({"rollout_percentage": "Must be zero while feature_enabled is false."})
    if not normalized["feature_enabled"] and (normalized["activation_enabled"] or normalized["deactivation_enabled"]):
        raise ConfigurationValidationError(
            {"activation_enabled": "Lifecycle transitions must be disabled while the feature is disabled."}
        )
    normalized["rollout_roles"] = _string_list(normalized["rollout_roles"], "rollout_roles")
    normalized["rollout_cohorts"] = _string_list(normalized["rollout_cohorts"], "rollout_cohorts")
    if rollout == 100 and (normalized["rollout_roles"] or normalized["rollout_cohorts"]):
        raise ConfigurationValidationError(
            {"rollout_roles": "Role and cohort targeting must be empty for a 100 percent rollout."}
        )
    normalized["allowed_resource_config_keys"] = allowed_keys
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
    }


class ApiManagementService:
    """Tenant-scoped, audited and idempotent module operations."""

    @staticmethod
    def default_configuration() -> dict[str, Any]:
        return copy.deepcopy(DEFAULT_CONFIGURATION)

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
        actor_id: str,
        correlation_id: str,
    ) -> ApiManagementConfiguration:
        configuration = ApiManagementConfiguration.objects.filter(tenant_id=tenant_id).first()
        if configuration is not None:
            return configuration
        document = validate_configuration_document(DEFAULT_CONFIGURATION)
        bootstrap_key = uuid.uuid4()
        try:
            configuration = ApiManagementConfiguration.objects.create(
                tenant_id=tenant_id,
                document=document,
                version=1,
                updated_by=actor_id,
            )
            ApiManagementConfigurationVersion.objects.create(
                tenant_id=tenant_id,
                version=1,
                document=document,
                actor_id=actor_id,
                correlation_id=correlation_id,
                idempotency_key=bootstrap_key,
                reason="bootstrap",
            )
            ApiManagementAuditRecord.objects.create(
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
            existing = ApiManagementConfiguration.objects.filter(tenant_id=tenant_id).first()
            if existing is None:
                raise
            return existing

    @transaction.atomic
    def get_configuration(
        self,
        tenant_id: object,
        *,
        actor_id: object,
        correlation_id: object,
    ) -> ApiManagementConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _required_text(actor_id, "actor_id")
        correlation = _required_text(correlation_id, "correlation_id")
        return self._bootstrap_configuration(tenant, actor, correlation)

    def preview_configuration(self, tenant_id: object, document: object) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        normalized = validate_configuration_document(document)
        current = ApiManagementConfiguration.objects.filter(tenant_id=tenant).first()
        before = current.document if current else DEFAULT_CONFIGURATION
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
        reason: str = "update",
    ) -> ApiManagementConfiguration:
        tenant, actor, correlation, key = self._context(tenant_id, actor_id, correlation_id, idempotency_key)
        normalized = validate_configuration_document(document)
        replay = ApiManagementConfigurationVersion.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if replay is not None:
            if replay.document != normalized or replay.reason != reason:
                raise IdempotencyConflictError("Idempotency key was already used for another configuration mutation.")
            current = ApiManagementConfiguration.objects.get(tenant_id=tenant)
            if current.version != replay.version:
                raise IdempotencyConflictError("The original configuration response is no longer current.")
            return current

        configuration = self._bootstrap_configuration(tenant, actor, correlation)
        configuration = ApiManagementConfiguration.objects.select_for_update().get(pk=configuration.pk)
        before = copy.deepcopy(configuration.document)
        next_version = configuration.version + 1
        configuration.document = normalized
        configuration.version = next_version
        configuration.updated_by = actor
        configuration.save(update_fields=["document", "version", "updated_by", "updated_at"])
        ApiManagementConfigurationVersion.objects.create(
            tenant_id=tenant,
            version=next_version,
            document=normalized,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            reason=reason,
        )
        ApiManagementAuditRecord.objects.create(
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

    def configuration_history(self, tenant_id: object) -> QuerySet[ApiManagementConfigurationVersion]:
        tenant = _uuid(tenant_id, "tenant_id")
        return ApiManagementConfigurationVersion.objects.filter(tenant_id=tenant).order_by("-version")

    def rollback_configuration(
        self,
        tenant_id: object,
        version: object,
        *,
        actor_id: object,
        correlation_id: object,
        idempotency_key: object,
    ) -> ApiManagementConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("version must be a positive integer.")
        snapshot = ApiManagementConfigurationVersion.objects.filter(tenant_id=tenant, version=version).first()
        if snapshot is None:
            raise LookupError("Configuration version was not found.")
        return self.update_configuration(
            tenant,
            snapshot.document,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            reason="rollback",
        )

    def export_configuration(
        self,
        tenant_id: object,
        *,
        actor_id: object,
        correlation_id: object,
    ) -> dict[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        configuration = self.get_configuration(
            tenant,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )
        return {
            "module": "api_management",
            "schema_version": 1,
            "version": configuration.version,
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
    ) -> ApiManagementConfiguration:
        if not isinstance(portable_document, Mapping):
            raise ConfigurationValidationError({"document": "Import must be an object."})
        if "document" in portable_document:
            if portable_document.get("module") not in (None, "api_management"):
                raise ConfigurationValidationError({"module": "Import belongs to another module."})
            document = portable_document["document"]
        else:
            document = portable_document
        return self.update_configuration(
            tenant_id,
            document,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            reason="import",
        )

    def _configuration_for_resource(
        self,
        tenant_id: uuid.UUID,
        actor_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        configuration = self._bootstrap_configuration(tenant_id, actor_id, correlation_id)
        return validate_configuration_document(configuration.document)

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
        percentage_enabled = tenant_id.int % 100 < policy["rollout_percentage"]
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
    ) -> ApiManagementResource:
        actor_value = actor_id if actor_id is not None else created_by
        tenant, actor, correlation, key = self._context(tenant_id, actor_value, correlation_id, idempotency_key)
        policy = self._configuration_for_resource(tenant, actor, correlation)
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
        ApiManagementAuditRecord.objects.create(
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
    ) -> QuerySet[ApiManagementResource]:
        """Apply only tenant-configured filtering, search and ordering."""

        tenant = _uuid(tenant_id, "tenant_id")
        actor = _required_text(actor_id, "actor_id")
        correlation = _required_text(correlation_id, "correlation_id")
        policy = self._configuration_for_resource(tenant, actor, correlation)
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
        policy = self._configuration_for_resource(tenant, actor, correlation)
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
        ApiManagementAuditRecord.objects.create(
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
        policy = self._configuration_for_resource(tenant, actor, correlation)
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
        ApiManagementAuditRecord.objects.create(
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
        policy = self._configuration_for_resource(tenant, actor, correlation)
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
        ApiManagementAuditRecord.objects.create(
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
            policy = self._configuration_for_resource(tenant, actor, correlation)
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
            ApiManagementAuditRecord.objects.create(
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
