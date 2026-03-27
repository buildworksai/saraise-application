"""
Circuit breaker for LLM provider fault isolation.

Implements the circuit breaker pattern to prevent cascading failures
when an LLM provider becomes unavailable. Each provider instance
maintains its own circuit breaker state.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Provider failed, requests fail immediately
- HALF_OPEN: Testing if provider has recovered
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, TypeVar

logger = logging.getLogger("saraise.ai.circuit_breaker")

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is OPEN and request is rejected."""

    def __init__(self, provider: str, reset_at: float) -> None:
        self.provider = provider
        self.reset_at = reset_at
        wait = max(0, reset_at - time.monotonic())
        super().__init__(f"Circuit breaker OPEN for provider '{provider}'. " f"Retry in {wait:.1f}s.")


class CircuitBreaker:
    """
    Per-provider circuit breaker with thread-safe state transitions.

    Usage:
        breaker = CircuitBreaker("openai", threshold=5, reset_seconds=60)

        try:
            result = breaker.call(lambda: provider.call(messages))
        except CircuitBreakerError:
            # Use fallback provider
            ...
    """

    def __init__(
        self,
        provider_name: str,
        threshold: int = 5,
        reset_seconds: int = 60,
    ) -> None:
        self.provider_name = provider_name
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.reset_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit HALF_OPEN for %s (testing recovery)", self.provider_name)
            return self._state

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function through circuit breaker."""
        state = self.state

        if state == CircuitState.OPEN:
            raise CircuitBreakerError(
                self.provider_name,
                self._last_failure_time + self.reset_seconds,
            )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as exc:
            self._on_failure(exc)
            raise

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit CLOSED for %s (recovered)", self.provider_name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit OPEN for %s (failed during recovery test): %s",
                    self.provider_name,
                    exc,
                )
            elif self._failure_count >= self.threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit OPEN for %s (%d failures in window): %s",
                    self.provider_name,
                    self._failure_count,
                    exc,
                )

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            logger.info("Circuit manually RESET for %s", self.provider_name)
