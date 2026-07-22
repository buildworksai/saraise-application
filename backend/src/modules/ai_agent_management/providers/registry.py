"""Deterministic provider-adapter registry.

Provider configuration and credentials remain owned by
``ai_provider_configuration``.  This registry contains executable adapters
only and rejects import-order dependent replacement.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

from .base import LLMProvider

ProviderT = TypeVar("ProviderT", bound=type[LLMProvider])


class ProviderRegistrationError(RuntimeError):
    """Raised when an adapter name is invalid or already registered."""


class ProviderRegistry:
    """Thread-safe registry of signed/installed provider adapter classes."""

    def __init__(self) -> None:
        self._registry: dict[str, type[LLMProvider]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ProviderRegistrationError("Provider adapter name is required")
        key = name.strip().lower()
        if len(key) > 100:
            raise ProviderRegistrationError("Provider adapter name is too long")
        return key

    def register(
        self,
        name: str,
        provider_class: ProviderT | None = None,
        *,
        replace: bool = False,
    ) -> ProviderT | Callable[[ProviderT], ProviderT]:
        """Register directly or as a decorator; replacement is explicit."""

        key = self._key(name)

        def decorator(candidate: ProviderT) -> ProviderT:
            if not isinstance(candidate, type) or not issubclass(candidate, LLMProvider):
                raise ProviderRegistrationError("Provider adapter must implement LLMProvider")
            with self._lock:
                existing = self._registry.get(key)
                if existing is not None and existing is not candidate and not replace:
                    raise ProviderRegistrationError(f"Provider adapter {key!r} is already registered")
                self._registry[key] = candidate
            return candidate

        if provider_class is None:
            return decorator
        return decorator(provider_class)

    def get(self, name: str) -> type[LLMProvider] | None:
        with self._lock:
            return self._registry.get(self._key(name))

    def require(self, name: str) -> type[LLMProvider]:
        candidate = self.get(name)
        if candidate is None:
            raise ProviderRegistrationError(f"Provider adapter {name!r} is unavailable")
        return candidate

    def unregister(self, name: str) -> type[LLMProvider] | None:
        with self._lock:
            return self._registry.pop(self._key(name), None)

    def list_providers(self) -> list[str]:
        with self._lock:
            return sorted(self._registry)

    def is_registered(self, name: str) -> bool:
        return self.get(name) is not None


_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    return _registry


__all__ = ["ProviderRegistrationError", "ProviderRegistry", "get_registry"]
