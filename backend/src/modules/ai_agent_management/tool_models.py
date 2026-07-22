"""Tenant-owned tool descriptors and immutable invocation evidence."""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from src.core.tenancy.registry import TENANT_SCOPED, tenancy_scope

from .models import AITenantModel, StatefulTenantModel, validate_same_tenant


def generate_uuid() -> str:
    """Preserve the callable referenced by migration 0001."""

    return str(uuid.uuid4())


class ToolSideEffectClass(models.TextChoices):
    READ_ONLY = "read_only", "Read only"
    WORKFLOW_TRANSITION = "workflow_transition", "Workflow transition"
    DATA_MUTATION = "data_mutation", "Data mutation"
    EXTERNAL_INTEGRATION = "external_integration", "External integration"


class ToolInvocationStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    BLOCKED = "blocked", "Blocked"
    CANCELLED = "cancelled", "Cancelled"


@tenancy_scope(TENANT_SCOPED)
class Tool(AITenantModel):
    name = models.CharField(max_length=255)
    owning_module = models.CharField(max_length=100)
    version = models.CharField(max_length=50, default="1.0.0")
    description = models.TextField(blank=True, default="")
    required_permissions = models.JSONField(default=list, blank=True)
    input_schema = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    side_effect_class = models.CharField(max_length=30, choices=ToolSideEffectClass.choices)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    registered_by = models.UUIDField()
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_tools"
        constraints = [models.UniqueConstraint(fields=("tenant_id", "name", "version"), name="ai_tool_t_name_ver_uniq")]
        indexes = [
            models.Index(fields=("tenant_id", "name", "version"), name="ai_tool_t_name_ver_idx"),
            models.Index(fields=("tenant_id", "owning_module", "is_active"), name="ai_tool_t_module_idx"),
            models.Index(fields=("tenant_id", "side_effect_class"), name="ai_tool_t_effect_idx"),
        ]
        ordering = ("name", "version", "id")

    def clean(self) -> None:
        if not isinstance(self.required_permissions, list) or not all(
            isinstance(permission, str) and permission.strip() for permission in self.required_permissions
        ):
            raise ValidationError({"required_permissions": "Must be a JSON list of nonblank permission strings."})
        for field_name in ("input_schema", "output_schema", "metadata"):
            if not isinstance(getattr(self, field_name), dict):
                raise ValidationError({field_name: "Must be a JSON object."})
        for field_name in ("input_schema", "output_schema"):
            schema = getattr(self, field_name)
            if schema.get("type") not in (None, "object"):
                raise ValidationError({field_name: "The root JSON Schema type must be object."})

    def __str__(self) -> str:
        return f"{self.name} v{self.version} ({self.owning_module})"


@tenancy_scope(TENANT_SCOPED)
class ToolInvocation(StatefulTenantModel):
    tool = models.ForeignKey(Tool, on_delete=models.PROTECT, related_name="invocations")
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.PROTECT,
        related_name="tool_invocations",
        null=True,
        blank=True,
    )
    approval_request = models.ForeignKey(
        "ApprovalRequest",
        on_delete=models.PROTECT,
        related_name="invocations",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=30,
        choices=ToolInvocationStatus.choices,
        default=ToolInvocationStatus.REQUESTED,
    )
    transition_history = models.JSONField(default=list, blank=True)
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(null=True, blank=True)
    error_code = models.CharField(max_length=100, blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    invoked_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)

    state_field = "status"
    terminal_states = frozenset(
        (
            ToolInvocationStatus.SUCCEEDED,
            ToolInvocationStatus.FAILED,
            ToolInvocationStatus.BLOCKED,
            ToolInvocationStatus.CANCELLED,
        )
    )

    class Meta:
        db_table = "ai_tool_invocations"
        constraints = [
            models.UniqueConstraint(fields=("tenant_id", "idempotency_key"), name="ai_tool_inv_t_idem_uniq"),
            models.CheckConstraint(
                condition=~Q(status=ToolInvocationStatus.SUCCEEDED) | Q(output_data__isnull=False),
                name="ai_tool_inv_success_output_ck",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=(ToolInvocationStatus.FAILED, ToolInvocationStatus.BLOCKED))
                | ~Q(error_code=""),
                name="ai_tool_inv_error_code_ck",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status__in=(
                            ToolInvocationStatus.SUCCEEDED,
                            ToolInvocationStatus.FAILED,
                            ToolInvocationStatus.BLOCKED,
                            ToolInvocationStatus.CANCELLED,
                        ),
                        completed_at__isnull=False,
                    )
                    | (
                        ~Q(
                            status__in=(
                                ToolInvocationStatus.SUCCEEDED,
                                ToolInvocationStatus.FAILED,
                                ToolInvocationStatus.BLOCKED,
                                ToolInvocationStatus.CANCELLED,
                            )
                        )
                        & Q(completed_at__isnull=True)
                    )
                ),
                name="ai_tool_inv_terminal_ck",
            ),
        ]
        indexes = [
            models.Index(fields=("tenant_id", "tool", "status", "invoked_at"), name="ai_tool_inv_t_tool_idx"),
            models.Index(fields=("tenant_id", "agent_execution", "invoked_at"), name="ai_tool_inv_t_exec_idx"),
        ]
        ordering = ("-invoked_at", "id")

    def clean(self) -> None:
        validate_same_tenant(self, "tool", "agent_execution", "approval_request")
        if not isinstance(self.input_data, dict):
            raise ValidationError({"input_data": "Must be a JSON object."})
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Must be a JSON list."})

    def __str__(self) -> str:
        return f"Invocation {self.id} ({self.status})"
