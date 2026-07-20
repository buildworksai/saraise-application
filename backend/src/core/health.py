"""Application liveness and dependency readiness primitives.

Liveness answers only whether this Django process can serve a response.
Readiness is intentionally fail-closed: at least one critical component must
register a fresh, successful probe before the application is considered ready.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

from django.http import HttpRequest, JsonResponse
from django.utils import timezone

logger = logging.getLogger("saraise.health")


@dataclass(frozen=True)
class HealthCheckResult:
    """Structured output returned by a component probe."""

    healthy: bool
    message: str = ""
    checked_at: datetime = field(default_factory=timezone.now)
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def last_checked_at(self) -> datetime:
        """Readable alias used by adapters around cached dependency checks."""

        return self.checked_at


# A concise alias for component implementations.
ProbeResult = HealthCheckResult
ProbeOutput = Union[HealthCheckResult, bool, Tuple[bool, str], Mapping[str, Any]]
Probe = Callable[[], ProbeOutput]


@dataclass(frozen=True)
class _RegisteredProbe:
    name: str
    probe: Probe
    critical: bool
    staleness_limit: timedelta


@dataclass(frozen=True)
class ReadinessReport:
    """Stable result object for views, tests, metrics, and orchestration."""

    ready: bool
    checked_at: datetime
    components: Mapping[str, Mapping[str, Any]]
    reason: str = ""

    @property
    def status_code(self) -> int:
        return 200 if self.ready else 503

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": "ready" if self.ready else "not_ready",
            "checked_at": self.checked_at.isoformat(),
            "components": dict(self.components),
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


class HealthRegistry:
    """Thread-safe registry of component probes and readiness policy."""

    def __init__(self, *, clock: Callable[[], datetime] = timezone.now) -> None:
        self._clock = clock
        self._probes: Dict[str, _RegisteredProbe] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        probe: Optional[Probe] = None,
        *,
        critical: bool = True,
        staleness_limit: Union[float, timedelta] = 30.0,
        replace: bool = False,
    ) -> Union[Probe, Callable[[Probe], Probe]]:
        """Register a probe directly or as a decorator.

        Duplicate component names are rejected unless ``replace=True`` is
        explicit, preventing one module from silently weakening another's
        readiness contract.
        """

        if not isinstance(name, str) or not name.strip():
            raise ValueError("health probe name must be a non-empty string")
        if not isinstance(critical, bool):
            raise ValueError("critical must be a boolean")
        limit = self._normalize_staleness_limit(staleness_limit)
        canonical_name = name.strip()

        def decorator(function: Probe) -> Probe:
            if not callable(function):
                raise ValueError("health probe must be callable")
            registration = _RegisteredProbe(
                name=canonical_name,
                probe=function,
                critical=critical,
                staleness_limit=limit,
            )
            with self._lock:
                if canonical_name in self._probes and not replace:
                    raise ValueError(f"health probe '{canonical_name}' is already registered")
                self._probes[canonical_name] = registration
            return function

        if probe is None:
            return decorator
        return decorator(probe)

    def unregister(self, name: str) -> bool:
        """Remove a component probe, returning whether it existed."""

        with self._lock:
            return self._probes.pop(name, None) is not None

    def clear(self) -> None:
        """Remove all probes, primarily for controlled shutdown and tests."""

        with self._lock:
            self._probes.clear()

    def check_readiness(self) -> ReadinessReport:
        """Execute critical probes and produce a fail-closed readiness report."""

        with self._lock:
            critical_probes = tuple(registration for registration in self._probes.values() if registration.critical)
        checked_at = self._aware(self._clock())
        if not critical_probes:
            return ReadinessReport(
                ready=False,
                checked_at=checked_at,
                components={},
                reason="no critical health probes registered",
            )

        components: Dict[str, Mapping[str, Any]] = {}
        ready = True
        for registration in critical_probes:
            component = self._run_probe(registration)
            components[registration.name] = component
            if component["status"] != "healthy":
                ready = False

        return ReadinessReport(
            ready=ready,
            checked_at=self._aware(self._clock()),
            components=components,
            reason="" if ready else "one or more critical health probes are not ready",
        )

    # Naming aliases make the registry natural in both service and view code.
    readiness = check_readiness
    run_checks = check_readiness

    @staticmethod
    def _normalize_staleness_limit(value: Union[float, timedelta]) -> timedelta:
        if isinstance(value, timedelta):
            limit = value
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("staleness_limit must be a positive number of seconds or timedelta")
        else:
            limit = timedelta(seconds=float(value))
        if limit.total_seconds() <= 0:
            raise ValueError("staleness_limit must be greater than zero")
        return limit

    def _run_probe(self, registration: _RegisteredProbe) -> Mapping[str, Any]:
        started = time.monotonic()
        try:
            raw_result = registration.probe()
            now = self._aware(self._clock())
            result = self._normalize_result(raw_result, now)
        except Exception as exc:
            now = self._aware(self._clock())
            logger.exception("Critical health probe failed: %s", registration.name)
            return {
                "status": "unhealthy",
                "critical": True,
                "stale": False,
                "message": f"probe raised {type(exc).__name__}",
                "checked_at": now.isoformat(),
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "details": {},
            }

        probe_checked_at = self._aware(result.checked_at)
        # Future timestamps are invalid rather than accepted as perpetually fresh.
        invalid_future_timestamp = probe_checked_at > now + timedelta(seconds=1)
        stale = invalid_future_timestamp or now - probe_checked_at > registration.staleness_limit
        healthy = bool(result.healthy) and not stale
        message = result.message
        if invalid_future_timestamp:
            message = message or "probe timestamp is in the future"
        elif stale:
            message = message or "probe result is stale"
        return {
            "status": "healthy" if healthy else "unhealthy",
            "critical": True,
            "stale": stale,
            "message": message,
            "checked_at": probe_checked_at.isoformat(),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "details": dict(result.details),
        }

    @staticmethod
    def _normalize_result(raw_result: ProbeOutput, now: datetime) -> HealthCheckResult:
        if isinstance(raw_result, HealthCheckResult):
            return raw_result
        if isinstance(raw_result, bool):
            return HealthCheckResult(healthy=raw_result, checked_at=now)
        if isinstance(raw_result, tuple) and len(raw_result) == 2:
            healthy, message = raw_result
            if not isinstance(healthy, bool) or not isinstance(message, str):
                raise TypeError("probe tuple must contain (bool, str)")
            return HealthCheckResult(healthy=healthy, message=message, checked_at=now)
        if isinstance(raw_result, Mapping):
            healthy_value = raw_result.get("healthy")
            if healthy_value is None and "status" in raw_result:
                healthy_value = str(raw_result["status"]).lower() in {"healthy", "ok", "pass", "ready"}
            if not isinstance(healthy_value, bool):
                raise TypeError("probe mapping must contain boolean 'healthy' or a recognized status")
            checked_at = raw_result.get("checked_at", raw_result.get("last_checked_at", now))
            if isinstance(checked_at, str):
                checked_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            if not isinstance(checked_at, datetime):
                raise TypeError("probe checked_at must be a datetime or ISO-8601 string")
            message = raw_result.get("message", "")
            details = raw_result.get("details", {})
            if not isinstance(message, str) or not isinstance(details, Mapping):
                raise TypeError("probe message must be a string and details must be a mapping")
            return HealthCheckResult(
                healthy=healthy_value,
                message=message,
                checked_at=checked_at,
                details=details,
            )
        raise TypeError("probe must return HealthCheckResult, bool, (bool, str), or mapping")

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("health clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=datetime_timezone.utc)
        return value


health_registry = HealthRegistry()


def health_live(request: HttpRequest) -> JsonResponse:
    """Process-only liveness; dependency state never affects this response."""

    del request
    return JsonResponse({"status": "alive"}, status=200)


def health_ready(request: HttpRequest) -> JsonResponse:
    """Return current critical dependency readiness."""

    del request
    report = health_registry.check_readiness()
    return JsonResponse(report.as_dict(), status=report.status_code)


def health(request: HttpRequest) -> JsonResponse:
    """Backward-compatible alias whose semantics are readiness, not liveness."""

    return health_ready(request)


__all__ = [
    "HealthCheckResult",
    "HealthRegistry",
    "ProbeResult",
    "ReadinessReport",
    "health",
    "health_live",
    "health_ready",
    "health_registry",
]
