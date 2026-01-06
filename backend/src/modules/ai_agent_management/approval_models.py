"""Approval Models.

Database models for human approval gates and SoD enforcement.
Task: 401.3 - Human Approval Gates
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone
from typing import Optional, Dict, Any
import uuid

from .models import TenantBaseModel, AgentExecution
from .tool_models import Tool


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class ApprovalStatus(models.TextChoices):
    """Approval request status."""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class ApprovalRequest(TenantBaseModel):
    """Approval request model.

    Tracks approval requests for tool invocations that require human approval.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    tool = models.ForeignKey(
        Tool,
        on_delete=models.CASCADE,
        related_name="approval_requests",
        db_index=True,
    )
    agent_execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.CASCADE,
        related_name="approval_requests",
        db_index=True,
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.CASCADE,
        related_name="approval_requests",
        null=True,
        blank=True,
        db_index=True,
    )
    requested_by = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User/agent who requested approval",
    )
    requested_for = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User/agent who will execute if approved",
    )
    approver_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        db_index=True,
        help_text="User ID who approved/rejected",
    )
    status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
        db_index=True,
    )
    tool_input = models.JSONField(help_text="Tool input data")
    justification = models.TextField(
        blank=True, help_text="Justification for the request"
    )
    rejection_reason = models.TextField(
        blank=True, help_text="Reason for rejection"
    )
    requested_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(
        null=True, blank=True, db_index=True, help_text="Approval expiration time"
    )
    decided_at = models.DateTimeField(
        null=True, blank=True, help_text="When approval decision was made"
    )
    metadata = models.JSONField(default=dict, help_text="Additional metadata")

    class Meta:
        db_table = "ai_approval_requests"
        indexes = [
            models.Index(fields=["tenant_id", "status"]),
            models.Index(fields=["tenant_id", "tool_id"]),
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "requested_by"]),
            models.Index(fields=["tenant_id", "requested_for"]),
            models.Index(fields=["tenant_id", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"Approval {self.id} for {self.tool.name} ({self.status})"


class SoDPolicy(TenantBaseModel):
    """SoD (Segregation of Duties) policy model.

    Defines SoD constraints for tool invocations.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    action_1 = models.CharField(
        max_length=255,
        db_index=True,
        help_text="First action in SoD constraint",
    )
    action_2 = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Second action in SoD constraint",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.CharField(max_length=36, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_sod_policies"
        indexes = [
            models.Index(fields=["tenant_id", "action_1"]),
            models.Index(fields=["tenant_id", "action_2"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["action_1", "action_2"]),
        ]
        unique_together = [["tenant_id", "action_1", "action_2"]]

    def __str__(self) -> str:
        return f"SoD Policy: {self.action_1} <-> {self.action_2}"


class SoDViolation(TenantBaseModel):
    """SoD violation tracking model.

    Records SoD violations for audit and monitoring.
    """

    id = models.CharField(
        max_length=36, primary_key=True, default=generate_uuid
    )
    policy = models.ForeignKey(
        SoDPolicy,
        on_delete=models.CASCADE,
        related_name="violations",
        db_index=True,
    )
    agent_execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.CASCADE,
        related_name="sod_violations",
        null=True,
        blank=True,
        db_index=True,
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.CASCADE,
        related_name="sod_violations",
        null=True,
        blank=True,
        db_index=True,
    )
    action_1_user = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User who performed first action",
    )
    action_2_user = models.CharField(
        max_length=36,
        db_index=True,
        help_text="User who attempted second action",
    )
    action_1_timestamp = models.DateTimeField(
        help_text="When first action was performed"
    )
    action_2_timestamp = models.DateTimeField(
        help_text="When second action was attempted"
    )
    blocked = models.BooleanField(
        default=True, db_index=True, help_text="Whether action was blocked"
    )
    violation_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "ai_sod_violations"
        indexes = [
            models.Index(fields=["tenant_id", "policy_id"]),
            models.Index(fields=["tenant_id", "blocked"]),
            models.Index(fields=["tenant_id", "violation_at"]),
        ]

    def __str__(self) -> str:
        return f"SoD Violation {self.id} ({self.policy.name})"

