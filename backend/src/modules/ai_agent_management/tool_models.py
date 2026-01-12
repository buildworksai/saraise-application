"""Tool Registry Models.

Database models for tool registration and metadata.
Task: 401.2 - Tool Registry & Schema Validation
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from django.db import models
from django.utils import timezone

from .models import TenantBaseModel
from .tool_registry import ToolSideEffectClass


def generate_uuid():
    """Generate UUID for model primary keys."""
    return str(uuid.uuid4())


class Tool(TenantBaseModel):
    """Tool registration model.

    Stores tool definitions in the database for persistence and discovery.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    name = models.CharField(max_length=255, db_index=True, help_text="Tool name (globally unique)")
    owning_module = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Module that owns this tool",
    )
    version = models.CharField(
        max_length=20,
        default="1.0.0",
        db_index=True,
        help_text="Tool version",
    )
    description = models.TextField(blank=True)
    required_permissions = models.JSONField(help_text="List of required permissions")
    input_schema = models.JSONField(help_text="Input schema definition")
    output_schema = models.JSONField(help_text="Output schema definition")
    side_effect_class = models.CharField(
        max_length=30,
        choices=[(choice.value, choice.name) for choice in ToolSideEffectClass],
        db_index=True,
        help_text="Side-effect classification",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, help_text="Tool metadata")
    registered_by = models.CharField(max_length=36, db_index=True, help_text="User who registered the tool")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_tools"
        indexes = [
            models.Index(fields=["tenant_id", "name"]),
            models.Index(fields=["tenant_id", "owning_module"]),
            models.Index(fields=["tenant_id", "side_effect_class"]),
            models.Index(fields=["tenant_id", "is_active"]),
            models.Index(fields=["name", "version"]),  # Unique constraint
        ]
        unique_together = [["name", "version"]]

    def __str__(self) -> str:
        return f"{self.name} v{self.version} ({self.owning_module})"


class ToolInvocation(TenantBaseModel):
    """Tool invocation tracking model.

    Tracks tool invocations for audit and monitoring.
    """

    id = models.CharField(max_length=36, primary_key=True, default=generate_uuid)
    tool = models.ForeignKey(
        Tool,
        on_delete=models.CASCADE,
        related_name="invocations",
        db_index=True,
    )
    agent_execution = models.ForeignKey(
        "AgentExecution",
        on_delete=models.CASCADE,
        related_name="tool_invocations",
        null=True,
        blank=True,
        db_index=True,
    )
    input_data = models.JSONField(help_text="Tool input data")
    output_data = models.JSONField(null=True, blank=True, help_text="Tool output data")
    success = models.BooleanField(default=True, db_index=True)
    error_message = models.TextField(blank=True)
    invoked_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "ai_tool_invocations"
        indexes = [
            models.Index(fields=["tenant_id", "tool_id"]),
            models.Index(fields=["tenant_id", "agent_execution_id"]),
            models.Index(fields=["tenant_id", "success"]),
            models.Index(fields=["tenant_id", "invoked_at"]),
        ]

    def __str__(self) -> str:
        return f"Invocation {self.id} of {self.tool.name}"
