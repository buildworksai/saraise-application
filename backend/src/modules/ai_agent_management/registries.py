"""Stable extension registries for agent runners and evaluation suites."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any, Protocol, TypeVar


class AgentRunner(Protocol):
    def __call__(self, *, tenant_id: str, execution_id: str, task: Mapping[str, Any]) -> Mapping[str, Any]: ...


class EvaluationSuiteRunner(Protocol):
    def __call__(self, *, tenant_id: str, agent_id: str, job_id: str) -> Mapping[str, Any]: ...


HandlerT = TypeVar("HandlerT", AgentRunner, EvaluationSuiteRunner)


class ExtensionRegistry:
    def __init__(self, kind: str, maximum_key_length: int | None = None) -> None:
        self.kind = kind
        self.maximum_key_length = maximum_key_length
        self._handlers: dict[str, Any] = {}
        self._lock = threading.RLock()

    def configure(self, maximum_key_length: int) -> None:
        if maximum_key_length <= 0:
            raise ValueError("Registry key limit must be positive")
        with self._lock:
            self.maximum_key_length = maximum_key_length

    def _key(self, key: str) -> str:
        if self.maximum_key_length is None:
            raise RuntimeError("Extension registry policy is not configured")
        if not isinstance(key, str) or not key.strip() or len(key.strip()) > self.maximum_key_length:
            raise ValueError(
                f"Extension key must be a non-empty string of at most {self.maximum_key_length} characters"
            )
        return key.strip()

    def register(self, key: str, handler: HandlerT | None = None) -> HandlerT | Callable[[HandlerT], HandlerT]:
        normalized = self._key(key)

        def decorator(candidate: HandlerT) -> HandlerT:
            if not callable(candidate):
                raise TypeError(f"{self.kind} handler must be callable")
            with self._lock:
                existing = self._handlers.get(normalized)
                if existing is not None and existing is not candidate:
                    raise ValueError(f"{self.kind} {normalized!r} is already registered")
                self._handlers[normalized] = candidate
            return candidate

        return decorator if handler is None else decorator(handler)

    def get(self, key: str) -> HandlerT | None:
        with self._lock:
            return self._handlers.get(self._key(key))

    def require(self, key: str) -> HandlerT:
        handler = self.get(key)
        if handler is None:
            raise LookupError(f"{self.kind} {key!r} is unavailable")
        return handler

    def unregister(self, key: str) -> HandlerT | None:
        with self._lock:
            return self._handlers.pop(self._key(key), None)

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._handlers))


runner_registry: ExtensionRegistry = ExtensionRegistry("agent runner")
evaluation_registry: ExtensionRegistry = ExtensionRegistry("evaluation suite")

__all__ = ["AgentRunner", "EvaluationSuiteRunner", "ExtensionRegistry", "evaluation_registry", "runner_registry"]
