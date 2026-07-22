"""Compatibility import for the durable execution runtime."""
from .services import ExecutionService
AgentRuntime = ExecutionService
__all__ = ["AgentRuntime", "ExecutionService"]
