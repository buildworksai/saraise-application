"""Typed tool extension registry and JSON Schema validation."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from jsonschema import Draft202012Validator, SchemaError, ValidationError


class ToolSideEffectClass(str, Enum):
    READ_ONLY = "read_only"
    WORKFLOW_TRANSITION = "workflow_transition"
    DATA_MUTATION = "data_mutation"
    EXTERNAL_INTEGRATION = "external_integration"


@dataclass(frozen=True)
class ToolSchema:
    type: str
    properties: dict[str, Any] | None = None
    required: list[str] | None = None
    additional_properties: bool = False

    def as_json_schema(self) -> dict[str, Any]:
        value: dict[str, Any] = {"type": self.type, "additionalProperties": self.additional_properties}
        if self.properties is not None:
            value["properties"] = self.properties
        if self.required is not None:
            value["required"] = self.required
        return value


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    owning_module: str
    required_permissions: list[str]
    input_schema: ToolSchema
    output_schema: ToolSchema
    side_effect_class: ToolSideEffectClass
    description: str = ""
    version: str = "1.0.0"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RestrictedToolContext:
    tenant_id: str
    actor_id: str
    execution_id: str
    correlation_id: str


class ToolHandler(Protocol):
    def __call__(self, context: RestrictedToolContext, input_data: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ToolRegistryError(RuntimeError):
    pass


class ToolNotRegistered(ToolRegistryError):
    pass


class ToolRegistry:
    """Deterministic registry; duplicate versioned keys never overwrite."""

    _NAME = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")

    def __init__(self) -> None:
        self._definitions: dict[tuple[str, str], ToolDefinition] = {}
        self._handlers: dict[tuple[str, str], ToolHandler] = {}
        self._lock = threading.RLock()

    @staticmethod
    def validate_schema(schema: Mapping[str, Any] | ToolSchema) -> None:
        value = schema.as_json_schema() if isinstance(schema, ToolSchema) else dict(schema)
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as exc:
            raise ValueError("Invalid JSON Schema") from exc

    @classmethod
    def validate_value(cls, schema: Mapping[str, Any] | ToolSchema, value: Any) -> None:
        document = schema.as_json_schema() if isinstance(schema, ToolSchema) else dict(schema)
        cls.validate_schema(document)
        try:
            Draft202012Validator(document).validate(value)
        except ValidationError as exc:
            path = ".".join(str(item) for item in exc.absolute_path)
            raise ValueError(f"Schema validation failed{f' at {path}' if path else ''}") from exc

    def register_tool(self, tool: ToolDefinition, handler: ToolHandler | None = None) -> None:
        if not self._NAME.fullmatch(tool.name):
            raise ValueError("Tool name must be a lowercase extension key")
        if not self._NAME.fullmatch(tool.owning_module):
            raise ValueError("Owning module must be a lowercase extension key")
        if not tool.required_permissions or not all(
            isinstance(permission, str) and permission.strip() for permission in tool.required_permissions
        ):
            raise ValueError("Tool required_permissions must be a non-empty string list")
        self.validate_schema(tool.input_schema)
        self.validate_schema(tool.output_schema)
        key = (tool.name, tool.version)
        with self._lock:
            if key in self._definitions:
                raise ValueError(f"Tool {tool.name} version {tool.version} already registered")
            self._definitions[key] = tool
            if handler is not None:
                self._handlers[key] = handler

    def get_tool(self, tool_name: str, version: str | None = None) -> ToolDefinition | None:
        with self._lock:
            candidates = [value for (name, _), value in self._definitions.items() if name == tool_name]
            if version is not None:
                return self._definitions.get((tool_name, version))
            return sorted(candidates, key=lambda item: item.version)[-1] if candidates else None

    def require_handler(self, tool_name: str, version: str) -> ToolHandler:
        try:
            return self._handlers[(tool_name, version)]
        except KeyError as exc:
            raise ToolNotRegistered(f"No executable handler is registered for {tool_name}@{version}") from exc

    def list_tools(
        self,
        owning_module: str | None = None,
        side_effect_class: ToolSideEffectClass | None = None,
    ) -> list[ToolDefinition]:
        with self._lock:
            tools = list(self._definitions.values())
        if owning_module:
            tools = [tool for tool in tools if tool.owning_module == owning_module]
        if side_effect_class:
            tools = [tool for tool in tools if tool.side_effect_class == side_effect_class]
        return sorted(tools, key=lambda item: (item.name, item.version))

    def get_tools_by_module(self, module_name: str) -> list[ToolDefinition]:
        return self.list_tools(owning_module=module_name)

    def validate_input(self, tool_name: str, input_data: dict[str, Any], version: str | None = None) -> bool:
        tool = self.get_tool(tool_name, version)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        try:
            self.validate_value(tool.input_schema, input_data)
        except ValueError:
            return False
        return True

    def validate_output(self, tool_name: str, output_data: Any, version: str | None = None) -> bool:
        tool = self.get_tool(tool_name, version)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        try:
            self.validate_value(tool.output_schema, output_data)
        except ValueError:
            return False
        return True

    def unregister_tool(self, tool_name: str, version: str | None = None) -> None:
        tool = self.get_tool(tool_name, version)
        if tool is None:
            raise ValueError(f"Tool {tool_name} not found")
        key = (tool.name, tool.version)
        with self._lock:
            self._definitions.pop(key)
            self._handlers.pop(key, None)


tool_registry = ToolRegistry()


__all__ = [
    "RestrictedToolContext",
    "ToolDefinition",
    "ToolHandler",
    "ToolNotRegistered",
    "ToolRegistry",
    "ToolSchema",
    "ToolSideEffectClass",
    "tool_registry",
]
