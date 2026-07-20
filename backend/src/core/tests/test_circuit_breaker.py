"""State-machine tests for the shared dependency circuit breaker."""

import pytest

from src.core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerError,
    CircuitBreakerRegistry,
    CircuitState,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _raise_failure() -> None:
    raise RuntimeError("dependency unavailable")


def test_breaker_opens_at_threshold_and_rejects_calls() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("catalog", failure_threshold=2, reset_timeout=10, clock=clock)

    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)
    assert breaker.state == CircuitState.OPEN
    assert breaker.failure_count == 2

    called = False

    def should_not_run() -> None:
        nonlocal called
        called = True

    with pytest.raises(CircuitBreakerError) as exc_info:
        breaker.call(should_not_run)
    assert exc_info.value.dependency == "catalog"
    assert exc_info.value.provider == "catalog"
    assert called is False


def test_half_open_success_closes_and_resets_failures() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("catalog", failure_threshold=1, reset_timeout=10, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)

    clock.advance(10)
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.call(lambda: "recovered") == "recovered"
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0
    assert breaker.reset_at is None


def test_half_open_failure_reopens_for_a_full_timeout() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker("catalog", failure_threshold=1, reset_timeout=10, clock=clock)
    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)

    clock.advance(10)
    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)
    assert breaker.state == CircuitState.OPEN
    assert breaker.reset_at == 120.0

    clock.advance(9.9)
    assert breaker.state == CircuitState.OPEN
    clock.advance(0.1)
    assert breaker.state == CircuitState.HALF_OPEN


def test_success_in_closed_state_and_manual_reset_clear_failures() -> None:
    breaker = CircuitBreaker(provider_name="legacy-provider", threshold=2, reset_seconds=30)
    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)
    assert breaker.call(lambda value: value + 1, 2) == 3
    assert breaker.failure_count == 0

    with pytest.raises(RuntimeError):
        breaker.call(_raise_failure)
    breaker.reset()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"dependency": ""}, "dependency"),
        ({"dependency": "x", "failure_threshold": 0}, "failure_threshold"),
        ({"dependency": "x", "reset_timeout": 0}, "reset_timeout"),
    ],
)
def test_invalid_breaker_configuration_is_rejected(kwargs: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CircuitBreaker(**kwargs)


def test_registry_keys_breakers_by_dependency_and_can_reset_them() -> None:
    registry = CircuitBreakerRegistry(failure_threshold=1, reset_timeout=30)
    catalog = registry.get("catalog")
    assert registry.get("catalog") is catalog
    billing = registry.get("billing")
    with pytest.raises(RuntimeError):
        catalog.call(_raise_failure)
    with pytest.raises(RuntimeError):
        billing.call(_raise_failure)

    registry.reset("catalog")
    assert catalog.state == CircuitState.CLOSED
    assert billing.state == CircuitState.OPEN
    registry.reset()
    assert billing.state == CircuitState.CLOSED
    registry.reset("not-materialized")

    with pytest.raises(ValueError, match="dependency"):
        registry.get(" ")
