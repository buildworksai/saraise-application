"""Tool Service.

High-level service for tool registration and management.
Task: 401.2 - Tool Registry & Schema Validation
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from django.utils import timezone
from django.db import transaction

from .models import AgentExecution
from .tool_registry import (
    ToolRegistry,
    ToolDefinition,
    ToolSchema,
    ToolSideEffectClass,
)
from .tool_models import Tool, ToolInvocation

logger = logging.getLogger(__name__)


class ToolService:
    """Service for managing tool registration and invocation."""

    def __init__(self) -> None:
        """Initialize tool service."""
        self.registry = ToolRegistry()

    def register_tool(
        self,
        tenant_id: str,
        tool_def: ToolDefinition,
        registered_by: str,
    ) -> Tool:
        """Register a tool in the database and registry.

        Args:
            tenant_id: Tenant ID.
            tool_def: Tool definition.
            registered_by: User ID who registered the tool.

        Returns:
            Created Tool instance.

        Raises:
            ValueError: If tool validation fails or tool already exists.
        """
        # Register in memory registry
        self.registry.register_tool(tool_def)

        # Store in database
        tool = Tool.objects.create(
            tenant_id=tenant_id,
            name=tool_def.name,
            owning_module=tool_def.owning_module,
            version=tool_def.version,
            description=tool_def.description,
            required_permissions=tool_def.required_permissions,
            input_schema={
                "type": tool_def.input_schema.type,
                "properties": tool_def.input_schema.properties or {},
                "required": tool_def.input_schema.required or [],
                "additionalProperties": tool_def.input_schema.additional_properties,
            },
            output_schema={
                "type": tool_def.output_schema.type,
                "properties": tool_def.output_schema.properties or {},
                "required": tool_def.output_schema.required or [],
                "additionalProperties": tool_def.output_schema.additional_properties,
            },
            side_effect_class=tool_def.side_effect_class.value,
            metadata=tool_def.metadata,
            registered_by=registered_by,
        )

        logger.info(
            f"Registered tool {tool.name} v{tool.version} for tenant {tenant_id}"
        )

        return tool

    def get_tool(
        self, tool_name: str, tenant_id: Optional[str] = None
    ) -> Optional[Tool]:
        """Get a tool by name.

        Args:
            tool_name: Tool name.
            tenant_id: Optional tenant ID filter.

        Returns:
            Tool instance or None if not found.
        """
        query = Tool.objects.filter(name=tool_name, is_active=True)

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        return query.first()

    def list_tools(
        self,
        tenant_id: Optional[str] = None,
        owning_module: Optional[str] = None,
        side_effect_class: Optional[str] = None,
    ) -> List[Tool]:
        """List registered tools.

        Args:
            tenant_id: Optional tenant ID filter.
            owning_module: Optional module filter.
            side_effect_class: Optional side-effect class filter.

        Returns:
            List of Tool instances.
        """
        query = Tool.objects.filter(is_active=True)

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        if owning_module:
            query = query.filter(owning_module=owning_module)

        if side_effect_class:
            query = query.filter(side_effect_class=side_effect_class)

        return list(query.order_by("name", "version"))

    def invoke_tool(
        self,
        tool_name: str,
        tenant_id: str,
        input_data: Dict[str, Any],
        agent_execution_id: Optional[str] = None,
    ) -> ToolInvocation:
        """Invoke a tool with input validation.

        Args:
            tool_name: Tool name.
            tenant_id: Tenant ID.
            input_data: Tool input data.
            agent_execution_id: Optional agent execution ID.

        Returns:
            ToolInvocation instance.

        Raises:
            ValueError: If tool not found or input validation fails.
        """
        # Get tool from database
        tool = self.get_tool(tool_name, tenant_id)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        # Get tool definition from registry
        tool_def = self.registry.get_tool(tool_name)
        if not tool_def:
            raise ValueError(f"Tool {tool_name} not found in registry")

        # Validate input
        if not self.registry.validate_input(tool_name, input_data):
            raise ValueError(f"Tool {tool_name} input validation failed")

        # Create invocation record
        invocation = ToolInvocation.objects.create(
            tenant_id=tenant_id,
            tool=tool,
            agent_execution_id=agent_execution_id,
            input_data=input_data,
            success=False,  # Will be updated after execution
            invoked_at=timezone.now(),
        )

        logger.info(
            f"Invoked tool {tool_name} for tenant {tenant_id} "
            f"(invocation {invocation.id})"
        )

        return invocation

    def complete_invocation(
        self,
        invocation_id: str,
        tenant_id: str,
        output_data: Any,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> ToolInvocation:
        """Complete a tool invocation.

        Args:
            invocation_id: Invocation ID.
            tenant_id: Tenant ID.
            output_data: Tool output data.
            success: Whether invocation succeeded.
            error_message: Error message if failed.

        Returns:
            Updated ToolInvocation instance.

        Raises:
            ValueError: If invocation not found or output validation fails.
        """
        invocation = ToolInvocation.objects.filter(
            id=invocation_id, tenant_id=tenant_id
        ).first()

        if not invocation:
            raise ValueError(f"Invocation {invocation_id} not found")

        # Validate output if successful
        if success:
            tool_def = self.registry.get_tool(invocation.tool.name)
            if tool_def:
                if not self.registry.validate_output(
                    invocation.tool.name, output_data
                ):
                    success = False
                    error_message = "Tool output validation failed"

        # Update invocation
        invocation.success = success
        invocation.output_data = output_data if success else None
        invocation.error_message = error_message or ""
        invocation.completed_at = timezone.now()

        # Calculate duration
        if invocation.invoked_at:
            duration = invocation.completed_at - invocation.invoked_at
            invocation.duration_ms = int(duration.total_seconds() * 1000)

        invocation.save(
            update_fields=[
                "success",
                "output_data",
                "error_message",
                "completed_at",
                "duration_ms",
                "updated_at",
            ]
        )

        logger.info(
            f"Completed tool invocation {invocation_id} "
            f"(success={success})"
        )

        return invocation

    def unregister_tool(
        self, tool_name: str, tenant_id: str, version: Optional[str] = None
    ) -> None:
        """Unregister a tool.

        Args:
            tool_name: Tool name.
            tenant_id: Tenant ID.
            version: Optional version (if not provided, unregisters all versions).

        Raises:
            ValueError: If tool not found.
        """
        query = Tool.objects.filter(name=tool_name, tenant_id=tenant_id)

        if version:
            query = query.filter(version=version)

        tools = list(query)

        if not tools:
            raise ValueError(f"Tool {tool_name} not found")

        # Unregister from registry
        for tool in tools:
            self.registry.unregister_tool(tool.name)

        # Deactivate in database
        query.update(is_active=False)

        logger.info(f"Unregistered tool {tool_name} for tenant {tenant_id}")


# Global tool service instance
tool_service = ToolService()

