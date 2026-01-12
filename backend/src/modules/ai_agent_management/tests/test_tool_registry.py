"""Tests for Tool Registry Service.

Task: 401.2 - Tool Registry & Schema Validation
"""

from __future__ import annotations

import pytest

from ..tool_registry import ToolDefinition, ToolRegistry, ToolSchema, ToolSideEffectClass


class TestToolRegistry:
    """Test tool registry service."""

    def test_register_tool(self) -> None:
        """Test registering a tool."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="test_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
                required=["input"],
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
            description="Test tool",
        )

        registry.register_tool(tool)

        assert registry.get_tool("test_tool") == tool

    def test_register_tool_duplicate(self) -> None:
        """Test registering duplicate tool fails."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="test_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        registry.register_tool(tool)

        # Try to register same tool again
        with pytest.raises(ValueError, match="already registered"):
            registry.register_tool(tool)

    def test_validate_input(self) -> None:
        """Test input validation."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="test_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
                required=["input"],
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        registry.register_tool(tool)

        # Valid input
        assert registry.validate_input("test_tool", {"input": "test"}) is True

        # Invalid input (missing required field)
        assert registry.validate_input("test_tool", {}) is False

        # Invalid input (wrong type)
        assert registry.validate_input("test_tool", {"input": 123}) is False

    def test_validate_output(self) -> None:
        """Test output validation."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="test_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        registry.register_tool(tool)

        # Valid output
        assert registry.validate_output("test_tool", {"output": "test"}) is True

        # Invalid output (wrong type)
        assert registry.validate_output("test_tool", {"output": 123}) is False

    def test_list_tools(self) -> None:
        """Test listing tools."""
        registry = ToolRegistry()

        tool1 = ToolDefinition(
            name="tool1",
            owning_module="module1",
            required_permissions=["perm1"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        tool2 = ToolDefinition(
            name="tool2",
            owning_module="module2",
            required_permissions=["perm2"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.DATA_MUTATION,
        )

        registry.register_tool(tool1)
        registry.register_tool(tool2)

        # List all tools
        all_tools = registry.list_tools()
        assert len(all_tools) == 2

        # Filter by module
        module1_tools = registry.list_tools(owning_module="module1")
        assert len(module1_tools) == 1
        assert module1_tools[0].name == "tool1"

        # Filter by side-effect class
        read_only_tools = registry.list_tools(side_effect_class=ToolSideEffectClass.READ_ONLY)
        assert len(read_only_tools) == 1
        assert read_only_tools[0].name == "tool1"

    def test_get_tools_by_module(self) -> None:
        """Test getting tools by module."""
        registry = ToolRegistry()

        tool1 = ToolDefinition(
            name="tool1",
            owning_module="module1",
            required_permissions=["perm1"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        tool2 = ToolDefinition(
            name="tool2",
            owning_module="module1",
            required_permissions=["perm2"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        registry.register_tool(tool1)
        registry.register_tool(tool2)

        module_tools = registry.get_tools_by_module("module1")
        assert len(module_tools) == 2
        assert {t.name for t in module_tools} == {"tool1", "tool2"}

    def test_unregister_tool(self) -> None:
        """Test unregistering a tool."""
        registry = ToolRegistry()

        tool = ToolDefinition(
            name="test_tool",
            owning_module="test_module",
            required_permissions=["test.permission"],
            input_schema=ToolSchema(
                type="object",
                properties={"input": {"type": "string"}},
            ),
            output_schema=ToolSchema(
                type="object",
                properties={"output": {"type": "string"}},
            ),
            side_effect_class=ToolSideEffectClass.READ_ONLY,
        )

        registry.register_tool(tool)
        assert registry.get_tool("test_tool") is not None

        registry.unregister_tool("test_tool")
        assert registry.get_tool("test_tool") is None
