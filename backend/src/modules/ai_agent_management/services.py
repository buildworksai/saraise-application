"""Tenant-first command services for the governed AI agent runtime.

All mutations are transactional.  Controllers only validate transport data and
delegate here; workers reuse the same commands under an explicit tenant
context.  Provider/tool content is intentionally excluded from logs and audit
snapshots.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

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
from .egress_models import EgressRequest, EgressRule, Secret, SecretAccess
from .models import Agent, AgentExecution, AgentSchedulerTask
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


class AgentServiceError(RuntimeError):
    """Stable service error safe to map at the API boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


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


def _safe_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Retain identifiers and control evidence, never free-form content."""

    if not value:
        return {}
    allowed = {"schema_version", "runner_key", "provider", "model", "pricing_version", "reason_code"}
    return {key: item for key, item in value.items() if key in allowed and isinstance(item, (str, int, bool))}


def _correlation_uuid() -> UUID:
    value = get_correlation_id()
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return uuid4()


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
    if not transition_key or len(transition_key) > 255:
        raise ValidationError({"transition_key": "A transition key of at most 255 characters is required."})
    return machine.apply(
        aggregate,
        command,
        tenant_id=tenant_id,
        transition_key=transition_key,
        metadata=_safe_metadata(metadata),
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

    if not transition_key or len(transition_key) > 255:
        raise ValidationError({"transition_key": "A transition key of at most 255 characters is required."})
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
            "metadata": _safe_metadata(metadata),
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
        values = _mapping(command, "command")
        values.pop("tenant_id", None)
        values.pop("created_by", None)
        values.pop("status", None)
        values.pop("transition_history", None)
        identity = values.get("identity_type")
        session_id = values.get("session_id")
        if identity == "user_bound" and not session_id:
            raise ValidationError({"session_id": "User-bound agents require a session."})
        if identity == "system_bound" and session_id:
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
        query = Agent.objects.filter(tenant_id=_uuid(tenant_id, "tenant_id"), deleted_at__isnull=True)
        values = _mapping(filters, "filters")
        for key in ("status", "identity_type", "runner_key", "subject_id"):
            if values.get(key) not in (None, ""):
                query = query.filter(**{key: values[key]})
        raw_search = values.get("search")
        search = "" if raw_search in (None, "") else str(raw_search).strip()[:255]
        if search:
            query = query.filter(Q(name__icontains=search) | Q(description__icontains=search))
        ordering = str(values.get("ordering", "name"))
        if ordering.lstrip("-") not in {"name", "created_at", "updated_at"}:
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
        return _transition(AGENT_MACHINE, AgentService.get_agent(tenant_id, agent_id), "disable", _uuid(tenant_id, "tenant_id"), transition_key, metadata={"reason_code": reason[:100]})

    @staticmethod
    @transaction.atomic
    def retire_agent(tenant_id: UUID, actor_id: UUID, agent_id: UUID, reason: str, transition_key: str) -> Agent:
        del actor_id
        tenant = _uuid(tenant_id, "tenant_id")
        return _transition_with_updates(
            AGENT_MACHINE,
            AgentService.get_agent(tenant, agent_id),
            "retire",
            tenant,
            transition_key,
            {"deleted_at": timezone.now()},
            metadata={"reason_code": reason[:100]},
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
        if not idempotency_key or len(idempotency_key) > 255:
            raise ValidationError({"idempotency_key": "A key of at most 255 characters is required."})
        prior = AgentExecution.objects.filter(tenant_id=tenant, idempotency_key=idempotency_key).first()
        if prior is not None:
            return OperationResult.succeeded(prior, evidence={"execution_id": str(prior.id), "duplicate": True})
        agent = AgentService.get_agent(tenant, agent_id)
        if agent.status != "active":
            return OperationResult.failed(code="AGENT_NOT_ACTIVE", message="The agent is not active.", http_status=409)
        killed = KillSwitchService.check(tenant, agent_id=agent.id)
        if killed.status != "succeeded":
            return OperationResult.failed(code=killed.error_code or "KILL_SWITCH_ACTIVE", message=killed.message or "Execution is disabled.", http_status=409)
        if runner_registry.get(agent.runner_key) is None:
            return OperationResult.unavailable(capability=f"runner:{agent.runner_key}", message="The configured runner is unavailable.")
        if agent.identity_type == "user_bound" and (
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
        return _transition_with_updates(
            EXECUTION_MACHINE, cls._owned(tenant, agent_id, execution_id), "terminate", tenant,
            transition_key, {"completed_at": timezone.now()}, metadata={"reason_code": reason[:100]},
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
        return _transition_with_updates(
            EXECUTION_MACHINE, ExecutionService.get_execution(tenant, execution_id), "fail", tenant,
            transition_key,
            {"error_code": error_code[:100], "error_message": safe_message, "completed_at": timezone.now()},
            metadata={"reason_code": error_code},
        )


class ScheduleService:
    @staticmethod
    @transaction.atomic
    def create_schedule(tenant_id: UUID, actor_id: UUID, agent_id: UUID, command: Mapping[str, Any]) -> AgentSchedulerTask:
        tenant, actor = _uuid(tenant_id, "tenant_id"), _actor(actor_id)
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
            priority=int(values.get("priority", 0)),
            max_retries=int(values.get("max_retries", 3)),
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
        if limit <= 0 or limit > 1000:
            raise ValidationError({"limit": "Must be between 1 and 1000."})
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
        return tool.side_effect_class != "read_only"

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
        approval = ApprovalService.get_request(tenant, approval_id)
        if approval.requested_by == approver:
            raise AgentServiceError("SELF_APPROVAL_FORBIDDEN", "Requestors cannot decide their own approval.")
        if approval.expires_at and approval.expires_at <= timezone.now():
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
            if not reason.strip():
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
        if approval.requested_by != actor:
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
        values = _mapping(command, "command")
        action_1, action_2 = sorted((str(values["action_1"]).strip(), str(values["action_2"]).strip()))
        if not action_1 or action_1 == action_2:
            raise ValidationError({"action_2": "Actions must be non-empty and different."})
        return SoDPolicy.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), created_by=_actor(actor_id), action_1=action_1, action_2=action_2, name=values["name"], description=values.get("description", ""))

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
        search = "" if raw_search in (None, "") else str(raw_search).strip()[:255]
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
    _FORBIDDEN = {ipaddress.ip_address("169.254.169.254"), ipaddress.ip_address("100.100.100.200"), ipaddress.ip_address("fd00:ec2::254")}

    @classmethod
    def _address(cls, value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        try:
            address = ipaddress.ip_address(value.split("%", 1)[0])
        except ValueError as exc:
            raise ValidationError({"destination": "Enter a canonical IP address."}) from exc
        comparable = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped else address
        if comparable in cls._FORBIDDEN or comparable.is_private or comparable.is_loopback or comparable.is_link_local or comparable.is_reserved or comparable.is_multicast or comparable.is_unspecified:
            raise ValidationError({"destination": "Internal, metadata, and non-routable destinations are forbidden."})
        return address

    @classmethod
    def normalize(cls, destination_type: str, destination: str) -> str:
        raw = destination.strip()
        if not raw or "*" in raw:
            raise ValidationError({"destination": "A concrete destination is required; wildcards are forbidden."})
        if destination_type == "domain":
            host = raw.rstrip(".").lower().encode("idna").decode("ascii")
            if host in {"localhost", "metadata", "metadata.google.internal"}:
                raise ValidationError({"destination": "Internal destinations are forbidden."})
            return host
        if destination_type == "ip":
            return str(cls._address(raw))
        if destination_type == "cidr":
            network = ipaddress.ip_network(raw, strict=True)
            cls._address(str(network.network_address))
            cls._address(str(network.broadcast_address))
            return str(network)
        if destination_type == "url_pattern":
            parsed = urlsplit(raw)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
                raise ValidationError({"destination": "Use a canonical HTTP(S) URL without credentials, query, or fragment."})
            host = cls.normalize("domain", parsed.hostname)
            return parsed._replace(netloc=f"{host}:{parsed.port}" if parsed.port else host).geturl()
        raise ValidationError({"destination_type": "Unsupported destination type."})

    @staticmethod
    @transaction.atomic
    def create_rule(tenant_id: UUID, actor_id: UUID, command: Mapping[str, Any]) -> EgressRule:
        values = _mapping(command, "command")
        values["destination"] = EgressService.normalize(values["destination_type"], values["destination"])
        values.pop("tenant_id", None)
        values.pop("created_by", None)
        rule = EgressRule(tenant_id=_uuid(tenant_id, "tenant_id"), created_by=_actor(actor_id), **values)
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
        rule.destination = EgressService.normalize(rule.destination_type, rule.destination)
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
        canonical = cls.normalize("domain", host)
        addresses: set[str] = set()
        try:
            for record in socket.getaddrinfo(canonical, port):
                address = str(cls._address(record[4][0]))
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
    def rotate_secret(tenant_id: UUID, actor_id: UUID, secret_id: UUID, plaintext: str) -> Secret:
        del actor_id
        secret = SecretService.get_metadata(tenant_id, secret_id)
        secret.ciphertext, secret.wrapped_data_key, secret.key_id = SecretService._encrypt(plaintext)
        secret.last_rotated_at = timezone.now()
        secret.save(update_fields=("ciphertext", "wrapped_data_key", "key_id", "last_rotated_at", "updated_at"))
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
        switch = KillSwitch.objects.get(tenant_id=tenant, id=_uuid(kill_switch_id, "kill_switch_id"))
        return _transition_with_updates(
            KILL_SWITCH_MACHINE, switch, "deactivate", tenant, transition_key,
            {"deactivated_by": actor, "deactivated_at": timezone.now()},
            metadata={"reason_code": reason[:100]},
        )


class AuditService:
    @staticmethod
    @transaction.atomic
    def start_trail(tenant_id: UUID, request_id: UUID, execution_id: UUID, actor_id: UUID) -> AuditTrail:
        tenant = _uuid(tenant_id, "tenant_id")
        trail, _ = AuditTrail.objects.get_or_create(tenant_id=tenant, request_id=_uuid(request_id, "request_id"), defaults={"correlation_id": _correlation_uuid(), "agent_execution": ExecutionService.get_execution(tenant, execution_id), "initiating_principal": _actor(actor_id), "summary": {}})
        return trail

    @staticmethod
    @transaction.atomic
    def record_event(tenant_id: UUID, event_type: str, actor_id: UUID, subject_id: UUID, outcome: str, **relations: Any) -> AuditEvent:
        allowed = {"agent_execution", "tool_invocation", "approval_request", "session_id", "request_id", "policy_decisions", "workflow_transitions", "affected_resources", "metadata"}
        values = {key: value for key, value in relations.items() if key in allowed}
        values["metadata"] = _safe_metadata(values.get("metadata"))
        return AuditEvent.objects.create(tenant_id=_uuid(tenant_id, "tenant_id"), event_type=event_type, initiating_principal=_actor(actor_id), subject_id=_uuid(subject_id, "subject_id"), correlation_id=_correlation_uuid(), outcome=outcome, outcome_details={}, **values)

    record_lifecycle_event = record_event
    record_tool_event = record_event
    record_approval_event = record_event

    @staticmethod
    @transaction.atomic
    def complete_trail(tenant_id: UUID, request_id: UUID, outcome: str, summary: Mapping[str, Any] | None = None) -> AuditTrail:
        trail = AuditService.get_trail(tenant_id, request_id)
        trail.completed_timestamp = timezone.now()
        trail.final_outcome = outcome
        trail.summary = _safe_metadata(summary)
        trail.save(update_fields=("completed_timestamp", "final_outcome", "summary", "updated_at"))
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
