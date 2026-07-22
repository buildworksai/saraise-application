"""Immutable, correlated AI runtime evidence."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

from .models import AITenantModel, AppendOnlyTenantModel, GovernedStateManager, validate_same_tenant


def generate_uuid() -> str:
    return str(uuid.uuid4())


class AuditEventType(models.TextChoices):
    AGENT_CREATED = "agent_created", "Agent created"
    AGENT_STARTED = "agent_started", "Agent started"
    AGENT_PAUSED = "agent_paused", "Agent paused"
    AGENT_RESUMED = "agent_resumed", "Agent resumed"
    AGENT_COMPLETED = "agent_completed", "Agent completed"
    AGENT_FAILED = "agent_failed", "Agent failed"
    AGENT_TERMINATED = "agent_terminated", "Agent terminated"
    TOOL_INVOKED = "tool_invoked", "Tool invoked"
    TOOL_COMPLETED = "tool_completed", "Tool completed"
    TOOL_FAILED = "tool_failed", "Tool failed"
    APPROVAL_REQUESTED = "approval_requested", "Approval requested"
    APPROVAL_GRANTED = "approval_granted", "Approval granted"
    APPROVAL_REJECTED = "approval_rejected", "Approval rejected"
    QUOTA_EXCEEDED = "quota_exceeded", "Quota exceeded"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated", "Kill switch activated"
    EGRESS_BLOCKED = "egress_blocked", "Egress blocked"
    SOD_VIOLATION = "sod_violation", "SoD violation"


class AuditOutcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    BLOCKED = "blocked", "Blocked"
    PENDING = "pending", "Pending"


class AuditFinalOutcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"
    BLOCKED = "blocked", "Blocked"
    PARTIAL = "partial", "Partial"


@tenancy_scope(TENANT_SCOPED)
class AuditEvent(AppendOnlyTenantModel):
    event_type = models.CharField(max_length=100)
    agent_execution = models.ForeignKey(
        "AgentExecution", on_delete=models.PROTECT, related_name="audit_events", null=True, blank=True
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation", on_delete=models.PROTECT, related_name="audit_events", null=True, blank=True
    )
    approval_request = models.ForeignKey(
        "ApprovalRequest", on_delete=models.PROTECT, related_name="audit_events", null=True, blank=True
    )
    initiating_principal = models.UUIDField()
    subject_id = models.UUIDField()
    session_id = models.UUIDField(null=True, blank=True)
    request_id = models.UUIDField()
    correlation_id = models.UUIDField()
    event_timestamp = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=20, choices=AuditOutcome.choices)
    outcome_details = models.JSONField(default=dict, blank=True)
    policy_decisions = models.JSONField(default=list, blank=True)
    workflow_transitions = models.JSONField(default=list, blank=True)
    affected_resources = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_audit_events"
        indexes = [
            models.Index(fields=("tenant_id", "correlation_id", "event_timestamp"), name="ai_audit_evt_t_corr_idx"),
            models.Index(fields=("tenant_id", "event_type", "event_timestamp"), name="ai_audit_evt_t_type_idx"),
            models.Index(fields=("tenant_id", "agent_execution", "event_timestamp"), name="ai_audit_evt_t_exec_idx"),
            models.Index(fields=("tenant_id", "outcome", "event_timestamp"), name="ai_audit_evt_t_outcome_idx"),
        ]
        ordering = ("event_timestamp", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent_execution", "tool_invocation", "approval_request")
        for field in ("outcome_details", "metadata"):
            if not isinstance(getattr(self, field), dict):
                raise ValidationError({field: "Must be a JSON object."})
        for field in ("policy_decisions", "workflow_transitions", "affected_resources"):
            if not isinstance(getattr(self, field), list):
                raise ValidationError({field: "Must be a JSON list."})

    def __str__(self) -> str:
        return f"Audit Event {self.id}: {self.event_type} ({self.outcome})"


@tenancy_scope(TENANT_SCOPED)
class AuditTrail(AITenantModel):
    request_id = models.UUIDField()
    correlation_id = models.UUIDField()
    agent_execution = models.ForeignKey("AgentExecution", on_delete=models.PROTECT, related_name="audit_trails")
    initiating_principal = models.UUIDField()
    request_timestamp = models.DateTimeField()
    completed_timestamp = models.DateTimeField(null=True, blank=True)
    final_outcome = models.CharField(max_length=20, choices=AuditFinalOutcome.choices, null=True, blank=True)
    events = models.ManyToManyField(AuditEvent, through="AuditTrailEvent", related_name="audit_trails")
    summary = models.JSONField(default=dict, blank=True)

    objects = GovernedStateManager()

    class Meta:
        db_table = "ai_audit_trails"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "request_id"), name="ai_audit_trail_t_req_uniq"),
            models.CheckConstraint(
                condition=(
                    Q(completed_timestamp__isnull=True, final_outcome__isnull=True)
                    | Q(completed_timestamp__isnull=False, final_outcome__isnull=False)
                ),
                name="ai_audit_trail_complete_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "request_id"), name="ai_audit_trail_t_req_idx"),
            models.Index(fields=("tenant_id", "correlation_id"), name="ai_audit_trail_t_corr_idx"),
            models.Index(fields=("tenant_id", "agent_execution"), name="ai_audit_trail_t_exec_idx"),
        ]
        ordering = ("-request_timestamp", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "agent_execution")
        if not isinstance(self.summary, dict):
            raise ValidationError({"summary": "Must be a JSON object."})

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding and self.pk:
            prior = (
                type(self)
                ._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id)
                .values("completed_timestamp")
                .first()
            )
            if prior and prior["completed_timestamp"] is not None:
                raise ValidationError("Completed audit trails are immutable.", code="terminal_immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        del args, kwargs
        raise ValidationError("Audit trails cannot be deleted.", code="evidence_protected")

    def __str__(self) -> str:
        return f"Audit Trail {self.id}: {self.request_id} ({self.final_outcome or 'pending'})"


@tenancy_scope(TENANT_SCOPED)
class AuditTrailEvent(AppendOnlyTenantModel):
    audit_trail = models.ForeignKey(AuditTrail, on_delete=models.PROTECT, related_name="ordered_events")
    audit_event = models.ForeignKey(AuditEvent, on_delete=models.PROTECT, related_name="trail_positions")
    position = models.PositiveIntegerField()
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_audit_trail_events"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "audit_trail", "position"), name="ai_audit_link_t_pos_uniq"),
            models.UniqueConstraint(
                fields=("tenant_id", "audit_trail", "audit_event"), name="ai_audit_link_t_event_uniq"
            ),
        ]
        indexes = [models.Index(fields=("tenant_id", "audit_trail", "position"), name="ai_audit_link_t_order_idx")]
        ordering = ("position", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "audit_trail", "audit_event")

    def __str__(self) -> str:
        return f"{self.audit_trail_id}:{self.position}"
