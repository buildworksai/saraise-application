"""Compatibility exports for the shared resilience circuit breaker.

The agent module deliberately owns no breaker state.  Existing integrations
that imported this module continue to resolve to the canonical implementation.
"""

from src.core.resilience import CircuitBreaker, CircuitBreakerError, CircuitOpenError, CircuitState

# Historical name retained without introducing a second implementation.
CircuitBreakerError = CircuitBreakerError

__all__ = ["CircuitBreaker", "CircuitBreakerError", "CircuitOpenError", "CircuitState"]
