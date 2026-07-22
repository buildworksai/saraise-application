"""Transactional business services for disaster-recovery operations.

The HTTP and worker layers deliberately contain no domain decisions.  Every
entry point starts with a tenant UUID, reloads records through ``for_tenant``,
and records durable work before returning an asynchronous acceptance.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from src.core.api.results import OperationResult
from src.core.async_jobs.models import AsyncJob, OutboxEvent, OutboxStatus
from src.core.async_jobs.services import enqueue
from src.core.state_machine import StateMachineError

from .adapter_registry import (
    AdapterNotRegistered,
    get_backup_catalog,
    get_extension_action,
    get_storage_adapter,
)
from .models import (
    BDRConfiguration,
    BDRConfigurationVersion,
    DRExercise,
    DRRunbook,
    DRStepExecution,
    ExerciseStatus,
    RecoveryPoint,
    RecoveryPointEvidence,
    RecoveryPointStatus,
    RestoreMode,
    RestoreRun,
    RestoreRunStatus,
    RunbookActionType,
    RunbookStatus,
    RunbookStep,
    StepFailureBehavior,
    TargetEnvironment,
)
from .ports import (
    BackupRequestReceipt,
    BackupStatus,
    BackupStatusSnapshot,
)
from .ports import BackupType as PortBackupType
from .ports import (
    RestoreCompensationPort,
    RestoreEnvironment,
)
from .ports import RestoreMode as PortRestoreMode
from .ports import (
    RestorePreflightPort,
    RestoreProviderReceipt,
    RestoreTarget,
)
from .ports import ScopeType as PortScopeType
from .state_machines import (
    EXERCISE_MACHINE,
    RECOVERY_POINT_MACHINE,
    RESTORE_RUN_MACHINE,
    RUNBOOK_MACHINE,
    STEP_EXECUTION_MACHINE,
)

logger = logging.getLogger("saraise.backup_disaster_recovery")

BACKUP_REQUEST_COMMAND = "backup_disaster_recovery.backup.request"
VERIFY_POINT_COMMAND = "backup_disaster_recovery.recovery_point.verify"
VALIDATE_RESTORE_COMMAND = "backup_disaster_recovery.restore.validate"
EXECUTE_RESTORE_COMMAND = "backup_disaster_recovery.restore.execute"
EXECUTE_EXERCISE_COMMAND = "backup_disaster_recovery.exercise.execute"

_DEFAULT_CONFIGURATION_DOCUMENT: dict[str, Any] = {
    "quota_costs": {
        "default": 1,
        "backup_execution": 10,
        "verification": 5,
        "restore_validation": 5,
        "restore_execution": 25,
        "exercise_execution": 20,
    },
    "resilience": {
        "timeout_seconds": 2.0,
        "max_attempts": 3,
        "initial_backoff_seconds": 0.1,
        "max_backoff_seconds": 2.0,
        "jitter_seconds": 0.1,
        "circuit_failure_threshold": 3,
        "circuit_reset_seconds": 30,
        "checksum_chunk_bytes": 1_048_576,
    },
    "health": {
        "probe_timeout_seconds": 2.0,
        "probe_timeout_max_seconds": 10.0,
        "provider_stale_seconds": 30,
        "outbox_max_lag_seconds": 60,
        "exercise_freshness_seconds": 86_400,
        "registry_staleness_seconds": 30,
        "exercise_registry_staleness_seconds": 86_400,
        "queue_degradation_seconds": 300,
    },
    "providers": {
        "storage_adapter_key": "local-filesystem",
        "local_filesystem_restore_modes": ["full"],
    },
    "runbooks": {
        "default_rpo_seconds": 3_600,
        "default_rto_seconds": 14_400,
        "objective_min_seconds": 1,
        "objective_max_seconds": 315_360_000,
        "min_publish_steps": 1,
        "unpublished_scan_limit": 100,
    },
    "steps": {
        "default_timeout_seconds": 300,
        "min_timeout_seconds": 1,
        "max_timeout_seconds": 86_400,
        "default_retry_limit": 0,
        "max_retry_limit": 10,
        "default_on_failure": "stop",
        "allowed_failure_behaviors": ["stop", "continue_degraded"],
        "max_components": 100,
        "max_verification_checks": 10,
        "allowed_verification_checks": ["connectivity", "integrity", "application", "security"],
        "max_reorder_items": 500,
        "reorder_collision_offset": 1_000,
        "require_draft_for_edits": True,
        "require_manual_approval_permission": True,
    },
    "restores": {
        "production_enabled": False,
        "production_requires_approver": True,
        "selective_requires_components": True,
        "full_prohibits_components": True,
    },
    "exercises": {
        "production_enabled": False,
        "default_schedule_offset_ms": 3_600_000,
        "evidence_freshness_days": 90,
    },
    "reports": {
        "allowed_buckets": ["day", "week", "month"],
        "default_bucket": "month",
        "default_interval_days": 30,
        "max_interval_days": 366,
        "max_results": 1_000,
        "compliant_percent": 100.0,
        "noncompliant_percent": 0.0,
    },
    "presentation": {
        "duration_minute_seconds": 60,
        "duration_hour_seconds": 3_600,
        "byte_base": 1_024,
        "status_positive": ["available", "ready", "succeeded", "passed", "published", "operational"],
        "status_negative": ["corrupt", "failed", "unavailable"],
        "status_warning": ["queued", "validating", "restoring", "verifying", "degraded"],
        "status_positive_token": "status-success",
        "status_negative_token": "status-danger",
        "status_warning_token": "status-warning",
    },
    "polling": {
        "dashboard_ms": 60_000,
        "recovery_point_ms": 4_000,
        "restore_ms": 4_000,
        "exercise_ms": 3_000,
        "exercise_page_size": 100,
        "active_restore_statuses": ["queued", "validating", "ready", "restoring", "verifying"],
        "active_exercise_statuses": ["queued", "running"],
    },
    "workflows": {
        "recovery_point": {
            "states": ["discovered", "verifying", "available", "corrupt", "expired", "deleted"],
            "terminal_states": ["deleted"],
            "transitions": [
                {"command": "begin_verification", "from_state": "discovered", "to_state": "verifying"},
                {"command": "begin_verification", "from_state": "available", "to_state": "verifying"},
                {"command": "mark_available", "from_state": "verifying", "to_state": "available"},
                {"command": "mark_corrupt", "from_state": "verifying", "to_state": "corrupt"},
                {"command": "expire", "from_state": "available", "to_state": "expired"},
                {"command": "delete", "from_state": "expired", "to_state": "deleted"},
                {"command": "delete", "from_state": "corrupt", "to_state": "deleted"},
            ],
            "retention_guard_commands": ["expire"],
        },
        "restore_run": {
            "states": ["queued", "validating", "ready", "restoring", "verifying", "succeeded", "failed", "cancelled"],
            "terminal_states": ["succeeded", "failed", "cancelled"],
            "transitions": [
                {"command": "begin_validation", "from_state": "queued", "to_state": "validating"},
                {"command": "mark_ready", "from_state": "validating", "to_state": "ready"},
                {"command": "begin_restore", "from_state": "ready", "to_state": "restoring"},
                {"command": "begin_verification", "from_state": "restoring", "to_state": "verifying"},
                {"command": "succeed", "from_state": "verifying", "to_state": "succeeded"},
                {"command": "fail", "from_state": "validating", "to_state": "failed"},
                {"command": "fail", "from_state": "restoring", "to_state": "failed"},
                {"command": "fail", "from_state": "verifying", "to_state": "failed"},
                {"command": "cancel", "from_state": "queued", "to_state": "cancelled"},
                {"command": "cancel", "from_state": "validating", "to_state": "cancelled"},
                {"command": "cancel", "from_state": "ready", "to_state": "cancelled"},
            ],
            "retention_guard_commands": [],
        },
        "runbook": {
            "states": ["draft", "published", "retired"],
            "terminal_states": ["retired"],
            "transitions": [
                {"command": "publish", "from_state": "draft", "to_state": "published"},
                {"command": "retire", "from_state": "published", "to_state": "retired"},
            ],
            "retention_guard_commands": [],
        },
        "exercise": {
            "states": ["scheduled", "queued", "running", "passed", "failed", "cancelled"],
            "terminal_states": ["passed", "failed", "cancelled"],
            "transitions": [
                {"command": "queue", "from_state": "scheduled", "to_state": "queued"},
                {"command": "start", "from_state": "queued", "to_state": "running"},
                {"command": "pass", "from_state": "running", "to_state": "passed"},
                {"command": "fail", "from_state": "running", "to_state": "failed"},
                {"command": "cancel", "from_state": "scheduled", "to_state": "cancelled"},
                {"command": "cancel", "from_state": "queued", "to_state": "cancelled"},
                {"command": "cancel", "from_state": "running", "to_state": "cancelled"},
            ],
            "retention_guard_commands": [],
        },
        "step_execution": {
            "states": ["pending", "running", "passed", "failed", "degraded", "skipped"],
            "terminal_states": ["passed", "failed", "degraded", "skipped"],
            "transitions": [
                {"command": "start", "from_state": "pending", "to_state": "running"},
                {"command": "pass", "from_state": "running", "to_state": "passed"},
                {"command": "fail", "from_state": "running", "to_state": "failed"},
                {"command": "degrade", "from_state": "running", "to_state": "degraded"},
                {"command": "skip", "from_state": "pending", "to_state": "skipped"},
            ],
            "retention_guard_commands": [],
        },
    },
}

DEFAULT_CONFIGURATION_DOCUMENT: Mapping[str, Any] = MappingProxyType(_DEFAULT_CONFIGURATION_DOCUMENT)
DEFAULT_ROLLOUT: Mapping[str, Any] = MappingProxyType({"enabled": True, "roles": [], "cohorts": []})


class BDRDomainError(RuntimeError):
    """Stable service error translated by the governed API boundary."""

    def __init__(self, code: str, message: str, *, http_status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.http_status = http_status


class ResourceNotFound(BDRDomainError):
    def __init__(self, resource: str) -> None:
        super().__init__("RESOURCE_NOT_FOUND", f"{resource} was not found.", http_status=404)


class DomainConflict(BDRDomainError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, http_status=409)


class DependencyUnavailable(BDRDomainError):
    def __init__(self, capability: str) -> None:
        super().__init__(
            "CAPABILITY_UNAVAILABLE",
            f"The {capability} capability is currently unavailable.",
            http_status=503,
        )


def _validate_configuration_node(candidate: object, template: object, path: str) -> None:
    if isinstance(template, Mapping):
        if not isinstance(candidate, Mapping):
            raise BDRDomainError("INVALID_CONFIGURATION", f"{path} must be an object.")
        unknown = set(candidate) - set(template)
        missing = set(template) - set(candidate)
        if unknown or missing:
            detail = ", ".join(sorted(str(item) for item in unknown or missing))
            raise BDRDomainError("INVALID_CONFIGURATION", f"{path} has invalid keys: {detail}.")
        for key, value in template.items():
            _validate_configuration_node(candidate[key], value, f"{path}.{key}")
        return
    if isinstance(template, list):
        if not isinstance(candidate, list):
            raise BDRDomainError("INVALID_CONFIGURATION", f"{path} must be an array.")
        expected = type(template[0]) if template else None
        if expected is not None and any(type(item) is not expected for item in candidate):
            raise BDRDomainError("INVALID_CONFIGURATION", f"{path} contains an invalid value type.")
        return
    expected_type = type(template)
    if type(candidate) is not expected_type:
        raise BDRDomainError("INVALID_CONFIGURATION", f"{path} has an invalid value type.")


def validate_configuration_document(document: object) -> dict[str, Any]:
    """Validate the complete policy document and all cross-field safe limits."""

    _validate_configuration_node(document, _DEFAULT_CONFIGURATION_DOCUMENT, "document")
    assert isinstance(document, Mapping)
    normalized = copy.deepcopy(dict(document))
    positive_paths = (
        ("quota_costs", "default"),
        ("quota_costs", "backup_execution"),
        ("quota_costs", "verification"),
        ("quota_costs", "restore_validation"),
        ("quota_costs", "restore_execution"),
        ("quota_costs", "exercise_execution"),
        ("resilience", "timeout_seconds"),
        ("resilience", "max_attempts"),
        ("resilience", "initial_backoff_seconds"),
        ("resilience", "max_backoff_seconds"),
        ("resilience", "jitter_seconds"),
        ("resilience", "circuit_failure_threshold"),
        ("resilience", "circuit_reset_seconds"),
        ("resilience", "checksum_chunk_bytes"),
        ("health", "probe_timeout_seconds"),
        ("health", "probe_timeout_max_seconds"),
        ("health", "provider_stale_seconds"),
        ("health", "outbox_max_lag_seconds"),
        ("health", "exercise_freshness_seconds"),
        ("health", "registry_staleness_seconds"),
        ("health", "exercise_registry_staleness_seconds"),
        ("health", "queue_degradation_seconds"),
        ("runbooks", "default_rpo_seconds"),
        ("runbooks", "default_rto_seconds"),
        ("runbooks", "objective_min_seconds"),
        ("runbooks", "objective_max_seconds"),
        ("runbooks", "min_publish_steps"),
        ("runbooks", "unpublished_scan_limit"),
        ("steps", "default_timeout_seconds"),
        ("steps", "min_timeout_seconds"),
        ("steps", "max_timeout_seconds"),
        ("steps", "max_retry_limit"),
        ("steps", "max_components"),
        ("steps", "max_verification_checks"),
        ("steps", "max_reorder_items"),
        ("steps", "reorder_collision_offset"),
        ("exercises", "default_schedule_offset_ms"),
        ("exercises", "evidence_freshness_days"),
        ("reports", "default_interval_days"),
        ("reports", "max_interval_days"),
        ("reports", "max_results"),
        ("presentation", "duration_minute_seconds"),
        ("presentation", "duration_hour_seconds"),
        ("presentation", "byte_base"),
        ("polling", "dashboard_ms"),
        ("polling", "recovery_point_ms"),
        ("polling", "restore_ms"),
        ("polling", "exercise_ms"),
        ("polling", "exercise_page_size"),
    )
    for section, key in positive_paths:
        if normalized[section][key] <= 0:
            raise BDRDomainError("INVALID_CONFIGURATION", f"document.{section}.{key} must be positive.")
    steps = normalized["steps"]
    if not 1 <= steps["min_timeout_seconds"] <= steps["default_timeout_seconds"] <= steps["max_timeout_seconds"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Step timeout limits are inconsistent.")
    if not 0 <= steps["default_retry_limit"] <= steps["max_retry_limit"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Step retry limits are inconsistent.")
    if steps["default_on_failure"] not in steps["allowed_failure_behaviors"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Default step failure behavior is not allowed.")
    runbooks = normalized["runbooks"]
    if runbooks["objective_min_seconds"] > runbooks["objective_max_seconds"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Objective limits are inconsistent.")
    reports = normalized["reports"]
    if reports["default_bucket"] not in reports["allowed_buckets"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Default report bucket is not allowed.")
    providers = normalized["providers"]
    if not providers["storage_adapter_key"].strip():
        raise BDRDomainError("INVALID_CONFIGURATION", "Storage adapter key must not be empty.")
    restore_modes = providers["local_filesystem_restore_modes"]
    if len(restore_modes) != len(set(restore_modes)) or not set(restore_modes) <= {"full", "selective"}:
        raise BDRDomainError("INVALID_CONFIGURATION", "Local restore modes are invalid.")
    resilience = normalized["resilience"]
    if resilience["initial_backoff_seconds"] > resilience["max_backoff_seconds"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Resilience backoff limits are inconsistent.")
    health = normalized["health"]
    if health["probe_timeout_seconds"] > health["probe_timeout_max_seconds"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Health timeout limits are inconsistent.")
    if normalized["presentation"]["duration_minute_seconds"] >= normalized["presentation"]["duration_hour_seconds"]:
        raise BDRDomainError("INVALID_CONFIGURATION", "Duration display thresholds are inconsistent.")
    for key in ("compliant_percent", "noncompliant_percent"):
        if not 0.0 <= normalized["reports"][key] <= 100.0:
            raise BDRDomainError("INVALID_CONFIGURATION", f"reports.{key} must be between 0 and 100.")
    for machine_name, definition in normalized["workflows"].items():
        state_values = definition["states"]
        terminal_values = definition["terminal_states"]
        if len(state_values) != len(set(state_values)) or len(terminal_values) != len(set(terminal_values)):
            raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} has duplicate states.")
        states = set(state_values)
        terminals = set(terminal_values)
        if not terminals <= states:
            raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} has unknown terminal states.")
        edge_keys: set[tuple[str, str]] = set()
        commands: set[str] = set()
        for transition in definition["transitions"]:
            if set(transition) != {"command", "from_state", "to_state"}:
                raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} transition schema is invalid.")
            if not all(isinstance(transition[key], str) and transition[key].strip() for key in transition):
                raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} transition values must be non-empty.")
            if transition["from_state"] not in states or transition["to_state"] not in states:
                raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} transition references an unknown state.")
            edge = (transition["command"], transition["from_state"])
            if edge in edge_keys:
                raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} has a duplicate command edge.")
            if transition["from_state"] in terminals:
                raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} transitions from a terminal state.")
            edge_keys.add(edge)
            commands.add(transition["command"])
        guards = definition["retention_guard_commands"]
        if len(guards) != len(set(guards)) or not set(guards) <= commands:
            raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} has invalid guard commands.")
        if machine_name != "recovery_point" and guards:
            raise BDRDomainError("INVALID_CONFIGURATION", f"{machine_name} cannot use retention guards.")
    return normalized


def _validate_rollout(rollout: object) -> dict[str, Any]:
    if not isinstance(rollout, Mapping) or set(rollout) != {"enabled", "roles", "cohorts"}:
        raise BDRDomainError("INVALID_CONFIGURATION", "rollout must contain enabled, roles, and cohorts.")
    if type(rollout["enabled"]) is not bool:
        raise BDRDomainError("INVALID_CONFIGURATION", "rollout.enabled must be boolean.")
    for key in ("roles", "cohorts"):
        values = rollout[key]
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise BDRDomainError("INVALID_CONFIGURATION", f"rollout.{key} must contain non-empty strings.")
        if len(values) != len(set(values)):
            raise BDRDomainError("INVALID_CONFIGURATION", f"rollout.{key} must contain unique values.")
    return copy.deepcopy(dict(rollout))


def get_configuration(tenant_id: UUID, environment: str = "default") -> BDRConfiguration:
    """Return a validated tenant configuration; strict defaults remain enforceable when absent."""

    configuration = BDRConfiguration.objects.for_tenant(tenant_id).filter(environment=environment).first()
    if configuration is None:
        return BDRConfiguration(
            tenant_id=tenant_id,
            environment=environment,
            document=copy.deepcopy(_DEFAULT_CONFIGURATION_DOCUMENT),
            rollout=copy.deepcopy(dict(DEFAULT_ROLLOUT)),
            version=0,
        )
    configuration.document = validate_configuration_document(configuration.document)
    configuration.rollout = _validate_rollout(configuration.rollout)
    return configuration


def _configuration_snapshot(configuration: BDRConfiguration) -> dict[str, Any]:
    return {
        "environment": configuration.environment,
        "document": copy.deepcopy(configuration.document),
        "rollout": copy.deepcopy(configuration.rollout),
    }


def _configuration_diff(before: object, after: object, prefix: str = "") -> list[dict[str, object]]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changes: list[dict[str, object]] = []
        for key in sorted(set(before) | set(after)):
            path = f"{prefix}.{key}" if prefix else str(key)
            changes.extend(_configuration_diff(before.get(key), after.get(key), path))
        return changes
    if before != after:
        return [{"path": prefix, "before": before, "after": after}]
    return []


class ConfigurationService:
    """Only mutation boundary for versioned tenant disaster-recovery policy."""

    def current(self, tenant_id: UUID, environment: str = "default") -> BDRConfiguration:
        return get_configuration(tenant_id, environment)

    def preview(
        self, tenant_id: UUID, document: object, rollout: object | None = None, environment: str = "default"
    ) -> dict[str, object]:
        current = get_configuration(tenant_id, environment)
        validated = validate_configuration_document(document)
        validated_rollout = _validate_rollout(rollout if rollout is not None else current.rollout)
        proposed = {"environment": environment, "document": validated, "rollout": validated_rollout}
        return {
            "valid": True,
            "changes": _configuration_diff(_configuration_snapshot(current), proposed),
            "document": validated,
            "rollout": validated_rollout,
        }

    @transaction.atomic
    def update(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        document: object,
        rollout: object | None = None,
        environment: str = "default",
        rollback_of: BDRConfigurationVersion | None = None,
    ) -> BDRConfiguration:
        validated = validate_configuration_document(document)
        environment = _required_text(environment, "environment")
        configuration = (
            BDRConfiguration.objects.select_for_update().for_tenant(tenant_id).filter(environment=environment).first()
        )
        if configuration is None:
            prior: dict[str, Any] = {}
            configuration = BDRConfiguration(
                tenant_id=tenant_id,
                environment=environment,
                document=validated,
                rollout=_validate_rollout(rollout if rollout is not None else dict(DEFAULT_ROLLOUT)),
                version=1,
            )
        else:
            prior = _configuration_snapshot(configuration)
            configuration.document = validated
            configuration.rollout = _validate_rollout(rollout if rollout is not None else configuration.rollout)
            configuration.version += 1
        configuration.save()
        BDRConfigurationVersion.objects.create(
            tenant_id=tenant_id,
            configuration=configuration,
            version=configuration.version,
            actor_id=actor_id,
            correlation_id=correlation_id,
            prior_value=prior,
            new_value=_configuration_snapshot(configuration),
            rollback_of=rollback_of,
        )
        return configuration

    def versions(self, tenant_id: UUID, environment: str = "default") -> QuerySet[BDRConfigurationVersion]:
        return (
            BDRConfigurationVersion.objects.for_tenant(tenant_id)
            .filter(configuration__environment=environment)
            .order_by("-version")
        )

    def rollback(
        self, tenant_id: UUID, actor_id: UUID, correlation_id: UUID, version: int, environment: str = "default"
    ) -> BDRConfiguration:
        target = self.versions(tenant_id, environment).filter(version=version).first()
        if target is None:
            raise ResourceNotFound("Configuration version")
        snapshot = target.new_value
        return self.update(
            tenant_id,
            actor_id,
            correlation_id,
            snapshot["document"],
            snapshot["rollout"],
            environment,
            rollback_of=target,
        )

    def import_document(
        self, tenant_id: UUID, actor_id: UUID, correlation_id: UUID, payload: object
    ) -> BDRConfiguration:
        if not isinstance(payload, Mapping) or "document" not in payload:
            raise BDRDomainError("INVALID_CONFIGURATION", "Import must contain a configuration document.")
        return self.update(
            tenant_id,
            actor_id,
            correlation_id,
            payload["document"],
            payload.get("rollout"),
            str(payload.get("environment", "default")),
        )

    def export_document(self, tenant_id: UUID, environment: str = "default") -> dict[str, Any]:
        configuration = get_configuration(tenant_id, environment)
        return {
            "schema": "saraise.backup-disaster-recovery.configuration/v1",
            "version": configuration.version,
            **_configuration_snapshot(configuration),
        }


@dataclass(frozen=True, slots=True)
class BackupRequestCommand:
    backup_type: str
    scope_type: str
    scope_ref: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RestoreRunCommand:
    recovery_point_id: UUID
    target_environment: str
    target_ref: str
    restore_mode: str
    selected_components: tuple[str, ...]
    idempotency_key: str
    runbook_id: UUID | None = None
    exercise_id: UUID | None = None
    approved_by: UUID | None = None
    step_up_token: str | None = None


@dataclass(frozen=True, slots=True)
class RunbookCommand:
    name: str
    slug: str
    description: str
    scope_type: str
    scope_ref: str
    adapter_key: str | None
    rpo_target_seconds: int
    rto_target_seconds: int
    owner_id: UUID
    backup_schedule_id: UUID | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class RunbookStepCommand:
    runbook_id: UUID
    step_key: str
    position: int
    name: str
    description: str
    action_type: str
    parameters: Mapping[str, object]
    timeout_seconds: int | None = None
    retry_limit: int | None = None
    on_failure: str | None = None
    extension_action_key: str | None = None
    approval_permission: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ExerciseCommand:
    name: str
    runbook_id: UUID
    exercise_type: str
    environment: str
    scheduled_for: datetime
    idempotency_key: str
    recovery_point_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ObjectiveMeasurement:
    restore_run_id: UUID
    runbook_id: UUID | None
    rpo_seconds: int | None
    rto_seconds: int | None
    rpo_target_seconds: int | None
    rto_target_seconds: int | None
    rpo_met: bool | None
    rto_met: bool | None
    measured_at: datetime
    outcome: str


@dataclass(frozen=True, slots=True)
class ReadinessSummary:
    protected: bool
    calculated_at: datetime
    rpo_compliance_percent: float
    rto_compliance_percent: float
    last_verified_recovery_point: RecoveryPoint | None
    latest_passed_exercise: DRExercise | None
    latest_successful_restore: RestoreRun | None
    latest_failed_restore: RestoreRun | None
    next_scheduled_exercise: DRExercise | None
    stale_runbook_count: int
    unpublished_runbook_count: int
    current_rpo_breaches: int
    current_rto_breaches: int
    provider_state: str
    queue_state: str
    provider_message: str


@dataclass(frozen=True, slots=True)
class ObjectiveReportBucket:
    period_start: datetime
    period_end: datetime
    runbook_id: UUID
    runbook_name: str
    runbook_version: int
    restore_count: int
    failed_restore_count: int
    rpo_compliance_percent: float
    rto_compliance_percent: float
    measurements: tuple[ObjectiveMeasurement, ...]


@dataclass(frozen=True, slots=True)
class ObjectiveReport:
    from_at: datetime
    to: datetime
    bucket: str
    total_restores: int
    failed_restores: int
    rpo_compliance_percent: float
    rto_compliance_percent: float
    buckets: tuple[ObjectiveReportBucket, ...]


def _required_text(value: str, field: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise BDRDomainError("VALIDATION_ERROR", f"{field} must not be empty.")
    return normalized


def _transition(machine: Any, aggregate: Any, command: str, key: str) -> Any:
    try:
        return machine.apply(
            aggregate,
            command,
            tenant_id=aggregate.tenant_id,
            transition_key=_required_text(key, "transition_key"),
        )
    except StateMachineError as exc:
        raise DomainConflict("INVALID_TRANSITION", "The requested lifecycle transition is not valid.") from exc


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, AdapterNotRegistered):
        return "ADAPTER_UNAVAILABLE"
    if isinstance(exc, TimeoutError):
        return "PROVIDER_TIMEOUT"
    return "PROVIDER_FAILURE"


def _audit_uuid(value: object, namespace: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return UUID(bytes=__import__("hashlib").sha256(f"{namespace}:{value}".encode()).digest()[:16])


def _catalog() -> Any:
    try:
        return get_backup_catalog()
    except AdapterNotRegistered as exc:
        raise DependencyUnavailable("backup catalog") from exc


def _adapter(key: str) -> Any:
    try:
        return get_storage_adapter(key)
    except AdapterNotRegistered as exc:
        raise DependencyUnavailable(f"storage adapter '{key}'") from exc


class BackupExecutionFacade:
    """Own backup requests while delegating capture/catalog authority."""

    def request_backup(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        command: BackupRequestCommand,
    ) -> OperationResult[BackupRequestReceipt]:
        scope_ref = _required_text(command.scope_ref, "scope_ref")
        idempotency_key = _required_text(command.idempotency_key, "idempotency_key")
        try:
            backup_type = PortBackupType(command.backup_type)
            scope_type = PortScopeType(command.scope_type)
        except ValueError as exc:
            raise BDRDomainError("VALIDATION_ERROR", "Unsupported backup scope or type.") from exc

        with transaction.atomic():
            receipt = _catalog().request_backup(
                tenant_id,
                actor_id,
                backup_type=backup_type,
                scope_type=scope_type,
                scope_ref=scope_ref,
                idempotency_key=idempotency_key,
            )
            job = enqueue(
                tenant_id,
                actor_id,
                BACKUP_REQUEST_COMMAND,
                {"backup_job_id": str(receipt.backup_job_id)},
                f"bdr:backup:{idempotency_key}",
            )
        return OperationResult.succeeded(
            receipt,
            evidence={"async_job_id": str(job.id), "backup_job_id": str(receipt.backup_job_id)},
            provider="backup_catalog",
        )

    def get_backup_status(self, tenant_id: UUID, backup_job_id: UUID) -> BackupStatusSnapshot:
        return _catalog().get_backup_status(tenant_id, backup_job_id)

    def register_recovery_point(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        backup_job_id: UUID,
    ) -> RecoveryPoint:
        existing = RecoveryPoint.objects.for_tenant(tenant_id).filter(backup_job_id=backup_job_id).first()
        if existing is not None:
            return existing
        descriptor = _catalog().describe_completed_artifact(tenant_id, backup_job_id)
        with transaction.atomic():
            try:
                point, _ = RecoveryPoint.objects.get_or_create(
                    tenant_id=tenant_id,
                    backup_job_id=backup_job_id,
                    defaults={
                        "backup_archive_id": descriptor.backup_archive_id,
                        "adapter_key": descriptor.adapter_key,
                        "artifact_locator_ref": descriptor.artifact_locator_ref,
                        "encryption_key_ref": descriptor.encryption_key_ref,
                        "scope_type": descriptor.scope_type.value,
                        "scope_ref": descriptor.scope_ref,
                        "backup_type": descriptor.backup_type.value,
                        "data_cutoff_at": descriptor.data_cutoff_at,
                        "captured_at": descriptor.captured_at,
                        "expires_at": descriptor.expires_at,
                        "size_bytes": descriptor.size_bytes,
                        "checksum_algorithm": descriptor.checksum_algorithm,
                        "checksum_digest": descriptor.checksum_digest,
                        "created_by": actor_id,
                    },
                )
            except IntegrityError:
                point = RecoveryPoint.objects.for_tenant(tenant_id).get(backup_job_id=backup_job_id)
        return point

    def execute_backup_request(self, tenant_id: UUID, job_id: UUID) -> Mapping[str, object]:
        job = AsyncJob.objects.for_tenant(tenant_id).filter(id=job_id).first()
        if job is None:
            raise ResourceNotFound("Async job")
        try:
            backup_job_id = UUID(str(job.payload["backup_job_id"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise BDRDomainError("INVALID_JOB_PAYLOAD", "The durable backup command is invalid.") from exc
        status = self.get_backup_status(tenant_id, backup_job_id)
        if status.status != BackupStatus.COMPLETED:
            raise DependencyUnavailable("completed backup artifact")
        point = self.register_recovery_point(tenant_id, UUID(str(job.actor_id)), backup_job_id)
        return {"backup_job_id": str(backup_job_id), "recovery_point_id": str(point.id)}


class RecoveryPointService:
    def get_recovery_point(self, tenant_id: UUID, recovery_point_id: UUID) -> RecoveryPoint:
        point = RecoveryPoint.objects.for_tenant(tenant_id).filter(id=recovery_point_id).first()
        if point is None:
            raise ResourceNotFound("Recovery point")
        return point

    def list_recovery_points(
        self, tenant_id: UUID, filters: Mapping[str, object] | None = None
    ) -> QuerySet[RecoveryPoint]:
        queryset = RecoveryPoint.objects.for_tenant(tenant_id)
        for field in ("status", "scope_type", "scope_ref"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters and filters.get("captured_after"):
            queryset = queryset.filter(captured_at__gte=filters["captured_after"])
        if filters and filters.get("captured_before"):
            queryset = queryset.filter(captured_at__lte=filters["captured_before"])
        return queryset.order_by("-captured_at", "-id")

    def request_verification(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        recovery_point_id: UUID,
        idempotency_key: str,
    ) -> AsyncJob:
        point = self.get_recovery_point(tenant_id, recovery_point_id)
        with transaction.atomic():
            point = _transition(
                RECOVERY_POINT_MACHINE,
                point,
                "begin_verification",
                f"verify:{idempotency_key}:start",
            )
            job = enqueue(
                tenant_id,
                actor_id,
                VERIFY_POINT_COMMAND,
                {"recovery_point_id": str(point.id)},
                f"bdr:verify:{idempotency_key}",
            )
        return job

    def execute_verification(self, tenant_id: UUID, recovery_point_id: UUID, job_id: UUID) -> RecoveryPoint:
        point = self.get_recovery_point(tenant_id, recovery_point_id)
        job = AsyncJob.objects.for_tenant(tenant_id).filter(id=job_id).first()
        actor_id = _audit_uuid(job.actor_id if job else job_id, "verification-actor")
        correlation_id = _audit_uuid(job.correlation_id if job else job_id, "verification-correlation")
        descriptor = _catalog().describe_completed_artifact(tenant_id, point.backup_job_id)
        try:
            result = _adapter(point.adapter_key).validate_artifact(tenant_id, descriptor, idempotency_key=str(job_id))
        except Exception as exc:
            evidence = {"valid": False, "error_code": _safe_error_code(exc)}
            self._append_evidence(point, actor_id, correlation_id, evidence)
            _transition(RECOVERY_POINT_MACHINE, point, "mark_corrupt", f"job:{job_id}:corrupt")
            raise

        evidence = {
            "valid": result.valid,
            "checksum_matches": result.checksum_matches,
            "artifact_available": result.artifact_available,
            "encryption_metadata_valid": result.encryption_metadata_valid,
            "provider_acknowledged": result.provider_acknowledged,
            "error_code": result.error_code,
        }
        self._append_evidence(point, actor_id, correlation_id, evidence)
        if all(
            (
                result.valid,
                result.checksum_matches,
                result.artifact_available,
                result.encryption_metadata_valid,
                result.provider_acknowledged,
            )
        ):
            point.verified_at = timezone.now()
            point.save(update_fields=["verified_at", "updated_at"])
            return _transition(RECOVERY_POINT_MACHINE, point, "mark_available", f"job:{job_id}:available")
        return _transition(RECOVERY_POINT_MACHINE, point, "mark_corrupt", f"job:{job_id}:corrupt")

    @staticmethod
    @transaction.atomic
    def _append_evidence(
        point: RecoveryPoint, actor_id: UUID, correlation_id: UUID, evidence: Mapping[str, object]
    ) -> RecoveryPointEvidence:
        locked = RecoveryPoint.objects.select_for_update().for_tenant(point.tenant_id).get(id=point.id)
        latest = locked.verification_events.order_by("-sequence").first()
        event = RecoveryPointEvidence.objects.create(
            tenant_id=point.tenant_id,
            recovery_point=locked,
            sequence=(latest.sequence if latest else 0) + 1,
            actor_id=actor_id,
            correlation_id=correlation_id,
            evidence=dict(evidence),
        )
        locked.latest_verification_evidence = event
        locked.save(update_fields=["latest_verification_evidence", "updated_at"])
        point.latest_verification_evidence = event
        return event

    def expire_recovery_point(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        recovery_point_id: UUID,
        transition_key: str,
    ) -> RecoveryPoint:
        del actor_id
        point = self.get_recovery_point(tenant_id, recovery_point_id)
        if point.expires_at is None or point.expires_at > timezone.now():
            raise DomainConflict("RETENTION_NOT_EXPIRED", "The recovery point has not reached its expiry time.")
        return _transition(RECOVERY_POINT_MACHINE, point, "expire", transition_key)


class RestoreService:
    def get_restore_run(self, tenant_id: UUID, restore_run_id: UUID) -> RestoreRun:
        run = (
            RestoreRun.objects.for_tenant(tenant_id)
            .select_related("recovery_point", "runbook", "exercise")
            .filter(id=restore_run_id)
            .first()
        )
        if run is None:
            raise ResourceNotFound("Restore run")
        return run

    def list_restore_runs(self, tenant_id: UUID, filters: Mapping[str, object] | None = None) -> QuerySet[RestoreRun]:
        queryset = RestoreRun.objects.for_tenant(tenant_id).select_related("recovery_point", "runbook", "exercise")
        for field in ("status", "target_environment", "recovery_point"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters and filters.get("requested_after"):
            queryset = queryset.filter(requested_at__gte=filters["requested_after"])
        if filters and filters.get("requested_before"):
            queryset = queryset.filter(requested_at__lte=filters["requested_before"])
        return queryset.order_by("-requested_at", "-id")

    def create_restore_run(self, tenant_id: UUID, actor_id: UUID, command: RestoreRunCommand) -> RestoreRun:
        policy = get_configuration(tenant_id).document
        restore_policy = policy["restores"]
        step_policy = policy["steps"]
        if len(command.selected_components) > int(step_policy["max_components"]):
            raise BDRDomainError("VALIDATION_ERROR", "Too many restore components were selected.")
        if (
            command.restore_mode == RestoreMode.SELECTIVE
            and restore_policy["selective_requires_components"]
            and not command.selected_components
        ):
            raise BDRDomainError("VALIDATION_ERROR", "Selective restores require components.")
        if (
            command.restore_mode == RestoreMode.FULL
            and restore_policy["full_prohibits_components"]
            and command.selected_components
        ):
            raise BDRDomainError("VALIDATION_ERROR", "Full restores do not accept components.")
        if command.target_environment == TargetEnvironment.PRODUCTION:
            if command.step_up_token:
                # Proof input is never accepted when no verifier capability exists.
                raise DependencyUnavailable("production restore step-up verification")
            if restore_policy["production_requires_approver"] and command.approved_by is None:
                raise BDRDomainError(
                    "PRODUCTION_APPROVAL_REQUIRED",
                    "A distinct, verified production approval is required.",
                    http_status=403,
                )
            if not restore_policy["production_enabled"]:
                raise DependencyUnavailable("production restore")
            # No verifier is registered in this foundation. Possession of an opaque
            # token is never treated as approval; enabling the flag still fails closed.
            raise DependencyUnavailable("production restore step-up verification")
        existing = RestoreRun.objects.for_tenant(tenant_id).filter(idempotency_key=command.idempotency_key).first()
        if existing is not None:
            return existing
        if (
            RestoreRun.objects.for_tenant(tenant_id)
            .filter(
                target_ref=command.target_ref,
                status__in=RestoreRun.ACTIVE_TARGET_STATUSES,
            )
            .exists()
        ):
            raise DomainConflict("TARGET_BUSY", "The restore target already has an active operation.")
        point = RecoveryPointService().get_recovery_point(tenant_id, command.recovery_point_id)
        if point.status != RecoveryPointStatus.AVAILABLE:
            raise DomainConflict("RECOVERY_POINT_UNAVAILABLE", "Only verified recovery points can be restored.")
        runbook = None
        if command.runbook_id:
            runbook = (
                DRRunbook.objects.for_tenant(tenant_id)
                .filter(id=command.runbook_id, status=RunbookStatus.PUBLISHED, deleted_at__isnull=True)
                .first()
            )
            if runbook is None:
                raise ResourceNotFound("Published runbook")
        exercise = None
        if command.exercise_id:
            exercise = DRExercise.objects.for_tenant(tenant_id).filter(id=command.exercise_id).first()
            if exercise is None:
                raise ResourceNotFound("Exercise")
        with transaction.atomic():
            try:
                run = RestoreRun.objects.create(
                    tenant_id=tenant_id,
                    recovery_point=point,
                    runbook=runbook,
                    exercise=exercise,
                    target_environment=command.target_environment,
                    target_ref=_required_text(command.target_ref, "target_ref"),
                    restore_mode=command.restore_mode,
                    selected_components=list(command.selected_components),
                    idempotency_key=_required_text(command.idempotency_key, "idempotency_key"),
                    requested_by=actor_id,
                    approved_by=command.approved_by,
                    requested_at=timezone.now(),
                )
            except (IntegrityError, DjangoValidationError) as exc:
                duplicate = (
                    RestoreRun.objects.for_tenant(tenant_id).filter(idempotency_key=command.idempotency_key).first()
                )
                if duplicate is not None:
                    return duplicate
                active_target = (
                    RestoreRun.objects.for_tenant(tenant_id)
                    .filter(
                        target_ref=command.target_ref,
                        status__in=RestoreRun.ACTIVE_TARGET_STATUSES,
                    )
                    .exists()
                )
                if active_target:
                    raise DomainConflict("TARGET_BUSY", "The restore target already has an active operation.") from exc
                if isinstance(exc, DjangoValidationError):
                    raise BDRDomainError("VALIDATION_ERROR", "The restore request failed domain validation.") from exc
                raise
            try:
                run = _transition(RESTORE_RUN_MACHINE, run, "begin_validation", f"create:{run.id}:validate")
            except DjangoValidationError as exc:
                raise DomainConflict("TARGET_BUSY", "The restore target already has an active operation.") from exc
            job = enqueue(
                tenant_id,
                actor_id,
                VALIDATE_RESTORE_COMMAND,
                {"restore_run_id": str(run.id)},
                f"bdr:restore-validate:{command.idempotency_key}",
            )
            run.async_job_id = job.id
            run.save(update_fields=["async_job_id", "updated_at"])
        return run

    def validate_restore(self, tenant_id: UUID, restore_run_id: UUID, job_id: UUID) -> RestoreRun:
        run = self.get_restore_run(tenant_id, restore_run_id)
        descriptor = _catalog().describe_completed_artifact(tenant_id, run.recovery_point.backup_job_id)
        adapter = _adapter(run.recovery_point.adapter_key)
        result = adapter.validate_artifact(tenant_id, descriptor, idempotency_key=str(job_id))
        target = RestoreTarget(
            environment=RestoreEnvironment(run.target_environment),
            target_ref=run.target_ref,
            mode=PortRestoreMode(run.restore_mode),
            selected_components=tuple(run.selected_components),
        )
        if not isinstance(adapter, RestorePreflightPort):
            raise DependencyUnavailable("restore target preflight")
        preflight = adapter.validate_restore_target(
            tenant_id, descriptor, target, idempotency_key=f"{job_id}:preflight"
        )
        run.validation_evidence = {
            "artifact_valid": result.valid,
            "checksum_matches": result.checksum_matches,
            "capacity_valid": preflight.capacity_valid,
            "compatibility_valid": preflight.compatibility_valid,
            "target_available": preflight.target_available,
            "preflight_evidence": dict(preflight.evidence),
            "error_code": result.error_code or preflight.error_code,
        }
        run.save(update_fields=["validation_evidence", "updated_at"])
        if not all(
            (
                result.valid,
                result.checksum_matches,
                result.artifact_available,
                preflight.capacity_valid,
                preflight.compatibility_valid,
                preflight.target_available,
            )
        ):
            run.error_code = result.error_code or preflight.error_code or "RESTORE_PREFLIGHT_FAILED"
            run.error_message = "Restore validation did not establish artifact integrity."
            run.save(update_fields=["error_code", "error_message", "updated_at"])
            return _transition(RESTORE_RUN_MACHINE, run, "fail", f"job:{job_id}:invalid")
        return _transition(RESTORE_RUN_MACHINE, run, "mark_ready", f"job:{job_id}:ready")

    def execute_restore(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        restore_run_id: UUID,
        idempotency_key: str,
    ) -> AsyncJob:
        run = self.get_restore_run(tenant_id, restore_run_id)
        if run.status != RestoreRunStatus.READY:
            raise DomainConflict("RESTORE_NOT_READY", "The restore must pass preflight validation first.")
        with transaction.atomic():
            job = enqueue(
                tenant_id,
                actor_id,
                EXECUTE_RESTORE_COMMAND,
                {"restore_run_id": str(run.id)},
                f"bdr:restore-execute:{idempotency_key}",
            )
            run.async_job_id = job.id
            run.save(update_fields=["async_job_id", "updated_at"])
        return job

    def execute_restore_job(self, tenant_id: UUID, restore_run_id: UUID, job_id: UUID) -> RestoreRun:
        run = self.get_restore_run(tenant_id, restore_run_id)
        run = _transition(RESTORE_RUN_MACHINE, run, "begin_restore", f"job:{job_id}:restore")
        run.started_at = run.started_at or timezone.now()
        run.save(update_fields=["started_at", "updated_at"])
        descriptor = _catalog().describe_completed_artifact(tenant_id, run.recovery_point.backup_job_id)
        target = RestoreTarget(
            environment=RestoreEnvironment(run.target_environment),
            target_ref=run.target_ref,
            mode=PortRestoreMode(run.restore_mode),
            selected_components=tuple(run.selected_components),
        )
        try:
            receipt = _adapter(run.recovery_point.adapter_key).restore(
                tenant_id, descriptor, target, idempotency_key=str(job_id)
            )
        except Exception as exc:
            run.error_code = _safe_error_code(exc)
            run.error_message = "The storage provider did not complete the restore."
            run.save(update_fields=["error_code", "error_message", "updated_at"])
            _transition(RESTORE_RUN_MACHINE, run, "fail", f"job:{job_id}:provider-failed")
            raise
        if not receipt.accepted or not receipt.completed:
            run.error_code = "RESTORE_NOT_COMPLETED"
            run.error_message = "The provider did not acknowledge a completed restore."
            run.save(update_fields=["error_code", "error_message", "updated_at"])
            return _transition(RESTORE_RUN_MACHINE, run, "fail", f"job:{job_id}:not-completed")
        run.validation_evidence = {
            **run.validation_evidence,
            "restore_receipt": {
                "operation_id": receipt.operation_id,
                "accepted": receipt.accepted,
                "completed": receipt.completed,
                "evidence": {
                    key: receipt.evidence[key]
                    for key in ("target_ref", "checksum_digest", "size_bytes")
                    if key in receipt.evidence
                },
            },
        }
        run.save(update_fields=["validation_evidence", "updated_at"])
        run = _transition(RESTORE_RUN_MACHINE, run, "begin_verification", f"job:{job_id}:verify")
        return self.verify_restore(tenant_id, run.id, job_id)

    def verify_restore(self, tenant_id: UUID, restore_run_id: UUID, job_id: UUID) -> RestoreRun:
        run = self.get_restore_run(tenant_id, restore_run_id)
        receipt_data = run.validation_evidence.get("restore_receipt", {})
        if not isinstance(receipt_data, Mapping):
            raise BDRDomainError("INVALID_RESTORE_EVIDENCE", "Restore acknowledgement is missing.")
        receipt = RestoreProviderReceipt(
            operation_id=str(receipt_data.get("operation_id", "")),
            accepted=receipt_data.get("accepted") is True,
            completed=receipt_data.get("completed") is True,
            evidence=(
                dict(receipt_data.get("evidence", {})) if isinstance(receipt_data.get("evidence"), Mapping) else {}
            ),
        )
        result = _adapter(run.recovery_point.adapter_key).verify_restore(
            tenant_id, receipt, idempotency_key=f"{job_id}:verify"
        )
        run.completed_at = timezone.now()
        run.verification_evidence = {
            "verified": result.verified,
            "provider_acknowledged": receipt.accepted and receipt.completed,
            "error_code": result.error_code,
        }
        if not result.verified:
            run.error_code = result.error_code or "RESTORE_VERIFICATION_FAILED"
            run.error_message = "Post-restore verification failed."
            adapter = _adapter(run.recovery_point.adapter_key)
            if not isinstance(adapter, RestoreCompensationPort):
                run.compensation_state = "unavailable"
                run.compensation_evidence = {"error_code": "COMPENSATION_UNAVAILABLE"}
                run.save(
                    update_fields=[
                        "completed_at",
                        "verification_evidence",
                        "error_code",
                        "error_message",
                        "compensation_state",
                        "compensation_evidence",
                        "updated_at",
                    ]
                )
                _transition(RESTORE_RUN_MACHINE, run, "fail", f"job:{job_id}:verification-failed")
                raise DependencyUnavailable("restore compensation")
            try:
                compensation = adapter.compensate_restore(tenant_id, receipt, idempotency_key=f"{job_id}:compensate")
            except Exception as exc:
                run.compensation_state = "failed"
                run.compensation_evidence = {"error_code": _safe_error_code(exc)}
                run.save(
                    update_fields=[
                        "completed_at",
                        "verification_evidence",
                        "error_code",
                        "error_message",
                        "compensation_state",
                        "compensation_evidence",
                        "updated_at",
                    ]
                )
                _transition(RESTORE_RUN_MACHINE, run, "fail", f"job:{job_id}:verification-failed")
                raise DependencyUnavailable("restore compensation") from exc
            run.compensation_state = "completed" if compensation.compensated else "failed"
            run.compensation_evidence = {
                "compensated": compensation.compensated,
                "error_code": compensation.error_code,
                "evidence": dict(compensation.evidence),
            }
            run.save(
                update_fields=[
                    "completed_at",
                    "verification_evidence",
                    "error_code",
                    "error_message",
                    "compensation_state",
                    "compensation_evidence",
                    "updated_at",
                ]
            )
            failed_run = _transition(RESTORE_RUN_MACHINE, run, "fail", f"job:{job_id}:verification-failed")
            if not compensation.compensated:
                raise DependencyUnavailable("restore compensation")
            return failed_run
        measurement = RecoveryObjectiveService().calculate_restore_objectives(tenant_id, run.id, persist=False)
        run.achieved_rpo_seconds = measurement.rpo_seconds
        run.achieved_rto_seconds = measurement.rto_seconds
        run.error_code = ""
        run.error_message = ""
        run.save(
            update_fields=[
                "completed_at",
                "verification_evidence",
                "achieved_rpo_seconds",
                "achieved_rto_seconds",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return _transition(RESTORE_RUN_MACHINE, run, "succeed", f"job:{job_id}:succeeded")

    def cancel_restore(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        restore_run_id: UUID,
        transition_key: str,
    ) -> RestoreRun:
        del actor_id
        run = self.get_restore_run(tenant_id, restore_run_id)
        if run.status not in {RestoreRunStatus.QUEUED, RestoreRunStatus.VALIDATING, RestoreRunStatus.READY}:
            raise DomainConflict("RESTORE_IRREVERSIBLE", "Restoration has passed the cancellable boundary.")
        run.completed_at = timezone.now()
        run.save(update_fields=["completed_at", "updated_at"])
        return _transition(RESTORE_RUN_MACHINE, run, "cancel", transition_key)


class RunbookService:
    def get_runbook(self, tenant_id: UUID, runbook_id: UUID, *, include_deleted: bool = False) -> DRRunbook:
        queryset = DRRunbook.objects.for_tenant(tenant_id)
        if not include_deleted:
            queryset = queryset.filter(deleted_at__isnull=True)
        runbook = queryset.filter(id=runbook_id).first()
        if runbook is None:
            raise ResourceNotFound("Runbook")
        return runbook

    def list_runbooks(self, tenant_id: UUID, filters: Mapping[str, object] | None = None) -> QuerySet[DRRunbook]:
        queryset = DRRunbook.objects.for_tenant(tenant_id).filter(deleted_at__isnull=True)
        for field in ("status", "scope_type", "owner_id"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        return queryset.order_by("-updated_at", "name", "version")

    def create_runbook(self, tenant_id: UUID, actor_id: UUID, command: RunbookCommand) -> DRRunbook:
        idempotency_key = command.idempotency_key or f"runbook:create:{actor_id}:{command.slug}"
        existing = DRRunbook.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
        policy = get_configuration(tenant_id).document
        adapter_key = command.adapter_key or str(policy["providers"]["storage_adapter_key"])
        objectives = policy["runbooks"]
        if (
            not int(objectives["objective_min_seconds"])
            <= command.rpo_target_seconds
            <= int(objectives["objective_max_seconds"])
        ):
            raise BDRDomainError("VALIDATION_ERROR", "RPO target is outside configured safe limits.")
        if (
            not int(objectives["objective_min_seconds"])
            <= command.rto_target_seconds
            <= int(objectives["objective_max_seconds"])
        ):
            raise BDRDomainError("VALIDATION_ERROR", "RTO target is outside configured safe limits.")
        _adapter(adapter_key)
        if command.backup_schedule_id:
            snapshot = _catalog().validate_schedule(tenant_id, command.backup_schedule_id)
            if not snapshot.active:
                raise DomainConflict("BACKUP_SCHEDULE_INACTIVE", "The selected backup schedule is inactive.")
        return DRRunbook.objects.create(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            name=_required_text(command.name, "name"),
            slug=_required_text(command.slug, "slug").lower(),
            description=command.description,
            scope_type=command.scope_type,
            scope_ref=_required_text(command.scope_ref, "scope_ref"),
            backup_schedule_id=command.backup_schedule_id,
            adapter_key=adapter_key,
            rpo_target_seconds=command.rpo_target_seconds,
            rto_target_seconds=command.rto_target_seconds,
            owner_id=command.owner_id,
            created_by=actor_id,
            updated_by=actor_id,
        )

    def update_draft(
        self, tenant_id: UUID, actor_id: UUID, runbook_id: UUID, changes: Mapping[str, object]
    ) -> DRRunbook:
        allowed = {
            "name",
            "description",
            "scope_type",
            "scope_ref",
            "backup_schedule_id",
            "adapter_key",
            "rpo_target_seconds",
            "rto_target_seconds",
            "owner_id",
        }
        if set(changes) - allowed:
            raise BDRDomainError("VALIDATION_ERROR", "Unsupported runbook field.")
        with transaction.atomic():
            runbook = (
                DRRunbook.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(id=runbook_id, deleted_at__isnull=True)
                .first()
            )
            if runbook is None:
                raise ResourceNotFound("Runbook")
            if runbook.status != RunbookStatus.DRAFT:
                raise DomainConflict("RUNBOOK_IMMUTABLE", "Published runbooks must be cloned before editing.")
            adapter_key = str(changes.get("adapter_key", runbook.adapter_key))
            _adapter(adapter_key)
            schedule_id = changes.get("backup_schedule_id", runbook.backup_schedule_id)
            if schedule_id:
                _catalog().validate_schedule(tenant_id, UUID(str(schedule_id)))
            for field, value in changes.items():
                setattr(runbook, field, value)
            runbook.updated_by = actor_id
            runbook.save()
            return runbook

    def clone_version(
        self, tenant_id: UUID, actor_id: UUID, runbook_id: UUID, idempotency_key: str | None = None
    ) -> DRRunbook:
        mutation_key = idempotency_key or f"runbook:clone:{actor_id}:{runbook_id}"
        replay = DRRunbook.objects.for_tenant(tenant_id).filter(idempotency_key=mutation_key).first()
        if replay is not None:
            return replay
        with transaction.atomic():
            source = (
                DRRunbook.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(id=runbook_id, deleted_at__isnull=True)
                .first()
            )
            if source is None:
                raise ResourceNotFound("Runbook")
            if source.status not in {RunbookStatus.PUBLISHED, RunbookStatus.RETIRED}:
                raise DomainConflict("RUNBOOK_NOT_VERSIONABLE", "Only released runbooks can be cloned.")
            latest = (
                DRRunbook.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(slug=source.slug)
                .order_by("-version")
                .first()
            )
            clone = DRRunbook.objects.create(
                tenant_id=tenant_id,
                idempotency_key=mutation_key,
                name=source.name,
                slug=source.slug,
                version=(latest.version if latest else source.version) + 1,
                description=source.description,
                scope_type=source.scope_type,
                scope_ref=source.scope_ref,
                backup_schedule_id=source.backup_schedule_id,
                adapter_key=source.adapter_key,
                rpo_target_seconds=source.rpo_target_seconds,
                rto_target_seconds=source.rto_target_seconds,
                owner_id=source.owner_id,
                supersedes=source,
                created_by=actor_id,
                updated_by=actor_id,
            )
            steps = source.steps.filter(deleted_at__isnull=True).order_by("position")
            for step in steps:
                RunbookStep.objects.create(
                    tenant_id=tenant_id,
                    idempotency_key=f"runbook:clone-step:{clone.id}:{step.step_key}",
                    runbook=clone,
                    step_key=step.step_key,
                    position=step.position,
                    name=step.name,
                    description=step.description,
                    action_type=step.action_type,
                    extension_action_key=step.extension_action_key,
                    parameters=step.parameters,
                    timeout_seconds=step.timeout_seconds,
                    retry_limit=step.retry_limit,
                    on_failure=step.on_failure,
                    approval_permission=step.approval_permission,
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            return clone

    def publish(self, tenant_id: UUID, actor_id: UUID, runbook_id: UUID, transition_key: str) -> DRRunbook:
        minimum_steps = int(get_configuration(tenant_id).document["runbooks"]["min_publish_steps"])
        with transaction.atomic():
            runbook = (
                DRRunbook.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(id=runbook_id, deleted_at__isnull=True)
                .first()
            )
            if runbook is None:
                raise ResourceNotFound("Runbook")
            if runbook.status != RunbookStatus.DRAFT:
                raise DomainConflict("RUNBOOK_NOT_DRAFT", "Only draft runbooks can be published.")
            steps = list(runbook.steps.filter(deleted_at__isnull=True).order_by("position"))
            if len(steps) < minimum_steps:
                raise BDRDomainError("RUNBOOK_EMPTY", "The runbook does not meet the configured active-step minimum.")
            _adapter(runbook.adapter_key)
            for step in steps:
                if step.action_type == RunbookActionType.EXTENSION:
                    try:
                        get_extension_action(str(step.extension_action_key))
                    except AdapterNotRegistered as exc:
                        raise DependencyUnavailable(f"extension action '{step.extension_action_key}'") from exc
            previous = (
                DRRunbook.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(slug=runbook.slug, status=RunbookStatus.PUBLISHED, deleted_at__isnull=True)
                .exclude(id=runbook.id)
                .first()
            )
            if previous is not None:
                previous.retired_at = timezone.now()
                previous.updated_by = actor_id
                previous.save(update_fields=["retired_at", "updated_by", "updated_at"])
                _transition(RUNBOOK_MACHINE, previous, "retire", f"{transition_key}:superseded")
            runbook.published_at = timezone.now()
            runbook.updated_by = actor_id
            runbook.save(update_fields=["published_at", "updated_by", "updated_at"])
            return _transition(RUNBOOK_MACHINE, runbook, "publish", transition_key)

    def retire(self, tenant_id: UUID, actor_id: UUID, runbook_id: UUID, transition_key: str) -> DRRunbook:
        runbook = self.get_runbook(tenant_id, runbook_id)
        runbook.retired_at = timezone.now()
        runbook.updated_by = actor_id
        runbook.save(update_fields=["retired_at", "updated_by", "updated_at"])
        return _transition(RUNBOOK_MACHINE, runbook, "retire", transition_key)

    def soft_delete_draft(self, tenant_id: UUID, actor_id: UUID, runbook_id: UUID) -> None:
        runbook = self.get_runbook(tenant_id, runbook_id)
        if runbook.status != RunbookStatus.DRAFT:
            raise DomainConflict("RUNBOOK_IMMUTABLE", "Only drafts can be deleted.")
        runbook.deleted_at = timezone.now()
        runbook.deleted_by = actor_id
        runbook.updated_by = actor_id
        runbook.save(update_fields=["deleted_at", "deleted_by", "updated_by", "updated_at"])

    def create_step(self, tenant_id: UUID, actor_id: UUID, command: RunbookStepCommand) -> RunbookStep:
        step_policy = get_configuration(tenant_id).document["steps"]
        idempotency_key = command.idempotency_key or f"runbook:step:{actor_id}:{command.runbook_id}:{command.step_key}"
        replay = RunbookStep.objects.for_tenant(tenant_id).filter(idempotency_key=idempotency_key).first()
        if replay is not None:
            return replay
        runbook = self.get_runbook(tenant_id, command.runbook_id)
        if step_policy["require_draft_for_edits"] and runbook.status != RunbookStatus.DRAFT:
            raise DomainConflict("RUNBOOK_IMMUTABLE", "Steps can only be added to a draft.")
        if command.action_type == RunbookActionType.EXTENSION:
            try:
                get_extension_action(str(command.extension_action_key))
            except AdapterNotRegistered as exc:
                raise DependencyUnavailable(f"extension action '{command.extension_action_key}'") from exc
        timeout_seconds = (
            command.timeout_seconds
            if command.timeout_seconds is not None
            else int(step_policy["default_timeout_seconds"])
        )
        retry_limit = (
            command.retry_limit if command.retry_limit is not None else int(step_policy["default_retry_limit"])
        )
        on_failure = command.on_failure or str(step_policy["default_on_failure"])
        if not int(step_policy["min_timeout_seconds"]) <= timeout_seconds <= int(step_policy["max_timeout_seconds"]):
            raise BDRDomainError("VALIDATION_ERROR", "Step timeout is outside configured safe limits.")
        if not 0 <= retry_limit <= int(step_policy["max_retry_limit"]):
            raise BDRDomainError("VALIDATION_ERROR", "Step retry limit is outside configured safe limits.")
        if on_failure not in step_policy["allowed_failure_behaviors"]:
            raise BDRDomainError("VALIDATION_ERROR", "Step failure behavior is not allowed.")
        normalized_parameters = dict(command.parameters)
        if command.action_type == RunbookActionType.VERIFY:
            checks = normalized_parameters.get("checks", list(step_policy["allowed_verification_checks"]))
            allowed_checks = set(step_policy["allowed_verification_checks"])
            if (
                not isinstance(checks, list)
                or len(checks) > int(step_policy["max_verification_checks"])
                or any(not isinstance(check, str) or check not in allowed_checks for check in checks)
            ):
                raise BDRDomainError("VALIDATION_ERROR", "Verification checks are outside configured limits.")
            normalized_parameters["checks"] = checks
        if (
            command.action_type == RunbookActionType.MANUAL_APPROVAL
            and step_policy["require_manual_approval_permission"]
            and not command.approval_permission
        ):
            raise BDRDomainError("VALIDATION_ERROR", "Manual approval permission is required.")
        return RunbookStep.objects.create(
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            runbook=runbook,
            step_key=command.step_key,
            position=command.position,
            name=command.name,
            description=command.description,
            action_type=command.action_type,
            extension_action_key=command.extension_action_key,
            parameters=normalized_parameters,
            timeout_seconds=timeout_seconds,
            retry_limit=retry_limit,
            on_failure=on_failure,
            approval_permission=command.approval_permission,
            created_by=actor_id,
            updated_by=actor_id,
        )

    def update_step(self, tenant_id: UUID, actor_id: UUID, step_id: UUID, changes: Mapping[str, object]) -> RunbookStep:
        allowed = {
            "step_key",
            "position",
            "name",
            "description",
            "action_type",
            "extension_action_key",
            "parameters",
            "timeout_seconds",
            "retry_limit",
            "on_failure",
            "approval_permission",
        }
        if set(changes) - allowed:
            raise BDRDomainError("VALIDATION_ERROR", "Unsupported runbook-step field.")
        with transaction.atomic():
            step = (
                RunbookStep.objects.select_for_update()
                .for_tenant(tenant_id)
                .select_related("runbook")
                .filter(id=step_id, deleted_at__isnull=True)
                .first()
            )
            if step is None:
                raise ResourceNotFound("Runbook step")
            if step.runbook.status != RunbookStatus.DRAFT:
                raise DomainConflict("RUNBOOK_IMMUTABLE", "Steps can only be edited on a draft.")
            policy = get_configuration(tenant_id).document["steps"]
            timeout = int(changes.get("timeout_seconds", step.timeout_seconds))
            retries = int(changes.get("retry_limit", step.retry_limit))
            behavior = str(changes.get("on_failure", step.on_failure))
            if not int(policy["min_timeout_seconds"]) <= timeout <= int(policy["max_timeout_seconds"]):
                raise BDRDomainError("VALIDATION_ERROR", "Step timeout is outside configured safe limits.")
            if not 0 <= retries <= int(policy["max_retry_limit"]):
                raise BDRDomainError("VALIDATION_ERROR", "Step retry limit is outside configured safe limits.")
            if behavior not in policy["allowed_failure_behaviors"]:
                raise BDRDomainError("VALIDATION_ERROR", "Step failure behavior is not allowed.")
            action_type = str(changes.get("action_type", step.action_type))
            parameters = changes.get("parameters", step.parameters)
            if action_type == RunbookActionType.VERIFY and isinstance(parameters, Mapping):
                normalized_parameters = dict(parameters)
                checks = normalized_parameters.get("checks", list(policy["allowed_verification_checks"]))
                if (
                    not isinstance(checks, list)
                    or len(checks) > int(policy["max_verification_checks"])
                    or any(check not in policy["allowed_verification_checks"] for check in checks)
                ):
                    raise BDRDomainError("VALIDATION_ERROR", "Verification checks are outside configured limits.")
                normalized_parameters["checks"] = checks
                if "parameters" in changes:
                    changes = {**changes, "parameters": normalized_parameters}
            for field, value in changes.items():
                setattr(step, field, value)
            step.updated_by = actor_id
            step.save()
            return step

    def soft_delete_step(self, tenant_id: UUID, actor_id: UUID, step_id: UUID) -> None:
        step = (
            RunbookStep.objects.for_tenant(tenant_id)
            .select_related("runbook")
            .filter(id=step_id, deleted_at__isnull=True)
            .first()
        )
        if step is None:
            raise ResourceNotFound("Runbook step")
        if step.runbook.status != RunbookStatus.DRAFT:
            raise DomainConflict("RUNBOOK_IMMUTABLE", "Steps can only be removed from a draft.")
        step.deleted_at = timezone.now()
        step.deleted_by = actor_id
        step.updated_by = actor_id
        step.save(update_fields=["deleted_at", "deleted_by", "updated_by", "updated_at"])

    def reorder_steps(
        self, tenant_id: UUID, actor_id: UUID, runbook_id: UUID, ordered_step_ids: list[UUID]
    ) -> list[RunbookStep]:
        step_policy = get_configuration(tenant_id).document["steps"]
        if len(ordered_step_ids) > int(step_policy["max_reorder_items"]):
            raise BDRDomainError("VALIDATION_ERROR", "Step order exceeds the configured safe limit.")
        with transaction.atomic():
            runbook = (
                DRRunbook.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(id=runbook_id, status=RunbookStatus.DRAFT, deleted_at__isnull=True)
                .first()
            )
            if runbook is None:
                raise ResourceNotFound("Draft runbook")
            steps = list(
                RunbookStep.objects.select_for_update()
                .for_tenant(tenant_id)
                .filter(runbook=runbook, deleted_at__isnull=True)
            )
            if len(ordered_step_ids) != len(steps) or set(ordered_step_ids) != {step.id for step in steps}:
                raise BDRDomainError("INVALID_STEP_ORDER", "The order must contain every active step exactly once.")
            by_id = {step.id: step for step in steps}
            offset = len(steps) + int(step_policy["reorder_collision_offset"])
            for position, step in enumerate(steps, start=1):
                step.position = offset + position
                step.save(update_fields=["position", "updated_at"])
            ordered: list[RunbookStep] = []
            for position, step_id in enumerate(ordered_step_ids, start=1):
                step = by_id[step_id]
                step.position = position
                step.updated_by = actor_id
                step.save(update_fields=["position", "updated_by", "updated_at"])
                ordered.append(step)
            return ordered


class DRExerciseService:
    def get_exercise(self, tenant_id: UUID, exercise_id: UUID) -> DRExercise:
        exercise = (
            DRExercise.objects.for_tenant(tenant_id)
            .select_related("runbook", "recovery_point")
            .filter(id=exercise_id)
            .first()
        )
        if exercise is None:
            raise ResourceNotFound("Exercise")
        return exercise

    def list_exercises(self, tenant_id: UUID, filters: Mapping[str, object] | None = None) -> QuerySet[DRExercise]:
        queryset = DRExercise.objects.for_tenant(tenant_id).select_related("runbook", "recovery_point")
        for field in ("status", "exercise_type", "runbook"):
            if filters and filters.get(field) not in (None, ""):
                queryset = queryset.filter(**{field: filters[field]})
        if filters and filters.get("scheduled_after"):
            queryset = queryset.filter(scheduled_for__gte=filters["scheduled_after"])
        if filters and filters.get("scheduled_before"):
            queryset = queryset.filter(scheduled_for__lte=filters["scheduled_before"])
        return queryset.order_by("-scheduled_for", "-id")

    def schedule_exercise(self, tenant_id: UUID, actor_id: UUID, command: ExerciseCommand) -> DRExercise:
        exercise_policy = get_configuration(tenant_id).document["exercises"]
        if command.environment == TargetEnvironment.PRODUCTION and not exercise_policy["production_enabled"]:
            raise BDRDomainError("VALIDATION_ERROR", "Production exercises are disabled by tenant policy.")
        existing = DRExercise.objects.for_tenant(tenant_id).filter(idempotency_key=command.idempotency_key).first()
        if existing is not None:
            return existing
        runbook = (
            DRRunbook.objects.for_tenant(tenant_id)
            .filter(id=command.runbook_id, status=RunbookStatus.PUBLISHED, deleted_at__isnull=True)
            .first()
        )
        if runbook is None:
            raise ResourceNotFound("Published runbook")
        point = None
        if command.recovery_point_id:
            point = RecoveryPointService().get_recovery_point(tenant_id, command.recovery_point_id)
        return DRExercise.objects.create(
            tenant_id=tenant_id,
            name=command.name,
            runbook=runbook,
            recovery_point=point,
            exercise_type=command.exercise_type,
            environment=command.environment,
            scheduled_for=command.scheduled_for,
            idempotency_key=command.idempotency_key,
            initiated_by=actor_id,
        )

    def update_scheduled_exercise(
        self, tenant_id: UUID, actor_id: UUID, exercise_id: UUID, changes: Mapping[str, object]
    ) -> DRExercise:
        del actor_id
        allowed = {"name", "recovery_point_id", "exercise_type", "environment", "scheduled_for"}
        if set(changes) - allowed:
            raise BDRDomainError("VALIDATION_ERROR", "Unsupported exercise field.")
        exercise = self.get_exercise(tenant_id, exercise_id)
        if exercise.status != ExerciseStatus.SCHEDULED:
            raise DomainConflict("EXERCISE_IMMUTABLE", "Only scheduled exercises can be edited.")
        if (
            changes.get("environment") == TargetEnvironment.PRODUCTION
            and not get_configuration(tenant_id).document["exercises"]["production_enabled"]
        ):
            raise BDRDomainError("VALIDATION_ERROR", "Production exercises are disabled by tenant policy.")
        for field, value in changes.items():
            if field == "recovery_point_id":
                value = RecoveryPointService().get_recovery_point(tenant_id, UUID(str(value))) if value else None
                field = "recovery_point"
            setattr(exercise, field, value)
        exercise.save()
        return exercise

    def start_exercise(self, tenant_id: UUID, actor_id: UUID, exercise_id: UUID, idempotency_key: str) -> AsyncJob:
        exercise = self.get_exercise(tenant_id, exercise_id)
        with transaction.atomic():
            exercise = _transition(EXERCISE_MACHINE, exercise, "queue", f"{idempotency_key}:queue")
            job = enqueue(
                tenant_id,
                actor_id,
                EXECUTE_EXERCISE_COMMAND,
                {"exercise_id": str(exercise.id)},
                f"bdr:exercise:{idempotency_key}",
            )
            exercise.async_job_id = job.id
            exercise.save(update_fields=["async_job_id", "updated_at"])
        return job

    def execute_exercise(self, tenant_id: UUID, exercise_id: UUID, job_id: UUID) -> DRExercise:
        exercise = self.get_exercise(tenant_id, exercise_id)
        exercise = _transition(EXERCISE_MACHINE, exercise, "start", f"job:{job_id}:start")
        exercise.started_at = timezone.now()
        if exercise.recovery_point_id is None:
            point = (
                RecoveryPoint.objects.for_tenant(tenant_id)
                .filter(
                    status=RecoveryPointStatus.AVAILABLE,
                    scope_type=exercise.runbook.scope_type,
                    scope_ref=exercise.runbook.scope_ref,
                    verified_at__isnull=False,
                )
                .order_by("-captured_at")
                .first()
            )
            if point is None:
                exercise.completed_at = timezone.now()
                exercise.summary = "No verified recovery point satisfies the runbook scope."
                exercise.save(update_fields=["started_at", "completed_at", "summary", "updated_at"])
                return _transition(EXERCISE_MACHINE, exercise, "fail", f"job:{job_id}:no-point")
            exercise.recovery_point = point
        exercise.save(update_fields=["started_at", "recovery_point", "updated_at"])

        any_degraded = False
        failed_step_id: UUID | None = None
        steps = list(exercise.runbook.steps.filter(deleted_at__isnull=True).order_by("position"))
        for step in steps:
            execution = DRStepExecution.objects.create(
                tenant_id=tenant_id,
                exercise=exercise,
                runbook_step=step,
                attempt=1,
                async_job_id=job_id,
            )
            execution = _transition(STEP_EXECUTION_MACHINE, execution, "start", f"job:{job_id}:step:{step.id}:start")
            execution.started_at = timezone.now()
            execution.save(update_fields=["started_at", "updated_at"])
            try:
                evidence = self._execute_step(tenant_id, exercise, step, execution, job_id)
            except Exception as exc:
                failed_step_id = step.id
                execution.completed_at = timezone.now()
                execution.error_code = _safe_error_code(exc)
                execution.error_message = "The runbook step did not produce valid evidence."
                execution.evidence = {"completed": False, "error_code": execution.error_code}
                execution.save(update_fields=["completed_at", "error_code", "error_message", "evidence", "updated_at"])
                command = "degrade" if step.on_failure == StepFailureBehavior.CONTINUE_DEGRADED else "fail"
                _transition(
                    STEP_EXECUTION_MACHINE,
                    execution,
                    command,
                    f"job:{job_id}:step:{step.id}:{command}",
                )
                if command == "degrade":
                    any_degraded = True
                    continue
                break
            execution.completed_at = timezone.now()
            execution.evidence = evidence
            execution.save(update_fields=["completed_at", "evidence", "updated_at"])
            _transition(STEP_EXECUTION_MACHINE, execution, "pass", f"job:{job_id}:step:{step.id}:pass")

        exercise.completed_at = timezone.now()
        exercise.failed_step_id = failed_step_id
        if exercise.recovery_point and exercise.started_at:
            exercise.observed_rpo_seconds = max(
                0, int((exercise.started_at - exercise.recovery_point.data_cutoff_at).total_seconds())
            )
            exercise.observed_rto_seconds = max(0, int((exercise.completed_at - exercise.started_at).total_seconds()))
            exercise.rpo_met = exercise.observed_rpo_seconds <= exercise.runbook.rpo_target_seconds
            exercise.rto_met = exercise.observed_rto_seconds <= exercise.runbook.rto_target_seconds
        failed = failed_step_id is not None or any_degraded or not steps
        exercise.summary = (
            "Exercise completed with failed or degraded evidence."
            if failed
            else "Every runbook step produced verified evidence."
        )
        exercise.evidence_summary = {
            "step_count": len(steps),
            "failed_step_id": str(failed_step_id) if failed_step_id else None,
            "degraded": any_degraded,
        }
        exercise.save(
            update_fields=[
                "completed_at",
                "failed_step_id",
                "observed_rpo_seconds",
                "observed_rto_seconds",
                "rpo_met",
                "rto_met",
                "summary",
                "evidence_summary",
                "updated_at",
            ]
        )
        return _transition(
            EXERCISE_MACHINE,
            exercise,
            "fail" if failed else "pass",
            f"job:{job_id}:{'failed' if failed else 'passed'}",
        )

    def _execute_step(
        self,
        tenant_id: UUID,
        exercise: DRExercise,
        step: RunbookStep,
        execution: DRStepExecution,
        job_id: UUID,
    ) -> dict[str, object]:
        point = exercise.recovery_point
        if point is None:
            raise BDRDomainError("RECOVERY_POINT_REQUIRED", "A recovery point is required.")
        descriptor = _catalog().describe_completed_artifact(tenant_id, point.backup_job_id)
        adapter = _adapter(point.adapter_key)
        if step.action_type in {RunbookActionType.VALIDATE_RECOVERY_POINT, RunbookActionType.VERIFY}:
            result = adapter.validate_artifact(tenant_id, descriptor, idempotency_key=f"{job_id}:{execution.id}")
            if not result.valid:
                raise BDRDomainError(result.error_code or "ARTIFACT_INVALID", "Artifact validation failed.")
            return {
                "action_type": step.action_type,
                "valid": result.valid,
                "checksum_matches": result.checksum_matches,
                "provider_acknowledged": result.provider_acknowledged,
            }
        if step.action_type == RunbookActionType.RESTORE:
            mode = str(step.parameters.get("restore_mode", RestoreMode.FULL))
            selected = step.parameters.get("selected_components", [])
            components = tuple(str(value) for value in selected) if isinstance(selected, list) else ()
            receipt = adapter.restore(
                tenant_id,
                descriptor,
                RestoreTarget(
                    environment=RestoreEnvironment(exercise.environment),
                    target_ref=f"exercise-{exercise.id}",
                    mode=PortRestoreMode(mode),
                    selected_components=components,
                ),
                idempotency_key=f"{job_id}:{execution.id}",
            )
            if not receipt.accepted or not receipt.completed:
                raise BDRDomainError("RESTORE_NOT_COMPLETED", "Exercise restore was not completed.")
            verified = adapter.verify_restore(tenant_id, receipt, idempotency_key=f"{job_id}:{execution.id}:verify")
            if not verified.verified:
                raise BDRDomainError(
                    verified.error_code or "RESTORE_VERIFICATION_FAILED",
                    "Exercise restore verification failed.",
                )
            execution.provider_operation_id = receipt.operation_id
            execution.save(update_fields=["provider_operation_id", "updated_at"])
            return {
                "action_type": step.action_type,
                "provider_acknowledged": True,
                "verified": True,
            }
        if step.action_type == RunbookActionType.EXTENSION:
            handler = get_extension_action(str(step.extension_action_key))
            result = handler(tenant_id=tenant_id, exercise=exercise, step=step, job_id=job_id)
            if not isinstance(result, Mapping) or result.get("succeeded") is not True:
                raise BDRDomainError("EXTENSION_FAILED", "The extension action did not establish success.")
            return {"action_type": step.action_type, "succeeded": True}
        raise DependencyUnavailable(f"runbook action '{step.action_type}'")

    def cancel_exercise(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        exercise_id: UUID,
        transition_key: str,
    ) -> DRExercise:
        del actor_id
        exercise = self.get_exercise(tenant_id, exercise_id)
        exercise.completed_at = timezone.now()
        exercise.save(update_fields=["completed_at", "updated_at"])
        return _transition(EXERCISE_MACHINE, exercise, "cancel", transition_key)


class RecoveryObjectiveService:
    def calculate_restore_objectives(
        self, tenant_id: UUID, restore_run_id: UUID, *, persist: bool = True
    ) -> ObjectiveMeasurement:
        run = RestoreService().get_restore_run(tenant_id, restore_run_id)
        start = run.started_at
        completion = run.completed_at
        rpo = max(0, int((start - run.recovery_point.data_cutoff_at).total_seconds())) if start else None
        rto = max(0, int((completion - start).total_seconds())) if start and completion else None
        target_rpo = run.runbook.rpo_target_seconds if run.runbook else None
        target_rto = run.runbook.rto_target_seconds if run.runbook else None
        measurement = ObjectiveMeasurement(
            restore_run_id=run.id,
            runbook_id=run.runbook_id,
            rpo_seconds=rpo,
            rto_seconds=rto,
            rpo_target_seconds=target_rpo,
            rto_target_seconds=target_rto,
            rpo_met=(rpo <= target_rpo) if rpo is not None and target_rpo is not None else None,
            rto_met=(rto <= target_rto) if rto is not None and target_rto is not None else None,
            measured_at=completion or run.requested_at,
            outcome=("succeeded" if run.status == RestoreRunStatus.SUCCEEDED else "failed"),
        )
        if persist:
            run.achieved_rpo_seconds = rpo
            run.achieved_rto_seconds = rto
            run.save(update_fields=["achieved_rpo_seconds", "achieved_rto_seconds", "updated_at"])
        return measurement

    def get_readiness_summary(self, tenant_id: UUID, at: datetime | None = None) -> ReadinessSummary:
        assessed_at = at or timezone.now()
        policy = get_configuration(tenant_id).document
        verified = (
            RecoveryPoint.objects.for_tenant(tenant_id)
            .filter(status=RecoveryPointStatus.AVAILABLE, verified_at__isnull=False)
            .order_by("-verified_at")
            .first()
        )
        passed = (
            DRExercise.objects.for_tenant(tenant_id)
            .filter(status=ExerciseStatus.PASSED)
            .order_by("-completed_at")
            .first()
        )
        succeeded = (
            RestoreRun.objects.for_tenant(tenant_id)
            .filter(status=RestoreRunStatus.SUCCEEDED)
            .order_by("-completed_at")
            .first()
        )
        failed = (
            RestoreRun.objects.for_tenant(tenant_id)
            .filter(status=RestoreRunStatus.FAILED)
            .order_by("-completed_at")
            .first()
        )
        next_exercise = (
            DRExercise.objects.for_tenant(tenant_id)
            .filter(status=ExerciseStatus.SCHEDULED, scheduled_for__gte=assessed_at)
            .order_by("scheduled_for")
            .first()
        )
        published = list(
            DRRunbook.objects.for_tenant(tenant_id).filter(status=RunbookStatus.PUBLISHED, deleted_at__isnull=True)
        )
        unpublished = list(
            DRRunbook.objects.for_tenant(tenant_id).filter(status=RunbookStatus.DRAFT, deleted_at__isnull=True)[
                : int(policy["runbooks"]["unpublished_scan_limit"])
            ]
        )
        evidence_days = int(policy["exercises"]["evidence_freshness_days"])
        exercise_fresh = bool(
            passed and passed.completed_at and passed.completed_at >= assessed_at - timedelta(days=evidence_days)
        )
        minimum_rpo = min((item.rpo_target_seconds for item in published), default=None)
        rpo_compliant = bool(
            verified
            and minimum_rpo is not None
            and (assessed_at - verified.data_cutoff_at).total_seconds() <= minimum_rpo
        )
        rto_compliant = bool(passed and passed.rto_met is True and exercise_fresh)
        stale = tuple(
            unpublished
            + [
                item
                for item in published
                if not DRExercise.objects.for_tenant(tenant_id)
                .filter(
                    runbook=item,
                    status=ExerciseStatus.PASSED,
                    completed_at__gte=assessed_at - timedelta(days=evidence_days),
                )
                .exists()
            ]
        )
        breaches: list[str] = []
        if not rpo_compliant:
            breaches.append("rpo")
        if not rto_compliant:
            breaches.append("rto")
        try:
            adapter_health = _adapter(
                published[0].adapter_key if published else str(policy["providers"]["storage_adapter_key"])
            ).health()
            provider_status = "operational" if adapter_health.healthy else "degraded"
        except Exception:
            provider_status = "unavailable"
        oldest_pending = OutboxEvent.objects.filter(status=OutboxStatus.PENDING).order_by("created_at").first()
        queue_status = "operational"
        if oldest_pending and oldest_pending.created_at < assessed_at - timedelta(
            seconds=int(policy["health"]["queue_degradation_seconds"])
        ):
            queue_status = "degraded"
        provider_message = ""
        if provider_status != "operational":
            provider_message = "The configured recovery provider is not fully operational."
        return ReadinessSummary(
            protected=bool(published and rpo_compliant and rto_compliant and exercise_fresh),
            calculated_at=assessed_at,
            rpo_compliance_percent=(
                float(policy["reports"]["compliant_percent"])
                if rpo_compliant
                else float(policy["reports"]["noncompliant_percent"])
            ),
            rto_compliance_percent=(
                float(policy["reports"]["compliant_percent"])
                if rto_compliant
                else float(policy["reports"]["noncompliant_percent"])
            ),
            last_verified_recovery_point=verified,
            latest_passed_exercise=passed,
            latest_successful_restore=succeeded,
            latest_failed_restore=failed,
            next_scheduled_exercise=next_exercise,
            stale_runbook_count=len(stale) - len(unpublished),
            unpublished_runbook_count=len(unpublished),
            current_rpo_breaches=int("rpo" in breaches),
            current_rto_breaches=int("rto" in breaches),
            provider_state=provider_status,
            queue_state=queue_status,
            provider_message=provider_message,
        )

    def report_objectives(self, tenant_id: UUID, filters: Mapping[str, object]) -> ObjectiveReport:
        report_policy = get_configuration(tenant_id).document["reports"]
        requested_to = filters.get("to")
        report_to = requested_to if isinstance(requested_to, datetime) else timezone.now()
        requested_from = filters.get("from")
        report_from = (
            requested_from
            if isinstance(requested_from, datetime)
            else report_to - timedelta(days=int(report_policy["default_interval_days"]))
        )
        if report_from >= report_to:
            raise BDRDomainError("VALIDATION_ERROR", "Report start must be before its end.")
        if report_to - report_from > timedelta(days=int(report_policy["max_interval_days"])):
            raise BDRDomainError("REPORT_RANGE_TOO_LARGE", "The report interval exceeds the configured maximum.")
        bucket = str(filters.get("bucket") or report_policy["default_bucket"])
        if bucket not in report_policy["allowed_buckets"]:
            raise BDRDomainError("VALIDATION_ERROR", "The report bucket is not allowed.")
        queryset = RestoreRun.objects.for_tenant(tenant_id).select_related("recovery_point", "runbook")
        if filters.get("runbook_id"):
            queryset = queryset.filter(runbook_id=filters["runbook_id"])
        queryset = queryset.filter(requested_at__gte=report_from, requested_at__lte=report_to)
        maximum = int(report_policy["max_results"])
        ordered_runs = tuple(queryset.order_by("requested_at", "id")[: maximum + 1])
        if len(ordered_runs) > maximum:
            raise BDRDomainError(
                "REPORT_RESULT_LIMIT",
                "The report exceeds the configured result limit; narrow the interval.",
                http_status=413,
            )
        measurements = tuple(
            self.calculate_restore_objectives(tenant_id, run.id, persist=False) for run in ordered_runs
        )
        grouped: dict[tuple[str, UUID], list[tuple[RestoreRun, ObjectiveMeasurement]]] = {}
        period_ends: dict[str, datetime] = {}
        for run, measurement in zip(ordered_runs, measurements):
            when = run.requested_at
            if bucket == "day":
                period = when.replace(hour=0, minute=0, second=0, microsecond=0)
                period_end = period + timedelta(days=1)
            elif bucket == "week":
                period = (when - timedelta(days=when.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                period_end = period + timedelta(days=7)
            else:
                period = when.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                if period.month == 12:
                    period_end = period.replace(year=period.year + 1, month=1)
                else:
                    period_end = period.replace(month=period.month + 1)
            if run.runbook_id is None:
                continue
            period_key = period.isoformat()
            period_ends[period_key] = period_end
            grouped.setdefault((period_key, run.runbook_id), []).append((run, measurement))

        buckets: list[ObjectiveReportBucket] = []
        for (period_key, runbook_id), entries in sorted(grouped.items()):
            runbook = entries[0][0].runbook
            entry_measurements = tuple(item[1] for item in entries)
            total = len(entries)
            rpo_known = [item for item in entry_measurements if item.rpo_met is not None]
            rto_known = [item for item in entry_measurements if item.rto_met is not None]
            buckets.append(
                ObjectiveReportBucket(
                    period_start=datetime.fromisoformat(period_key),
                    period_end=period_ends[period_key],
                    runbook_id=runbook_id,
                    runbook_name=runbook.name,
                    runbook_version=runbook.version,
                    restore_count=total,
                    failed_restore_count=sum(item.outcome == "failed" for item in entry_measurements),
                    rpo_compliance_percent=(
                        100.0 * sum(item.rpo_met is True for item in rpo_known) / len(rpo_known) if rpo_known else 0.0
                    ),
                    rto_compliance_percent=(
                        100.0 * sum(item.rto_met is True for item in rto_known) / len(rto_known) if rto_known else 0.0
                    ),
                    measurements=entry_measurements,
                )
            )
        from_at = (
            report_from
            if isinstance(report_from, datetime)
            else (ordered_runs[0].requested_at if ordered_runs else timezone.now())
        )
        to_at = (
            report_to
            if isinstance(report_to, datetime)
            else (ordered_runs[-1].requested_at if ordered_runs else from_at)
        )
        rpo_known = [item for item in measurements if item.rpo_met is not None]
        rto_known = [item for item in measurements if item.rto_met is not None]
        return ObjectiveReport(
            from_at=from_at,
            to=to_at,
            bucket=bucket,
            total_restores=len(measurements),
            failed_restores=sum(item.outcome == "failed" for item in measurements),
            rpo_compliance_percent=(
                100.0 * sum(item.rpo_met is True for item in rpo_known) / len(rpo_known) if rpo_known else 0.0
            ),
            rto_compliance_percent=(
                100.0 * sum(item.rto_met is True for item in rto_known) / len(rto_known) if rto_known else 0.0
            ),
            buckets=tuple(buckets),
        )


def dataclass_payload(value: object) -> dict[str, object]:
    """Convert a public service result without leaking private provider fields."""

    return asdict(value)  # type: ignore[arg-type]


__all__ = [
    "BDRDomainError",
    "BackupExecutionFacade",
    "BackupRequestCommand",
    "DRExerciseService",
    "DomainConflict",
    "ExerciseCommand",
    "ObjectiveMeasurement",
    "ObjectiveReport",
    "ReadinessSummary",
    "RecoveryObjectiveService",
    "RecoveryPointService",
    "ResourceNotFound",
    "RestoreRunCommand",
    "RestoreService",
    "RunbookCommand",
    "RunbookService",
    "RunbookStepCommand",
    "dataclass_payload",
]
