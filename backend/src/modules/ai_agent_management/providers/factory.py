"""
Provider factory with automatic failover and circuit breakers.

The factory manages provider instances, handles failover between
primary and fallback providers, and maintains per-provider circuit
breakers for fault isolation.
"""

from __future__ import annotations

import logging
from typing import Optional

from .base import LLMProvider, LLMResponse, ProviderStatus
from .circuit_breaker import CircuitBreaker, CircuitBreakerError

logger = logging.getLogger("saraise.ai.provider_factory")


class ProviderFactory:
    """
    Factory for creating and managing LLM provider instances.

    Supports:
    - Primary + fallback provider configuration
    - Per-provider circuit breakers
    - Automatic failover on provider failure
    - Provider health monitoring
    """

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._fallback_chain: list[str] = []

    def register(
        self,
        provider: LLMProvider,
        *,
        is_fallback: bool = False,
    ) -> None:
        """Register a provider instance."""
        name = provider.name
        self._providers[name] = provider
        self._circuit_breakers[name] = CircuitBreaker(
            provider_name=name,
            threshold=provider.config.circuit_breaker_threshold,
            reset_seconds=provider.config.circuit_breaker_reset_seconds,
        )

        if is_fallback:
            self._fallback_chain.append(name)
        else:
            # Primary provider goes to front of chain
            self._fallback_chain.insert(0, name)

        logger.info(
            "Registered provider '%s' (fallback=%s, chain=%s)",
            name,
            is_fallback,
            self._fallback_chain,
        )

    def get(self, name: str) -> Optional[LLMProvider]:
        """Get a provider by name."""
        return self._providers.get(name)

    def call_with_failover(
        self,
        messages: list[dict[str, str]],
        *,
        preferred_provider: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Call LLM with automatic failover through provider chain.

        Tries providers in order:
        1. preferred_provider (if specified and available)
        2. Primary provider
        3. Fallback providers in registration order

        Raises ProviderError if ALL providers fail.
        """
        chain = list(self._fallback_chain)
        if preferred_provider and preferred_provider in self._providers:
            chain.remove(preferred_provider) if preferred_provider in chain else None
            chain.insert(0, preferred_provider)

        last_error: Optional[Exception] = None

        for provider_name in chain:
            provider = self._providers.get(provider_name)
            if not provider:
                continue

            breaker = self._circuit_breakers.get(provider_name)
            if not breaker:
                continue

            try:
                response = breaker.call(provider.call, messages, **kwargs)
                # Track cost
                response.cost_usd = provider.get_cost(response.usage)
                return response
            except CircuitBreakerError as exc:
                logger.warning("Skipping %s: %s", provider_name, exc)
                last_error = exc
                continue
            except Exception as exc:
                logger.error(
                    "Provider %s failed: %s — trying next in chain",
                    provider_name,
                    exc,
                )
                last_error = exc
                continue

        raise RuntimeError(f"All providers failed. Chain: {chain}. Last error: {last_error}")

    def health_check_all(self) -> dict[str, ProviderStatus]:
        """Run health checks on all registered providers."""
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = provider.health_check()
            except Exception as exc:
                logger.error("Health check failed for %s: %s", name, exc)
                results[name] = ProviderStatus.UNAVAILABLE
        return results


# Module-level singleton
_factory: Optional[ProviderFactory] = None


def get_provider_factory() -> ProviderFactory:
    """Get or create the global provider factory."""
    global _factory
    if _factory is None:
        _factory = ProviderFactory()
    return _factory


def get_provider(name: str) -> Optional[LLMProvider]:
    """Convenience: get a provider from the global factory."""
    return get_provider_factory().get(name)
