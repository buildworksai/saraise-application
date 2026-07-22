"""Provider-boundary resilience, SSRF, and correlation tests with zero real HTTP."""

from __future__ import annotations

import ipaddress
from uuid import uuid4

import httpx
import pytest
from django.core.exceptions import ValidationError

from src.core.middleware.correlation import HEADER_NAME
from src.core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError, CircuitState
from src.core.resilience.http import (
    DependencyResponseError,
    DependencyTimeoutError,
    ResilientHttpClient,
    UnsafeDestinationError,
)
from src.modules.ai_agent_management.providers.factory import ProviderFactory
from src.modules.ai_agent_management.providers.registry import ProviderRegistry
from src.modules.ai_agent_management.services import EgressService


def _client(monkeypatch, handler, **kwargs):
    monkeypatch.setattr(
        "src.core.resilience.http._resolved_addresses",
        lambda host, port: {ipaddress.ip_address("93.184.216.34")},
    )
    return ResilientHttpClient(
        {"provider": {"base_url": "https://provider.example/", "allowed_hosts": ["provider.example"]}},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda delay: None,
        jitter=lambda start, end: 0,
        **kwargs,
    )


def test_timeout_is_bounded_and_typed(monkeypatch):
    calls = 0

    def timeout(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("test timeout", request=request)

    client = _client(monkeypatch, timeout, max_retries=1)
    with pytest.raises(DependencyTimeoutError) as caught:
        client.get("/v1/models", dependency="provider")
    assert calls == 2
    assert caught.value.dependency == "provider"
    assert "test timeout" not in str(caught.value)


def test_retry_boundary_only_retries_idempotent_methods(monkeypatch):
    calls = []

    def unavailable(request):
        calls.append(request.method)
        return httpx.Response(503, request=request)

    client = _client(monkeypatch, unavailable, max_retries=2)
    with pytest.raises(DependencyResponseError):
        client.get("/v1/models", dependency="provider")
    assert calls == ["GET", "GET", "GET"]
    calls.clear()
    with pytest.raises(DependencyResponseError):
        client.post("/v1/completions", dependency="provider", json={})
    assert calls == ["POST"]


def test_circuit_open_half_open_and_recovery_are_deterministic():
    now = [100.0]
    breaker = CircuitBreaker("provider", failure_threshold=1, reset_timeout=10, clock=lambda: now[0])

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("dependency body")))
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitBreakerError):
        breaker.call(lambda: "must not run")

    now[0] = 111.0
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.call(lambda: "healthy") == "healthy"
    assert breaker.state is CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.parametrize(
    "destination",
    (
        "127.0.0.1",
        "127.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.100.100.200",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd00:ec2::254",
        "::ffff:127.0.0.1",
    ),
)
def test_egress_rejects_private_metadata_and_alternate_addresses(destination):
    with pytest.raises((ValueError, ValidationError)) as caught:
        EgressService.normalize("ip", destination)
    assert type(caught.value).__name__ in {"ValidationError", "AddressValueError"}


def test_resilient_client_rejects_metadata_and_unallowlisted_targets_before_transport(monkeypatch):
    transported = []

    def transport(request):
        transported.append(request.url)
        return httpx.Response(200, request=request)

    client = _client(monkeypatch, transport)
    for destination in (
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1",
        "https://attacker.example/redirect",
        "https://user:password@provider.example/path",
    ):
        with pytest.raises(UnsafeDestinationError):
            client.get(destination, dependency="provider")
    assert transported == []


def test_dns_rebinding_to_private_address_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "src.core.resilience.http._resolved_addresses",
        lambda host, port: {ipaddress.ip_address("93.184.216.34"), ipaddress.ip_address("127.0.0.1")},
    )
    client = ResilientHttpClient(
        {"provider": "provider.example"},
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))),
    )
    with pytest.raises(UnsafeDestinationError):
        client.get("https://provider.example/v1/models", dependency="provider")


def test_correlation_header_propagates_and_caller_cannot_override(monkeypatch):
    captured = {}

    def transport(request):
        captured.update(request.headers)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = _client(monkeypatch, transport)
    response = client.get(
        "/v1/models",
        dependency="provider",
        correlation_id="corr-authoritative",
        headers={HEADER_NAME: "spoofed"},
    )
    assert response.status_code == 200
    assert httpx.Headers(captured)[HEADER_NAME] == "corr-authoritative"


def test_invalid_or_cross_tenant_provider_payload_is_not_resolved():
    tenant_id = uuid4()
    provider_id = uuid4()
    registry = ProviderRegistry()
    invalid = ProviderFactory(
        lambda tenant, config: {"tenant_id": str(tenant), "adapter_key": "missing"},
        registry=registry,
    ).resolve(tenant_id, provider_id)
    assert invalid.status == "unavailable"
    assert invalid.http_status == 503

    cross_tenant = ProviderFactory(
        lambda tenant, config: {"tenant_id": str(uuid4()), "adapter_key": "missing"},
        registry=registry,
    ).resolve(tenant_id, provider_id)
    assert cross_tenant.status == "failed"
    assert cross_tenant.error_code == "PROVIDER_TENANT_MISMATCH"
    assert cross_tenant.http_status == 404
