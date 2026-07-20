"""Shared fault-isolation and outbound HTTP primitives."""

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
)
from .http import (
    ConfigurationError,
    DependencyConnectionError,
    DependencyNotAllowedError,
    DependencyResponseError,
    DependencyTimeoutError,
    HttpClientConfigurationError,
    ResilientHttpClient,
    ResilientHttpError,
    UnsafeDestinationError,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerError",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "CircuitState",
    "ConfigurationError",
    "DependencyConnectionError",
    "DependencyNotAllowedError",
    "DependencyResponseError",
    "DependencyTimeoutError",
    "HttpClientConfigurationError",
    "ResilientHttpClient",
    "ResilientHttpError",
    "UnsafeDestinationError",
]
