"""Tenant-first command services for the governed AI agent runtime.

All mutations are transactional.  Controllers only validate transport data and
delegate here; workers reuse the same commands under an explicit tenant
context.  Provider/tool content is intentionally excluded from logs and audit
snapshots.
"""

from __future__ import annotations

import ipaddress
import hashlib
import socket
from copy import deepcopy
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, QuerySet, Sum
from django.utils import timezone

from src.core.access.entitlements import Quota, QuotaService
from src.core.api import OperationResult
from src.core.async_jobs.models import AsyncJob, JobStatus
from src.core.async_jobs.services import enqueue, transition as transition_job
from src.core.encryption import EncryptionService
from src.core.middleware.correlation import get_correlation_id
from src.core.state_machine import (
    IdempotencyConflictError,
    IllegalTransitionError,
    StateMachine,
    TerminalStateError,
    Transition,
)

from .approval_models import ApprovalRequest, SoDPolicy, SoDViolation
from .audit_models import AuditEvent, AuditTrail
from .egress_models import EgressRequest, EgressRule, Secret, SecretAccess, SecretRotationRecord
from .models import (
    Agent,
    AgentExecution,
    AgentManagementConfiguration,
    AgentManagementConfigurationVersion,
    AgentSchedulerTask,
)
from .quota_models import KillSwitch, QuotaUsage, ShardSaturation
from .registries import evaluation_registry, runner_registry
from .token_models import CostRecord, CostSummary, TokenUsage
from .tool_models import Tool, ToolInvocation
from .tool_registry import RestrictedToolContext, ToolNotRegistered, ToolRegistry, tool_registry

EXECUTE_COMMAND = "ai_agent_management.execute"
SCHEDULE_COMMAND = "ai_agent_management.dispatch_schedule"
EVALUATE_COMMAND = "ai_agent_management.evaluate"
RED_TEAM_COMMAND = "ai_agent_management.red_team"
INVOKE_TOOL_COMMAND = "ai_agent_management.invoke_tool"
EXPIRE_APPROVALS_COMMAND = "ai_agent_management.expire_approvals"
AGGREGATE_COST_COMMAND = "ai_agent_management.aggregate_cost"
KILL_SWITCH_COMMAND = "ai_agent_management.enforce_kill_switch"

CONFIGURATION_ENVIRONMENTS = ("development", "staging", "production")
DEFAULT_CONFIGURATION: dict[str, Any] = {
    "schema_version": "1.0",
    "provider": {
        "max_tokens": 4096,
        "temperature": 0.7,
        "timeout_seconds": 30,
        "max_retries": 3,
        "retry_backoff_seconds": 0.25,
        "circuit_failure_threshold": 5,
        "circuit_reset_seconds": 60,
    },
    "runner": {
        "allowed_task_fields": ["messages", "temperature", "max_tokens", "stop_sequences"],
        "maximum_messages": 100,
        "allowed_roles": ["system", "user", "assistant", "tool"],
    },
    "registry": {"key_maximum_length": 100},
    "agent": {
        "metadata_fields": ["schema_version", "runner_key", "provider", "model", "pricing_version", "reason_code"],
        "transition_key_maximum_length": 255,
        "execution_idempotency_key_maximum_length": 255,
        "search_maximum_length": 255,
        "ordering_fields": ["name", "-name", "created_at", "-created_at", "updated_at", "-updated_at"],
        "transition_reason_maximum_length": 100,
        "error_code_maximum_length": 100,
        "user_bound_requires_active_session": True,
        "only_active_agents_may_execute": True,
        "identity_session_rules": {
            "user_bound_requires_session": True,
            "system_bound_forbids_session": True,
        },
        "execution_state_transitions": {
            "created": ["validated", "failed", "terminated"],
            "validated": ["queued", "failed", "terminated"],
            "queued": ["running", "failed", "terminated", "timed_out"],
            "running": ["paused", "completed", "failed", "terminated", "timed_out"],
            "paused": ["running", "failed", "terminated", "timed_out"],
            "completed": [],
            "failed": [],
            "terminated": [],
            "timed_out": [],
        },
    },
    "schedule": {
        "default_priority": 0,
        "priority_minimum": -100,
        "priority_maximum": 100,
        "default_maximum_retries": 3,
        "maximum_retries_limit": 65535,
        "dispatch_batch_minimum": 1,
        "dispatch_batch_maximum": 1000,
    },
    "approval": {
        "require_for_non_read_only_tools": True,
        "requester_may_approve_own_request": False,
        "enforce_expiry": True,
        "rejection_requires_reason": True,
        "only_requester_may_cancel": True,
    },
    "separation_of_duties": {
        "actions_must_be_nonempty_and_different": True,
        "counterpart_detection_enabled": True,
    },
    "egress": {
        "forbidden_ip_addresses": [
            "0.0.0.0",
            "255.255.255.255",
            "::",
            "169.254.169.254",
            "100.100.100.200",
            "fd00:ec2::254",
        ],
        "internal_hostname_suffixes": ["localhost", "metadata", "metadata.google.internal", ".local", ".internal"],
        "allowed_url_schemes": ["http", "https"],
        "forbid_url_credentials": True,
        "forbid_url_query": True,
        "forbid_url_fragment": True,
    },
    "health": {
        "cache_probe_timeout_seconds": 5,
        "minimum_rls_table_count": 21,
        "outbox_stale_minutes": 5,
    },
    "evaluation": {
        "quality_pass_threshold": 0.8,
        "quality_warn_threshold": 0.5,
        "hallucination_pass_threshold": 0.9,
        "hallucination_warn_threshold": 0.7,
        "max_token_fallback": 4096,
        "characters_per_estimated_token": 4,
        "minimum_useful_output_length": 20,
        "short_output_penalty": 0.3,
        "efficiency_pass_threshold": 0.7,
        "efficiency_warn_threshold": 0.4,
        "latency_percentiles": [0.95, 0.99],
    },
    "secret": {"rotation_interval_minimum_days": 1},
    "ui": {
        "agent_page_size": 25,
        "execution_page_size": 25,
        "execution_poll_interval_ms": 5000,
        "approval_page_size": 100,
        "approval_poll_interval_ms": 30000,
        "schedule_page_size": 25,
        "selection_page_size": 100,
        "usage_page_size": 100,
        "summary_page_size": 25,
        "health_poll_interval_ms": 60000,
        "saturation_warning_threshold": 0.6,
        "saturation_critical_threshold": 0.8,
        "status_tokens": {
            "success": "status-success",
            "info": "status-info",
            "warning": "status-warning",
            "danger": "status-danger",
            "neutral": "status-neutral",
        },
        "status_token_by_state": {
            "active": "success",
            "completed": "success",
            "approved": "success",
            "running": "info",
            "queued": "info",
            "pending": "warning",
            "paused": "warning",
            "failed": "danger",
            "rejected": "danger",
            "blocked": "danger",
            "disabled": "neutral",
            "retired": "neutral",
        },
        "navigation_order": {
            "agents": 30,
            "executions": 31,
            "schedules": 32,
            "approvals": 33,
            "tools": 34,
            "configuration": 35,
            "governance": 36,
            "usage": 37,
            "audit": 38,
        },
    },
    "rollout": {"enabled": True, "roles": [], "cohorts": []},
}


class AgentServiceError(RuntimeError):
    """Stable service error safe to map at the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConfigurationService:
    """Validate and version the complete tenant runtime policy document."""

    @staticmethod
    def _environment(value: str | None) -> str:
        environment = str(value or "production").strip().lower()
        if environment not in CONFIGURATION_ENVIRONMENTS:
            raise ValidationError({"environment": f"Must be one of {', '.join(CONFIGURATION_ENVIRONMENTS)}."})
        return environment

    @staticmethod
    def _correlation(value: UUID | str) -> UUID:
        return _uuid(value, "correlation_id")

    @staticmethod
    def _number(
        document: Mapping[str, Any],
        section: str,
        key: str,
        minimum: float,
        maximum: float,
        *,
        integer: bool = False,
    ) -> None:
        value = document[section][key]
        expected = int if integer else (int, float)
        if isinstance(value, bool) or not isinstance(value, expected) or not minimum <= float(value) <= maximum:
            kind = "integer" if integer else "number"
            raise ValidationError(
                {f"{section}.{key}": f"Must be a {kind} between {minimum:g} and {maximum:g}."}
            )

    @classmethod
    def validate_document(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValidationError({"document": "Must be a JSON object."})
        document = deepcopy(dict(value))
        expected_sections = set(DEFAULT_CONFIGURATION)
        if set(document) != expected_sections:
            unknown = sorted(set(document) - expected_sections)
            missing = sorted(expected_sections - set(document))
            raise ValidationError(
                {"document": f"Document sections must match the schema; missing={missing}, unknown={unknown}."}
            )
        for section, defaults in DEFAULT_CONFIGURATION.items():
            if section == "schema_version":
                if document[section] != defaults:
                    raise ValidationError({"schema_version": "Unsupported configuration schema version."})
                continue
            if not isinstance(document[section], dict) or set(document[section]) != set(defaults):
                raise ValidationError({section: "Fields must exactly match the configuration schema."})

        numeric_bounds = (
            ("provider", "max_tokens", 1, 1_000_000, True),
            ("provider", "temperature", 0, 2, False),
            ("provider", "timeout_seconds", 1, 600, True),
            ("provider", "max_retries", 0, 20, True),
            ("provider", "retry_backoff_seconds", 0, 60, False),
            ("provider", "circuit_failure_threshold", 1, 100, True),
            ("provider", "circuit_reset_seconds", 1, 3600, True),
            ("runner", "maximum_messages", 1, 10_000, True),
            ("registry", "key_maximum_length", 1, 255, True),
            ("agent", "transition_key_maximum_length", 16, 1024, True),
            ("agent", "execution_idempotency_key_maximum_length", 16, 1024, True),
            ("agent", "search_maximum_length", 1, 4096, True),
            ("agent", "transition_reason_maximum_length", 1, 4096, True),
            ("agent", "error_code_maximum_length", 1, 255, True),
            ("schedule", "default_priority", -100, 100, True),
            ("schedule", "priority_minimum", -100, 100, True),
            ("schedule", "priority_maximum", -100, 100, True),
            ("schedule", "default_maximum_retries", 0, 65535, True),
            ("schedule", "maximum_retries_limit", 0, 65535, True),
            ("schedule", "dispatch_batch_minimum", 1, 1000, True),
            ("schedule", "dispatch_batch_maximum", 1, 1000, True),
            ("health", "cache_probe_timeout_seconds", 1, 300, True),
            ("health", "minimum_rls_table_count", 1, 1000, True),
            ("health", "outbox_stale_minutes", 1, 1440, True),
            ("evaluation", "quality_pass_threshold", 0, 1, False),
            ("evaluation", "quality_warn_threshold", 0, 1, False),
            ("evaluation", "hallucination_pass_threshold", 0, 1, False),
            ("evaluation", "hallucination_warn_threshold", 0, 1, False),
            ("evaluation", "max_token_fallback", 1, 1_000_000, True),
            ("evaluation", "characters_per_estimated_token", 1, 20, True),
            ("evaluation", "minimum_useful_output_length", 0, 10_000, True),
            ("evaluation", "short_output_penalty", 0, 1, False),
            ("evaluation", "efficiency_pass_threshold", 0, 1, False),
            ("evaluation", "efficiency_warn_threshold", 0, 1, False),
            ("secret", "rotation_interval_minimum_days", 1, 3650, True),
            ("ui", "agent_page_size", 1, 100, True),
            ("ui", "execution_page_size", 1, 100, True),
            ("ui", "execution_poll_interval_ms", 1000, 300_000, True),
            ("ui", "approval_page_size", 1, 100, True),
            ("ui", "approval_poll_interval_ms", 1000, 300_000, True),
            ("ui", "schedule_page_size", 1, 100, True),
            ("ui", "selection_page_size", 1, 100, True),
            ("ui", "usage_page_size", 1, 100, True),
            ("ui", "summary_page_size", 1, 100, True),
            ("ui", "health_poll_interval_ms", 5_000, 300_000, True),
            ("ui", "saturation_warning_threshold", 0, 1, False),
            ("ui", "saturation_critical_threshold", 0, 1, False),
        )
        for section, key, minimum, maximum, integer in numeric_bounds:
            cls._number(document, section, key, minimum, maximum, integer=integer)
        for key, value in document["ui"]["navigation_order"].items():
            if isinstance(value, bool) or not isinstance(value, int) or not -1_000 <= value <= 1_000:
                raise ValidationError({f"ui.navigation_order.{key}": "Must be an integer from -1000 to 1000."})
        if len(set(document["ui"]["navigation_order"].values())) != len(
            document["ui"]["navigation_order"]
        ):
            raise ValidationError({"ui.navigation_order": "Every navigation item requires a unique order."})

        if document["schedule"]["priority_minimum"] > document["schedule"]["default_priority"]:
            raise ValidationError({"schedule.default_priority": "Must not be below the configured priority minimum."})
        if document["schedule"]["default_priority"] > document["schedule"]["priority_maximum"]:
            raise ValidationError({"schedule.default_priority": "Must not exceed the configured priority maximum."})
        if document["schedule"]["default_maximum_retries"] > document["schedule"]["maximum_retries_limit"]:
            raise ValidationError({"schedule.default_maximum_retries": "Must not exceed the retry limit."})
        if document["schedule"]["dispatch_batch_minimum"] > document["schedule"]["dispatch_batch_maximum"]:
            raise ValidationError({"schedule.dispatch_batch_minimum": "Must not exceed the batch maximum."})
        for prefix in ("quality", "hallucination", "efficiency"):
            if document["evaluation"][f"{prefix}_warn_threshold"] > document["evaluation"][f"{prefix}_pass_threshold"]:
                raise ValidationError({f"evaluation.{prefix}_warn_threshold": "Must not exceed the pass threshold."})
        if document["ui"]["saturation_warning_threshold"] > document["ui"]["saturation_critical_threshold"]:
            raise ValidationError({"ui.saturation_warning_threshold": "Must not exceed the critical threshold."})

        allowlists = (
            ("runner", "allowed_task_fields"),
            ("runner", "allowed_roles"),
            ("agent", "metadata_fields"),
            ("agent", "ordering_fields"),
            ("egress", "forbidden_ip_addresses"),
            ("egress", "internal_hostname_suffixes"),
            ("egress", "allowed_url_schemes"),
            ("evaluation", "latency_percentiles"),
            ("rollout", "roles"),
            ("rollout", "cohorts"),
        )
        for section, key in allowlists:
            items = document[section][key]
            if not isinstance(items, list) or len(items) != len(set(map(str, items))):
                raise ValidationError({f"{section}.{key}": "Must be a duplicate-free list."})
        if not document["runner"]["allowed_task_fields"] or not document["runner"]["allowed_roles"]:
            raise ValidationError({"runner": "Task-field and role allow-lists must not be empty."})
        allowed_task_fields = {"messages", "temperature", "max_tokens", "stop_sequences"}
        if not set(document["runner"]["allowed_task_fields"]).issubset(allowed_task_fields):
            raise ValidationError({"runner.allowed_task_fields": "Contains an unsupported task field."})
        if not set(document["runner"]["allowed_roles"]).issubset({"system", "user", "assistant", "tool"}):
            raise ValidationError({"runner.allowed_roles": "Contains an unsupported message role."})
        allowed_metadata = set(DEFAULT_CONFIGURATION["agent"]["metadata_fields"])
        if not set(document["agent"]["metadata_fields"]).issubset(allowed_metadata):
            raise ValidationError({"agent.metadata_fields": "Contains a sensitive or unsupported field."})
        allowed_ordering = set(DEFAULT_CONFIGURATION["agent"]["ordering_fields"])
        if not set(document["agent"]["ordering_fields"]).issubset(allowed_ordering):
            raise ValidationError({"agent.ordering_fields": "Contains an unsupported ordering field."})
        if not set(document["egress"]["allowed_url_schemes"]).issubset({"http", "https"}):
            raise ValidationError({"egress.allowed_url_schemes": "Only HTTP and HTTPS can be enabled."})
        required_forbidden_addresses = set(DEFAULT_CONFIGURATION["egress"]["forbidden_ip_addresses"])
        if not required_forbidden_addresses.issubset(document["egress"]["forbidden_ip_addresses"]):
            raise ValidationError(
                {"egress.forbidden_ip_addresses": "The platform SSRF deny-list cannot be weakened."}
            )
        try:
            for address in document["egress"]["forbidden_ip_addresses"]:
                ipaddress.ip_address(address)
        except (TypeError, ValueError) as exc:
            raise ValidationError({"egress.forbidden_ip_addresses": "Every entry must be an IP address."}) from exc
        required_host_suffixes = set(DEFAULT_CONFIGURATION["egress"]["internal_hostname_suffixes"])
        if not required_host_suffixes.issubset(document["egress"]["internal_hostname_suffixes"]):
            raise ValidationError(
                {"egress.internal_hostname_suffixes": "The platform internal-host deny-list cannot be weakened."}
            )
        if not all(
            isinstance(value, str)
            and value
            and len(value) <= 253
            and not any(character.isspace() for character in value)
            for value in document["egress"]["internal_hostname_suffixes"]
        ):
            raise ValidationError({"egress.internal_hostname_suffixes": "Every suffix must be a valid hostname suffix."})
        if not all(
            isinstance(item, (int, float)) and not isinstance(item, bool) and 0 < float(item) < 1
            for item in document["evaluation"]["latency_percentiles"]
        ):
            raise ValidationError({"evaluation.latency_percentiles": "Each percentile must be between zero and one."})

        boolean_fields = {
            "agent": (
                "user_bound_requires_active_session",
                "only_active_agents_may_execute",
            ),
            "approval": tuple(DEFAULT_CONFIGURATION["approval"]),
            "separation_of_duties": tuple(DEFAULT_CONFIGURATION["separation_of_duties"]),
            "egress": (
                "forbid_url_credentials",
                "forbid_url_query",
                "forbid_url_fragment",
            ),
            "rollout": ("enabled",),
        }
        for section, keys in boolean_fields.items():
            for key in keys:
                if not isinstance(document[section][key], bool):
                    raise ValidationError({f"{section}.{key}": "Must be a boolean."})
        for key in DEFAULT_CONFIGURATION["agent"]["identity_session_rules"]:
            if not isinstance(document["agent"]["identity_session_rules"].get(key), bool):
                raise ValidationError({f"agent.identity_session_rules.{key}": "Must be a boolean."})
        if set(document["agent"]["identity_session_rules"]) != set(
            DEFAULT_CONFIGURATION["agent"]["identity_session_rules"]
        ):
            raise ValidationError({"agent.identity_session_rules": "Fields must exactly match the schema."})

        graph = document["agent"]["execution_state_transitions"]
        states = set(DEFAULT_CONFIGURATION["agent"]["execution_state_transitions"])
        if not isinstance(graph, dict) or set(graph) != states:
            raise ValidationError({"agent.execution_state_transitions": "Every known execution state is required."})
        for state, destinations in graph.items():
            if (
                not isinstance(destinations, list)
                or len(destinations) != len(set(destinations))
                or state in destinations
                or not set(destinations).issubset(states)
            ):
                raise ValidationError(
                    {f"agent.execution_state_transitions.{state}": "Destinations must be unique known states."}
                )
        for terminal in ("completed", "failed", "terminated", "timed_out"):
            if graph[terminal]:
                raise ValidationError(
                    {f"agent.execution_state_transitions.{terminal}": "Terminal states cannot have outgoing transitions."}
                )

        expected_status_tokens = DEFAULT_CONFIGURATION["ui"]["status_tokens"]
        if (
            not isinstance(document["ui"]["status_tokens"], dict)
            or set(document["ui"]["status_tokens"]) != set(expected_status_tokens)
            or document["ui"]["status_tokens"] != expected_status_tokens
        ):
            raise ValidationError({"ui.status_tokens": "Only the semantic design-system tokens are allowed."})
        status_map = document["ui"]["status_token_by_state"]
        if not isinstance(status_map, dict) or not status_map:
            raise ValidationError({"ui.status_token_by_state": "At least one status mapping is required."})
        if not all(
            isinstance(state, str)
            and state
            and len(state) <= 64
            and category in expected_status_tokens
            for state, category in status_map.items()
        ):
            raise ValidationError({"ui.status_token_by_state": "Every state must map to a semantic token category."})
        expected_navigation = DEFAULT_CONFIGURATION["ui"]["navigation_order"]
        if set(document["ui"]["navigation_order"]) != set(expected_navigation):
            raise ValidationError({"ui.navigation_order": "Every module navigation item is required."})
        for field in ("roles", "cohorts"):
            if not all(isinstance(item, str) and 0 < len(item.strip()) <= 100 for item in document["rollout"][field]):
                raise ValidationError({f"rollout.{field}": "Entries must be nonblank strings of at most 100 characters."})
        return document

    @classmethod
    def defaults(cls) -> dict[str, Any]:
        return deepcopy(DEFAULT_CONFIGURATION)

    @classmethod
    def resolve(cls, tenant_id: UUID, environment: str = "production") -> dict[str, Any]:
        record = AgentManagementConfiguration.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"),
            environment=cls._environment(environment),
        ).first()
        return cls.defaults() if record is None else cls.validate_document(record.document)

    @classmethod
    def current(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        environment: str = "production",
    ) -> AgentManagementConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        actor = _actor(actor_id)
        correlation = cls._correlation(correlation_id)
        env = cls._environment(environment)
        with transaction.atomic():
            record = AgentManagementConfiguration.objects.select_for_update().filter(
                tenant_id=tenant, environment=env
            ).first()
            if record is not None:
                return record
            document = cls.validate_document(cls.defaults())
            record = AgentManagementConfiguration.objects.create(
                tenant_id=tenant, environment=env, version=1, document=document
            )
            AgentManagementConfigurationVersion.objects.create(
                tenant_id=tenant,
                environment=env,
                version=1,
                previous_document={},
                document=document,
                changed_by=actor,
                correlation_id=correlation,
                change_type="bootstrap",
            )
            return record

    @classmethod
    def preview(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        document: Mapping[str, Any],
        *,
        environment: str = "production",
        expected_version: int,
    ) -> dict[str, Any]:
        """Validate a proposed document and return a non-mutating field diff."""

        current = cls.current(tenant_id, actor_id, correlation_id, environment)
        if current.version != expected_version:
            raise ValidationError({"expected_version": "Configuration changed; reload before previewing."})
        validated = cls.validate_document(document)
        changes: list[dict[str, Any]] = []

        def compare(path: str, before: Any, after: Any) -> None:
            if isinstance(before, Mapping) and isinstance(after, Mapping):
                for key in sorted(set(before) | set(after)):
                    compare(f"{path}.{key}" if path else key, before.get(key), after.get(key))
            elif before != after:
                changes.append({"path": path, "before": deepcopy(before), "after": deepcopy(after)})

        compare("", current.document, validated)
        return {
            "valid": True,
            "changed": bool(changes),
            "current_version": current.version,
            "proposed_version": current.version + 1 if changes else current.version,
            "changes": changes,
        }

    @classmethod
    @transaction.atomic
    def replace(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        document: Mapping[str, Any],
        *,
        environment: str = "production",
        change_type: str = "update",
        expected_version: int | None = None,
    ) -> AgentManagementConfiguration:
        current = cls.current(tenant_id, actor_id, correlation_id, environment)
        current = AgentManagementConfiguration.objects.select_for_update().get(
            tenant_id=current.tenant_id, environment=current.environment
        )
        if expected_version is not None and current.version != expected_version:
            raise ValidationError({"expected_version": "Configuration changed; reload before saving."})
        validated = cls.validate_document(document)
        if validated == current.document:
            return current
        previous = deepcopy(current.document)
        current.version += 1
        current.document = validated
        current.save(update_fields=("version", "document", "updated_at"))
        AgentManagementConfigurationVersion.objects.create(
            tenant_id=current.tenant_id,
            environment=current.environment,
            version=current.version,
            previous_document=previous,
            document=validated,
            changed_by=_actor(actor_id),
            correlation_id=cls._correlation(correlation_id),
            change_type=change_type,
        )
        return current

    @classmethod
    def import_document(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        value: Mapping[str, Any],
    ) -> AgentManagementConfiguration:
        envelope = _mapping(value, "document")
        if envelope.get("schema") != "saraise.ai-agent-management.configuration/v1":
            raise ValidationError({"schema": "Unsupported configuration document schema."})
        return cls.replace(
            tenant_id,
            actor_id,
            correlation_id,
            _mapping(envelope.get("configuration"), "configuration"),
            environment=str(envelope.get("environment", "production")),
            change_type="import",
            expected_version=envelope.get("expected_version"),
        )

    @classmethod
    def export_document(
        cls, tenant_id: UUID, actor_id: UUID, correlation_id: UUID, environment: str = "production"
    ) -> dict[str, Any]:
        current = cls.current(tenant_id, actor_id, correlation_id, environment)
        return {
            "schema": "saraise.ai-agent-management.configuration/v1",
            "environment": current.environment,
            "version": current.version,
            "configuration": deepcopy(current.document),
        }

    @classmethod
    @transaction.atomic
    def rollback(
        cls,
        tenant_id: UUID,
        actor_id: UUID,
        correlation_id: UUID,
        target_version: int,
        environment: str = "production",
    ) -> AgentManagementConfiguration:
        tenant = _uuid(tenant_id, "tenant_id")
        env = cls._environment(environment)
        target = AgentManagementConfigurationVersion.objects.get(
            tenant_id=tenant, environment=env, version=target_version
        )
        return cls.replace(
            tenant,
            actor_id,
            correlation_id,
            target.document,
            environment=env,
            change_type="rollback",
        )

    @staticmethod
    def versions(tenant_id: UUID, environment: str = "production") -> QuerySet[AgentManagementConfigurationVersion]:
        return AgentManagementConfigurationVersion.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id"),
            environment=ConfigurationService._environment(environment),
        ).order_by("-version", "id")


class SessionValidator(Protocol):
    def is_active(self, tenant_id: UUID, subject_id: UUID, session_id: UUID) -> bool: ...


class DatabaseSessionValidator:
    """Validate worker-time session freshness against Django session storage."""

    def is_active(self, tenant_id: UUID, subject_id: UUID, session_id: UUID) -> bool:
        del tenant_id
        session = Session.objects.filter(session_key=str(session_id), expire_date__gt=timezone.now()).first()
        if session is None:
            return False
        try:
            decoded = session.get_decoded()
        except Exception:
            return False
        return str(decoded.get("_auth_user_id", "")) == str(subject_id)


session_validator: SessionValidator = DatabaseSessionValidator()


def configure_session_validator(validator: SessionValidator) -> None:
    global session_validator
    session_validator = validator


def _uuid(value: UUID | str, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({name: "Must be a valid UUID."}) from exc


def _mapping(value: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValidationError({name: "Must be an object."})
    return dict(value)


def _safe_metadata(value: Mapping[str, Any] | None, tenant_id: UUID | None = None) -> dict[str, Any]:
    """Retain identifiers and control evidence, never free-form content."""

    if not value:
        return {}
    allowed = set(
        ConfigurationService.resolve(tenant_id)["agent"]["metadata_fields"]
        if tenant_id is not None
        else DEFAULT_CONFIGURATION["agent"]["metadata_fields"]
    )
    return {key: item for key, item in value.items() if key in allowed and isinstance(item, (str, int, bool))}


def _correlation_uuid(fallback: UUID | str | None = None) -> UUID:
    value = get_correlation_id()
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        if fallback is not None:
            return _uuid(fallback, "correlation_id")
        raise ValidationError({"correlation_id": "A valid propagated correlation_id is required."}) from exc


def _actor(value: UUID | str) -> UUID:
    return _uuid(value, "actor_id")


def _transition(
    machine: StateMachine[Any],
    aggregate: Any,
    command: str,
    tenant_id: UUID,
    transition_key: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Any:
    configuration = ConfigurationService.resolve(tenant_id)
    maximum = int(configuration["agent"]["transition_key_maximum_length"])
    if not transition_key or len(transition_key) > maximum:
        raise ValidationError({"transition_key": f"A transition key of at most {maximum} characters is required."})
    if type(aggregate) is AgentExecution:
        current = str(getattr(aggregate, machine.state_field))
        edge = next(
            (candidate for candidate in machine.transitions if candidate.command == command and candidate.source == current),
            None,
        )
        graph = configuration["agent"]["execution_state_transitions"]
        if edge is not None and edge.target not in graph.get(current, []):
            raise IllegalTransitionError(f"Tenant configuration forbids {current!r} to {edge.target!r}")
    return machine.apply(
        aggregate,
        command,
        tenant_id=tenant_id,
        transition_key=transition_key,
        metadata=_safe_metadata(metadata, tenant_id),
    )


def _transition_with_updates(
    machine: StateMachine[Any],
    aggregate: Any,
    command: str,
    tenant_id: UUID,
    transition_key: str,
    updates: Mapping[str, Any],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Any:
    """Persist a lifecycle edge and its terminal invariants in one write.

    Several aggregates have database checks tying a terminal state to evidence
    fields.  Saving the state and those fields separately is both invalid and
    observably racy, so this adapter performs the state-machine decision under
    a row lock and writes the complete edge atomically.
    """

    configuration = ConfigurationService.resolve(tenant_id)
    maximum = int(configuration["agent"]["transition_key_maximum_length"])
    if not transition_key or len(transition_key) > maximum:
        raise ValidationError({"transition_key": f"A transition key of at most {maximum} characters is required."})
    model = type(aggregate)
    locked = model._base_manager.select_for_update().get(pk=aggregate.pk, tenant_id=tenant_id)
    history = list(getattr(locked, "transition_history", []))
    existing = next((item for item in history if item.get("transition_key") == transition_key), None)
    if existing:
        if existing.get("command") != command:
            raise IdempotencyConflictError(f"Transition key {transition_key!r} already belongs to another command")
        return locked
    state_field = machine.state_field
    current = str(getattr(locked, state_field))
    if current in machine.terminal_states:
        raise TerminalStateError(f"{model._meta.label} {locked.pk} is immutable in terminal state {current!r}")
    edge = next((candidate for candidate in machine.transitions if candidate.command == command and candidate.source == current), None)
    if edge is None:
        raise IllegalTransitionError(f"Command {command!r} cannot transition {model._meta.label} from {current!r}")
    now = timezone.now()
    setattr(locked, state_field, edge.target)
    for field, value in updates.items():
        setattr(locked, field, value)
    history.append(
        {
            "transition_key": transition_key,
            "command": command,
            "from_state": current,
            "to_state": edge.target,
            "occurred_at": now.isoformat(),
            "metadata": _safe_metadata(metadata, tenant_id),
        }
    )
    locked.transition_history = history
    locked.save(update_fields=sorted({state_field, "transition_history", "updated_at", *updates.keys()}))
    return locked


AGENT_MACHINE = StateMachine(
    name="ai_agent_management.agent",
    model=Agent,
    states=("draft", "active", "disabled", "retired"),
    transitions=(
        Transition("activate", "draft", "active"),
        Transition("activate", "disabled", "active"),
        Transition("disable", "active", "disabled"),
        Transition("retire", "draft", "retired"),
        Transition("retire", "active", "retired"),
        Transition("retire", "disabled", "retired"),
    ),
    terminal_states=("retired",),
)

EXECUTION_MACHINE = StateMachine(
    name="ai_agent_management.execution",
    model=AgentExecution,
    state_field="state",
    states=("created", "validated", "queued", "running", "paused", "completed", "failed", "terminated", "timed_out"),
    transitions=(
        Transition("validate", "created", "validated"),
        Transition("enqueue", "validated", "queued"),
        Transition("start", "queued", "running"),
        Transition("pause", "running", "paused"),
        Transition("resume", "paused", "running"),
        Transition("complete", "running", "completed"),
        *(Transition("fail", source, "failed") for source in ("created", "validated", "queued", "running", "paused")),
        *(Transition("terminate", source, "terminated") for source in ("created", "validated", "queued", "running", "paused")),
        *(Transition("timeout", source, "timed_out") for source in ("queued", "running", "paused")),
    ),
    terminal_states=("completed", "failed", "terminated", "timed_out"),
)

SCHEDULE_MACHINE = StateMachine(
    name="ai_agent_management.schedule",
    model=AgentSchedulerTask,
    states=("pending", "queued", "running", "completed", "failed", "cancelled"),
    transitions=(
        Transition("enqueue", "pending", "queued"),
        Transition("start", "queued", "running"),
        Transition("complete", "running", "completed"),
        Transition("retry", "running", "pending"),
        *(Transition("fail", source, "failed") for source in ("pending", "queued", "running")),
        *(Transition("cancel", source, "cancelled") for source in ("pending", "queued")),
    ),
    terminal_states=("completed", "failed", "cancelled"),
)

APPROVAL_MACHINE = StateMachine(
    name="ai_agent_management.approval",
    model=ApprovalRequest,
    states=("pending", "approved", "rejected", "expired", "cancelled"),
    transitions=(
        Transition("approve", "pending", "approved"),
        Transition("reject", "pending", "rejected"),
        Transition("expire", "pending", "expired"),
        Transition("cancel", "pending", "cancelled"),
    ),
    terminal_states=("approved", "rejected", "expired", "cancelled"),
)

KILL_SWITCH_MACHINE = StateMachine(
    name="ai_agent_management.kill_switch",
    model=KillSwitch,
    states=("active", "inactive"),
    transitions=(Transition("deactivate", "active", "inactive"),),
    terminal_states=("inactive",),
)


class AgentService:
    @staticmethod
    @transaction.atomic
    def create_agent(tenant_id: UUID, actor_id: UUID, command: Mapping[str, Any]) -> Agent:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        identity_policy = ConfigurationService.resolve(tenant)["agent"]["identity_session_rules"]
        values = _mapping(command, "command")
        values.pop("tenant_id", None)
        values.pop("created_by", None)
        values.pop("status", None)
        values.pop("transition_history", None)
        identity = values.get("identity_type")
        session_id = values.get("session_id")
        if identity_policy["user_bound_requires_session"] and identity == "user_bound" and not session_id:
            raise ValidationError({"session_id": "User-bound agents require a session."})
        if identity_policy["system_bound_forbids_session"] and identity == "system_bound" and session_id:
            raise ValidationError({"session_id": "System-bound agents cannot carry a user session."})
        runner_key = str(values.get("runner_key", "")).strip()
        if not runner_key:
            raise ValidationError({"runner_key": "A runner key is required."})
        agent = Agent(tenant_id=tenant, created_by=actor, status="draft", transition_history=[], **values)
        agent.full_clean()
        agent.save()
        return agent

    @staticmethod
    @transaction.atomic
    def update_agent(tenant_id: UUID, actor_id: UUID, agent_id: UUID, changes: Mapping[str, Any]) -> Agent:
        del actor_id
        agent = AgentService.get_agent(tenant_id, agent_id, for_update=True)
        if agent.status == "retired":
            raise AgentServiceError("AGENT_RETIRED", "Retired agents are immutable.")
        protected = {"tenant_id", "created_by", "status", "transition_history", "deleted_at"}
        for field, value in _mapping(changes, "changes").items():
            if field in protected:
                raise ValidationError({field: "This field is server controlled."})
            setattr(agent, field, value)
        agent.full_clean()
        agent.save()
        return agent

    @staticmethod
    def get_agent(tenant_id: UUID, agent_id: UUID, *, for_update: bool = False) -> Agent:
        query = Agent.objects.select_for_update() if for_update else Agent.objects
        return query.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(agent_id, "agent_id"))

    @staticmethod
    def list_agents(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[Agent]:
        tenant = _uuid(tenant_id, "tenant_id")
        configuration = ConfigurationService.resolve(tenant)["agent"]
        query = Agent.objects.filter(tenant_id=tenant, deleted_at__isnull=True)
        values = _mapping(filters, "filters")
        for key in ("status", "identity_type", "runner_key", "subject_id"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        raw_search = values.get("search")
        search = (
            ""
            if raw_search in (None, "")
            else str(raw_search).strip()[: int(configuration["search_maximum_length"])]
        )
        if search:
            query = query.filter(Q(name__icontains=search) | Q(description__icontains=search))
        ordering = str(values.get("ordering", "name"))
        if ordering not in set(configuration["ordering_fields"]):
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return query.order_by(ordering, "id")

    @staticmethod
    @transaction.atomic
    def activate_agent(tenant_id: UUID, actor_id: UUID, agent_id: UUID, transition_key: str) -> Agent:
        agent = AgentService.get_agent(tenant_id, agent_id)
        if runner_registry.get(agent.runner_key) is None:
            raise AgentServiceError("RUNNER_UNAVAILABLE", "The configured runner is unavailable.")
        if agent.identity_type == "user_bound" and (
            not agent.session_id or not session_validator.is_active(agent.tenant_id, agent.subject_id, agent.session_id)
        ):
            raise AgentServiceError("SESSION_STALE", "The bound user session is no longer active.")
        result = KillSwitchService.check(agent.tenant_id, agent_id=agent.id)
        if result.status != "succeeded":
            raise AgentServiceError(result.error_code or "KILL_SWITCH_ACTIVE", result.message or "Execution is disabled.")
        del actor_id
        return _transition(AGENT_MACHINE, agent, "activate", agent.tenant_id, transition_key)

    @staticmethod
    @transaction.atomic
    def disable_agent(tenant_id: UUID, actor_id: UUID, agent_id: UUID, reason: str, transition_key: str) -> Agent:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        maximum = int(ConfigurationService.resolve(tenant)["agent"]["transition_reason_maximum_length"])
        return _transition(AGENT_MACHINE, AgentService.get_agent(tenant, agent_id), "disable", tenant, transition_key, metadata={"reason_code": reason[:maximum]})

    @staticmethod
    @transaction.atomic
    def retire_agent(tenant_id: UUID, actor_id: UUID, agent_id: UUID, reason: str, transition_key: str) -> Agent:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        maximum = int(ConfigurationService.resolve(tenant)["agent"]["transition_reason_maximum_length"])
        return _transition_with_updates(
            AGENT_MACHINE,
            AgentService.get_agent(tenant, agent_id),
            "retire",
            tenant,
            transition_key,
            {"deleted_at": timezone.now()},
            metadata={"reason_code": reason[:maximum]},
        )


class ExecutionService:
    @staticmethod
    @transaction.atomic
    def execute(
        tenant_id: UUID,
        actor_id: UUID,
        agent_id: UUID,
        task: Mapping[str, Any],
        idempotency_key: str,
        schedule_at: datetime | None = None,
    ) -> OperationResult[AgentExecution]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        configuration = ConfigurationService.resolve(tenant)
        maximum = int(configuration["agent"]["execution_idempotency_key_maximum_length"])
        if not idempotency_key or len(idempotency_key) > maximum:
            raise ValidationError({"idempotency_key": f"A key of at most {maximum} characters is required."})
        prior = AgentExecution.objects.filter(tenant_id=tenant, idempotency_key=idempotency_key).first()
        if prior is not None:
            return OperationResult.succeeded(prior, evidence={"execution_id": str(prior.id), "duplicate": True})
        agent = AgentService.get_agent(tenant, agent_id)
        if configuration["agent"]["only_active_agents_may_execute"] and agent.status != "active":
            return OperationResult.failed(code="AGENT_NOT_ACTIVE", message="The agent is not active.", http_status=409)
        killed = KillSwitchService.check(tenant, agent_id=agent.id)
        if killed.status != "succeeded":
            return OperationResult.failed(code=killed.error_code or "KILL_SWITCH_ACTIVE", message=killed.message or "Execution is disabled.", http_status=409)
        if runner_registry.get(agent.runner_key) is None:
            return OperationResult.unavailable(capability=f"runner:{agent.runner_key}", message="The configured runner is unavailable.")
        if configuration["agent"]["user_bound_requires_active_session"] and agent.identity_type == "user_bound" and (
            not agent.session_id or not session_validator.is_active(tenant, agent.subject_id, agent.session_id)
        ):
            return OperationResult.failed(code="SESSION_STALE", message="The bound user session is no longer active.", http_status=409)
        if schedule_at is not None:
            schedule = ScheduleService.create_schedule(
                tenant,
                actor,
                agent.id,
                {"scheduled_at": schedule_at, "task_data": dict(task), "idempotency_key": idempotency_key},
            )
            return OperationResult.succeeded(
                schedule.execution,
                evidence={"execution_id": str(schedule.execution_id), "schedule_id": str(schedule.id)},
            )
        execution_id = uuid4()
        job = enqueue(
            tenant,
            actor,
            EXECUTE_COMMAND,
            {"execution_id": str(execution_id), "agent_id": str(agent.id)},
            f"ai-execution:{idempotency_key}",
        )
        execution = AgentExecution.objects.create(
            id=execution_id,
            tenant_id=tenant,
            agent=agent,
            state="created",
            transition_history=[],
            initiating_actor_id=actor,
            session_id=agent.session_id,
            task_definition=dict(task),
            input_metadata={},
            idempotency_key=idempotency_key,
            provider_config_id=agent.provider_config_id,
            async_job_id=job.id,
        )
        execution = _transition(EXECUTION_MACHINE, execution, "validate", tenant, f"{idempotency_key}:validate")
        execution = _transition(EXECUTION_MACHINE, execution, "enqueue", tenant, f"{idempotency_key}:enqueue")
        return OperationResult.succeeded(
            execution,
            evidence={"execution_id": str(execution.id), "async_job_id": str(job.id)},
        )

    @staticmethod
    def get_execution(tenant_id: UUID, execution_id: UUID) -> AgentExecution:
        return AgentExecution.objects.select_related("agent").get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(execution_id, "execution_id"))

    @staticmethod
    def list_executions(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[AgentExecution]:
        query = AgentExecution.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("agent")
        values = _mapping(filters, "filters")
        aliases = {"agent_id": "agent_id", "state": "state", "actor_id": "initiating_actor_id"}
        for source, target in aliases.items():
            if values.get(source) not in (None, ""):
                query = query.filter(**{target: values[source]})
        if values.get("created_after"):
            query = query.filter(created_at__gte=values["created_after"])
        if values.get("created_before"):
            query = query.filter(created_at__lte=values["created_before"])
        ordering = str(values.get("ordering", "-created_at"))
        if ordering.lstrip("-") not in {"created_at", "started_at", "completed_at"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return query.order_by(ordering, "id")

    @staticmethod
    def _owned(tenant_id: UUID, agent_id: UUID, execution_id: UUID) -> AgentExecution:
        return AgentExecution.objects.select_related("agent").get(
            tenant_id=_uuid(tenant_id, "tenant_id"),
            agent_id=_uuid(agent_id, "agent_id"),
            id=_uuid(execution_id, "execution_id"),
        )

    @classmethod
    @transaction.atomic
    def pause(cls, tenant_id: UUID, actor_id: UUID, agent_id: UUID, execution_id: UUID, transition_key: str) -> AgentExecution:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        return _transition(EXECUTION_MACHINE, cls._owned(tenant, agent_id, execution_id), "pause", tenant, transition_key)

    @classmethod
    @transaction.atomic
    def resume(cls, tenant_id: UUID, actor_id: UUID, agent_id: UUID, execution_id: UUID, transition_key: str) -> AgentExecution:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        execution = cls._owned(tenant, agent_id, execution_id)
        if execution.session_id and not session_validator.is_active(tenant, execution.agent.subject_id, execution.session_id):
            raise AgentServiceError("SESSION_STALE", "The bound user session is no longer active.")
        return _transition(EXECUTION_MACHINE, execution, "resume", tenant, transition_key)

    @classmethod
    @transaction.atomic
    def terminate(cls, tenant_id: UUID, actor_id: UUID, agent_id: UUID, execution_id: UUID, reason: str, transition_key: str) -> AgentExecution:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        maximum = int(ConfigurationService.resolve(tenant)["agent"]["transition_reason_maximum_length"])
        return _transition_with_updates(
            EXECUTION_MACHINE, cls._owned(tenant, agent_id, execution_id), "terminate", tenant,
            transition_key, {"completed_at": timezone.now()}, metadata={"reason_code": reason[:maximum]},
        )

    @staticmethod
    @transaction.atomic
    def complete(tenant_id: UUID, execution_id: UUID, result: Mapping[str, Any], evidence: Mapping[str, Any], transition_key: str) -> AgentExecution:
        tenant = _uuid(tenant_id, "tenant_id")
        execution = ExecutionService.get_execution(tenant, execution_id)
        return _transition_with_updates(
            EXECUTION_MACHINE, execution, "complete", tenant, transition_key,
            {"result": dict(result), "completed_at": timezone.now()}, metadata=evidence,
        )

    @staticmethod
    @transaction.atomic
    def fail(tenant_id: UUID, execution_id: UUID, error_code: str, safe_message: str, transition_key: str) -> AgentExecution:
        tenant = _uuid(tenant_id, "tenant_id")
        maximum = int(ConfigurationService.resolve(tenant)["agent"]["error_code_maximum_length"])
        return _transition_with_updates(
            EXECUTION_MACHINE, ExecutionService.get_execution(tenant, execution_id), "fail", tenant,
            transition_key,
            {"error_code": error_code[:maximum], "error_message": safe_message, "completed_at": timezone.now()},
            metadata={"reason_code": error_code},
        )


class ScheduleService:
    @staticmethod
    @transaction.atomic
    def create_schedule(tenant_id: UUID, actor_id: UUID, agent_id: UUID, command: Mapping[str, Any]) -> AgentSchedulerTask:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        schedule_configuration = ConfigurationService.resolve(tenant)["schedule"]
        values = _mapping(command, "command")
        key = str(values.get("idempotency_key", "")).strip()
        if not key:
            raise ValidationError({"idempotency_key": "This field is required."})
        prior = AgentSchedulerTask.objects.filter(tenant_id=tenant, idempotency_key=key).first()
        if prior:
            return prior
        agent = AgentService.get_agent(tenant, agent_id)
        scheduled_at = values.get("scheduled_at")
        if not isinstance(scheduled_at, datetime):
            raise ValidationError({"scheduled_at": "A valid datetime is required."})
        priority = int(values.get("priority", schedule_configuration["default_priority"]))
        maximum_retries = int(
            values.get("max_retries", schedule_configuration["default_maximum_retries"])
        )
        if not int(schedule_configuration["priority_minimum"]) <= priority <= int(
            schedule_configuration["priority_maximum"]
        ):
            raise ValidationError({"priority": "Outside the configured safe priority range."})
        if not 0 <= maximum_retries <= int(schedule_configuration["maximum_retries_limit"]):
            raise ValidationError({"max_retries": "Outside the configured safe retry range."})
        execution_id, schedule_id = uuid4(), uuid4()
        job = enqueue(tenant, actor, SCHEDULE_COMMAND, {"schedule_id": str(schedule_id)}, f"ai-schedule:{key}")
        execution = AgentExecution.objects.create(
            id=execution_id,
            tenant_id=tenant,
            agent=agent,
            initiating_actor_id=actor,
            session_id=agent.session_id,
            task_definition=_mapping(values.get("task_data"), "task_data"),
            input_metadata={},
            idempotency_key=f"schedule:{key}",
            provider_config_id=agent.provider_config_id,
            transition_history=[],
            async_job_id=job.id,
        )
        schedule = AgentSchedulerTask.objects.create(
            id=schedule_id,
            tenant_id=tenant,
            agent=agent,
            execution=execution,
            scheduled_at=scheduled_at,
            priority=priority,
            max_retries=maximum_retries,
            task_data=_mapping(values.get("task_data"), "task_data"),
            created_by=actor,
            idempotency_key=key,
            transition_history=[],
            async_job_id=job.id,
        )
        return schedule

    @staticmethod
    def get_schedule(tenant_id: UUID, task_id: UUID) -> AgentSchedulerTask:
        return AgentSchedulerTask.objects.select_related("agent", "execution").get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(task_id, "task_id"))

    @staticmethod
    def list_schedules(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[AgentSchedulerTask]:
        query = AgentSchedulerTask.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("agent", "execution")
        values = _mapping(filters, "filters")
        for key in ("agent_id", "status"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        if values.get("scheduled_after"):
            query = query.filter(scheduled_at__gte=values["scheduled_after"])
        if values.get("scheduled_before"):
            query = query.filter(scheduled_at__lte=values["scheduled_before"])
        ordering = str(values.get("ordering", "scheduled_at"))
        if ordering.lstrip("-") not in {"priority", "scheduled_at"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return query.order_by(ordering, "id")

    @staticmethod
    @transaction.atomic
    def cancel_schedule(tenant_id: UUID, actor_id: UUID, task_id: UUID, transition_key: str) -> AgentSchedulerTask:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        return _transition(SCHEDULE_MACHINE, ScheduleService.get_schedule(tenant, task_id), "cancel", tenant, transition_key)

    @staticmethod
    @transaction.atomic
    def dispatch_due(tenant_id: UUID, now: datetime, limit: int) -> int:
        tenant = _uuid(tenant_id, "tenant_id")
        limits = ConfigurationService.resolve(tenant)["schedule"]
        minimum, maximum = int(limits["dispatch_batch_minimum"]), int(limits["dispatch_batch_maximum"])
        if limit < minimum or limit > maximum:
            raise ValidationError({"limit": f"Must be between {minimum} and {maximum}."})
        rows = list(AgentSchedulerTask.objects.select_for_update(skip_locked=True).filter(tenant_id=tenant, status="pending", scheduled_at__lte=now).order_by("-priority", "scheduled_at", "id")[:limit])
        for row in rows:
            _transition(SCHEDULE_MACHINE, row, "enqueue", tenant, f"dispatch:{row.id}")
        return len(rows)

    @staticmethod
    @transaction.atomic
    def recover_stale(tenant_id: UUID, stale_before: datetime) -> int:
        tenant = _uuid(tenant_id, "tenant_id")
        rows = list(AgentSchedulerTask.objects.select_for_update(skip_locked=True).filter(tenant_id=tenant, status="running", updated_at__lt=stale_before))
        recovered = 0
        for row in rows:
            if row.retry_count < row.max_retries:
                row.retry_count += 1
                row.save(update_fields=("retry_count", "updated_at"))
                _transition(SCHEDULE_MACHINE, row, "retry", tenant, f"recover:{row.id}:{row.retry_count}")
                recovered += 1
            else:
                _transition(SCHEDULE_MACHINE, row, "fail", tenant, f"exhaust:{row.id}")
        return recovered


class ApprovalService:
    @staticmethod
    def requires_approval(tenant_id: UUID, actor_id: UUID, tool_id: UUID, input_data: Mapping[str, Any]) -> bool:
        del actor_id, input_data
        tool = ToolService.get_tool(tenant_id, tool_id)
        policy = ConfigurationService.resolve(tenant_id)["approval"]
        return bool(policy["require_for_non_read_only_tools"] and tool.side_effect_class != "read_only")

    @staticmethod
    @transaction.atomic
    def create_request(tenant_id: UUID, actor_id: UUID, execution_id: UUID, invocation_id: UUID | None, command: Mapping[str, Any]) -> ApprovalRequest:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        values = _mapping(command, "command")
        execution = ExecutionService.get_execution(tenant, execution_id)
        tool = ToolService.get_tool(tenant, _uuid(values["tool_id"], "tool_id"))
        invocation = None
        if invocation_id:
            invocation = ToolInvocation.objects.get(tenant_id=tenant, id=_uuid(invocation_id, "invocation_id"), tool=tool)
        approval = ApprovalRequest(
            tenant_id=tenant,
            tool=tool,
            agent_execution=execution,
            tool_invocation=invocation,
            requested_by=actor,
            requested_for=_uuid(values.get("requested_for", execution.initiating_actor_id), "requested_for"),
            tool_input=_mapping(values.get("tool_input"), "tool_input"),
            justification=str(values.get("justification", "")),
            expires_at=values.get("expires_at"),
            metadata={},
            transition_history=[],
        )
        approval.full_clean()
        approval.save()
        return approval

    @staticmethod
    def get_request(tenant_id: UUID, approval_id: UUID) -> ApprovalRequest:
        return ApprovalRequest.objects.select_related("tool", "agent_execution", "tool_invocation").get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(approval_id, "approval_id"))

    @staticmethod
    def list_requests(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[ApprovalRequest]:
        query = ApprovalRequest.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id")).select_related("tool", "agent_execution")
        values = _mapping(filters, "filters")
        aliases = {"status": "status", "tool_id": "tool_id", "execution_id": "agent_execution_id", "approver_id": "approver_id"}
        for source, target in aliases.items():
            if values.get(source) not in (None, ""):
                query = query.filter(**{target: values[source]})
        if values.get("expires_after"):
            query = query.filter(expires_at__gte=values["expires_after"])
        if values.get("expires_before"):
            query = query.filter(expires_at__lte=values["expires_before"])
        return query.order_by("-requested_at", "id")

    @staticmethod
    @transaction.atomic
    def _decide(tenant_id: UUID, approver_id: UUID, approval_id: UUID, command: str, transition_key: str, reason: str = "") -> ApprovalRequest:
        tenant, approver = _uuid(tenant_id, "tenant_id"), _actor(approver_id)
        policy = ConfigurationService.resolve(tenant)["approval"]
        approval = ApprovalService.get_request(tenant, approval_id)
        if not policy["requester_may_approve_own_request"] and approval.requested_by == approver:
            raise AgentServiceError("SELF_APPROVAL_FORBIDDEN", "Requestors cannot decide their own approval.")
        if policy["enforce_expiry"] and approval.expires_at and approval.expires_at <= timezone.now():
            _transition_with_updates(
                APPROVAL_MACHINE, approval, "expire", tenant, f"expire:{approval.id}",
                {"approver_id": approver, "decided_at": timezone.now()},
            )
            raise AgentServiceError("APPROVAL_EXPIRED", "The approval request has expired.")
        sod = SoDService.evaluate(tenant, approver, f"approval:{command}", approval.agent_execution_id)
        if sod.status != "succeeded":
            raise AgentServiceError(sod.error_code or "SOD_VIOLATION", sod.message or "Segregation of duties denied this decision.")
        updates: dict[str, Any] = {"approver_id": approver, "decided_at": timezone.now()}
        if command == "reject":
            if policy["rejection_requires_reason"] and not reason.strip():
                raise ValidationError({"reason": "A rejection reason is required."})
            updates["rejection_reason"] = reason
        return _transition_with_updates(APPROVAL_MACHINE, approval, command, tenant, transition_key, updates)

    @classmethod
    def approve(cls, tenant_id: UUID, approver_id: UUID, approval_id: UUID, transition_key: str) -> ApprovalRequest:
        return cls._decide(tenant_id, approver_id, approval_id, "approve", transition_key)

    @classmethod
    def reject(cls, tenant_id: UUID, approver_id: UUID, approval_id: UUID, reason: str, transition_key: str) -> ApprovalRequest:
        return cls._decide(tenant_id, approver_id, approval_id, "reject", transition_key, reason)

    @staticmethod
    @transaction.atomic
    def cancel(tenant_id: UUID, actor_id: UUID, approval_id: UUID, transition_key: str) -> ApprovalRequest:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        approval = ApprovalService.get_request(tenant, approval_id)
        if ConfigurationService.resolve(tenant)["approval"]["only_requester_may_cancel"] and approval.requested_by != actor:
            raise AgentServiceError("APPROVAL_CANCEL_FORBIDDEN", "Only the requestor may cancel this approval.")
        return _transition_with_updates(
            APPROVAL_MACHINE, approval, "cancel", tenant, transition_key, {"decided_at": timezone.now()}
        )

    @staticmethod
    @transaction.atomic
    def expire_pending(tenant_id: UUID, now: datetime) -> int:
        tenant = _uuid(tenant_id, "tenant_id")
        rows = list(ApprovalRequest.objects.select_for_update(skip_locked=True).filter(tenant_id=tenant, status="pending", expires_at__lte=now))
        for row in rows:
            _transition_with_updates(
                APPROVAL_MACHINE, row, "expire", tenant, f"expire:{row.id}",
                {"approver_id": row.requested_for, "decided_at": now},
            )
        return len(rows)


class SoDService:
    @staticmethod
    @transaction.atomic
    def create_policy(tenant_id: UUID, actor_id: UUID, command: Mapping[str, Any]) -> SoDPolicy:
        tenant = _uuid(tenant_id, "tenant_id")
        sod_configuration = ConfigurationService.resolve(tenant)["separation_of_duties"]
        values = _mapping(command, "command")
        action_1, action_2 = sorted((str(values["action_1"]).strip(), str(values["action_2"]).strip()))
        if sod_configuration["actions_must_be_nonempty_and_different"] and (
            not action_1 or action_1 == action_2
        ):
            raise ValidationError({"action_2": "Actions must be non-empty and different."})
        return SoDPolicy.objects.create(tenant_id=tenant, created_by=_actor(actor_id), action_1=action_1, action_2=action_2, name=values["name"], description=values.get("description", ""))

    @staticmethod
    @transaction.atomic
    def update_policy(tenant_id: UUID, actor_id: UUID, policy_id: UUID, changes: Mapping[str, Any]) -> SoDPolicy:
        del actor_id
        policy = SoDService.get_policy(tenant_id, policy_id)
        for field, value in _mapping(changes, "changes").items():
            if field not in {"name", "description", "action_1", "action_2", "is_active"}:
                raise ValidationError({field: "This field is not editable."})
            setattr(policy, field, value)
        policy.action_1, policy.action_2 = sorted((policy.action_1, policy.action_2))
        policy.full_clean()
        policy.save()
        return policy

    @staticmethod
    def get_policy(tenant_id: UUID, policy_id: UUID) -> SoDPolicy:
        return SoDPolicy.objects.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(policy_id, "policy_id"))

    @staticmethod
    def list_policies(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[SoDPolicy]:
        query = SoDPolicy.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"))
        values = _mapping(filters, "filters")
        if values.get("is_active") is not None:
            query = query.filter(is_active=values["is_active"])
        return query.order_by("name", "id")

    @staticmethod
    @transaction.atomic
    def deactivate_policy(tenant_id: UUID, actor_id: UUID, policy_id: UUID) -> SoDPolicy:
        del actor_id
        policy = SoDService.get_policy(tenant_id, policy_id)
        policy.is_active = False
        policy.save(update_fields=("is_active", "updated_at"))
        return policy

    @staticmethod
    def evaluate(tenant_id: UUID, actor_id: UUID, action: str, execution_id: UUID) -> OperationResult[None]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        if not ConfigurationService.resolve(tenant)["separation_of_duties"]["counterpart_detection_enabled"]:
            return OperationResult.succeeded(None, evidence={"policy": "counterpart_detection_disabled"})
        prior_actions = AuditEvent.objects.filter(tenant_id=tenant, agent_execution_id=execution_id, outcome="success").values_list("event_type", "initiating_principal")
        for policy in SoDPolicy.objects.filter(tenant_id=tenant, is_active=True).filter(Q(action_1=action) | Q(action_2=action)):
            counterpart = policy.action_2 if policy.action_1 == action else policy.action_1
            if any(event == counterpart and principal == actor for event, principal in prior_actions):
                return OperationResult.failed(code="SOD_VIOLATION", message="Segregation of duties denied this action.", http_status=409)
        return OperationResult.succeeded(None, evidence={"evaluated_policies": True})

    @staticmethod
    @transaction.atomic
    def record_violation(tenant_id: UUID, **values: Any) -> SoDViolation:
        values.pop("tenant_id", None)
        return SoDViolation.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), **values)


class ToolService:
    @staticmethod
    @transaction.atomic
    def register_tool(tenant_id: UUID, actor_id: UUID, command: Mapping[str, Any]) -> Tool:
        values = _mapping(command, "command")
        values.pop("tenant_id", None)
        values.pop("registered_by", None)
        ToolRegistry.validate_schema(values["input_schema"])
        ToolRegistry.validate_schema(values["output_schema"])
        tool = Tool(tenant_id=_uuid(tenant_id, "tenant_id"), registered_by=_actor(actor_id), **values)
        tool.full_clean()
        tool.save()
        return tool

    @staticmethod
    @transaction.atomic
    def update_tool(tenant_id: UUID, actor_id: UUID, tool_id: UUID, changes: Mapping[str, Any]) -> Tool:
        del actor_id
        tool = ToolService.get_tool(tenant_id, tool_id)
        for field, value in _mapping(changes, "changes").items():
            if field in {"tenant_id", "registered_by", "registered_at"}:
                raise ValidationError({field: "This field is server controlled."})
            setattr(tool, field, value)
        ToolRegistry.validate_schema(tool.input_schema)
        ToolRegistry.validate_schema(tool.output_schema)
        tool.full_clean()
        tool.save()
        return tool

    @staticmethod
    def get_tool(tenant_id: UUID, tool_id: UUID) -> Tool:
        return Tool.objects.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(tool_id, "tool_id"))

    @staticmethod
    def list_tools(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[Tool]:
        query = Tool.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"))
        values = _mapping(filters, "filters")
        for key in ("owning_module", "side_effect_class", "is_active"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        raw_search = values.get("search")
        maximum = int(ConfigurationService.resolve(_uuid(tenant_id, "tenant_id"))["agent"]["search_maximum_length"])
        search = "" if raw_search in (None, "") else str(raw_search).strip()[:maximum]
        if search:
            query = query.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return query.order_by("name", "version", "id")

    @staticmethod
    @transaction.atomic
    def deactivate_tool(tenant_id: UUID, actor_id: UUID, tool_id: UUID) -> Tool:
        del actor_id
        tool = ToolService.get_tool(tenant_id, tool_id)
        tool.is_active = False
        tool.save(update_fields=("is_active", "updated_at"))
        return tool

    @staticmethod
    def validate_input(tenant_id: UUID, tool_id: UUID, value: Any) -> None:
        ToolRegistry.validate_value(ToolService.get_tool(tenant_id, tool_id).input_schema, value)

    @staticmethod
    def validate_output(tenant_id: UUID, tool_id: UUID, value: Any) -> None:
        ToolRegistry.validate_value(ToolService.get_tool(tenant_id, tool_id).output_schema, value)

    @staticmethod
    def validation_diagnostic(
        tenant_id: UUID,
        tool_id: UUID,
        direction: str,
        value: Any,
    ) -> dict[str, Any]:
        method = ToolService.validate_input if direction == "input" else ToolService.validate_output
        method(tenant_id, tool_id, value)
        return {"valid": True, "direction": direction, "issues": ()}

    @staticmethod
    @transaction.atomic
    def invoke(tenant_id: UUID, actor_id: UUID, execution_id: UUID, tool_id: UUID, input_data: Mapping[str, Any], idempotency_key: str) -> OperationResult[ToolInvocation]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        prior = ToolInvocation.objects.filter(tenant_id=tenant, idempotency_key=idempotency_key).first()
        if prior:
            return OperationResult.succeeded(prior, evidence={"invocation_id": str(prior.id), "duplicate": True})
        execution = ExecutionService.get_execution(tenant, execution_id)
        tool = ToolService.get_tool(tenant, tool_id)
        ToolService.validate_input(tenant, tool.id, input_data)
        try:
            tool_registry.require_handler(tool.name, tool.version)
        except ToolNotRegistered:
            return OperationResult.unavailable(capability=f"tool:{tool.name}@{tool.version}", message="The tool implementation is unavailable.")
        state = "awaiting_approval" if ApprovalService.requires_approval(tenant, actor, tool.id, input_data) else "requested"
        invocation = ToolInvocation.objects.create(tenant_id=tenant, tool=tool, agent_execution=execution, status=state, transition_history=[], input_data=dict(input_data), idempotency_key=idempotency_key)
        job = enqueue(tenant, actor, INVOKE_TOOL_COMMAND, {"invocation_id": str(invocation.id)}, f"ai-tool:{idempotency_key}")
        return OperationResult.succeeded(invocation, evidence={"invocation_id": str(invocation.id), "async_job_id": str(job.id)})


class EgressService:
    @classmethod
    def _address(cls, value: str, tenant_id: UUID | None = None) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        try:
            address = ipaddress.ip_address(value.split("%", 1)[0])
        except ValueError as exc:
            raise ValidationError({"destination": "Enter a canonical IP address."}) from exc
        comparable = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
        configuration = (
            ConfigurationService.resolve(tenant_id)["egress"]
            if tenant_id is not None
            else DEFAULT_CONFIGURATION["egress"]
        )
        forbidden = {ipaddress.ip_address(item) for item in configuration["forbidden_ip_addresses"]}
        if comparable in forbidden or comparable.is_private or comparable.is_loopback or comparable.is_link_local or comparable.is_reserved or comparable.is_multicast or comparable.is_unspecified:
            raise ValidationError({"destination": "Internal, metadata, and non-routable destinations are forbidden."})
        return address

    @classmethod
    def normalize(cls, destination_type: str, destination: str, tenant_id: UUID | None = None) -> str:
        raw = destination.strip()
        configuration = (
            ConfigurationService.resolve(tenant_id)["egress"]
            if tenant_id is not None
            else DEFAULT_CONFIGURATION["egress"]
        )
        if not raw or "*" in raw:
            raise ValidationError({"destination": "A concrete destination is required; wildcards are forbidden."})
        if destination_type == "domain":
            host = raw.rstrip(".").lower().encode("idna").decode("ascii")
            if any(host == item or host.endswith(item) for item in configuration["internal_hostname_suffixes"]):
                raise ValidationError({"destination": "Internal destinations are forbidden."})
            return host
        if destination_type == "ip":
            return str(cls._address(raw, tenant_id))
        if destination_type == "cidr":
            network = ipaddress.ip_network(raw, strict=True)
            cls._address(str(network.network_address), tenant_id)
            cls._address(str(network.broadcast_address), tenant_id)
            return str(network)
        if destination_type == "url_pattern":
            parsed = urlsplit(raw)
            if (
                parsed.scheme not in set(configuration["allowed_url_schemes"])
                or not parsed.hostname
                or (configuration["forbid_url_credentials"] and (parsed.username or parsed.password))
                or (configuration["forbid_url_fragment"] and parsed.fragment)
                or (configuration["forbid_url_query"] and parsed.query)
            ):
                raise ValidationError({"destination": "Use a canonical HTTP(S) URL without credentials, query, or fragment."})
            host = cls.normalize("domain", parsed.hostname, tenant_id)
            return parsed._replace(netloc=f"{host}:{parsed.port}" if parsed.port else host).geturl()
        raise ValidationError({"destination_type": "Unsupported destination type."})

    @staticmethod
    @transaction.atomic
    def create_rule(tenant_id: UUID, actor_id: UUID, command: Mapping[str, Any]) -> EgressRule:
        tenant = _uuid(tenant_id, "tenant_id")
        values = _mapping(command, "command")
        values["destination"] = EgressService.normalize(values["destination_type"], values["destination"], tenant)
        values.pop("tenant_id", None)
        values.pop("created_by", None)
        rule = EgressRule(tenant_id=tenant, created_by=_actor(actor_id), **values)
        rule.full_clean()
        rule.save()
        return rule

    @staticmethod
    @transaction.atomic
    def update_rule(tenant_id: UUID, actor_id: UUID, rule_id: UUID, changes: Mapping[str, Any]) -> EgressRule:
        del actor_id
        rule = EgressService.get_rule(tenant_id, rule_id)
        for field, value in _mapping(changes, "changes").items():
            if field in {"tenant_id", "created_by"}:
                raise ValidationError({field: "This field is server controlled."})
            setattr(rule, field, value)
        rule.destination = EgressService.normalize(rule.destination_type, rule.destination, _uuid(tenant_id, "tenant_id"))
        rule.full_clean()
        rule.save()
        return rule

    @staticmethod
    def get_rule(tenant_id: UUID, rule_id: UUID) -> EgressRule:
        return EgressRule.objects.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(rule_id, "rule_id"))

    @staticmethod
    def list_rules(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[EgressRule]:
        query = EgressRule.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"))
        values = _mapping(filters, "filters")
        for key in ("is_active", "destination_type", "protocol"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        return query.order_by("name", "id")

    @staticmethod
    @transaction.atomic
    def deactivate_rule(tenant_id: UUID, actor_id: UUID, rule_id: UUID) -> EgressRule:
        del actor_id
        rule = EgressService.get_rule(tenant_id, rule_id)
        rule.is_active = False
        rule.save(update_fields=("is_active", "updated_at"))
        return rule

    @classmethod
    @transaction.atomic
    def evaluate(cls, tenant_id: UUID, execution_id: UUID, destination: str, port: int | None, protocol: str) -> EgressRequest:
        tenant = _uuid(tenant_id, "tenant_id")
        execution = ExecutionService.get_execution(tenant, execution_id)
        parsed = urlsplit(destination if "://" in destination else f"//{destination}")
        host = parsed.hostname or destination
        canonical = cls.normalize("domain", host, tenant)
        addresses: set[str] = set()
        try:
            for record in socket.getaddrinfo(canonical, port):
                address = str(cls._address(record[4][0], tenant))
                addresses.add(address)
        except (OSError, ValueError, ValidationError):
            addresses.clear()
        rules = EgressRule.objects.filter(tenant_id=tenant, is_active=True, protocol=protocol).filter(Q(port=port) | Q(port__isnull=True))
        matched = None
        for rule in rules:
            if rule.destination_type == "domain" and rule.destination == canonical:
                matched = rule
                break
            if rule.destination_type == "ip" and rule.destination in addresses:
                matched = rule
                break
            if rule.destination_type == "cidr" and any(ipaddress.ip_address(address) in ipaddress.ip_network(rule.destination) for address in addresses):
                matched = rule
                break
        return EgressRequest.objects.create(tenant_id=tenant, agent_execution=execution, destination=canonical, resolved_address=sorted(addresses)[0] if addresses else None, port=port, protocol=protocol, allowed=matched is not None and bool(addresses), matched_rule=matched, reason_code="ALLOWLIST_MATCH" if matched and addresses else "EGRESS_DENIED", metadata={})


class SecretValue:
    """Non-serializable secret wrapper confined to worker execution code."""

    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        self.__value = value

    def reveal(self) -> str:
        return self.__value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        raise TypeError("SecretValue cannot be converted to text")


class SecretService:
    @staticmethod
    def _encrypt(plaintext: str) -> tuple[str, str, str]:
        if not isinstance(plaintext, str) or not plaintext:
            raise ValidationError({"plaintext": "A non-empty secret value is required."})
        key_id = str(getattr(settings, "SARAISE_ENCRYPTION_KEY_ID", "")).strip()
        if not key_id:
            raise AgentServiceError("ENCRYPTION_UNAVAILABLE", "Secret encryption key metadata is not configured.")
        data_key = Fernet.generate_key()
        ciphertext = Fernet(data_key).encrypt(plaintext.encode()).decode()
        wrapped = EncryptionService.encrypt(data_key.decode())
        return ciphertext, wrapped, key_id

    @staticmethod
    @transaction.atomic
    def create_secret(tenant_id: UUID, actor_id: UUID, command: Mapping[str, Any]) -> Secret:
        values = _mapping(command, "command")
        plaintext = str(values.pop("plaintext", ""))
        ciphertext, wrapped, key_id = SecretService._encrypt(plaintext)
        values.pop("tenant_id", None)
        values.pop("created_by", None)
        return Secret.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), created_by=_actor(actor_id), ciphertext=ciphertext, wrapped_data_key=wrapped, key_id=key_id, **values)

    @staticmethod
    def get_metadata(tenant_id: UUID, secret_id: UUID) -> Secret:
        return Secret.objects.get(tenant_id=_uuid(tenant_id, "tenant_id"), id=_uuid(secret_id, "secret_id"))

    @staticmethod
    def list_metadata(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[Secret]:
        query = Secret.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"))
        values = _mapping(filters, "filters")
        for key in ("secret_type", "is_active"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        return query.order_by("name", "id")

    @staticmethod
    @transaction.atomic
    def rotate_secret(
        tenant_id: UUID,
        actor_id: UUID,
        secret_id: UUID,
        plaintext: str,
        idempotency_key: str | None = None,
        correlation_id: UUID | None = None,
    ) -> Secret:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        configuration = ConfigurationService.resolve(tenant)
        maximum = int(configuration["agent"]["execution_idempotency_key_maximum_length"])
        if idempotency_key is None:
            digest = hashlib.sha256(plaintext.encode()).hexdigest()
            idempotency_key = f"compat:{secret_id}:{digest}"
        key = str(idempotency_key).strip()
        if not key or len(key) > maximum:
            raise ValidationError({"idempotency_key": f"A key of at most {maximum} characters is required."})
        existing = SecretRotationRecord.objects.filter(
            tenant_id=tenant, idempotency_key=key
        ).select_related("secret").first()
        if existing is not None:
            if existing.secret_id != _uuid(secret_id, "secret_id"):
                raise IdempotencyConflictError("The idempotency key belongs to another secret.")
            return existing.secret
        secret = Secret.objects.select_for_update().get(tenant_id=tenant, id=_uuid(secret_id, "secret_id"))
        ciphertext, wrapped_data_key, key_id = SecretService._encrypt(plaintext)
        prior = (secret.ciphertext, secret.wrapped_data_key, secret.key_id)
        rotated_at = timezone.now()
        try:
            secret.ciphertext = ciphertext
            secret.wrapped_data_key = wrapped_data_key
            secret.key_id = key_id
            secret.last_rotated_at = rotated_at
            secret.save(
                update_fields=("ciphertext", "wrapped_data_key", "key_id", "last_rotated_at", "updated_at")
            )
            SecretRotationRecord.objects.create(
                tenant_id=tenant,
                secret=secret,
                idempotency_key=key,
                rotated_by=actor,
                correlation_id=(
                    ConfigurationService._correlation(correlation_id)
                    if correlation_id is not None
                    else uuid5(NAMESPACE_URL, f"saraise:secret-rotation:{tenant}:{key}")
                ),
                previous_ciphertext=prior[0],
                previous_wrapped_data_key=prior[1],
                previous_key_id=prior[2],
                resulting_rotated_at=rotated_at,
            )
        except Exception:
            # The transaction is the primary rollback. Restoring the in-memory
            # aggregate prevents callers from observing a half-applied value.
            secret.ciphertext, secret.wrapped_data_key, secret.key_id = prior
            raise
        return secret

    @staticmethod
    @transaction.atomic
    def deactivate_secret(tenant_id: UUID, actor_id: UUID, secret_id: UUID) -> Secret:
        del actor_id
        secret = SecretService.get_metadata(tenant_id, secret_id)
        secret.is_active = False
        secret.save(update_fields=("is_active", "updated_at"))
        return secret

    @staticmethod
    @transaction.atomic
    def resolve_for_execution(tenant_id: UUID, actor_id: UUID, secret_id: UUID, execution_id: UUID, purpose: str) -> SecretValue:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        if not purpose.strip():
            raise ValidationError({"purpose": "A purpose is required."})
        secret = SecretService.get_metadata(tenant, secret_id)
        execution = ExecutionService.get_execution(tenant, execution_id)
        if not secret.is_active or (secret.expires_at and secret.expires_at <= timezone.now()):
            raise AgentServiceError("SECRET_UNAVAILABLE", "The secret is inactive or expired.")
        data_key = EncryptionService.decrypt(secret.wrapped_data_key).encode()
        try:
            plaintext = Fernet(data_key).decrypt(secret.ciphertext.encode()).decode()
        except Exception as exc:
            raise AgentServiceError("SECRET_DECRYPTION_FAILED", "The secret could not be decrypted.") from exc
        SecretAccess.objects.create(tenant_id=tenant, secret=secret, agent_execution=execution, accessed_by=actor, purpose=purpose, metadata={})
        return SecretValue(plaintext)


class UsageService:
    @staticmethod
    @transaction.atomic
    def enqueue_cost_recalculation(
        tenant_id: UUID,
        actor_id: UUID,
        command: Mapping[str, Any],
        correlation_id: UUID,
    ) -> AsyncJob:
        values = _mapping(command, "command")
        idempotency_key = str(values.pop("idempotency_key", "")).strip()
        configuration = ConfigurationService.resolve(tenant_id)
        maximum = int(configuration["agent"]["execution_idempotency_key_maximum_length"])
        if not idempotency_key or len(idempotency_key) > maximum:
            raise ValidationError(
                {"idempotency_key": f"A key of at most {maximum} characters is required."}
            )
        payload = {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in values.items()
        }
        payload["correlation_id"] = str(ConfigurationService._correlation(correlation_id))
        job = enqueue(
            _uuid(tenant_id, "tenant_id"),
            _actor(actor_id),
            AGGREGATE_COST_COMMAND,
            payload,
            idempotency_key,
        )
        if str(job.correlation_id) != payload["correlation_id"]:
            job.correlation_id = payload["correlation_id"]
            job.save(update_fields=("correlation_id", "updated_at"))
        return job

    @staticmethod
    def reserve_quota(tenant_id: UUID, resource: str, amount: int, execution_id: UUID | None = None) -> OperationResult[int]:
        tenant = _uuid(tenant_id, "tenant_id")
        result = QuotaService().consume(tenant, resource, cost=amount)
        if not result.allowed:
            return OperationResult.failed(code="QUOTA_EXCEEDED", message="The tenant quota is exhausted or unavailable.", evidence={"remaining": result.remaining}, http_status=429)
        UsageService.record_quota_usage(tenant, resource, amount, result.remaining, execution_id)
        return OperationResult.succeeded(result.remaining, evidence={"remaining": result.remaining, "consumed": amount})

    @staticmethod
    @transaction.atomic
    def record_quota_usage(tenant_id: UUID, resource: str, amount: int, remaining_after: int, execution_id: UUID | None = None) -> QuotaUsage:
        execution = ExecutionService.get_execution(tenant_id, execution_id) if execution_id else None
        return QuotaUsage.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), resource=resource, agent_execution=execution, usage_value=amount, remaining_after=remaining_after, metadata={})

    @staticmethod
    @transaction.atomic
    def record_token_usage(tenant_id: UUID, execution_id: UUID, provider: str, model: str, input_tokens: int, output_tokens: int, metadata: Mapping[str, Any] | None = None) -> TokenUsage:
        return TokenUsage.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), agent_execution=ExecutionService.get_execution(tenant_id, execution_id), provider=provider, model=model, input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens, metadata=_safe_metadata(metadata))

    @staticmethod
    @transaction.atomic
    def record_cost(tenant_id: UUID, amount: Decimal, pricing_version: str | None, **values: Any) -> OperationResult[CostRecord]:
        if not pricing_version:
            return OperationResult.unavailable(capability="provider_pricing", message="Versioned provider pricing is unavailable.")
        values.pop("tenant_id", None)
        record = CostRecord.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), amount=amount, pricing_version=pricing_version, **values)
        return OperationResult.succeeded(record, evidence={"cost_record_id": str(record.id), "pricing_version": pricing_version})

    @staticmethod
    def get_usage(tenant_id: UUID) -> dict[str, QuerySet[Any]]:
        tenant = _uuid(tenant_id, "tenant_id")
        return {"quotas": Quota.objects.filter(tenant_id=tenant).order_by("resource"), "usage": QuotaUsage.objects.filter(tenant_id=tenant).order_by("-usage_timestamp", "id"), "tokens": TokenUsage.objects.filter(tenant_id=tenant).order_by("-usage_timestamp", "id")}

    @staticmethod
    def get_cost_breakdown(tenant_id: UUID, start: datetime, end: datetime, currency: str = "USD") -> dict[str, Any]:
        rows = CostRecord.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), currency=currency, cost_timestamp__gte=start, cost_timestamp__lt=end)
        return {"total": rows.aggregate(value=Sum("amount"))["value"] or Decimal("0"), "by_type": list(rows.values("cost_type").annotate(total=Sum("amount")).order_by("cost_type"))}

    @staticmethod
    @transaction.atomic
    def generate_cost_summary(tenant_id: UUID, period_start: datetime, period_end: datetime, period_type: str, currency: str) -> CostSummary:
        tenant = _uuid(tenant_id, "tenant_id")
        costs = CostRecord.objects.filter(tenant_id=tenant, currency=currency, cost_timestamp__gte=period_start, cost_timestamp__lt=period_end)
        total = costs.aggregate(value=Sum("amount"))["value"] or Decimal("0")
        by_type = {item["cost_type"]: str(item["total"]) for item in costs.values("cost_type").annotate(total=Sum("amount"))}
        token_total = TokenUsage.objects.filter(tenant_id=tenant, usage_timestamp__gte=period_start, usage_timestamp__lt=period_end).aggregate(value=Sum("total_tokens"))["value"] or 0
        execution_total = AgentExecution.objects.filter(tenant_id=tenant, created_at__gte=period_start, created_at__lt=period_end).count()
        summary, _ = CostSummary.objects.update_or_create(tenant_id=tenant, period_start=period_start, period_end=period_end, period_type=period_type, currency=currency, defaults={"total_cost": total, "cost_by_type": by_type, "cost_by_module": {}, "cost_by_provider": {}, "total_tokens": token_total, "total_executions": execution_total, "calculated_at": timezone.now()})
        return summary


class KillSwitchService:
    @staticmethod
    def list_switches(tenant_id: UUID) -> QuerySet[KillSwitch]:
        return KillSwitch.objects.filter(
            tenant_id=_uuid(tenant_id, "tenant_id")
        ).order_by("-created_at", "id")

    @staticmethod
    def check(tenant_id: UUID, agent_id: UUID | None = None, shard_id: UUID | None = None) -> OperationResult[None]:
        tenant = _uuid(tenant_id, "tenant_id")
        query = KillSwitch.objects.filter(tenant_id=tenant, status="active")
        applies = query.filter(scope="tenant", scope_id__isnull=True)
        if agent_id:
            applies = applies | query.filter(scope="agent", scope_id=_uuid(agent_id, "agent_id"))
        if shard_id:
            applies = applies | query.filter(scope="shard", scope_id=_uuid(shard_id, "shard_id"))
        if applies.exists():
            return OperationResult.failed(code="KILL_SWITCH_ACTIVE", message="AI execution is disabled for this scope.", http_status=409)
        return OperationResult.succeeded(None, evidence={"checked": True})

    @staticmethod
    @transaction.atomic
    def activate(tenant_id: UUID, actor_id: UUID, scope: str, scope_id: UUID | None, reason: str, transition_key: str) -> KillSwitch:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        if scope == "tenant" and scope_id is not None:
            raise ValidationError({"scope_id": "Tenant scope must not include a scope identifier."})
        if scope in {"agent", "shard"} and scope_id is None:
            raise ValidationError({"scope_id": "This scope requires an identifier."})
        switch = KillSwitch.objects.create(tenant_id=tenant, name=f"{scope}-emergency-control", scope=scope, scope_id=scope_id, status="active", transition_history=[{"transition_key": transition_key, "command": "activate", "from_state": "inactive", "to_state": "active", "occurred_at": timezone.now().isoformat(), "metadata": {}}], reason=reason, activated_by=actor, activated_at=timezone.now())
        enqueue(tenant, actor, KILL_SWITCH_COMMAND, {"kill_switch_id": str(switch.id)}, f"ai-kill:{transition_key}")
        return switch

    @staticmethod
    @transaction.atomic
    def deactivate(tenant_id: UUID, actor_id: UUID, kill_switch_id: UUID, reason: str, transition_key: str) -> KillSwitch:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        maximum = int(ConfigurationService.resolve(tenant)["agent"]["transition_reason_maximum_length"])
        switch = KillSwitch.objects.get(tenant_id=tenant, id=_uuid(kill_switch_id, "kill_switch_id"))
        return _transition_with_updates(
            KILL_SWITCH_MACHINE, switch, "deactivate", tenant, transition_key,
            {"deactivated_by": actor, "deactivated_at": timezone.now()},
            metadata={"reason_code": reason[:maximum]},
        )


class AuditService:
    @staticmethod
    @transaction.atomic
    def start_trail(tenant_id: UUID, request_id: UUID, execution_id: UUID, actor_id: UUID) -> AuditTrail:
        tenant = _uuid(tenant_id, "tenant_id")
        request = _uuid(request_id, "request_id")
        trail, _ = AuditTrail.objects.get_or_create(tenant_id=tenant, request_id=request, defaults={"correlation_id": _correlation_uuid(request), "agent_execution": ExecutionService.get_execution(tenant, execution_id), "initiating_principal": _actor(actor_id), "summary": {}})
        return trail

    @staticmethod
    @transaction.atomic
    def record_event(tenant_id: UUID, event_type: str, actor_id: UUID, subject_id: UUID, outcome: str, **relations: Any) -> AuditEvent:
        allowed = {"agent_execution", "tool_invocation", "approval_request", "session_id", "request_id", "policy_decisions", "workflow_transitions", "affected_resources", "metadata"}
        values = {key: value for key, value in relations.items() if key in allowed}
        values["metadata"] = _safe_metadata(values.get("metadata"))
        request_id = _uuid(values.get("request_id"), "request_id")
        values["request_id"] = request_id
        return AuditEvent.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), event_type=event_type, initiating_principal=_actor(actor_id), subject_id=_uuid(subject_id, "subject_id"), correlation_id=_correlation_uuid(request_id), outcome=outcome, outcome_details={}, **values)

    record_lifecycle_event = record_event
    record_tool_event = record_event
    record_approval_event = record_event

    @staticmethod
    @transaction.atomic
    def complete_trail(tenant_id: UUID, request_id: UUID, outcome: str, summary: Mapping[str, Any] | None = None) -> AuditTrail:
        trail = AuditService.get_trail(tenant_id, request_id)
        existing = AuditEvent.objects.filter(
            tenant_id=trail.tenant_id,
            request_id=trail.request_id,
            event_type="audit_trail_completed",
        ).first()
        if existing is not None:
            return trail
        event = AuditEvent.objects.create(
            tenant_id=trail.tenant_id,
            event_type="audit_trail_completed",
            agent_execution=trail.agent_execution,
            initiating_principal=trail.initiating_principal,
            subject_id=trail.agent_execution.agent.subject_id,
            session_id=trail.agent_execution.session_id,
            request_id=trail.request_id,
            correlation_id=trail.correlation_id,
            outcome=outcome if outcome in {"success", "failure", "blocked"} else "failure",
            outcome_details={"final_outcome": outcome},
            policy_decisions=[],
            workflow_transitions=[],
            affected_resources=[],
            metadata=_safe_metadata(summary, trail.tenant_id),
        )
        position = trail.ordered_events.count()
        from .audit_models import AuditTrailEvent

        AuditTrailEvent.objects.create(
            tenant_id=trail.tenant_id,
            audit_trail=trail,
            audit_event=event,
            position=position,
        )
        return trail

    @staticmethod
    def get_trail(tenant_id: UUID, request_id: UUID) -> AuditTrail:
        return AuditTrail.objects.select_related("agent_execution").get(tenant_id=_uuid(tenant_id, "tenant_id"), request_id=_uuid(request_id, "request_id"))

    @staticmethod
    def query_events(tenant_id: UUID, filters: Mapping[str, Any] | None = None) -> QuerySet[AuditEvent]:
        query = AuditEvent.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"))
        values = _mapping(filters, "filters")
        for key in ("event_type", "outcome", "correlation_id", "agent_execution_id"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        if values.get("started_at"):
            query = query.filter(event_timestamp__gte=values["started_at"])
        if values.get("ended_at"):
            query = query.filter(event_timestamp__lte=values["ended_at"])
        return query.order_by("-event_timestamp", "id")


class EvaluationService:
    @staticmethod
    @transaction.atomic
    def start_evaluation(tenant_id: UUID, actor_id: UUID, agent_id: UUID, suite_key: str, idempotency_key: str) -> OperationResult[AsyncJob]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        agent = AgentService.get_agent(tenant, agent_id)
        if evaluation_registry.get(suite_key) is None:
            return OperationResult.unavailable(capability=f"evaluation_suite:{suite_key}", message="The evaluation suite is unavailable.")
        if runner_registry.get(agent.runner_key) is None:
            return OperationResult.unavailable(capability=f"runner:{agent.runner_key}", message="The configured runner is unavailable.")
        job = enqueue(tenant, actor, EVALUATE_COMMAND, {"agent_id": str(agent.id), "suite_key": suite_key}, f"ai-eval:{idempotency_key}")
        return OperationResult.succeeded(job, evidence={"async_job_id": str(job.id), "suite_key": suite_key})

    @staticmethod
    def run_evaluation_job(tenant_id: UUID, job_id: UUID) -> Mapping[str, Any]:
        tenant = _uuid(tenant_id, "tenant_id")
        job = AsyncJob.objects.get(
            tenant_id=tenant,
            id=_uuid(job_id, "job_id"),
            command__in=(EVALUATE_COMMAND, RED_TEAM_COMMAND),
        )
        owns_lifecycle = job.status == JobStatus.QUEUED
        if owns_lifecycle:
            job = transition_job(
                job.id, tenant, JobStatus.RUNNING, expected_status=JobStatus.QUEUED,
                reason="Evaluation worker claimed job",
            )
        suite_key = str(job.payload.get("suite_key", ""))
        runner = evaluation_registry.require(suite_key)
        try:
            result = runner(tenant_id=str(tenant), agent_id=str(job.payload["agent_id"]), job_id=str(job.id))
        except Exception:
            if owns_lifecycle:
                transition_job(
                    job.id, tenant, JobStatus.FAILED, expected_status=JobStatus.RUNNING,
                    error_message="Evaluation suite failed.", reason="Evaluation suite raised an exception",
                )
            raise
        if not isinstance(result, Mapping) or "metrics" not in result or "status" not in result:
            if owns_lifecycle:
                transition_job(
                    job.id, tenant, JobStatus.FAILED, expected_status=JobStatus.RUNNING,
                    error_message="Invalid evaluation evidence.", reason="Evaluation result contract rejected",
                )
            raise AgentServiceError("INVALID_EVALUATION_RESULT", "The evaluation suite returned invalid evidence.")
        evidence = dict(result)
        if owns_lifecycle:
            transition_job(
                job.id, tenant, JobStatus.SUCCEEDED, expected_status=JobStatus.RUNNING,
                result=evidence, reason="Evaluation evidence persisted",
            )
        return evidence

    @staticmethod
    @transaction.atomic
    def start_red_team(tenant_id: UUID, actor_id: UUID, agent_id: UUID, suite_key: str, idempotency_key: str) -> OperationResult[AsyncJob]:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
        agent = AgentService.get_agent(tenant, agent_id)
        if evaluation_registry.get(suite_key) is None:
            return OperationResult.unavailable(
                capability=f"evaluation_suite:{suite_key}", message="The red-team suite is unavailable."
            )
        if runner_registry.get(agent.runner_key) is None:
            return OperationResult.unavailable(
                capability=f"runner:{agent.runner_key}", message="The configured runner is unavailable."
            )
        job = enqueue(
            tenant, actor, RED_TEAM_COMMAND,
            {"agent_id": str(agent.id), "suite_key": suite_key, "isolated": True},
            f"ai-red-team:{idempotency_key}",
        )
        return OperationResult.succeeded(job, evidence={"async_job_id": str(job.id), "suite_key": suite_key})


# Source-compatible singleton used by legacy adapters; new code uses class APIs.
agent_service = AgentService()


__all__ = [
    "AGGREGATE_COST_COMMAND", "AgentService", "AgentServiceError", "ApprovalService", "AuditService",
    "EVALUATE_COMMAND", "EvaluationService", "ExecutionService", "EgressService", "INVOKE_TOOL_COMMAND",
    "KillSwitchService", "ScheduleService", "SecretService", "SecretValue", "SoDService", "ToolService",
    "UsageService", "agent_service", "configure_session_validator",
]
