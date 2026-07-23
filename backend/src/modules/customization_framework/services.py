"""Tenant-safe customization domain services and paid-module extension contract.

The module deliberately evaluates a small declarative language.  Tenant input
never reaches Python evaluation, imports, SQL, the filesystem, or the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import wraps
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models import Max, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from src.core.api import CapabilityUnavailable
from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id
from src.core.observability.correlation import correlation_id_var
from src.core.state_machine import (
    IdempotencyConflictError,
    StateMachine,
    Transition,
)
from src.core.state_machine import registry as state_machine_registry

from .models import (
    BusinessRule,
    BusinessRuleVersion,
    ConfigurationAuditRecord,
    CustomFieldDefinition,
    CustomFieldDefinitionVersion,
    CustomFieldValue,
    FormDefinition,
    FormLayoutVersion,
    IdempotentCommand,
    LifecycleTransitionRecord,
    PublicationRecord,
    RuleExecution,
    RuntimeConfiguration,
    RuntimeConfigurationVersion,
)

logger = logging.getLogger("saraise.customization_framework")

PLATFORM_CEILINGS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "json_bytes": 1024 * 1024,
        "ast_nodes": 4096,
        "ast_depth": 64,
        "evaluation_ms": 1000,
        "field_key_length": 100,
        "field_label_length": 160,
        "resource_key_length": 120,
        "contract_version_length": 32,
        "form_key_length": 100,
        "form_name_length": 160,
        "change_summary_length": 500,
        "idempotency_key_length": 128,
        "rule_priority_max": 1000,
        "page_size": 100,
    }
)
PLATFORM_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$")
PLATFORM_FIELD_TYPES: Final[frozenset[str]] = frozenset(
    {"text", "long_text", "integer", "decimal", "boolean", "date", "datetime", "uuid", "choice", "multi_choice", "json"}
)
PLATFORM_RULE_TRIGGERS: Final[frozenset[str]] = frozenset({"validate", "before_create", "before_update", "form_change"})
PLATFORM_CONDITION_OPERATORS: Final[frozenset[str]] = frozenset(
    {
        "and",
        "or",
        "not",
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "contains",
        "starts_with",
        "ends_with",
        "is_null",
        "not_null",
        "changed",
    }
)
PLATFORM_ACTION_TYPES: Final[frozenset[str]] = frozenset(
    {"reject-with-message", "set-derived-value", "set-required", "set-visible", "set-enabled", "emit-field-diagnostic"}
)


def default_configuration_document() -> dict[str, object]:
    """Return the complete, safe tenant configuration seed.

    Defaults are centralized here so runtime code never embeds business
    thresholds or workflow policy. Platform ceilings above remain
    non-configurable security boundaries.
    """

    return {
        "limits": {
            "json_bytes": 64 * 1024,
            "ast_nodes": 256,
            "ast_depth": 16,
            "evaluation_ms": 50,
            "field_key_length": 100,
            "field_label_length": 160,
            "resource_key_length": 120,
            "contract_version_length": 32,
            "form_key_length": 100,
            "form_name_length": 160,
            "change_summary_length": 500,
            "idempotency_key_length": 128,
            "rule_priority_min": 1,
            "rule_priority_max": 1000,
        },
        "policies": {
            "slug_pattern": r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$",
            "field_types": sorted(PLATFORM_FIELD_TYPES),
            "rule_triggers": sorted(PLATFORM_RULE_TRIGGERS),
            "condition_operators": sorted(PLATFORM_CONDITION_OPERATORS),
            "action_types": sorted(PLATFORM_ACTION_TYPES),
            "value_sources": ["ui", "api", "import"],
            "value_allowed_statuses": ["active", "deprecated"],
            "field_delete_statuses": ["draft", "retired"],
            "form_delete_statuses": ["draft", "archived"],
            "field_transitions": {
                "draft": {"activate": "active"},
                "active": {"deprecate": "deprecated"},
                "deprecated": {"retire": "retired"},
            },
            "form_transitions": {
                "draft": {"publish": "published", "archive": "archived"},
                "published": {"publish_revision": "published", "archive": "archived"},
            },
            "rule_transitions": {
                "draft": {"publish": "published", "retire": "retired"},
                "published": {"publish_revision": "published", "pause": "paused", "retire": "retired"},
                "paused": {"resume": "published", "retire": "retired"},
            },
        },
        "defaults": {
            "field_required": False,
            "field_searchable": False,
            "field_status": "draft",
            "form_status": "draft",
            "layout_schema_version": 1,
            "layout_status": "candidate",
            "form_surface": "default",
            "form_layout": {"schema_version": 1, "sections": []},
            "rule_priority": 100,
            "rule_stop_on_match": False,
            "rule_status": "draft",
            "rule_language_version": 1,
            "rule_version_status": "candidate",
            "contract_version": "1.0",
        },
        "list_preferences": {
            "page_size": 25,
            "field_ordering": "key",
            "form_ordering": "key",
            "rule_ordering": "priority",
            "execution_ordering": "-executed_at",
        },
        "navigation": {
            "fields_order": 70,
            "field_values_order": 71,
            "forms_order": 72,
            "rules_order": 73,
            "executions_order": 74,
            "configuration_order": 75,
        },
        "rollout": {"enabled": True, "roles": [], "cohorts": []},
        "rbac": {"action_access": {}, "sod_actions": []},
    }


class CustomizationError(RuntimeError):
    """Base error that contains no sensitive payload."""


class CustomizationValidationError(CustomizationError):
    """A declarative document or domain command is invalid."""

    def __init__(self, message: str, *, detail: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.detail = dict(detail or {})


class CustomizationNotFound(CustomizationError):
    """A tenant-scoped object is not visible to the caller."""


class OptimisticLockConflict(CustomizationError):
    """The aggregate changed after the caller read it."""


class EvaluationIdempotencyConflict(CustomizationError):
    """An evaluation key was reused for different input."""


def _configuration_section(document: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = document.get(name)
    if not isinstance(value, Mapping):
        raise CustomizationValidationError(f"configuration.{name} must be an object")
    return value


def _positive_config_int(
    values: Mapping[str, object],
    name: str,
    *,
    minimum: int = 1,
    maximum: int,
) -> int:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise CustomizationValidationError(
            f"configuration.{name} must be between {minimum} and {maximum}",
            detail={name: [f"Must be an integer between {minimum} and {maximum}."]},
        )
    return value


def validate_configuration_document(document: object) -> dict[str, object]:
    """Validate and normalize the complete tenant document server-side."""

    if not isinstance(document, Mapping):
        raise CustomizationValidationError("configuration document must be an object")
    required_sections = {
        "limits",
        "policies",
        "defaults",
        "list_preferences",
        "navigation",
        "rollout",
        "rbac",
    }
    if set(document) != required_sections:
        missing = sorted(required_sections - set(document))
        unknown = sorted(set(document) - required_sections)
        raise CustomizationValidationError(
            "configuration document has an invalid section inventory",
            detail={"missing_sections": missing, "unknown_sections": unknown},
        )

    normalized = deepcopy(dict(document))
    limits = _configuration_section(normalized, "limits")
    required_limits = set(PLATFORM_CEILINGS) - {"page_size"}
    required_limits.add("rule_priority_min")
    if set(limits) != required_limits:
        raise CustomizationValidationError("configuration.limits must contain every governed limit")
    for key, ceiling in PLATFORM_CEILINGS.items():
        if key != "page_size":
            _positive_config_int(limits, key, maximum=ceiling)
    priority_min = _positive_config_int(
        limits,
        "rule_priority_min",
        maximum=int(limits["rule_priority_max"]),
    )
    if priority_min > int(limits["rule_priority_max"]):
        raise CustomizationValidationError("rule_priority_min cannot exceed rule_priority_max")

    policies = _configuration_section(normalized, "policies")
    required_policies = {
        "slug_pattern",
        "field_types",
        "rule_triggers",
        "condition_operators",
        "action_types",
        "value_sources",
        "value_allowed_statuses",
        "field_delete_statuses",
        "form_delete_statuses",
        "field_transitions",
        "form_transitions",
        "rule_transitions",
    }
    if set(policies) != required_policies:
        raise CustomizationValidationError("configuration.policies must contain every governed policy")
    slug_pattern = policies["slug_pattern"]
    if slug_pattern not in {
        r"^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$",
        r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
    }:
        raise CustomizationValidationError("slug_pattern is not in the platform safe allow-list")

    def validate_allowlist(name: str, platform: set[str] | frozenset[str]) -> list[str]:
        raw = policies[name]
        if not isinstance(raw, list) or not raw or any(not isinstance(item, str) for item in raw):
            raise CustomizationValidationError(f"configuration.policies.{name} must be a non-empty string array")
        values = list(dict.fromkeys(raw))
        if not set(values).issubset(platform):
            raise CustomizationValidationError(f"configuration.policies.{name} contains unsupported values")
        normalized["policies"][name] = values  # type: ignore[index]
        return values

    validate_allowlist("field_types", PLATFORM_FIELD_TYPES)
    validate_allowlist("rule_triggers", PLATFORM_RULE_TRIGGERS)
    validate_allowlist("condition_operators", PLATFORM_CONDITION_OPERATORS)
    validate_allowlist("action_types", PLATFORM_ACTION_TYPES)
    validate_allowlist("value_sources", {"ui", "api", "import"})
    validate_allowlist("value_allowed_statuses", {"active", "deprecated"})
    validate_allowlist("field_delete_statuses", {"draft", "retired"})
    validate_allowlist("form_delete_statuses", {"draft", "archived"})

    for name, statuses in (
        ("field_transitions", {"draft", "active", "deprecated", "retired"}),
        ("form_transitions", {"draft", "published", "archived"}),
        ("rule_transitions", {"draft", "published", "paused", "retired"}),
    ):
        transitions = policies[name]
        if not isinstance(transitions, Mapping):
            raise CustomizationValidationError(f"configuration.policies.{name} must be an object")
        for source, commands in transitions.items():
            if source not in statuses or not isinstance(commands, Mapping):
                raise CustomizationValidationError(f"configuration.policies.{name} contains an invalid source")
            if any(not isinstance(command, str) or target not in statuses for command, target in commands.items()):
                raise CustomizationValidationError(f"configuration.policies.{name} contains an invalid transition")

    defaults = _configuration_section(normalized, "defaults")
    required_defaults = {
        "field_required",
        "field_searchable",
        "field_status",
        "form_status",
        "layout_schema_version",
        "layout_status",
        "form_surface",
        "form_layout",
        "rule_priority",
        "rule_stop_on_match",
        "rule_status",
        "rule_language_version",
        "rule_version_status",
        "contract_version",
    }
    if set(defaults) != required_defaults:
        raise CustomizationValidationError("configuration.defaults must contain every governed default")
    for boolean_name in ("field_required", "field_searchable", "rule_stop_on_match"):
        if not isinstance(defaults[boolean_name], bool):
            raise CustomizationValidationError(f"configuration.defaults.{boolean_name} must be boolean")
    if defaults["field_status"] not in {"draft"} or defaults["form_status"] not in {"draft"}:
        raise CustomizationValidationError("new aggregate status defaults must remain fail-closed drafts")
    if defaults["layout_status"] not in {"candidate"} or defaults["rule_version_status"] not in {"candidate"}:
        raise CustomizationValidationError("new version status defaults must remain candidates")
    if defaults["rule_status"] not in {"draft"}:
        raise CustomizationValidationError("new rule status must remain draft")
    if not isinstance(defaults["form_surface"], str) or not defaults["form_surface"]:
        raise CustomizationValidationError("configuration.defaults.form_surface must be non-empty")
    if not isinstance(defaults["contract_version"], str) or not defaults["contract_version"]:
        raise CustomizationValidationError("configuration.defaults.contract_version must be non-empty")
    _positive_config_int(
        defaults,
        "layout_schema_version",
        maximum=65535,
    )
    _positive_config_int(defaults, "rule_language_version", maximum=65535)
    _positive_config_int(
        defaults,
        "rule_priority",
        minimum=int(limits["rule_priority_min"]),
        maximum=int(limits["rule_priority_max"]),
    )
    form_layout = defaults["form_layout"]
    if (
        not isinstance(form_layout, Mapping)
        or form_layout.get("schema_version") != defaults["layout_schema_version"]
        or not isinstance(form_layout.get("sections"), list)
    ):
        raise CustomizationValidationError("configuration.defaults.form_layout is invalid")

    list_preferences = _configuration_section(normalized, "list_preferences")
    if set(list_preferences) != {
        "page_size",
        "field_ordering",
        "form_ordering",
        "rule_ordering",
        "execution_ordering",
    }:
        raise CustomizationValidationError("configuration.list_preferences has an invalid inventory")
    _positive_config_int(list_preferences, "page_size", maximum=PLATFORM_CEILINGS["page_size"])
    ordering_allowlists = {
        "field_ordering": {"key", "-key", "label", "-label", "status", "-status", "updated_at", "-updated_at"},
        "form_ordering": {"key", "-key", "name", "-name", "status", "-status", "updated_at", "-updated_at"},
        "rule_ordering": {"priority", "-priority", "key", "-key", "status", "-status", "updated_at", "-updated_at"},
        "execution_ordering": {"executed_at", "-executed_at", "duration_ms", "-duration_ms", "status", "-status"},
    }
    for key, choices in ordering_allowlists.items():
        if list_preferences[key] not in choices:
            raise CustomizationValidationError(f"configuration.list_preferences.{key} is unsupported")

    navigation = _configuration_section(normalized, "navigation")
    if set(navigation) != {
        "fields_order",
        "field_values_order",
        "forms_order",
        "rules_order",
        "executions_order",
        "configuration_order",
    }:
        raise CustomizationValidationError("configuration.navigation has an invalid inventory")
    nav_values = [_positive_config_int(navigation, key, minimum=0, maximum=10000) for key in navigation]
    if len(nav_values) != len(set(nav_values)):
        raise CustomizationValidationError("configuration.navigation orders must be unique")

    rollout = _configuration_section(normalized, "rollout")
    if set(rollout) != {"enabled", "roles", "cohorts"} or not isinstance(rollout["enabled"], bool):
        raise CustomizationValidationError("configuration.rollout has an invalid inventory")
    for key in ("roles", "cohorts"):
        if not isinstance(rollout[key], list) or any(not isinstance(item, str) or not item for item in rollout[key]):
            raise CustomizationValidationError(f"configuration.rollout.{key} must be a string array")

    rbac = _configuration_section(normalized, "rbac")
    if set(rbac) != {"action_access", "sod_actions"}:
        raise CustomizationValidationError("configuration.rbac has an invalid inventory")
    if not isinstance(rbac["action_access"], Mapping) or not isinstance(rbac["sod_actions"], list):
        raise CustomizationValidationError("configuration.rbac must contain action_access and sod_actions")
    if len(_canonical(normalized).encode("utf-8")) > PLATFORM_CEILINGS["json_bytes"]:
        raise CustomizationValidationError("configuration document exceeds the platform ceiling")
    return normalized


def effective_configuration(tenant_id: UUID) -> dict[str, object]:
    """Return validated tenant configuration, falling back to the safe seed.

    The seed enforces every check and therefore never turns missing
    configuration into an authorization or validation bypass.
    """

    tenant = _uuid(tenant_id, "tenant_id")
    current = RuntimeConfiguration.objects.filter(tenant_id=tenant).first()
    document = current.document if current is not None else default_configuration_document()
    return validate_configuration_document(document)


class CustomizationConfigurationService:
    """Versioned tenant configuration with immutable evidence and rollback."""

    def get(self, tenant_id: UUID) -> RuntimeConfiguration | None:
        return RuntimeConfiguration.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).first()

    def preview(self, tenant_id: UUID, *, document: object) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        candidate = validate_configuration_document(document)
        before = effective_configuration(tenant)
        changes = {
            key: {"before": before[key], "after": candidate[key]} for key in candidate if before[key] != candidate[key]
        }
        return {"valid": True, "document": candidate, "changes": changes, "requires_restart": False}

    def export_document(self, tenant_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        current = self.get(tenant)
        return {
            "schema": "saraise.customization-framework.configuration/v1",
            "tenant_id": str(tenant),
            "version": current.version if current is not None else 0,
            "environment": current.environment if current is not None else "default",
            "document": effective_configuration(tenant),
        }

    def list_versions(self, tenant_id: UUID) -> QuerySet[RuntimeConfigurationVersion]:
        return RuntimeConfigurationVersion.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).order_by("-version")

    def list_audit(self, tenant_id: UUID) -> QuerySet[ConfigurationAuditRecord]:
        return ConfigurationAuditRecord.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).order_by("-created_at")

    def update(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        expected_version: int,
        document: object,
        environment: str = "default",
        action: str = "update",
    ) -> RuntimeConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        correlation = _uuid(correlation_id, "correlation_id")
        key = _required_text(
            idempotency_key,
            "idempotency_key",
            maximum=int(effective_configuration(tenant)["limits"]["idempotency_key_length"]),  # type: ignore[index]
        )
        storage_key = hashlib.sha256(f"runtime_configuration:{key}".encode("utf-8")).hexdigest()
        candidate = validate_configuration_document(document)
        fingerprint = _hash(action, expected_version, environment, candidate)
        with transaction.atomic():
            replay = (
                IdempotentCommand.objects.select_for_update()
                .filter(
                    tenant_id=tenant,
                    command_type="runtime_configuration",
                    idempotency_key=storage_key,
                )
                .first()
            )
            if replay is not None:
                if replay.request_fingerprint != fingerprint:
                    raise EvaluationIdempotencyConflict("idempotency key was already used for another command")
                existing = RuntimeConfiguration.objects.filter(
                    tenant_id=tenant,
                    id=replay.resource_id,
                ).first()
                if existing is None:
                    raise CustomizationError("idempotent command evidence references a missing result")
                return existing

            current = RuntimeConfiguration.objects.select_for_update().filter(tenant_id=tenant).first()
            current_version = current.version if current is not None else 0
            if expected_version != current_version:
                raise OptimisticLockConflict("configuration changed; reload before retrying")
            before = effective_configuration(tenant)
            new_version = current_version + 1
            if current is None:
                current = RuntimeConfiguration.objects.create(
                    tenant_id=tenant,
                    document=candidate,
                    version=new_version,
                    environment=environment,
                    updated_by=actor,
                )
            else:
                current.document = candidate
                current.version = new_version
                current.environment = environment
                current.updated_by = actor
                current.save(update_fields=["document", "version", "environment", "updated_by", "updated_at"])
            RuntimeConfigurationVersion.objects.create(
                tenant_id=tenant,
                configuration=current,
                version=new_version,
                environment=environment,
                document=candidate,
                actor_id=actor,
                correlation_id=correlation,
            )
            ConfigurationAuditRecord.objects.create(
                tenant_id=tenant,
                configuration=current,
                action=action,
                version=new_version,
                before=before,
                after=candidate,
                actor_id=actor,
                correlation_id=correlation,
            )
            IdempotentCommand.objects.create(
                tenant_id=tenant,
                command_type="runtime_configuration",
                idempotency_key=storage_key,
                request_fingerprint=fingerprint,
                response_payload={"configuration_id": str(current.id), "version": new_version},
                response_status=200,
                resource_type="runtime_configuration",
                resource_id=current.id,
                actor_id=actor,
                correlation_id=correlation,
            )
        return current

    def import_document(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        expected_version: int,
        payload: object,
    ) -> RuntimeConfiguration:
        if not isinstance(payload, Mapping) or payload.get("schema") != (
            "saraise.customization-framework.configuration/v1"
        ):
            raise CustomizationValidationError("unsupported configuration import schema")
        if str(payload.get("tenant_id")) != str(_uuid(tenant_id, "tenant_id")):
            raise CustomizationValidationError("configuration import belongs to another tenant")
        return self.update(
            tenant_id,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            document=payload.get("document"),
            environment=str(payload.get("environment", "default")),
            action="import",
        )

    def rollback(
        self,
        tenant_id: UUID,
        *,
        actor_id: UUID,
        correlation_id: UUID,
        idempotency_key: str,
        expected_version: int,
        target_version: int,
    ) -> RuntimeConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        target = RuntimeConfigurationVersion.objects.filter(
            tenant_id=tenant,
            version=target_version,
        ).first()
        if target is None:
            raise CustomizationNotFound("configuration version not found")
        return self.update(
            tenant,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            document=target.document,
            environment=target.environment,
            action=f"rollback:{target_version}",
        )


@dataclass(frozen=True, slots=True)
class ResourceContract:
    """Versioned, immutable contract registered by a free or paid module."""

    module: str
    resource: str
    version: str
    fields: Mapping[str, Mapping[str, object]]
    custom_field_types: frozenset[str]
    form_surfaces: frozenset[str]
    rule_triggers: frozenset[str]
    entitlement_keys: frozenset[str]
    capabilities: Mapping[str, object]
    available: bool = True
    discovery: Mapping[str, object] | None = None


class CustomizationRegistry:
    """Stable process registry consumed by free and paid modules.

    Registration is explicit and collision-safe.  Unregistering marks a
    contract unavailable rather than deleting its identity, so stored
    customization records remain interpretable.
    """

    _contracts: dict[tuple[str, str, str], ResourceContract] = {}
    _lock = threading.RLock()

    @classmethod
    def _load_durable_contracts(cls) -> None:
        """Load signed/registered module metadata from durable registry rows."""

        try:
            from src.core.module_registry_models import ModuleRegistryEntry

            entries = ModuleRegistryEntry.objects.filter(is_active=True).only("name", "version", "metadata")
            declarations: list[Mapping[str, object]] = []
            for entry in entries:
                raw = (entry.metadata or {}).get("customization_resource_contracts", [])
                if not isinstance(raw, list):
                    raise CustomizationValidationError(
                        f"module registry entry {entry.name}@{entry.version} has invalid customization contracts"
                    )
                declarations.extend(item for item in raw if isinstance(item, Mapping))
        except CustomizationValidationError:
            raise
        except Exception as exc:
            raise CapabilityUnavailable(
                capability="module-registry.customization-contracts",
                detail={"code": "dependency_unavailable", "dependency": "module-registry"},
            ) from exc
        if not declarations:
            raise CapabilityUnavailable(
                capability="module-registry.customization-contracts",
                detail={"code": "dependency_unavailable", "dependency": "module-registry"},
            )
        for declaration in declarations:
            capabilities = declaration.get("capabilities")
            fields = declaration.get("fields")
            if not isinstance(capabilities, Mapping) or not isinstance(fields, Mapping):
                raise CustomizationValidationError("durable resource contract is malformed")
            cls.register_resource_contract(
                str(declaration.get("module", "")),
                str(declaration.get("resource", "")),
                str(declaration.get("version", "")),
                fields,
                capabilities,
            )

    @classmethod
    def register_resource_contract(
        cls,
        module: str,
        resource: str,
        version: str,
        fields: Mapping[str, Mapping[str, object]],
        capabilities: Mapping[str, object],
    ) -> ResourceContract:
        module_key = _slug(module, "module")
        resource_key = _slug(resource, "resource")
        version_key = _required_text(version, "version", maximum=32)
        if not isinstance(fields, Mapping) or not isinstance(capabilities, Mapping):
            raise CustomizationValidationError("fields and capabilities must be objects")
        defaults = default_configuration_document()
        policies = defaults["policies"]
        supported_types = frozenset(capabilities.get("custom_field_types", policies["field_types"]))
        triggers = frozenset(capabilities.get("rule_triggers", policies["rule_triggers"]))
        if not supported_types or not supported_types.issubset(PLATFORM_FIELD_TYPES):
            raise CustomizationValidationError("resource contract declares unsupported custom field types")
        if not triggers.issubset(PLATFORM_RULE_TRIGGERS):
            raise CustomizationValidationError("resource contract declares unsupported rule triggers")
        normalized_fields = {_slug(key, "field key"): MappingProxyType(dict(value)) for key, value in fields.items()}
        contract = ResourceContract(
            module_key,
            resource_key,
            version_key,
            MappingProxyType(normalized_fields),
            supported_types,
            frozenset(str(item) for item in capabilities.get("form_surfaces", (defaults["defaults"]["form_surface"],))),
            triggers,
            frozenset(str(item) for item in capabilities.get("entitlement_keys", ())),
            MappingProxyType(dict(capabilities)),
            bool(capabilities.get("available", False)),
            MappingProxyType(dict(capabilities.get("discovery", {}))),
        )
        identity = (module_key, resource_key, version_key)
        with cls._lock:
            existing = cls._contracts.get(identity)
            if existing is not None and existing != contract:
                raise CustomizationValidationError("an incompatible resource contract is already registered")
            cls._contracts[identity] = contract
        return contract

    @classmethod
    def unregister_resource_contract(cls, module: str, resource: str, version: str) -> ResourceContract | None:
        identity = (
            _slug(module, "module"),
            _slug(resource, "resource"),
            _required_text(version, "version", maximum=32),
        )
        with cls._lock:
            existing = cls._contracts.get(identity)
            if existing is None:
                return None
            unavailable = replace(existing, available=False)
            cls._contracts[identity] = unavailable
            return unavailable

    @classmethod
    def list_resource_contracts(cls, *, include_unavailable: bool = True) -> tuple[ResourceContract, ...]:
        if not cls._contracts:
            cls._load_durable_contracts()
        with cls._lock:
            contracts = tuple(cls._contracts[key] for key in sorted(cls._contracts))
        return contracts if include_unavailable else tuple(item for item in contracts if item.available)

    @classmethod
    def resolve_resource_contract(cls, tenant_id: UUID, module: str, resource: str, version: str) -> ResourceContract:
        _uuid(tenant_id, "tenant_id")
        identity = (
            _slug(module, "module"),
            _slug(resource, "resource"),
            _required_text(version, "version", maximum=32),
        )
        if not cls._contracts:
            cls._load_durable_contracts()
        with cls._lock:
            contract = cls._contracts.get(identity)
        if contract is None or not contract.available:
            raise CapabilityUnavailable(
                capability=f"{identity[0]}.{identity[1]}@{identity[2]}",
                detail={"code": "capability_unavailable", "module": identity[0], "resource": identity[1]},
            )
        return contract

    @classmethod
    def get_active_field_schema(cls, tenant_id: UUID, module: str, resource: str) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        definitions = CustomFieldDefinition.objects.filter(
            tenant_id=tenant,
            owner_module=_slug(module, "module"),
            target_resource=_slug(resource, "resource"),
            status="active",
            deleted_at__isnull=True,
        ).order_by("key")
        return {item.key: _definition_schema(item) for item in definitions}

    @classmethod
    def get_published_form(cls, tenant_id: UUID, module: str, resource: str, form_key: str) -> dict[str, object]:
        return FormService().get_render_schema(tenant_id, module=module, resource=resource, form_key=form_key)

    @classmethod
    def validate_record_extensions(
        cls, tenant_id: UUID, module: str, resource: str, record_id: UUID, values: Mapping[str, object]
    ) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        _uuid(record_id, "record_id")
        if not isinstance(values, Mapping):
            raise CustomizationValidationError("values must be an object")
        definitions = {
            item.key: item
            for item in CustomFieldDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=_slug(module, "module"),
                target_resource=_slug(resource, "resource"),
                status="active",
                deleted_at__isnull=True,
            )
        }
        unknown = sorted(set(values) - set(definitions))
        diagnostics: list[dict[str, object]] = []
        if unknown:
            diagnostics.extend({"code": "unknown_field", "field": item} for item in unknown)
        service = CustomFieldService()
        for key, definition in definitions.items():
            if key not in values:
                if definition.required:
                    diagnostics.append({"code": "required", "field": key})
                continue
            try:
                service.validate_value(
                    tenant, definition_id=definition.id, value=values[key], target_record_id=record_id
                )
            except CustomizationValidationError as exc:
                diagnostics.append({"code": "invalid_value", "field": key, "message": str(exc)})
        return {"valid": not diagnostics, "diagnostics": diagnostics}

    @classmethod
    def evaluate_rules(
        cls,
        tenant_id: UUID,
        module: str,
        resource: str,
        trigger: str,
        record: Mapping[str, object],
        changed_fields: Sequence[str],
        actor_id: UUID,
        idempotency_key: str,
    ) -> list[RuleExecution]:
        return BusinessRuleService().evaluate_for_resource(
            tenant_id,
            module=module,
            resource=resource,
            trigger=trigger,
            record=record,
            changed_fields=changed_fields,
            target_record_id=None,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

    @classmethod
    def get_dependency_impact(cls, tenant_id: UUID, module: str, resource: str, field_key: str) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        definition = CustomFieldDefinition.objects.filter(
            tenant_id=tenant,
            owner_module=_slug(module, "module"),
            target_resource=_slug(resource, "resource"),
            key=_slug(field_key, "field_key"),
            deleted_at__isnull=True,
        ).first()
        if definition is None:
            raise CustomizationNotFound("field definition not found")
        return CustomFieldService().get_definition_impact(tenant, definition_id=definition.id)


def _uuid(value: object, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CustomizationValidationError(f"{name} must be a valid UUID") from exc


def _required_text(value: object, name: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CustomizationValidationError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise CustomizationValidationError(f"{name} must not exceed {maximum} characters")
    return normalized


def _slug(value: object, name: str, *, tenant_id: UUID | None = None) -> str:
    configuration = effective_configuration(tenant_id) if tenant_id is not None else default_configuration_document()
    limits = configuration["limits"]
    policies = configuration["policies"]
    normalized = _required_text(
        value,
        name,
        maximum=int(limits["resource_key_length"]),
    ).lower()
    if re.fullmatch(str(policies["slug_pattern"]), normalized) is None:
        raise CustomizationValidationError(f"{name} must use lowercase slug syntax")
    return normalized


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _json_size(value: object, name: str, *, tenant_id: UUID | None = None) -> None:
    configuration = effective_configuration(tenant_id) if tenant_id is not None else default_configuration_document()
    limit = int(configuration["limits"]["json_bytes"])
    if len(_canonical(value).encode("utf-8")) > limit:
        raise CustomizationValidationError(f"{name} exceeds the configured {limit}-byte limit")


def _hash(*documents: object) -> str:
    return hashlib.sha256(_canonical(documents).encode("utf-8")).hexdigest()


def _correlation_uuid() -> UUID:
    raw = get_correlation_id()
    if not raw:
        established = uuid.uuid4()
        correlation_id_var.set(str(established))
        return established
    try:
        return UUID(raw)
    except (TypeError, ValueError, AttributeError) as exc:
        raise CustomizationValidationError("correlation_id must be a valid UUID") from exc


def idempotent_mutation(command_type: str) -> Any:
    """Persist and replay a complete tenant mutation atomically."""

    def decorate(operation: Any) -> Any:
        @wraps(operation)
        def wrapped(self: object, tenant_id: UUID, *args: object, **kwargs: object) -> object:
            tenant = _uuid(tenant_id, "tenant_id")
            raw_key = kwargs.pop("command_idempotency_key", None)
            if raw_key is None:
                # Internal callers remain source-compatible. All HTTP mutation
                # paths require this key at ingress and pass it here.
                return operation(self, tenant, *args, **kwargs)
            limit = int(effective_configuration(tenant)["limits"]["idempotency_key_length"])
            key = _required_text(raw_key, "idempotency_key", maximum=limit)
            storage_key = hashlib.sha256(f"{command_type}:{key}".encode("utf-8")).hexdigest()
            fingerprint = _hash(command_type, args, kwargs)
            with transaction.atomic():
                replay = (
                    IdempotentCommand.objects.select_for_update()
                    .filter(
                        tenant_id=tenant,
                        idempotency_key=storage_key,
                    )
                    .first()
                )
                if replay is not None:
                    if replay.command_type != command_type or replay.request_fingerprint != fingerprint:
                        raise EvaluationIdempotencyConflict("idempotency key was already used for another command")
                    model = apps.get_model(replay.resource_type)
                    result = model.objects.filter(tenant_id=tenant, id=replay.resource_id).first()
                    if result is None:
                        raise CustomizationError("idempotent command evidence references a missing result")
                    return result
                result = operation(self, tenant, *args, **kwargs)
                resource_id = getattr(result, "id", None)
                resource_type = getattr(getattr(result, "_meta", None), "label_lower", "")
                if resource_id is None or not resource_type:
                    raise CustomizationError("idempotent mutation did not return a persisted resource")
                actor = _uuid(kwargs.get("actor_id"), "actor_id")
                correlation = _correlation_uuid()
                IdempotentCommand.objects.create(
                    tenant_id=tenant,
                    idempotency_key=storage_key,
                    command_type=command_type,
                    request_fingerprint=fingerprint,
                    response_payload={"resource_id": str(resource_id), "resource_type": resource_type},
                    response_status=200,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    actor_id=actor,
                    correlation_id=correlation,
                )
                return result

        return wrapped

    return decorate


def _event(
    tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, event_type: str, actor_id: UUID, **payload: object
) -> OutboxEvent:
    safe_payload = {"entity_id": str(aggregate_id), "actor_id": str(actor_id), **payload}
    return OutboxEvent.objects.create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=f"customization_framework.{event_type}",
        payload={"schema_version": 1, "correlation_id": str(_correlation_uuid()), "payload": safe_payload},
    )


def _log(operation: str, entity: object, actor_id: UUID, started: float, outcome: str = "succeeded") -> None:
    logger.info(
        "Customization domain operation completed",
        extra={
            "correlation_id": str(_correlation_uuid()),
            "tenant_id": str(getattr(entity, "tenant_id")),
            "actor_id": str(actor_id),
            "operation": operation,
            "entity_type": entity.__class__.__name__,
            "entity_id": str(getattr(entity, "id")),
            "resulting_state": getattr(entity, "status", None),
            "lock_version": getattr(entity, "lock_version", None),
            "version": getattr(entity, "version", None),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "outcome": outcome,
        },
    )


def _lock(queryset: QuerySet[Any], object_id: UUID, label: str) -> Any:
    value = queryset.select_for_update().filter(id=object_id).first()
    if value is None:
        raise CustomizationNotFound(f"{label} not found")
    return value


def _check_lock(value: object, expected: int) -> None:
    if not isinstance(expected, int) or expected < 1:
        raise CustomizationValidationError("expected_lock_version must be a positive integer")
    if getattr(value, "lock_version") != expected:
        raise OptimisticLockConflict("the record has changed; reload before retrying")


def _apply_transition(
    machine: StateMachine[Any], aggregate: Any, command: str, transition_key: str, actor_id: UUID
) -> bool:
    """Apply configured lifecycle policy and append immutable evidence."""

    tenant = _uuid(aggregate.tenant_id, "tenant_id")
    configuration = effective_configuration(tenant)
    key = _required_text(
        transition_key,
        "transition_key",
        maximum=int(configuration["limits"]["idempotency_key_length"]),
    )
    actor = _uuid(actor_id, "actor_id")
    aggregate_type = {
        CustomFieldDefinition: "field_definition",
        FormDefinition: "form",
        BusinessRule: "rule",
    }.get(type(aggregate))
    if aggregate_type is None:
        raise CustomizationValidationError("unsupported lifecycle aggregate")
    existing = LifecycleTransitionRecord.objects.filter(
        tenant_id=tenant,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate.id,
        transition_key=key,
    ).first()
    if existing is not None:
        if existing.command != command:
            raise IdempotencyConflictError("transition key belongs to another command")
        return False
    current = str(aggregate.status)
    policy_name = {
        "field_definition": "field_transitions",
        "form": "form_transitions",
        "rule": "rule_transitions",
    }[aggregate_type]
    transitions = configuration["policies"][policy_name]
    commands = transitions.get(current, {}) if isinstance(transitions, Mapping) else {}
    target = commands.get(command) if isinstance(commands, Mapping) else None
    if current in machine.terminal_states and target is None:
        raise CustomizationValidationError("terminal lifecycle state is immutable")
    if not isinstance(target, str):
        raise CustomizationValidationError("lifecycle transition is not allowed")
    aggregate.status = target
    previous_version = (
        LifecycleTransitionRecord.objects.filter(
            tenant_id=tenant,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate.id,
        ).aggregate(models_max=Max("version"))["models_max"]
        or 0
    )
    correlation = _correlation_uuid()
    LifecycleTransitionRecord.objects.create(
        tenant_id=tenant,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate.id,
        version=previous_version + 1,
        transition_key=key,
        command=command,
        from_state=current,
        to_state=target,
        metadata={"correlation_id": str(correlation)},
        actor_id=actor,
        correlation_id=correlation,
        occurred_at=timezone.now(),
    )
    return True


def _normalize_definition_data(
    data: Mapping[str, object],
    *,
    tenant_id: UUID,
    partial: bool = False,
) -> dict[str, object]:
    configuration = effective_configuration(tenant_id)
    limits = configuration["limits"]
    policies = configuration["policies"]
    defaults = configuration["defaults"]
    allowed = {
        "key",
        "label",
        "description",
        "owner_module",
        "target_resource",
        "target_contract_version",
        "data_type",
        "required",
        "searchable",
        "default_value",
        "validation_schema",
        "presentation_schema",
    }
    unknown = set(data) - allowed
    if unknown:
        raise CustomizationValidationError(f"unknown field definition keys: {', '.join(sorted(unknown))}")
    normalized = dict(data)
    if not partial:
        normalized.setdefault("required", defaults["field_required"])
        normalized.setdefault("searchable", defaults["field_searchable"])
    for key in ("key", "owner_module", "target_resource"):
        if key in normalized:
            normalized[key] = _slug(normalized[key], key, tenant_id=tenant_id)
    if "key" in normalized and len(str(normalized["key"])) > int(limits["field_key_length"]):
        raise CustomizationValidationError("key exceeds the configured field key length")
    if "label" in normalized:
        normalized["label"] = _required_text(
            normalized["label"],
            "label",
            maximum=int(limits["field_label_length"]),
        )
    if "description" in normalized:
        normalized["description"] = str(normalized["description"]).strip()
    if "target_contract_version" in normalized:
        normalized["target_contract_version"] = _required_text(
            normalized["target_contract_version"],
            "target_contract_version",
            maximum=int(limits["contract_version_length"]),
        )
    if "data_type" in normalized and normalized["data_type"] not in policies["field_types"]:
        raise CustomizationValidationError("unsupported field data type")
    for key in ("validation_schema", "presentation_schema"):
        if key in normalized:
            if not isinstance(normalized[key], Mapping):
                raise CustomizationValidationError(f"{key} must be an object")
            _json_size(normalized[key], key, tenant_id=tenant_id)
            normalized[key] = dict(normalized[key])
    if not partial:
        missing = {"key", "label", "owner_module", "target_resource", "target_contract_version", "data_type"} - set(
            normalized
        )
        if missing:
            raise CustomizationValidationError(f"missing field definition keys: {', '.join(sorted(missing))}")
    return normalized


def _definition_schema(definition: CustomFieldDefinition) -> dict[str, object]:
    type_map: dict[str, object] = {
        "text": "string",
        "long_text": "string",
        "integer": "integer",
        "decimal": "number",
        "boolean": "boolean",
        "date": "string",
        "datetime": "string",
        "uuid": "string",
        "choice": "string",
        "multi_choice": "array",
        "json": ["object", "array", "string", "number", "boolean", "null"],
    }
    schema = dict(definition.validation_schema or {})
    declared = schema.get("type")
    expected = type_map[definition.data_type]
    if declared is not None and declared != expected:
        raise CustomizationValidationError("validation schema type conflicts with the field data type")
    schema["type"] = expected
    if definition.data_type == "date":
        schema.setdefault("format", "date")
    elif definition.data_type == "datetime":
        schema.setdefault("format", "date-time")
    elif definition.data_type == "uuid":
        schema.setdefault("format", "uuid")
    elif definition.data_type == "multi_choice":
        schema.setdefault("items", {"type": "string"})
        schema.setdefault("uniqueItems", True)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CustomizationValidationError("validation schema is not a valid JSON Schema") from exc
    return schema


def _definition_document(definition: CustomFieldDefinition) -> dict[str, object]:
    return {
        "key": definition.key,
        "label": definition.label,
        "description": definition.description,
        "owner_module": definition.owner_module,
        "target_resource": definition.target_resource,
        "target_contract_version": definition.target_contract_version,
        "data_type": definition.data_type,
        "required": definition.required,
        "searchable": definition.searchable,
        "default_value": definition.default_value,
        "validation_schema": definition.validation_schema,
        "presentation_schema": definition.presentation_schema,
        "status": definition.status,
        "activated_at": definition.activated_at.isoformat() if definition.activated_at else None,
        "deprecated_at": definition.deprecated_at.isoformat() if definition.deprecated_at else None,
        "retired_at": definition.retired_at.isoformat() if definition.retired_at else None,
    }


def _record_definition_version(
    definition: CustomFieldDefinition,
    *,
    actor_id: UUID,
    correlation_id: UUID | None = None,
) -> CustomFieldDefinitionVersion:
    number = (
        CustomFieldDefinitionVersion.objects.filter(
            tenant_id=definition.tenant_id,
            definition_id=definition.id,
        ).aggregate(maximum=Max("version"))["maximum"]
        or 0
    ) + 1
    document = _definition_document(definition)
    return CustomFieldDefinitionVersion.objects.create(
        tenant_id=definition.tenant_id,
        definition=definition,
        version=number,
        document=document,
        content_hash=_hash(document),
        actor_id=actor_id,
        correlation_id=correlation_id or _correlation_uuid(),
    )


class CustomFieldService:
    """Field-definition and field-value aggregate service."""

    registry = CustomizationRegistry

    @idempotent_mutation("field_definition.create")
    def create_definition(
        self, tenant_id: UUID, *, actor_id: UUID, data: Mapping[str, object]
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = effective_configuration(tenant)
        values = _normalize_definition_data(data, tenant_id=tenant)
        contract = self.registry.resolve_resource_contract(
            tenant, str(values["owner_module"]), str(values["target_resource"]), str(values["target_contract_version"])
        )
        if values["data_type"] not in contract.custom_field_types:
            raise CustomizationValidationError("target contract does not support this field type")
        with transaction.atomic():
            definition = CustomFieldDefinition.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                status=configuration["defaults"]["field_status"],
                **values,
            )
            _definition_schema(definition)
            if "default_value" in values and values["default_value"] is not None:
                self._validate_definition_value(definition, values["default_value"])
            _record_definition_version(definition, actor_id=actor)
            _event(
                tenant, "field_definition", definition.id, "field_definition.created", actor, status=definition.status
            )
        _log("create_definition", definition, actor, started)
        return definition

    def get_definition(self, tenant_id: UUID, *, definition_id: UUID) -> CustomFieldDefinition:
        value = CustomFieldDefinition.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(definition_id, "definition_id"), deleted_at__isnull=True
        ).first()
        if value is None:
            raise CustomizationNotFound("field definition not found")
        return value

    def list_definitions(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "key"
    ) -> QuerySet[CustomFieldDefinition]:
        queryset = CustomFieldDefinition.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True
        )
        allowed_filters = {"owner_module", "target_resource", "data_type", "status"}
        for key, value in (filters or {}).items():
            if key not in allowed_filters:
                raise CustomizationValidationError(f"unsupported definition filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(_ordering(ordering, {"key", "label", "status", "created_at", "updated_at"}, "key"))

    @idempotent_mutation("field_definition.update")
    def update_definition(
        self,
        tenant_id: UUID,
        *,
        definition_id: UUID,
        expected_lock_version: int,
        actor_id: UUID,
        data: Mapping[str, object],
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        updates = _normalize_definition_data(data, tenant_id=tenant, partial=True)
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            _check_lock(definition, expected_lock_version)
            if definition.status != "draft" and {"key", "owner_module", "target_resource", "data_type"} & set(updates):
                raise CustomizationValidationError("identity and data type are immutable after activation")
            for key, value in updates.items():
                setattr(definition, key, value)
            self.registry.resolve_resource_contract(
                tenant, definition.owner_module, definition.target_resource, definition.target_contract_version
            )
            _definition_schema(definition)
            if definition.default_value is not None:
                self._validate_definition_value(definition, definition.default_value)
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(update_fields=[*updates, "updated_by", "lock_version", "updated_at"])
            _record_definition_version(definition, actor_id=actor)
            _event(
                tenant,
                "field_definition",
                definition.id,
                "field_definition.updated",
                actor,
                status=definition.status,
                lock_version=definition.lock_version,
            )
        _log("update_definition", definition, actor, started)
        return definition

    @idempotent_mutation("field_definition.transition")
    def transition_definition(
        self, tenant_id: UUID, *, definition_id: UUID, command: str, transition_key: str, actor_id: UUID
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            if command == "activate":
                self.registry.resolve_resource_contract(
                    tenant, definition.owner_module, definition.target_resource, definition.target_contract_version
                )
                _definition_schema(definition)
                if definition.default_value is not None:
                    self._validate_definition_value(definition, definition.default_value)
            if not _apply_transition(FIELD_STATE_MACHINE, definition, command, transition_key, actor):
                return definition
            now = timezone.now()
            timestamp_field = {"activate": "activated_at", "deprecate": "deprecated_at", "retire": "retired_at"}[
                command
            ]
            setattr(definition, timestamp_field, now)
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(
                update_fields=[
                    "status",
                    timestamp_field,
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _record_definition_version(definition, actor_id=actor)
            event_name = {"activate": "activated", "deprecate": "deprecated", "retire": "retired"}[command]
            _event(
                tenant,
                "field_definition",
                definition.id,
                f"field_definition.{event_name}",
                actor,
                status=definition.status,
            )
        _log(f"transition_definition.{command}", definition, actor, started)
        return definition

    def list_definition_versions(
        self,
        tenant_id: UUID,
        *,
        definition_id: UUID,
    ) -> QuerySet[CustomFieldDefinitionVersion]:
        definition = self.get_definition(tenant_id, definition_id=definition_id)
        return CustomFieldDefinitionVersion.objects.filter(
            tenant_id=definition.tenant_id,
            definition_id=definition.id,
        ).order_by("-version")

    @idempotent_mutation("field_definition.rollback")
    def rollback_definition(
        self,
        tenant_id: UUID,
        *,
        definition_id: UUID,
        target_version: int,
        expected_lock_version: int,
        actor_id: UUID,
    ) -> CustomFieldDefinition:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            _check_lock(definition, expected_lock_version)
            snapshot = CustomFieldDefinitionVersion.objects.filter(
                tenant_id=tenant,
                definition_id=definition.id,
                version=target_version,
            ).first()
            if snapshot is None:
                raise CustomizationNotFound("field definition version not found")
            document = dict(snapshot.document)
            mutable_fields = {
                "label",
                "description",
                "required",
                "searchable",
                "default_value",
                "validation_schema",
                "presentation_schema",
            }
            normalized = _normalize_definition_data(
                {key: document[key] for key in mutable_fields},
                tenant_id=tenant,
                partial=True,
            )
            for key, value in normalized.items():
                setattr(definition, key, value)
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(update_fields=[*normalized, "updated_by", "lock_version", "updated_at"])
            _record_definition_version(definition, actor_id=actor)
            _event(
                tenant,
                "field_definition",
                definition.id,
                "field_definition.rolled_back",
                actor,
                target_version=target_version,
                lock_version=definition.lock_version,
            )
        return definition

    @idempotent_mutation("field_definition.delete")
    def delete_definition(
        self, tenant_id: UUID, *, definition_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> CustomFieldDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            definition = _lock(
                CustomFieldDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(definition_id, "definition_id"),
                "field definition",
            )
            _check_lock(definition, expected_lock_version)
            impact = self.get_definition_impact(tenant, definition_id=definition.id)
            if impact["blocking"]:
                raise CustomizationValidationError("field definition has unresolved dependencies", detail=impact)
            delete_statuses = effective_configuration(tenant)["policies"]["field_delete_statuses"]
            if definition.status not in delete_statuses:
                raise CustomizationValidationError("field definition status does not permit deletion")
            definition.deleted_at = timezone.now()
            definition.deleted_by = actor
            definition.updated_by = actor
            definition.lock_version += 1
            definition.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(
                tenant, "field_definition", definition.id, "field_definition.deleted", actor, status=definition.status
            )
        _log("delete_definition", definition, actor, started)
        return definition

    def _validate_definition_value(self, definition: CustomFieldDefinition, value: object) -> None:
        _json_size(value, "value", tenant_id=definition.tenant_id)
        errors = sorted(
            Draft202012Validator(_definition_schema(definition), format_checker=FormatChecker()).iter_errors(value),
            key=lambda item: list(item.path),
        )
        if errors:
            raise CustomizationValidationError(
                "value does not conform to the field definition",
                detail={"errors": [{"path": list(item.path), "message": item.message} for item in errors]},
            )

    def validate_value(
        self, tenant_id: UUID, *, definition_id: UUID, value: object, target_record_id: UUID | None = None
    ) -> dict[str, object]:
        definition = self.get_definition(tenant_id, definition_id=definition_id)
        if target_record_id is not None:
            _uuid(target_record_id, "target_record_id")
        self._validate_definition_value(definition, value)
        return {
            "valid": True,
            "definition_id": str(definition.id),
            "definition_revision": definition.lock_version,
            "diagnostics": [],
        }

    @idempotent_mutation("field_value.upsert")
    def upsert_value(
        self,
        tenant_id: UUID,
        *,
        definition_id: UUID,
        target_record_id: UUID,
        value: object,
        source: str,
        expected_lock_version: int | None,
        actor_id: UUID,
    ) -> CustomFieldValue:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        target = _uuid(target_record_id, "target_record_id")
        configuration = effective_configuration(tenant)
        if source not in configuration["policies"]["value_sources"]:
            raise CustomizationValidationError("source is not allowed by tenant configuration")
        definition = self.get_definition(tenant, definition_id=definition_id)
        if definition.status not in configuration["policies"]["value_allowed_statuses"]:
            raise CustomizationValidationError("field status does not permit stored values")
        self.validate_value(tenant, definition_id=definition.id, value=value, target_record_id=target)
        with transaction.atomic():
            existing = (
                CustomFieldValue.objects.select_for_update()
                .filter(tenant_id=tenant, definition_id=definition.id, target_record_id=target, deleted_at__isnull=True)
                .first()
            )
            if existing is None:
                if expected_lock_version is not None:
                    raise OptimisticLockConflict("field value does not exist")
                result = CustomFieldValue.objects.create(
                    tenant_id=tenant,
                    definition=definition,
                    target_record_id=target,
                    value=value,
                    definition_revision=definition.lock_version,
                    source=source,
                    created_by=actor,
                    updated_by=actor,
                )
            else:
                if expected_lock_version is None:
                    raise OptimisticLockConflict("field value already exists; provide expected_lock_version")
                _check_lock(existing, expected_lock_version)
                existing.value = value
                existing.source = source
                existing.definition_revision = definition.lock_version
                existing.updated_by = actor
                existing.lock_version += 1
                existing.save(
                    update_fields=["value", "source", "definition_revision", "updated_by", "lock_version", "updated_at"]
                )
                result = existing
            _event(
                tenant,
                "field_value",
                result.id,
                "field_value.upserted",
                actor,
                definition_id=str(definition.id),
                lock_version=result.lock_version,
            )
        _log("upsert_value", result, actor, started)
        return result

    def get_value(self, tenant_id: UUID, *, definition_id: UUID, target_record_id: UUID) -> CustomFieldValue:
        value = (
            CustomFieldValue.objects.filter(
                tenant_id=_uuid(tenant_id, "tenant_id"),
                definition_id=_uuid(definition_id, "definition_id"),
                target_record_id=_uuid(target_record_id, "target_record_id"),
                deleted_at__isnull=True,
            )
            .select_related("definition")
            .first()
        )
        if value is None:
            raise CustomizationNotFound("field value not found")
        return value

    def list_values(
        self,
        tenant_id: UUID,
        *,
        filters: Mapping[str, object] | None = None,
        ordering: str = "-updated_at",
        require_scope: bool = True,
    ) -> QuerySet[CustomFieldValue]:
        supplied = dict(filters or {})
        if require_scope and not (supplied.get("target_record_id") or supplied.get("definition_id")):
            raise CustomizationValidationError("target_record_id or definition_id is required")
        tenant = _uuid(tenant_id, "tenant_id")
        queryset = CustomFieldValue.objects.filter(tenant_id=tenant, deleted_at__isnull=True).select_related(
            "definition"
        )
        allowed = {
            "definition_id",
            "target_record_id",
            "source",
            "updated_at_after",
            "updated_at_before",
        }
        unknown = set(supplied) - allowed
        if unknown:
            key = sorted(unknown)[0]
            raise CustomizationValidationError(
                f"unsupported field value filter: {key}",
                detail={key: ["Unsupported filter."]},
            )
        for key in ("definition_id", "target_record_id"):
            if supplied.get(key):
                queryset = queryset.filter(**{key: _uuid(supplied[key], key)})
        if supplied.get("source"):
            policies = effective_configuration(tenant)["policies"]
            if not isinstance(policies, Mapping):
                raise CustomizationValidationError("configuration policies are unavailable")
            allowed_sources = policies.get("value_sources")
            if not isinstance(allowed_sources, list) or str(supplied["source"]) not in allowed_sources:
                raise CustomizationValidationError(
                    "unsupported field value source",
                    detail={"source": ["Unsupported value."]},
                )
            queryset = queryset.filter(source=str(supplied["source"]))
        for key, lookup in (
            ("updated_at_after", "updated_at__gte"),
            ("updated_at_before", "updated_at__lte"),
        ):
            raw = supplied.get(key)
            if raw:
                parsed = parse_datetime(str(raw))
                if parsed is None:
                    raise CustomizationValidationError(
                        f"{key} must be an ISO-8601 datetime",
                        detail={key: ["Must be an ISO-8601 datetime."]},
                    )
                queryset = queryset.filter(**{lookup: parsed})
        return queryset.order_by(
            _ordering(ordering, {"updated_at", "created_at"}, "updated_at"),
            "id",
        )

    @idempotent_mutation("field_value.delete")
    def delete_value(
        self, tenant_id: UUID, *, value_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> CustomFieldValue:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            value = _lock(
                CustomFieldValue.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(value_id, "value_id"),
                "field value",
            )
            _check_lock(value, expected_lock_version)
            value.deleted_at = timezone.now()
            value.deleted_by = actor
            value.updated_by = actor
            value.lock_version += 1
            value.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(
                tenant, "field_value", value.id, "field_value.deleted", actor, definition_id=str(value.definition_id)
            )
        _log("delete_value", value, actor, started)
        return value

    def get_definition_impact(self, tenant_id: UUID, *, definition_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        definition = self.get_definition(tenant, definition_id=definition_id)
        value_count = CustomFieldValue.objects.filter(
            tenant_id=tenant, definition_id=definition.id, deleted_at__isnull=True
        ).count()
        forms = []
        for version in FormLayoutVersion.objects.filter(tenant_id=tenant, form__deleted_at__isnull=True).select_related(
            "form"
        ):
            if definition.key in _collect_field_refs(version.layout):
                forms.append({"form_id": str(version.form_id), "version_id": str(version.id), "status": version.status})
        rules = []
        for version in BusinessRuleVersion.objects.filter(
            tenant_id=tenant, rule__deleted_at__isnull=True
        ).select_related("rule"):
            dependencies = version.dependencies or []
            if definition.key in dependencies or any(
                isinstance(item, Mapping) and item.get("field_key") == definition.key for item in dependencies
            ):
                rules.append({"rule_id": str(version.rule_id), "version_id": str(version.id), "status": version.status})
        return {
            "entity_type": "field_definition",
            "entity_id": str(definition.id),
            "value_count": value_count,
            "forms": forms,
            "rules": rules,
            "dependency_count": value_count + len(forms) + len(rules),
            "blocking": bool(value_count or forms or rules),
            "capability_unavailable": _capability_unavailable(
                tenant,
                module=definition.owner_module,
                resource=definition.target_resource,
                version=definition.target_contract_version,
            ),
        }


def _ordering(value: str, allowed: set[str], default: str) -> str:
    if not isinstance(value, str):
        return default
    descending = value.startswith("-")
    field = value[1:] if descending else value
    if field not in allowed:
        raise CustomizationValidationError("unsupported ordering field")
    return f"-{field}" if descending else field


def _capability_unavailable(
    tenant_id: UUID,
    *,
    module: str,
    resource: str,
    version: str,
) -> bool:
    try:
        CustomizationRegistry.resolve_resource_contract(
            tenant_id,
            module,
            resource,
            version,
        )
    except CapabilityUnavailable:
        return True
    return False


def _collect_field_refs(document: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(document, Mapping):
        for key in ("field", "field_key"):
            value = document.get(key)
            if isinstance(value, str) and PLATFORM_SLUG_RE.fullmatch(value):
                refs.add(value)
        for value in document.values():
            refs.update(_collect_field_refs(value))
    elif isinstance(document, list):
        for value in document:
            refs.update(_collect_field_refs(value))
    return refs


class FormService:
    """Form aggregate and immutable layout publication service."""

    registry = CustomizationRegistry

    @idempotent_mutation("form.create")
    def create_form(self, tenant_id: UUID, *, actor_id: UUID, data: Mapping[str, object]) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = effective_configuration(tenant)
        values = _form_data(data, tenant_id=tenant)
        self.registry.resolve_resource_contract(
            tenant, values["owner_module"], values["target_resource"], values["target_contract_version"]
        )
        with transaction.atomic():
            form = FormDefinition.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                status=configuration["defaults"]["form_status"],
                **values,
            )
            _event(tenant, "form", form.id, "form.created", actor, status=form.status)
        _log("create_form", form, actor, started)
        return form

    def get_form(self, tenant_id: UUID, *, form_id: UUID) -> FormDefinition:
        value = FormDefinition.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(form_id, "form_id"), deleted_at__isnull=True
        ).first()
        if value is None:
            raise CustomizationNotFound("form not found")
        return value

    def list_forms(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "key"
    ) -> QuerySet[FormDefinition]:
        queryset = FormDefinition.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True)
        for key, value in (filters or {}).items():
            if key not in {"owner_module", "target_resource", "status"}:
                raise CustomizationValidationError(f"unsupported form filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(_ordering(ordering, {"key", "name", "status", "created_at", "updated_at"}, "key"))

    def list_layout_versions(
        self,
        tenant_id: UUID,
        *,
        filters: Mapping[str, object] | None = None,
        ordering: str = "-version",
    ) -> QuerySet[FormLayoutVersion]:
        queryset = FormLayoutVersion.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("form")
        allowed = {"form_id", "status", "version"}
        for key, value in (filters or {}).items():
            if key not in allowed:
                raise CustomizationValidationError(f"unsupported layout version filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(
            _ordering(ordering, {"version", "created_at", "status"}, "version"),
            "id",
        )

    @idempotent_mutation("form.update")
    def update_form(
        self, tenant_id: UUID, *, form_id: UUID, expected_lock_version: int, actor_id: UUID, data: Mapping[str, object]
    ) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        updates = _form_data(data, tenant_id=tenant, partial=True)
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            _check_lock(form, expected_lock_version)
            if form.status != "draft" and {"key", "owner_module", "target_resource", "target_contract_version"} & set(
                updates
            ):
                raise CustomizationValidationError("published form identity is immutable")
            for key, value in updates.items():
                setattr(form, key, value)
            form.updated_by = actor
            form.lock_version += 1
            form.save(update_fields=[*updates, "updated_by", "lock_version", "updated_at"])
            _event(tenant, "form", form.id, "form.updated", actor, status=form.status, lock_version=form.lock_version)
        _log("update_form", form, actor, started)
        return form

    def validate_layout(self, tenant_id: UUID, *, form_id: UUID, layout: object) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        form = self.get_form(tenant, form_id=form_id)
        configuration = effective_configuration(tenant)
        _json_size(layout, "layout", tenant_id=tenant)
        diagnostics: list[dict[str, object]] = []
        if (
            not isinstance(layout, Mapping)
            or layout.get("schema_version") != configuration["defaults"]["layout_schema_version"]
            or not isinstance(layout.get("sections"), list)
        ):
            diagnostics.append({"code": "invalid_layout_schema", "path": []})
        refs = _collect_field_refs(layout)
        if len(refs) != len(_ordered_field_ref_occurrences(layout)):
            diagnostics.append({"code": "duplicate_field_reference", "path": []})
        active = set(
            CustomFieldDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=form.owner_module,
                target_resource=form.target_resource,
                deleted_at__isnull=True,
            )
            .exclude(status="retired")
            .values_list("key", flat=True)
        )
        for ref in sorted(refs - active):
            diagnostics.append({"code": "unresolved_or_retired_field", "field": ref})
        try:
            self.registry.resolve_resource_contract(
                tenant, form.owner_module, form.target_resource, form.target_contract_version
            )
        except CapabilityUnavailable:
            diagnostics.append({"code": "capability_unavailable"})
        return {"valid": not diagnostics, "diagnostics": diagnostics, "field_references": sorted(refs)}

    @idempotent_mutation("form.layout_version.create")
    def create_layout_version(
        self, tenant_id: UUID, *, form_id: UUID, actor_id: UUID, layout: object, change_summary: str
    ) -> FormLayoutVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = effective_configuration(tenant)
        summary = _required_text(
            change_summary,
            "change_summary",
            maximum=int(configuration["limits"]["change_summary_length"]),
        )
        report = self.validate_layout(tenant, form_id=form_id, layout=layout)
        if not report["valid"]:
            raise CustomizationValidationError("layout validation failed", detail=report)
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            version_number = (
                FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            ) + 1
            try:
                version = FormLayoutVersion.objects.create(
                    tenant_id=tenant,
                    form=form,
                    version=version_number,
                    schema_version=configuration["defaults"]["layout_schema_version"],
                    layout=layout,
                    content_hash=_hash(layout),
                    change_summary=summary,
                    status=configuration["defaults"]["layout_status"],
                    validation_errors=[],
                    created_by=actor,
                )
            except IntegrityError as exc:
                raise CustomizationValidationError("an identical layout version already exists") from exc
            _event(
                tenant,
                "form_layout",
                version.id,
                "form.layout_version_created",
                actor,
                form_id=str(form.id),
                version=version.version,
            )
        _log("create_layout_version", version, actor, started)
        return version

    @idempotent_mutation("form.publish")
    def publish_layout(
        self, tenant_id: UUID, *, form_id: UUID, layout_version_id: UUID, transition_key: str, actor_id: UUID
    ) -> FormLayoutVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            source = _lock(
                FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id),
                _uuid(layout_version_id, "layout_version_id"),
                "layout version",
            )
            report = self.validate_layout(tenant, form_id=form.id, layout=source.layout)
            if not report["valid"]:
                raise CustomizationValidationError("layout publication validation failed", detail=report)
            if source.status not in {"candidate", "published", "superseded"}:
                raise CustomizationValidationError("only a candidate or historical valid layout can be published")
            replay = PublicationRecord.objects.filter(
                tenant_id=tenant,
                aggregate_type="form",
                aggregate_id=form.id,
                publication_key=transition_key,
                event_type="published",
            ).first()
            if replay is not None and replay.snapshot_id != source.id:
                raise IdempotencyConflictError("publication key was already used for another layout version")
            if replay is not None:
                return source
            previous_publication = (
                PublicationRecord.objects.filter(
                    tenant_id=tenant,
                    aggregate_type="form",
                    aggregate_id=form.id,
                    event_type="published",
                )
                .order_by("-occurred_at", "-id")
                .first()
            )
            command = "publish_revision" if form.status == "published" else "publish"
            changed = _apply_transition(FORM_STATE_MACHINE, form, command, transition_key, actor)
            if not changed:
                raise IdempotencyConflictError("publication lifecycle evidence is inconsistent")
            now = timezone.now()
            next_version = (
                FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id).aggregate(maximum=Max("version"))[
                    "maximum"
                ]
                or 0
            ) + 1
            published_snapshot = FormLayoutVersion.objects.create(
                tenant_id=tenant,
                form=form,
                version=next_version,
                schema_version=source.schema_version,
                layout=source.layout,
                content_hash=_hash(source.layout, {"publication_key": transition_key, "version": next_version}),
                change_summary=f"Published from version {source.version}",
                status="published",
                validation_errors=[],
                created_by=actor,
                published_at=now,
                published_by=actor,
            )
            correlation = _correlation_uuid()
            if previous_publication is not None:
                PublicationRecord.objects.create(
                    tenant_id=tenant,
                    aggregate_type="form",
                    aggregate_id=form.id,
                    snapshot_id=previous_publication.snapshot_id,
                    version=previous_publication.version,
                    event_type="superseded",
                    publication_key=transition_key,
                    actor_id=actor,
                    correlation_id=correlation,
                    occurred_at=now,
                )
            PublicationRecord.objects.create(
                tenant_id=tenant,
                aggregate_type="form",
                aggregate_id=form.id,
                snapshot_id=published_snapshot.id,
                version=published_snapshot.version,
                event_type="published",
                publication_key=transition_key,
                supersedes_snapshot_id=previous_publication.snapshot_id if previous_publication else None,
                actor_id=actor,
                correlation_id=correlation,
                occurred_at=now,
            )
            form.published_version = published_snapshot.version
            form.published_at = now
            form.published_by = actor
            form.updated_by = actor
            form.lock_version += 1
            form.save(
                update_fields=[
                    "status",
                    "published_version",
                    "published_at",
                    "published_by",
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _event(
                tenant,
                "form",
                form.id,
                "form.published",
                actor,
                layout_version_id=str(published_snapshot.id),
                version=published_snapshot.version,
            )
        _log("publish_layout", form, actor, started)
        return published_snapshot

    @idempotent_mutation("form.archive")
    def archive_form(self, tenant_id: UUID, *, form_id: UUID, transition_key: str, actor_id: UUID) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            if not _apply_transition(FORM_STATE_MACHINE, form, "archive", transition_key, actor):
                return form
            form.archived_at = timezone.now()
            form.updated_by = actor
            form.lock_version += 1
            form.save(
                update_fields=[
                    "status",
                    "archived_at",
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _event(tenant, "form", form.id, "form.archived", actor, status=form.status)
        _log("archive_form", form, actor, started)
        return form

    @idempotent_mutation("form.delete")
    def delete_form(
        self, tenant_id: UUID, *, form_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> FormDefinition:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            form = _lock(
                FormDefinition.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(form_id, "form_id"),
                "form",
            )
            _check_lock(form, expected_lock_version)
            if form.status not in effective_configuration(tenant)["policies"]["form_delete_statuses"]:
                raise CustomizationValidationError("form status does not permit deletion")
            form.deleted_at = timezone.now()
            form.deleted_by = actor
            form.updated_by = actor
            form.lock_version += 1
            form.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(tenant, "form", form.id, "form.deleted", actor, status=form.status)
        _log("delete_form", form, actor, started)
        return form

    def get_render_schema(
        self,
        tenant_id: UUID,
        *,
        form_id: UUID | None = None,
        module: str | None = None,
        resource: str | None = None,
        form_key: str | None = None,
    ) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        if form_id is not None:
            form = self.get_form(tenant, form_id=form_id)
        elif module and resource and form_key:
            form = FormDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=_slug(module, "module"),
                target_resource=_slug(resource, "resource"),
                key=_slug(form_key, "form_key"),
                status="published",
                deleted_at__isnull=True,
            ).first()
            if form is None:
                raise CustomizationNotFound("published form not found")
        else:
            raise CustomizationValidationError("form_id or module/resource/form_key is required")
        if form.status != "published" or form.published_version is None:
            raise CustomizationValidationError("form is not published")
        self.registry.resolve_resource_contract(
            tenant, form.owner_module, form.target_resource, form.target_contract_version
        )
        version = FormLayoutVersion.objects.filter(
            tenant_id=tenant, form_id=form.id, version=form.published_version, status="published"
        ).first()
        if version is None:
            raise CustomizationNotFound("published layout not found")
        return {
            "form_id": str(form.id),
            "form_key": form.key,
            "owner_module": form.owner_module,
            "target_resource": form.target_resource,
            "contract_version": form.target_contract_version,
            "version": version.version,
            "content_hash": version.content_hash,
            "layout": version.layout,
            "fields": [
                {
                    "id": str(definition.id),
                    "tenant_id": str(definition.tenant_id),
                    **_definition_document(definition),
                    "created_by": str(definition.created_by),
                    "updated_by": str(definition.updated_by),
                    "created_at": definition.created_at.isoformat(),
                    "updated_at": definition.updated_at.isoformat(),
                    "deleted_at": None,
                    "deleted_by": None,
                    "lock_version": definition.lock_version,
                }
                for definition in CustomFieldDefinition.objects.filter(
                    tenant_id=tenant,
                    owner_module=form.owner_module,
                    target_resource=form.target_resource,
                    status="active",
                    deleted_at__isnull=True,
                ).order_by("key")
            ],
        }

    def get_form_impact(self, tenant_id: UUID, *, form_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        form = self.get_form(tenant, form_id=form_id)
        versions = FormLayoutVersion.objects.filter(tenant_id=tenant, form_id=form.id)
        refs: set[str] = set()
        for layout in versions.values_list("layout", flat=True):
            refs.update(_collect_field_refs(layout))
        return {
            "entity_type": "form",
            "entity_id": str(form.id),
            "layout_version_count": versions.count(),
            "field_references": sorted(refs),
            "dependency_count": len(refs),
            "blocking": form.status == "published",
            "capability_unavailable": _capability_unavailable(
                tenant,
                module=form.owner_module,
                resource=form.target_resource,
                version=form.target_contract_version,
            ),
        }


def _form_data(
    data: Mapping[str, object],
    *,
    tenant_id: UUID,
    partial: bool = False,
) -> dict[str, Any]:
    configuration = effective_configuration(tenant_id)
    limits = configuration["limits"]
    allowed = {"key", "name", "description", "owner_module", "target_resource", "target_contract_version"}
    unknown = set(data) - allowed
    if unknown:
        raise CustomizationValidationError(f"unknown form keys: {', '.join(sorted(unknown))}")
    result = dict(data)
    for key in ("key", "owner_module", "target_resource"):
        if key in result:
            result[key] = _slug(result[key], key, tenant_id=tenant_id)
    if "key" in result and len(str(result["key"])) > int(limits["form_key_length"]):
        raise CustomizationValidationError("key exceeds the configured form key length")
    if "name" in result:
        result["name"] = _required_text(result["name"], "name", maximum=int(limits["form_name_length"]))
    if "target_contract_version" in result:
        result["target_contract_version"] = _required_text(
            result["target_contract_version"],
            "target_contract_version",
            maximum=int(limits["contract_version_length"]),
        )
    if "description" in result:
        result["description"] = str(result["description"]).strip()
    if not partial:
        missing = {"key", "name", "owner_module", "target_resource", "target_contract_version"} - set(result)
        if missing:
            raise CustomizationValidationError(f"missing form keys: {', '.join(sorted(missing))}")
    return result


def _ordered_field_ref_occurrences(document: object) -> list[str]:
    result: list[str] = []
    if isinstance(document, Mapping):
        for key in ("field", "field_key"):
            value = document.get(key)
            if isinstance(value, str) and PLATFORM_SLUG_RE.fullmatch(value):
                result.append(value)
        for value in document.values():
            result.extend(_ordered_field_ref_occurrences(value))
    elif isinstance(document, list):
        for value in document:
            result.extend(_ordered_field_ref_occurrences(value))
    return result


class _EvaluationBudget:
    def __init__(self, tenant_id: UUID) -> None:
        configuration = effective_configuration(tenant_id)
        limits = configuration["limits"]
        policies = configuration["policies"]
        self.started = time.monotonic()
        self.nodes = 0
        self.max_nodes = int(limits["ast_nodes"])
        self.max_depth = int(limits["ast_depth"])
        self.max_evaluation_ms = int(limits["evaluation_ms"])
        self.message_length = int(limits["change_summary_length"])
        self.condition_operators = frozenset(policies["condition_operators"])
        self.action_types = frozenset(policies["action_types"])
        self.slug_pattern = re.compile(str(policies["slug_pattern"]))

    def visit(self, depth: int) -> None:
        self.nodes += 1
        if self.nodes > self.max_nodes:
            raise CustomizationValidationError("rule AST exceeds node limit")
        if depth > self.max_depth:
            raise CustomizationValidationError("rule AST exceeds depth limit")
        if (time.monotonic() - self.started) * 1000 > self.max_evaluation_ms:
            raise TimeoutError("rule evaluation time limit exceeded")


def _validate_condition(node: object, budget: _EvaluationBudget, depth: int = 1) -> set[str]:
    budget.visit(depth)
    if not isinstance(node, Mapping):
        raise CustomizationValidationError("condition nodes must be objects")
    allowed_keys = {"operator", "operands", "operand", "field", "value", "values"}
    if set(node) - allowed_keys:
        raise CustomizationValidationError("condition contains unknown or dangerous keys")
    operator = node.get("operator")
    if operator not in budget.condition_operators:
        raise CustomizationValidationError("unknown rule condition operator")
    dependencies: set[str] = set()
    if operator in {"and", "or"}:
        operands = node.get("operands")
        if not isinstance(operands, list) or not operands:
            raise CustomizationValidationError(f"{operator} requires operands")
        for child in operands:
            dependencies.update(_validate_condition(child, budget, depth + 1))
    elif operator == "not":
        dependencies.update(_validate_condition(node.get("operand"), budget, depth + 1))
    else:
        field = node.get("field")
        if not isinstance(field, str) or not budget.slug_pattern.fullmatch(field):
            raise CustomizationValidationError("condition field must be a simple slug")
        dependencies.add(field)
    return dependencies


def _validate_actions(actions: object, budget: _EvaluationBudget, depth: int = 1) -> set[str]:
    if not isinstance(actions, list) or not actions:
        raise CustomizationValidationError("action_ast must be a non-empty array")
    dependencies: set[str] = set()
    for action in actions:
        budget.visit(depth)
        if not isinstance(action, Mapping):
            raise CustomizationValidationError("actions must be objects")
        if set(action) - {"type", "field", "value", "message", "code", "severity"}:
            raise CustomizationValidationError("action contains unknown or dangerous keys")
        if action.get("type") not in budget.action_types:
            raise CustomizationValidationError("unknown rule action type")
        if action.get("type") in {
            "set-derived-value",
            "set-required",
            "set-visible",
            "set-enabled",
            "emit-field-diagnostic",
        }:
            field = action.get("field")
            if not isinstance(field, str) or not budget.slug_pattern.fullmatch(field):
                raise CustomizationValidationError("action field must be a simple slug")
            dependencies.add(field)
        if action.get("type") in {"reject-with-message", "emit-field-diagnostic"}:
            _required_text(action.get("message"), "action message", maximum=budget.message_length)
    return dependencies


def _evaluate_condition(
    node: Mapping[str, object],
    record: Mapping[str, object],
    changed: frozenset[str],
    budget: _EvaluationBudget,
    diagnostics: list[dict[str, object]],
    depth: int = 1,
) -> bool:
    budget.visit(depth)
    operator = str(node["operator"])
    if operator == "and":
        result = all(_evaluate_condition(item, record, changed, budget, diagnostics, depth + 1) for item in node["operands"])  # type: ignore[arg-type]
    elif operator == "or":
        result = any(_evaluate_condition(item, record, changed, budget, diagnostics, depth + 1) for item in node["operands"])  # type: ignore[arg-type]
    elif operator == "not":
        result = not _evaluate_condition(node["operand"], record, changed, budget, diagnostics, depth + 1)  # type: ignore[arg-type]
    else:
        field = str(node["field"])
        actual = record.get(field)
        expected = node.get("value", node.get("values"))
        operations = {
            "eq": lambda: actual == expected,
            "ne": lambda: actual != expected,
            "gt": lambda: actual is not None and actual > expected,
            "gte": lambda: actual is not None and actual >= expected,
            "lt": lambda: actual is not None and actual < expected,
            "lte": lambda: actual is not None and actual <= expected,
            "in": lambda: actual in expected,
            "not_in": lambda: actual not in expected,
            "contains": lambda: expected in actual,
            "starts_with": lambda: isinstance(actual, str)
            and isinstance(expected, str)
            and actual.startswith(expected),
            "ends_with": lambda: isinstance(actual, str) and isinstance(expected, str) and actual.endswith(expected),
            "is_null": lambda: actual is None,
            "not_null": lambda: actual is not None,
            "changed": lambda: field in changed,
        }
        try:
            result = bool(operations[operator]())
        except (TypeError, ValueError):
            result = False
    diagnostics.append({"operator": operator, "matched": result})
    return result


class BusinessRuleService:
    """Immutable rule versions, lifecycle, and deterministic evaluation."""

    registry = CustomizationRegistry

    @idempotent_mutation("rule.create")
    def create_rule(self, tenant_id: UUID, *, actor_id: UUID, data: Mapping[str, object]) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = effective_configuration(tenant)
        values = _rule_data(data, tenant_id=tenant)
        contract = self.registry.resolve_resource_contract(
            tenant, values["owner_module"], values["target_resource"], values["target_contract_version"]
        )
        if values["trigger"] not in contract.rule_triggers:
            raise CustomizationValidationError("target contract does not support this trigger")
        with transaction.atomic():
            rule = BusinessRule.objects.create(
                tenant_id=tenant,
                created_by=actor,
                updated_by=actor,
                status=configuration["defaults"]["rule_status"],
                **values,
            )
            _event(tenant, "business_rule", rule.id, "rule.created", actor, status=rule.status)
        _log("create_rule", rule, actor, started)
        return rule

    def get_rule(self, tenant_id: UUID, *, rule_id: UUID) -> BusinessRule:
        value = BusinessRule.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(rule_id, "rule_id"), deleted_at__isnull=True
        ).first()
        if value is None:
            raise CustomizationNotFound("business rule not found")
        return value

    def list_rules(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "priority"
    ) -> QuerySet[BusinessRule]:
        queryset = BusinessRule.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True)
        for key, value in (filters or {}).items():
            if key not in {"owner_module", "target_resource", "trigger", "status"}:
                raise CustomizationValidationError(f"unsupported rule filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(
            _ordering(ordering, {"priority", "key", "status", "created_at", "updated_at"}, "priority"), "id"
        )

    def list_rule_versions(
        self,
        tenant_id: UUID,
        *,
        filters: Mapping[str, object] | None = None,
        ordering: str = "-version",
    ) -> QuerySet[BusinessRuleVersion]:
        queryset = BusinessRuleVersion.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("rule")
        allowed = {"rule_id", "status", "version"}
        for key, value in (filters or {}).items():
            if key not in allowed:
                raise CustomizationValidationError(f"unsupported rule version filter: {key}")
            queryset = queryset.filter(**{key: value})
        return queryset.order_by(
            _ordering(ordering, {"version", "created_at", "status"}, "version"),
            "id",
        )

    @idempotent_mutation("rule.update")
    def update_rule(
        self, tenant_id: UUID, *, rule_id: UUID, expected_lock_version: int, actor_id: UUID, data: Mapping[str, object]
    ) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        updates = _rule_data(data, tenant_id=tenant, partial=True)
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            _check_lock(rule, expected_lock_version)
            if rule.status != "draft" and {
                "key",
                "owner_module",
                "target_resource",
                "trigger",
                "target_contract_version",
            } & set(updates):
                raise CustomizationValidationError("published rule identity and trigger are immutable")
            for key, value in updates.items():
                setattr(rule, key, value)
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(update_fields=[*updates, "updated_by", "lock_version", "updated_at"])
            _event(
                tenant,
                "business_rule",
                rule.id,
                "rule.updated",
                actor,
                status=rule.status,
                lock_version=rule.lock_version,
            )
        _log("update_rule", rule, actor, started)
        return rule

    def validate_rule_version(
        self, tenant_id: UUID, *, rule_id: UUID, condition_ast: object, action_ast: object
    ) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        rule = self.get_rule(tenant, rule_id=rule_id)
        _json_size(condition_ast, "condition_ast", tenant_id=tenant)
        _json_size(action_ast, "action_ast", tenant_id=tenant)
        budget = _EvaluationBudget(tenant)
        dependencies = _validate_condition(condition_ast, budget)
        dependencies.update(_validate_actions(action_ast, budget))
        fields = set(
            CustomFieldDefinition.objects.filter(
                tenant_id=tenant,
                owner_module=rule.owner_module,
                target_resource=rule.target_resource,
                deleted_at__isnull=True,
            )
            .exclude(status="retired")
            .values_list("key", flat=True)
        )
        contract = self.registry.resolve_resource_contract(
            tenant, rule.owner_module, rule.target_resource, rule.target_contract_version
        )
        fields.update(contract.fields)
        unresolved = sorted(dependencies - fields)
        if unresolved:
            raise CustomizationValidationError("rule references unresolved fields", detail={"fields": unresolved})
        return {"valid": True, "diagnostics": [], "dependencies": sorted(dependencies), "node_count": budget.nodes}

    @idempotent_mutation("rule.version.create")
    def create_rule_version(
        self,
        tenant_id: UUID,
        *,
        rule_id: UUID,
        actor_id: UUID,
        condition_ast: object,
        action_ast: object,
        change_summary: str,
    ) -> BusinessRuleVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = effective_configuration(tenant)
        summary = _required_text(
            change_summary,
            "change_summary",
            maximum=int(configuration["limits"]["change_summary_length"]),
        )
        report = self.validate_rule_version(tenant, rule_id=rule_id, condition_ast=condition_ast, action_ast=action_ast)
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            number = (
                BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            ) + 1
            try:
                version = BusinessRuleVersion.objects.create(
                    tenant_id=tenant,
                    rule=rule,
                    version=number,
                    language_version=configuration["defaults"]["rule_language_version"],
                    condition_ast=condition_ast,
                    action_ast=action_ast,
                    dependencies=report["dependencies"],
                    content_hash=_hash(condition_ast, action_ast),
                    status=configuration["defaults"]["rule_version_status"],
                    validation_errors=[],
                    change_summary=summary,
                    created_by=actor,
                )
            except IntegrityError as exc:
                raise CustomizationValidationError("an identical rule version already exists") from exc
            _event(
                tenant,
                "business_rule_version",
                version.id,
                "rule.version_created",
                actor,
                rule_id=str(rule.id),
                version=number,
            )
        _log("create_rule_version", version, actor, started)
        return version

    @idempotent_mutation("rule.publish")
    def publish_rule_version(
        self, tenant_id: UUID, *, rule_id: UUID, version_id: UUID, transition_key: str, actor_id: UUID
    ) -> BusinessRuleVersion:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            source = _lock(
                BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id),
                _uuid(version_id, "version_id"),
                "rule version",
            )
            self.validate_rule_version(
                tenant, rule_id=rule.id, condition_ast=source.condition_ast, action_ast=source.action_ast
            )
            if source.status not in {"candidate", "published", "superseded"}:
                raise CustomizationValidationError("only a candidate or historical valid rule can be published")
            replay = PublicationRecord.objects.filter(
                tenant_id=tenant,
                aggregate_type="rule",
                aggregate_id=rule.id,
                publication_key=transition_key,
                event_type="published",
            ).first()
            if replay is not None and replay.snapshot_id != source.id:
                raise IdempotencyConflictError("publication key was already used for another rule version")
            if replay is not None:
                return source
            previous_publication = (
                PublicationRecord.objects.filter(
                    tenant_id=tenant,
                    aggregate_type="rule",
                    aggregate_id=rule.id,
                    event_type="published",
                )
                .order_by("-occurred_at", "-id")
                .first()
            )
            command = "publish_revision" if rule.status in {"published", "paused"} else "publish"
            changed = _apply_transition(RULE_STATE_MACHINE, rule, command, transition_key, actor)
            if not changed:
                raise IdempotencyConflictError("publication lifecycle evidence is inconsistent")
            now = timezone.now()
            next_version = (
                BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id).aggregate(maximum=Max("version"))[
                    "maximum"
                ]
                or 0
            ) + 1
            published_snapshot = BusinessRuleVersion.objects.create(
                tenant_id=tenant,
                rule=rule,
                version=next_version,
                language_version=source.language_version,
                condition_ast=source.condition_ast,
                action_ast=source.action_ast,
                dependencies=source.dependencies,
                content_hash=_hash(
                    source.condition_ast,
                    source.action_ast,
                    {"publication_key": transition_key, "version": next_version},
                ),
                status="published",
                validation_errors=[],
                change_summary=f"Published from version {source.version}",
                created_by=actor,
                published_at=now,
                published_by=actor,
            )
            correlation = _correlation_uuid()
            if previous_publication is not None:
                PublicationRecord.objects.create(
                    tenant_id=tenant,
                    aggregate_type="rule",
                    aggregate_id=rule.id,
                    snapshot_id=previous_publication.snapshot_id,
                    version=previous_publication.version,
                    event_type="superseded",
                    publication_key=transition_key,
                    actor_id=actor,
                    correlation_id=correlation,
                    occurred_at=now,
                )
            PublicationRecord.objects.create(
                tenant_id=tenant,
                aggregate_type="rule",
                aggregate_id=rule.id,
                snapshot_id=published_snapshot.id,
                version=published_snapshot.version,
                event_type="published",
                publication_key=transition_key,
                supersedes_snapshot_id=previous_publication.snapshot_id if previous_publication else None,
                actor_id=actor,
                correlation_id=correlation,
                occurred_at=now,
            )
            rule.published_version = published_snapshot.version
            rule.published_at = now
            rule.published_by = actor
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(
                update_fields=[
                    "status",
                    "published_version",
                    "published_at",
                    "published_by",
                    "updated_by",
                    "lock_version",
                    "updated_at",
                ]
            )
            _event(
                tenant,
                "business_rule",
                rule.id,
                "rule.published",
                actor,
                version_id=str(published_snapshot.id),
                version=published_snapshot.version,
            )
        _log("publish_rule_version", rule, actor, started)
        return published_snapshot

    @idempotent_mutation("rule.transition")
    def transition_rule(
        self, tenant_id: UUID, *, rule_id: UUID, command: str, transition_key: str, actor_id: UUID
    ) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            if not _apply_transition(RULE_STATE_MACHINE, rule, command, transition_key, actor):
                return rule
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(update_fields=["status", "updated_by", "lock_version", "updated_at"])
            _event(tenant, "business_rule", rule.id, f"rule.{command}d", actor, status=rule.status)
        _log(f"transition_rule.{command}", rule, actor, started)
        return rule

    @idempotent_mutation("rule.delete")
    def delete_rule(
        self, tenant_id: UUID, *, rule_id: UUID, expected_lock_version: int, actor_id: UUID
    ) -> BusinessRule:
        started = time.monotonic()
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        with transaction.atomic():
            rule = _lock(
                BusinessRule.objects.filter(tenant_id=tenant, deleted_at__isnull=True),
                _uuid(rule_id, "rule_id"),
                "business rule",
            )
            _check_lock(rule, expected_lock_version)
            if rule.status not in {"draft", "retired"}:
                raise CustomizationValidationError("only draft or retired rules can be deleted")
            rule.deleted_at = timezone.now()
            rule.deleted_by = actor
            rule.updated_by = actor
            rule.lock_version += 1
            rule.save(update_fields=["deleted_at", "deleted_by", "updated_by", "lock_version", "updated_at"])
            _event(tenant, "business_rule", rule.id, "rule.deleted", actor, status=rule.status)
        _log("delete_rule", rule, actor, started)
        return rule

    @idempotent_mutation("rule.evaluate")
    def evaluate(
        self,
        tenant_id: UUID,
        *,
        rule_id: UUID,
        record: Mapping[str, object],
        changed_fields: Sequence[str],
        target_record_id: UUID | None,
        actor_id: UUID,
        idempotency_key: str,
    ) -> RuleExecution:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        rule = self.get_rule(tenant, rule_id=rule_id)
        key = _required_text(
            idempotency_key,
            "idempotency_key",
            maximum=int(effective_configuration(tenant)["limits"]["idempotency_key_length"]),
        )
        fingerprint = _hash(record, sorted(changed_fields))
        existing = RuleExecution.objects.filter(tenant_id=tenant, rule_id=rule.id, idempotency_key=key).first()
        if existing is not None:
            if existing.input_fingerprint != fingerprint:
                raise EvaluationIdempotencyConflict("idempotency key was already used for different input")
            return existing
        if rule.status != "published" or rule.published_version is None:
            raise CustomizationValidationError("only published rules can be evaluated")
        version = BusinessRuleVersion.objects.filter(
            tenant_id=tenant, rule_id=rule.id, version=rule.published_version, status="published"
        ).first()
        if version is None:
            raise CustomizationNotFound("published rule version not found")
        started = time.monotonic()
        diagnostics: list[dict[str, object]] = []
        status = "failed"
        result: dict[str, object] = {}
        try:
            self.validate_rule_version(
                tenant, rule_id=rule.id, condition_ast=version.condition_ast, action_ast=version.action_ast
            )
            budget = _EvaluationBudget(tenant)
            matched = _evaluate_condition(version.condition_ast, record, frozenset(changed_fields), budget, diagnostics)
            actions = []
            if matched:
                for action in version.action_ast:
                    safe = {
                        key: action[key]
                        for key in ("type", "field", "value", "message", "code", "severity")
                        if key in action
                    }
                    actions.append(safe)
                status = "rejected" if any(item["type"] == "reject-with-message" for item in actions) else "matched"
                result = {"matched": True, "actions": actions}
            else:
                status = "not_matched"
                result = {"matched": False, "actions": []}
        except Exception as exc:
            diagnostics = [{"code": "evaluation_failed", "error_type": exc.__class__.__name__}]
            result = {"matched": False, "actions": []}
        duration = max(0, int((time.monotonic() - started) * 1000))
        correlation = _correlation_uuid()
        try:
            execution = RuleExecution.objects.create(
                tenant_id=tenant,
                rule=rule,
                rule_version=version,
                target_record_id=_uuid(target_record_id, "target_record_id") if target_record_id else None,
                trigger=rule.trigger,
                idempotency_key=key,
                status=status,
                input_fingerprint=fingerprint,
                result=result,
                diagnostics=diagnostics,
                duration_ms=duration,
                correlation_id=correlation,
                executed_by=actor,
            )
        except IntegrityError:
            existing = RuleExecution.objects.filter(tenant_id=tenant, rule_id=rule.id, idempotency_key=key).first()
            if existing is None:
                raise
            if existing.input_fingerprint != fingerprint:
                raise EvaluationIdempotencyConflict("idempotency key was already used for different input")
            return existing
        _log("evaluate_rule", execution, actor, started, outcome=status)
        return execution

    def evaluate_for_resource(
        self,
        tenant_id: UUID,
        *,
        module: str,
        resource: str,
        trigger: str,
        record: Mapping[str, object],
        changed_fields: Sequence[str],
        target_record_id: UUID | None,
        actor_id: UUID,
        idempotency_key: str,
    ) -> list[RuleExecution]:
        tenant = _uuid(tenant_id, "tenant_id")
        trigger_value = _required_text(trigger, "trigger", maximum=32)
        if trigger_value not in effective_configuration(tenant)["policies"]["rule_triggers"]:
            raise CustomizationValidationError("unsupported rule trigger")
        rules = BusinessRule.objects.filter(
            tenant_id=tenant,
            owner_module=_slug(module, "module", tenant_id=tenant),
            target_resource=_slug(resource, "resource", tenant_id=tenant),
            trigger=trigger_value,
            status="published",
            deleted_at__isnull=True,
        ).order_by("priority", "id")
        results = []
        for rule in rules:
            execution = self.evaluate(
                tenant,
                rule_id=rule.id,
                record=record,
                changed_fields=changed_fields,
                target_record_id=target_record_id,
                actor_id=actor_id,
                idempotency_key=f"{idempotency_key}:{rule.id}",
            )
            results.append(execution)
            if rule.stop_on_match and execution.status in {"matched", "rejected"}:
                break
        return results

    def list_executions(
        self, tenant_id: UUID, *, filters: Mapping[str, object] | None = None, ordering: str = "-executed_at"
    ) -> QuerySet[RuleExecution]:
        queryset = RuleExecution.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related(
            "rule", "rule_version"
        )
        mappings = {
            "rule_id": "rule_id",
            "rule_version_id": "rule_version_id",
            "target_record_id": "target_record_id",
            "status": "status",
            "correlation_id": "correlation_id",
            "executed_after": "executed_at__gte",
            "executed_before": "executed_at__lte",
        }
        for key, value in (filters or {}).items():
            if key not in mappings:
                raise CustomizationValidationError(f"unsupported execution filter: {key}")
            queryset = queryset.filter(**{mappings[key]: value})
        return queryset.order_by(_ordering(ordering, {"executed_at", "duration_ms", "status"}, "executed_at"))

    def get_execution(self, tenant_id: UUID, *, execution_id: UUID) -> RuleExecution:
        value = (
            RuleExecution.objects.filter(
                tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(execution_id, "execution_id")
            )
            .select_related("rule", "rule_version")
            .first()
        )
        if value is None:
            raise CustomizationNotFound("rule execution not found")
        return value

    def get_rule_impact(self, tenant_id: UUID, *, rule_id: UUID) -> dict[str, object]:
        tenant = _uuid(tenant_id, "tenant_id")
        rule = self.get_rule(tenant, rule_id=rule_id)
        versions = BusinessRuleVersion.objects.filter(tenant_id=tenant, rule_id=rule.id)
        executions = RuleExecution.objects.filter(tenant_id=tenant, rule_id=rule.id).count()
        dependencies = sorted(
            {str(item) for values in versions.values_list("dependencies", flat=True) for item in (values or [])}
        )
        return {
            "entity_type": "business_rule",
            "entity_id": str(rule.id),
            "version_count": versions.count(),
            "execution_count": executions,
            "field_references": dependencies,
            "dependency_count": len(dependencies) + executions,
            "blocking": rule.status == "published" or executions > 0,
            "capability_unavailable": _capability_unavailable(
                tenant,
                module=rule.owner_module,
                resource=rule.target_resource,
                version=rule.target_contract_version,
            ),
        }


def _rule_data(
    data: Mapping[str, object],
    *,
    tenant_id: UUID,
    partial: bool = False,
) -> dict[str, Any]:
    configuration = effective_configuration(tenant_id)
    limits = configuration["limits"]
    policies = configuration["policies"]
    defaults = configuration["defaults"]
    allowed = {
        "key",
        "name",
        "description",
        "owner_module",
        "target_resource",
        "target_contract_version",
        "trigger",
        "priority",
        "stop_on_match",
    }
    unknown = set(data) - allowed
    if unknown:
        raise CustomizationValidationError(f"unknown rule keys: {', '.join(sorted(unknown))}")
    result = dict(data)
    if not partial:
        result.setdefault("priority", defaults["rule_priority"])
        result.setdefault("stop_on_match", defaults["rule_stop_on_match"])
    for key in ("key", "owner_module", "target_resource"):
        if key in result:
            result[key] = _slug(result[key], key, tenant_id=tenant_id)
    if "name" in result:
        result["name"] = _required_text(result["name"], "name", maximum=int(limits["form_name_length"]))
    if "target_contract_version" in result:
        result["target_contract_version"] = _required_text(
            result["target_contract_version"],
            "target_contract_version",
            maximum=int(limits["contract_version_length"]),
        )
    if "trigger" in result and result["trigger"] not in policies["rule_triggers"]:
        raise CustomizationValidationError("unsupported rule trigger")
    if "priority" in result and (
        isinstance(result["priority"], bool)
        or not isinstance(result["priority"], int)
        or not int(limits["rule_priority_min"]) <= result["priority"] <= int(limits["rule_priority_max"])
    ):
        raise CustomizationValidationError("priority is outside the configured safe range")
    if "description" in result:
        result["description"] = str(result["description"]).strip()
    if not partial:
        missing = {"key", "name", "owner_module", "target_resource", "target_contract_version", "trigger"} - set(result)
        if missing:
            raise CustomizationValidationError(f"missing rule keys: {', '.join(sorted(missing))}")
    return result


def _state_machine_from_policy(
    *,
    name: str,
    model: type,
    states: tuple[str, ...],
    terminal_states: tuple[str, ...],
    policy_name: str,
) -> StateMachine[Any]:
    raw = default_configuration_document()["policies"][policy_name]
    if not isinstance(raw, Mapping):
        raise RuntimeError(f"Default lifecycle policy {policy_name} is invalid")
    transitions = tuple(
        Transition(command, source, target)
        for source, commands in raw.items()
        if isinstance(source, str) and isinstance(commands, Mapping)
        for command, target in commands.items()
        if isinstance(command, str) and isinstance(target, str)
    )
    return StateMachine(
        name=name,
        model=model,
        states=states,
        terminal_states=terminal_states,
        transitions=transitions,
    )


FIELD_STATE_MACHINE = _state_machine_from_policy(
    name="customization_framework.field_definition",
    model=CustomFieldDefinition,
    states=("draft", "active", "deprecated", "retired"),
    terminal_states=("retired",),
    policy_name="field_transitions",
)
FORM_STATE_MACHINE = _state_machine_from_policy(
    name="customization_framework.form",
    model=FormDefinition,
    states=("draft", "published", "archived"),
    terminal_states=("archived",),
    policy_name="form_transitions",
)
RULE_STATE_MACHINE = _state_machine_from_policy(
    name="customization_framework.rule",
    model=BusinessRule,
    states=("draft", "published", "paused", "retired"),
    terminal_states=("retired",),
    policy_name="rule_transitions",
)
for _machine in (FIELD_STATE_MACHINE, FORM_STATE_MACHINE, RULE_STATE_MACHINE):
    if _machine.name not in state_machine_registry.names():
        state_machine_registry.register(_machine.name or "", _machine)


__all__ = [
    "BusinessRuleService",
    "CustomizationConfigurationService",
    "CustomizationError",
    "CustomizationNotFound",
    "CustomizationRegistry",
    "CustomizationValidationError",
    "EvaluationIdempotencyConflict",
    "PLATFORM_CEILINGS",
    "FormService",
    "OptimisticLockConflict",
    "ResourceContract",
    "CustomFieldService",
    "default_configuration_document",
    "effective_configuration",
    "validate_configuration_document",
]
