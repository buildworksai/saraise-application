"""Bounded, observable resilience boundary for synchronous provider adapters."""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Callable, TypeVar
from uuid import UUID

from src.core.resilience import CircuitBreaker

from .base import LLMProvider
from ..services import AgentServiceError, ConfigurationService

logger = logging.getLogger("saraise.ai_agent_management.provider")
T = TypeVar("T")
_lock = threading.Lock()
_breakers: dict[tuple[str, int, float], CircuitBreaker[Any]] = {}


def _breaker(dependency: str, threshold: int, reset_seconds: float) -> CircuitBreaker[Any]:
    key = (dependency, threshold, reset_seconds)
    with _lock:
        value = _breakers.get(key)
        if value is None:
            value = CircuitBreaker(
                dependency,
                failure_threshold=threshold,
                reset_timeout=reset_seconds,
            )
            _breakers[key] = value
        return value


def resilient_provider_call(
    tenant_id: UUID,
    correlation_id: UUID,
    provider: LLMProvider,
    operation: Callable[[], T],
) -> T:
    """Execute a provider operation with tenant-configured timeout/retry/breaker policy."""

    policy = ConfigurationService.resolve(tenant_id)["provider"]
    timeout = float(policy["timeout_seconds"])
    retries = int(policy["max_retries"])
    backoff = float(policy["retry_backoff_seconds"])
    breaker = _breaker(
        provider.config.dependency_key,
        int(policy["circuit_failure_threshold"]),
        float(policy["circuit_reset_seconds"]),
    )
    for attempt in range(retries + 1):
        try:
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-provider")
            try:
                future = executor.submit(breaker.call, operation)
                result = future.result(timeout=timeout)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            logger.info(
                "provider_call",
                extra={
                    "event": "ai_provider_call",
                    "tenant_id": str(tenant_id),
                    "correlation_id": str(correlation_id),
                    "operation": "completion",
                    "outcome": "success",
                    "attempt": attempt + 1,
                    "circuit_state": breaker.state.value,
                },
            )
            return result
        except FutureTimeout as exc:
            breaker.record_failure(exc)
            error: Exception = AgentServiceError("PROVIDER_TIMEOUT", "The provider call exceeded its timeout.")
        except Exception as exc:
            error = exc
        logger.warning(
            "provider_call",
            extra={
                "event": "ai_provider_call",
                "tenant_id": str(tenant_id),
                "correlation_id": str(correlation_id),
                "operation": "completion",
                "outcome": "retry" if attempt < retries else "failure",
                "attempt": attempt + 1,
                "circuit_state": breaker.state.value,
            },
        )
        if attempt >= retries:
            raise error
        time.sleep(backoff * (2**attempt) + random.uniform(0, backoff))
    raise AssertionError("Provider retry loop terminated without an outcome")
