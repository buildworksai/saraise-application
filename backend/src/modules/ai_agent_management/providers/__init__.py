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
from src.core.resilience import CircuitBreaker, CircuitBreakerError, CircuitOpenError, CircuitState
from .exceptions import (
    ProviderAuthError,
    ProviderError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)
from .factory import ProviderFactory, configure_provider_factory, get_provider, get_provider_factory
from .registry import ProviderRegistrationError, ProviderRegistry, get_registry

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
    "CircuitOpenError",
    # Exceptions
    "ProviderError",
    "ProviderTimeoutError",
    "ProviderRateLimitError",
    "ProviderAuthError",
    "ProviderQuotaError",
    # Factory and registry
    "ProviderFactory",
    "ProviderRegistry",
    "ProviderRegistrationError",
    "configure_provider_factory",
    "get_provider",
    "get_provider_factory",
    "get_registry",
]
