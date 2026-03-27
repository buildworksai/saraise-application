"""
LLM Provider Abstraction Layer for SARAISE AI Agents.

SARAISE AI Architecture: Provider-agnostic LLM integration with
circuit breakers, cost tracking, and automatic failover.
"""

from .base import (
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
    ProviderConfig,
    ProviderStatus,
    TokenUsage,
)
from .circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState
from .exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from .factory import ProviderFactory, get_provider, get_provider_factory
from .registry import ProviderRegistry, get_registry

__all__ = [
    # Base classes and data structures
    "LLMProvider",
    "LLMResponse",
    "EmbeddingResponse",
    "ProviderConfig",
    "TokenUsage",
    "ProviderStatus",
    # Circuit breaker
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitState",
    # Exceptions
    "ProviderError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "ProviderAuthError",
    "ProviderQuotaError",
    # Factory and registry
    "ProviderFactory",
    "ProviderRegistry",
    "get_provider",
    "get_provider_factory",
    "get_registry",
]
