"""Transactional, tenant-governed Human Resources business services."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, TypeVar, cast
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status as http_status

from src.core.async_jobs.models import OutboxEvent
from src.core.observability import get_correlation_id
from src.core.state_machine import TransitionRecord

from .events import publish_domain_event
from .models import (
    Attendance,
    AttendanceRevision,
    AttendanceSource,
    AttendanceStatus,
    Department,
    Employee,
    EmploymentStatus,
    HRBaseModel,
    HumanResourcesConfiguration,
    HumanResourcesConfigurationAudit,
    HumanResourcesConfigurationVersion,
    HumanResourcesMutationCommand,
    LeaveBalance,
    LeaveRequest,
    LeaveRequestStatus,
    LeaveType,
)
from .state_machines import EMPLOYEE_LIFECYCLE_MACHINE, LEAVE_REQUEST_MACHINE

logger = logging.getLogger("saraise.human_resources")
ModelT = TypeVar("ModelT", bound=HRBaseModel)


class HumanResourcesServiceError(ValidationError):
    """Stable public domain failure consumed by the governed API layer."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "HR_VALIDATION_ERROR",
        status_code: int = http_status.HTTP_400_BAD_REQUEST,
        details: Mapping[str, object] | None = None,
    ) -> None:
        self.error_code = code
        self.code = code
        self.http_status = status_code
        self.status_code = status_code
        self.public_message = message
        self.details = dict(details or {})
        self.detail = self.details
        super().__init__(message, code=code)


class HRNotFoundError(HumanResourcesServiceError):
    def __init__(self, resource: str) -> None:
        super().__init__(
            f"{resource} was not found.",
            code="HR_RESOURCE_NOT_FOUND",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )


class HRConflictError(HumanResourcesServiceError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "HR_RESOURCE_CONFLICT",
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message, code=code, status_code=http_status.HTTP_409_CONFLICT, details=details)


class HRValidationError(HumanResourcesServiceError):
    """Invalid client or domain input (HTTP 400)."""


class HRCapabilityUnavailableError(HumanResourcesServiceError):
    def __init__(self, message: str = "The requested HR capability is unavailable.") -> None:
        super().__init__(
            message,
            code="HR_CAPABILITY_UNAVAILABLE",
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class HumanResourcesMutationCommandService:
    """Reserve and complete tenant-scoped idempotent HTTP mutation commands."""

    @staticmethod
    def fingerprint(*, method: str, path: str, action: str, query: object, body: object) -> str:
        return _fingerprint(
            {
                "method": method.upper(),
                "path": path,
                "action": action,
                "query": query,
                "body": body,
            }
        )

    @staticmethod
    def begin(
        tenant_id: UUID,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        method: str,
        path: str,
        actor_id: str,
        correlation_id: str,
    ) -> tuple[HumanResourcesMutationCommand, bool]:
        key = _key(idempotency_key)
        existing = (
            HumanResourcesMutationCommand.objects.for_tenant(tenant_id)
            .select_for_update()
            .filter(idempotency_key=key)
            .first()
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise HRConflictError(
                    "The idempotency key was already used for a different command.",
                    code="HR_IDEMPOTENCY_CONFLICT",
                )
            if existing.completed_at is None:
                raise HRConflictError(
                    "The original command is still in progress.",
                    code="HR_IDEMPOTENCY_IN_PROGRESS",
                )
            return existing, True
        try:
            command = HumanResourcesMutationCommand.objects.create(
                tenant_id=tenant_id,
                idempotency_key=key,
                request_fingerprint=request_fingerprint,
                method=method.upper(),
                path=path,
                actor_id=_actor(actor_id),
                correlation_id=_correlation(correlation_id),
            )
        except IntegrityError as exc:
            raise HRConflictError(
                "The idempotency key is already being processed.",
                code="HR_IDEMPOTENCY_IN_PROGRESS",
            ) from exc
        return command, False

    @staticmethod
    def complete(
        command: HumanResourcesMutationCommand,
        *,
        response_status: int,
        response_body: object,
    ) -> None:
        normalized_body = json.loads(json.dumps(response_body, default=str))
        updated = HumanResourcesMutationCommand.objects.filter(
            pk=command.pk,
            tenant_id=command.tenant_id,
            completed_at__isnull=True,
        ).update(
            response_status=response_status,
            response_body=normalized_body,
            completed_at=timezone.now(),
        )
        if updated != 1:
            raise HRConflictError(
                "The mutation command could not be completed exactly once.",
                code="HR_IDEMPOTENCY_COMPLETION_CONFLICT",
            )

    @staticmethod
    def abandon(command: HumanResourcesMutationCommand) -> None:
        HumanResourcesMutationCommand.objects.filter(
            pk=command.pk,
            tenant_id=command.tenant_id,
            completed_at__isnull=True,
        ).delete()


class HumanResourcesConfigurationService:
    """Validate, version, audit, import, export, and resolve tenant HR policy."""

    _DEFAULT_DOCUMENT: Mapping[str, object] = {
        "schema_version": 1,
        "allowed_values": {
            "employment_types": ["full_time", "part_time", "contractor", "temporary"],
            "employment_statuses": ["active", "on_leave", "inactive", "terminated"],
            "attendance_statuses": ["present", "absent", "late", "half_day", "on_leave"],
            "attendance_sources": ["manual", "clock", "import"],
            "leave_types": ["annual", "sick", "personal", "maternity", "paternity", "unpaid"],
            "leave_states": ["pending", "approved", "rejected", "cancelled"],
            "leave_scopes": ["all", "self", "team", "approval_queue"],
        },
        "limits": {
            "actor_identifier_max_length": 255,
            "idempotency_key_max_length": 255,
            "department_code_max_length": 50,
            "department_name_max_length": 255,
            "employee_number_max_length": 50,
            "employee_name_max_length": 100,
            "employee_email_max_length": 255,
            "employee_phone_max_length": 50,
            "employee_position_max_length": 100,
            "hierarchy_max_depth": 100,
            "reporting_tree_default_depth": 5,
            "reporting_tree_max_depth": 20,
            "department_tree_max_nodes": 500,
            "max_hours_per_day": "24.00",
            "leave_amount_minimum": "0.01",
            "list_page_size": 25,
            "lookup_page_size": 100,
            "leave_input_minimum": "0.00",
            "leave_input_step": "0.25",
            "decimal_quantum": "0.01",
        },
        "defaults": {
            "department_active": True,
            "employment_type": "full_time",
            "employment_status": "active",
            "attendance_hours": "0.00",
            "attendance_status": "present",
            "attendance_source": "manual",
            "leave_type": "annual",
            "leave_request_status": "pending",
            "leave_entitled_days": "0.00",
            "leave_carried_days": "0.00",
            "leave_adjustment_version": 1,
            "leave_adjustment_note": "Initial allocation",
            "leave_scope": "all",
            "department_ordering": "department_code",
            "event_schema_version": 1,
        },
        "policies": {
            "manager_eligible_statuses": ["active", "on_leave"],
            "employee_active_statuses": ["active", "on_leave"],
            "attendance_eligible_statuses": ["active", "on_leave"],
            "clock_in_eligible_statuses": ["active"],
            "leave_eligible_statuses": ["active", "on_leave"],
            "attendance_zero_work_statuses": ["absent", "on_leave"],
            "leave_overlap_blocking_statuses": ["pending", "approved"],
            "department_deactivation_blocks_active_children": True,
            "department_deactivation_blocks_active_employees": True,
            "employee_inactivation_requires_no_managed_departments": True,
            "employee_archive_statuses": ["terminated"],
            "employee_archive_blocks_pending_leave": True,
            "leave_balance_enforce_capacity": True,
            "leave_submission_blocks_insufficient_balance": True,
            "allow_future_employee_transitions": False,
            "approved_leave_cancel_before_start_only": True,
            "leave_duration_calendar": "inclusive",
            "one_attendance_per_employee_date": True,
        },
        "workflows": {
            "employee_terminal_states": ["terminated"],
            "employee_transitions": [
                ["place_on_leave", "active", "on_leave"],
                ["return_from_leave", "on_leave", "active"],
                ["deactivate", "active", "inactive"],
                ["deactivate", "on_leave", "inactive"],
                ["activate", "inactive", "active"],
                ["terminate", "active", "terminated"],
                ["terminate", "on_leave", "terminated"],
                ["terminate", "inactive", "terminated"],
            ],
            "leave_terminal_states": ["rejected", "cancelled"],
            "leave_transitions": [
                ["approve", "pending", "approved"],
                ["reject", "pending", "rejected"],
                ["cancel", "pending", "cancelled"],
                ["cancel", "approved", "cancelled"],
            ],
        },
        "feature_rollout": {
            "enabled": True,
            "percentage": 100,
            "roles": [],
            "cohorts": [],
        },
        "visual": {
            "positive_status_token": "status-positive",
            "warning_status_token": "status-warning",
        },
        "operations": {"health_staleness_seconds": 30.0},
    }
    _TOP_LEVEL = frozenset(_DEFAULT_DOCUMENT)

    @classmethod
    def default_document(cls) -> dict[str, object]:
        return deepcopy(dict(cls._DEFAULT_DOCUMENT))

    @staticmethod
    def _mapping(document: Mapping[str, object], key: str) -> Mapping[str, object]:
        value = document.get(key)
        if not isinstance(value, Mapping):
            raise HRValidationError(f"configuration.{key} must be an object.")
        return value

    @classmethod
    def validate_document(cls, raw: object) -> dict[str, object]:
        if not isinstance(raw, Mapping):
            raise HRValidationError("configuration document must be an object.")
        unknown = set(raw) - cls._TOP_LEVEL
        missing = cls._TOP_LEVEL - set(raw)
        if unknown or missing:
            raise HRValidationError(
                "configuration document fields do not match the governed schema.",
                details={"unknown": sorted(unknown), "missing": sorted(missing)},
            )
        document = deepcopy(dict(raw))
        if document.get("schema_version") != 1:
            raise HRValidationError("configuration.schema_version must be 1.")
        allowed = cls._mapping(document, "allowed_values")
        limits = cls._mapping(document, "limits")
        defaults = cls._mapping(document, "defaults")
        policies = cls._mapping(document, "policies")
        workflows = cls._mapping(document, "workflows")
        rollout = cls._mapping(document, "feature_rollout")
        visual = cls._mapping(document, "visual")
        operations = cls._mapping(document, "operations")
        expected_keys = {
            section: set(cast(Mapping[str, object], cls._DEFAULT_DOCUMENT[section]))
            for section in cls._TOP_LEVEL - {"schema_version"}
        }
        sections = {
            "allowed_values": allowed,
            "limits": limits,
            "defaults": defaults,
            "policies": policies,
            "workflows": workflows,
            "feature_rollout": rollout,
            "visual": visual,
            "operations": operations,
        }
        for name, section in sections.items():
            if set(section) != expected_keys[name]:
                raise HRValidationError(
                    f"configuration.{name} fields do not match the governed schema.",
                    details={
                        "unknown": sorted(set(section) - expected_keys[name]),
                        "missing": sorted(expected_keys[name] - set(section)),
                    },
                )
        list_keys = (
            "employment_types",
            "employment_statuses",
            "attendance_statuses",
            "attendance_sources",
            "leave_types",
            "leave_states",
            "leave_scopes",
        )
        for key in list_keys:
            values = allowed[key]
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise HRValidationError(f"configuration.allowed_values.{key} must be a non-empty string list.")
            if len(values) != len(set(values)):
                raise HRValidationError(f"configuration.allowed_values.{key} cannot contain duplicates.")
        bounded = {
            "actor_identifier_max_length": (32, 1024),
            "idempotency_key_max_length": (16, 1024),
            "department_code_max_length": (1, 50),
            "department_name_max_length": (1, 255),
            "employee_number_max_length": (1, 50),
            "employee_name_max_length": (1, 100),
            "employee_email_max_length": (3, 255),
            "employee_phone_max_length": (1, 50),
            "employee_position_max_length": (1, 100),
            "hierarchy_max_depth": (1, 500),
            "reporting_tree_default_depth": (1, 100),
            "reporting_tree_max_depth": (1, 100),
            "department_tree_max_nodes": (1, 10000),
            "list_page_size": (1, 100),
            "lookup_page_size": (1, 100),
        }
        for key, (minimum, maximum) in bounded.items():
            value = limits[key]
            if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
                raise HRValidationError(f"configuration.limits.{key} must be between {minimum} and {maximum}.")
        if cast(int, limits["reporting_tree_default_depth"]) > cast(int, limits["reporting_tree_max_depth"]):
            raise HRValidationError("reporting_tree_default_depth cannot exceed reporting_tree_max_depth.")
        decimal_bounds = {
            "max_hours_per_day": (Decimal("0.01"), Decimal("24.00")),
            "leave_amount_minimum": (Decimal("0.01"), Decimal("365.00")),
            "leave_input_minimum": (Decimal("0.00"), Decimal("365.00")),
            "leave_input_step": (Decimal("0.01"), Decimal("365.00")),
            "decimal_quantum": (Decimal("0.01"), Decimal("1.00")),
        }
        for key, (minimum, maximum) in decimal_bounds.items():
            value = _decimal(limits[key], f"configuration.limits.{key}")
            if value < minimum or value > maximum:
                raise HRValidationError(f"configuration.limits.{key} is outside its safe range.")
            document["limits"][key] = format(value, ".2f")  # type: ignore[index]
        default_memberships = {
            "employment_type": "employment_types",
            "employment_status": "employment_statuses",
            "attendance_status": "attendance_statuses",
            "attendance_source": "attendance_sources",
            "leave_type": "leave_types",
            "leave_request_status": "leave_states",
            "leave_scope": "leave_scopes",
        }
        for default_key, allowed_key in default_memberships.items():
            if defaults[default_key] not in cast(list[object], allowed[allowed_key]):
                raise HRValidationError(f"configuration.defaults.{default_key} must be allowed.")
        for policy_key, allowed_key in {
            "manager_eligible_statuses": "employment_statuses",
            "employee_active_statuses": "employment_statuses",
            "attendance_eligible_statuses": "employment_statuses",
            "clock_in_eligible_statuses": "employment_statuses",
            "leave_eligible_statuses": "employment_statuses",
            "attendance_zero_work_statuses": "attendance_statuses",
            "leave_overlap_blocking_statuses": "leave_states",
            "employee_archive_statuses": "employment_statuses",
        }.items():
            values = policies[policy_key]
            if (
                not isinstance(values, list)
                or not values
                or not set(values).issubset(set(cast(list[object], allowed[allowed_key])))
            ):
                raise HRValidationError(f"configuration.policies.{policy_key} contains unsupported values.")
        boolean_policy_keys = (
            "department_deactivation_blocks_active_children",
            "department_deactivation_blocks_active_employees",
            "employee_inactivation_requires_no_managed_departments",
            "employee_archive_blocks_pending_leave",
            "leave_balance_enforce_capacity",
            "leave_submission_blocks_insufficient_balance",
            "allow_future_employee_transitions",
            "approved_leave_cancel_before_start_only",
            "one_attendance_per_employee_date",
        )
        for key in boolean_policy_keys:
            if not isinstance(policies[key], bool):
                raise HRValidationError(f"configuration.policies.{key} must be boolean.")
        for prefix, states_key, transitions_key in (
            ("employee", "employment_statuses", "employee_transitions"),
            ("leave", "leave_states", "leave_transitions"),
        ):
            state_values = set(cast(list[str], allowed[states_key]))
            terminal_values = workflows[f"{prefix}_terminal_states"]
            transitions_value = workflows[transitions_key]
            if (
                not isinstance(terminal_values, list)
                or not terminal_values
                or not set(terminal_values).issubset(state_values)
            ):
                raise HRValidationError(f"configuration.workflows.{prefix}_terminal_states is invalid.")
            if not isinstance(transitions_value, list) or not transitions_value:
                raise HRValidationError(f"configuration.workflows.{transitions_key} must be non-empty.")
            for edge in transitions_value:
                if (
                    not isinstance(edge, list)
                    or len(edge) != 3
                    or any(not isinstance(value, str) or not value for value in edge)
                    or edge[1] not in state_values
                    or edge[2] not in state_values
                ):
                    raise HRValidationError(f"configuration.workflows.{transitions_key} contains an invalid edge.")
        percentage = rollout["percentage"]
        if not isinstance(percentage, int) or isinstance(percentage, bool) or not 0 <= percentage <= 100:
            raise HRValidationError("configuration.feature_rollout.percentage must be between 0 and 100.")
        if not isinstance(rollout["enabled"], bool):
            raise HRValidationError("configuration.feature_rollout.enabled must be boolean.")
        for key in ("roles", "cohorts"):
            if not isinstance(rollout[key], list) or any(not isinstance(value, str) for value in rollout[key]):
                raise HRValidationError(f"configuration.feature_rollout.{key} must be a string list.")
        staleness = operations["health_staleness_seconds"]
        if not isinstance(staleness, (int, float)) or isinstance(staleness, bool) or not 1 <= staleness <= 300:
            raise HRValidationError("configuration.operations.health_staleness_seconds must be between 1 and 300.")
        return document

    @classmethod
    def _config_fields(cls, document: Mapping[str, object]) -> dict[str, object]:
        limits = cls._mapping(document, "limits")
        return {
            "actor_identifier_max_length": limits["actor_identifier_max_length"],
            "idempotency_key_max_length": limits["idempotency_key_max_length"],
            "hierarchy_max_depth": limits["hierarchy_max_depth"],
            "reporting_tree_max_depth": limits["reporting_tree_max_depth"],
            "department_tree_max_nodes": limits["department_tree_max_nodes"],
            "max_hours_per_day": limits["max_hours_per_day"],
        }

    @classmethod
    @transaction.atomic
    def ensure_configuration(cls, tenant_id: UUID, environment: str = "default") -> HumanResourcesConfiguration:
        tenant = _tenant(tenant_id)
        environment_value = str(environment or "").strip()
        if not environment_value or len(environment_value) > 32:
            raise HRValidationError("environment must contain between 1 and 32 characters.")
        configuration = (
            HumanResourcesConfiguration.objects.for_tenant(tenant)
            .select_for_update()
            .filter(environment=environment_value)
            .first()
        )
        if configuration is not None:
            return configuration
        document = cls.validate_document(cls.default_document())
        configuration = HumanResourcesConfiguration.objects.create(
            tenant_id=tenant,
            environment=environment_value,
            version=1,
            document=document,
            updated_by="system:configuration-bootstrap",
            **cls._config_fields(document),
        )
        correlation = str(uuid.uuid4())
        snapshot = HumanResourcesConfigurationVersion.objects.create(
            tenant_id=tenant,
            configuration=configuration,
            environment=environment_value,
            version=1,
            document=document,
            created_by=configuration.updated_by,
            correlation_id=correlation,
            change_reason="Defensible module defaults",
        )
        HumanResourcesConfigurationAudit.objects.create(
            tenant_id=tenant,
            configuration=configuration,
            environment=environment_value,
            version=snapshot.version,
            action="bootstrap",
            actor_id=configuration.updated_by,
            correlation_id=correlation,
            idempotency_key="system:configuration-bootstrap",
            request_fingerprint=_fingerprint({"document": document, "environment": environment_value}),
            before_document=None,
            after_document=document,
            change_reason=snapshot.change_reason,
        )
        return configuration

    @classmethod
    def get_document(cls, tenant_id: UUID, environment: str = "default") -> dict[str, object]:
        return deepcopy(cls.ensure_configuration(tenant_id, environment).document)

    @classmethod
    def preview(cls, tenant_id: UUID, document: object, environment: str = "default") -> dict[str, object]:
        current = cls.ensure_configuration(tenant_id, environment)
        normalized = cls.validate_document(document)
        changes = cls._diff(current.document, normalized)
        return {"valid": True, "normalized_document": normalized, "changes": changes}

    @classmethod
    def _diff(cls, before: object, after: object, path: str = "") -> list[dict[str, object]]:
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            changes: list[dict[str, object]] = []
            for key in sorted(set(before) | set(after)):
                child = f"{path}.{key}" if path else str(key)
                changes.extend(cls._diff(before.get(key), after.get(key), child))
            return changes
        if before != after:
            return [{"path": path, "before": before, "after": after}]
        return []

    @classmethod
    @transaction.atomic
    def update(
        cls,
        tenant_id: UUID,
        *,
        document: object,
        environment: str,
        actor_id: str,
        correlation_id: str | None,
        change_reason: str,
        idempotency_key: str,
        action: str = "update",
        rolled_back_from_version: int | None = None,
    ) -> HumanResourcesConfiguration:
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        key = _key(idempotency_key)
        reason = str(change_reason or "").strip()
        if not reason or len(reason) > 500:
            raise HRValidationError("change_reason must contain between 1 and 500 characters.")
        normalized = cls.validate_document(document)
        fingerprint = _fingerprint(
            {"document": normalized, "environment": environment, "action": action, "rollback": rolled_back_from_version}
        )
        existing = (
            HumanResourcesConfigurationAudit.objects.for_tenant(tenant)
            .filter(environment=environment, idempotency_key=key)
            .first()
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HRConflictError(
                    "The idempotency key was already used for a different configuration command.",
                    code="HR_IDEMPOTENCY_CONFLICT",
                )
            return HumanResourcesConfiguration.objects.for_tenant(tenant).get(pk=existing.configuration_id)
        configuration = cls.ensure_configuration(tenant, environment)
        configuration = HumanResourcesConfiguration.objects.select_for_update().get(pk=configuration.pk)
        before = deepcopy(configuration.document)
        configuration.version += 1
        configuration.document = normalized
        configuration.updated_by = actor
        for field_name, value in cls._config_fields(normalized).items():
            setattr(configuration, field_name, value)
        configuration.full_clean()
        configuration.save()
        HumanResourcesConfigurationVersion.objects.create(
            tenant_id=tenant,
            configuration=configuration,
            environment=environment,
            version=configuration.version,
            document=normalized,
            created_by=actor,
            correlation_id=correlation,
            change_reason=reason,
            rolled_back_from_version=rolled_back_from_version,
        )
        HumanResourcesConfigurationAudit.objects.create(
            tenant_id=tenant,
            configuration=configuration,
            environment=environment,
            version=configuration.version,
            action=action,
            actor_id=actor,
            correlation_id=correlation,
            idempotency_key=key,
            request_fingerprint=fingerprint,
            before_document=before,
            after_document=normalized,
            change_reason=reason,
        )
        return configuration

    @classmethod
    @transaction.atomic
    def rollback(
        cls,
        tenant_id: UUID,
        *,
        environment: str,
        version: int,
        actor_id: str,
        correlation_id: str | None,
        change_reason: str,
        idempotency_key: str,
    ) -> HumanResourcesConfiguration:
        tenant = _tenant(tenant_id)
        snapshot = (
            HumanResourcesConfigurationVersion.objects.for_tenant(tenant)
            .filter(environment=environment, version=version)
            .first()
        )
        if snapshot is None:
            raise HRNotFoundError("configuration version")
        return cls.update(
            tenant,
            document=snapshot.document,
            environment=environment,
            actor_id=actor_id,
            correlation_id=correlation_id,
            change_reason=change_reason,
            idempotency_key=idempotency_key,
            action="rollback",
            rolled_back_from_version=version,
        )


@dataclass(slots=True)
class DepartmentNode:
    id: UUID
    department_code: str
    department_name: str
    is_active: bool
    manager_id: UUID | None
    manager_name: str | None
    children: list["DepartmentNode"] = field(default_factory=list)


@dataclass(slots=True)
class EmployeeTreeNode:
    id: UUID
    employee_number: str
    full_name: str
    position: str
    employment_status: str
    children: list["EmployeeTreeNode"] = field(default_factory=list)


def _tenant(value: UUID | str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HRValidationError("tenant_id must be a UUID.") from exc


def _identifier(value: UUID | str, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HRValidationError(f"{field_name} must be a UUID.") from exc


def _actor(value: object) -> str:
    actor = str(value or "").strip()
    limits = cast(Mapping[str, object], HumanResourcesConfigurationService.default_document()["limits"])
    maximum = cast(int, limits["actor_identifier_max_length"])
    if not actor or len(actor) > maximum:
        raise HRValidationError(f"actor_id must be a non-empty identifier of at most {maximum} characters.")
    return actor


def _key(value: object) -> str:
    key = str(value or "").strip()
    limits = cast(Mapping[str, object], HumanResourcesConfigurationService.default_document()["limits"])
    maximum = cast(int, limits["idempotency_key_max_length"])
    if not key or len(key) > maximum:
        raise HRValidationError(f"An idempotency key of at most {maximum} characters is required.")
    return key


def _correlation(value: str | None) -> str:
    correlation = str(value or get_correlation_id() or uuid.uuid4()).strip()
    limits = cast(Mapping[str, object], HumanResourcesConfigurationService.default_document()["limits"])
    return correlation[: cast(int, limits["actor_identifier_max_length"])]


def _decimal(value: object, field_name: str) -> Decimal:
    limits = cast(Mapping[str, object], HumanResourcesConfigurationService.default_document()["limits"])
    quantum = Decimal(str(limits["decimal_quantum"]))
    try:
        amount = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise HRValidationError(f"{field_name} must be a decimal number.") from exc
    return amount


def _date(value: object, field_name: str) -> date:
    if isinstance(value, datetime):
        raise HRValidationError(f"{field_name} must be a date, not a timestamp.")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HRValidationError(f"{field_name} must use ISO date format.") from exc


def _fingerprint(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log(
    action: str,
    aggregate: HRBaseModel,
    actor_id: str,
    correlation_id: str,
    started: float,
    *,
    prior_state: str | None = None,
    new_state: str | None = None,
) -> None:
    logger.info(
        "Human Resources domain operation completed",
        extra={
            "correlation_id": correlation_id,
            "tenant_id": str(aggregate.tenant_id),
            "actor_id": actor_id,
            "action": action,
            "aggregate_type": aggregate._meta.model_name,
            "aggregate_id": str(aggregate.pk),
            "prior_state": prior_state,
            "new_state": new_state,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "result_code": "succeeded",
        },
    )


def _get(model: type[ModelT], tenant_id: UUID, object_id: UUID | str, label: str) -> ModelT:
    value = model.objects.for_tenant(tenant_id).filter(pk=_identifier(object_id, f"{label}_id")).first()
    if value is None:
        raise HRNotFoundError(label)
    return cast(ModelT, value)


def _lock(model: type[ModelT], tenant_id: UUID, object_id: UUID | str, label: str) -> ModelT:
    value = (
        model.objects.for_tenant(tenant_id).select_for_update().filter(pk=_identifier(object_id, f"{label}_id")).first()
    )
    if value is None:
        raise HRNotFoundError(label)
    return cast(ModelT, value)


def _save(instance: ModelT, *, update_fields: set[str] | None = None) -> ModelT:
    try:
        instance.full_clean()
        if update_fields is None:
            instance.save()
        else:
            instance.save(update_fields=sorted(update_fields | {"updated_at"}))
    except HumanResourcesServiceError:
        raise
    except ValidationError as exc:
        fields = getattr(exc, "message_dict", None) or {"non_field_errors": exc.messages}
        raise HRValidationError("The HR record is invalid.", details={"fields": fields}) from exc
    except IntegrityError as exc:
        raise HRConflictError("An HR record with these unique values already exists.") from exc
    return instance


def _archive(instance: HRBaseModel, actor_id: str) -> None:
    instance.deleted_at = timezone.now()
    instance.deleted_by = actor_id
    instance.updated_by = actor_id
    instance.save(update_fields=("deleted_at", "deleted_by", "updated_by", "updated_at"))


def _event(
    aggregate: HRBaseModel,
    event_type: str,
    actor_id: str,
    correlation_id: str,
    *,
    causation_id: str | None = None,
    **payload: object,
) -> OutboxEvent:
    return publish_domain_event(
        aggregate.tenant_id,
        event_type,
        str(aggregate._meta.model_name),
        aggregate.id,
        actor_id=actor_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload,
    )


def _idempotent_result(
    model: type[ModelT],
    tenant_id: UUID,
    *,
    event_type: str,
    idempotency_key: str,
    fingerprint: str,
) -> ModelT | None:
    """Resolve a durable command replay from its committed outbox envelope."""

    events = OutboxEvent.objects.for_tenant(tenant_id).filter(event_type=event_type).only("aggregate_id", "payload")
    for event in events.iterator():
        envelope = event.payload if isinstance(event.payload, dict) else {}
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict) or payload.get("idempotency_key") != idempotency_key:
            continue
        if payload.get("fingerprint") != fingerprint:
            raise HRConflictError(
                "The idempotency key was already used for a different command.",
                code="HR_IDEMPOTENCY_CONFLICT",
            )
        result = model.objects.for_tenant(tenant_id).filter(pk=event.aggregate_id).first()
        if result is None:
            raise HRConflictError("The original idempotent command result is no longer available.")
        return cast(ModelT, result)
    return None


def _record_transition(
    aggregate: Employee | LeaveRequest,
    *,
    machine: Any,
    command: str,
    transition_key: str,
    actor_id: str,
    correlation_id: str,
    effective_date: date | None = None,
    reason: str = "",
) -> tuple[bool, str, str]:
    """Apply a core StateMachine edge while saving coupled fields atomically."""

    key = _key(transition_key)
    existing = machine.recorder.find(aggregate, key)
    if existing is not None:
        if existing.command != command:
            raise HRConflictError(
                "The transition key was already used for another command.",
                code="HR_IDEMPOTENCY_CONFLICT",
            )
        return False, existing.from_state, existing.to_state
    current = str(getattr(aggregate, machine.state_field))
    document = HumanResourcesConfigurationService.get_document(aggregate.tenant_id)
    workflows = cast(Mapping[str, object], document["workflows"])
    if isinstance(aggregate, Employee):
        terminal_states = cast(list[str], workflows["employee_terminal_states"])
        transitions = cast(list[list[str]], workflows["employee_transitions"])
    else:
        terminal_states = cast(list[str], workflows["leave_terminal_states"])
        transitions = cast(list[list[str]], workflows["leave_transitions"])
    if current in terminal_states:
        raise HRConflictError("The aggregate is in a terminal state.", code="HR_INVALID_TRANSITION")
    configured_edges = [edge for edge in transitions if len(edge) == 3 and edge[0] == command]
    if not configured_edges:
        raise HRConflictError("The transition command is unsupported.", code="HR_INVALID_TRANSITION")
    configured_edge = next((edge for edge in configured_edges if edge[1] == current), None)
    if configured_edge is None:
        raise HRConflictError("The transition is not valid from the current state.", code="HR_INVALID_TRANSITION")
    metadata = {
        "actor_id": actor_id,
        "correlation_id": correlation_id,
        "effective_date": effective_date.isoformat() if effective_date else None,
        "reason": reason,
    }
    record = TransitionRecord(
        transition_key=key,
        command=command,
        from_state=current,
        to_state=configured_edge[2],
        occurred_at=timezone.now().isoformat(),
        metadata=metadata,
    )
    setattr(aggregate, machine.state_field, configured_edge[2])
    machine.recorder.record(aggregate, record)
    return True, current, configured_edge[2]


class DepartmentService:
    """Department hierarchy, lifecycle, and tenant-reference authority."""

    @staticmethod
    def validate_manager(tenant_id: UUID, manager_id: UUID) -> Employee:
        tenant = _tenant(tenant_id)
        manager = _get(Employee, tenant, manager_id, "employee")
        policy = HumanResourcesConfigurationService.get_document(tenant)
        eligible = set(cast(Mapping[str, object], policy["policies"])["manager_eligible_statuses"])
        if manager.employment_status not in eligible:
            raise HRConflictError("The department manager must be active.")
        return manager

    @staticmethod
    @transaction.atomic
    def validate_parent(tenant_id: UUID, department_id: UUID, parent_id: UUID) -> None:
        tenant = _tenant(tenant_id)
        department = _identifier(department_id, "department_id")
        parent = _identifier(parent_id, "parent_id")
        # Locking the whole small hierarchy serializes reciprocal reparenting.
        links = dict(
            Department.objects.for_tenant(tenant).select_for_update().values_list("id", "parent_department_id")
        )
        if parent not in links:
            raise HRNotFoundError("parent department")
        seen = {department}
        current: UUID | None = parent
        policy = HumanResourcesConfigurationService.get_document(tenant)
        maximum_depth = cast(int, cast(Mapping[str, object], policy["limits"])["hierarchy_max_depth"])
        for _ in range(maximum_depth):
            if current is None:
                return
            if current in seen:
                raise HRConflictError("Department hierarchy cannot contain a cycle.")
            seen.add(current)
            current = links.get(current)
        raise HRConflictError("Department hierarchy exceeds the supported depth.")

    @classmethod
    @transaction.atomic
    def create_department(
        cls,
        tenant_id: UUID,
        *,
        code: str,
        name: str,
        parent_id: UUID | None = None,
        manager_id: UUID | None = None,
        description: str = "",
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Department:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        policy = HumanResourcesConfigurationService.get_document(tenant)
        limits = cast(Mapping[str, object], policy["limits"])
        defaults = cast(Mapping[str, object], policy["defaults"])
        code_value, name_value = code.strip().upper(), name.strip()
        if not code_value or not name_value:
            raise HRValidationError("Department code and name are required.")
        if len(code_value) > cast(int, limits["department_code_max_length"]):
            raise HRValidationError("Department code exceeds the configured safe limit.")
        if len(name_value) > cast(int, limits["department_name_max_length"]):
            raise HRValidationError("Department name exceeds the configured safe limit.")
        parent = _get(Department, tenant, parent_id, "parent department") if parent_id else None
        manager = cls.validate_manager(tenant, manager_id) if manager_id else None
        department = Department(
            tenant_id=tenant,
            department_code=code_value,
            department_name=name_value,
            parent_department=parent,
            manager=manager,
            is_active=cast(bool, defaults["department_active"]),
            description=description.strip(),
            created_by=actor,
            updated_by=actor,
        )
        _save(department)
        _event(department, "human_resources.department.created", actor, correlation)
        _log("create_department", department, actor, correlation, started)
        return department

    @classmethod
    @transaction.atomic
    def update_department(
        cls,
        tenant_id: UUID,
        department_id: UUID,
        *,
        changes: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Department:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        department = _lock(Department, tenant, department_id, "department")
        allowed = {
            "department_code",
            "code",
            "department_name",
            "name",
            "parent_department_id",
            "parent_id",
            "manager_id",
            "description",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise HRValidationError("Unsupported department update fields.", details={"fields": sorted(unknown)})
        if "department_code" in changes or "code" in changes:
            department.department_code = str(changes.get("department_code", changes.get("code"))).strip().upper()
        if "department_name" in changes or "name" in changes:
            department.department_name = str(changes.get("department_name", changes.get("name"))).strip()
        if "description" in changes:
            department.description = str(changes["description"] or "").strip()
        if "parent_department_id" in changes or "parent_id" in changes:
            value = changes.get("parent_department_id", changes.get("parent_id"))
            if value:
                cls.validate_parent(tenant, department.id, cast(UUID, value))
                department.parent_department = _get(Department, tenant, cast(UUID, value), "parent department")
            else:
                department.parent_department = None
        if "manager_id" in changes:
            value = changes["manager_id"]
            department.manager = cls.validate_manager(tenant, cast(UUID, value)) if value else None
        department.updated_by = actor
        _save(department)
        _event(department, "human_resources.department.updated", actor, correlation)
        _log("update_department", department, actor, correlation, started)
        return department

    @staticmethod
    @transaction.atomic
    def deactivate_department(
        tenant_id: UUID,
        department_id: UUID,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Department:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        department = _lock(Department, tenant, department_id, "department")
        if Department.objects.for_tenant(tenant).filter(parent_department=department, is_active=True).exists():
            raise HRConflictError("Deactivate active child departments first.")
        if Employee.objects.for_tenant(tenant).filter(department=department, is_active=True).exists():
            raise HRConflictError("Move or deactivate active employees first.")
        department.is_active = False
        department.updated_by = actor
        _save(department, update_fields={"is_active", "updated_by"})
        _event(department, "human_resources.department.deactivated", actor, correlation)
        _log(
            "deactivate_department",
            department,
            actor,
            correlation,
            started,
            prior_state="active",
            new_state="inactive",
        )
        return department

    @staticmethod
    @transaction.atomic
    def activate_department(
        tenant_id: UUID,
        department_id: UUID,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Department:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        department = _lock(Department, tenant, department_id, "department")
        if department.is_active:
            return department
        if department.parent_department_id:
            parent = _get(Department, tenant, department.parent_department_id, "parent department")
            if not parent.is_active:
                raise HRConflictError("Activate the parent department first.")
        department.is_active = True
        department.updated_by = actor
        _save(department, update_fields={"is_active", "updated_by"})
        _event(department, "human_resources.department.activated", actor, correlation)
        _log(
            "activate_department",
            department,
            actor,
            correlation,
            started,
            prior_state="inactive",
            new_state="active",
        )
        return department

    @staticmethod
    @transaction.atomic
    def delete_department(
        tenant_id: UUID,
        department_id: UUID,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> None:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        department = _lock(Department, tenant, department_id, "department")
        if Department.objects.for_tenant(tenant).filter(parent_department=department, is_active=True).exists():
            raise HRConflictError("A department with active children cannot be archived.")
        if Employee.objects.for_tenant(tenant).filter(department=department, is_active=True).exists():
            raise HRConflictError("A department with active employees cannot be archived.")
        _archive(department, actor)
        _event(department, "human_resources.department.archived", actor, correlation)
        _log("delete_department", department, actor, correlation, started)

    @staticmethod
    def get_hierarchy(
        tenant_id: UUID,
        *,
        root_id: UUID | None = None,
        include_inactive: bool = False,
    ) -> list[DepartmentNode]:
        tenant = _tenant(tenant_id)
        policy = HumanResourcesConfigurationService.get_document(tenant)
        limits = cast(Mapping[str, object], policy["limits"])
        maximum_nodes = cast(int, limits["department_tree_max_nodes"])
        maximum_depth = cast(int, limits["hierarchy_max_depth"])
        departments = list(Department.objects.for_tenant(tenant).select_related("manager").order_by("department_code"))
        if len(departments) > maximum_nodes:
            raise HRConflictError(
                "Department hierarchy exceeds the configured node limit.",
                code="HR_HIERARCHY_NODE_LIMIT_EXCEEDED",
                details={"maximum_nodes": maximum_nodes},
            )
        if not include_inactive:
            departments = [item for item in departments if item.is_active]
        by_id = {
            item.id: DepartmentNode(
                id=item.id,
                department_code=item.department_code,
                department_name=item.department_name,
                is_active=item.is_active,
                manager_id=item.manager_id,
                manager_name=item.manager.full_name if item.manager_id else None,
            )
            for item in departments
        }
        roots: list[DepartmentNode] = []
        for item in departments:
            node = by_id[item.id]
            if item.parent_department_id in by_id:
                by_id[item.parent_department_id].children.append(node)
            else:
                roots.append(node)
        if root_id is not None:
            root = by_id.get(_identifier(root_id, "root_id"))
            if root is None:
                raise HRNotFoundError("department")
            roots = [root]
        # Iterative cycle/depth verification also protects reads of legacy rows.
        stack: list[tuple[DepartmentNode, frozenset[UUID], int]] = [(node, frozenset(), 1) for node in roots]
        while stack:
            node, ancestors, depth = stack.pop()
            if node.id in ancestors:
                raise HRConflictError("Department hierarchy contains a cycle.")
            if depth > maximum_depth:
                raise HRConflictError("Department hierarchy exceeds the supported depth.")
            stack.extend((child, ancestors | {node.id}, depth + 1) for child in node.children)
        return roots


class EmployeeService:
    """Employee creation, reporting lines, lifecycle, and archival."""

    @staticmethod
    def validate_department(tenant_id: UUID, department_id: UUID) -> Department:
        department = _get(Department, _tenant(tenant_id), department_id, "department")
        if not department.is_active:
            raise HRConflictError("The employee department must be active.")
        return department

    @staticmethod
    @transaction.atomic
    def validate_manager(tenant_id: UUID, employee_id: UUID, manager_id: UUID) -> Employee:
        tenant = _tenant(tenant_id)
        employee = _identifier(employee_id, "employee_id")
        manager = _get(Employee, tenant, manager_id, "manager")
        policy = HumanResourcesConfigurationService.get_document(tenant)
        policies = cast(Mapping[str, object], policy["policies"])
        limits = cast(Mapping[str, object], policy["limits"])
        if manager.employment_status not in set(cast(list[str], policies["manager_eligible_statuses"])):
            raise HRConflictError("The manager must be active.")
        links = dict(Employee.objects.for_tenant(tenant).select_for_update().values_list("id", "manager_id"))
        seen = {employee}
        current: UUID | None = manager.id
        for _ in range(cast(int, limits["hierarchy_max_depth"])):
            if current is None:
                return manager
            if current in seen:
                raise HRConflictError("Reporting lines cannot contain a cycle.")
            seen.add(current)
            current = links.get(current)
        raise HRConflictError("Reporting line exceeds the supported depth.")

    @classmethod
    @transaction.atomic
    def create_employee(
        cls,
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Employee:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        forbidden = {
            "tenant_id",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "employment_status",
            "is_active",
            "termination_date",
            "termination_reason",
            "transition_history",
        }
        if forbidden & set(data):
            raise HRValidationError("Client-controlled tenant, audit, and lifecycle fields are forbidden.")
        values = dict(data)
        policy = HumanResourcesConfigurationService.get_document(tenant)
        defaults = cast(Mapping[str, object], policy["defaults"])
        policies = cast(Mapping[str, object], policy["policies"])
        limits = cast(Mapping[str, object], policy["limits"])
        allowed_values = cast(Mapping[str, object], policy["allowed_values"])
        department_id = values.pop("department_id", values.pop("department", None))
        manager_id = values.pop("manager_id", values.pop("manager", None))
        required = ("employee_number", "first_name", "last_name", "email", "hire_date")
        missing = [name for name in required if not str(values.get(name, "")).strip()]
        if missing:
            raise HRValidationError("Required employee fields are missing.", details={"fields": missing})
        employee_number = str(values.pop("employee_number")).strip().upper()
        email = str(values.pop("email")).strip().lower()
        first_name = str(values.pop("first_name")).strip()
        last_name = str(values.pop("last_name")).strip()
        phone = str(values.pop("phone", "") or "").strip()
        position = str(values.pop("position", "") or "").strip()
        employment_type = str(values.pop("employment_type", defaults["employment_type"]))
        bounded_values = {
            "employee_number": (employee_number, "employee_number_max_length"),
            "first_name": (first_name, "employee_name_max_length"),
            "last_name": (last_name, "employee_name_max_length"),
            "email": (email, "employee_email_max_length"),
            "phone": (phone, "employee_phone_max_length"),
            "position": (position, "employee_position_max_length"),
        }
        for field_name, (field_value, limit_name) in bounded_values.items():
            if len(field_value) > cast(int, limits[limit_name]):
                raise HRValidationError(f"{field_name} exceeds the configured safe limit.")
        if employment_type not in cast(list[str], allowed_values["employment_types"]):
            raise HRValidationError("employment_type is not enabled by tenant configuration.")
        duplicate = Employee.objects.for_tenant(tenant).filter(
            Q(employee_number=employee_number) | Q(email__iexact=email)
        )
        if duplicate.exists():
            raise HRConflictError("An employee with this number or email already exists.")
        employee = Employee(
            tenant_id=tenant,
            employee_number=employee_number,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            position=position,
            hire_date=_date(values.pop("hire_date"), "hire_date"),
            employment_type=employment_type,
            department=cls.validate_department(tenant, cast(UUID, department_id)) if department_id else None,
            created_by=actor,
            updated_by=actor,
        )
        if values:
            raise HRValidationError("Unsupported employee fields.", details={"fields": sorted(values)})
        if manager_id:
            employee.manager = _get(Employee, tenant, cast(UUID, manager_id), "manager")
            if employee.manager.employment_status not in set(cast(list[str], policies["manager_eligible_statuses"])):
                raise HRConflictError("The manager must be active.")
        _save(employee)
        _event(employee, "human_resources.employee.created", actor, correlation)
        _log("create_employee", employee, actor, correlation, started)
        return employee

    @classmethod
    @transaction.atomic
    def update_employee(
        cls,
        tenant_id: UUID,
        employee_id: UUID,
        *,
        changes: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Employee:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        employee = _lock(Employee, tenant, employee_id, "employee")
        allowed = {
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "phone",
            "department_id",
            "department",
            "manager_id",
            "manager",
            "position",
            "hire_date",
            "employment_type",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise HRValidationError("Unsupported employee update fields.", details={"fields": sorted(unknown)})
        previous_department, previous_manager = employee.department_id, employee.manager_id
        for name in ("first_name", "last_name", "phone", "position"):
            if name in changes:
                setattr(employee, name, str(changes[name] or "").strip())
        if "employee_number" in changes:
            employee.employee_number = str(changes["employee_number"]).strip().upper()
        if "email" in changes:
            employee.email = str(changes["email"]).strip().lower()
        duplicate = (
            Employee.objects.for_tenant(tenant)
            .filter(Q(employee_number=employee.employee_number) | Q(email__iexact=employee.email))
            .exclude(pk=employee.pk)
        )
        if duplicate.exists():
            raise HRConflictError("An employee with this number or email already exists.")
        if "hire_date" in changes:
            employee.hire_date = _date(changes["hire_date"], "hire_date")
        if "employment_type" in changes:
            employee.employment_type = str(changes["employment_type"])
        if "department_id" in changes or "department" in changes:
            value = changes.get("department_id", changes.get("department"))
            employee.department = cls.validate_department(tenant, cast(UUID, value)) if value else None
        if "manager_id" in changes or "manager" in changes:
            value = changes.get("manager_id", changes.get("manager"))
            employee.manager = cls.validate_manager(tenant, employee.id, cast(UUID, value)) if value else None
        employee.updated_by = actor
        _save(employee)
        _event(employee, "human_resources.employee.updated", actor, correlation)
        if previous_department != employee.department_id:
            _event(
                employee,
                "human_resources.employee.department_changed",
                actor,
                correlation,
                previous_department_id=previous_department,
                new_department_id=employee.department_id,
            )
        if previous_manager != employee.manager_id:
            _event(
                employee,
                "human_resources.employee.manager_changed",
                actor,
                correlation,
                previous_manager_id=previous_manager,
                new_manager_id=employee.manager_id,
            )
        _log("update_employee", employee, actor, correlation, started)
        return employee

    @staticmethod
    @transaction.atomic
    def transition_employee(
        tenant_id: UUID,
        employee_id: UUID,
        *,
        command: str,
        transition_key: str,
        effective_date: date | None,
        reason: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Employee:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        employee = _lock(Employee, tenant, employee_id, "employee")
        effective = effective_date or timezone.localdate()
        if effective < employee.hire_date:
            raise HRValidationError("effective_date cannot precede hire_date.")
        if effective > timezone.localdate():
            raise HRCapabilityUnavailableError("Future employee transitions require an installed scheduling extension.")
        applied, prior, target = _record_transition(
            employee,
            machine=EMPLOYEE_LIFECYCLE_MACHINE,
            command=command,
            transition_key=transition_key,
            actor_id=actor,
            correlation_id=correlation,
            effective_date=effective,
            reason=reason.strip(),
        )
        if not applied:
            return employee
        if target in {EmploymentStatus.INACTIVE, EmploymentStatus.TERMINATED}:
            manages_departments = Department.objects.for_tenant(tenant).filter(manager=employee, is_active=True)
            manages_employees = Employee.objects.for_tenant(tenant).filter(manager=employee, is_active=True)
            if manages_departments.exists() or manages_employees.exists():
                raise HRConflictError("Reassign this employee's active management responsibilities first.")
        employee.is_active = target in {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE}
        if target == EmploymentStatus.TERMINATED:
            employee.termination_date = effective
            employee.termination_reason = reason.strip()
        else:
            employee.termination_date = None
            employee.termination_reason = ""
        employee.updated_by = actor
        _save(
            employee,
            update_fields={
                "employment_status",
                "is_active",
                "termination_date",
                "termination_reason",
                "transition_history",
                "updated_by",
            },
        )
        _event(
            employee,
            "human_resources.employee.status_changed",
            actor,
            correlation,
            causation_id=transition_key,
            command=command,
            from_state=prior,
            to_state=target,
            effective_date=effective.isoformat(),
            transition_key=transition_key,
        )
        if target == EmploymentStatus.TERMINATED:
            _event(
                employee,
                "human_resources.employee.terminated",
                actor,
                correlation,
                causation_id=transition_key,
                effective_date=effective.isoformat(),
                transition_key=transition_key,
            )
        _log("transition_employee", employee, actor, correlation, started, prior_state=prior, new_state=target)
        return employee

    @staticmethod
    @transaction.atomic
    def delete_employee(
        tenant_id: UUID,
        employee_id: UUID,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> None:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        employee = _lock(Employee, tenant, employee_id, "employee")
        if employee.employment_status != EmploymentStatus.TERMINATED:
            raise HRConflictError("Only a terminated employee can be archived.", code="HR_INVALID_TRANSITION")
        if (
            LeaveRequest.objects.for_tenant(tenant)
            .filter(employee=employee, status=LeaveRequestStatus.PENDING)
            .exists()
        ):
            raise HRConflictError("Resolve pending leave before archiving the employee.")
        manages_departments = Department.objects.for_tenant(tenant).filter(manager=employee, is_active=True)
        manages_employees = Employee.objects.for_tenant(tenant).filter(manager=employee, is_active=True)
        if manages_departments.exists() or manages_employees.exists():
            raise HRConflictError("Reassign this employee's management responsibilities first.")
        _archive(employee, actor)
        _event(employee, "human_resources.employee.archived", actor, correlation)
        _log("delete_employee", employee, actor, correlation, started)

    @staticmethod
    def get_reporting_tree(tenant_id: UUID, employee_id: UUID, *, depth: int | None = None) -> EmployeeTreeNode:
        tenant = _tenant(tenant_id)
        policy = HumanResourcesConfigurationService.get_document(tenant)
        limits = cast(Mapping[str, object], policy["limits"])
        resolved_depth = cast(int, limits["reporting_tree_default_depth"]) if depth is None else depth
        maximum_depth = cast(int, limits["reporting_tree_max_depth"])
        if not isinstance(resolved_depth, int) or resolved_depth < 1 or resolved_depth > maximum_depth:
            raise HRValidationError(f"depth must be between 1 and {maximum_depth}.")
        root_employee = _get(Employee, tenant, employee_id, "employee")
        employees = list(Employee.objects.for_tenant(tenant).order_by("employee_number"))
        by_manager: dict[UUID, list[Employee]] = {}
        for item in employees:
            if item.manager_id:
                by_manager.setdefault(item.manager_id, []).append(item)

        def node(item: Employee) -> EmployeeTreeNode:
            return EmployeeTreeNode(
                item.id,
                item.employee_number,
                item.full_name,
                item.position,
                item.employment_status,
            )

        root = node(root_employee)
        stack: list[tuple[Employee, EmployeeTreeNode, int, frozenset[UUID]]] = [(root_employee, root, 1, frozenset())]
        while stack:
            current, current_node, level, ancestors = stack.pop()
            if current.id in ancestors:
                raise HRConflictError("Reporting tree contains a cycle.")
            if level >= resolved_depth:
                continue
            for report in by_manager.get(current.id, []):
                child = node(report)
                current_node.children.append(child)
                stack.append((report, child, level + 1, ancestors | {current.id}))
        return root


def _validate_attendance_date(attendance_date: date, *timestamps: datetime | None) -> None:
    for value in timestamps:
        if value is None:
            continue
        if timezone.is_naive(value) or timezone.localtime(value).date() != attendance_date:
            raise HRValidationError(
                "Clock timestamps must include an offset and match attendance_date in the tenant timezone.",
                code="HR_TIMEZONE_MISMATCH",
            )


def _hours(check_in: datetime | None, check_out: datetime | None) -> Decimal:
    if check_in is None or check_out is None:
        defaults = cast(Mapping[str, object], HumanResourcesConfigurationService.default_document()["defaults"])
        return Decimal(str(defaults["attendance_hours"]))
    limits = cast(Mapping[str, object], HumanResourcesConfigurationService.default_document()["limits"])
    return Decimal(str((check_out - check_in).total_seconds() / 3600)).quantize(
        Decimal(str(limits["decimal_quantum"])),
        rounding=ROUND_HALF_UP,
    )


class AttendanceService:
    """Attendance recording, correction, and durable clock commands."""

    @staticmethod
    @transaction.atomic
    def create_attendance(
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Attendance:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        forbidden = {"tenant_id", "created_by", "updated_by", "deleted_at", "deleted_by"}
        if forbidden & set(data):
            raise HRValidationError("Client-controlled tenant and audit fields are forbidden.")
        policy = HumanResourcesConfigurationService.get_document(tenant)
        policies = cast(Mapping[str, object], policy["policies"])
        defaults = cast(Mapping[str, object], policy["defaults"])
        allowed = cast(Mapping[str, object], policy["allowed_values"])
        limits = cast(Mapping[str, object], policy["limits"])
        employee_id = data.get("employee_id", data.get("employee"))
        employee = _get(Employee, tenant, cast(UUID, employee_id), "employee")
        if employee.employment_status not in set(cast(list[str], policies["attendance_eligible_statuses"])):
            raise HRConflictError("Attendance can only be recorded for an active or on-leave employee.")
        attendance_date = _date(data.get("attendance_date"), "attendance_date")
        check_in = cast(datetime | None, data.get("check_in_time"))
        check_out = cast(datetime | None, data.get("check_out_time"))
        _validate_attendance_date(attendance_date, check_in, check_out)
        source = str(data.get("source", defaults["attendance_source"]))
        status_value = str(data.get("status", defaults["attendance_status"]))
        if source not in cast(list[str], allowed["attendance_sources"]):
            raise HRValidationError("Attendance source is not enabled by tenant policy.")
        if status_value not in cast(list[str], allowed["attendance_statuses"]):
            raise HRValidationError("Attendance status is not enabled by tenant policy.")
        calculated = _hours(check_in, check_out)
        amount = _decimal(data.get("hours_worked", calculated), "hours_worked")
        if amount > Decimal(str(limits["max_hours_per_day"])):
            raise HRValidationError("hours_worked exceeds the configured daily maximum.")
        attendance = Attendance(
            tenant_id=tenant,
            employee=employee,
            attendance_date=attendance_date,
            check_in_time=check_in,
            check_out_time=check_out,
            hours_worked=amount,
            status=status_value,
            source=source,
            notes=str(data.get("notes", "") or "").strip(),
            created_by=actor,
            updated_by=actor,
        )
        _save(attendance)
        _event(
            attendance,
            "human_resources.attendance.recorded",
            actor,
            correlation,
            employee_id=employee.id,
            attendance_date=attendance_date.isoformat(),
            status=status_value,
        )
        _log("create_attendance", attendance, actor, correlation, started)
        return attendance

    @staticmethod
    @transaction.atomic
    def update_attendance(
        tenant_id: UUID,
        attendance_id: UUID,
        *,
        changes: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Attendance:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        attendance = _lock(Attendance, tenant, attendance_id, "attendance")
        allowed = {
            "attendance_date",
            "check_in_time",
            "check_out_time",
            "hours_worked",
            "status",
            "source",
            "notes",
            "correction_reason",
        }
        unknown = set(changes) - allowed
        if unknown:
            raise HRValidationError("Unsupported attendance update fields.", details={"fields": sorted(unknown)})
        reason = str(changes.get("correction_reason", changes.get("notes", ""))).strip()
        if not reason:
            raise HRValidationError("A correction note is required.", code="HR_CORRECTION_NOTE_REQUIRED")
        field_names = (
            "attendance_date",
            "check_in_time",
            "check_out_time",
            "hours_worked",
            "status",
            "source",
            "notes",
        )
        persisted_before = {
            name: (
                getattr(attendance, name).isoformat()
                if isinstance(getattr(attendance, name), (date, datetime))
                else (
                    str(getattr(attendance, name))
                    if isinstance(getattr(attendance, name), Decimal)
                    else getattr(attendance, name)
                )
            )
            for name in field_names
        }
        latest_revision = (
            AttendanceRevision.objects.for_tenant(tenant)
            .filter(attendance=attendance)
            .order_by("-revision")
            .only("revision", "after_values")
            .first()
        )
        before = deepcopy(latest_revision.after_values) if latest_revision is not None else persisted_before
        effective = dict(before)
        for name in field_names:
            if name in changes:
                effective[name] = changes[name]
        effective_date = _date(effective["attendance_date"], "attendance_date")
        effective_check_in = cast(datetime | None, effective["check_in_time"])
        effective_check_out = cast(datetime | None, effective["check_out_time"])
        _validate_attendance_date(effective_date, effective_check_in, effective_check_out)
        if "hours_worked" in changes:
            effective["hours_worked"] = format(_decimal(changes["hours_worked"], "hours_worked"), ".2f")
        elif "check_in_time" in changes or "check_out_time" in changes:
            effective["hours_worked"] = format(_hours(effective_check_in, effective_check_out), ".2f")
        effective["attendance_date"] = effective_date.isoformat()
        policy = HumanResourcesConfigurationService.get_document(tenant)
        limits = cast(Mapping[str, object], policy["limits"])
        policies = cast(Mapping[str, object], policy["policies"])
        if Decimal(str(effective["hours_worked"])) > Decimal(str(limits["max_hours_per_day"])):
            raise HRValidationError("hours_worked exceeds the configured daily maximum.")
        if effective["status"] in cast(list[str], policies["attendance_zero_work_statuses"]) and (
            Decimal(str(effective["hours_worked"])) != 0
            or effective_check_in is not None
            or effective_check_out is not None
        ):
            raise HRValidationError("The configured non-work statuses cannot contain worked time.")
        for name in ("check_in_time", "check_out_time"):
            value = effective[name]
            if isinstance(value, datetime):
                effective[name] = value.isoformat()
        effective["notes"] = str(effective["notes"]).strip()
        previous_revision = latest_revision.revision if latest_revision is not None else 0
        AttendanceRevision.objects.create(
            tenant_id=tenant,
            attendance=attendance,
            revision=previous_revision + 1,
            before_values=before,
            after_values=effective,
            reason=reason,
            actor_id=actor,
            correlation_id=correlation,
        )
        for name in field_names:
            value = effective[name]
            if name == "attendance_date":
                value = effective_date
            elif name in {"check_in_time", "check_out_time"} and isinstance(value, str):
                value = datetime.fromisoformat(value)
            elif name == "hours_worked":
                value = Decimal(str(value))
            setattr(attendance, name, value)
        _event(
            attendance,
            "human_resources.attendance.corrected",
            actor,
            correlation,
            employee_id=attendance.employee_id,
            attendance_date=attendance.attendance_date.isoformat(),
            status=attendance.status,
            attendance_revision=previous_revision + 1,
            before_check_in_time=before["check_in_time"],
            before_check_out_time=before["check_out_time"],
            before_hours_worked=before["hours_worked"],
            after_check_in_time=effective["check_in_time"],
            after_check_out_time=effective["check_out_time"],
            after_hours_worked=effective["hours_worked"],
        )
        _log("update_attendance", attendance, actor, correlation, started)
        return attendance

    @staticmethod
    @transaction.atomic
    def delete_attendance(
        tenant_id: UUID,
        attendance_id: UUID,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> None:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        attendance = _lock(Attendance, tenant, attendance_id, "attendance")
        _archive(attendance, actor)
        _event(
            attendance,
            "human_resources.attendance.archived",
            actor,
            correlation,
            employee_id=attendance.employee_id,
            attendance_date=attendance.attendance_date.isoformat(),
        )
        _log("delete_attendance", attendance, actor, correlation, started)

    @staticmethod
    @transaction.atomic
    def clock_in(
        tenant_id: UUID,
        *,
        employee_id: UUID,
        occurred_at: datetime | None,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> Attendance:
        started = time.monotonic()
        tenant, actor, key, correlation = (
            _tenant(tenant_id),
            _actor(actor_id),
            _key(idempotency_key),
            _correlation(correlation_id),
        )
        employee_uuid = _identifier(employee_id, "employee_id")
        fingerprint = _fingerprint(
            {
                "employee_id": employee_uuid,
                "occurred_at": occurred_at if occurred_at is not None else "server_time",
            }
        )
        replay = _idempotent_result(
            Attendance,
            tenant,
            event_type="human_resources.attendance.clocked_in",
            idempotency_key=key,
            fingerprint=fingerprint,
        )
        if replay:
            return replay
        occurred_at = occurred_at or timezone.now()
        employee = cast(Employee, _lock(Employee, tenant, employee_uuid, "employee"))
        if employee.employment_status != EmploymentStatus.ACTIVE:
            raise HRConflictError("Only an active employee can clock in.")
        if timezone.is_naive(occurred_at):
            raise HRValidationError("occurred_at must include a timezone offset.", code="HR_TIMEZONE_MISMATCH")
        attendance_date = timezone.localtime(occurred_at).date()
        if Attendance.objects.for_tenant(tenant).filter(employee=employee, attendance_date=attendance_date).exists():
            raise HRConflictError("Attendance already exists for this employee and date.")
        attendance = Attendance(
            tenant_id=tenant,
            employee=employee,
            attendance_date=attendance_date,
            check_in_time=occurred_at,
            hours_worked=Decimal("0.00"),
            status=AttendanceStatus.PRESENT,
            source=AttendanceSource.CLOCK,
            created_by=actor,
            updated_by=actor,
        )
        _save(attendance)
        _event(
            attendance,
            "human_resources.attendance.clocked_in",
            actor,
            correlation,
            employee_id=employee.id,
            attendance_date=attendance_date.isoformat(),
            idempotency_key=key,
            fingerprint=fingerprint,
        )
        _log("clock_in", attendance, actor, correlation, started)
        return attendance

    @staticmethod
    @transaction.atomic
    def clock_out(
        tenant_id: UUID,
        attendance_id: UUID,
        *,
        occurred_at: datetime | None,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> Attendance:
        started = time.monotonic()
        tenant, actor, key, correlation = (
            _tenant(tenant_id),
            _actor(actor_id),
            _key(idempotency_key),
            _correlation(correlation_id),
        )
        attendance_uuid = _identifier(attendance_id, "attendance_id")
        fingerprint = _fingerprint(
            {
                "attendance_id": attendance_uuid,
                "occurred_at": occurred_at if occurred_at is not None else "server_time",
            }
        )
        replay = _idempotent_result(
            Attendance,
            tenant,
            event_type="human_resources.attendance.clocked_out",
            idempotency_key=key,
            fingerprint=fingerprint,
        )
        if replay:
            return replay
        occurred_at = occurred_at or timezone.now()
        attendance = _lock(Attendance, tenant, attendance_uuid, "attendance")
        if attendance.check_in_time is None:
            raise HRConflictError("Clock-out requires an existing check-in.", code="HR_INVALID_TRANSITION")
        if attendance.check_out_time is not None:
            raise HRConflictError("This attendance record is already clocked out.", code="HR_INVALID_TRANSITION")
        _validate_attendance_date(attendance.attendance_date, occurred_at)
        if occurred_at <= attendance.check_in_time:
            raise HRValidationError("occurred_at must be after check-in.")
        attendance.check_out_time = occurred_at
        attendance.hours_worked = _hours(attendance.check_in_time, occurred_at)
        attendance.updated_by = actor
        _save(attendance, update_fields={"check_out_time", "hours_worked", "updated_by"})
        _event(
            attendance,
            "human_resources.attendance.clocked_out",
            actor,
            correlation,
            employee_id=attendance.employee_id,
            attendance_date=attendance.attendance_date.isoformat(),
            idempotency_key=key,
            fingerprint=fingerprint,
        )
        _log("clock_out", attendance, actor, correlation, started)
        return attendance

    @staticmethod
    @transaction.atomic
    def recalculate_hours(
        tenant_id: UUID,
        attendance_id: UUID,
        *,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> Attendance:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        attendance = _lock(Attendance, tenant, attendance_id, "attendance")
        if not attendance.check_in_time or not attendance.check_out_time:
            raise HRConflictError("Both clock timestamps are required to recalculate hours.")
        attendance.hours_worked = _hours(attendance.check_in_time, attendance.check_out_time)
        attendance.updated_by = actor
        _save(attendance, update_fields={"hours_worked", "updated_by"})
        _event(
            attendance,
            "human_resources.attendance.corrected",
            actor,
            correlation,
            employee_id=attendance.employee_id,
            attendance_date=attendance.attendance_date.isoformat(),
            status=attendance.status,
        )
        _log("recalculate_hours", attendance, actor, correlation, started)
        return attendance


def _check_version(balance: LeaveBalance, expected_version: int | None) -> None:
    if expected_version is not None and balance.adjustment_version != expected_version:
        raise HRConflictError(
            "The leave balance changed after it was loaded.",
            code="HR_VERSION_CONFLICT",
            details={"expected_version": expected_version, "current_version": balance.adjustment_version},
        )


def _save_balance(balance: LeaveBalance, actor: str, note: str, fields: set[str]) -> LeaveBalance:
    balance.adjustment_version += 1
    balance.last_adjusted_by = actor
    balance.adjustment_note = note.strip()
    balance.updated_by = actor
    return cast(
        LeaveBalance,
        _save(
            balance,
            update_fields=fields | {"adjustment_version", "last_adjusted_by", "adjustment_note", "updated_by"},
        ),
    )


class LeaveBalanceService:
    """Explicit allocation and atomic reservation accounting."""

    @staticmethod
    @transaction.atomic
    def create_balance(
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> LeaveBalance:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        forbidden = {
            "tenant_id",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
            "used_days",
            "pending_days",
            "adjustment_version",
            "last_adjusted_by",
        }
        if forbidden & set(data):
            raise HRValidationError("Client-controlled tenant, audit, and balance state is forbidden.")
        employee_id = data.get("employee_id", data.get("employee"))
        employee = cast(Employee, _lock(Employee, tenant, cast(UUID, employee_id), "employee"))
        period_start = _date(data.get("period_start"), "period_start")
        period_end = _date(data.get("period_end"), "period_end")
        if period_end < period_start:
            raise HRValidationError("Balance period end cannot precede start.", code="HR_BALANCE_PERIOD_INVALID")
        leave_type = str(data.get("leave_type", ""))
        if leave_type not in LeaveType.values:
            raise HRValidationError("leave_type is invalid.")
        overlap = LeaveBalance.objects.for_tenant(tenant).filter(
            employee=employee,
            leave_type=leave_type,
            period_start__lte=period_end,
            period_end__gte=period_start,
        )
        if overlap.exists():
            raise HRConflictError("Leave balance periods cannot overlap.")
        balance = LeaveBalance(
            tenant_id=tenant,
            employee=employee,
            leave_type=leave_type,
            period_start=period_start,
            period_end=period_end,
            entitled_days=_decimal(data.get("entitled_days", 0), "entitled_days"),
            carried_days=_decimal(data.get("carried_days", 0), "carried_days"),
            created_by=actor,
            updated_by=actor,
            last_adjusted_by=actor,
            adjustment_note=str(data.get("adjustment_note", "Initial allocation")).strip(),
        )
        _save(balance)
        _event(
            balance,
            "human_resources.leave_balance.created",
            actor,
            correlation,
            employee_id=employee.id,
            leave_type=leave_type,
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            version=balance.adjustment_version,
        )
        _log("create_balance", balance, actor, correlation, started)
        return balance

    @staticmethod
    @transaction.atomic
    def update_allocation(
        tenant_id: UUID,
        balance_id: UUID,
        *,
        entitled_days: Decimal,
        carried_days: Decimal,
        expected_version: int,
        note: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> LeaveBalance:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        balance = _lock(LeaveBalance, tenant, balance_id, "leave balance")
        _check_version(balance, expected_version)
        if not note.strip():
            raise HRValidationError("An allocation adjustment note is required.")
        balance.entitled_days = _decimal(entitled_days, "entitled_days")
        balance.carried_days = _decimal(carried_days, "carried_days")
        if balance.remaining_days < 0:
            raise HRConflictError(
                "Allocation reduction would make remaining leave negative.",
                code="HR_INSUFFICIENT_BALANCE",
            )
        _save_balance(balance, actor, note, {"entitled_days", "carried_days"})
        _event(
            balance,
            "human_resources.leave_balance.adjusted",
            actor,
            correlation,
            employee_id=balance.employee_id,
            leave_type=balance.leave_type,
            version=balance.adjustment_version,
        )
        _log("update_allocation", balance, actor, correlation, started)
        return balance

    @staticmethod
    @transaction.atomic
    def reserve(
        tenant_id: UUID,
        balance_id: UUID,
        *,
        days: Decimal,
        actor_id: str,
        expected_version: int | None = None,
        correlation_id: str | None = None,
    ) -> LeaveBalance:
        return LeaveBalanceService._mutate(
            tenant_id,
            balance_id,
            days=days,
            actor_id=actor_id,
            expected_version=expected_version,
            correlation_id=correlation_id,
            operation="reserve",
        )

    @staticmethod
    @transaction.atomic
    def approve_reservation(
        tenant_id: UUID,
        balance_id: UUID,
        *,
        days: Decimal,
        actor_id: str,
        expected_version: int | None = None,
        correlation_id: str | None = None,
    ) -> LeaveBalance:
        return LeaveBalanceService._mutate(
            tenant_id,
            balance_id,
            days=days,
            actor_id=actor_id,
            expected_version=expected_version,
            correlation_id=correlation_id,
            operation="consume",
        )

    @staticmethod
    @transaction.atomic
    def release_reservation(
        tenant_id: UUID,
        balance_id: UUID,
        *,
        days: Decimal,
        actor_id: str,
        expected_version: int | None = None,
        correlation_id: str | None = None,
    ) -> LeaveBalance:
        return LeaveBalanceService._mutate(
            tenant_id,
            balance_id,
            days=days,
            actor_id=actor_id,
            expected_version=expected_version,
            correlation_id=correlation_id,
            operation="release",
        )

    @staticmethod
    @transaction.atomic
    def reverse_usage(
        tenant_id: UUID,
        balance_id: UUID,
        *,
        days: Decimal,
        actor_id: str,
        expected_version: int | None = None,
        correlation_id: str | None = None,
    ) -> LeaveBalance:
        return LeaveBalanceService._mutate(
            tenant_id,
            balance_id,
            days=days,
            actor_id=actor_id,
            expected_version=expected_version,
            correlation_id=correlation_id,
            operation="reverse",
        )

    @staticmethod
    def _mutate(
        tenant_id: UUID,
        balance_id: UUID,
        *,
        days: Decimal,
        actor_id: str,
        expected_version: int | None,
        correlation_id: str | None,
        operation: str,
    ) -> LeaveBalance:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        balance = _lock(LeaveBalance, tenant, balance_id, "leave balance")
        _check_version(balance, expected_version)
        amount = _decimal(days, "days")
        if amount <= 0:
            raise HRValidationError("days must be positive.")
        if operation == "reserve":
            if balance.remaining_days < amount:
                raise HRConflictError("The leave balance is insufficient.", code="HR_INSUFFICIENT_BALANCE")
            balance.pending_days += amount
            fields, event_type = {"pending_days"}, "human_resources.leave_balance.reserved"
        elif operation == "consume":
            if balance.pending_days < amount:
                raise HRConflictError("The pending reservation is insufficient.")
            balance.pending_days -= amount
            balance.used_days += amount
            fields, event_type = {"pending_days", "used_days"}, "human_resources.leave_balance.consumed"
        elif operation == "release":
            if balance.pending_days < amount:
                raise HRConflictError("The pending reservation is insufficient.")
            balance.pending_days -= amount
            fields, event_type = {"pending_days"}, "human_resources.leave_balance.released"
        elif operation == "reverse":
            if balance.used_days < amount:
                raise HRConflictError("Used leave is insufficient to reverse.")
            balance.used_days -= amount
            fields, event_type = {"used_days"}, "human_resources.leave_balance.released"
        else:
            raise AssertionError("Unsupported balance mutation")
        _save_balance(balance, actor, operation, fields)
        _event(
            balance,
            event_type,
            actor,
            correlation,
            employee_id=balance.employee_id,
            leave_type=balance.leave_type,
            version=balance.adjustment_version,
        )
        _log(operation, balance, actor, correlation, started)
        return balance

    @staticmethod
    @transaction.atomic
    def delete_balance(tenant_id: UUID, balance_id: UUID, *, actor_id: str, correlation_id: str | None = None) -> None:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        balance = _lock(LeaveBalance, tenant, balance_id, "leave balance")
        if balance.used_days or balance.pending_days:
            raise HRConflictError("A used or reserved leave balance cannot be archived.")
        _archive(balance, actor)
        _event(
            balance,
            "human_resources.leave_balance.archived",
            actor,
            correlation,
            employee_id=balance.employee_id,
            leave_type=balance.leave_type,
            version=balance.adjustment_version,
        )
        _log("delete_balance", balance, actor, correlation, started)


class LeaveRequestService:
    """Balance-backed leave request submission and approval lifecycle."""

    @staticmethod
    def calculate_days(tenant_id: UUID, *, employee_id: UUID, start_date: date, end_date: date) -> Decimal:
        tenant = _tenant(tenant_id)
        _get(Employee, tenant, employee_id, "employee")
        start, end = _date(start_date, "start_date"), _date(end_date, "end_date")
        if end < start:
            raise HRValidationError("Leave end date cannot precede start date.", code="HR_BALANCE_PERIOD_INVALID")
        document = HumanResourcesConfigurationService.get_document(tenant)
        policies = cast(Mapping[str, object], document["policies"])
        limits = cast(Mapping[str, object], document["limits"])
        if policies["leave_duration_calendar"] != "inclusive":
            raise HRCapabilityUnavailableError("The configured leave calendar policy is unavailable.")
        return Decimal((end - start).days + 1).quantize(Decimal(str(limits["decimal_quantum"])))

    @classmethod
    @transaction.atomic
    def submit_request(
        cls,
        tenant_id: UUID,
        *,
        data: Mapping[str, object],
        actor_id: str,
        idempotency_key: str,
        correlation_id: str | None = None,
    ) -> LeaveRequest:
        started = time.monotonic()
        tenant, actor, key, correlation = (
            _tenant(tenant_id),
            _actor(actor_id),
            _key(idempotency_key),
            _correlation(correlation_id),
        )
        forbidden = {
            "tenant_id",
            "days_requested",
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "cancelled_by",
            "cancelled_at",
            "transition_history",
            "created_by",
            "updated_by",
            "deleted_at",
            "deleted_by",
        }
        if forbidden & set(data):
            raise HRValidationError("Client-controlled tenant, audit, and request state is forbidden.")
        employee_id = _identifier(cast(UUID, data.get("employee_id", data.get("employee"))), "employee_id")
        balance_id = _identifier(
            cast(UUID, data.get("leave_balance_id", data.get("leave_balance"))),
            "leave_balance_id",
        )
        start, end = _date(data.get("start_date"), "start_date"), _date(data.get("end_date"), "end_date")
        leave_type = str(data.get("leave_type", ""))
        fingerprint = _fingerprint(
            {
                "employee_id": employee_id,
                "leave_balance_id": balance_id,
                "leave_type": leave_type,
                "start_date": start,
                "end_date": end,
                "reason": str(data.get("reason", "")),
            }
        )
        replay = _idempotent_result(
            LeaveRequest,
            tenant,
            event_type="human_resources.leave_request.submitted",
            idempotency_key=key,
            fingerprint=fingerprint,
        )
        if replay:
            return replay
        employee = cast(Employee, _lock(Employee, tenant, employee_id, "employee"))
        document = HumanResourcesConfigurationService.get_document(tenant)
        policies = cast(Mapping[str, object], document["policies"])
        allowed = cast(Mapping[str, object], document["allowed_values"])
        defaults = cast(Mapping[str, object], document["defaults"])
        if leave_type not in cast(list[str], allowed["leave_types"]):
            raise HRValidationError("leave_type is not enabled by tenant configuration.")
        if employee.employment_status not in set(cast(list[str], policies["leave_eligible_statuses"])):
            raise HRConflictError("Leave can only be requested for an active employee.")
        balance = _lock(LeaveBalance, tenant, balance_id, "leave balance")
        days = cls.calculate_days(tenant, employee_id=employee.id, start_date=start, end_date=end)
        balance_mismatch = (
            balance.employee_id != employee.id
            or balance.leave_type != leave_type
            or start < balance.period_start
            or end > balance.period_end
        )
        if balance_mismatch:
            raise HRValidationError(
                "The selected balance does not cover the request.",
                code="HR_BALANCE_PERIOD_INVALID",
            )
        overlap = LeaveRequest.objects.for_tenant(tenant).filter(
            employee=employee,
            status__in=cast(list[str], policies["leave_overlap_blocking_statuses"]),
            start_date__lte=end,
            end_date__gte=start,
        )
        if overlap.exists():
            raise HRConflictError("The leave request overlaps an existing request.", code="HR_LEAVE_OVERLAP")
        if cast(bool, policies["leave_submission_blocks_insufficient_balance"]) and balance.remaining_days < days:
            raise HRConflictError("The leave balance is insufficient.", code="HR_INSUFFICIENT_BALANCE")
        balance.pending_days += days
        _save_balance(balance, actor, "request reservation", {"pending_days"})
        request = LeaveRequest(
            tenant_id=tenant,
            employee=employee,
            leave_balance=balance,
            leave_type=leave_type,
            start_date=start,
            end_date=end,
            days_requested=days,
            reason=str(data.get("reason", "") or "").strip(),
            status=str(defaults["leave_request_status"]),
            created_by=actor,
            updated_by=actor,
            transition_history=[
                TransitionRecord(
                    transition_key=key,
                    command="submit",
                    from_state="",
                    to_state=str(defaults["leave_request_status"]),
                    occurred_at=timezone.now().isoformat(),
                    metadata={"actor_id": actor, "correlation_id": correlation},
                ).as_dict()
            ],
        )
        _save(request)
        _event(
            balance,
            "human_resources.leave_balance.reserved",
            actor,
            correlation,
            causation_id=key,
            employee_id=employee.id,
            leave_type=leave_type,
            leave_request_id=request.id,
            version=balance.adjustment_version,
        )
        _event(
            request,
            "human_resources.leave_request.submitted",
            actor,
            correlation,
            causation_id=key,
            employee_id=employee.id,
            leave_balance_id=balance.id,
            leave_type=leave_type,
            idempotency_key=key,
            fingerprint=fingerprint,
            status=request.status,
        )
        _log("submit_request", request, actor, correlation, started)
        return request

    @classmethod
    @transaction.atomic
    def update_pending_request(
        cls,
        tenant_id: UUID,
        request_id: UUID,
        *,
        changes: Mapping[str, object],
        actor_id: str,
        correlation_id: str | None = None,
    ) -> LeaveRequest:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        request = _lock(LeaveRequest, tenant, request_id, "leave request")
        if request.status != LeaveRequestStatus.PENDING:
            raise HRConflictError("Only pending leave requests can be updated.", code="HR_INVALID_TRANSITION")
        allowed = {"leave_balance_id", "leave_balance", "leave_type", "start_date", "end_date", "reason"}
        unknown = set(changes) - allowed
        if unknown:
            raise HRValidationError("Unsupported leave request fields.", details={"fields": sorted(unknown)})
        new_balance_id = changes.get("leave_balance_id", changes.get("leave_balance", request.leave_balance_id))
        balance_ids = sorted(
            {
                request.leave_balance_id,
                _identifier(cast(UUID, new_balance_id), "leave_balance_id"),
            },
            key=str,
        )
        locked_balances = {
            item.id: item
            for item in LeaveBalance.objects.for_tenant(tenant)
            .select_for_update()
            .filter(id__in=balance_ids)
            .order_by("id")
        }
        if len(locked_balances) != len(balance_ids):
            raise HRNotFoundError("leave balance")
        old_balance = locked_balances[request.leave_balance_id]
        new_balance = locked_balances[_identifier(cast(UUID, new_balance_id), "leave_balance_id")]
        start = _date(changes.get("start_date", request.start_date), "start_date")
        end = _date(changes.get("end_date", request.end_date), "end_date")
        leave_type = str(changes.get("leave_type", request.leave_type))
        days = cls.calculate_days(tenant, employee_id=request.employee_id, start_date=start, end_date=end)
        balance_mismatch = (
            new_balance.employee_id != request.employee_id
            or new_balance.leave_type != leave_type
            or start < new_balance.period_start
            or end > new_balance.period_end
        )
        if balance_mismatch:
            raise HRValidationError(
                "The selected balance does not cover the request.",
                code="HR_BALANCE_PERIOD_INVALID",
            )
        overlap = (
            LeaveRequest.objects.for_tenant(tenant)
            .filter(
                employee_id=request.employee_id,
                status__in=(LeaveRequestStatus.PENDING, LeaveRequestStatus.APPROVED),
                start_date__lte=end,
                end_date__gte=start,
            )
            .exclude(pk=request.pk)
        )
        if overlap.exists():
            raise HRConflictError("The leave request overlaps an existing request.", code="HR_LEAVE_OVERLAP")
        old_balance.pending_days -= request.days_requested
        if old_balance.id == new_balance.id:
            if old_balance.remaining_days < days:
                raise HRConflictError("The leave balance is insufficient.", code="HR_INSUFFICIENT_BALANCE")
            old_balance.pending_days += days
            _save_balance(old_balance, actor, "request updated", {"pending_days"})
        else:
            if new_balance.remaining_days < days:
                raise HRConflictError("The leave balance is insufficient.", code="HR_INSUFFICIENT_BALANCE")
            new_balance.pending_days += days
            _save_balance(old_balance, actor, "request moved", {"pending_days"})
            _save_balance(new_balance, actor, "request moved", {"pending_days"})
        request.leave_balance = new_balance
        request.leave_type = leave_type
        request.start_date, request.end_date, request.days_requested = start, end, days
        if "reason" in changes:
            request.reason = str(changes["reason"] or "").strip()
        request.updated_by = actor
        _save(request)
        _event(
            request,
            "human_resources.leave_request.updated",
            actor,
            correlation,
            employee_id=request.employee_id,
            leave_balance_id=new_balance.id,
            leave_type=leave_type,
            status=request.status,
        )
        _log("update_pending_request", request, actor, correlation, started)
        return request

    @classmethod
    def _transition(
        cls,
        tenant_id: UUID,
        request_id: UUID,
        *,
        command: str,
        transition_key: str,
        actor_id: str,
        correlation_id: str | None,
        rejection_reason: str = "",
    ) -> LeaveRequest:
        started = time.monotonic()
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        request = _lock(LeaveRequest, tenant, request_id, "leave request")
        existing = LEAVE_REQUEST_MACHINE.recorder.find(request, _key(transition_key))
        if existing is not None:
            if existing.command != command:
                raise HRConflictError(
                    "The transition key was already used for another command.",
                    code="HR_IDEMPOTENCY_CONFLICT",
                )
            return request
        cancellation_started = (
            command == "cancel"
            and request.status == LeaveRequestStatus.APPROVED
            and request.start_date <= timezone.localdate()
        )
        if cancellation_started:
            raise HRConflictError("Approved leave cannot be cancelled after it starts.", code="HR_INVALID_TRANSITION")
        if command == "reject" and not rejection_reason.strip():
            raise HRValidationError("A rejection reason is required.")
        balance = _lock(LeaveBalance, tenant, request.leave_balance_id, "leave balance")
        applied, prior, target = _record_transition(
            request,
            machine=LEAVE_REQUEST_MACHINE,
            command=command,
            transition_key=transition_key,
            actor_id=actor,
            correlation_id=correlation,
        )
        if not applied:
            return request
        now = timezone.now()
        if command == "approve":
            if balance.pending_days < request.days_requested:
                raise HRConflictError("The reserved balance is insufficient.", code="HR_INSUFFICIENT_BALANCE")
            balance.pending_days -= request.days_requested
            balance.used_days += request.days_requested
            request.approved_by, request.approved_at = actor, now
            balance_event = "human_resources.leave_balance.consumed"
            fields = {"pending_days", "used_days"}
        elif command == "reject":
            if balance.pending_days < request.days_requested:
                raise HRConflictError("The reserved balance is insufficient.")
            balance.pending_days -= request.days_requested
            request.rejection_reason = rejection_reason.strip()
            balance_event = "human_resources.leave_balance.released"
            fields = {"pending_days"}
        else:
            request.cancelled_by, request.cancelled_at = actor, now
            if prior == LeaveRequestStatus.PENDING:
                if balance.pending_days < request.days_requested:
                    raise HRConflictError("The reserved balance is insufficient.")
                balance.pending_days -= request.days_requested
                fields = {"pending_days"}
            else:
                if balance.used_days < request.days_requested:
                    raise HRConflictError("Used leave is insufficient to reverse.")
                balance.used_days -= request.days_requested
                fields = {"used_days"}
            balance_event = "human_resources.leave_balance.released"
        _save_balance(balance, actor, command, fields)
        request.updated_by = actor
        _save(
            request,
            update_fields={
                "status",
                "transition_history",
                "approved_by",
                "approved_at",
                "rejection_reason",
                "cancelled_by",
                "cancelled_at",
                "updated_by",
            },
        )
        _event(
            balance,
            balance_event,
            actor,
            correlation,
            causation_id=transition_key,
            employee_id=request.employee_id,
            leave_type=request.leave_type,
            leave_request_id=request.id,
            version=balance.adjustment_version,
        )
        request_event = {
            "approve": "human_resources.leave_request.approved",
            "reject": "human_resources.leave_request.rejected",
            "cancel": "human_resources.leave_request.cancelled",
        }[command]
        _event(
            request,
            request_event,
            actor,
            correlation,
            causation_id=transition_key,
            employee_id=request.employee_id,
            leave_balance_id=balance.id,
            leave_type=request.leave_type,
            status=target,
            transition_key=transition_key,
        )
        _log(
            f"{command}_request",
            request,
            actor,
            correlation,
            started,
            prior_state=prior,
            new_state=target,
        )
        return request

    @classmethod
    @transaction.atomic
    def approve_request(
        cls,
        tenant_id: UUID,
        request_id: UUID,
        *,
        transition_key: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> LeaveRequest:
        return cls._transition(
            tenant_id,
            request_id,
            command="approve",
            transition_key=transition_key,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )

    @classmethod
    @transaction.atomic
    def reject_request(
        cls,
        tenant_id: UUID,
        request_id: UUID,
        *,
        transition_key: str,
        rejection_reason: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> LeaveRequest:
        return cls._transition(
            tenant_id,
            request_id,
            command="reject",
            transition_key=transition_key,
            rejection_reason=rejection_reason,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )

    @classmethod
    @transaction.atomic
    def cancel_request(
        cls,
        tenant_id: UUID,
        request_id: UUID,
        *,
        transition_key: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> LeaveRequest:
        return cls._transition(
            tenant_id,
            request_id,
            command="cancel",
            transition_key=transition_key,
            actor_id=actor_id,
            correlation_id=correlation_id,
        )

    @classmethod
    @transaction.atomic
    def delete_request(
        cls,
        tenant_id: UUID,
        request_id: UUID,
        *,
        transition_key: str,
        actor_id: str,
        correlation_id: str | None = None,
    ) -> None:
        tenant, actor, correlation = _tenant(tenant_id), _actor(actor_id), _correlation(correlation_id)
        request = _lock(LeaveRequest, tenant, request_id, "leave request")
        if request.status in {LeaveRequestStatus.PENDING, LeaveRequestStatus.APPROVED}:
            request = cls.cancel_request(
                tenant,
                request.id,
                transition_key=transition_key,
                actor_id=actor,
                correlation_id=correlation,
            )
        elif request.status != LeaveRequestStatus.CANCELLED:
            raise HRConflictError(
                "Only a cancellable or cancelled request can be archived.",
                code="HR_INVALID_TRANSITION",
            )
        _archive(request, actor)
        _event(
            request,
            "human_resources.leave_request.archived",
            actor,
            correlation,
            causation_id=transition_key,
            employee_id=request.employee_id,
            leave_balance_id=request.leave_balance_id,
            leave_type=request.leave_type,
            status=request.status,
        )


__all__ = [
    "AttendanceService",
    "DepartmentNode",
    "DepartmentService",
    "EmployeeService",
    "EmployeeTreeNode",
    "HRCapabilityUnavailableError",
    "HRConflictError",
    "HRNotFoundError",
    "HRValidationError",
    "HumanResourcesServiceError",
    "HumanResourcesConfigurationService",
    "LeaveBalanceService",
    "LeaveRequestService",
]
