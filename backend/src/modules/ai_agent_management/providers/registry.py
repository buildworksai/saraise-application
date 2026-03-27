"""
Provider registry for discovering and configuring available LLM providers.

Maps provider names to their implementation classes. New providers are
registered here and automatically available to the factory.
"""

from __future__ import annotations

import logging
from typing import Type

from .base import LLMProvider

logger = logging.getLogger("saraise.ai.provider_registry")


class ProviderRegistry:
    """
    Registry of available LLM provider implementations.

    Usage:
        registry = ProviderRegistry()
        registry.register("openai", OpenAIProvider)
        registry.register("anthropic", AnthropicProvider)

        provider_cls = registry.get("openai")
        provider = provider_cls(config)
    """

    def __init__(self) -> None:
        self._registry: dict[str, Type[LLMProvider]] = {}

    def register(self, name: str, provider_class: Type[LLMProvider]) -> None:
        """Register a provider implementation class."""
        if name in self._registry:
            logger.warning("Overwriting provider registration for '%s'", name)
        self._registry[name] = provider_class
        logger.info("Registered provider class '%s' -> %s", name, provider_class.__name__)

    def get(self, name: str) -> Type[LLMProvider] | None:
        """Get a provider class by name."""
        return self._registry.get(name)

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._registry.keys())

    def is_registered(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._registry


# Global registry singleton
_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    return _registry
