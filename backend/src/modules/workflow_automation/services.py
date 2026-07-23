"""Tenant-first business services for workflow automation.

HTTP controllers and durable workers both call this module.  Every public
entry point validates its tenant boundary, uses row locks for lifecycle
changes, and records durable evidence before reporting success.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, Mapping, Sequence

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from src.core.api import CapabilityUnavailable, OperationFailed
from src.core.async_jobs.models import AsyncJob, JobStatus, OutboxEvent
from src.core.async_jobs.services import enqueue
from src.core.async_jobs.services import transition as transition_job
from src.core.middleware.correlation import get_correlation_id
from src.core.observability.logging import redact_text
from src.core.state_machine import (
    IdempotencyConflictError,
    IllegalTransitionError,
    StateMachineError,
    TerminalStateError,
)

from .extensions import (
    WorkflowActionInvocation,
    action_registry,
    condition_registry,
    execute_registered_action,
)
from .models import (
    Workflow,
    WorkflowAutomationConfiguration,
    WorkflowAutomationConfigurationRevision,
    WorkflowInstance,
    WorkflowStep,
    WorkflowStepExecution,
    WorkflowTask,
    WorkflowTransitionAudit,
)
from .serializers import validate_json_value, validate_step_config
from .state_machines import WORKFLOW_DEFINITION_MACHINE, WORKFLOW_INSTANCE_MACHINE, WORKFLOW_TASK_MACHINE

logger = logging.getLogger("saraise.workflow_automation")
User = get_user_model()

EXECUTE_INSTANCE_COMMAND = "workflow_automation.execute_instance"
EXPIRE_TASKS_COMMAND = "workflow_automation.expire_tasks"
TERMINAL_INSTANCE_STATES = frozenset({"completed", "failed", "cancelled"})
TERMINAL_TASK_STATES = frozenset({"completed", "rejected", "cancelled", "expired"})


def default_configuration_document() -> dict[str, Any]:
    """Return the complete, portable default policy document for a new tenant."""

    return {
        "defaults": {
            "workflow_version": 1,
            "workflow_type": "sequential",
            "trigger_type": "manual",
            "definition_status": "draft",
            "execution_priority": 5,
            "step_execution_attempt": 1,
            "approval_assignment_kind": "user",
            "approval_due_seconds": 86400,
            "approval_rejection_behavior": "fail",
            "approval_completion_rule": "any",
            "timeout_action": "fail",
            "cancellation_reason": "Workflow instance cancelled",
            "task_status": "pending",
            "task_ordering": "due_date",
            "task_scope": "mine",
        },
        "limits": {
            "execution_priority_min": 1,
            "execution_priority_max": 9,
            "json_max_depth": 12,
            "json_max_items": 2000,
            "json_max_string_length": 32768,
            "reject_reason_max_length": 2000,
            "duration_max_seconds": 31536000,
            "transition_key_max_length": 255,
            "failure_message_max_length": 2000,
            "cancellation_reason_max_length": 500,
            "catalog_default_limit": 25,
            "catalog_max_limit": 100,
            "catalog_search_max_length": 200,
            "assignee_result_limit": 100,
            "email_template_key_max_length": 100,
            "email_recipient_max_length": 254,
            "generated_step_key_max_length": 64,
            "workflow_page_size": 20,
            "execution_step_multiplier": 2,
        },
        "allowed_values": {
            "workflow_types": ["approval", "state_machine", "sequential", "conditional"],
            "trigger_types": ["manual"],
            "definition_statuses": ["draft", "published", "archived"],
            "step_types": ["action", "approval", "notification", "decision"],
            "timeout_actions": ["fail", "cancel"],
            "approval_rejection_behaviors": ["fail", "goto", "cancel"],
            "approval_completion_rules": ["any", "all"],
            "notification_channels": ["in_app", "email"],
            "catalog_orderings": ["key", "display_name"],
        },
        "trigger_schemas": {
            "manual": {"required": [], "allowed": []},
        },
        "step_schemas": {
            "action": {
                "required": ["handler", "schema_version", "input_mapping"],
                "optional": ["configuration", "public_output_keys"],
            },
            "approval": {
                "required": ["assignment_kind", "assignee_id", "rejection_behavior"],
                "optional": [
                    "due_in_seconds",
                    "reject_step_key",
                    "completion_rule",
                    "display_context_keys",
                ],
            },
            "notification": {
                "required": ["channel", "recipient_mapping", "template_key"],
                "optional": ["public_output_keys"],
            },
            "decision": {
                "required": ["condition", "true_step_key", "false_step_key"],
                "optional": ["schema_version"],
            },
        },
        "notification_handlers": {
            "in_app": {"handler": "core.in_app_notification.v1", "schema_version": "1"},
            "email": {"handler": "core.email_notification.v1", "schema_version": "1"},
        },
        "step_handlers": {
            "action": "registered_action",
            "approval": "approval_task",
            "notification": "registered_action",
            "decision": "registered_condition",
        },
        "condition_input_mappings": {
            "core.equals.v1": {
                "left": {"source": "context_path", "field": "left_path"},
                "right": {"source": "literal", "field": "right_value"},
            },
            "core.truthy.v1": {
                "value": {"source": "context_path", "field": "value_path"},
            },
        },
        "lifecycle": {
            "definition": {
                "draft": ["published", "draft"],
                "published": ["archived"],
                "archived": [],
            },
            "instance": {
                "pending": ["running", "cancelled"],
                "running": ["waiting", "completed", "failed", "cancelled"],
                "waiting": ["running", "failed", "cancelled"],
                "completed": [],
                "failed": [],
                "cancelled": [],
            },
            "task": {
                "pending": ["completed", "rejected", "cancelled", "expired"],
                "completed": [],
                "rejected": [],
                "cancelled": [],
                "expired": [],
            },
        },
        "allowed_actions": {
            "workflow": {
                "draft": ["view", "edit", "publish", "delete"],
                "published": ["view", "clone", "archive", "start"],
                "archived": ["view", "clone"],
            },
            "instance": {
                "pending": ["view", "cancel"],
                "running": ["view", "cancel"],
                "waiting": ["view", "cancel"],
                "completed": ["view"],
                "failed": ["view"],
                "cancelled": ["view"],
            },
            "task": {
                "pending": ["view", "complete", "reject"],
                "completed": ["view"],
                "rejected": ["view"],
                "cancelled": ["view"],
                "expired": ["view"],
            },
        },
        "action_quota_costs": {
            "core.in_app_notification.v1": 0,
            "core.email_notification.v1": 1,
            "core.context_projection.v1": 0,
            "core.terminal_completion.v1": 0,
        },
        "operational": {
            "api_quota_cost": 1,
            "v1_sunset": "Thu, 31 Dec 2026 23:59:59 GMT",
            "outbox_stale_seconds": 300,
            "health_staleness_seconds": 30,
            "email_timeout_seconds": 10,
            "email_retry_attempts": 3,
            "email_retry_base_ms": 250,
            "email_circuit_failure_threshold": 5,
            "email_circuit_reset_seconds": 60,
            "execution_poll_interval_ms": 15000,
            "execution_detail_poll_interval_ms": 5000,
        },
        "ui": {
            "sidebar_orders": {"workflows": 80, "instances": 81, "tasks": 82, "configuration": 83},
            "duration_display_threshold_ms": 60000,
            "due_time_unit_seconds": 3600,
            "minimum_due_time_units": 1,
            "reject_reason_max_length": 1000,
        },
        "feature_flags": {
            "event_triggers": {"enabled": False, "roles": [], "cohorts": []},
            "scheduled_triggers": {"enabled": False, "roles": [], "cohorts": []},
            "parallel_workflows": {"enabled": False, "roles": [], "cohorts": []},
            "timeout_notifications": {"enabled": False, "roles": [], "cohorts": []},
        },
    }


class WorkflowConfigurationService:
    """Tenant-safe configuration command/query service and validation authority."""

    ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})

    @staticmethod
    def _environment(value: object) -> str:
        environment = str(value or "production").strip().lower()
        if environment not in WorkflowConfigurationService.ENVIRONMENTS:
            raise ValidationError({"environment": ["Unsupported environment."]})
        return environment

    @staticmethod
    def validate_document(document: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(document, Mapping):
            raise ValidationError({"document": ["Must be a JSON object."]})
        candidate = dict(document)
        expected = set(default_configuration_document())
        if set(candidate) != expected:
            raise ValidationError({"document": [f"Configuration sections must be exactly: {sorted(expected)}."]})
        defaults = candidate.get("defaults")
        limits = candidate.get("limits")
        allowed = candidate.get("allowed_values")
        operational = candidate.get("operational")
        ui = candidate.get("ui")
        flags = candidate.get("feature_flags")
        if not all(isinstance(value, Mapping) for value in (defaults, limits, allowed, operational, ui, flags)):
            raise ValidationError({"document": ["Configuration sections must be JSON objects."]})

        baseline = default_configuration_document()
        errors: dict[str, list[str]] = {}
        for section in ("defaults", "limits", "allowed_values", "operational", "ui", "feature_flags"):
            configured = candidate.get(section)
            expected_keys = set(baseline[section])
            if not isinstance(configured, Mapping) or set(configured) != expected_keys:
                errors[section] = [f"Must contain exactly these fields: {sorted(expected_keys)}."]

        integer_bounds = {
            "execution_priority_min": (1, 9),
            "execution_priority_max": (1, 9),
            "json_max_depth": (1, 32),
            "json_max_items": (1, 10000),
            "json_max_string_length": (1, 1048576),
            "reject_reason_max_length": (1, 10000),
            "duration_max_seconds": (1, 31536000),
            "transition_key_max_length": (32, 255),
            "failure_message_max_length": (128, 10000),
            "cancellation_reason_max_length": (1, 5000),
            "catalog_default_limit": (1, 500),
            "catalog_max_limit": (1, 500),
            "catalog_search_max_length": (1, 1000),
            "assignee_result_limit": (1, 500),
            "email_template_key_max_length": (1, 255),
            "email_recipient_max_length": (64, 320),
            "generated_step_key_max_length": (8, 128),
            "workflow_page_size": (1, 100),
            "execution_step_multiplier": (1, 10),
        }
        for name, (minimum, maximum) in integer_bounds.items():
            value = limits.get(name)  # type: ignore[union-attr]
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                errors[f"limits.{name}"] = [f"Must be an integer from {minimum} through {maximum}."]
        if (
            isinstance(limits.get("catalog_default_limit"), int)  # type: ignore[union-attr]
            and isinstance(limits.get("catalog_max_limit"), int)  # type: ignore[union-attr]
            and limits["catalog_default_limit"] > limits["catalog_max_limit"]  # type: ignore[index]
        ):
            errors["limits.catalog_default_limit"] = ["Must not exceed catalog_max_limit."]
        if (
            isinstance(limits.get("execution_priority_min"), int)  # type: ignore[union-attr]
            and isinstance(limits.get("execution_priority_max"), int)  # type: ignore[union-attr]
            and limits["execution_priority_min"] > limits["execution_priority_max"]  # type: ignore[index]
        ):
            errors["limits.execution_priority_min"] = ["Must not exceed execution_priority_max."]

        allowlist_contract = {
            "workflow_types": {"approval", "state_machine", "sequential", "conditional"},
            "trigger_types": {"manual"},
            "definition_statuses": {"draft", "published", "archived"},
            "step_types": {"action", "approval", "notification", "decision"},
            "timeout_actions": {"fail", "cancel"},
            "approval_rejection_behaviors": {"fail", "goto", "cancel"},
            "approval_completion_rules": {"any", "all"},
            "notification_channels": {"in_app", "email"},
            "catalog_orderings": {"key", "display_name"},
        }
        for name, safe_values in allowlist_contract.items():
            values = allowed.get(name)  # type: ignore[union-attr]
            if not isinstance(values, list) or not values or not set(values).issubset(safe_values):
                errors[f"allowed_values.{name}"] = [f"Must be a non-empty subset of {sorted(safe_values)}."]
        default_dependencies = {
            "workflow_type": "workflow_types",
            "trigger_type": "trigger_types",
            "definition_status": "definition_statuses",
            "approval_rejection_behavior": "approval_rejection_behaviors",
            "approval_completion_rule": "approval_completion_rules",
            "timeout_action": "timeout_actions",
        }
        for default_name, allowlist_name in default_dependencies.items():
            if defaults.get(default_name) not in allowed.get(allowlist_name, []):  # type: ignore[union-attr]
                errors[f"defaults.{default_name}"] = [
                    f"Must be enabled by allowed_values.{allowlist_name}."
                ]
        for default_name, limit_name in {
            "approval_due_seconds": "duration_max_seconds",
        }.items():
            value = defaults.get(default_name)  # type: ignore[union-attr]
            maximum = limits.get(limit_name)  # type: ignore[union-attr]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or not isinstance(maximum, int)
                or value > maximum
            ):
                errors[f"defaults.{default_name}"] = [f"Must be within limits.{limit_name}."]
        priority = defaults.get("execution_priority")  # type: ignore[union-attr]
        priority_min = limits.get("execution_priority_min")  # type: ignore[union-attr]
        priority_max = limits.get("execution_priority_max")  # type: ignore[union-attr]
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or not isinstance(priority_min, int)
            or not isinstance(priority_max, int)
            or not priority_min <= priority <= priority_max
        ):
            errors["defaults.execution_priority"] = ["Must be within the configured priority limits."]
        if (
            not isinstance(defaults.get("workflow_version"), int)  # type: ignore[union-attr]
            or defaults["workflow_version"] < 1  # type: ignore[index]
        ):
            errors["defaults.workflow_version"] = ["Must be a positive integer."]
        if (
            not isinstance(defaults.get("step_execution_attempt"), int)  # type: ignore[union-attr]
            or defaults["step_execution_attempt"] < 1  # type: ignore[index]
        ):
            errors["defaults.step_execution_attempt"] = ["Must be a positive integer."]
        cancellation_reason = defaults.get("cancellation_reason")  # type: ignore[union-attr]
        cancellation_maximum = limits.get("cancellation_reason_max_length")  # type: ignore[union-attr]
        if (
            not isinstance(cancellation_reason, str)
            or not cancellation_reason.strip()
            or not isinstance(cancellation_maximum, int)
            or len(cancellation_reason) > cancellation_maximum
        ):
            errors["defaults.cancellation_reason"] = [
                "Must be nonblank and within limits.cancellation_reason_max_length."
            ]
        step_handlers = candidate.get("step_handlers")
        supported_step_handlers = {
            "action": "registered_action",
            "approval": "approval_task",
            "notification": "registered_action",
            "decision": "registered_condition",
        }
        if not isinstance(step_handlers, Mapping) or dict(step_handlers) != supported_step_handlers:
            errors["step_handlers"] = [
                "Must map each supported step type to its fixed, safe execution primitive."
            ]
        lifecycle = candidate.get("lifecycle")
        safe_lifecycle = default_configuration_document()["lifecycle"]
        if not isinstance(lifecycle, Mapping):
            errors["lifecycle"] = ["Must be an object."]
        else:
            for domain, safe_graph in safe_lifecycle.items():
                configured_graph = lifecycle.get(domain)
                if not isinstance(configured_graph, Mapping) or set(configured_graph) != set(safe_graph):
                    errors[f"lifecycle.{domain}"] = ["Must declare every lifecycle state."]
                    continue
                for source, targets in configured_graph.items():
                    if (
                        not isinstance(targets, list)
                        or not set(targets).issubset(set(safe_graph[source]))
                    ):
                        errors[f"lifecycle.{domain}.{source}"] = [
                            "May only enable transitions supported by the fixed state-machine engine."
                        ]
        action_quota_costs = candidate.get("action_quota_costs")
        safe_quota_keys = set(baseline["action_quota_costs"])
        if (
            not isinstance(action_quota_costs, Mapping)
            or set(action_quota_costs) != safe_quota_keys
            or any(
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 100
                for value in action_quota_costs.values()
            )
        ):
            errors["action_quota_costs"] = [
                "Must assign every built-in action an integer quota cost from 0 through 100."
            ]

        for name, bounds in {
            "api_quota_cost": (1, 100),
            "outbox_stale_seconds": (30, 86400),
            "health_staleness_seconds": (5, 3600),
            "email_timeout_seconds": (1, 60),
            "email_retry_attempts": (1, 10),
            "email_retry_base_ms": (10, 10000),
            "email_circuit_failure_threshold": (1, 100),
            "email_circuit_reset_seconds": (1, 3600),
            "execution_poll_interval_ms": (1000, 300000),
            "execution_detail_poll_interval_ms": (1000, 300000),
        }.items():
            value = operational.get(name)  # type: ignore[union-attr]
            if isinstance(value, bool) or not isinstance(value, int) or not bounds[0] <= value <= bounds[1]:
                errors[f"operational.{name}"] = [f"Must be an integer from {bounds[0]} through {bounds[1]}."]
        if not isinstance(operational.get("v1_sunset"), str) or not operational["v1_sunset"]:  # type: ignore[index,union-attr]
            errors["operational.v1_sunset"] = ["Must be a non-empty HTTP-date."]

        if not isinstance(ui.get("sidebar_orders"), Mapping):  # type: ignore[union-attr]
            errors["ui.sidebar_orders"] = ["Must be an object."]
        else:
            sidebar_orders = ui["sidebar_orders"]  # type: ignore[index]
            expected_sidebar_keys = set(baseline["ui"]["sidebar_orders"])
            values = list(sidebar_orders.values())
            if (
                set(sidebar_orders) != expected_sidebar_keys
                or any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000 for value in values)
                or len(values) != len(set(values))
            ):
                errors["ui.sidebar_orders"] = [
                    "Must assign each navigation item a unique integer from 0 through 1000."
                ]
        for name, bounds in {
            "duration_display_threshold_ms": (1, 86400000),
            "due_time_unit_seconds": (60, 86400),
            "minimum_due_time_units": (1, 365),
            "reject_reason_max_length": (1, 10000),
        }.items():
            value = ui.get(name)  # type: ignore[union-attr]
            if isinstance(value, bool) or not isinstance(value, int) or not bounds[0] <= value <= bounds[1]:
                errors[f"ui.{name}"] = [f"Must be an integer from {bounds[0]} through {bounds[1]}."]
        if (
            isinstance(ui.get("reject_reason_max_length"), int)  # type: ignore[union-attr]
            and isinstance(limits.get("reject_reason_max_length"), int)  # type: ignore[union-attr]
            and ui["reject_reason_max_length"] > limits["reject_reason_max_length"]  # type: ignore[index]
        ):
            errors["ui.reject_reason_max_length"] = [
                "Must not exceed limits.reject_reason_max_length."
            ]
        for flag_name, rollout in flags.items():  # type: ignore[union-attr]
            if (
                not isinstance(rollout, Mapping)
                or not isinstance(rollout.get("enabled"), bool)
                or not isinstance(rollout.get("roles"), list)
                or not isinstance(rollout.get("cohorts"), list)
            ):
                errors[f"feature_flags.{flag_name}"] = [
                    "Must contain enabled (boolean), roles (array), and cohorts (array)."
                ]
                continue
            for field in ("roles", "cohorts"):
                values = rollout[field]
                if (
                    any(not isinstance(value, str) or not value.strip() or len(value) > 128 for value in values)
                    or len(values) != len(set(values))
                ):
                    errors[f"feature_flags.{flag_name}.{field}"] = [
                        "Must contain unique, nonblank identifiers no longer than 128 characters."
                    ]
        unavailable_dependencies = {
            "event_triggers": "event",
            "scheduled_triggers": "scheduled",
            "parallel_workflows": "parallel",
            "timeout_notifications": "notify",
        }
        for flag_name, required_value in unavailable_dependencies.items():
            rollout = flags.get(flag_name)  # type: ignore[union-attr]
            enabled = isinstance(rollout, Mapping) and rollout.get("enabled") is True
            enabled_values = (
                allowed.get("timeout_actions", [])
                if flag_name == "timeout_notifications"
                else allowed.get(
                    "workflow_types" if flag_name == "parallel_workflows" else "trigger_types",
                    [],
                )
            )
            if enabled and required_value not in enabled_values:
                errors[f"feature_flags.{flag_name}.enabled"] = [
                    "Cannot be enabled until its end-to-end adapter is present in the safe allow-list."
                ]
        if errors:
            raise ValidationError(errors)
        validate_json_value(
            candidate,
            max_depth=int(limits["json_max_depth"]),  # type: ignore[index]
            max_items=int(limits["json_max_items"]),  # type: ignore[index]
            max_string_length=int(limits["json_max_string_length"]),  # type: ignore[index]
        )
        return candidate

    @staticmethod
    def get_configuration(
        tenant_id: uuid.UUID | str,
        environment: str = "production",
        *,
        create: bool = True,
    ) -> WorkflowAutomationConfiguration:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        environment = WorkflowConfigurationService._environment(environment)
        queryset = WorkflowAutomationConfiguration.objects.for_tenant(tenant_uuid)
        try:
            return queryset.get(environment=environment)
        except WorkflowAutomationConfiguration.DoesNotExist:
            if not create:
                raise NotFound("Workflow automation configuration is not initialized.")
        with transaction.atomic():
            configuration, created = queryset.select_for_update().get_or_create(
                tenant_id=tenant_uuid,
                environment=environment,
                defaults={"document": default_configuration_document(), "version": 1},
            )
            if created:
                WorkflowAutomationConfigurationRevision.objects.for_tenant(tenant_uuid).create(
                    tenant_id=tenant_uuid,
                    configuration=configuration,
                    version=1,
                    previous_document={},
                    document=configuration.document,
                    actor=None,
                    correlation_id=_correlation_id(),
                    change_reason="initial-defaults",
                )
            return configuration

    @staticmethod
    def value(tenant_id: uuid.UUID | str, path: str, environment: str = "production") -> Any:
        value: Any = WorkflowConfigurationService.get_configuration(tenant_id, environment).document
        components = path.split(".")
        index = 0
        while index < len(components):
            component = components[index]
            if not isinstance(value, Mapping) or component not in value:
                if isinstance(value, Mapping):
                    dotted_key = next(
                        (
                            ".".join(components[index:end])
                            for end in range(len(components), index, -1)
                            if ".".join(components[index:end]) in value
                        ),
                        None,
                    )
                    if dotted_key is not None:
                        value = value[dotted_key]
                        index += len(dotted_key.split("."))
                        continue
                raise OperationFailed(
                    error_code="WORKFLOW_CONFIGURATION_INVALID",
                    message="Required workflow configuration is missing.",
                    http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            value = value[component]
            index += 1
        return value

    @staticmethod
    def update_configuration(
        tenant_id: uuid.UUID | str,
        actor: object,
        document: Mapping[str, Any],
        *,
        environment: str = "production",
        expected_version: int,
        change_reason: str,
    ) -> WorkflowAutomationConfiguration:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        actor_id = _actor_id(actor)
        clean = WorkflowConfigurationService.validate_document(document)
        if not change_reason.strip():
            raise ValidationError({"change_reason": ["This field may not be blank."]})
        correlation_id = _correlation_id()
        with transaction.atomic():
            configuration = WorkflowConfigurationService.get_configuration(tenant_uuid, environment)
            configuration = WorkflowAutomationConfiguration.objects.for_tenant(tenant_uuid).select_for_update().get(
                id=configuration.id
            )
            if configuration.version != expected_version:
                raise _conflict("CONFIGURATION_VERSION_CONFLICT", "The configuration changed; reload before saving.")
            previous = dict(configuration.document)
            if previous == clean:
                return configuration
            configuration.version += 1
            configuration.document = clean
            configuration.updated_by_id = actor_id
            configuration.save(update_fields=("version", "document", "updated_by", "updated_at"))
            WorkflowAutomationConfigurationRevision.objects.for_tenant(tenant_uuid).create(
                tenant_id=tenant_uuid,
                configuration=configuration,
                version=configuration.version,
                previous_document=previous,
                document=clean,
                actor_id=actor_id,
                correlation_id=correlation_id,
                change_reason=change_reason.strip(),
            )
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_automation_configuration",
                aggregate_id=configuration.id,
                event_type="workflow.configuration.changed",
                payload={"version": configuration.version, "correlation_id": correlation_id},
            )
            return configuration

    @staticmethod
    def preview(
        tenant_id: uuid.UUID | str,
        document: Mapping[str, Any],
        environment: str = "production",
    ) -> dict[str, Any]:
        clean = WorkflowConfigurationService.validate_document(document)
        current = WorkflowConfigurationService.get_configuration(tenant_id, environment)
        changed = sorted(key for key in clean if clean[key] != current.document.get(key))
        return {
            "valid": True,
            "current_version": current.version,
            "changed_sections": changed,
            "restart_required": False,
        }

    @staticmethod
    def history(
        tenant_id: uuid.UUID | str,
        environment: str = "production",
    ) -> QuerySet[WorkflowAutomationConfigurationRevision]:
        configuration = WorkflowConfigurationService.get_configuration(tenant_id, environment)
        return WorkflowAutomationConfigurationRevision.objects.for_tenant(configuration.tenant_id).filter(
            configuration=configuration
        )

    @staticmethod
    def rollback(
        tenant_id: uuid.UUID | str,
        actor: object,
        target_version: int,
        *,
        environment: str = "production",
        expected_version: int,
    ) -> WorkflowAutomationConfiguration:
        configuration = WorkflowConfigurationService.get_configuration(tenant_id, environment)
        try:
            revision = WorkflowAutomationConfigurationRevision.objects.for_tenant(configuration.tenant_id).get(
                configuration=configuration,
                version=target_version,
            )
        except WorkflowAutomationConfigurationRevision.DoesNotExist as exc:
            raise NotFound("Configuration version not found.") from exc
        return WorkflowConfigurationService.update_configuration(
            configuration.tenant_id,
            actor,
            revision.document,
            environment=environment,
            expected_version=expected_version,
            change_reason=f"rollback-to-version-{target_version}",
        )


@dataclass(frozen=True, slots=True)
class DefinitionValidationIssue:
    code: str
    message: str
    path: str = ""
    step_key: str = ""
    severity: str = "error"


@dataclass(frozen=True, slots=True)
class DefinitionValidationResult:
    valid: bool
    errors: tuple[DefinitionValidationIssue, ...] = ()
    warnings: tuple[DefinitionValidationIssue, ...] = ()

    @property
    def issues(self) -> tuple[DefinitionValidationIssue, ...]:
        """Return blocking issues through the public validation contract."""

        return self.errors

    def as_dict(self) -> dict[str, Any]:
        def issue(item: DefinitionValidationIssue) -> dict[str, Any]:
            return {
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
                "step_key": item.step_key or None,
                "pointer": item.path or None,
                "remediation": None,
            }

        return {
            "valid": self.valid,
            "issues": [issue(item) for item in self.errors],
            "errors": [issue(item) for item in self.errors],
            "warnings": [issue(item) for item in self.warnings],
        }


def _as_uuid(value: uuid.UUID | str, field_name: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({field_name: ["Must be a valid UUID."]}) from exc


def _actor_id(actor: object | None) -> str:
    actor_id = getattr(actor, "pk", getattr(actor, "id", None))
    if actor_id in (None, ""):
        raise PermissionDenied("An authenticated actor is required.")
    return str(actor_id)


def _transition_key(
    tenant_id: uuid.UUID | str,
    value: str,
    field_name: str = "transition_key",
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({field_name: ["This field may not be blank."]})
    maximum = int(WorkflowConfigurationService.value(tenant_id, "limits.transition_key_max_length"))
    if len(value.strip()) > maximum:
        raise ValidationError({field_name: [f"Must not exceed {maximum} characters."]})
    return value.strip()


def _correlation_id() -> str:
    return get_correlation_id() or str(uuid.uuid4())


def _conflict(code: str, message: str, detail: object | None = None) -> OperationFailed:
    return OperationFailed(
        error_code=code,
        message=message,
        detail=detail,
        http_status=status.HTTP_409_CONFLICT,
    )


def _emit_event(
    tenant_id: uuid.UUID,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
) -> OutboxEvent:
    """Write a transactional event without embedding business payloads."""

    event_payload = {
        "aggregate_id": str(aggregate_id),
        "tenant_id": str(tenant_id),
        "correlation_id": _correlation_id(),
    }
    event_payload.update(dict(payload or {}))
    return OutboxEvent.objects.for_tenant(tenant_id).create(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=event_payload,
    )


def _safe_failure_message(tenant_id: uuid.UUID | str, message: object) -> str:
    sanitized = redact_text(str(message or "Workflow execution failed."))
    maximum = int(WorkflowConfigurationService.value(tenant_id, "limits.failure_message_max_length"))
    return sanitized[:maximum]


def _validate_tenant_json(
    tenant_id: uuid.UUID | str,
    value: Any,
    *,
    path: str,
) -> Any:
    limits = WorkflowConfigurationService.get_configuration(tenant_id).document["limits"]
    return validate_json_value(
        value,
        path=path,
        max_depth=int(limits["json_max_depth"]),
        max_items=int(limits["json_max_items"]),
        max_string_length=int(limits["json_max_string_length"]),
    )


def _history_has(aggregate: object, transition_key: str, command: str) -> bool:
    history = getattr(aggregate, "transition_history", [])
    return any(
        isinstance(item, Mapping) and item.get("transition_key") == transition_key and item.get("command") == command
        for item in history
    )


def _apply_machine(machine: object, aggregate: object, command: str, **kwargs: Any) -> Any:
    correlation_id = str(kwargs.pop("correlation_id", "") or _correlation_id())
    metadata = dict(kwargs.pop("metadata", {}) or {})
    metadata["correlation_id"] = correlation_id
    kwargs["metadata"] = metadata
    from_state = str(getattr(aggregate, getattr(machine, "state_field", "status"), ""))
    transition_key = str(kwargs.get("transition_key", ""))
    tenant_id = getattr(aggregate, "tenant_id", kwargs.get("tenant_id"))
    if tenant_id is not None and not _history_has(aggregate, transition_key, command):
        domain = {
            WORKFLOW_DEFINITION_MACHINE: "definition",
            WORKFLOW_INSTANCE_MACHINE: "instance",
            WORKFLOW_TASK_MACHINE: "task",
        }.get(machine)
        if domain is None:
            raise OperationFailed(
                error_code="STATE_MACHINE_UNCONFIGURED",
                message="The lifecycle engine is not governed by tenant configuration.",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        edge = next(
            (
                candidate
                for candidate in getattr(machine, "transitions", ())
                if candidate.command == command and candidate.source == from_state
            ),
            None,
        )
        if edge is not None:
            configured_targets = WorkflowConfigurationService.value(
                tenant_id,
                f"lifecycle.{domain}.{from_state}",
            )
            if edge.target not in configured_targets:
                raise _conflict(
                    "TRANSITION_DISABLED",
                    "This lifecycle transition is disabled by tenant configuration.",
                )
    try:
        result = machine.apply(aggregate, command, **kwargs)  # type: ignore[attr-defined]
    except IdempotencyConflictError as exc:
        raise _conflict("IDEMPOTENCY_CONFLICT", "The idempotency key was already used for another command.") from exc
    except (IllegalTransitionError, TerminalStateError) as exc:
        raise _conflict("ILLEGAL_TRANSITION", "The requested lifecycle transition is no longer legal.") from exc
    except StateMachineError as exc:
        raise OperationFailed(
            error_code="STATE_TRANSITION_FAILED",
            message="The lifecycle transition could not be applied.",
            http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc
    if isinstance(result, Workflow):
        WorkflowTransitionAudit.objects.for_tenant(result.tenant_id).get_or_create(
            tenant_id=result.tenant_id,
            workflow=result,
            transition_key=transition_key,
            command=command,
            defaults={
                "from_state": from_state,
                "to_state": result.status,
                "actor_id": metadata.get("actor_id"),
                "correlation_id": correlation_id,
                "occurred_at": timezone.now(),
            },
        )
    return result


def _handler_from_registry(registry: object, key: str, schema_version: str | None = None) -> Any:
    try:
        if schema_version:
            try:
                return registry.get(key, schema_version=schema_version)  # type: ignore[attr-defined]
            except TypeError:
                return registry.get(key)  # type: ignore[attr-defined]
        return registry.get(key)  # type: ignore[attr-defined]
    except (KeyError, LookupError) as exc:
        raise CapabilityUnavailable(
            capability=key,
            message="A workflow extension required by this definition is unavailable.",
        ) from exc


def _handler_key_for_step(
    tenant_id: uuid.UUID | str,
    step: WorkflowStep,
) -> tuple[str, str | None]:
    if step.step_type == "action":
        return str(step.config["handler"]), str(step.config.get("schema_version") or "") or None
    if step.step_type == "notification":
        channel = str(step.config.get("channel", ""))
        configured = WorkflowConfigurationService.value(
            tenant_id,
            f"notification_handlers.{channel}",
        )
        if not isinstance(configured, Mapping):
            raise CapabilityUnavailable(capability=f"notification:{channel}")
        return str(configured["handler"]), str(configured["schema_version"])
    raise ValueError("Only action and notification steps use action handlers")


def _descriptor_health(handler: object) -> tuple[bool, str]:
    try:
        result = handler.health()
    except Exception:
        return False, "degraded"
    healthy = getattr(result, "healthy", None)
    if isinstance(healthy, bool):
        return healthy, "healthy" if healthy else "degraded"
    status_value = getattr(result, "status", None)
    if status_value is None and isinstance(result, Mapping):
        status_value = result.get("status")
    normalized = str(status_value or "").lower()
    return normalized in {"healthy", "ok", "available"}, normalized or "degraded"


def _read_context_path(context: Mapping[str, Any], path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        if not isinstance(value, Mapping) or part not in value:
            raise OperationFailed(
                error_code="CONTEXT_PATH_MISSING",
                message="A configured workflow context value is unavailable.",
                detail={"path": path},
            )
        value = value[part]
    return value


def _mapped_input(mapping: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for target, source in mapping.items():
        if not isinstance(source, str) or not source.strip():
            raise OperationFailed(
                error_code="INPUT_MAPPING_INVALID",
                message="Workflow input mappings must contain context paths.",
            )
        output[str(target)] = _read_context_path(context, source)
    return output


def _action_configuration(step_type: str, config: Mapping[str, Any]) -> dict[str, Any]:
    if step_type == "action":
        if config.get("handler") == "core.context_projection.v1":
            return {"input_mapping": dict(config.get("input_mapping", {}))}
        return dict(config.get("configuration", {}))
    if config.get("channel") == "email":
        return {"template_key": str(config.get("template_key", ""))}
    return {"notification_type": "workflow"}


def _notification_input(instance: WorkflowInstance, step: WorkflowStep) -> dict[str, Any]:
    mapping = step.config.get("recipient_mapping", {})
    recipient_values = _mapped_input(mapping, instance.context_data)
    templates = getattr(settings, "WORKFLOW_NOTIFICATION_TEMPLATES", {})
    template = templates.get(step.config.get("template_key")) if isinstance(templates, Mapping) else None
    if step.config.get("channel") == "email":
        recipient = recipient_values.get("recipient_email") or recipient_values.get("email")
        if not recipient:
            raise OperationFailed(
                error_code="NOTIFICATION_RECIPIENT_MISSING", message="The email recipient is unavailable."
            )
        return {"recipient_email": recipient, "template_context": dict(instance.context_data)}
    if not isinstance(template, Mapping):
        raise CapabilityUnavailable(
            capability=f"notification_template:{step.config.get('template_key', '')}",
            message="The configured notification template is unavailable.",
        )
    recipient = recipient_values.get("recipient_id") or recipient_values.get("user_id")
    title = template.get("title")
    message = template.get("message")
    if not recipient or not isinstance(title, str) or not isinstance(message, str):
        raise OperationFailed(error_code="NOTIFICATION_INPUT_INVALID", message="The notification input is incomplete.")
    try:
        rendered_title = title.format_map(dict(instance.context_data))
        rendered_message = message.format_map(dict(instance.context_data))
    except (KeyError, ValueError) as exc:
        raise OperationFailed(
            error_code="NOTIFICATION_TEMPLATE_FAILED", message="Notification template rendering failed."
        ) from exc
    return {"recipient_id": str(recipient), "title": rendered_title, "message": rendered_message}


def _context_schema_errors(schema: Mapping[str, Any], value: Mapping[str, Any], path: str = "context") -> list[str]:
    """Validate the intentionally small, deterministic JSON Schema subset."""

    errors: list[str] = []
    if schema.get("type", "object") != "object":
        return ["required_context_schema.type must be object"]
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        errors.append("required_context_schema.required must be an array of strings")
        required = []
    for name in required:
        if name not in value:
            errors.append(f"{path}.{name} is required")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        errors.append("required_context_schema.properties must be an object")
        return errors
    allowed_types: dict[str, tuple[type[Any], ...]] = {
        "string": (str,),
        "number": (int, float),
        "integer": (int,),
        "boolean": (bool,),
        "object": (dict,),
        "array": (list,),
        "null": (type(None),),
    }
    for name, item in value.items():
        definition = properties.get(name)
        if definition is None:
            if schema.get("additionalProperties") is False:
                errors.append(f"{path}.{name} is not allowed")
            continue
        if not isinstance(definition, Mapping):
            errors.append(f"required_context_schema.properties.{name} must be an object")
            continue
        expected = definition.get("type")
        if expected in allowed_types:
            expected_types = allowed_types[str(expected)]
            if expected == "integer" and isinstance(item, bool):
                errors.append(f"{path}.{name} must be an integer")
            elif expected == "number" and isinstance(item, bool):
                errors.append(f"{path}.{name} must be a number")
            elif not isinstance(item, expected_types):
                errors.append(f"{path}.{name} must be {expected}")
    return errors


class WorkflowDefinitionService:
    @staticmethod
    def create_workflow(tenant_id: uuid.UUID | str, actor: object, payload: Mapping[str, Any]) -> Workflow:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        clean = dict(payload)
        clean.pop("tenant_id", None)
        result = WorkflowDefinitionService.validate_definition(tenant_uuid, clean)
        if not result.valid:
            raise ValidationError(result.as_dict())
        steps = list(clean.pop("steps", []))
        clean.pop("expected_updated_at", None)
        clean["key"] = str(clean["key"]).strip()
        clean["name"] = str(clean["name"]).strip()
        configuration = WorkflowConfigurationService.get_configuration(tenant_uuid).document
        clean.setdefault("workflow_type", configuration["defaults"]["workflow_type"])
        clean.setdefault("trigger_type", configuration["defaults"]["trigger_type"])

        with transaction.atomic():
            if Workflow.objects.for_tenant(tenant_uuid).filter(key=clean["key"]).exists():
                raise _conflict("WORKFLOW_KEY_EXISTS", "A workflow with this key already exists.")
            workflow = Workflow(
                tenant_id=tenant_uuid,
                version=int(configuration["defaults"]["workflow_version"]),
                status=str(configuration["defaults"]["definition_status"]),
                created_by=actor,
                **clean,
            )
            workflow.full_clean()
            workflow.save(force_insert=True)
            WorkflowDefinitionService._create_steps(tenant_uuid, workflow, steps)
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_definition",
                aggregate_id=workflow.id,
                event_type="workflow.definition.created",
                payload={"workflow_id": str(workflow.id), "version": workflow.version},
            )
        logger.info(
            "Workflow definition created",
            extra={
                "tenant_id": str(tenant_uuid),
                "actor_id": _actor_id(actor),
                "workflow_id": str(workflow.id),
                "command": "create",
                "outcome": "succeeded",
            },
        )
        return WorkflowDefinitionService.get_workflow(tenant_uuid, workflow.id)

    @staticmethod
    def _create_steps(tenant_id: uuid.UUID, workflow: Workflow, steps: Sequence[Mapping[str, Any]]) -> None:
        for raw_step in steps:
            step_data = dict(raw_step)
            step_data.pop("tenant_id", None)
            step = WorkflowStep(tenant_id=tenant_id, workflow=workflow, **step_data)
            step.full_clean()
            step.save(force_insert=True)

    @staticmethod
    def get_workflow(tenant_id: uuid.UUID | str, workflow_id: uuid.UUID | str) -> Workflow:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        workflow_uuid = _as_uuid(workflow_id, "workflow_id")
        try:
            return (
                Workflow.objects.for_tenant(tenant_uuid)
                .filter(deleted_at__isnull=True)
                .select_related("created_by", "published_by")
                .prefetch_related(
                    Prefetch("steps", queryset=WorkflowStep.objects.for_tenant(tenant_uuid).order_by("order"))
                )
                .get(id=workflow_uuid)
            )
        except Workflow.DoesNotExist as exc:
            raise NotFound("Workflow not found.") from exc

    @staticmethod
    def list_workflows(tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None) -> QuerySet[Workflow]:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        values = dict(filters or {})
        queryset = (
            Workflow.objects.for_tenant(tenant_uuid)
            .filter(deleted_at__isnull=True)
            .select_related("created_by")
            .annotate(step_count=Count("steps", filter=Q(steps__tenant_id=tenant_uuid)))
        )
        exact = {
            "status": "status",
            "workflow_type": "workflow_type",
            "trigger_type": "trigger_type",
            "key": "key",
            "created_by": "created_by_id",
        }
        for parameter, field in exact.items():
            if values.get(parameter) not in (None, ""):
                queryset = queryset.filter(**{field: values[parameter]})
        if values.get("updated_after"):
            queryset = queryset.filter(updated_at__gte=values["updated_after"])
        search = str(values.get("search", "")).strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(description__icontains=search) | Q(key__icontains=search)
            )
        ordering = str(values.get("ordering", "-updated_at"))
        allowed = {"name", "version", "created_at", "updated_at"}
        field = ordering.removeprefix("-")
        return queryset.order_by(ordering if field in allowed else "-updated_at", "id")

    @staticmethod
    def update_workflow(
        tenant_id: uuid.UUID | str,
        workflow_id: uuid.UUID | str,
        actor: object,
        payload: Mapping[str, Any],
    ) -> Workflow:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        workflow_uuid = _as_uuid(workflow_id, "workflow_id")
        changes = dict(payload)
        changes.pop("tenant_id", None)
        expected_updated_at = changes.pop("expected_updated_at", None)
        if expected_updated_at is None:
            raise ValidationError({"expected_updated_at": ["This field is required."]})

        with transaction.atomic():
            try:
                workflow = (
                    Workflow.objects.for_tenant(tenant_uuid)
                    .select_for_update()
                    .prefetch_related(
                        Prefetch("steps", queryset=WorkflowStep.objects.for_tenant(tenant_uuid).order_by("order"))
                    )
                    .get(id=workflow_uuid, deleted_at__isnull=True)
                )
            except Workflow.DoesNotExist as exc:
                raise NotFound("Workflow not found.") from exc
            if workflow.status != "draft":
                raise _conflict("WORKFLOW_IMMUTABLE", "Published and archived workflow versions are immutable.")
            expected = (
                expected_updated_at
                if isinstance(expected_updated_at, datetime)
                else datetime.fromisoformat(str(expected_updated_at).replace("Z", "+00:00"))
            )
            if workflow.updated_at != expected:
                raise _conflict(
                    "WORKFLOW_EDIT_CONFLICT",
                    "The workflow changed after it was loaded. Reload before saving.",
                    {"updated_at": workflow.updated_at.isoformat()},
                )

            merged = {
                "key": workflow.key,
                "name": workflow.name,
                "description": workflow.description,
                "workflow_type": workflow.workflow_type,
                "trigger_type": workflow.trigger_type,
                "trigger_config": getattr(workflow, "trigger_config", {}),
                "required_context_schema": workflow.required_context_schema,
                "steps": [
                    WorkflowDefinitionService._step_payload(step)
                    for step in WorkflowStep.objects.for_tenant(tenant_uuid).filter(workflow=workflow).order_by("order")
                ],
            }
            merged.update(changes)
            result = WorkflowDefinitionService.validate_definition(tenant_uuid, merged)
            if not result.valid:
                raise ValidationError(result.as_dict())
            steps = merged.pop("steps")
            merged.pop("key", None)  # The logical key is stable across versions.
            for field, value in merged.items():
                if hasattr(workflow, field):
                    setattr(workflow, field, value)
            workflow.full_clean()
            workflow.save()
            if "steps" in changes:
                WorkflowStep.objects.for_tenant(tenant_uuid).filter(workflow=workflow).delete()
                WorkflowDefinitionService._create_steps(tenant_uuid, workflow, steps)
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_definition",
                aggregate_id=workflow.id,
                event_type="workflow.definition.updated",
                payload={"workflow_id": str(workflow.id), "version": workflow.version},
            )
        return WorkflowDefinitionService.get_workflow(tenant_uuid, workflow_uuid)

    @staticmethod
    def _step_payload(step: WorkflowStep) -> dict[str, Any]:
        fields = {
            "key": step.key,
            "name": step.name,
            "step_type": step.step_type,
            "order": step.order,
            "config": step.config,
            "timeout_seconds": step.timeout_seconds,
            "timeout_action": step.timeout_action,
            "is_terminal": step.is_terminal,
        }
        for optional in ("next_step_keys", "join_key"):
            if hasattr(step, optional):
                fields[optional] = getattr(step, optional)
        return fields

    @staticmethod
    def _pin_handler_contracts(tenant_id: uuid.UUID, workflow: Workflow) -> None:
        """Persist the exact extension ABI consumed by an immutable version."""

        for step in WorkflowStep.objects.for_tenant(tenant_id).filter(workflow=workflow).order_by("order"):
            descriptor: object | None = None
            if step.step_type in {"action", "notification"}:
                handler_key, schema_version = _handler_key_for_step(workflow.tenant_id, step)
                descriptor = _handler_from_registry(action_registry, handler_key, schema_version).descriptor
            elif step.step_type == "decision":
                condition = step.config["condition"]
                condition_key = (
                    condition if isinstance(condition, str) else condition.get("handler") or condition.get("key")
                )
                descriptor = _handler_from_registry(
                    condition_registry,
                    str(condition_key),
                    step.config.get("schema_version"),
                ).descriptor
            if descriptor is None:
                continue
            WorkflowStep.objects.for_tenant(tenant_id).filter(id=step.id, workflow=workflow).update(
                handler_contract_version=str(getattr(descriptor, "contract_version")),
                handler_contract_fingerprint=str(getattr(descriptor, "contract_fingerprint")),
            )

    @staticmethod
    def validate_definition(
        tenant_id: uuid.UUID | str,
        payload: Mapping[str, Any],
    ) -> DefinitionValidationResult:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        configuration = WorkflowConfigurationService.get_configuration(tenant_uuid).document
        errors: list[DefinitionValidationIssue] = []
        warnings: list[DefinitionValidationIssue] = []
        steps = payload.get("steps")
        if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)) or not steps:
            errors.append(
                DefinitionValidationIssue("STEPS_REQUIRED", "At least one workflow step is required.", "steps")
            )
            return DefinitionValidationResult(False, tuple(errors), tuple(warnings))
        key = str(payload.get("key", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not key:
            errors.append(DefinitionValidationIssue("KEY_REQUIRED", "Workflow key must not be blank.", "key"))
        if not name:
            errors.append(DefinitionValidationIssue("NAME_REQUIRED", "Workflow name must not be blank.", "name"))

        workflow_type = str(payload.get("workflow_type", configuration["defaults"]["workflow_type"]))
        if workflow_type not in configuration["allowed_values"]["workflow_types"]:
            errors.append(
                DefinitionValidationIssue(
                    "WORKFLOW_TYPE_UNAVAILABLE",
                    "This workflow type is not enabled for the tenant.",
                    "workflow_type",
                )
            )
        trigger_type = payload.get("trigger_type", configuration["defaults"]["trigger_type"])
        trigger_config = payload.get("trigger_config", {})
        if not isinstance(trigger_config, Mapping):
            errors.append(
                DefinitionValidationIssue(
                    "TRIGGER_CONFIG_INVALID", "Trigger config must be an object.", "trigger_config"
                )
            )
        elif trigger_type not in configuration["allowed_values"]["trigger_types"]:
            errors.append(
                DefinitionValidationIssue(
                    "TRIGGER_TYPE_UNAVAILABLE",
                    "This trigger type has no enabled end-to-end adapter.",
                    "trigger_type",
                )
            )
        else:
            trigger_schema = configuration["trigger_schemas"].get(str(trigger_type))
            if not isinstance(trigger_schema, Mapping):
                errors.append(
                    DefinitionValidationIssue(
                        "TRIGGER_SCHEMA_UNAVAILABLE",
                        "The configured trigger schema is unavailable.",
                        "trigger_config",
                    )
                )
            else:
                allowed_fields = set(trigger_schema.get("allowed", []))
                required_fields = set(trigger_schema.get("required", []))
                if set(trigger_config) - allowed_fields or required_fields - set(trigger_config):
                    errors.append(
                        DefinitionValidationIssue(
                            "TRIGGER_CONFIG_INVALID",
                            "Trigger configuration does not match the tenant schema.",
                            "trigger_config",
                        )
                    )

        schema = payload.get("required_context_schema", {})
        if not isinstance(schema, Mapping):
            errors.append(
                DefinitionValidationIssue(
                    "CONTEXT_SCHEMA_INVALID", "Context schema must be an object.", "required_context_schema"
                )
            )
        else:
            for message in _context_schema_errors(schema, {}):
                if "is required" not in message:
                    errors.append(
                        DefinitionValidationIssue("CONTEXT_SCHEMA_INVALID", message, "required_context_schema")
                    )

        keys: list[str] = []
        orders: list[int] = []
        by_key: dict[str, Mapping[str, Any]] = {}
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, Mapping):
                errors.append(DefinitionValidationIssue("STEP_INVALID", "Step must be an object.", f"steps.{index}"))
                continue
            step_key = str(raw_step.get("key", "")).strip()
            keys.append(step_key)
            by_key[step_key] = raw_step
            try:
                order = int(raw_step.get("order"))
                if order < 1:
                    raise ValueError
                orders.append(order)
            except (TypeError, ValueError):
                errors.append(
                    DefinitionValidationIssue(
                        "STEP_ORDER_INVALID", "Step order must be positive.", f"steps.{index}.order", step_key
                    )
                )
            try:
                validate_step_config(
                    str(raw_step.get("step_type", "")),
                    raw_step.get("config", {}),
                    policy=configuration,
                )
            except ValidationError as exc:
                errors.append(
                    DefinitionValidationIssue("STEP_CONFIG_INVALID", str(exc.detail), f"steps.{index}.config", step_key)
                )
            timeout = raw_step.get("timeout_seconds")
            timeout_action = raw_step.get("timeout_action")
            if (timeout is None) != (timeout_action is None):
                errors.append(
                    DefinitionValidationIssue(
                        "STEP_TIMEOUT_INVALID",
                        "timeout_seconds and timeout_action must be supplied together.",
                        f"steps.{index}",
                        step_key,
                    )
                )
            if isinstance(timeout, int) and (
                timeout < 1 or timeout > int(configuration["limits"]["duration_max_seconds"])
            ):
                errors.append(
                    DefinitionValidationIssue(
                        "STEP_TIMEOUT_INVALID",
                        "timeout_seconds is outside the tenant safe limits.",
                        f"steps.{index}.timeout_seconds",
                        step_key,
                    )
                )
            if timeout_action is not None and timeout_action not in configuration["allowed_values"]["timeout_actions"]:
                errors.append(
                    DefinitionValidationIssue(
                        "TIMEOUT_ACTION_UNCONFIGURED",
                        "This timeout action is not enabled for the tenant.",
                        f"steps.{index}.timeout_action",
                        step_key,
                    )
                )

        duplicates = {item for item in keys if keys.count(item) > 1}
        for duplicate in sorted(duplicates):
            errors.append(
                DefinitionValidationIssue("STEP_KEY_DUPLICATE", "Step keys must be unique.", "steps", duplicate)
            )
        duplicate_orders = {item for item in orders if orders.count(item) > 1}
        if duplicate_orders:
            errors.append(DefinitionValidationIssue("STEP_ORDER_DUPLICATE", "Step orders must be unique.", "steps"))
        if errors:
            return DefinitionValidationResult(False, tuple(errors), tuple(warnings))

        ordered = sorted(by_key.values(), key=lambda step: int(step["order"]))
        edges: dict[str, set[str]] = {str(step["key"]): set() for step in ordered}
        for index, step in enumerate(ordered):
            step_key = str(step["key"])
            config = step.get("config", {})
            if step["step_type"] == "decision":
                edges[step_key].update({str(config["true_step_key"]), str(config["false_step_key"])})
                condition = config["condition"]
                condition_key = (
                    condition if isinstance(condition, str) else condition.get("handler") or condition.get("key")
                )
                try:
                    condition_handler = _handler_from_registry(
                        condition_registry, str(condition_key), config.get("schema_version")
                    )
                    condition_handler.validate(condition)
                except CapabilityUnavailable:
                    errors.append(
                        DefinitionValidationIssue(
                            "CONDITION_UNAVAILABLE",
                            "The registered condition is unavailable.",
                            f"steps.{index}.config.condition",
                            step_key,
                        )
                    )
                except Exception:
                    errors.append(
                        DefinitionValidationIssue(
                            "CONDITION_INVALID",
                            "The condition configuration is invalid.",
                            f"steps.{index}.config.condition",
                            step_key,
                        )
                    )
            elif step["step_type"] == "approval" and config.get("rejection_behavior") == "goto":
                edges[step_key].add(str(config.get("reject_step_key")))
            next_keys = step.get("next_step_keys")
            if isinstance(next_keys, list):
                edges[step_key].update(str(item) for item in next_keys)
            elif index + 1 < len(ordered) and not step.get("is_terminal"):
                edges[step_key].add(str(ordered[index + 1]["key"]))

            if step["step_type"] in {"action", "notification"}:
                proxy = type("StepProxy", (), {"step_type": step["step_type"], "config": config})()
                try:
                    handler_key, schema_version = _handler_key_for_step(
                        tenant_uuid,
                        proxy,  # type: ignore[arg-type]
                    )
                    handler = _handler_from_registry(action_registry, handler_key, schema_version)
                    handler.validate_config(_action_configuration(str(step["step_type"]), config))
                    healthy, _ = _descriptor_health(handler)
                    if not healthy:
                        warnings.append(
                            DefinitionValidationIssue(
                                "HANDLER_DEGRADED",
                                "The handler is currently degraded.",
                                f"steps.{index}.config",
                                step_key,
                                "warning",
                            )
                        )
                except CapabilityUnavailable:
                    errors.append(
                        DefinitionValidationIssue(
                            "HANDLER_UNAVAILABLE",
                            "The registered handler is unavailable.",
                            f"steps.{index}.config",
                            step_key,
                        )
                    )
                except Exception:
                    errors.append(
                        DefinitionValidationIssue(
                            "HANDLER_CONFIG_INVALID",
                            "The handler configuration is invalid.",
                            f"steps.{index}.config",
                            step_key,
                        )
                    )

        all_keys = set(edges)
        for source, targets in edges.items():
            for target in targets:
                if target not in all_keys:
                    errors.append(
                        DefinitionValidationIssue(
                            "STEP_REFERENCE_UNKNOWN", f"Step references unknown target {target!r}.", "steps", source
                        )
                    )
        if errors:
            return DefinitionValidationResult(False, tuple(errors), tuple(warnings))

        root = str(ordered[0]["key"])
        reachable: set[str] = set()
        visiting: set[str] = set()
        cycle_nodes: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                cycle_nodes.add(node)
                return
            if node in reachable:
                return
            visiting.add(node)
            reachable.add(node)
            for child in edges[node]:
                visit(child)
            visiting.remove(node)

        visit(root)
        if cycle_nodes:
            errors.append(
                DefinitionValidationIssue(
                    "WORKFLOW_CYCLE", "Workflow graphs must not contain cycles.", "steps", sorted(cycle_nodes)[0]
                )
            )
        for unreachable in sorted(all_keys - reachable):
            errors.append(
                DefinitionValidationIssue(
                    "STEP_UNREACHABLE", "Step is not reachable from the first step.", "steps", unreachable
                )
            )
        terminals = {str(step["key"]) for step in ordered if step.get("is_terminal") or not edges[str(step["key"])]}
        if not terminals or not (reachable & terminals):
            errors.append(
                DefinitionValidationIssue(
                    "TERMINAL_PATH_MISSING", "The workflow requires a reachable terminal path.", "steps"
                )
            )
        return DefinitionValidationResult(not errors, tuple(errors), tuple(warnings))

    @staticmethod
    def publish_workflow(
        tenant_id: uuid.UUID | str,
        workflow_id: uuid.UUID | str,
        actor: object,
        transition_key: str,
    ) -> Workflow:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        workflow_uuid = _as_uuid(workflow_id, "workflow_id")
        key = _transition_key(tenant_uuid, transition_key)
        with transaction.atomic():
            try:
                workflow = (
                    Workflow.objects.for_tenant(tenant_uuid)
                    .select_for_update()
                    .prefetch_related(
                        Prefetch("steps", queryset=WorkflowStep.objects.for_tenant(tenant_uuid).order_by("order"))
                    )
                    .get(id=workflow_uuid, deleted_at__isnull=True)
                )
            except Workflow.DoesNotExist as exc:
                raise NotFound("Workflow not found.") from exc
            if workflow.status != "draft":
                return _apply_machine(
                    WORKFLOW_DEFINITION_MACHINE,
                    workflow,
                    "publish",
                    transition_key=key,
                    tenant_id=tenant_uuid,
                    context={"definition_valid": True},
                    metadata={"actor_id": _actor_id(actor)},
                )
            result = WorkflowDefinitionService.validate_definition(
                tenant_uuid,
                {
                    "key": workflow.key,
                    "name": workflow.name,
                    "description": workflow.description,
                    "workflow_type": workflow.workflow_type,
                    "trigger_type": workflow.trigger_type,
                    "trigger_config": getattr(workflow, "trigger_config", {}),
                    "required_context_schema": workflow.required_context_schema,
                    "steps": [
                        WorkflowDefinitionService._step_payload(step)
                        for step in WorkflowStep.objects.for_tenant(tenant_uuid)
                        .filter(workflow=workflow)
                        .order_by("order")
                    ],
                },
            )
            if not result.valid:
                raise ValidationError(result.as_dict())
            WorkflowDefinitionService._pin_handler_contracts(tenant_uuid, workflow)
            current = (
                Workflow.objects.for_tenant(tenant_uuid)
                .select_for_update()
                .filter(key=workflow.key, status="published", deleted_at__isnull=True)
                .exclude(id=workflow.id)
                .first()
            )
            if current is not None:
                _apply_machine(
                    WORKFLOW_DEFINITION_MACHINE,
                    current,
                    "archive",
                    transition_key=f"{key}:archive:{current.id}",
                    tenant_id=tenant_uuid,
                    metadata={"actor_id": _actor_id(actor)},
                )
            workflow = _apply_machine(
                WORKFLOW_DEFINITION_MACHINE,
                workflow,
                "publish",
                transition_key=key,
                tenant_id=tenant_uuid,
                context={
                    "definition_valid": True,
                    "handlers_registered": True,
                    "terminal_path_reachable": True,
                    "references_resolved": True,
                },
                metadata={"actor_id": _actor_id(actor)},
            )
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_definition",
                aggregate_id=workflow.id,
                event_type="workflow.definition.published",
                payload={"workflow_id": str(workflow.id), "version": workflow.version},
            )
        return WorkflowDefinitionService.get_workflow(tenant_uuid, workflow_uuid)

    @staticmethod
    def archive_workflow(
        tenant_id: uuid.UUID | str, workflow_id: uuid.UUID | str, actor: object, transition_key: str
    ) -> Workflow:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        workflow_uuid = _as_uuid(workflow_id, "workflow_id")
        key = _transition_key(tenant_uuid, transition_key)
        with transaction.atomic():
            try:
                workflow = (
                    Workflow.objects.for_tenant(tenant_uuid)
                    .select_for_update()
                    .get(id=workflow_uuid, deleted_at__isnull=True)
                )
            except Workflow.DoesNotExist as exc:
                raise NotFound("Workflow not found.") from exc
            replay = _history_has(workflow, key, "archive")
            workflow = _apply_machine(
                WORKFLOW_DEFINITION_MACHINE,
                workflow,
                "archive",
                transition_key=key,
                tenant_id=tenant_uuid,
                metadata={"actor_id": _actor_id(actor)},
            )
            if not replay:
                _emit_event(
                    tenant_uuid,
                    aggregate_type="workflow_definition",
                    aggregate_id=workflow.id,
                    event_type="workflow.definition.archived",
                    payload={"workflow_id": str(workflow.id), "version": workflow.version},
                )
        return WorkflowDefinitionService.get_workflow(tenant_uuid, workflow.id)

    @staticmethod
    def clone_version(tenant_id: uuid.UUID | str, workflow_id: uuid.UUID | str, actor: object) -> Workflow:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        source = WorkflowDefinitionService.get_workflow(tenant_uuid, workflow_id)
        with transaction.atomic():
            siblings = Workflow.objects.for_tenant(tenant_uuid).select_for_update().filter(key=source.key)
            next_version = max(siblings.values_list("version", flat=True), default=0) + 1
            existing = siblings.filter(version=next_version).first()
            if existing is not None:
                return WorkflowDefinitionService.get_workflow(tenant_uuid, existing.id)
            clone = Workflow.objects.for_tenant(tenant_uuid).create(
                tenant_id=tenant_uuid,
                key=source.key,
                version=next_version,
                name=source.name,
                description=source.description,
                workflow_type=source.workflow_type,
                trigger_type=source.trigger_type,
                trigger_config=getattr(source, "trigger_config", {}),
                status=str(
                    WorkflowConfigurationService.value(
                        tenant_uuid,
                        "defaults.definition_status",
                    )
                ),
                required_context_schema=source.required_context_schema,
                created_by=actor,
            )
            WorkflowDefinitionService._create_steps(
                tenant_uuid,
                clone,
                [
                    WorkflowDefinitionService._step_payload(step)
                    for step in WorkflowStep.objects.for_tenant(tenant_uuid).filter(workflow=source).order_by("order")
                ],
            )
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_definition",
                aggregate_id=clone.id,
                event_type="workflow.definition.created",
                payload={"workflow_id": str(clone.id), "version": clone.version, "cloned_from": str(source.id)},
            )
        return WorkflowDefinitionService.get_workflow(tenant_uuid, clone.id)

    @staticmethod
    def delete_draft(tenant_id: uuid.UUID | str, workflow_id: uuid.UUID | str, actor: object) -> None:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        workflow_uuid = _as_uuid(workflow_id, "workflow_id")
        with transaction.atomic():
            try:
                workflow = (
                    Workflow.objects.for_tenant(tenant_uuid)
                    .select_for_update()
                    .get(id=workflow_uuid, deleted_at__isnull=True)
                )
            except Workflow.DoesNotExist as exc:
                raise NotFound("Workflow not found.") from exc
            if (
                workflow.status != "draft"
                or WorkflowInstance.objects.for_tenant(tenant_uuid).filter(workflow=workflow).exists()
            ):
                raise _conflict("WORKFLOW_DELETE_FORBIDDEN", "Only unused draft workflows can be deleted.")
            _apply_machine(
                WORKFLOW_DEFINITION_MACHINE,
                workflow,
                "soft_delete",
                transition_key=f"delete:{workflow.id}",
                tenant_id=tenant_uuid,
                metadata={"actor_id": _actor_id(actor)},
            )
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_definition",
                aggregate_id=workflow.id,
                event_type="workflow.definition.deleted",
                payload={"workflow_id": str(workflow.id)},
            )


class WorkflowExecutionService:
    @staticmethod
    def public_projection(instance: WorkflowInstance) -> tuple[dict[str, Any], dict[str, Any]]:
        """Project only definition-authorized context and result fields."""

        schema = instance.workflow.required_context_schema
        properties = schema.get("properties", {}) if isinstance(schema, Mapping) else {}
        public_context = {
            str(key): instance.context_data[key]
            for key, definition in properties.items()
            if (
                key in instance.context_data
                and isinstance(definition, Mapping)
                and definition.get("x-public") is True
            )
        }
        raw_steps = instance.result_data.get("steps", {})
        public_steps: dict[str, Any] = {}
        if isinstance(raw_steps, Mapping):
            steps = {
                step.key: step
                for step in WorkflowStep.objects.for_tenant(instance.tenant_id).filter(workflow=instance.workflow)
            }
            for step_key, raw_result in raw_steps.items():
                step = steps.get(str(step_key))
                if step is None or not isinstance(raw_result, Mapping):
                    continue
                output = raw_result.get("output", {})
                allowed = step.config.get("public_output_keys", [])
                projected_output = (
                    {
                        key: output[key]
                        for key in allowed
                        if isinstance(key, str) and isinstance(output, Mapping) and key in output
                    }
                    if isinstance(allowed, list)
                    else {}
                )
                public_steps[str(step_key)] = {
                    "status": str(raw_result.get("status", "")),
                    "output": projected_output,
                }
        return public_context, {"steps": public_steps}

    @staticmethod
    def start_workflow(
        tenant_id: uuid.UUID | str,
        workflow_id: uuid.UUID | str,
        actor: object,
        context: Mapping[str, Any],
        idempotency_key: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | str | None = None,
        priority: int | None = None,
    ) -> WorkflowInstance:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        configuration = WorkflowConfigurationService.get_configuration(tenant_uuid).document
        workflow_uuid = _as_uuid(workflow_id, "workflow_id")
        idem = _transition_key(tenant_uuid, idempotency_key, "idempotency_key")
        if not isinstance(context, Mapping):
            raise ValidationError({"context": ["Must be an object."]})
        clean_context = _validate_tenant_json(
            tenant_uuid,
            dict(context),
            path="context",
        )
        if priority is None:
            priority = int(configuration["defaults"]["execution_priority"])
        priority_min = int(configuration["limits"]["execution_priority_min"])
        priority_max = int(configuration["limits"]["execution_priority_max"])
        if isinstance(priority, bool) or not priority_min <= int(priority) <= priority_max:
            raise ValidationError({"priority": [f"Must be between {priority_min} and {priority_max}."]})
        entity_uuid = _as_uuid(entity_id, "entity_id") if entity_id else None
        with transaction.atomic():
            existing = WorkflowInstance.objects.for_tenant(tenant_uuid).filter(idempotency_key=idem).first()
            if existing is not None:
                if existing.workflow_id != workflow_uuid:
                    raise _conflict("IDEMPOTENCY_CONFLICT", "The idempotency key belongs to another workflow start.")
                return existing
            try:
                workflow = (
                    Workflow.objects.for_tenant(tenant_uuid)
                    .select_for_update()
                    .prefetch_related(
                        Prefetch("steps", queryset=WorkflowStep.objects.for_tenant(tenant_uuid).order_by("order"))
                    )
                    .get(id=workflow_uuid, deleted_at__isnull=True)
                )
            except Workflow.DoesNotExist as exc:
                raise NotFound("Workflow not found.") from exc
            if workflow.status != "published":
                raise _conflict("WORKFLOW_NOT_PUBLISHED", "Only published workflows can be started.")
            if workflow.trigger_type != configuration["defaults"]["trigger_type"]:
                raise CapabilityUnavailable(
                    capability=f"workflow_trigger:{workflow.trigger_type}",
                    message="This trigger requires a registered adapter and cannot start through the manual API.",
                )
            if workflow.workflow_type == "parallel":
                raise CapabilityUnavailable(
                    capability="parallel_workflow_execution",
                    message="Parallel execution is unavailable until durable fan-out and join support is configured.",
                )
            result = WorkflowDefinitionService.validate_definition(
                tenant_uuid,
                {
                    "key": workflow.key,
                    "name": workflow.name,
                    "description": workflow.description,
                    "workflow_type": workflow.workflow_type,
                    "trigger_type": workflow.trigger_type,
                    "trigger_config": getattr(workflow, "trigger_config", {}),
                    "required_context_schema": workflow.required_context_schema,
                    "steps": [
                        WorkflowDefinitionService._step_payload(step)
                        for step in WorkflowStep.objects.for_tenant(tenant_uuid)
                        .filter(workflow=workflow)
                        .order_by("order")
                    ],
                },
            )
            if not result.valid:
                raise CapabilityUnavailable(
                    capability="workflow_definition",
                    message="This workflow has unavailable required handlers.",
                    detail=result.as_dict(),
                )
            context_errors = _context_schema_errors(workflow.required_context_schema, clean_context)
            if context_errors:
                raise ValidationError({"context": context_errors})
            instance = WorkflowInstance.objects.for_tenant(tenant_uuid).create(
                tenant_id=tenant_uuid,
                workflow=workflow,
                workflow_version=workflow.version,
                state="pending",
                context_data=clean_context,
                result_data={},
                entity_type=(entity_type or "").strip(),
                entity_id=entity_uuid,
                priority=int(priority),
                idempotency_key=idem,
                correlation_id=_correlation_id(),
                started_by=actor,
            )
            job = enqueue(
                tenant_uuid,
                _actor_id(actor),
                EXECUTE_INSTANCE_COMMAND,
                {"instance_id": str(instance.id)},
                f"workflow-instance:{instance.id}:start",
            )
            instance.async_job_id = job.id
            instance.save(update_fields=("async_job_id", "updated_at"))
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_instance",
                aggregate_id=instance.id,
                event_type="workflow.execution.requested",
                payload={"instance_id": str(instance.id), "workflow_id": str(workflow.id), "job_id": str(job.id)},
            )
            return instance

    @staticmethod
    def get_instance(tenant_id: uuid.UUID | str, instance_id: uuid.UUID | str) -> WorkflowInstance:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        instance_uuid = _as_uuid(instance_id, "instance_id")
        try:
            return (
                WorkflowInstance.objects.for_tenant(tenant_uuid)
                .select_related("workflow", "current_step", "started_by")
                .prefetch_related(
                    Prefetch("tasks", queryset=WorkflowTask.objects.for_tenant(tenant_uuid).select_related("step")),
                    Prefetch(
                        "workflow__steps", queryset=WorkflowStep.objects.for_tenant(tenant_uuid).order_by("order")
                    ),
                )
                .get(id=instance_uuid)
            )
        except WorkflowInstance.DoesNotExist as exc:
            raise NotFound("Workflow instance not found.") from exc

    @staticmethod
    def list_instances(
        tenant_id: uuid.UUID | str, filters: Mapping[str, Any] | None = None
    ) -> QuerySet[WorkflowInstance]:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        values = dict(filters or {})
        queryset = WorkflowInstance.objects.for_tenant(tenant_uuid).select_related(
            "workflow", "current_step", "started_by"
        )
        exact = {
            "workflow_id": "workflow_id",
            "state": "state",
            "entity_type": "entity_type",
            "entity_id": "entity_id",
            "started_by": "started_by_id",
        }
        for parameter, field in exact.items():
            if values.get(parameter) not in (None, ""):
                queryset = queryset.filter(**{field: values[parameter]})
        if values.get("created_after"):
            queryset = queryset.filter(created_at__gte=values["created_after"])
        if values.get("created_before"):
            queryset = queryset.filter(created_at__lte=values["created_before"])
        search = str(values.get("search", "")).strip()
        if search:
            queryset = queryset.filter(
                Q(workflow__name__icontains=search)
                | Q(entity_type__icontains=search)
                | Q(correlation_id__icontains=search)
            )
        ordering = str(values.get("ordering", "-created_at"))
        allowed = {"priority", "created_at", "completed_at"}
        return queryset.order_by(ordering if ordering.removeprefix("-") in allowed else "-created_at", "id")

    @staticmethod
    def cancel_instance(
        tenant_id: uuid.UUID | str,
        instance_id: uuid.UUID | str,
        actor: object,
        transition_key: str,
        reason: str | None = None,
    ) -> WorkflowInstance:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        instance = WorkflowExecutionService.get_instance(tenant_uuid, instance_id)
        key = _transition_key(tenant_uuid, transition_key)
        configured_reason = str(
            reason
            or WorkflowConfigurationService.value(
                tenant_uuid,
                "defaults.cancellation_reason",
            )
        ).strip()
        maximum = int(
            WorkflowConfigurationService.value(
                tenant_uuid,
                "limits.cancellation_reason_max_length",
            )
        )
        if not configured_reason or len(configured_reason) > maximum:
            raise ValidationError(
                {"reason": [f"Must contain between 1 and {maximum} characters."]}
            )
        with transaction.atomic():
            instance = _apply_machine(
                WORKFLOW_INSTANCE_MACHINE,
                instance,
                "cancel",
                transition_key=key,
                tenant_id=tenant_uuid,
                metadata={"actor_id": _actor_id(actor), "reason": redact_text(configured_reason)},
            )
            WorkflowTaskService.cancel_open_tasks(
                tenant_uuid,
                instance.id,
                actor,
                configured_reason,
            )
            if instance.async_job_id:
                job = AsyncJob.objects.for_tenant(tenant_uuid).filter(id=instance.async_job_id).first()
                if job and job.status not in {
                    JobStatus.CANCELLED,
                    JobStatus.SUCCEEDED,
                    JobStatus.FAILED,
                    JobStatus.TIMED_OUT,
                }:
                    transition_job(
                        job.id,
                        tenant_uuid,
                        JobStatus.CANCELLED,
                        expected_status=job.status,
                        actor_id=_actor_id(actor),
                        reason=redact_text(configured_reason),
                    )
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_instance",
                aggregate_id=instance.id,
                event_type="workflow.execution.cancelled",
                payload={"instance_id": str(instance.id), "workflow_id": str(instance.workflow_id)},
            )
        return WorkflowExecutionService.get_instance(tenant_uuid, instance.id)

    @staticmethod
    def execute_instance_job(tenant_id: uuid.UUID | str, job: AsyncJob) -> dict[str, Any]:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        if job.tenant_id != tenant_uuid or job.command != EXECUTE_INSTANCE_COMMAND:
            raise PermissionDenied("Job tenant or command does not match the workflow execution contract.")
        instance_id = job.payload.get("instance_id")
        instance = WorkflowExecutionService.get_instance(tenant_uuid, instance_id)
        if instance.state in TERMINAL_INSTANCE_STATES or instance.state == "waiting":
            return {"instance_id": str(instance.id), "state": instance.state}
        if instance.state == "pending":
            instance = _apply_machine(
                WORKFLOW_INSTANCE_MACHINE,
                instance,
                "start",
                transition_key=f"job:{job.id}:start",
                tenant_id=tenant_uuid,
                metadata={"job_id": str(job.id)},
            )
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_instance",
                aggregate_id=instance.id,
                event_type="workflow.execution.started",
                payload={
                    "instance_id": str(instance.id),
                    "workflow_id": str(instance.workflow_id),
                    "job_id": str(job.id),
                },
            )
        max_steps = max(
            WorkflowStep.objects.for_tenant(tenant_uuid).filter(workflow=instance.workflow).count()
            * int(WorkflowConfigurationService.value(tenant_uuid, "limits.execution_step_multiplier")),
            1,
        )
        for _ in range(max_steps):
            instance = WorkflowExecutionService.execute_current_step(tenant_uuid, instance.id, job_id=job.id)
            if instance.state in TERMINAL_INSTANCE_STATES or instance.state == "waiting":
                return {"instance_id": str(instance.id), "state": instance.state}
        return WorkflowExecutionService.fail_instance(
            tenant_uuid,
            instance.id,
            "EXECUTION_BOUND_EXCEEDED",
            "Workflow exceeded its validated execution bound.",
            f"job:{job.id}:bounded-failure",
        ).result_data

    @staticmethod
    def execute_current_step(
        tenant_id: uuid.UUID | str, instance_id: uuid.UUID | str, *, job_id: uuid.UUID | None = None
    ) -> WorkflowInstance:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        instance = WorkflowExecutionService.get_instance(tenant_uuid, instance_id)
        if instance.state != "running":
            return instance
        step = instance.current_step
        if step is None:
            step = (
                WorkflowStep.objects.for_tenant(tenant_uuid)
                .filter(workflow=instance.workflow)
                .order_by("order")
                .first()
            )
            if step is None:
                return WorkflowExecutionService.fail_instance(
                    tenant_uuid,
                    instance.id,
                    "EMPTY_WORKFLOW",
                    "Published workflow has no executable step.",
                    f"instance:{instance.id}:empty",
                )
            with transaction.atomic():
                locked_instance = (
                    WorkflowInstance.objects.for_tenant(tenant_uuid)
                    .select_for_update()
                    .get(
                        id=instance.id,
                        state="running",
                    )
                )
                locked_instance.current_step = step
                locked_instance.save(update_fields=("current_step", "updated_at"))
                instance.current_step = step
        started = monotonic()
        try:
            execution_primitive = WorkflowConfigurationService.value(
                tenant_uuid,
                f"step_handlers.{step.step_type}",
            )
            if execution_primitive == "registered_action":
                WorkflowExecutionService._execute_action_step(tenant_uuid, instance, step, job_id)
                next_step = WorkflowExecutionService._next_step(tenant_uuid, instance, step)
                return WorkflowExecutionService._advance_or_complete(tenant_uuid, instance, step, next_step, job_id)
            if execution_primitive == "approval_task":
                WorkflowExecutionService._create_approval_task(tenant_uuid, instance, step)
                return _apply_machine(
                    WORKFLOW_INSTANCE_MACHINE,
                    instance,
                    "wait_for_task",
                    transition_key=f"instance:{instance.id}:wait:{step.id}",
                    tenant_id=tenant_uuid,
                    metadata={"step_id": str(step.id), "job_id": str(job_id or "")},
                )
            if execution_primitive == "registered_condition":
                next_step = WorkflowExecutionService._evaluate_decision(tenant_uuid, instance, step)
                with transaction.atomic():
                    locked_instance = (
                        WorkflowInstance.objects.for_tenant(tenant_uuid)
                        .select_for_update()
                        .get(
                            id=instance.id,
                            state="running",
                        )
                    )
                    locked_instance.current_step = next_step
                    locked_instance.save(update_fields=("current_step", "updated_at"))
                return WorkflowExecutionService.get_instance(tenant_uuid, instance.id)
            return WorkflowExecutionService.fail_instance(
                tenant_uuid,
                instance.id,
                "STEP_TYPE_UNSUPPORTED",
                "Workflow step type is unsupported.",
                f"instance:{instance.id}:unsupported:{step.id}",
            )
        except CapabilityUnavailable as exc:
            return WorkflowExecutionService.fail_instance(
                tenant_uuid,
                instance.id,
                "CAPABILITY_UNAVAILABLE",
                exc.public_message,
                f"instance:{instance.id}:unavailable:{step.id}",
            )
        except OperationFailed as exc:
            return WorkflowExecutionService.fail_instance(
                tenant_uuid, instance.id, exc.error_code, exc.public_message, f"instance:{instance.id}:failed:{step.id}"
            )
        finally:
            logger.info(
                "Workflow step execution finished",
                extra={
                    "tenant_id": str(tenant_uuid),
                    "workflow_id": str(instance.workflow_id),
                    "instance_id": str(instance.id),
                    "command": "execute_step",
                    "duration_ms": round((monotonic() - started) * 1000, 3),
                    "outcome": "recorded",
                },
            )

    @staticmethod
    def _execute_action_step(
        tenant_id: uuid.UUID, instance: WorkflowInstance, step: WorkflowStep, job_id: uuid.UUID | None
    ) -> None:
        key, schema_version = _handler_key_for_step(tenant_id, step)
        handler = _handler_from_registry(action_registry, key, schema_version)
        healthy, _ = _descriptor_health(handler)
        if not healthy:
            raise CapabilityUnavailable(capability=key, message="The required workflow handler is degraded.")
        descriptor = handler.descriptor
        if step.handler_contract_version and step.handler_contract_version != descriptor.contract_version:
            raise CapabilityUnavailable(
                capability=key, message="The installed handler version no longer matches this workflow."
            )
        if step.handler_contract_fingerprint and step.handler_contract_fingerprint != descriptor.contract_fingerprint:
            raise CapabilityUnavailable(
                capability=key, message="The installed handler contract no longer matches this workflow."
            )
        configuration = _action_configuration(step.step_type, step.config)
        action_input = (
            _notification_input(instance, step)
            if step.step_type == "notification"
            else _mapped_input(step.config.get("input_mapping", {}), instance.context_data)
        )
        operation_key = f"{job_id or instance.id}:{step.id}"
        input_fingerprint = hashlib.sha256(
            json.dumps(action_input, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        now = timezone.now()
        with transaction.atomic():
            execution = (
                WorkflowStepExecution.objects.for_tenant(tenant_id)
                .select_for_update()
                .filter(operation_key=operation_key)
                .first()
            )
            if execution is not None and execution.state == "succeeded":
                return
            if execution is not None and execution.state == "running":
                WorkflowStepExecution.objects.for_tenant(tenant_id).filter(
                    id=execution.id,
                    state="running",
                ).lifecycle_update(
                    state="failed",
                    completed_at=now,
                    duration_ms=0,
                    failure_code="ACTION_OUTCOME_UNCERTAIN",
                    failure_message=(
                        "A prior delivery ended without durable handler evidence; " "manual reconciliation is required."
                    ),
                    provider_evidence={"reconciled": False},
                )
                raise OperationFailed(
                    error_code="ACTION_OUTCOME_UNCERTAIN",
                    message="A prior action delivery has an uncertain outcome and was not repeated.",
                )
            if execution is not None and execution.state == "failed":
                raise OperationFailed(
                    error_code=execution.failure_code or "ACTION_PREVIOUSLY_FAILED",
                    message=execution.failure_message or "The workflow action previously failed and was not repeated.",
                )
            if execution is None:
                execution = WorkflowStepExecution.objects.for_tenant(tenant_id).create(
                    tenant_id=tenant_id,
                    instance=instance,
                    step=step,
                    attempt=int(
                        WorkflowConfigurationService.value(
                            tenant_id, "defaults.step_execution_attempt"
                        )
                    ),
                    operation_key=operation_key,
                    state="running",
                    handler_key=key,
                    handler_contract_version=descriptor.contract_version,
                    handler_contract_fingerprint=descriptor.contract_fingerprint,
                    input_fingerprint=input_fingerprint,
                    correlation_id=instance.correlation_id,
                    async_job_id=job_id,
                    started_at=now,
                )
            elif execution.state == "cancelled":
                raise OperationFailed(error_code="EXECUTION_CANCELLED", message="The workflow step was cancelled.")
        invocation = WorkflowActionInvocation(
            tenant_id=tenant_id,
            workflow_id=instance.workflow_id,
            instance_id=instance.id,
            step_id=step.id,
            actor_id=str(instance.started_by_id) if instance.started_by_id is not None else None,
            correlation_id=instance.correlation_id,
            idempotency_key=operation_key,
            handler_key=key,
            descriptor_version=descriptor.contract_version,
            descriptor_fingerprint=descriptor.contract_fingerprint,
            config=configuration,
            input=action_input,
            cancellation_probe=lambda: WorkflowInstance.objects.for_tenant(tenant_id)
            .filter(id=instance.id, state="cancelled")
            .exists(),
        )
        started = monotonic()
        result = execute_registered_action(invocation)
        elapsed_ms = max(0, int((monotonic() - started) * 1_000))
        completed_at = timezone.now()
        if result.status != "succeeded":
            WorkflowStepExecution.objects.for_tenant(tenant_id).filter(
                id=execution.id,
                state="running",
            ).lifecycle_update(
                state="failed",
                completed_at=completed_at,
                duration_ms=elapsed_ms,
                failure_code=str(result.error_code or "ACTION_FAILED")[:64],
                failure_message=_safe_failure_message(tenant_id, result.message),
                provider_evidence=dict(result.evidence),
            )
            result.unwrap()
        value = result.unwrap()
        evidence = dict(result.evidence)
        with transaction.atomic():
            locked_instance = (
                WorkflowInstance.objects.for_tenant(tenant_id)
                .select_for_update()
                .get(
                    id=instance.id,
                    state="running",
                )
            )
            result_data = dict(locked_instance.result_data)
            step_results = dict(result_data.get("steps", {}))
            step_results[str(step.key)] = {"status": "succeeded", "evidence": evidence, "output": value}
            result_data["steps"] = step_results
            WorkflowInstance.objects.for_tenant(tenant_id).filter(
                id=locked_instance.id,
                state="running",
            ).lifecycle_update(result_data=result_data)
            WorkflowStepExecution.objects.for_tenant(tenant_id).filter(
                id=execution.id,
                state="running",
            ).lifecycle_update(
                state="succeeded",
                completed_at=completed_at,
                duration_ms=elapsed_ms,
                output_evidence=evidence,
                provider_evidence={"provider": result.provider} if result.provider else {},
            )
            instance.result_data = result_data

    @staticmethod
    def _create_approval_task(tenant_id: uuid.UUID, instance: WorkflowInstance, step: WorkflowStep) -> WorkflowTask:
        config = step.config
        assignment_kind = str(config["assignment_kind"])
        assignee_key = str(config["assignee_id"]).strip()
        due_date = (
            timezone.now() + timedelta(seconds=int(config.get("due_in_seconds") or step.timeout_seconds))
            if (config.get("due_in_seconds") or step.timeout_seconds)
            else None
        )
        task_values: dict[str, Any] = {
            "tenant_id": tenant_id,
            "instance": instance,
            "step": step,
            "assignment_kind": assignment_kind,
            "assignment_key": f"{assignment_kind}:{assignee_key}",
            "status": WorkflowConfigurationService.value(tenant_id, "defaults.task_status"),
            "due_date": due_date,
            "correlation_id": instance.correlation_id,
        }
        if assignment_kind == "user":
            try:
                assignee = User.objects.select_related("profile").get(pk=assignee_key, is_active=True)
            except (User.DoesNotExist, ValueError, TypeError) as exc:
                raise OperationFailed(
                    error_code="ASSIGNEE_NOT_FOUND", message="The configured assignee is unavailable."
                ) from exc
            profile_tenant = getattr(getattr(assignee, "profile", None), "tenant_id", None)
            if str(profile_tenant) != str(tenant_id):
                raise OperationFailed(
                    error_code="ASSIGNEE_NOT_FOUND", message="The configured assignee is unavailable."
                )
            task_values["assignee"] = assignee
        else:
            from src.modules.security_access_control.models import Role

            assignee_uuid = _as_uuid(assignee_key, "assignee_id")
            if not Role.objects.filter(id=assignee_uuid, tenant_id=tenant_id, is_active=True).exists():
                raise OperationFailed(
                    error_code="ASSIGNEE_ROLE_NOT_FOUND", message="The configured assignee role is unavailable."
                )
            task_values["assignee_role_id"] = assignee_uuid
        try:
            task, _ = WorkflowTask.objects.for_tenant(tenant_id).get_or_create(
                tenant_id=tenant_id,
                instance=instance,
                step=step,
                assignment_key=task_values["assignment_key"],
                defaults=task_values,
            )
            return task
        except IntegrityError:
            return WorkflowTask.objects.for_tenant(tenant_id).get(
                instance=instance, step=step, assignment_key=task_values["assignment_key"]
            )

    @staticmethod
    def _evaluate_decision(tenant_id: uuid.UUID, instance: WorkflowInstance, step: WorkflowStep) -> WorkflowStep:
        condition = step.config["condition"]
        condition_key = condition.get("handler")
        handler = _handler_from_registry(condition_registry, str(condition_key), step.config.get("schema_version"))
        mapping = WorkflowConfigurationService.value(
            tenant_id,
            f"condition_input_mappings.{condition_key}",
        )
        if not isinstance(mapping, Mapping):
            evaluation_context = dict(instance.context_data)
        else:
            evaluation_context: dict[str, Any] = {}
            for target, rule in mapping.items():
                if not isinstance(rule, Mapping):
                    raise OperationFailed(
                        error_code="CONDITION_MAPPING_INVALID",
                        message="The configured condition mapping is invalid.",
                    )
                field = str(rule.get("field", ""))
                if rule.get("source") == "context_path":
                    evaluation_context[str(target)] = _read_context_path(
                        instance.context_data,
                        str(condition[field]),
                    )
                elif rule.get("source") == "literal":
                    evaluation_context[str(target)] = condition[field]
                else:
                    raise OperationFailed(
                        error_code="CONDITION_MAPPING_INVALID",
                        message="The configured condition mapping source is invalid.",
                    )
        branch = bool(handler.evaluate(evaluation_context))
        target_key = step.config["true_step_key"] if branch else step.config["false_step_key"]
        try:
            return WorkflowStep.objects.for_tenant(tenant_id).get(workflow=instance.workflow, key=target_key)
        except WorkflowStep.DoesNotExist as exc:
            raise OperationFailed(
                error_code="DECISION_TARGET_MISSING", message="A declared decision branch is unavailable."
            ) from exc

    @staticmethod
    def _next_step(tenant_id: uuid.UUID, instance: WorkflowInstance, step: WorkflowStep) -> WorkflowStep | None:
        next_keys = getattr(step, "next_step_keys", None)
        if isinstance(next_keys, list) and next_keys:
            return (
                WorkflowStep.objects.for_tenant(tenant_id).filter(workflow=instance.workflow, key=next_keys[0]).first()
            )
        return (
            WorkflowStep.objects.for_tenant(tenant_id)
            .filter(workflow=instance.workflow, order__gt=step.order)
            .order_by("order")
            .first()
        )

    @staticmethod
    def _advance_or_complete(
        tenant_id: uuid.UUID,
        instance: WorkflowInstance,
        step: WorkflowStep,
        next_step: WorkflowStep | None,
        job_id: uuid.UUID | None,
    ) -> WorkflowInstance:
        if step.is_terminal or next_step is None:
            with transaction.atomic():
                locked_instance = (
                    WorkflowInstance.objects.for_tenant(tenant_id)
                    .select_for_update()
                    .get(
                        id=instance.id,
                        state="running",
                    )
                )
                locked_instance.current_step = None
                locked_instance.save(update_fields=("current_step", "updated_at"))
                instance.current_step = None
                completed = _apply_machine(
                    WORKFLOW_INSTANCE_MACHINE,
                    instance,
                    "complete",
                    transition_key=f"instance:{instance.id}:complete:{step.id}",
                    tenant_id=tenant_id,
                    metadata={"step_id": str(step.id), "job_id": str(job_id or "")},
                )
                _emit_event(
                    tenant_id,
                    aggregate_type="workflow_instance",
                    aggregate_id=instance.id,
                    event_type="workflow.execution.completed",
                    payload={"instance_id": str(instance.id), "workflow_id": str(instance.workflow_id)},
                )
            return completed
        with transaction.atomic():
            locked_instance = (
                WorkflowInstance.objects.for_tenant(tenant_id)
                .select_for_update()
                .get(
                    id=instance.id,
                    state="running",
                )
            )
            locked_instance.current_step = next_step
            locked_instance.save(update_fields=("current_step", "updated_at"))
        return WorkflowExecutionService.get_instance(tenant_id, instance.id)

    @staticmethod
    def resume_after_task(
        tenant_id: uuid.UUID | str, task_id: uuid.UUID | str, actor: object, transition_key: str
    ) -> WorkflowInstance:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        task = WorkflowTaskService._get_task_row(tenant_uuid, task_id)
        instance = task.instance
        if task.status == "completed":
            pending = WorkflowTask.objects.for_tenant(tenant_uuid).filter(
                instance=instance, step=task.step, status="pending"
            )
            completion_default = WorkflowConfigurationService.value(
                tenant_uuid, "defaults.approval_completion_rule"
            )
            if task.step.config.get("completion_rule", completion_default) == "all" and pending.exists():
                return instance
            next_step = WorkflowExecutionService._next_step(tenant_uuid, instance, task.step)
            if next_step is None or task.step.is_terminal:
                instance = _apply_machine(
                    WORKFLOW_INSTANCE_MACHINE,
                    instance,
                    "task_completed",
                    transition_key=f"{transition_key}:resume",
                    tenant_id=tenant_uuid,
                    metadata={"task_id": str(task.id), "actor_id": _actor_id(actor)},
                )
                return WorkflowExecutionService._advance_or_complete(tenant_uuid, instance, task.step, None, None)
        elif task.status == "rejected":
            behavior = task.step.config.get(
                "rejection_behavior",
                WorkflowConfigurationService.value(
                    tenant_uuid, "defaults.approval_rejection_behavior"
                ),
            )
            if behavior == "cancel":
                return WorkflowExecutionService.cancel_instance(
                    tenant_uuid, instance.id, actor, f"{transition_key}:cancel"
                )
            if behavior != "goto":
                return WorkflowExecutionService.fail_instance(
                    tenant_uuid,
                    instance.id,
                    "TASK_REJECTED",
                    "A required workflow approval was rejected.",
                    f"{transition_key}:fail",
                )
            target_key = task.step.config.get("reject_step_key")
            try:
                next_step = WorkflowStep.objects.for_tenant(tenant_uuid).get(workflow=instance.workflow, key=target_key)
            except WorkflowStep.DoesNotExist as exc:
                raise OperationFailed(
                    error_code="REJECTION_TARGET_MISSING", message="The configured rejection target is unavailable."
                ) from exc
        else:
            raise _conflict("TASK_NOT_DECIDED", "The workflow task has not reached a decision state.")

        instance = _apply_machine(
            WORKFLOW_INSTANCE_MACHINE,
            instance,
            "task_completed",
            transition_key=f"{transition_key}:resume",
            tenant_id=tenant_uuid,
            metadata={"task_id": str(task.id), "actor_id": _actor_id(actor)},
        )
        with transaction.atomic():
            locked_instance = (
                WorkflowInstance.objects.for_tenant(tenant_uuid)
                .select_for_update()
                .get(
                    id=instance.id,
                    state="running",
                )
            )
            locked_instance.current_step = next_step
            locked_instance.save(update_fields=("current_step", "updated_at"))
        job = enqueue(
            tenant_uuid,
            _actor_id(actor),
            EXECUTE_INSTANCE_COMMAND,
            {"instance_id": str(instance.id)},
            f"workflow-instance:{instance.id}:resume:{task.id}",
        )
        with transaction.atomic():
            locked_instance = WorkflowInstance.objects.for_tenant(tenant_uuid).select_for_update().get(id=instance.id)
            locked_instance.async_job_id = job.id
            locked_instance.save(update_fields=("async_job_id", "updated_at"))
        return WorkflowExecutionService.get_instance(tenant_uuid, instance.id)

    @staticmethod
    def fail_instance(
        tenant_id: uuid.UUID | str, instance_id: uuid.UUID | str, code: str, message: str, transition_key: str
    ) -> WorkflowInstance:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        instance = WorkflowExecutionService.get_instance(tenant_uuid, instance_id)
        if instance.state == "failed" and _history_has(instance, transition_key, "fail"):
            return instance
        instance = _apply_machine(
            WORKFLOW_INSTANCE_MACHINE,
            instance,
            "fail",
            transition_key=_transition_key(tenant_uuid, transition_key),
            tenant_id=tenant_uuid,
            metadata={
                "failure_code": str(code)[:64],
                "failure_message": _safe_failure_message(tenant_uuid, message),
            },
        )
        _emit_event(
            tenant_uuid,
            aggregate_type="workflow_instance",
            aggregate_id=instance.id,
            event_type="workflow.execution.failed",
            payload={
                "instance_id": str(instance.id),
                "workflow_id": str(instance.workflow_id),
                "failure_code": str(code)[:64],
            },
        )
        return WorkflowExecutionService.get_instance(tenant_uuid, instance.id)

    @staticmethod
    def to_invocation_result(tenant_id: uuid.UUID | str, instance_id: uuid.UUID | str) -> Any:
        from src.modules.automation_orchestration.workflow_adapter import WorkflowInvocationResult

        instance = WorkflowExecutionService.get_instance(tenant_id, instance_id)
        status_map = {
            "pending": "accepted",
            "running": "accepted",
            "waiting": "accepted",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "failed",
        }
        return WorkflowInvocationResult(
            status=status_map[instance.state],
            instance_id=instance.id,
            output=dict(instance.result_data),
            error_code=instance.failure_code or ("WORKFLOW_CANCELLED" if instance.state == "cancelled" else ""),
            error_message=instance.failure_message
            or ("Workflow execution was cancelled." if instance.state == "cancelled" else ""),
        )


class WorkflowTaskService:
    @staticmethod
    def _get_task_row(tenant_id: uuid.UUID, task_id: uuid.UUID | str, *, lock: bool = False) -> WorkflowTask:
        task_uuid = _as_uuid(task_id, "task_id")
        queryset = WorkflowTask.objects.for_tenant(tenant_id).select_related("instance__workflow", "step", "assignee")
        if lock:
            queryset = queryset.select_for_update()
        try:
            return queryset.get(id=task_uuid)
        except WorkflowTask.DoesNotExist as exc:
            raise NotFound("Workflow task not found.") from exc

    @staticmethod
    def _effective_permissions(tenant_id: uuid.UUID, actor: object) -> set[str]:
        permissions: set[str] = set()
        if getattr(actor, "is_superuser", False):
            permissions.update({"workflow_automation.task:manage", "workflow_automation.task:self_approve"})
        try:
            from src.modules.security_access_control.services import SecurityAccessControlService

            effective = SecurityAccessControlService.get_user_effective_permissions(getattr(actor, "pk"), tenant_id)
            permissions.update(effective)
            permissions.update(
                permission.replace("workflow_automation:task:", "workflow_automation.task:")
                for permission in effective
                if permission.startswith("workflow_automation:task:")
            )
        except Exception:
            pass
        return permissions

    @staticmethod
    def _is_role_eligible(tenant_id: uuid.UUID, actor: object, role_id: uuid.UUID | None) -> bool:
        if role_id is None:
            return False
        try:
            from src.modules.security_access_control.models import UserRole

            now = timezone.now()
            return (
                UserRole.objects.filter(
                    user=actor, role_id=role_id, role__tenant_id=tenant_id, role__is_active=True, valid_from__lte=now
                )
                .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
                .exists()
            )
        except Exception:
            return False

    @staticmethod
    def _can_manage(tenant_id: uuid.UUID, actor: object) -> bool:
        return "workflow_automation.task:manage" in WorkflowTaskService._effective_permissions(tenant_id, actor)

    @staticmethod
    def _verify_assignment(
        tenant_id: uuid.UUID,
        task: WorkflowTask,
        actor: object,
        *,
        for_decision: bool = False,
    ) -> None:
        direct = task.assignment_kind == "user" and str(task.assignee_id) == str(getattr(actor, "pk", None))
        role = task.assignment_kind == "role" and WorkflowTaskService._is_role_eligible(
            tenant_id, actor, task.assignee_role_id
        )
        manager = WorkflowTaskService._can_manage(tenant_id, actor)
        if not (direct or role or manager):
            raise PermissionDenied("The workflow task is not assigned to this actor.")
        author_id = task.instance.workflow.created_by_id
        if (
            for_decision
            and str(author_id) == str(getattr(actor, "pk", None))
            and "workflow_automation.task:self_approve"
            not in WorkflowTaskService._effective_permissions(tenant_id, actor)
        ):
            raise PermissionDenied(
                "Workflow authors may not approve their own task without explicit policy permission."
            )

    @staticmethod
    def get_task(tenant_id: uuid.UUID | str, task_id: uuid.UUID | str, actor: object) -> WorkflowTask:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        task = WorkflowTaskService._get_task_row(tenant_uuid, task_id)
        WorkflowTaskService._verify_assignment(tenant_uuid, task, actor)
        return task

    @staticmethod
    def list_tasks(
        tenant_id: uuid.UUID | str, actor: object, filters: Mapping[str, Any] | None = None
    ) -> QuerySet[WorkflowTask]:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        values = dict(filters or {})
        queryset = WorkflowTask.objects.for_tenant(tenant_uuid).select_related("instance__workflow", "step", "assignee")
        scope = values.get("scope", "mine")
        if scope == "all":
            if not WorkflowTaskService._can_manage(tenant_uuid, actor):
                raise PermissionDenied("Managed task scope requires task-management permission.")
        else:
            from src.modules.security_access_control.models import UserRole

            now = timezone.now()
            role_ids = (
                UserRole.objects.filter(
                    user=actor, role__tenant_id=tenant_uuid, role__is_active=True, valid_from__lte=now
                )
                .filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
                .values_list("role_id", flat=True)
            )
            queryset = queryset.filter(Q(assignee=actor) | Q(assignee_role_id__in=role_ids))
        exact = {
            "status": "status",
            "workflow_id": "instance__workflow_id",
            "instance_id": "instance_id",
            "assignment_kind": "assignment_kind",
        }
        for parameter, field in exact.items():
            if values.get(parameter) not in (None, ""):
                queryset = queryset.filter(**{field: values[parameter]})
        if str(values.get("overdue", "")).lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(status="pending", due_date__lt=timezone.now())
        if values.get("due_before"):
            queryset = queryset.filter(due_date__lte=values["due_before"])
        search = str(values.get("search", "")).strip()
        if search:
            queryset = queryset.filter(Q(instance__workflow__name__icontains=search) | Q(step__name__icontains=search))
        ordering = str(values.get("ordering", "due_date,created_at"))
        requested = [field.strip() for field in ordering.split(",") if field.strip()]
        allowed = {"due_date", "created_at"}
        valid = [field for field in requested if field.removeprefix("-") in allowed]
        return queryset.order_by(*(valid or ["due_date", "created_at"]), "id")

    @staticmethod
    def complete_task(
        tenant_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        actor: object,
        meta_data: Mapping[str, Any],
        transition_key: str,
    ) -> WorkflowTask:
        return WorkflowTaskService._decide(tenant_id, task_id, actor, "complete", meta_data, transition_key)

    @staticmethod
    def reject_task(
        tenant_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        actor: object,
        reason: str,
        meta_data: Mapping[str, Any],
        transition_key: str,
    ) -> WorkflowTask:
        if not isinstance(reason, str) or not reason.strip():
            raise ValidationError({"reason": ["A rejection reason is required."]})
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        maximum = int(WorkflowConfigurationService.value(tenant_uuid, "limits.reject_reason_max_length"))
        if len(reason.strip()) > maximum:
            raise ValidationError({"reason": [f"Must not exceed {maximum} characters."]})
        evidence = dict(meta_data)
        evidence["reason"] = reason.strip()
        return WorkflowTaskService._decide(tenant_id, task_id, actor, "reject", evidence, transition_key)

    @staticmethod
    def _decide(
        tenant_id: uuid.UUID | str,
        task_id: uuid.UUID | str,
        actor: object,
        command: str,
        meta_data: Mapping[str, Any],
        transition_key: str,
    ) -> WorkflowTask:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        key = _transition_key(tenant_uuid, transition_key)
        clean_meta = _validate_tenant_json(
            tenant_uuid,
            dict(meta_data),
            path="meta_data",
        )
        with transaction.atomic():
            task = WorkflowTaskService._get_task_row(tenant_uuid, task_id, lock=True)
            WorkflowTaskService._verify_assignment(tenant_uuid, task, actor, for_decision=True)
            if _history_has(task, key, command):
                return task
            task.meta_data = {**task.meta_data, **clean_meta}
            task.save(update_fields=("meta_data", "updated_at"))
            task = _apply_machine(
                WORKFLOW_TASK_MACHINE,
                task,
                command,
                transition_key=key,
                tenant_id=tenant_uuid,
                metadata={"actor_id": _actor_id(actor)},
            )
            WorkflowExecutionService.resume_after_task(tenant_uuid, task.id, actor, key)
            _emit_event(
                tenant_uuid,
                aggregate_type="workflow_task",
                aggregate_id=task.id,
                event_type=f"workflow.task.{command}d",
                payload={"task_id": str(task.id), "instance_id": str(task.instance_id)},
            )
            return WorkflowTaskService._get_task_row(tenant_uuid, task.id)

    @staticmethod
    def expire_due_tasks(tenant_id: uuid.UUID | str, now: datetime) -> int:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        if not isinstance(now, datetime):
            raise ValidationError({"now": ["Must be a datetime."]})
        task_ids = list(
            WorkflowTask.objects.for_tenant(tenant_uuid)
            .filter(status="pending", due_date__lte=now)
            .values_list("id", flat=True)
        )
        expired = 0
        for task_id in task_ids:
            with transaction.atomic():
                task = WorkflowTaskService._get_task_row(tenant_uuid, task_id, lock=True)
                if task.status != "pending" or not task.due_date or task.due_date > now:
                    continue
                key = f"task:{task.id}:expire:{task.due_date.isoformat()}"
                task = _apply_machine(
                    WORKFLOW_TASK_MACHINE,
                    task,
                    "expire",
                    transition_key=key,
                    tenant_id=tenant_uuid,
                    metadata={"actor_id": "system"},
                )
                action = task.step.timeout_action or WorkflowConfigurationService.value(
                    tenant_uuid, "defaults.timeout_action"
                )
                if action == "cancel":
                    WorkflowExecutionService.cancel_instance(
                        tenant_uuid, task.instance_id, _SystemActor(), f"{key}:cancel"
                    )
                elif action in {"notify", "escalate"}:
                    WorkflowExecutionService.fail_instance(
                        tenant_uuid,
                        task.instance_id,
                        "TIMEOUT_CAPABILITY_UNAVAILABLE",
                        "The configured timeout capability is unavailable.",
                        f"{key}:unavailable",
                    )
                else:
                    WorkflowExecutionService.fail_instance(
                        tenant_uuid,
                        task.instance_id,
                        "TASK_EXPIRED",
                        "A workflow approval task expired.",
                        f"{key}:fail",
                    )
                expired += 1
        return expired

    @staticmethod
    def cancel_open_tasks(tenant_id: uuid.UUID | str, instance_id: uuid.UUID | str, actor: object, reason: str) -> int:
        tenant_uuid = _as_uuid(tenant_id, "tenant_id")
        instance_uuid = _as_uuid(instance_id, "instance_id")
        ids = list(
            WorkflowTask.objects.for_tenant(tenant_uuid)
            .filter(instance_id=instance_uuid, status="pending")
            .values_list("id", flat=True)
        )
        cancelled = 0
        for task_id in ids:
            with transaction.atomic():
                task = WorkflowTaskService._get_task_row(tenant_uuid, task_id, lock=True)
                if task.status != "pending":
                    continue
                task.meta_data = {
                    **task.meta_data,
                    "cancellation_reason": _safe_failure_message(tenant_uuid, reason),
                }
                task.save(update_fields=("meta_data", "updated_at"))
                _apply_machine(
                    WORKFLOW_TASK_MACHINE,
                    task,
                    "cancel",
                    transition_key=f"task:{task.id}:cancel:{instance_uuid}",
                    tenant_id=tenant_uuid,
                    metadata={"actor_id": _actor_id(actor)},
                )
                cancelled += 1
        return cancelled


class _SystemActor:
    pk = "system"
    id = "system"
    is_superuser = True


class SaraiseWorkflowExecutionAdapter:
    """DTO-only automation-orchestration SPI implementation."""

    version = "1.0"

    def invoke(self, request: Any) -> Any:
        try:
            actor = User.objects.get(pk=request.actor_id)
        except (User.DoesNotExist, ValueError, TypeError):
            from src.modules.automation_orchestration.workflow_adapter import WorkflowInvocationResult

            return WorkflowInvocationResult(
                status="unavailable", error_code="ACTOR_UNAVAILABLE", error_message="The workflow actor is unavailable."
            )
        instance = WorkflowExecutionService.start_workflow(
            request.tenant_id, request.workflow_id, actor, request.input, request.idempotency_token
        )
        return WorkflowExecutionService.to_invocation_result(request.tenant_id, instance.id)

    def cancel(self, tenant_id: uuid.UUID, instance_id: uuid.UUID, idempotency_token: str) -> bool:
        instance = WorkflowExecutionService.get_instance(tenant_id, instance_id)
        actor = instance.started_by
        if actor is None:
            return False
        cancelled = WorkflowExecutionService.cancel_instance(tenant_id, instance_id, actor, idempotency_token)
        return cancelled.state == "cancelled"

    def available(self) -> bool:
        try:
            from src.core.async_jobs.services import get_handler

            get_handler(EXECUTE_INSTANCE_COMMAND)
            return True
        except Exception:
            return False


# Compatibility facade for old in-process callers.  It contains no business
# logic and delegates to the governed services.
class WorkflowEngine:
    def start_workflow(
        self, workflow_id: Any, tenant_id: Any, user: object, context_data: Mapping[str, Any] | None = None
    ) -> WorkflowInstance:
        return WorkflowExecutionService.start_workflow(
            tenant_id, workflow_id, user, context_data or {}, str(uuid.uuid4())
        )

    def transition_task(
        self,
        task_id: Any,
        tenant_id: Any,
        action: str,
        meta_data: Mapping[str, Any] | None = None,
        actor: object | None = None,
    ) -> WorkflowTask:
        if actor is None:
            raise PermissionDenied("An authenticated actor is required.")
        key = str(uuid.uuid4())
        if action == "complete":
            return WorkflowTaskService.complete_task(tenant_id, task_id, actor, meta_data or {}, key)
        if action == "reject":
            reason = str((meta_data or {}).get("reason", ""))
            return WorkflowTaskService.reject_task(tenant_id, task_id, actor, reason, meta_data or {}, key)
        raise ValidationError({"action": ["Unsupported task action."]})
