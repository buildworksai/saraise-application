"""Thread-safe circuit breakers for isolating failing dependencies.

The breaker deliberately owns no retry policy.  It protects one logical
dependency operation and can therefore be reused by HTTP, queue, storage, or
provider adapters without coupling those adapters to each other.
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

logger = logging.getLogger("saraise.resilience.circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    """The three states of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerError(RuntimeError):
    """Raised when an open circuit rejects an operation."""

    def __init__(self, dependency: str, reset_at: float) -> None:
        self.dependency = dependency
        # ``provider`` preserves the useful attribute from the module-local
        # breaker that this implementation generalizes.
        self.provider = dependency
        self.reset_at = reset_at
        wait_seconds = max(0.0, reset_at - time.monotonic())
        super().__init__(f"Circuit breaker is open for dependency '{dependency}'; " f"retry in {wait_seconds:.1f}s")


# A descriptive alias for callers that prefer the state in the exception name.
CircuitOpenError = CircuitBreakerError


class CircuitBreaker(Generic[T]):
    """Closed/open/half-open state machine for one dependency key.

    Exactly one operation is admitted while half-open.  Concurrent callers are
    rejected until that recovery probe succeeds or fails, preventing a thundering
    herd when a dependency's reset timeout expires.

    The legacy ``provider_name``, ``threshold``, and ``reset_seconds`` keyword
    aliases make migration from the proven AI-provider breaker mechanical.
    """

    def __init__(
        self,
        dependency: Optional[str] = None,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        *,
        provider_name: Optional[str] = None,
        threshold: Optional[int] = None,
        reset_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        dependency_key = dependency if dependency is not None else provider_name
        if not isinstance(dependency_key, str) or not dependency_key.strip():
            raise ValueError("dependency must be a non-empty string")

        if threshold is not None:
            failure_threshold = threshold
        if reset_seconds is not None:
            reset_timeout = reset_seconds
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int):
            raise ValueError("failure_threshold must be a positive integer")
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be a positive integer")
        if isinstance(reset_timeout, bool) or not isinstance(reset_timeout, (int, float)):
            raise ValueError("reset_timeout must be a positive number")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be a positive number")

        self.dependency = dependency_key.strip()
        self.provider_name = self.dependency
        self.failure_threshold = failure_threshold
        self.threshold = failure_threshold
        self.reset_timeout = float(reset_timeout)
        self.reset_seconds = float(reset_timeout)
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_at: Optional[float] = None
        self._half_open_probe_active = False
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        """Return current state, promoting an expired open circuit."""

        with self._lock:
            self._promote_if_due(self._clock())
            return self._state

    @property
    def failure_count(self) -> int:
        """Return the number of consecutive failed logical operations."""

        with self._lock:
            return self._failure_count

    @property
    def reset_at(self) -> Optional[float]:
        """Return the monotonic deadline for an open circuit, if any."""

        with self._lock:
            if self._last_failure_at is None:
                return None
            return self._last_failure_at + self.reset_timeout

    def call(self, function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute ``function`` when the circuit admits an operation."""

        self._acquire_permission()
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            self.record_failure(exc)
            raise
        self.record_success()
        return result

    def record_success(self) -> None:
        """Close the circuit after a successful operation."""

        with self._lock:
            recovered = self._state == CircuitState.HALF_OPEN
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_at = None
            self._half_open_probe_active = False
        if recovered:
            logger.info("Circuit closed after dependency recovery: %s", self.dependency)

    def record_failure(self, error: Optional[BaseException] = None) -> None:
        """Record a failed operation and open the circuit when required."""

        with self._lock:
            was_half_open = self._state == CircuitState.HALF_OPEN
            self._failure_count += 1
            self._last_failure_at = self._clock()
            self._half_open_probe_active = False
            if was_half_open or self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit opened for dependency %s after %d failure(s): %s",
                    self.dependency,
                    self._failure_count,
                    error,
                )

    def reset(self) -> None:
        """Manually restore the initial closed state."""

        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_at = None
            self._half_open_probe_active = False
        logger.info("Circuit manually reset for dependency %s", self.dependency)

    def _acquire_permission(self) -> None:
        now = self._clock()
        with self._lock:
            self._promote_if_due(now)
            if self._state == CircuitState.OPEN:
                assert self._last_failure_at is not None
                raise CircuitBreakerError(
                    self.dependency,
                    self._last_failure_at + self.reset_timeout,
                )
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_probe_active:
                    # A recovery probe is already in flight. Use a fresh reset
                    # deadline in the exception so callers receive useful retry
                    # guidance without changing breaker state.
                    raise CircuitBreakerError(self.dependency, now + self.reset_timeout)
                self._half_open_probe_active = True

    def _promote_if_due(self, now: float) -> None:
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_at is not None
            and now - self._last_failure_at >= self.reset_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_probe_active = False
            logger.info("Circuit half-open for dependency %s", self.dependency)


class CircuitBreakerRegistry:
    """Thread-safe owner of one circuit breaker per dependency key."""

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int):
            raise ValueError("failure_threshold must be a positive integer")
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be a positive integer")
        if isinstance(reset_timeout, bool) or not isinstance(reset_timeout, (int, float)):
            raise ValueError("reset_timeout must be a positive number")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be a positive number")
        self._failure_threshold = failure_threshold
        self._reset_timeout = float(reset_timeout)
        self._clock = clock
        self._breakers: Dict[str, CircuitBreaker[Any]] = {}
        self._lock = threading.Lock()

    def get(self, dependency: str) -> CircuitBreaker[Any]:
        """Return the stable breaker associated with ``dependency``."""

        if not isinstance(dependency, str) or not dependency.strip():
            raise ValueError("dependency must be a non-empty string")
        key = dependency.strip()
        with self._lock:
            breaker = self._breakers.get(key)
            if breaker is None:
                breaker = CircuitBreaker(
                    key,
                    failure_threshold=self._failure_threshold,
                    reset_timeout=self._reset_timeout,
                    clock=self._clock,
                )
                self._breakers[key] = breaker
            return breaker

    def reset(self, dependency: Optional[str] = None) -> None:
        """Reset one breaker, or all currently materialized breakers."""

        with self._lock:
            breakers = (
                [self._breakers[dependency]]
                if dependency is not None and dependency in self._breakers
                else list(self._breakers.values()) if dependency is None else []
            )
        for breaker in breakers:
            breaker.reset()
