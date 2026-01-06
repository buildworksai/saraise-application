"""AI Audit Trail Models.

Database models for comprehensive audit trail: request → agent → tool → outcome.
Task: 403.1 - AI Audit Trail
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from typing import Optional, Dict, Any
import uuid

from .models import TenantBaseModel


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class AuditEventType(models.TextChoices):
    """Audit event types."""

    AGENT_CREATED = "agent_created", "Agent Created"
    AGENT_STARTED = "agent_started", "Agent Started"
    AGENT_PAUSED = "agent_paused", "Agent Paused"
    AGENT_RESUMED = "agent_resumed", "Agent Resumed"
    AGENT_COMPLETED = "agent_completed", "Agent Completed"
    AGENT_FAILED = "agent_failed", "Agent Failed"
    AGENT_TERMINATED = "agent_terminated", "Agent Terminated"
    TOOL_INVOKED = "tool_invoked", "Tool Invoked"
    TOOL_COMPLETED = "tool_completed", "Tool Completed"
    TOOL_FAILED = "tool_failed", "Tool Failed"
    APPROVAL_REQUESTED = "approval_requested", "Approval Requested"
    APPROVAL_GRANTED = "approval_granted", "Approval Granted"
    APPROVAL_REJECTED = "approval_rejected", "Approval Rejected"
    QUOTA_EXCEEDED = "quota_exceeded", "Quota Exceeded"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated", "Kill Switch Activated"
    EGRESS_BLOCKED = "egress_blocked", "Egress Blocked"
    SOD_VIOLATION = "sod_violation", "SoD Violation"


class AuditEvent(TenantBaseModel):
    """AI audit event model.

    Comprehensive audit trail for all AI agent operations.
    Implements: request → agent → tool → outcome
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    event_type = models.CharField(
        max_length=50,
        choices=AuditEventType.choices,
        db_index=True,
        help_text="Type of audit event",
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="audit_events",
        null=True,
        blank=True,
        db_index=True,
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        db_index=True,
    )
    approval_request = models.ForeignKey(
        "ApprovalRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
        db_index=True,
    )
    initiating_principal = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User/agent who initiated the action",
    )
    subject_id = models.CharField(
        max_length=36,
        db_index=True,
        help_text="Subject ID (user or system role)",
    )
    session_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        db_index=True,
        help_text="Session ID (for user-bound agents)",
    )
    request_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        db_index=True,
        help_text="Request ID for tracking",
    )
    event_timestamp = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    outcome = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("failure", "Failure"),
            ("blocked", "Blocked"),
            ("pending", "Pending"),
        ],
        db_index=True,
        help_text="Event outcome",
    )
    outcome_details = models.JSONField(
        default=dict,
        help_text="Detailed outcome information",
    )
    policy_decisions = models.JSONField(
        default=list,
        help_text="Policy evaluation decisions",
    )
    workflow_transitions = models.JSONField(
        default=list,
        help_text="Workflow transitions",
    )
    affected_resources = models.JSONField(
        default=list,
        help_text="Resources affected by this event",
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Additional event metadata",
    )

    class Meta:
        db_table = "ai_audit_events"
        indexes = [
            models.Index(fields=["tenant_id", "event_type"]),
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "initiating_principal"]),
            models.Index(fields=["tenant_id", "session_id"]),
            models.Index(fields=["tenant_id", "request_id"]),
            models.Index(fields=["tenant_id", "event_timestamp"]),
            models.Index(fields=["tenant_id", "outcome"]),
        ]

    def __str__(self) -> str:
        return f"Audit Event {self.id}: {self.event_type} ({self.outcome})"


class AuditTrail(TenantBaseModel):
    """Audit trail model.

    Links related audit events into a complete trail:
    request → agent → tool → outcome
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    request_id = models.CharField(
        max_length=36,
        unique=True,
        db_index=True,
        help_text="Request ID (unique identifier for the trail)",
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="audit_trail",
        db_index=True,
    )
    initiating_principal = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User/agent who initiated the request",
    )
    request_timestamp = models.DateTimeField(
        auto_now_add=True, db_index=True
    )
    completed_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When the trail was completed",
    )
    final_outcome = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("failure", "Failure"),
            ("blocked", "Blocked"),
            ("partial", "Partial Success"),
        ],
        null=True,
        blank=True,
        db_index=True,
        help_text="Final outcome of the request",
    )
    events = models.ManyToManyField(
        AuditEvent,
        related_name="audit_trails",
        help_text="Events in this audit trail",
    )
    summary = models.JSONField(
        default=dict,
        help_text="Trail summary (tools invoked, approvals, etc.)",
    )

    class Meta:
        db_table = "ai_audit_trails"
        indexes = [
            models.Index(fields=["tenant_id", "request_id"]),
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "initiating_principal"]),
            models.Index(fields=["tenant_id", "request_timestamp"]),
            models.Index(fields=["tenant_id", "final_outcome"]),
        ]

    def __str__(self) -> str:
        return f"Audit Trail {self.id}: {self.request_id} ({self.final_outcome or 'pending'})"

