"""Transactional authorization services and fail-closed policy evaluation."""

from __future__ import annotations

import json
import hashlib
import logging
import re
import threading
import uuid
from copy import deepcopy
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from src.core.access import PolicyEvaluation
from src.core.async_jobs.models import OutboxEvent
from src.core.resilience.http import ResilientHttpClient

from .models import (
    FieldSecurity,
    MutationReplay,
    Permission,
    PermissionSet,
    PermissionSetPermission,
    Role,
    RolePermission,
    RowSecurityRule,
    SecurityAuditLog,
    SecurityConfiguration,
    SecurityConfigurationVersion,
    SecurityProfile,
    SecurityProfileAssignment,
    UserPermissionSet,
    UserRole,
)
from .predicates import compile_predicate, predicate_matches, validate_predicate
from .validators import redact_sensitive

logger = logging.getLogger("saraise.security_access_control")
SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
PERMISSION_CODE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<module>[a-z][a-z0-9_-]{0,99})\.(?P<resource>[a-z][a-z0-9_-]{0,99}):(?P<action>[a-z][a-z0-9_-]{0,49})$"
)
POLICY_DEPENDENCY = "policy-engine"


def default_security_configuration() -> dict[str, object]:
    """Return the defensible seed copied into each tenant's persisted configuration."""

    return {
        "limits": {
            "rate_requests_per_minute": 240,
            "correlation_id_max_length": 128,
            "correlation_id_pattern": r"^[A-Za-z0-9._:-]+$",
            "role_hierarchy_max_depth": 16,
            "permission_set_duration_min_days": 1,
            "permission_set_duration_max_days": 365,
            "profile_idle_timeout_min_minutes": 5,
            "profile_idle_timeout_max_minutes": 1440,
            "profile_absolute_timeout_min_hours": 1,
            "profile_absolute_timeout_max_hours": 168,
            "profile_concurrent_sessions_min": 1,
            "profile_concurrent_sessions_max": 100,
            "predicate_max_depth": 8,
            "predicate_max_nodes": 64,
            "predicate_max_in_values": 100,
            "predicate_hard_max_depth": 16,
            "predicate_hard_max_nodes": 256,
            "predicate_hard_max_in_values": 500,
            "predicate_compound_max_arguments": 20,
            "audit_payload_max_bytes": 16384,
            "policy_array_max_entries": 100,
            "mfa_methods_max_entries": 20,
            "audit_redaction_max_depth": 8,
            "audit_collection_max_entries": 100,
            "audit_string_max_length": 2000,
            "required_text_max_length": 2000,
            "audit_reason_codes_max_entries": 32,
            "user_agent_max_length": 512,
            "audit_default_window_days": 30,
            "audit_max_window_days": 90,
            "row_priority_min": -32768,
            "row_priority_max": 32767,
            "name_min_length": 2,
            "name_max_length": 255,
            "description_max_length": 4000,
            "list_page_size": 25,
            "lookup_page_size": 100,
        },
        "defaults": {
            "field_visibility": "visible",
            "field_edit_control": "editable",
            "row_rule_type": "ownership",
            "row_rule_priority": 0,
            "row_owner_field": "owner_id",
            "profile_assignment_precedence": 0,
            "security_profile": {
                "profile_type": "standard",
                "mfa_required": "conditional",
                "allowed_mfa_methods": ["totp", "webauthn"],
                "time_restrictions": {
                    "timezone": "UTC",
                    "weekdays": [1, 2, 3, 4, 5],
                    "windows": [{"start": "09:00", "end": "17:00"}],
                },
                "session_timeout_minutes": 60,
                "absolute_session_timeout_hours": 8,
                "max_concurrent_sessions": 5,
                "download_allowed": True,
                "print_allowed": True,
                "copy_paste_allowed": True,
                "mobile_access_allowed": True,
                "login_notification": False,
                "access_notification": False,
            },
            "automatic_revocation_reason": "Superseded by renewal",
            "mfa_precedence": {"never": 0, "sensitive_actions": 1, "conditional": 2, "always": 3},
            "allowed_mfa_methods": ["totp", "webauthn", "push", "sms", "email", "recovery_code"],
        },
        "ordering": {
            "roles": ["name"],
            "role_assignments": ["-valid_from"],
            "permission_sets": ["name"],
            "permission_set_grants": ["-granted_at"],
            "field_rules": ["module", "resource", "field"],
            "row_rules": ["-priority", "module", "resource"],
            "security_profiles": ["name"],
            "profile_assignments": ["-precedence", "-valid_from"],
            "audit_logs": ["-timestamp"],
        },
        "resilience": {
            "connect_timeout_seconds": 1.0,
            "read_timeout_seconds": 2.0,
            "max_retries": 2,
            "failure_threshold": 3,
            "reset_timeout_seconds": 30.0,
        },
        "remote_context_keys": [
            "record_id", "resource_id", "module", "resource", "owner_id",
            "classification", "country", "requested_fields",
        ],
        "ui": {"loading_skeleton_rows": 6, "audit_timeline_page_size": 10},
        "semantic_tokens": {
            "success": "status-success", "danger": "status-danger",
            "warning": "status-warning", "neutral": "status-neutral",
        },
        "commercial_controls": {"entitlement": "not_required", "quota": "not_required"},
        "baseline_profile": {
            "mfa_required": "always",
            "allowed_mfa_methods": ["totp", "webauthn"],
            "session_timeout_minutes": 15,
            "absolute_session_timeout_hours": 4,
            "max_concurrent_sessions": 1,
            "download_allowed": False,
            "print_allowed": False,
            "copy_paste_allowed": False,
            "mobile_access_allowed": False,
            "ip_whitelist": [], "ip_blacklist": [], "allowed_countries": [], "blocked_countries": [],
        },
        "feature_flags": {"configuration_ui": {"enabled": True, "percentage": 100, "roles": [], "cohorts": []}},
    }


DEFAULT_ROLLOUT: Mapping[str, object] = {
    "enabled": True,
    "percentage": 100,
    "role_ids": [],
    "cohorts": [],
}


class SecurityServiceError(RuntimeError):
    """Base public domain error with a stable code."""

    code = "SECURITY_OPERATION_FAILED"


class SecurityNotFound(SecurityServiceError):
    code = "RESOURCE_NOT_FOUND"


class SecurityConflict(SecurityServiceError):
    code = "CONFLICT"


class SecurityValidationError(SecurityServiceError):
    code = "VALIDATION_ERROR"

    def __init__(self, message: str, *, detail: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.detail = dict(detail or {})


class SecurityConfigurationMissing(SecurityServiceError):
    """Raised when an authorization control has no valid tenant configuration."""

    code = "SECURITY_CONFIGURATION_MISSING"


class SecurityDependencyUnavailable(SecurityServiceError):
    """Raised instead of fabricating an authorization integration result."""

    code = "SECURITY_DEPENDENCY_UNAVAILABLE"


class ConfigurationService:
    """Validate, version, import, export, preview, and roll back tenant configuration."""

    ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})
    ROOT_KEYS = frozenset(
        {
            "limits", "defaults", "ordering", "resilience", "remote_context_keys", "ui",
            "semantic_tokens", "commercial_controls", "baseline_profile", "feature_flags",
        }
    )
    ORDERING_ALLOWED: Mapping[str, frozenset[str]] = {
        "roles": frozenset({"name", "created_at", "updated_at"}),
        "role_assignments": frozenset({"valid_from", "created_at"}),
        "permission_sets": frozenset({"name", "created_at"}),
        "permission_set_grants": frozenset({"granted_at", "expires_at", "created_at"}),
        "field_rules": frozenset({"module", "resource", "field", "created_at"}),
        "row_rules": frozenset({"priority", "module", "resource", "created_at"}),
        "security_profiles": frozenset({"name", "created_at", "updated_at"}),
        "profile_assignments": frozenset({"precedence", "valid_from", "created_at"}),
        "audit_logs": frozenset({"timestamp", "action", "decision"}),
    }

    @staticmethod
    def _integer(mapping: Mapping[str, object], key: str, minimum: int, maximum: int) -> int:
        value = mapping.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise SecurityValidationError(
                "Invalid security configuration", detail={f"limits.{key}": [f"Must be {minimum}..{maximum}."]}
            )
        return value

    @classmethod
    def validate_document(cls, document: object) -> dict[str, object]:
        if not isinstance(document, Mapping) or set(document) != cls.ROOT_KEYS:
            raise SecurityValidationError(
                "Invalid security configuration",
                detail={"document": ["Configuration must contain exactly the governed top-level sections."]},
            )
        normalized = deepcopy(dict(document))
        limits = normalized["limits"]
        defaults = normalized["defaults"]
        resilience = normalized["resilience"]
        baseline = normalized["baseline_profile"]
        if not all(isinstance(value, Mapping) for value in (limits, defaults, resilience, baseline)):
            raise SecurityValidationError("Invalid security configuration", detail={"document": ["Invalid section."]})
        assert isinstance(limits, Mapping) and isinstance(defaults, Mapping)
        assert isinstance(resilience, Mapping) and isinstance(baseline, Mapping)
        bounded = {
            "rate_requests_per_minute": (1, 10000), "correlation_id_max_length": (32, 256),
            "role_hierarchy_max_depth": (1, 64), "permission_set_duration_min_days": (1, 3650),
            "permission_set_duration_max_days": (1, 3650), "profile_idle_timeout_min_minutes": (1, 1440),
            "profile_idle_timeout_max_minutes": (1, 10080), "profile_absolute_timeout_min_hours": (1, 168),
            "profile_absolute_timeout_max_hours": (1, 744), "profile_concurrent_sessions_min": (1, 100),
            "profile_concurrent_sessions_max": (1, 1000), "predicate_max_depth": (1, 16),
            "predicate_max_nodes": (1, 256), "predicate_max_in_values": (1, 500),
            "predicate_hard_max_depth": (1, 32), "predicate_hard_max_nodes": (1, 1024),
            "predicate_hard_max_in_values": (1, 2000), "predicate_compound_max_arguments": (1, 100),
            "audit_payload_max_bytes": (1024, 1048576), "policy_array_max_entries": (1, 1000),
            "mfa_methods_max_entries": (1, 50), "audit_redaction_max_depth": (1, 32),
            "audit_collection_max_entries": (1, 1000), "audit_string_max_length": (128, 10000),
            "required_text_max_length": (128, 10000), "audit_reason_codes_max_entries": (1, 100),
            "user_agent_max_length": (64, 4096), "audit_default_window_days": (1, 365),
            "audit_max_window_days": (1, 3650), "row_priority_min": (-32768, 0),
            "row_priority_max": (0, 32767), "name_min_length": (1, 255),
            "name_max_length": (1, 512), "description_max_length": (1, 20000),
            "list_page_size": (1, 100), "lookup_page_size": (1, 500),
        }
        for key, bounds in bounded.items():
            cls._integer(limits, key, *bounds)
        pairs = (
            ("permission_set_duration_min_days", "permission_set_duration_max_days"),
            ("profile_idle_timeout_min_minutes", "profile_idle_timeout_max_minutes"),
            ("profile_absolute_timeout_min_hours", "profile_absolute_timeout_max_hours"),
            ("profile_concurrent_sessions_min", "profile_concurrent_sessions_max"),
            ("audit_default_window_days", "audit_max_window_days"),
            ("row_priority_min", "row_priority_max"), ("name_min_length", "name_max_length"),
        )
        for lower, upper in pairs:
            if int(limits[lower]) > int(limits[upper]):
                raise SecurityValidationError(
                    "Invalid security configuration", detail={f"limits.{lower}": [f"Must not exceed {upper}."]}
                )
        pattern = limits.get("correlation_id_pattern")
        try:
            if not isinstance(pattern, str) or re.compile(pattern).groups:
                raise ValueError
        except (re.error, ValueError) as exc:
            raise SecurityValidationError(
                "Invalid security configuration", detail={"limits.correlation_id_pattern": ["Invalid safe regex."]}
            ) from exc
        allowed_mfa = defaults.get("allowed_mfa_methods")
        profile_defaults = defaults.get("security_profile")
        if not isinstance(allowed_mfa, list) or not allowed_mfa or not all(isinstance(v, str) for v in allowed_mfa):
            raise SecurityValidationError("Invalid security configuration", detail={"defaults.allowed_mfa_methods": ["Required allow-list."]})
        if len(set(allowed_mfa)) != len(allowed_mfa) or len(allowed_mfa) > int(limits["mfa_methods_max_entries"]):
            raise SecurityValidationError("Invalid security configuration", detail={"defaults.allowed_mfa_methods": ["Duplicate or excessive values."]})
        if not isinstance(profile_defaults, Mapping):
            raise SecurityValidationError("Invalid security configuration", detail={"defaults.security_profile": ["Required."]})
        cls._validate_profile(profile_defaults, limits, frozenset(allowed_mfa), "defaults.security_profile")
        cls._validate_profile(baseline, limits, frozenset(allowed_mfa), "baseline_profile")
        if baseline.get("mfa_required") != "always" or any(
            baseline.get(flag) is not False
            for flag in ("download_allowed", "print_allowed", "copy_paste_allowed", "mobile_access_allowed")
        ):
            raise SecurityValidationError(
                "Invalid security configuration",
                detail={"baseline_profile": ["The mandatory baseline must require MFA and deny data egress."]},
            )
        for key in ("connect_timeout_seconds", "read_timeout_seconds", "reset_timeout_seconds"):
            value = resilience.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.05 <= float(value) <= 300:
                raise SecurityValidationError("Invalid security configuration", detail={f"resilience.{key}": ["Out of safe bounds."]})
        cls._integer(resilience, "max_retries", 1, 8)
        cls._integer(resilience, "failure_threshold", 1, 20)
        context_keys = normalized["remote_context_keys"]
        if not isinstance(context_keys, list) or not context_keys or len(context_keys) > 64 or not all(
            isinstance(value, str) and SLUG_RE.fullmatch(value) for value in context_keys
        ):
            raise SecurityValidationError("Invalid security configuration", detail={"remote_context_keys": ["Invalid allow-list."]})
        controls = normalized["commercial_controls"]
        if not isinstance(controls, Mapping) or controls.get("entitlement") not in {"not_required", "required"} or controls.get("quota") not in {"not_required", "required"}:
            raise SecurityValidationError("Invalid security configuration", detail={"commercial_controls": ["Invalid modes."]})
        ordering = normalized["ordering"]
        if not isinstance(ordering, Mapping) or set(ordering) != set(cls.ORDERING_ALLOWED):
            raise SecurityValidationError("Invalid security configuration", detail={"ordering": ["Incomplete ordering policy."]})
        for resource, allowed in cls.ORDERING_ALLOWED.items():
            values = ordering.get(resource)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or value.removeprefix("-") not in allowed for value in values
            ):
                raise SecurityValidationError(
                    "Invalid security configuration", detail={f"ordering.{resource}": ["Unsupported ordering."]}
                )
        ui = normalized["ui"]
        if not isinstance(ui, Mapping):
            raise SecurityValidationError("Invalid security configuration", detail={"ui": ["Required."]})
        cls._integer(ui, "loading_skeleton_rows", 1, 20)
        cls._integer(ui, "audit_timeline_page_size", 1, 100)
        tokens = normalized["semantic_tokens"]
        if not isinstance(tokens, Mapping) or set(tokens) != {"success", "danger", "warning", "neutral"} or any(
            not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", value)
            for value in tokens.values()
        ):
            raise SecurityValidationError("Invalid security configuration", detail={"semantic_tokens": ["Invalid token map."]})
        flags = normalized["feature_flags"]
        if not isinstance(flags, Mapping) or not flags:
            raise SecurityValidationError("Invalid security configuration", detail={"feature_flags": ["At least one flag is required."]})
        for name, flag in flags.items():
            if not isinstance(name, str) or not SLUG_RE.fullmatch(name) or not isinstance(flag, Mapping):
                raise SecurityValidationError("Invalid security configuration", detail={"feature_flags": ["Invalid flag."]})
            if set(flag) != {"enabled", "percentage", "roles", "cohorts"}:
                raise SecurityValidationError("Invalid security configuration", detail={f"feature_flags.{name}": ["Invalid shape."]})
            percentage = flag.get("percentage")
            if not isinstance(flag.get("enabled"), bool) or isinstance(percentage, bool) or not isinstance(percentage, int) or not 0 <= percentage <= 100:
                raise SecurityValidationError("Invalid security configuration", detail={f"feature_flags.{name}": ["Invalid rollout."]})
            if any(not isinstance(flag.get(key), list) or len(flag[key]) > 100 for key in ("roles", "cohorts")):
                raise SecurityValidationError("Invalid security configuration", detail={f"feature_flags.{name}": ["Invalid targets."]})
        return normalized

    @staticmethod
    def _validate_profile(
        profile: Mapping[str, object], limits: Mapping[str, object], allowed_mfa: frozenset[str], path: str
    ) -> None:
        checks = (
            ("session_timeout_minutes", "profile_idle_timeout_min_minutes", "profile_idle_timeout_max_minutes"),
            ("absolute_session_timeout_hours", "profile_absolute_timeout_min_hours", "profile_absolute_timeout_max_hours"),
            ("max_concurrent_sessions", "profile_concurrent_sessions_min", "profile_concurrent_sessions_max"),
        )
        for key, low, high in checks:
            value = profile.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or not int(limits[low]) <= value <= int(limits[high]):
                raise SecurityValidationError("Invalid security configuration", detail={f"{path}.{key}": ["Out of configured bounds."]})
        methods = profile.get("allowed_mfa_methods")
        if not isinstance(methods, list) or not methods or not set(methods) <= allowed_mfa:
            raise SecurityValidationError("Invalid security configuration", detail={f"{path}.allowed_mfa_methods": ["Outside allow-list."]})
        if profile.get("mfa_required") not in {"always", "conditional", "sensitive_actions", "never"}:
            raise SecurityValidationError("Invalid security configuration", detail={f"{path}.mfa_required": ["Invalid value."]})

    @staticmethod
    def validate_rollout(rollout: object) -> dict[str, object]:
        if not isinstance(rollout, Mapping) or set(rollout) != {"enabled", "percentage", "role_ids", "cohorts"}:
            raise SecurityValidationError("Invalid rollout", detail={"rollout": ["Invalid rollout document."]})
        percentage = rollout.get("percentage")
        if not isinstance(rollout.get("enabled"), bool) or isinstance(percentage, bool) or not isinstance(percentage, int) or not 0 <= percentage <= 100:
            raise SecurityValidationError("Invalid rollout", detail={"rollout.percentage": ["Must be 0..100."]})
        for key in ("role_ids", "cohorts"):
            values = rollout.get(key)
            if not isinstance(values, list) or len(values) > 100 or not all(isinstance(value, str) and value for value in values):
                raise SecurityValidationError("Invalid rollout", detail={f"rollout.{key}": ["Invalid allow-list."]})
        return deepcopy(dict(rollout))

    @classmethod
    @transaction.atomic
    def current(
        cls, tenant_id: UUID, *, actor_id: UUID, correlation_id: str, environment: str | None = None
    ) -> SecurityConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        current = SecurityConfiguration.objects.select_for_update().for_tenant(tenant).first()
        if current is not None:
            cls.validate_document(current.document)
            cls.validate_rollout(current.rollout)
            return current
        env = str(environment or getattr(settings, "SARAISE_ENVIRONMENT", "development")).lower()
        if env not in cls.ENVIRONMENTS:
            raise SecurityConfigurationMissing("A valid tenant security environment is required")
        document = cls.validate_document(default_security_configuration())
        rollout = cls.validate_rollout(DEFAULT_ROLLOUT)
        current = SecurityConfiguration(
            tenant_id=tenant, environment=env, version=1, document=document, rollout=rollout,
            updated_by=actor, correlation_id=correlation_id,
        )
        current.save(force_insert=True)
        SecurityConfigurationVersion.objects.create(
            tenant_id=tenant, version=1, environment=env, previous_document=None, current_document=document,
            previous_rollout=None, current_rollout=rollout, actor_id=actor, correlation_id=correlation_id,
            reason="Initial governed tenant configuration", change_kind="bootstrap",
        )
        _security_event(
            tenant,
            event_type="security.configuration.changed",
            aggregate_type="security_configuration",
            aggregate_id=current.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "bootstrap", "version": 1},
        )
        return current

    @classmethod
    def require_existing(cls, tenant_id: UUID) -> SecurityConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        current = SecurityConfiguration.objects.for_tenant(tenant).first()
        if current is None:
            raise SecurityConfigurationMissing("Tenant security configuration is required")
        cls.validate_document(current.document)
        cls.validate_rollout(current.rollout)
        return current

    @staticmethod
    def _diff(previous: Mapping[str, object], current: Mapping[str, object], prefix: str = "") -> list[dict[str, object]]:
        changes: list[dict[str, object]] = []
        for key in sorted(set(previous) | set(current)):
            path = f"{prefix}.{key}" if prefix else key
            before, after = previous.get(key), current.get(key)
            if isinstance(before, Mapping) and isinstance(after, Mapping):
                changes.extend(ConfigurationService._diff(before, after, path))
            elif before != after:
                changes.append({"path": path, "before": before, "after": after})
        return changes

    @classmethod
    def preview(cls, current: SecurityConfiguration, *, document: object, rollout: object | None = None) -> dict[str, object]:
        normalized_document = cls.validate_document(document)
        normalized_rollout = cls.validate_rollout(current.rollout if rollout is None else rollout)
        return {
            "valid": True,
            "diff": cls._diff(current.document, normalized_document) + cls._diff(current.rollout, normalized_rollout, "rollout"),
            "normalized_document": normalized_document,
            "normalized_rollout": normalized_rollout,
        }

    @classmethod
    @transaction.atomic
    def replace(
        cls, tenant_id: UUID, *, document: object, environment: str, rollout: object | None, actor_id: UUID,
        correlation_id: str, reason: str, change_kind: str = "update",
    ) -> SecurityConfiguration:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        current = cls.current(tenant, actor_id=actor, correlation_id=correlation_id, environment=environment)
        current = SecurityConfiguration.objects.select_for_update().get(pk=current.pk)
        if environment not in cls.ENVIRONMENTS:
            raise SecurityValidationError("Invalid environment", detail={"environment": ["Unsupported value."]})
        normalized_document = cls.validate_document(document)
        normalized_rollout = cls.validate_rollout(current.rollout if rollout is None else rollout)
        previous_document, previous_rollout = deepcopy(current.document), deepcopy(current.rollout)
        current.version += 1
        current.environment, current.document, current.rollout = environment, normalized_document, normalized_rollout
        current.updated_by, current.correlation_id = actor, correlation_id
        current.save()
        SecurityConfigurationVersion.objects.create(
            tenant_id=tenant, version=current.version, environment=environment,
            previous_document=previous_document, current_document=normalized_document,
            previous_rollout=previous_rollout, current_rollout=normalized_rollout,
            actor_id=actor, correlation_id=correlation_id, reason=_required_text(reason, "reason"),
            change_kind=change_kind,
        )
        _security_event(
            tenant,
            event_type="security.configuration.changed",
            aggregate_type="security_configuration",
            aggregate_id=current.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": change_kind, "version": current.version},
        )
        return current

    @classmethod
    def update_rollout(cls, tenant_id: UUID, *, rollout: object, actor_id: UUID, correlation_id: str, reason: str) -> SecurityConfiguration:
        current = cls.require_existing(tenant_id)
        return cls.replace(
            tenant_id, document=current.document, environment=current.environment, rollout=rollout,
            actor_id=actor_id, correlation_id=correlation_id, reason=reason, change_kind="rollout",
        )

    @classmethod
    def rollback(
        cls, tenant_id: UUID, version: int, *, actor_id: UUID, correlation_id: str, reason: str
    ) -> SecurityConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        target = SecurityConfigurationVersion.objects.for_tenant(tenant).filter(version=version).first()
        if target is None:
            raise SecurityNotFound("Configuration version was not found")
        return cls.replace(
            tenant, document=target.current_document, environment=target.environment, rollout=target.current_rollout,
            actor_id=actor_id, correlation_id=correlation_id, reason=reason, change_kind="rollback",
        )

    @staticmethod
    def export_document(current: SecurityConfiguration) -> dict[str, object]:
        return {
            "schema_version": "1.0", "environment": current.environment, "version": current.version,
            "document": deepcopy(current.document), "rollout": deepcopy(current.rollout),
        }


class MutationReplayService:
    """Execute a mutation and persist its response atomically for safe retries."""

    @staticmethod
    @transaction.atomic
    def execute(
        tenant_id: UUID,
        *,
        idempotency_key: str,
        operation: str,
        request_document: Mapping[str, object],
        correlation_id: str,
        callback: Any,
    ) -> tuple[dict[str, object], int, bool]:
        tenant = _uuid(tenant_id, "tenant_id")
        key = str(idempotency_key).strip()
        if not key or len(key) > 128 or not re.fullmatch(r"[A-Za-z0-9._:-]+", key):
            raise SecurityValidationError(
                "A valid Idempotency-Key is required", detail={"idempotency_key": ["Required for mutations."]}
            )
        encoded = json.dumps(request_document, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        request_hash = hashlib.sha256(operation.encode("utf-8") + b"\0" + encoded).hexdigest()
        replay = MutationReplay.objects.select_for_update().for_tenant(tenant).filter(idempotency_key=key).first()
        if replay is not None:
            if replay.request_hash != request_hash or replay.operation != operation:
                raise SecurityConflict("Idempotency-Key was already used for a different mutation")
            return deepcopy(replay.response_document), replay.response_status, True
        response_document, response_status, resource_id = callback()
        MutationReplay.objects.create(
            tenant_id=tenant, idempotency_key=key, request_hash=request_hash, operation=operation,
            resource_id=resource_id, response_status=response_status, response_document=response_document,
            correlation_id=correlation_id,
        )
        return deepcopy(response_document), response_status, False


@dataclass(frozen=True, slots=True)
class EffectivePermissionSet:
    allowed: frozenset[str]
    denied: frozenset[str]
    role_ids: tuple[str, ...]
    permission_set_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FieldAccessDecision:
    field: str
    visibility: str
    edit_control: str
    mask_pattern: str
    applied_rule_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RowAccessExplanation:
    allowed: bool
    applied_rule_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EffectiveSecurityProfile:
    profile_ids: tuple[str, ...]
    precedence: int | None
    restrictions: Mapping[str, object]
    enforcement: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AccessDecisionResult:
    allowed: bool
    subject_id: str
    permission_code: str
    reason_codes: tuple[str, ...]
    applied_policy_ids: tuple[str, ...]
    entitlement: Mapping[str, object]
    quota: Mapping[str, object]
    field_decisions: tuple[Mapping[str, object], ...]
    row_explanation: Mapping[str, object]
    profile: Mapping[str, object]
    audit_id: str | None = None
    correlation_id: str = ""
    evaluated_at: datetime | None = None


def _uuid(value: UUID | str, field: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise SecurityValidationError(f"{field} must be a UUID", detail={field: ["Invalid UUID."]}) from exc


def _actor_uuid(value: object) -> UUID:
    """Normalize native user primary keys into the immutable UUID evidence contract."""

    try:
        return _uuid(str(value), "actor_id")
    except SecurityValidationError:
        if value is None or not str(value):
            raise SecurityValidationError("actor_id is required")
        return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


def _slug(value: object, field: str) -> str:
    normalized = str(value).strip().lower().replace(" ", "_")
    if not SLUG_RE.fullmatch(normalized):
        raise SecurityValidationError(f"{field} is invalid", detail={field: ["Use a lowercase slug."]})
    return normalized


def _required_text(value: object, field: str, maximum: int | None = None) -> str:
    if maximum is None:
        limits = default_security_configuration()["limits"]
        if not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Required-text validation configuration is unavailable")
        maximum = int(limits["required_text_max_length"])
    normalized = str(value).strip()
    if not normalized or len(normalized) > maximum:
        raise SecurityValidationError(
            f"{field} is required", detail={field: [f"Must contain 1 to {maximum} characters."]}
        )
    return normalized


def _model_validation(instance: Any) -> None:
    try:
        instance.full_clean()
    except ValidationError as exc:
        raise SecurityValidationError(
            "Domain validation failed", detail=getattr(exc, "message_dict", {"non_field_errors": exc.messages})
        ) from exc


def _tenant_user(tenant_id: UUID, user_id: UUID | str) -> Any:
    user = get_user_model().objects.filter(id=user_id).first()
    profile_tenant = getattr(getattr(user, "profile", None), "tenant_id", None) if user is not None else None
    if user is None or str(profile_tenant) != str(tenant_id):
        raise SecurityNotFound("User is not a member of this tenant")
    return user


def _role(tenant_id: UUID, role_id: UUID | str, *, lock: bool = False) -> Role:
    queryset = Role.objects.for_tenant(tenant_id).filter(id=role_id, is_deleted=False)
    if lock:
        queryset = queryset.select_for_update()
    role = queryset.first()
    if role is None:
        raise SecurityNotFound("Role was not found")
    return role


def _permission_set(tenant_id: UUID, permission_set_id: UUID | str, *, lock: bool = False) -> PermissionSet:
    queryset = PermissionSet.objects.for_tenant(tenant_id).filter(id=permission_set_id, is_deleted=False)
    if lock:
        queryset = queryset.select_for_update()
    item = queryset.first()
    if item is None:
        raise SecurityNotFound("Permission set was not found")
    return item


def _resource_fields(module: str, resource: str) -> tuple[str, ...]:
    """Resolve extension metadata without coupling paid modules to ORM models."""

    try:
        from .extensions import get_resource_descriptor

        descriptor = get_resource_descriptor(module, resource)
    except (ImportError, LookupError, ValueError) as exc:
        raise SecurityValidationError(
            "Resource security metadata is not registered",
            detail={"resource": [f"No active descriptor for {module}.{resource}."]},
        ) from exc
    fields = getattr(descriptor, "fields", ())
    names = tuple(str(getattr(item, "name", item)) for item in fields)
    if not names:
        raise SecurityValidationError("Resource descriptor contains no policy fields")
    return names


def _security_event(
    tenant_id: UUID,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    actor_id: UUID,
    correlation_id: str,
    payload: Mapping[str, object] | None = None,
) -> tuple[OutboxEvent, SecurityAuditLog]:
    evidence = AuditService.append_with_outbox(
        tenant_id,
        action=event_type,
        actor_type=SecurityAuditLog.ActorType.USER,
        actor_id=actor_id,
        resource_type=aggregate_type,
        resource_id=aggregate_id,
        decision=None,
        reason_codes=("CONFIGURATION_CHANGED",),
        details=payload or {},
        ip_address=None,
        user_agent="",
        correlation_id=correlation_id,
    )
    logger.info(
        event_type,
        extra={
            "correlation_id": correlation_id,
            "tenant_id": str(tenant_id),
            "actor_id": str(actor_id),
            "resource_type": aggregate_type,
            "resource_id": str(aggregate_id),
            "action": event_type,
            "decision": None,
            "reason_codes": ["CONFIGURATION_CHANGED"],
            "latency_ms": 0,
        },
    )
    return evidence


class AuditService:
    """Only supported append path for immutable security evidence."""

    @staticmethod
    def append(
        tenant_id: UUID,
        *,
        action: str,
        actor_type: str,
        actor_id: UUID,
        resource_type: str,
        resource_id: UUID | None,
        decision: str | None,
        reason_codes: Sequence[str],
        details: Mapping[str, object],
        ip_address: str | None,
        user_agent: str,
        correlation_id: str,
        outbox_event_id: UUID | None = None,
    ) -> SecurityAuditLog:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        limits = configuration.document.get("limits")
        if not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Audit safety limits are required")
        codes = tuple(_required_text(item, "reason_code", 100) for item in reason_codes)
        max_codes = int(limits["audit_reason_codes_max_entries"])
        max_bytes = int(limits["audit_payload_max_bytes"])
        if len(codes) > max_codes:
            raise SecurityValidationError(f"At most {max_codes} reason codes are allowed")
        if len(json.dumps(details, separators=(",", ":"), default=str).encode()) > max_bytes:
            raise SecurityValidationError(f"Audit details exceed {max_bytes} bytes")
        safe_details = redact_sensitive(
            details,
            max_depth=int(limits["audit_redaction_max_depth"]),
            max_collection=int(limits["audit_collection_max_entries"]),
            max_string=int(limits["audit_string_max_length"]),
        )
        record = SecurityAuditLog(
            tenant_id=tenant,
            action=_required_text(action, "action", 100),
            actor_type=actor_type,
            actor_id=actor,
            resource_type=_required_text(resource_type, "resource_type", 100),
            resource_id=resource_id,
            decision=decision,
            reason_codes=list(codes),
            details=safe_details,
            ip_address=ip_address,
            user_agent=str(user_agent)[: int(limits["user_agent_max_length"])],
            correlation_id=_required_text(correlation_id, "correlation_id", int(limits["correlation_id_max_length"])),
            outbox_event_id=outbox_event_id,
        )
        _model_validation(record)
        record.save(force_insert=True)
        return record

    @classmethod
    def append_with_outbox(cls, tenant_id: UUID, **kwargs: Any) -> tuple[OutboxEvent, SecurityAuditLog]:
        tenant = _uuid(tenant_id, "tenant_id")
        resource_id = kwargs.get("resource_id") or uuid.uuid4()
        with transaction.atomic():
            event = OutboxEvent.objects.create(
                tenant_id=tenant,
                aggregate_type=str(kwargs["resource_type"]),
                aggregate_id=resource_id,
                event_type=str(kwargs["action"]),
                payload={
                    "schema_version": 1,
                    "resource_type": str(kwargs["resource_type"]),
                    "resource_id": str(resource_id),
                    "actor_id": str(kwargs["actor_id"]),
                    "correlation_id": str(kwargs["correlation_id"]),
                    "reason_codes": list(kwargs.get("reason_codes", ())),
                },
            )
            audit = cls.append(tenant, outbox_event_id=event.id, **kwargs)
            return event, audit


class RoleService:
    """Role hierarchy, explicit decisions, and temporal role assignments."""

    @staticmethod
    @transaction.atomic
    def create_role(
        tenant_id: UUID,
        *,
        name: str,
        code: str,
        role_type: str,
        description: str = "",
        parent_role_id: UUID | None = None,
        actor_id: UUID,
        correlation_id: str,
    ) -> Role:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        parent = _role(tenant, parent_role_id, lock=True) if parent_role_id else None
        normalized_code = _slug(code, "code").replace("-", "_")
        if Role.objects.for_tenant(tenant).filter(code=normalized_code, is_deleted=False).exists():
            raise SecurityConflict("An active role with this code already exists")
        role = Role(
            tenant_id=tenant,
            name=_required_text(name, "name", 255),
            code=normalized_code,
            role_type=role_type,
            description=str(description).strip(),
            parent_role=parent,
            hierarchy_level=(parent.hierarchy_level + 1 if parent else 0),
            created_by=actor,
            updated_by=actor,
        )
        _model_validation(role)
        try:
            role.save(force_insert=True)
        except IntegrityError as exc:
            raise SecurityConflict("An active role with this code already exists") from exc
        _security_event(
            tenant,
            event_type="security.role.changed",
            aggregate_type="role",
            aggregate_id=role.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "create", "code": role.code},
        )
        return role

    @staticmethod
    @transaction.atomic
    def update_role(
        tenant_id: UUID,
        role_id: UUID,
        *,
        changes: Mapping[str, object],
        actor_id: UUID,
        correlation_id: str,
    ) -> Role:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        limits = configuration.document["limits"]
        if not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Role hierarchy limits are required")
        maximum_depth = int(limits["role_hierarchy_max_depth"])
        role = _role(tenant, role_id, lock=True)
        allowed = {"name", "code", "description", "role_type", "parent_role_id", "is_active"}
        if set(changes) - allowed:
            raise SecurityValidationError(
                "Unsupported role changes", detail={"changes": ["Contains protected fields."]}
            )
        if role.is_system and any(key in changes for key in ("code", "role_type")):
            raise SecurityConflict("System role code and type are protected")
        if "code" in changes:
            changed_code = _slug(changes["code"], "code").replace("-", "_")
            if Role.objects.for_tenant(tenant).filter(code=changed_code, is_deleted=False).exclude(id=role.id).exists():
                raise SecurityConflict("An active role with this code already exists")
        before = {key: str(getattr(role, key, "")) for key in allowed if key in changes}
        if "parent_role_id" in changes:
            parent_id = changes["parent_role_id"]
            parent = _role(tenant, parent_id, lock=True) if parent_id else None
            role.parent_role = parent
            role.hierarchy_level = parent.hierarchy_level + 1 if parent else 0
        for key in allowed - {"parent_role_id"}:
            if key in changes:
                value = changes[key]
                if key == "code":
                    value = _slug(value, "code").replace("-", "_")
                setattr(role, key, value)
        role.updated_by = actor
        _model_validation(role)
        role.save()
        # Recalculate descendants deterministically and reject subtrees beyond the bound.
        frontier = [(role, role.hierarchy_level)]
        seen = {role.id}
        while frontier:
            parent, level = frontier.pop(0)
            children = list(
                Role.objects.select_for_update().for_tenant(tenant).filter(parent_role=parent, is_deleted=False)
            )
            for child in children:
                if child.id in seen or level + 1 > maximum_depth:
                    raise SecurityValidationError(
                        f"Role hierarchy is cyclic or exceeds {maximum_depth} levels"
                    )
                seen.add(child.id)
                child.hierarchy_level = level + 1
                child.updated_by = actor
                child.save(update_fields=("hierarchy_level", "updated_by", "updated_at"))
                frontier.append((child, child.hierarchy_level))
        _security_event(
            tenant,
            event_type="security.role.changed",
            aggregate_type="role",
            aggregate_id=role.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update", "before": before, "after": {k: str(getattr(role, k, "")) for k in before}},
        )
        return role

    @staticmethod
    @transaction.atomic
    def delete_role(
        tenant_id: UUID,
        role_id: UUID,
        *,
        actor_id: UUID,
        reason: str,
        correlation_id: str,
    ) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        role = _role(tenant, role_id, lock=True)
        if role.is_system:
            raise SecurityConflict("System roles cannot be deleted")
        if Role.objects.for_tenant(tenant).filter(parent_role=role, is_deleted=False).exists():
            raise SecurityConflict("A role with active child roles cannot be deleted")
        if UserRole.objects.for_tenant(tenant).filter(role=role, revoked_at__isnull=True).exists():
            raise SecurityConflict("A role with active assignments cannot be deleted")
        role.is_deleted, role.deleted_at, role.is_active, role.updated_by = True, timezone.now(), False, actor
        role.save(update_fields=("is_deleted", "deleted_at", "is_active", "updated_by", "updated_at"))
        _security_event(
            tenant,
            event_type="security.role.changed",
            aggregate_type="role",
            aggregate_id=role.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "delete", "reason": _required_text(reason, "reason")},
        )

    @staticmethod
    @transaction.atomic
    def set_role_permission(
        tenant_id: UUID,
        role_id: UUID,
        permission_id: UUID,
        *,
        is_granted: bool,
        actor_id: UUID,
        correlation_id: str,
    ) -> RolePermission:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        role = _role(tenant, role_id, lock=True)
        permission = Permission.objects.filter(id=permission_id).first()
        if permission is None:
            raise SecurityNotFound("Permission was not found")
        item, _ = RolePermission.objects.for_tenant(tenant).update_or_create(
            tenant_id=tenant,
            role=role,
            permission=permission,
            defaults={"is_granted": bool(is_granted), "updated_by": actor, "created_by": actor},
        )
        _security_event(
            tenant,
            event_type="security.role.changed",
            aggregate_type="role",
            aggregate_id=role.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "set_permission", "permission": permission.code, "is_granted": bool(is_granted)},
        )
        return item

    @staticmethod
    @transaction.atomic
    def remove_role_permission(
        tenant_id: UUID,
        role_id: UUID,
        permission_id: UUID,
        *,
        actor_id: UUID,
        correlation_id: str,
    ) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        role = _role(tenant, role_id, lock=True)
        item = (
            RolePermission.objects.select_for_update()
            .for_tenant(tenant)
            .filter(role=role, permission_id=permission_id)
            .first()
        )
        if item is None:
            raise SecurityNotFound("Explicit role permission was not found")
        item.delete()
        _security_event(
            tenant,
            event_type="security.role.changed",
            aggregate_type="role",
            aggregate_id=role.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "remove_permission", "permission_id": str(permission_id)},
        )

    @staticmethod
    @transaction.atomic
    def assign_role(
        tenant_id: UUID,
        user_id: UUID,
        role_id: UUID,
        *,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        reason: str,
        actor_id: UUID,
        correlation_id: str,
    ) -> UserRole:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        defaults = configuration.document.get("defaults")
        if not isinstance(defaults, Mapping):
            raise SecurityConfigurationMissing("Assignment defaults are required")
        user, role = _tenant_user(tenant, user_id), _role(tenant, role_id, lock=True)
        start = valid_from or timezone.now()
        existing = (
            UserRole.objects.select_for_update()
            .for_tenant(tenant)
            .filter(user=user, role=role, revoked_at__isnull=True)
            .first()
        )
        if existing and existing.is_active:
            raise SecurityConflict("An active assignment already exists")
        if existing:
            existing.revoked_at, existing.revoked_by = timezone.now(), actor
            existing.revocation_reason = str(defaults["automatic_revocation_reason"])
            existing.save(update_fields=("revoked_at", "revoked_by", "revocation_reason", "updated_at"))
        assignment = UserRole(
            tenant_id=tenant,
            user=user,
            role=role,
            valid_from=start,
            valid_until=valid_until,
            assigned_by=actor,
            reason=_required_text(reason, "reason"),
        )
        _model_validation(assignment)
        assignment.save(force_insert=True)
        _security_event(
            tenant,
            event_type="security.assignment.changed",
            aggregate_type="user_role",
            aggregate_id=assignment.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "assign", "role_id": str(role.id)},
        )
        return assignment

    @staticmethod
    @transaction.atomic
    def update_role_assignment(
        tenant_id: UUID,
        assignment_id: UUID,
        *,
        valid_from: datetime | None,
        valid_until: datetime | None,
        reason: str | None,
        actor_id: UUID,
        correlation_id: str,
    ) -> UserRole:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = UserRole.objects.select_for_update().for_tenant(tenant).filter(id=assignment_id).first()
        if item is None:
            raise SecurityNotFound("Assignment was not found")
        if item.revoked_at:
            raise SecurityConflict("A revoked assignment cannot be changed")
        if valid_from is not None:
            item.valid_from = valid_from
        if valid_until is not None:
            item.valid_until = valid_until
        if reason is not None:
            item.reason = _required_text(reason, "reason")
        _model_validation(item)
        item.save()
        _security_event(
            tenant,
            event_type="security.assignment.changed",
            aggregate_type="user_role",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def revoke_role_assignment(
        tenant_id: UUID,
        assignment_id: UUID,
        *,
        reason: str,
        actor_id: UUID,
        correlation_id: str,
    ) -> UserRole:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = UserRole.objects.select_for_update().for_tenant(tenant).filter(id=assignment_id).first()
        if item is None:
            raise SecurityNotFound("Assignment was not found")
        if item.revoked_at is None:
            item.revoked_at, item.revoked_by = timezone.now(), actor
            item.revocation_reason = _required_text(reason, "reason")
            item.save(update_fields=("revoked_at", "revoked_by", "revocation_reason", "updated_at"))
            _security_event(
                tenant,
                event_type="security.assignment.changed",
                aggregate_type="user_role",
                aggregate_id=item.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"operation": "revoke"},
            )
        return item


class PermissionCatalogService:
    """Immutable catalog discovery and trusted manifest registration."""

    @staticmethod
    def list_permissions(
        tenant_id: UUID,
        *,
        module: str | None = None,
        resource: str | None = None,
        action: str | None = None,
        search: str | None = None,
    ) -> QuerySet[Permission]:
        _uuid(tenant_id, "tenant_id")
        queryset = Permission.objects.all()
        for field, value in (("module", module), ("resource", resource), ("action", action)):
            if value:
                queryset = queryset.filter(**{field: str(value).lower()})
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return queryset

    @staticmethod
    def get_permission(tenant_id: UUID, permission_id: UUID) -> Permission:
        _uuid(tenant_id, "tenant_id")
        item = Permission.objects.filter(id=permission_id).first()
        if item is None:
            raise SecurityNotFound("Permission was not found")
        return item

    @staticmethod
    def resolve_code(tenant_id: UUID, permission_code: str) -> Permission:
        _uuid(tenant_id, "tenant_id")
        match = PERMISSION_CODE_RE.fullmatch(str(permission_code))
        if match is None:
            raise SecurityValidationError("Malformed canonical permission code")
        item = Permission.objects.filter(**match.groupdict()).first()
        if item is None:
            raise SecurityNotFound("Permission was not found")
        return item

    @staticmethod
    @transaction.atomic
    def register_manifest_permissions(
        tenant_id: UUID,
        *,
        module_manifest: Mapping[str, object],
        actor_id: UUID,
        correlation_id: str,
    ) -> tuple[Permission, ...]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        metadata = module_manifest.get("metadata", {})
        extension_contract = metadata.get("extension_contract", {}) if isinstance(metadata, Mapping) else {}
        permission_catalog = (
            extension_contract.get("permission_catalog", {}) if isinstance(extension_contract, Mapping) else {}
        )
        declared_namespace = permission_catalog.get("namespace") if isinstance(permission_catalog, Mapping) else None
        namespace = _slug(
            module_manifest.get("permission_namespace", declared_namespace or module_manifest.get("name", "")),
            "namespace",
        )
        rows = module_manifest.get("permissions")
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise SecurityValidationError("Manifest permissions must be an array")
        registered: list[Permission] = []
        for raw in rows:
            descriptor = {"code": raw} if isinstance(raw, str) else raw
            if not isinstance(descriptor, Mapping):
                raise SecurityValidationError("Permission descriptor must be a string or object")
            code = str(descriptor.get("code", ""))
            match = PERMISSION_CODE_RE.fullmatch(code)
            if match is None or match.group("module") != namespace:
                raise SecurityValidationError("Permission code is malformed or outside the owned namespace")
            defaults = {
                "name": str(descriptor.get("name", code)),
                "description": str(descriptor.get("description", "")),
                "risk_level": str(descriptor.get("risk_level", Permission.RiskLevel.MEDIUM)),
            }
            item, created = Permission.objects.get_or_create(**match.groupdict(), defaults=defaults)
            if not created and any(getattr(item, key) != value for key, value in defaults.items()):
                raise SecurityConflict(f"Catalog entry {code} is immutable and differs from the manifest")
            registered.append(item)
        evidence_id = uuid.uuid5(uuid.NAMESPACE_URL, f"catalog:{namespace}")
        _security_event(
            tenant,
            event_type="security.permission_catalog.registered",
            aggregate_type="permission_catalog",
            aggregate_id=evidence_id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"namespace": namespace, "count": len(registered)},
        )
        return tuple(registered)


class PermissionSetService:
    @staticmethod
    @transaction.atomic
    def create_permission_set(
        tenant_id: UUID,
        *,
        name: str,
        description: str = "",
        default_duration_days: int | None = None,
        is_active: bool = True,
        actor_id: UUID,
        correlation_id: str,
    ) -> PermissionSet:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        limits = configuration.document.get("limits")
        if not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Permission-set limits are required")
        if default_duration_days is not None and not (
            int(limits["permission_set_duration_min_days"])
            <= default_duration_days
            <= int(limits["permission_set_duration_max_days"])
        ):
            raise SecurityValidationError("Default duration is outside tenant configuration limits")
        normalized_name = _required_text(name, "name", 255)
        if PermissionSet.objects.for_tenant(tenant).filter(name=normalized_name, is_deleted=False).exists():
            raise SecurityConflict("An active permission set with this name already exists")
        item = PermissionSet(
            tenant_id=tenant,
            name=normalized_name,
            description=str(description).strip(),
            default_duration_days=default_duration_days,
            is_active=is_active,
            created_by=actor,
            updated_by=actor,
        )
        _model_validation(item)
        try:
            item.save(force_insert=True)
        except IntegrityError as exc:
            raise SecurityConflict("An active permission set with this name already exists") from exc
        _security_event(
            tenant,
            event_type="security.permission_set.changed",
            aggregate_type="permission_set",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "create"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def update_permission_set(
        tenant_id: UUID, permission_set_id: UUID, *, changes: Mapping[str, object], actor_id: UUID, correlation_id: str
    ) -> PermissionSet:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = _permission_set(tenant, permission_set_id, lock=True)
        allowed = {"name", "description", "default_duration_days", "is_active"}
        if set(changes) - allowed:
            raise SecurityValidationError("Unsupported permission-set changes")
        for key, value in changes.items():
            setattr(item, key, value)
        item.updated_by = actor
        _model_validation(item)
        item.save()
        _security_event(
            tenant,
            event_type="security.permission_set.changed",
            aggregate_type="permission_set",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def delete_permission_set(
        tenant_id: UUID, permission_set_id: UUID, *, actor_id: UUID, reason: str, correlation_id: str
    ) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = _permission_set(tenant, permission_set_id, lock=True)
        if (
            UserPermissionSet.objects.for_tenant(tenant)
            .filter(permission_set=item, revoked_at__isnull=True, expires_at__gt=timezone.now())
            .exists()
        ):
            raise SecurityConflict("Permission set has active grants")
        item.is_deleted, item.deleted_at, item.is_active, item.updated_by = True, timezone.now(), False, actor
        item.save(update_fields=("is_deleted", "deleted_at", "is_active", "updated_by", "updated_at"))
        _security_event(
            tenant,
            event_type="security.permission_set.changed",
            aggregate_type="permission_set",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "delete", "reason": _required_text(reason, "reason")},
        )

    @staticmethod
    @transaction.atomic
    def set_permissions(
        tenant_id: UUID, permission_set_id: UUID, *, permission_ids: Sequence[UUID], actor_id: UUID, correlation_id: str
    ) -> PermissionSet:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = _permission_set(tenant, permission_set_id, lock=True)
        ids = tuple(dict.fromkeys(_uuid(value, "permission_id") for value in permission_ids))
        permissions = {row.id: row for row in Permission.objects.filter(id__in=ids)}
        if set(ids) != set(permissions):
            raise SecurityValidationError("One or more permission IDs are unknown")
        active = {
            row.permission_id: row
            for row in PermissionSetPermission.objects.select_for_update()
            .for_tenant(tenant)
            .filter(permission_set=item, removed_at__isnull=True)
        }
        now = timezone.now()
        for permission_id, membership in active.items():
            if permission_id not in permissions:
                membership.removed_at, membership.removed_by = now, actor
                membership.save(update_fields=("removed_at", "removed_by"))
        for permission_id, permission in permissions.items():
            if permission_id not in active:
                PermissionSetPermission.objects.create(
                    tenant_id=tenant, permission_set=item, permission=permission, added_by=actor
                )
        _security_event(
            tenant,
            event_type="security.permission_set.changed",
            aggregate_type="permission_set",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "replace_membership", "count": len(ids)},
        )
        return item

    @staticmethod
    @transaction.atomic
    def grant_to_user(
        tenant_id: UUID,
        permission_set_id: UUID,
        user_id: UUID,
        *,
        expires_at: datetime | None,
        duration_days: int | None,
        reason: str,
        actor_id: UUID,
        correlation_id: str,
    ) -> UserPermissionSet:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        limits = configuration.document.get("limits")
        defaults = configuration.document.get("defaults")
        if not isinstance(limits, Mapping) or not isinstance(defaults, Mapping):
            raise SecurityConfigurationMissing("Grant configuration is required")
        if duration_days is not None and not (
            int(limits["permission_set_duration_min_days"])
            <= duration_days
            <= int(limits["permission_set_duration_max_days"])
        ):
            raise SecurityValidationError("Grant duration is outside tenant configuration limits")
        item, user = _permission_set(tenant, permission_set_id, lock=True), _tenant_user(tenant, user_id)
        if not item.is_active:
            raise SecurityConflict("Inactive permission sets cannot be granted")
        if expires_at is not None and duration_days is not None:
            raise SecurityValidationError("Provide expires_at or duration_days, not both")
        start = timezone.now()
        days = duration_days if duration_days is not None else item.default_duration_days
        expiry = expires_at or (start + timedelta(days=days) if days else None)
        if expiry is None:
            raise SecurityValidationError("An explicit expiry or configured default duration is required")
        existing = (
            UserPermissionSet.objects.select_for_update()
            .for_tenant(tenant)
            .filter(user=user, permission_set=item, revoked_at__isnull=True)
            .first()
        )
        if existing and existing.is_active:
            raise SecurityConflict("An active permission-set grant already exists")
        if existing:
            existing.revoked_at, existing.revoked_by, existing.revocation_reason = (
                start,
                actor,
                str(defaults["automatic_revocation_reason"]),
            )
            existing.save(update_fields=("revoked_at", "revoked_by", "revocation_reason", "updated_at"))
        grant = UserPermissionSet(
            tenant_id=tenant,
            user=user,
            permission_set=item,
            granted_at=start,
            expires_at=expiry,
            granted_by=actor,
            reason=_required_text(reason, "reason"),
        )
        _model_validation(grant)
        grant.save(force_insert=True)
        _security_event(
            tenant,
            event_type="security.assignment.changed",
            aggregate_type="user_permission_set",
            aggregate_id=grant.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "grant", "permission_set_id": str(item.id)},
        )
        return grant

    @staticmethod
    @transaction.atomic
    def update_user_grant(
        tenant_id: UUID,
        grant_id: UUID,
        *,
        expires_at: datetime,
        reason: str | None = None,
        actor_id: UUID,
        correlation_id: str,
    ) -> UserPermissionSet:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        grant = UserPermissionSet.objects.select_for_update().for_tenant(tenant).filter(id=grant_id).first()
        if grant is None:
            raise SecurityNotFound("Grant was not found")
        if grant.revoked_at or grant.expires_at <= timezone.now():
            raise SecurityConflict("A revoked or expired grant cannot be changed")
        grant.expires_at = expires_at
        if reason is not None:
            grant.reason = _required_text(reason, "reason")
        _model_validation(grant)
        grant.save()
        _security_event(
            tenant,
            event_type="security.assignment.changed",
            aggregate_type="user_permission_set",
            aggregate_id=grant.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update"},
        )
        return grant

    @staticmethod
    @transaction.atomic
    def revoke_user_grant(
        tenant_id: UUID, grant_id: UUID, *, reason: str, actor_id: UUID, correlation_id: str
    ) -> UserPermissionSet:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        grant = UserPermissionSet.objects.select_for_update().for_tenant(tenant).filter(id=grant_id).first()
        if grant is None:
            raise SecurityNotFound("Grant was not found")
        if grant.revoked_at is None:
            grant.revoked_at, grant.revoked_by, grant.revocation_reason = (
                timezone.now(),
                actor,
                _required_text(reason, "reason"),
            )
            grant.save(update_fields=("revoked_at", "revoked_by", "revocation_reason", "updated_at"))
            _security_event(
                tenant,
                event_type="security.assignment.changed",
                aggregate_type="user_permission_set",
                aggregate_id=grant.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"operation": "revoke"},
            )
        return grant


class FieldSecurityService:
    @staticmethod
    @transaction.atomic
    def create_rule(
        tenant_id: UUID,
        *,
        module: str,
        resource: str,
        field: str,
        role_id: UUID,
        visibility: str | None = None,
        edit_control: str | None = None,
        mask_pattern: str = "",
        is_active: bool = True,
        actor_id: UUID,
        correlation_id: str,
    ) -> FieldSecurity:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        defaults = configuration.document.get("defaults")
        if not isinstance(defaults, Mapping):
            raise SecurityConfigurationMissing("Field-security defaults are required")
        module_key, resource_key, field_key = (
            _slug(module, "module"),
            _slug(resource, "resource"),
            _slug(field, "field"),
        )
        if field_key not in _resource_fields(module_key, resource_key):
            raise SecurityValidationError("Field is not registered for policy use")
        item = FieldSecurity(
            tenant_id=tenant,
            module=module_key,
            resource=resource_key,
            field=field_key,
            role=_role(tenant, role_id),
            visibility=visibility or str(defaults["field_visibility"]),
            edit_control=edit_control or str(defaults["field_edit_control"]),
            mask_pattern=mask_pattern,
            is_active=is_active,
            created_by=actor,
            updated_by=actor,
        )
        _model_validation(item)
        try:
            item.save(force_insert=True)
        except IntegrityError as exc:
            raise SecurityConflict("An active field rule already exists") from exc
        _security_event(
            tenant,
            event_type="security.field_rule.changed",
            aggregate_type="field_security",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "create"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def update_rule(
        tenant_id: UUID, rule_id: UUID, *, changes: Mapping[str, object], actor_id: UUID, correlation_id: str
    ) -> FieldSecurity:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = FieldSecurity.objects.select_for_update().for_tenant(tenant).filter(id=rule_id, is_deleted=False).first()
        if item is None:
            raise SecurityNotFound("Field rule was not found")
        allowed = {"visibility", "edit_control", "mask_pattern", "is_active"}
        if set(changes) - allowed:
            raise SecurityValidationError("Field target and role are immutable")
        for key, value in changes.items():
            setattr(item, key, value)
        item.updated_by = actor
        _model_validation(item)
        item.save()
        _security_event(
            tenant,
            event_type="security.field_rule.changed",
            aggregate_type="field_security",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def delete_rule(tenant_id: UUID, rule_id: UUID, *, actor_id: UUID, reason: str, correlation_id: str) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = FieldSecurity.objects.select_for_update().for_tenant(tenant).filter(id=rule_id, is_deleted=False).first()
        if item is None:
            raise SecurityNotFound("Field rule was not found")
        item.is_deleted, item.deleted_at, item.is_active, item.updated_by = True, timezone.now(), False, actor
        item.save(update_fields=("is_deleted", "deleted_at", "is_active", "updated_by", "updated_at"))
        _security_event(
            tenant,
            event_type="security.field_rule.changed",
            aggregate_type="field_security",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "delete", "reason": _required_text(reason, "reason")},
        )

    @staticmethod
    def resolve_field_access(
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        *,
        fields: Sequence[str],
        context: Mapping[str, object] | None = None,
    ) -> dict[str, FieldAccessDecision]:
        del context
        tenant = _uuid(tenant_id, "tenant_id")
        role_ids = AccessEvaluationService.active_role_ids(tenant, user_id)
        requested = tuple(dict.fromkeys(str(field) for field in fields))
        registered = frozenset(_resource_fields(module, resource))
        if not set(requested).issubset(registered):
            raise SecurityValidationError("One or more fields are not registered")
        rules = FieldSecurity.objects.for_tenant(tenant).filter(
            module=module,
            resource=resource,
            field__in=requested,
            role_id__in=role_ids,
            is_active=True,
            is_deleted=False,
        )
        by_field: dict[str, list[FieldSecurity]] = {field: [] for field in requested}
        for rule in rules:
            by_field[rule.field].append(rule)
        visibility_rank = {"visible": 0, "masked": 1, "hidden": 2, "redacted": 3}
        edit_rank = {"required": 0, "editable": 1, "read_only": 2}
        result: dict[str, FieldAccessDecision] = {}
        for field, candidates in by_field.items():
            if not candidates:
                result[field] = FieldAccessDecision(field, "hidden", "read_only", "", (), ("DENY_DEFAULT",))
                continue
            visibility = max((item.visibility for item in candidates), key=visibility_rank.__getitem__)
            edit = max((item.edit_control for item in candidates), key=edit_rank.__getitem__)
            if visibility != "visible":
                edit = "read_only"
            masks = sorted(item.mask_pattern for item in candidates if item.visibility == "masked")
            result[field] = FieldAccessDecision(
                field,
                visibility,
                edit,
                masks[0] if visibility == "masked" and masks else "",
                tuple(sorted(str(item.id) for item in candidates)),
                ("FIELD_RULE_APPLIED",),
            )
        return result


class RowSecurityService:
    @staticmethod
    @transaction.atomic
    def create_rule(
        tenant_id: UUID,
        *,
        module: str,
        resource: str,
        role_id: UUID,
        rule_type: str | None = None,
        filter_criteria: Mapping[str, object],
        priority: int | None = None,
        is_active: bool = True,
        actor_id: UUID,
        correlation_id: str,
    ) -> RowSecurityRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        module_key, resource_key = _slug(module, "module"), _slug(resource, "resource")
        ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        configuration = ConfigurationService.require_existing(tenant)
        defaults = configuration.document.get("defaults")
        limits = configuration.document.get("limits")
        if not isinstance(defaults, Mapping) or not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Row-security configuration is required")
        resolved_priority = int(defaults["row_rule_priority"] if priority is None else priority)
        if not int(limits["row_priority_min"]) <= resolved_priority <= int(limits["row_priority_max"]):
            raise SecurityValidationError("Row priority is outside tenant configuration limits")
        validate_predicate(
            filter_criteria, allowed_fields=_resource_fields(module_key, resource_key), tenant_id=tenant
        )
        item = RowSecurityRule(
            tenant_id=tenant,
            module=module_key,
            resource=resource_key,
            role=_role(tenant, role_id),
            rule_type=rule_type or str(defaults["row_rule_type"]),
            filter_criteria=dict(filter_criteria),
            priority=resolved_priority,
            is_active=is_active,
            created_by=actor,
            updated_by=actor,
        )
        _model_validation(item)
        item.save(force_insert=True)
        _security_event(
            tenant,
            event_type="security.row_rule.changed",
            aggregate_type="row_security_rule",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "create", "version": item.version},
        )
        return item

    @staticmethod
    @transaction.atomic
    def update_rule(
        tenant_id: UUID, rule_id: UUID, *, changes: Mapping[str, object], actor_id: UUID, correlation_id: str
    ) -> RowSecurityRule:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        previous = (
            RowSecurityRule.objects.select_for_update().for_tenant(tenant).filter(id=rule_id, is_deleted=False).first()
        )
        if previous is None:
            raise SecurityNotFound("Row rule was not found")
        allowed = {"filter_criteria", "priority", "is_active", "rule_type"}
        if set(changes) - allowed:
            raise SecurityValidationError("Row target and role are immutable")
        criteria = changes.get("filter_criteria", previous.filter_criteria)
        ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        validate_predicate(
            criteria, allowed_fields=_resource_fields(previous.module, previous.resource), tenant_id=tenant
        )
        previous.is_active, previous.is_deleted, previous.deleted_at, previous.updated_by = (
            False,
            True,
            timezone.now(),
            actor,
        )
        previous.save(update_fields=("is_active", "is_deleted", "deleted_at", "updated_by", "updated_at"))
        item = RowSecurityRule(
            tenant_id=tenant,
            module=previous.module,
            resource=previous.resource,
            role=previous.role,
            rule_type=str(changes.get("rule_type", previous.rule_type)),
            filter_criteria=criteria,
            priority=int(changes.get("priority", previous.priority)),
            is_active=bool(changes.get("is_active", True)),
            version=previous.version + 1,
            created_by=actor,
            updated_by=actor,
        )
        _model_validation(item)
        item.save(force_insert=True)
        _security_event(
            tenant,
            event_type="security.row_rule.changed",
            aggregate_type="row_security_rule",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "version", "supersedes": str(previous.id), "version": item.version},
        )
        return item

    @staticmethod
    @transaction.atomic
    def delete_rule(tenant_id: UUID, rule_id: UUID, *, actor_id: UUID, reason: str, correlation_id: str) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = (
            RowSecurityRule.objects.select_for_update().for_tenant(tenant).filter(id=rule_id, is_deleted=False).first()
        )
        if item is None:
            raise SecurityNotFound("Row rule was not found")
        item.is_deleted, item.deleted_at, item.is_active, item.updated_by = True, timezone.now(), False, actor
        item.save(update_fields=("is_deleted", "deleted_at", "is_active", "updated_by", "updated_at"))
        _security_event(
            tenant,
            event_type="security.row_rule.changed",
            aggregate_type="row_security_rule",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "delete", "reason": _required_text(reason, "reason")},
        )

    @staticmethod
    def compile_queryset_filter(
        tenant_id: UUID, user_id: UUID, module: str, resource: str, *, context: Mapping[str, object] | None = None
    ) -> Q:
        tenant = _uuid(tenant_id, "tenant_id")
        subject = {"id": user_id, **dict(context or {})}
        rules = (
            RowSecurityRule.objects.for_tenant(tenant)
            .filter(
                module=module,
                resource=resource,
                role_id__in=AccessEvaluationService.active_role_ids(tenant, user_id),
                is_active=True,
                is_deleted=False,
            )
            .order_by("-priority", "id")
        )
        fields = _resource_fields(module, resource)
        result = Q(pk__in=[])
        matched = False
        for rule in rules:
            result |= compile_predicate(
                rule.filter_criteria, allowed_fields=fields, subject_attributes=subject, tenant_id=tenant
            )
            matched = True
        return result if matched else Q(pk__in=[])

    @staticmethod
    def explain_row_access(
        tenant_id: UUID,
        user_id: UUID,
        module: str,
        resource: str,
        *,
        record_attributes: Mapping[str, object],
        context: Mapping[str, object] | None = None,
    ) -> RowAccessExplanation:
        tenant = _uuid(tenant_id, "tenant_id")
        fields = _resource_fields(module, resource)
        subject = {"id": user_id, **dict(context or {})}
        applied: list[str] = []
        for rule in (
            RowSecurityRule.objects.for_tenant(tenant)
            .filter(
                module=module,
                resource=resource,
                role_id__in=AccessEvaluationService.active_role_ids(tenant, user_id),
                is_active=True,
                is_deleted=False,
            )
            .order_by("-priority", "id")
        ):
            if predicate_matches(
                rule.filter_criteria,
                record=record_attributes,
                allowed_fields=fields,
                subject_attributes=subject,
                tenant_id=tenant,
            ):
                applied.append(str(rule.id))
        return RowAccessExplanation(
            bool(applied), tuple(applied), ("ROW_RULE_APPLIED",) if applied else ("DENY_DEFAULT",)
        )


class SecurityProfileService:
    PROFILE_FIELDS = frozenset(field.name for field in SecurityProfile._meta.fields) - frozenset(
        {"id", "tenant_id", "created_at", "updated_at", "created_by", "updated_by", "is_deleted", "deleted_at"}
    )

    @staticmethod
    @transaction.atomic
    def create_profile(tenant_id: UUID, *, actor_id: UUID, correlation_id: str, **values: object) -> SecurityProfile:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        configured_defaults = configuration.document.get("defaults")
        profile_defaults = configured_defaults.get("security_profile") if isinstance(configured_defaults, Mapping) else None
        if not isinstance(profile_defaults, Mapping):
            raise SecurityConfigurationMissing("Security profile defaults are required")
        if set(values) - SecurityProfileService.PROFILE_FIELDS:
            raise SecurityValidationError("Unsupported security profile fields")
        name = _required_text(values.get("name", ""), "name", 255)
        if SecurityProfile.objects.for_tenant(tenant).filter(name=name, is_deleted=False).exists():
            raise SecurityConflict("An active security profile with this name already exists")
        values = {**deepcopy(dict(profile_defaults)), **values, "name": name}
        item = SecurityProfile(tenant_id=tenant, created_by=actor, updated_by=actor, **values)
        _model_validation(item)
        item.save(force_insert=True)
        _security_event(
            tenant,
            event_type="security.profile.changed",
            aggregate_type="security_profile",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "create"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def update_profile(
        tenant_id: UUID, profile_id: UUID, *, changes: Mapping[str, object], actor_id: UUID, correlation_id: str
    ) -> SecurityProfile:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        item = (
            SecurityProfile.objects.select_for_update()
            .for_tenant(tenant)
            .filter(id=profile_id, is_deleted=False)
            .first()
        )
        if item is None:
            raise SecurityNotFound("Security profile was not found")
        if set(changes) - SecurityProfileService.PROFILE_FIELDS:
            raise SecurityValidationError("Unsupported security profile fields")
        for key, value in changes.items():
            setattr(item, key, value)
        item.updated_by = actor
        _model_validation(item)
        item.save()
        _security_event(
            tenant,
            event_type="security.profile.changed",
            aggregate_type="security_profile",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def delete_profile(tenant_id: UUID, profile_id: UUID, *, actor_id: UUID, reason: str, correlation_id: str) -> None:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = (
            SecurityProfile.objects.select_for_update()
            .for_tenant(tenant)
            .filter(id=profile_id, is_deleted=False)
            .first()
        )
        if item is None:
            raise SecurityNotFound("Security profile was not found")
        if (
            SecurityProfileAssignment.objects.for_tenant(tenant)
            .filter(security_profile=item, revoked_at__isnull=True)
            .exists()
        ):
            raise SecurityConflict("Assigned profiles cannot be deleted")
        item.is_deleted, item.deleted_at, item.is_active, item.updated_by = True, timezone.now(), False, actor
        item.save(update_fields=("is_deleted", "deleted_at", "is_active", "updated_by", "updated_at"))
        _security_event(
            tenant,
            event_type="security.profile.changed",
            aggregate_type="security_profile",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "delete", "reason": _required_text(reason, "reason")},
        )

    @staticmethod
    @transaction.atomic
    def assign_profile(
        tenant_id: UUID,
        profile_id: UUID,
        *,
        user_id: UUID | str | None = None,
        role_id: UUID | None = None,
        precedence: int | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        reason: str,
        actor_id: UUID,
        correlation_id: str,
    ) -> SecurityProfileAssignment:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        defaults = configuration.document.get("defaults")
        limits = configuration.document.get("limits")
        if not isinstance(defaults, Mapping) or not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Profile assignment configuration is required")
        resolved_precedence = int(defaults["profile_assignment_precedence"] if precedence is None else precedence)
        if not int(limits["row_priority_min"]) <= resolved_precedence <= int(limits["row_priority_max"]):
            raise SecurityValidationError("Assignment precedence is outside tenant configuration limits")
        profile = (
            SecurityProfile.objects.for_tenant(tenant).filter(id=profile_id, is_deleted=False, is_active=True).first()
        )
        if profile is None:
            raise SecurityNotFound("Security profile was not found")
        user = _tenant_user(tenant, user_id) if user_id else None
        role = _role(tenant, role_id) if role_id else None
        item = SecurityProfileAssignment(
            tenant_id=tenant,
            security_profile=profile,
            user=user,
            role=role,
            precedence=resolved_precedence,
            valid_from=valid_from or timezone.now(),
            valid_until=valid_until,
            assigned_by=actor,
            reason=_required_text(reason, "reason"),
        )
        _model_validation(item)
        try:
            item.save(force_insert=True)
        except IntegrityError as exc:
            raise SecurityConflict("An active profile assignment already exists") from exc
        _security_event(
            tenant,
            event_type="security.assignment.changed",
            aggregate_type="security_profile_assignment",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "assign"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def update_profile_assignment(
        tenant_id: UUID, assignment_id: UUID, *, changes: Mapping[str, object], actor_id: UUID, correlation_id: str
    ) -> SecurityProfileAssignment:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = SecurityProfileAssignment.objects.select_for_update().for_tenant(tenant).filter(id=assignment_id).first()
        if item is None:
            raise SecurityNotFound("Profile assignment was not found")
        if item.revoked_at:
            raise SecurityConflict("A revoked assignment cannot be changed")
        allowed = {"precedence", "valid_from", "valid_until", "reason"}
        if set(changes) - allowed:
            raise SecurityValidationError("Assignment subject and profile are immutable")
        for key, value in changes.items():
            setattr(item, key, value)
        _model_validation(item)
        item.save()
        _security_event(
            tenant,
            event_type="security.assignment.changed",
            aggregate_type="security_profile_assignment",
            aggregate_id=item.id,
            actor_id=actor,
            correlation_id=correlation_id,
            payload={"operation": "update"},
        )
        return item

    @staticmethod
    @transaction.atomic
    def revoke_profile_assignment(
        tenant_id: UUID, assignment_id: UUID, *, reason: str, actor_id: UUID, correlation_id: str
    ) -> SecurityProfileAssignment:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        item = SecurityProfileAssignment.objects.select_for_update().for_tenant(tenant).filter(id=assignment_id).first()
        if item is None:
            raise SecurityNotFound("Profile assignment was not found")
        if item.revoked_at is None:
            item.revoked_at, item.revoked_by, item.revocation_reason = (
                timezone.now(),
                actor,
                _required_text(reason, "reason"),
            )
            item.save(update_fields=("revoked_at", "revoked_by", "revocation_reason", "updated_at"))
            _security_event(
                tenant,
                event_type="security.assignment.changed",
                aggregate_type="security_profile_assignment",
                aggregate_id=item.id,
                actor_id=actor,
                correlation_id=correlation_id,
                payload={"operation": "revoke"},
            )
        return item

    @staticmethod
    def resolve_effective_profile(
        tenant_id: UUID, user_id: UUID, *, context: Mapping[str, object] | None = None
    ) -> EffectiveSecurityProfile:
        del context
        tenant = _uuid(tenant_id, "tenant_id")
        now = timezone.now()
        roles = AccessEvaluationService.active_role_ids(tenant, user_id)
        assignments = list(
            SecurityProfileAssignment.objects.for_tenant(tenant)
            .filter(Q(user_id=user_id) | Q(role_id__in=roles), revoked_at__isnull=True, valid_from__lte=now)
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
            .select_related("security_profile")
            .order_by("-precedence", "id")
        )
        assignments = [
            item for item in assignments if item.security_profile.is_active and not item.security_profile.is_deleted
        ]
        if not assignments:
            configuration = ConfigurationService.require_existing(tenant)
            baseline = configuration.document.get("baseline_profile")
            if not isinstance(baseline, Mapping):
                raise SecurityConfigurationMissing("A valid mandatory baseline security profile is required")
            return EffectiveSecurityProfile(
                (f"tenant-baseline:v{configuration.version}",),
                -32768,
                deepcopy(dict(baseline)),
                {
                    "mfa_required": "authentication_service",
                    "session_limits": "authentication_service",
                    "network_and_geography": "access_pipeline",
                    "data_handling": "resource_enforcement_facade",
                },
            )
        top = assignments[0].precedence
        profiles = [item.security_profile for item in assignments if item.precedence == top]
        configuration = ConfigurationService.require_existing(tenant)
        defaults = configuration.document.get("defaults")
        mfa_rank = defaults.get("mfa_precedence") if isinstance(defaults, Mapping) else None
        if not isinstance(mfa_rank, Mapping) or set(mfa_rank) != {"never", "sensitive_actions", "conditional", "always"}:
            raise SecurityConfigurationMissing("MFA precedence configuration is missing or invalid")
        restrictions: dict[str, object] = {
            "mfa_required": max((item.mfa_required for item in profiles), key=mfa_rank.__getitem__),
            "allowed_mfa_methods": (
                sorted(set.intersection(*(set(item.allowed_mfa_methods) for item in profiles))) if profiles else []
            ),
            "session_timeout_minutes": min(item.session_timeout_minutes for item in profiles),
            "absolute_session_timeout_hours": min(item.absolute_session_timeout_hours for item in profiles),
            "max_concurrent_sessions": min(item.max_concurrent_sessions for item in profiles),
            "download_allowed": all(item.download_allowed for item in profiles),
            "print_allowed": all(item.print_allowed for item in profiles),
            "copy_paste_allowed": all(item.copy_paste_allowed for item in profiles),
            "mobile_access_allowed": all(item.mobile_access_allowed for item in profiles),
            "ip_whitelist": (
                sorted(set.intersection(*(set(item.ip_whitelist) for item in profiles)))
                if all(item.ip_whitelist for item in profiles)
                else []
            ),
            "ip_blacklist": sorted(set().union(*(set(item.ip_blacklist) for item in profiles))),
            "allowed_countries": (
                sorted(set.intersection(*(set(item.allowed_countries) for item in profiles)))
                if all(item.allowed_countries for item in profiles)
                else []
            ),
            "blocked_countries": sorted(set().union(*(set(item.blocked_countries) for item in profiles))),
        }
        enforcement = {
            "password_policy": "advisory",
            "mfa_required": "authentication_service",
            "session_limits": "authentication_service",
            "network_and_geography": "access_pipeline",
            "data_handling": "resource_enforcement_facade",
        }
        return EffectiveSecurityProfile(tuple(str(item.id) for item in profiles), top, restrictions, enforcement)


_policy_clients: dict[tuple[str, int], ResilientHttpClient] = {}
_policy_client_lock = threading.Lock()
_policy_client_context = threading.local()


def get_policy_http_client() -> ResilientHttpClient:
    tenant_id = getattr(_policy_client_context, "tenant_id", None)
    if tenant_id is None:
        raise SecurityConfigurationMissing("Tenant context is required for the policy client")
    configuration = ConfigurationService.require_existing(tenant_id)
    resilience = configuration.document.get("resilience")
    if not isinstance(resilience, Mapping):
        raise SecurityConfigurationMissing("Policy resilience configuration is required")
    cache_key = (str(configuration.tenant_id), configuration.version)
    with _policy_client_lock:
        client = _policy_clients.get(cache_key)
        if client is None:
            client = ResilientHttpClient(
                connect_timeout=float(resilience["connect_timeout_seconds"]),
                read_timeout=float(resilience["read_timeout_seconds"]),
                max_retries=int(resilience["max_retries"]),
                failure_threshold=int(resilience["failure_threshold"]),
                reset_timeout=float(resilience["reset_timeout_seconds"]),
            )
            _policy_clients[cache_key] = client
        return client


def reset_policy_http_client() -> None:
    with _policy_client_lock:
        for client in _policy_clients.values():
            client.close()
        _policy_clients.clear()


class PolicyEvaluatorComposition:
    """Validated application-policy composition kept outside the authorization primitive."""

    @staticmethod
    def authoritative() -> Callable[..., PolicyEvaluation]:
        mode = str(getattr(settings, "SARAISE_MODE", "")).lower()
        if mode == "saas":
            return AccessEvaluationService.evaluate_remote
        if mode in {"development", "self-hosted"}:
            return AccessEvaluationService.evaluate_local

        def deny_invalid_configuration(*args: object, **kwargs: object) -> PolicyEvaluation:
            del args, kwargs
            return PolicyEvaluation(False, ("EVALUATOR_CONFIGURATION_INVALID",), ())

        return deny_invalid_configuration


class AccessEvaluationService:
    @staticmethod
    def active_role_ids(tenant_id: UUID, user_id: UUID, *, at: datetime | None = None) -> tuple[UUID, ...]:
        configuration = ConfigurationService.require_existing(tenant_id)
        limits = configuration.document.get("limits")
        if not isinstance(limits, Mapping):
            raise SecurityConfigurationMissing("Role hierarchy limits are required")
        maximum_depth = int(limits["role_hierarchy_max_depth"])
        when = at or timezone.now()
        direct = (
            UserRole.objects.for_tenant(tenant_id)
            .filter(
                user_id=user_id,
                revoked_at__isnull=True,
                valid_from__lte=when,
                role__is_active=True,
                role__is_deleted=False,
            )
            .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=when))
            .select_related("role")
        )
        result: set[UUID] = set()
        for assignment in direct:
            role = assignment.role
            depth = 0
            while role is not None and role.id not in result and depth <= maximum_depth:
                if role.is_active and not role.is_deleted:
                    result.add(role.id)
                role = (
                    Role.objects.for_tenant(tenant_id)
                    .filter(id=role.parent_role_id, is_active=True, is_deleted=False)
                    .first()
                    if role.parent_role_id
                    else None
                )
                depth += 1
        return tuple(sorted(result, key=str))

    @classmethod
    def get_effective_permissions(
        cls, tenant_id: UUID, user_id: UUID, *, at: datetime | None = None
    ) -> EffectivePermissionSet:
        tenant = _uuid(tenant_id, "tenant_id")
        _tenant_user(tenant, user_id)
        when = at or timezone.now()
        role_ids = cls.active_role_ids(tenant, user_id, at=when)
        decisions = RolePermission.objects.for_tenant(tenant).filter(role_id__in=role_ids).select_related("permission")
        allowed = {item.permission.code for item in decisions if item.is_granted}
        denied = {item.permission.code for item in decisions if not item.is_granted}
        grants = UserPermissionSet.objects.for_tenant(tenant).filter(
            user_id=user_id,
            revoked_at__isnull=True,
            granted_at__lte=when,
            expires_at__gt=when,
            permission_set__is_active=True,
            permission_set__is_deleted=False,
        )
        set_ids = tuple(str(item.permission_set_id) for item in grants)
        memberships = (
            PermissionSetPermission.objects.for_tenant(tenant)
            .filter(permission_set_id__in=[item.permission_set_id for item in grants], removed_at__isnull=True)
            .select_related("permission")
        )
        allowed.update(item.permission.code for item in memberships)
        allowed.difference_update(denied)
        return EffectivePermissionSet(
            frozenset(allowed), frozenset(denied), tuple(str(item) for item in role_ids), set_ids
        )

    @classmethod
    def evaluate_local(
        cls,
        tenant_id: UUID,
        identity: object,
        permission_code: str,
        *,
        resource_context: Mapping[str, object] | None = None,
        request: object | None = None,
        correlation_id: str = "",
    ) -> PolicyEvaluation:
        tenant = _uuid(tenant_id, "tenant_id")
        subject_id = getattr(identity, "id", None)
        if subject_id is None:
            return PolicyEvaluation(False, ("SUBJECT_ID_REQUIRED",), ())
        correlation = correlation_id or str(getattr(request, "correlation_id", "")) or f"evaluation-{uuid.uuid4()}"
        ConfigurationService.current(tenant, actor_id=_actor_uuid(subject_id), correlation_id=correlation)
        effective = cls.get_effective_permissions(tenant, subject_id)
        if permission_code in effective.denied:
            return PolicyEvaluation(False, ("EXPLICIT_DENY",), effective.role_ids)
        if permission_code not in effective.allowed:
            return PolicyEvaluation(False, ("DENY_DEFAULT",), ())
        context_values = dict(resource_context or {})
        profile = SecurityProfileService.resolve_effective_profile(tenant, subject_id, context=context_values)
        if not profile.profile_ids or not profile.restrictions:
            return PolicyEvaluation(False, ("PROFILE_CONFIGURATION_MISSING",), ())
        module, resource = context_values.get("module"), context_values.get("resource")
        if bool(module) != bool(resource):
            return PolicyEvaluation(False, ("INVALID_RESOURCE_CONTEXT",), ())
        applied = list(effective.role_ids + effective.permission_set_ids + profile.profile_ids)
        if isinstance(module, str) and isinstance(resource, str):
            requested_fields = context_values.get("requested_fields", [])
            if not isinstance(requested_fields, Sequence) or isinstance(requested_fields, (str, bytes)):
                return PolicyEvaluation(False, ("INVALID_RESOURCE_CONTEXT",), tuple(applied))
            try:
                field_decisions = FieldSecurityService.resolve_field_access(
                    tenant, subject_id, module, resource, fields=tuple(str(value) for value in requested_fields),
                    context=context_values,
                )
                row = RowSecurityService.explain_row_access(
                    tenant, subject_id, module, resource, record_attributes=context_values, context=context_values,
                )
            except (SecurityValidationError, SecurityNotFound):
                return PolicyEvaluation(False, ("INVALID_RESOURCE_CONTEXT",), tuple(applied))
            applied.extend(rule for decision in field_decisions.values() for rule in decision.applied_rule_ids)
            applied.extend(row.applied_rule_ids)
            if any(decision.visibility in {"hidden", "redacted"} for decision in field_decisions.values()) or not row.allowed:
                return PolicyEvaluation(False, ("RESOURCE_POLICY_DENIED",), tuple(dict.fromkeys(applied)))
        return PolicyEvaluation(True, ("ALLOW",), tuple(dict.fromkeys(applied)))

    @staticmethod
    def evaluate_remote(
        tenant_id: UUID,
        identity: object,
        permission_code: str,
        *,
        resource_context: Mapping[str, object] | None = None,
        request: object | None = None,
        correlation_id: str = "",
    ) -> PolicyEvaluation:
        tenant = _uuid(tenant_id, "tenant_id")
        correlation = correlation_id or str(getattr(request, "correlation_id", "")) or f"evaluation-{uuid.uuid4()}"
        try:
            configuration = ConfigurationService.current(
                tenant,
                actor_id=_actor_uuid(getattr(identity, "id", None)),
                correlation_id=correlation,
            )
        except SecurityServiceError as exc:
            logger.warning(
                "security.policy_dependency.degraded",
                extra={"tenant_id": str(tenant), "correlation_id": correlation, "reason_codes": [exc.code]},
            )
            return PolicyEvaluation(False, ("SECURITY_CONFIGURATION_INVALID",), ())
        configured_keys = configuration.document.get("remote_context_keys")
        if not isinstance(configured_keys, list):
            return PolicyEvaluation(False, ("SECURITY_CONFIGURATION_INVALID",), ())
        allowed_context_keys = frozenset(str(value) for value in configured_keys)
        context_values = dict(resource_context or {})
        if set(context_values) - allowed_context_keys or any(
            isinstance(value, Mapping) for value in context_values.values()
        ):
            return PolicyEvaluation(False, ("INVALID_RESOURCE_CONTEXT",), ())
        payload = {
            "tenant_id": str(tenant),
            "subject": {"id": str(getattr(identity, "id", "")), "type": "user"},
            "action": permission_code,
            "resource": {"attributes": context_values},
            "context": {"correlation_id": correlation},
        }
        try:
            _policy_client_context.tenant_id = tenant
            response = get_policy_http_client().post(
                "/api/v1/evaluate", dependency=POLICY_DEPENDENCY, correlation_id=correlation, json=payload
            )
            if response.status_code != 200:
                return PolicyEvaluation(False, ("ENGINE_UNAVAILABLE",), ())
            body = response.json()
            if not isinstance(body, Mapping) or body.get("decision") not in {"allow", "deny"}:
                return PolicyEvaluation(False, ("INVALID_POLICY_RESPONSE",), ())
            reasons = body.get("reason_codes", ())
            policies = body.get("applied_policies", ())
            if (
                not isinstance(reasons, Sequence)
                or isinstance(reasons, (str, bytes))
                or not isinstance(policies, Sequence)
                or isinstance(policies, (str, bytes))
            ):
                return PolicyEvaluation(False, ("INVALID_POLICY_RESPONSE",), ())
            return PolicyEvaluation(
                body["decision"] == "allow", tuple(str(item) for item in reasons), tuple(str(item) for item in policies)
            )
        except Exception as exc:
            logger.warning(
                "security.policy_dependency.degraded",
                extra={"tenant_id": str(tenant), "correlation_id": correlation, "reason_codes": [type(exc).__name__]},
            )
            return PolicyEvaluation(False, ("ENGINE_UNAVAILABLE",), ())

    @classmethod
    def evaluate(
        cls,
        tenant_id: UUID,
        identity: object,
        required_permission: str,
        *,
        resource_context: Mapping[str, object] | None = None,
        request: object | None = None,
        correlation_id: str = "",
        evaluator: Callable[..., PolicyEvaluation] | None = None,
    ) -> PolicyEvaluation:
        authoritative = evaluator or PolicyEvaluatorComposition.authoritative()
        return authoritative(
            tenant_id,
            identity,
            required_permission,
            resource_context=resource_context,
            request=request,
            correlation_id=correlation_id,
        )

    @classmethod
    @transaction.atomic
    def simulate(
        cls,
        tenant_id: UUID,
        subject_id: UUID,
        permission_code: str,
        *,
        resource_context: Mapping[str, object] | None,
        actor_id: UUID,
        correlation_id: str,
    ) -> AccessDecisionResult:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _uuid(actor_id, "actor_id")
        subject = _tenant_user(tenant, subject_id)
        configuration = ConfigurationService.current(tenant, actor_id=actor, correlation_id=correlation_id)
        PermissionCatalogService.resolve_code(tenant, permission_code)
        context_values = dict(resource_context or {})
        evaluation = cls.evaluate(
            tenant,
            subject,
            permission_code,
            resource_context=context_values,
            correlation_id=correlation_id,
        )
        controls = configuration.document.get("commercial_controls")
        if not isinstance(controls, Mapping):
            raise SecurityConfigurationMissing("Commercial control policy is required")
        if controls.get("entitlement") != "not_required" or controls.get("quota") != "not_required":
            raise SecurityDependencyUnavailable("Configured entitlement or quota evaluator is unavailable")
        entitlement = {"required": False, "allowed": True, "reason_code": "NOT_REQUIRED_BY_CONFIGURATION"}
        quota = {"required": False, "allowed": True, "remaining": None, "reason_code": "NOT_REQUIRED_BY_CONFIGURATION"}
        profile = SecurityProfileService.resolve_effective_profile(tenant, subject.id, context=context_values)
        if not profile.profile_ids:
            raise SecurityConfigurationMissing("No effective or baseline security profile is available")
        module, resource = context_values.get("module"), context_values.get("resource")
        requested_fields = context_values.get("requested_fields", [])
        if not isinstance(requested_fields, Sequence) or isinstance(requested_fields, (str, bytes)):
            raise SecurityValidationError("requested_fields must be an array")
        field_decisions: tuple[Mapping[str, object], ...] = ()
        row_explanation: Mapping[str, object] = {
            "allowed": evaluation.allowed,
            "applied_rule_ids": [],
            "reason_codes": ["NOT_APPLICABLE_WITHOUT_RESOURCE"],
            "explanation": "No resource target was supplied; row policy is not applicable.",
        }
        if isinstance(module, str) and isinstance(resource, str):
            resolved_fields = FieldSecurityService.resolve_field_access(
                tenant,
                subject.id,
                module,
                resource,
                fields=tuple(str(value) for value in requested_fields),
                context=context_values,
            )
            field_decisions = tuple(
                {
                    "field": item.field,
                    "visibility": item.visibility,
                    "edit_control": item.edit_control,
                    "mask_pattern": item.mask_pattern,
                    "reason_codes": list(item.reason_codes),
                    "applied_policy_ids": list(item.applied_rule_ids),
                }
                for item in resolved_fields.values()
            )
            row = RowSecurityService.explain_row_access(
                tenant,
                subject.id,
                module,
                resource,
                record_attributes=context_values,
                context=context_values,
            )
            row_explanation = {
                "allowed": row.allowed,
                "applied_rule_ids": list(row.applied_rule_ids),
                "reason_codes": list(row.reason_codes),
                "explanation": "A matching tenant row policy allowed access." if row.allowed else "No matching tenant row policy allowed access.",
            }
        final_allowed = evaluation.allowed and bool(row_explanation["allowed"]) and all(
            item["visibility"] not in {"hidden", "redacted"} for item in field_decisions
        )
        reason_codes = evaluation.reason_codes
        if evaluation.allowed and not final_allowed:
            reason_codes = tuple(dict.fromkeys(reason_codes + ("RESOURCE_POLICY_DENIED",)))
        _, audit = AuditService.append_with_outbox(
            tenant,
            action="security.access.decided",
            actor_type="user",
            actor_id=actor,
            resource_type="access_decision",
            resource_id=None,
            decision="allow" if final_allowed else "deny",
            reason_codes=reason_codes or (("ALLOW",) if final_allowed else ("DENY_DEFAULT",)),
            details={
                "subject_id": str(subject_id),
                "permission_code": permission_code,
                "profile_ids": list(profile.profile_ids),
                "field_decision_count": len(field_decisions),
                "row_allowed": bool(row_explanation["allowed"]),
            },
            ip_address=None,
            user_agent="",
            correlation_id=correlation_id,
        )
        return AccessDecisionResult(
            allowed=final_allowed,
            subject_id=str(subject_id),
            permission_code=permission_code,
            reason_codes=reason_codes,
            applied_policy_ids=evaluation.applied_policies,
            entitlement=entitlement,
            quota=quota,
            field_decisions=field_decisions,
            row_explanation=row_explanation,
            profile={
                "profile_ids": list(profile.profile_ids),
                "precedence": profile.precedence,
                "restrictions": dict(profile.restrictions),
                "enforcement": dict(profile.enforcement),
            },
            audit_id=str(audit.id),
            correlation_id=correlation_id,
            evaluated_at=timezone.now(),
        )

    @staticmethod
    def decision_payload(result: AccessDecisionResult) -> dict[str, object]:
        """Construct the complete public decision envelope in the service layer."""

        payload = asdict(result)
        payload["decision"] = "allow" if result.allowed else "deny"
        payload["audit_log_id"] = payload.pop("audit_id")
        payload.pop("profile", None)
        return payload


class SecurityPolicyEvaluator:
    """Adapter implementing the frozen ``src.core.access.PolicyEvaluator`` protocol."""

    def evaluate(
        self, tenant_id: UUID, identity: object, required_permission: str, *, request: object | None = None
    ) -> PolicyEvaluation:
        return AccessEvaluationService.evaluate(tenant_id, identity, required_permission, request=request)


__all__ = [
    "AccessDecisionResult",
    "AccessEvaluationService",
    "AuditService",
    "EffectivePermissionSet",
    "EffectiveSecurityProfile",
    "FieldAccessDecision",
    "FieldSecurityService",
    "PermissionCatalogService",
    "PermissionSetService",
    "RoleService",
    "RowAccessExplanation",
    "RowSecurityService",
    "SecurityConflict",
    "SecurityNotFound",
    "SecurityPolicyEvaluator",
    "SecurityProfileService",
    "SecurityValidationError",
    "get_policy_http_client",
    "reset_policy_http_client",
]
