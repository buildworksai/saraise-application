"""Readiness checks expose real state without tenant or secret leakage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone as django_timezone

from src.core.async_jobs.models import OutboxEvent
from src.modules.blockchain_traceability import health
from src.modules.blockchain_traceability.models import LedgerNetwork
from src.modules.blockchain_traceability.providers import (
    CapabilityMetadata,
    ProviderHealth,
    ledger_provider_registry,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


class HealthyLedgerAdapter:
    provider_type = "test-health-ledger"

    def __init__(self) -> None:
        self.calls = 0

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(key=self.provider_type, display_name="Test health ledger")

    def validate_options(self, options: object) -> None:
        assert isinstance(options, dict)

    def health(self, network: LedgerNetwork) -> ProviderHealth:
        self.calls += 1
        return ProviderHealth(
            available=True,
            code="ready",
            checked_at=datetime.now(timezone.utc),
            evidence={"circuit_state": "closed"},
        )


def _network(tenant_id, provider_type: str, *, secret_ref: str = "vault://opaque") -> LedgerNetwork:
    return LedgerNetwork.objects.create(
        tenant_id=tenant_id,
        network_key=f"network-{uuid4().hex[:8]}",
        name="Private configured network",
        provider_type=provider_type,
        dependency_key=f"traceability.{provider_type}",
        network_namespace="test",
        secret_ref=secret_ref,
        status="active",
        created_by="health-test",
    )


def test_database_check_executes_a_real_query() -> None:
    result = health._database_check()
    assert result["name"] == "database"
    assert result["status"] == "healthy"
    assert result["code"] == "ready"


def test_network_probe_is_tenant_selected_cached_and_sanitized(tenant_a, tenant_b) -> None:
    adapter = HealthyLedgerAdapter()
    ledger_provider_registry.register(adapter.provider_type, adapter)
    try:
        selected = _network(tenant_a.id, adapter.provider_type, secret_ref="vault://tenant-a-secret")
        other = _network(tenant_b.id, "unregistered-other", secret_ref="vault://tenant-b-secret")

        first = health._network_check(tenant_a.id)
        second = health._network_check(tenant_a.id)

        assert first == second
        assert first["status"] == "healthy"
        assert first["circuit_state"] == "closed"
        assert adapter.calls == 1
        rendered = repr(first)
        assert str(tenant_a.id) not in rendered
        assert str(tenant_b.id) not in rendered
        assert selected.secret_ref not in rendered
        assert other.secret_ref not in rendered
        assert selected.network_key not in rendered
        assert other.network_key not in rendered
    finally:
        ledger_provider_registry.unregister(adapter.provider_type)


def test_missing_active_network_is_degraded_not_fabricated_success(tenant_a) -> None:
    result = health._network_check(tenant_a.id)
    assert result["status"] == "degraded"
    assert result["code"] == "active_network_not_configured"


def test_outbox_age_metric_uses_only_oldest_pending_row_for_tenant(monkeypatch, tenant_a, tenant_b) -> None:
    observed: list[float] = []
    monkeypatch.setattr(health.metrics.OUTBOX_AGE, "set", observed.append)
    tenant_age = health.OUTBOX_FRESHNESS.total_seconds() + 10
    other_age = tenant_age * 10
    tenant_event = OutboxEvent.objects.create(
        tenant_id=tenant_a.id,
        aggregate_type="ledger_anchor",
        aggregate_id=uuid4(),
        event_type="blockchain_traceability.anchor.requested",
        payload={},
    )
    other_event = OutboxEvent.objects.create(
        tenant_id=tenant_b.id,
        aggregate_type="ledger_anchor",
        aggregate_id=uuid4(),
        event_type="blockchain_traceability.anchor.requested",
        payload={},
    )
    now = django_timezone.now()
    OutboxEvent.objects.filter(pk=tenant_event.pk).update(
        created_at=now - health.OUTBOX_FRESHNESS - timedelta(seconds=10)
    )
    OutboxEvent.objects.filter(pk=other_event.pk).update(created_at=now - timedelta(seconds=other_age))

    result = health._outbox_check(tenant_a.id)

    assert result["status"] == "unavailable"
    assert len(observed) == 1
    assert tenant_age <= observed[0] < tenant_age + 5
    assert observed[0] < other_age


def test_module_health_uses_503_only_for_required_dependency_failure(monkeypatch, tenant_a) -> None:
    def healthy(name: str) -> dict[str, object]:
        return {
            "name": name,
            "status": "healthy",
            "code": "ready",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    monkeypatch.setattr(health, "_database_check", lambda: healthy("database"))
    monkeypatch.setattr(health, "_cache_check", lambda tenant_id: healthy("cache"))
    monkeypatch.setattr(health, "_outbox_check", lambda tenant_id: healthy("async_outbox"))
    monkeypatch.setattr(health, "_adapter_check", lambda: healthy("adapters"))
    monkeypatch.setattr(
        health,
        "_network_check",
        lambda tenant_id: {
            **healthy("network"),
            "status": "degraded",
            "code": "active_network_not_configured",
        },
    )

    payload, status_code = health.module_health(tenant_a.id)
    assert status_code == 200
    assert payload["status"] == "degraded"

    monkeypatch.setattr(
        health,
        "_outbox_check",
        lambda tenant_id: {**healthy("async_outbox"), "status": "unavailable", "code": "stale"},
    )
    payload, status_code = health.module_health(tenant_a.id)
    assert status_code == 503
    assert payload["status"] == "unavailable"


def test_health_payload_never_contains_global_counts_or_exception_text(monkeypatch, tenant_a) -> None:
    monkeypatch.setattr(
        health, "connection", SimpleNamespace(cursor=lambda: (_ for _ in ()).throw(RuntimeError("dsn")))
    )
    payload, _ = health.module_health(tenant_a.id)
    rendered = repr(payload).lower()
    assert "count" not in rendered
    assert "total" not in rendered
    assert "dsn" not in rendered
    assert "traceback" not in rendered
    assert "secret" not in rendered
