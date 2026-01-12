"""Tool Registry Service.

Implements tool registry with runtime schema validation.
Task: 401.2 - Tool Registry & Schema Validation
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    logger.warning("jsonschema not available, schema validation will be limited")

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class ToolSideEffectClass(str, Enum):
    """Tool side-effect classification."""

    READ_ONLY = "read_only"
    WORKFLOW_TRANSITION = "workflow_transition"
    DATA_MUTATION = "data_mutation"
    EXTERNAL_INTEGRATION = "external_integration"


@dataclass
class ToolSchema:
    """Tool input/output schema definition."""

    type: str  # "object", "array", "string", etc.
    properties: Optional[Dict[str, Any]] = None
    required: Optional[List[str]] = None
    additional_properties: bool = True


@dataclass
class ToolDefinition:
    """Tool definition for registration."""

    name: str
    owning_module: str
    required_permissions: List[str]
    input_schema: ToolSchema
    output_schema: ToolSchema
    side_effect_class: ToolSideEffectClass
    description: str = ""
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    """Tool registry service for managing agent tools.

    Implements:
    - Tool registration
    - Runtime schema validation
    - Tool metadata management
    - Tool versioning
    - Tool discovery
    """

    def __init__(self) -> None:
        """Initialize tool registry."""
        self._tools: Dict[str, ToolDefinition] = {}
        self._tools_by_module: Dict[str, List[str]] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool in the registry.

        Args:
            tool: Tool definition.

        Raises:
            ValueError: If tool validation fails or tool already exists.
        """
        # Validate tool name format
        if not tool.name or not isinstance(tool.name, str):
            raise ValueError("Tool name must be a non-empty string")

        # Validate owning module
        if not tool.owning_module or not isinstance(tool.owning_module, str):
            raise ValueError("Tool owning_module must be a non-empty string")

        # Validate permissions
        if not tool.required_permissions or not isinstance(tool.required_permissions, list):
            raise ValueError("Tool required_permissions must be a non-empty list")

        # Validate side-effect class
        if not isinstance(tool.side_effect_class, ToolSideEffectClass):
            raise ValueError("Invalid side_effect_class")

        # Validate schemas
        self._validate_schema(tool.input_schema, "input_schema")
        self._validate_schema(tool.output_schema, "output_schema")

        # Check for duplicate tool name
        if tool.name in self._tools:
            existing_tool = self._tools[tool.name]
            if existing_tool.version == tool.version:
                raise ValueError(f"Tool {tool.name} version {tool.version} already registered")

        # Register tool
        self._tools[tool.name] = tool

        # Track by module
        if tool.owning_module not in self._tools_by_module:
            self._tools_by_module[tool.owning_module] = []
        self._tools_by_module[tool.owning_module].append(tool.name)

        logger.info(f"Registered tool {tool.name} v{tool.version} from module " f"{tool.owning_module}")

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name.

        Args:
            tool_name: Tool name.

        Returns:
            ToolDefinition instance or None if not found.
        """
        return self._tools.get(tool_name)

    def list_tools(
        self,
        owning_module: Optional[str] = None,
        side_effect_class: Optional[ToolSideEffectClass] = None,
    ) -> List[ToolDefinition]:
        """List registered tools.

        Args:
            owning_module: Optional module filter.
            side_effect_class: Optional side-effect class filter.

        Returns:
            List of ToolDefinition instances.
        """
        tools = list(self._tools.values())

        if owning_module:
            tools = [t for t in tools if t.owning_module == owning_module]

        if side_effect_class:
            tools = [t for t in tools if t.side_effect_class == side_effect_class]

        return tools

    def get_tools_by_module(self, module_name: str) -> List[ToolDefinition]:
        """Get all tools for a module.

        Args:
            module_name: Module name.

        Returns:
            List of ToolDefinition instances.
        """
        tool_names = self._tools_by_module.get(module_name, [])
        return [self._tools[name] for name in tool_names]

    def validate_input(self, tool_name: str, input_data: Dict[str, Any]) -> bool:
        """Validate tool input against schema.

        Args:
            tool_name: Tool name.
            input_data: Input data to validate.

        Returns:
            True if valid, False otherwise.

        Raises:
            ValueError: If tool not found.
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        return self._validate_against_schema(input_data, tool.input_schema)

    def validate_output(self, tool_name: str, output_data: Any) -> bool:
        """Validate tool output against schema.

        Args:
            tool_name: Tool name.
            output_data: Output data to validate.

        Returns:
            True if valid, False otherwise.

        Raises:
            ValueError: If tool not found.
        """
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        return self._validate_against_schema(output_data, tool.output_schema)

    def unregister_tool(self, tool_name: str) -> None:
        """Unregister a tool.

        Args:
            tool_name: Tool name.

        Raises:
            ValueError: If tool not found.
        """
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")

        del self._tools[tool_name]

        # Remove from module tracking
        if tool.owning_module in self._tools_by_module:
            if tool_name in self._tools_by_module[tool.owning_module]:
                self._tools_by_module[tool.owning_module].remove(tool_name)

        logger.info(f"Unregistered tool {tool_name}")

    def _validate_schema(self, schema: ToolSchema, schema_name: str) -> None:
        """Validate schema definition.

        Args:
            schema: Schema to validate.
            schema_name: Schema name for error messages.

        Raises:
            ValueError: If schema is invalid.
        """
        if not schema.type:
            raise ValueError(f"{schema_name}.type is required")

        if schema.type == "object" and not schema.properties:
            raise ValueError(f"{schema_name}.properties is required for object type")

    def _validate_against_schema(self, data: Any, schema: ToolSchema) -> bool:
        """Validate data against schema using JSON Schema.

        Args:
            data: Data to validate.
            schema: Schema definition.

        Returns:
            True if valid, False otherwise.
        """
        if not JSONSCHEMA_AVAILABLE:
            # Fallback to basic type checking if jsonschema not available
            return self._basic_type_validation(data, schema)

        try:
            # Convert ToolSchema to JSON Schema format
            json_schema = {
                "type": schema.type,
            }

            if schema.properties:
                json_schema["properties"] = schema.properties

            if schema.required:
                json_schema["required"] = schema.required

            json_schema["additionalProperties"] = schema.additional_properties

            # Validate using jsonschema
            jsonschema.validate(instance=data, schema=json_schema)

            return True

        except jsonschema.ValidationError as e:
            logger.warning(f"Schema validation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Schema validation error: {e}")
            return False

    def _basic_type_validation(self, data: Any, schema: ToolSchema) -> bool:
        """Basic type validation fallback when jsonschema not available.

        Args:
            data: Data to validate.
            schema: Schema definition.

        Returns:
            True if valid, False otherwise.
        """
        # Basic type checking
        type_map = {
            "object": dict,
            "array": list,
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "null": type(None),
        }

        expected_type = type_map.get(schema.type)
        if expected_type and not isinstance(data, expected_type):
            return False

        # Check required fields for objects
        if schema.type == "object" and isinstance(data, dict):
            if schema.required:
                for field in schema.required:
                    if field not in data:
                        return False

        return True


# Global tool registry instance
tool_registry = ToolRegistry()
