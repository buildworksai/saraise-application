"""Tenant-safe approval and segregation-of-duties evidence models."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

from .models import AITenantModel, AgentExecution, AppendOnlyTenantModel, StatefulTenantModel, validate_same_tenant


def generate_uuid() -> str:
    """Preserve the callable referenced by migration 0001."""

    return str(uuid.uuid4())


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


@tenancy_scope(TENANT_SCOPED)
class ApprovalRequest(StatefulTenantModel):
    tool = models.ForeignKey("Tool", on_delete=models.PROTECT, related_name="approval_requests")
    agent_execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.PROTECT,
        related_name="approval_requests",
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.PROTECT,
        related_name="approval_requests",
        null=True,
        blank=True,
    )
    requested_by = models.UUIDField()
    requested_for = models.UUIDField()
    approver_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    transition_history = models.JSONField(default=list, blank=True, editable=False)
    tool_input = models.JSONField(default=dict, blank=True)
    justification = models.TextField(blank=True, default="")
    rejection_reason = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    state_field = "status"
    terminal_states = frozenset(
        (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED, ApprovalStatus.CANCELLED)
    )

    class Meta:
        db_table = "ai_approval_requests"
        constraints = [
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(expires_at__gt=F("requested_at")),
                name="ai_approval_expiry_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=ApprovalStatus.PENDING, approver_id__isnull=True, decided_at__isnull=True)
                    | Q(status=ApprovalStatus.CANCELLED, approver_id__isnull=True, decided_at__isnull=False)
                    | Q(
                        status__in=(ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED),
                        approver_id__isnull=False,
                        decided_at__isnull=False,
                    )
                ),
                name="ai_approval_decision_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status=ApprovalStatus.REJECTED) | ~Q(rejection_reason=""),
                name="ai_approval_reject_reason_ck",
            ),
            models.CheckConstraint(
                condition=Q(approver_id__isnull=True) | ~Q(approver_id=F("requested_by")),
                name="ai_approval_no_self_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "status", "requested_at"), name="ai_approval_t_status_idx"),
            models.Index(fields=("tenant_id", "approver_id", "status"), name="ai_approval_t_approver_idx"),
            models.Index(fields=("tenant_id", "agent_execution"), name="ai_approval_t_exec_idx"),
            models.Index(fields=("tenant_id", "expires_at"), name="ai_approval_t_expiry_idx"),
        ]
        ordering = ("-requested_at", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "tool", "agent_execution", "tool_invocation")
        if self.tool_invocation_id and self.tool_invocation.agent_execution_id != self.agent_execution_id:
            raise ValidationError({"tool_invocation": "The invocation must belong to the approval execution."})
        if not isinstance(self.tool_input, dict):
            raise ValidationError({"tool_input": "Must be a JSON object."})
        if not isinstance(self.metadata, dict):
            raise ValidationError({"metadata": "Must be a JSON object."})

    def __str__(self) -> str:
        return f"Approval {self.id} ({self.status})"


@tenancy_scope(TENANT_SCOPED)
class SoDPolicy(AITenantModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    action_1 = models.CharField(max_length=255)
    action_2 = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_by = models.UUIDField()

    class Meta:
        db_table = "ai_sod_policies"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant_id", "action_1", "action_2"),
                name="ai_sod_t_actions_uniq",
            ),
            models.CheckConstraint(condition=~Q(action_1=F("action_2")), name="ai_sod_actions_differ_ck"),
            models.CheckConstraint(condition=Q(action_1__lt=F("action_2")), name="ai_sod_actions_order_ck"),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "is_active"), name="ai_sod_t_active_idx"),
            models.Index(fields=("tenant_id", "action_1"), name="ai_sod_t_action1_idx"),
            models.Index(fields=("tenant_id", "action_2"), name="ai_sod_t_action2_idx"),
        ]
        ordering = ("name", "id")

    def clean(self) -> None:
        self.action_1 = self.action_1.strip()
        self.action_2 = self.action_2.strip()
        if self.action_1 == self.action_2:
            raise ValidationError("SoD actions must differ.")
        if self.action_2 < self.action_1:
            self.action_1, self.action_2 = self.action_2, self.action_1

    def __str__(self) -> str:
        return f"SoD Policy: {self.action_1} <-> {self.action_2}"


@tenancy_scope(TENANT_SCOPED)
class SoDViolation(AppendOnlyTenantModel):
    policy = models.ForeignKey(SoDPolicy, on_delete=models.PROTECT, related_name="violations")
    agent_execution = models.ForeignKey(
        AgentExecution,
        on_delete=models.PROTECT,
        related_name="sod_violations",
        null=True,
        blank=True,
    )
    tool_invocation = models.ForeignKey(
        "ToolInvocation",
        on_delete=models.PROTECT,
        related_name="sod_violations",
        null=True,
        blank=True,
    )
    action_1_user = models.UUIDField()
    action_2_user = models.UUIDField()
    action_1_timestamp = models.DateTimeField()
    action_2_timestamp = models.DateTimeField()
    blocked = models.BooleanField(default=True)
    violation_at = models.DateTimeField(auto_now_add=True)
    evidence = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_sod_violations"
        constraints = [
            models.CheckConstraint(
                condition=Q(agent_execution__isnull=False) | Q(tool_invocation__isnull=False),
                name="ai_sod_violation_parent_ck",
            ),
            models.CheckConstraint(
                condition=Q(action_2_timestamp__gte=F("action_1_timestamp")),
                name="ai_sod_violation_time_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "policy", "violation_at"), name="ai_sod_v_t_policy_idx"),
            models.Index(fields=("tenant_id", "blocked", "violation_at"), name="ai_sod_v_t_blocked_idx"),
        ]
        ordering = ("-violation_at", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "policy", "agent_execution", "tool_invocation")
        if not isinstance(self.evidence, dict):
            raise ValidationError({"evidence": "Must be a JSON object."})

    def __str__(self) -> str:
        return f"SoD Violation {self.id}"
