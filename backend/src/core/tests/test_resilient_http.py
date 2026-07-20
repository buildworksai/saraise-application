"""Security and fault-isolation tests for resilient outbound HTTP."""

import ipaddress
import socket
from concurrent.futures import TimeoutError as FutureTimeoutError
from unittest.mock import Mock

import httpcore
import httpx
import pytest

from src.core.resilience.circuit_breaker import CircuitBreakerError, CircuitState
from src.core.resilience.http import (
    DependencyConnectionError,
    DependencyNotAllowedError,
    DependencyResponseError,
    DependencyTimeoutError,
    HttpClientConfigurationError,
    ResilientHttpClient,
    UnsafeDestinationError,
    _mapped_httpx_exception,
    _PinnedHTTPTransport,
    _PinnedNetworkBackend,
    _resolved_addresses,
)


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.core.resilience.http._resolved_addresses",
        lambda host, port: {ipaddress.ip_address("93.184.216.34")},
    )


def test_missing_or_empty_allowlist_fails_closed(settings) -> None:
    settings.SARAISE_HTTP_DEPENDENCIES = None
    with pytest.raises(HttpClientConfigurationError):
        ResilientHttpClient()
    with pytest.raises(HttpClientConfigurationError):
        ResilientHttpClient({})


def test_django_setting_configuration_and_malformed_policies_fail_closed(settings, public_dns) -> None:
    settings.SARAISE_HTTP_DEPENDENCIES = {"catalog": ["api.example.com"]}
    client = ResilientHttpClient(max_retries=0, transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    try:
        assert client.get("https://api.example.com/health", dependency="catalog").status_code == 204
    finally:
        client.close()

    for malformed in (
        {"catalog": []},
        {"catalog": {}},
        {"catalog": {"base_url": "ftp://api.example.com"}},
        {"catalog": {"base_url": "https://api.example.com", "allowed_hosts": ["other.example.com"]}},
    ):
        with pytest.raises(HttpClientConfigurationError):
            ResilientHttpClient(malformed)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connect_timeout": 0},
        {"read_timeout": True},
        {"max_retries": -1},
        {"retry_backoff": -0.1},
        {"failure_threshold": 0},
        {"reset_timeout": 0},
    ],
)
def test_invalid_transport_configuration_is_rejected(kwargs: dict) -> None:
    with pytest.raises(HttpClientConfigurationError):
        ResilientHttpClient({"catalog": "api.example.com"}, **kwargs)


def test_client_and_transport_cannot_both_be_supplied() -> None:
    injected = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    try:
        with pytest.raises(HttpClientConfigurationError, match="client or transport"):
            ResilientHttpClient(
                {"catalog": "api.example.com"},
                client=injected,
                transport=httpx.MockTransport(lambda request: httpx.Response(200)),
            )
    finally:
        injected.close()


def test_dependency_and_host_allowlists_are_enforced_before_transport(public_dns) -> None:
    client = ResilientHttpClient({"catalog": "api.example.com"}, max_retries=0)
    try:
        with pytest.raises(DependencyNotAllowedError):
            client.get("https://api.example.com/items", dependency="billing")
        with pytest.raises(UnsafeDestinationError, match="not allowlisted"):
            client.get("https://attacker.example/items", dependency="catalog")
    finally:
        client.close()


@pytest.mark.parametrize(
    ("host", "address"),
    [
        ("private.example", "10.0.0.4"),
        ("loopback.example", "127.0.0.1"),
        ("link-local.example", "169.254.169.254"),
        ("ipv6-private.example", "fd00::1"),
    ],
)
def test_private_loopback_link_local_and_metadata_addresses_are_blocked(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
    address: str,
) -> None:
    monkeypatch.setattr(
        "src.core.resilience.http._resolved_addresses",
        lambda resolved_host, port: {ipaddress.ip_address(address)},
    )
    client = ResilientHttpClient({"dependency": host}, max_retries=0)
    try:
        with pytest.raises(UnsafeDestinationError, match="internal or non-routable"):
            client.get(f"https://{host}/health", dependency="dependency")
    finally:
        client.close()


def test_metadata_hostname_is_blocked_even_before_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver_called = False

    def resolver(host: str, port: int):
        nonlocal resolver_called
        resolver_called = True
        return {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr("src.core.resilience.http._resolved_addresses", resolver)
    client = ResilientHttpClient({"metadata": "metadata.google.internal"})
    try:
        with pytest.raises(UnsafeDestinationError, match="metadata service"):
            client.get("http://metadata.google.internal/computeMetadata/v1/", dependency="metadata")
        assert resolver_called is False
    finally:
        client.close()


@pytest.mark.parametrize(
    "url",
    [
        "relative/without-base",
        "ftp://api.example.com/items",
        "https://user:password@api.example.com/items",
        "https://api.example.com:invalid/items",
        " https://api.example.com/items",
    ],
)
def test_malformed_or_unsafe_urls_are_rejected(public_dns, url: str) -> None:
    client = ResilientHttpClient({"catalog": "api.example.com"})
    try:
        with pytest.raises(UnsafeDestinationError):
            client.get(url, dependency="catalog")
    finally:
        client.close()


def test_unresolved_allowlisted_host_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.core.resilience.http._resolved_addresses", lambda host, port: set())
    client = ResilientHttpClient({"catalog": "api.example.com"}, failure_threshold=1)
    try:
        with pytest.raises(DependencyConnectionError, match="could not be resolved"):
            client.get("https://api.example.com/items", dependency="catalog")
        with pytest.raises(CircuitBreakerError):
            client.get("https://api.example.com/items", dependency="catalog")
    finally:
        client.close()


def test_per_request_timeout_cannot_disable_configured_limits(public_dns) -> None:
    client = ResilientHttpClient({"catalog": "api.example.com"})
    try:
        with pytest.raises(HttpClientConfigurationError, match="timeout overrides"):
            client.get("https://api.example.com/items", dependency="catalog", timeout=None)
    finally:
        client.close()


def test_dns_resolution_collects_valid_records_and_ignores_malformed_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-address", 443)),
        ],
    )
    assert _resolved_addresses("api.example.com", 443) == {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: (_ for _ in ()).throw(socket.gaierror()))
    assert _resolved_addresses("missing.example", 443) == set()


def test_pinning_backend_connects_to_validated_ip_not_hostname() -> None:
    backend = _PinnedNetworkBackend()
    backend._delegate = Mock()
    stream = Mock(spec=httpcore.NetworkStream)
    backend._delegate.connect_tcp.return_value = stream
    backend.pin("api.example.com", {ipaddress.ip_address("93.184.216.34")})

    assert backend.connect_tcp("api.example.com", 443, timeout=2) is stream
    backend._delegate.connect_tcp.assert_called_once_with(
        "93.184.216.34",
        443,
        timeout=2,
        local_address=None,
        socket_options=None,
    )
    with pytest.raises(httpcore.ConnectError, match="No validated address"):
        backend.connect_tcp("unvalidated.example", 443)


def test_pinned_transport_preserves_origin_for_http_and_tls_layers() -> None:
    backend = _PinnedNetworkBackend()
    transport = _PinnedHTTPTransport(backend)
    transport._pool.close()
    transport._pool = Mock()
    transport._pool.handle_request.return_value = httpcore.Response(
        status=200,
        headers=[(b"content-type", b"text/plain")],
        content=b"healthy",
    )
    request = httpx.Request("GET", "https://api.example.com/health")

    response = transport.handle_request(request)

    core_request = transport._pool.handle_request.call_args.args[0]
    assert core_request.url.host == b"api.example.com"
    assert response.status_code == 200
    assert response.read() == b"healthy"
    transport.close()


def test_httpcore_transport_errors_are_translated_to_typed_httpx_errors() -> None:
    request = httpx.Request("GET", "https://api.example.com/health")
    mapped = _mapped_httpx_exception(httpcore.ConnectTimeout("timed out"), request)
    assert isinstance(mapped, httpx.ConnectTimeout)
    assert mapped.request is request


def test_dns_resolution_honors_connect_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class TimedOutFuture:
        def result(self, timeout: float):
            raise FutureTimeoutError()

        def cancel(self) -> bool:
            return True

    monkeypatch.setattr(
        "src.core.resilience.http._DNS_EXECUTOR.submit",
        lambda function, host, port: TimedOutFuture(),
    )
    client = ResilientHttpClient(
        {"catalog": "api.example.com"},
        connect_timeout=0.01,
        failure_threshold=1,
        transport=httpx.MockTransport(lambda request: httpx.Response(200)),
    )
    try:
        with pytest.raises(DependencyTimeoutError, match="DNS resolution"):
            client.get("https://api.example.com/items", dependency="catalog")
        assert client.get_breaker("catalog").state == CircuitState.OPEN
    finally:
        client.close()


def test_timeout_is_retried_for_get_and_raised_as_typed_failure(public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow dependency", request=request)

    client = ResilientHttpClient(
        {"catalog": "api.example.com"},
        max_retries=1,
        retry_backoff=0,
        transport=httpx.MockTransport(handler),
        sleep=lambda delay: None,
    )
    try:
        with pytest.raises(DependencyTimeoutError):
            client.get("https://api.example.com/items", dependency="catalog")
        assert calls == 2
    finally:
        client.close()


def test_post_is_never_retried(public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    client = ResilientHttpClient(
        {"catalog": "api.example.com"},
        max_retries=3,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(DependencyConnectionError):
            client.post("https://api.example.com/items", dependency="catalog", json={"name": "one"})
        assert calls == 1
    finally:
        client.close()


def test_breaker_opens_per_dependency_and_short_circuits_transport(public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("offline", request=request)

    client = ResilientHttpClient(
        {"catalog": "api.example.com", "billing": "billing.example.com"},
        failure_threshold=1,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(DependencyConnectionError):
            client.get("https://api.example.com/items", dependency="catalog")
        assert client.get_breaker("catalog").state == CircuitState.OPEN
        assert client.get_breaker("billing").state == CircuitState.CLOSED

        with pytest.raises(CircuitBreakerError):
            client.get("https://api.example.com/items", dependency="catalog")
        assert calls == 1
    finally:
        client.close()


def test_correlation_id_is_propagated_and_relative_base_url_is_supported(public_dns) -> None:
    observed_request = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_request
        observed_request = request
        return httpx.Response(200, json={"ok": True})

    client = ResilientHttpClient(
        {"catalog": {"base_url": "https://api.example.com/v1"}},
        transport=httpx.MockTransport(handler),
    )
    try:
        response = client.get(
            "items",
            dependency="catalog",
            correlation_id="req_test123456",
            headers={"x-correlation-id": "spoofed-value"},
        )
        assert response.status_code == 200
        assert observed_request.url == httpx.URL("https://api.example.com/v1/items")
        assert observed_request.headers["X-Correlation-ID"] == "req_test123456"
    finally:
        client.close()


def test_retryable_upstream_status_raises_after_retries(public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, request=request)

    client = ResilientHttpClient(
        {"catalog": "api.example.com"},
        max_retries=1,
        retry_backoff=0,
        transport=httpx.MockTransport(handler),
        sleep=lambda delay: None,
    )
    try:
        with pytest.raises(DependencyResponseError) as exc_info:
            client.get("https://api.example.com/items", dependency="catalog")
        assert exc_info.value.status_code == 503
        assert calls == 2
    finally:
        client.close()


def test_server_error_is_a_dependency_failure_even_for_non_idempotent_calls(public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, request=request)

    client = ResilientHttpClient(
        {"catalog": "api.example.com"},
        max_retries=3,
        failure_threshold=1,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(DependencyResponseError) as exc_info:
            client.post("https://api.example.com/items", dependency="catalog", json={"name": "one"})
        assert exc_info.value.status_code == 500
        assert calls == 1
        assert client.get_breaker("catalog").state == CircuitState.OPEN
    finally:
        client.close()


def test_transport_failure_can_recover_on_an_idempotent_retry(public_dns) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("transient", request=request)
        return httpx.Response(200, request=request)

    with ResilientHttpClient(
        {"catalog": "api.example.com"},
        max_retries=1,
        retry_backoff=0,
        transport=httpx.MockTransport(handler),
        sleep=lambda delay: None,
    ) as client:
        assert client.get("https://api.example.com/items", dependency="catalog").status_code == 200
    assert calls == 2


@pytest.mark.parametrize("method", ["head", "options", "put", "patch", "delete"])
def test_convenience_methods_delegate_without_redirects(public_dns, method: str) -> None:
    observed_method = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_method
        observed_method = request.method
        return httpx.Response(200, request=request)

    client = ResilientHttpClient(
        {"catalog": "api.example.com"},
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        response = getattr(client, method)("https://api.example.com/items", dependency="catalog")
        assert response.status_code == 200
        assert observed_method == method.upper()
    finally:
        client.close()
