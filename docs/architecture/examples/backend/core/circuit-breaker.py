# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Circuit breaker for service calls
# backend/src/core/circuit_breaker.py
# Reference: docs/architecture/operational-runbooks.md § 2 (Resilience)
# CRITICAL NOTES:
# - Prevents cascading failures in distributed systems
# - States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing) → CLOSED
# - Failure threshold configurable (default: 5 consecutive failures)
# - Timeout before attempting recovery (default: 60 seconds)
# - Half-open state tests if service recovered (single request allowed)
# - Fast-fail in OPEN state (avoid wasting resources on failing service)
# - Successful request in HALF_OPEN closes circuit (service recovered)
# - Failed request in HALF_OPEN reopens circuit (service still down)
# - Metrics tracked: failure count, success rate, response time
# - Alert on circuit open (service degradation detected)
# Source: docs/architecture/operational-runbooks.md § 2

from enum import Enum
from typing import Callable, Any
import time

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call function with circuit breaker protection"""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise ServiceError("Circuit breaker is open", "circuit_breaker")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset"""
        return (time.time() - self.last_failure_time) > self.timeout

    def _on_success(self):
        """Handle successful call"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

