"""Tenant-aware, sanitized readiness checks for traceability dependencies."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from src.core.async_jobs.models import OutboxEvent, OutboxStatus

from . import metrics
from .models import LedgerNetwork
from .providers import (
    AdapterNotRegisteredError,
    get_ledger_provider,
    ledger_provider_registry,
    list_provider_capabilities,
)
from .services import DEFAULT_CONFIGURATION

PROBE_TTL_SECONDS = int(DEFAULT_CONFIGURATION["health_policy"]["provider_probe_cache_ttl_seconds"])
OUTBOX_FRESHNESS = timedelta(seconds=int(DEFAULT_CONFIGURATION["health_policy"]["outbox_freshness_seconds"]))


def _health_policy(tenant_id: UUID) -> Mapping[str, object]:
    from .services import BlockchainTraceabilityConfigurationService

    return BlockchainTraceabilityConfigurationService().document(tenant_id)["health_policy"]


def _now() -> str:
    return timezone.now().isoformat()


def _dependency(name: str, status: str, code: str, *, circuit_state: str | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "name": name,
        "status": status,
        "code": code,
        "checked_at": _now(),
    }
    if circuit_state is not None:
        value["circuit_state"] = circuit_state
    return value


def _database_check() -> dict[str, object]:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            ready = cursor.fetchone() == (1,)
        return _dependency("database", "healthy" if ready else "unavailable", "ready" if ready else "query_failed")
    except Exception:
        return _dependency("database", "unavailable", "dependency_unavailable")


def _cache_check(tenant_id: UUID) -> dict[str, object]:
    key = f"blockchain_traceability:health:cache:{tenant_id}"
    try:
        marker = _now()
        cache.set(key, marker, timeout=int(_health_policy(tenant_id)["cache_marker_ttl_seconds"]))
        ready = cache.get(key) == marker
        return _dependency("cache", "healthy" if ready else "unavailable", "ready" if ready else "roundtrip_failed")
    except Exception:
        return _dependency("cache", "unavailable", "dependency_unavailable")


def _outbox_check(tenant_id: UUID) -> dict[str, object]:
    """Inspect only this tenant's pending publications and expose no counts."""

    try:
        checked_at = timezone.now()
        oldest_created_at = (
            OutboxEvent.objects.filter(
                tenant_id=tenant_id,
                status=OutboxStatus.PENDING,
            )
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        age_seconds = (
            max(0.0, (checked_at - oldest_created_at).total_seconds()) if oldest_created_at is not None else 0.0
        )
        metrics.OUTBOX_AGE.set(age_seconds)
        freshness_seconds = int(_health_policy(tenant_id)["outbox_freshness_seconds"])
        stale = oldest_created_at is not None and (checked_at - oldest_created_at).total_seconds() > freshness_seconds
        return _dependency(
            "async_outbox",
            "unavailable" if stale else "healthy",
            "stale_pending_evidence" if stale else "fresh",
        )
    except Exception:
        return _dependency("async_outbox", "unavailable", "dependency_unavailable")


def _adapter_check() -> dict[str, object]:
    try:
        capabilities = list_provider_capabilities()
        ledger_keys = ledger_provider_registry.keys()
        descriptors_valid = all(isinstance(items, tuple) for items in capabilities.values())
        if not descriptors_valid:
            return _dependency("adapters", "unavailable", "invalid_registry")
        if not ledger_keys:
            # Local hash chains remain usable without a ledger connector.
            return _dependency("adapters", "degraded", "ledger_provider_not_configured")
        return _dependency("adapters", "healthy", "registered")
    except Exception:
        return _dependency("adapters", "unavailable", "registry_unavailable")


def _breaker_state(adapter: object, dependency_key: str, evidence: Mapping[str, object]) -> str:
    candidate = evidence.get("circuit_state")
    if isinstance(candidate, str) and candidate in {"closed", "open", "half_open"}:
        return candidate
    for attribute in ("client", "_client"):
        client = getattr(adapter, attribute, None)
        get_breaker = getattr(client, "get_breaker", None)
        if callable(get_breaker):
            try:
                state = getattr(get_breaker(dependency_key), "state", None)
                value = getattr(state, "value", state)
                if value in {"closed", "open", "half_open"}:
                    return str(value)
            except Exception:
                return "not_applicable"
    return "not_applicable"


def _network_check(tenant_id: UUID) -> dict[str, object]:
    """Probe the deterministic active default, caching evidence for 30 seconds."""

    try:
        network = (
            LedgerNetwork.objects.filter(tenant_id=tenant_id, status="active", is_deleted=False)
            .order_by("network_key", "id")
            .first()
        )
    except Exception:
        return _dependency("network", "unavailable", "configuration_unavailable", circuit_state="not_applicable")
    if network is None:
        return _dependency("network", "degraded", "active_network_not_configured", circuit_state="not_applicable")

    cache_key = f"blockchain_traceability:health:network:{tenant_id}:{network.id}"
    try:
        cached = cache.get(cache_key)
    except Exception:
        cached = None
    if isinstance(cached, Mapping):
        allowed = {"name", "status", "code", "checked_at", "circuit_state"}
        if set(cached).issubset(allowed):
            return dict(cached)

    try:
        adapter = get_ledger_provider(network.provider_type)
        from .services import execute_resilient_provider_call

        provider_health = execute_resilient_provider_call(
            tenant_id, "health_network_probe", lambda: adapter.health(network)
        )
        evidence = provider_health.evidence if isinstance(provider_health.evidence, Mapping) else {}
        circuit_state = _breaker_state(adapter, network.dependency_key, evidence)
        available = bool(provider_health.available)
        simulated = bool(provider_health.simulated)
        result = _dependency(
            "network",
            "degraded" if simulated else "healthy" if available else "unavailable",
            "simulated_provider" if simulated else str(provider_health.code or "unknown"),
            circuit_state=circuit_state,
        )
    except AdapterNotRegisteredError:
        result = _dependency("network", "unavailable", "provider_not_registered", circuit_state="not_applicable")
    except Exception:
        result = _dependency("network", "unavailable", "provider_unavailable", circuit_state="unknown")

    try:
        cache.set(
            cache_key,
            result,
            timeout=int(_health_policy(tenant_id)["provider_probe_cache_ttl_seconds"]),
        )
    except Exception:
        pass
    return result


def module_health(tenant_id: UUID) -> tuple[dict[str, object], int]:
    """Return real checks without tenant data, row counts, secrets, or traces."""

    dependencies = [
        _database_check(),
        _cache_check(tenant_id),
        _outbox_check(tenant_id),
        _adapter_check(),
        _network_check(tenant_id),
    ]
    required_unavailable = any(
        item["status"] == "unavailable"
        for item in dependencies
        if item["name"] in {"database", "cache", "async_outbox"}
    )
    degraded = any(item["status"] != "healthy" for item in dependencies)
    overall = "unavailable" if required_unavailable else "degraded" if degraded else "healthy"
    return (
        {"status": overall, "checked_at": _now(), "dependencies": dependencies},
        status_code_for(overall),
    )


def status_code_for(status_value: str) -> int:
    return 503 if status_value == "unavailable" else 200


__all__ = ["PROBE_TTL_SECONDS", "module_health", "status_code_for"]
