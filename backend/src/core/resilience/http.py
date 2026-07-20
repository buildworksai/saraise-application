"""Fail-closed, SSRF-resistant HTTP client for declared dependencies."""

from __future__ import annotations

import ipaddress
import logging
import random
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, FrozenSet, Iterable, Iterator, Mapping, Optional, Set, Union, cast
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
from django.conf import settings

from src.core.middleware.correlation import HEADER_NAME, get_correlation_id

from .circuit_breaker import CircuitBreaker, CircuitBreakerRegistry, CircuitState

logger = logging.getLogger("saraise.resilience.http")

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IDEMPOTENT_METHODS: FrozenSet[str] = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
RETRYABLE_STATUS_CODES: FrozenSet[int] = frozenset({408, 429})
_METADATA_HOSTS = frozenset(
    {
        "instance-data",
        "instance-data.ec2.internal",
        "metadata",
        "metadata.google.internal",
    }
)
_METADATA_ADDRESSES = frozenset(
    {
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)
_DNS_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="saraise-dns")


def _mapped_httpx_exception(exc: Exception, request: httpx.Request) -> httpx.TransportError:
    mappings = (
        (httpcore.ConnectTimeout, httpx.ConnectTimeout),
        (httpcore.ReadTimeout, httpx.ReadTimeout),
        (httpcore.WriteTimeout, httpx.WriteTimeout),
        (httpcore.PoolTimeout, httpx.PoolTimeout),
        (httpcore.ConnectError, httpx.ConnectError),
        (httpcore.ReadError, httpx.ReadError),
        (httpcore.WriteError, httpx.WriteError),
        (httpcore.ProxyError, httpx.ProxyError),
        (httpcore.ProtocolError, httpx.ProtocolError),
    )
    for source, target in mappings:
        if isinstance(exc, source):
            return target(str(exc), request=request)
    return httpx.TransportError(str(exc), request=request)


@contextmanager
def _map_httpcore_exceptions(request: httpx.Request) -> Iterator[None]:
    try:
        yield
    except (httpcore.TimeoutException, httpcore.NetworkError, httpcore.ProxyError, httpcore.ProtocolError) as exc:
        raise _mapped_httpx_exception(exc, request) from exc


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes], request: httpx.Request) -> None:
        self._stream = stream
        self._request = request

    def __iter__(self) -> Iterator[bytes]:
        with _map_httpcore_exceptions(self._request):
            yield from self._stream

    def close(self) -> None:
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """Connect to prevalidated IPs while preserving hostname-based TLS SNI."""

    def __init__(self) -> None:
        self._delegate = httpcore.SyncBackend()
        self._addresses: Dict[str, TupleOfAddresses] = {}
        self._lock = threading.RLock()

    def pin(self, host: str, addresses: Set[IPAddress]) -> None:
        ordered = tuple(sorted((str(address) for address in addresses), key=lambda value: (":" in value, value)))
        with self._lock:
            self._addresses[_normalize_host(host)] = ordered

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.NetworkStream:
        with self._lock:
            addresses = self._addresses.get(_normalize_host(host))
        if not addresses:
            raise httpcore.ConnectError(f"No validated address is pinned for host '{host}'")
        # The returned stream receives the original hostname later in
        # ``start_tls``, so certificate verification and SNI are not weakened.
        return self._delegate.connect_tcp(
            addresses[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.NetworkStream:
        del path, timeout, socket_options
        raise httpcore.ConnectError("Unix sockets are forbidden for resilient outbound HTTP")

    def sleep(self, seconds: float) -> None:
        self._delegate.sleep(seconds)


TupleOfAddresses = tuple[str, ...]


class _PinnedHTTPTransport(httpx.BaseTransport):
    """HTTPX transport backed by an address-pinning httpcore connection pool."""

    def __init__(self, backend: _PinnedNetworkBackend) -> None:
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=backend,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if not isinstance(request.stream, httpx.SyncByteStream):
            raise TypeError("Pinned HTTP transport requires a synchronous request stream")
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with _map_httpcore_exceptions(request):
            core_response = self._pool.handle_request(core_request)
        if not isinstance(core_response.stream, Iterable):
            raise TypeError("Pinned HTTP transport received an asynchronous response stream")
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_CoreResponseStream(core_response.stream, request),
            extensions=core_response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


class ResilientHttpError(RuntimeError):
    """Base class for typed outbound HTTP failures."""

    def __init__(self, message: str, *, dependency: str, url: Optional[str] = None) -> None:
        self.dependency = dependency
        self.url = url
        super().__init__(message)


class HttpClientConfigurationError(ResilientHttpError):
    """Raised when no safe dependency policy has been configured."""


class DependencyNotAllowedError(ResilientHttpError):
    """Raised when a caller names an undeclared dependency."""


class UnsafeDestinationError(ResilientHttpError):
    """Raised when a URL fails syntax, allowlist, DNS, or address checks."""


class DependencyTimeoutError(ResilientHttpError):
    """Raised when connect/read/write/pool timeout is exhausted."""


class DependencyConnectionError(ResilientHttpError):
    """Raised for a non-timeout transport failure."""


class DependencyResponseError(ResilientHttpError):
    """Raised after an upstream returns a retryable failure response."""

    def __init__(self, *, dependency: str, url: str, response: httpx.Response) -> None:
        self.response = response
        self.status_code = response.status_code
        super().__init__(
            f"Dependency '{dependency}' returned retryable HTTP status {response.status_code}",
            dependency=dependency,
            url=url,
        )


# Short aliases keep exception handling readable at integration boundaries.
ConfigurationError = HttpClientConfigurationError
HttpTimeoutError = DependencyTimeoutError


@dataclass(frozen=True)
class DependencyPolicy:
    """Normalized egress policy for one logical dependency."""

    allowed_hosts: FrozenSet[str]
    base_url: Optional[str] = None


def _normalize_host(value: str) -> str:
    value = value.strip().rstrip(".").lower()
    if not value or "\x00" in value:
        raise ValueError("host must be a non-empty canonical hostname or IP")
    try:
        return value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("host is not a valid IDNA hostname") from exc


def _host_from_allowlist_entry(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("allowed host entries must be non-empty strings")
    candidate = value.strip()
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid port in allowed host entry: {candidate}") from exc
    del port
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError(f"invalid allowed host entry: {candidate}")
    return _normalize_host(parsed.hostname)


def _iter_allowed_hosts(value: Any) -> Iterable[Any]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping) or not isinstance(value, Iterable):
        raise ValueError("allowed_hosts must be a string or iterable of strings")
    return value


def _normalize_policies(configuration: Mapping[str, Any]) -> Dict[str, DependencyPolicy]:
    policies: Dict[str, DependencyPolicy] = {}
    for raw_dependency, raw_policy in configuration.items():
        if not isinstance(raw_dependency, str) or not raw_dependency.strip():
            raise ValueError("dependency keys must be non-empty strings")
        dependency = raw_dependency.strip()
        base_url: Optional[str] = None

        if isinstance(raw_policy, Mapping):
            base_value = raw_policy.get("base_url")
            if base_value is not None:
                if not isinstance(base_value, str) or not base_value.strip():
                    raise ValueError(f"base_url for dependency '{dependency}' must be a URL")
                base_url = base_value.strip().rstrip("/") + "/"
            hosts_value = raw_policy.get("allowed_hosts", raw_policy.get("hosts"))
            if hosts_value is None and base_url is not None:
                hosts_value = (base_url,)
            if hosts_value is None:
                raise ValueError(f"dependency '{dependency}' must declare allowed_hosts or base_url")
        else:
            hosts_value = raw_policy
            if isinstance(raw_policy, str) and "://" in raw_policy:
                base_url = raw_policy.strip().rstrip("/") + "/"

        hosts = frozenset(_host_from_allowlist_entry(item) for item in _iter_allowed_hosts(hosts_value))
        if not hosts:
            raise ValueError(f"dependency '{dependency}' has an empty host allowlist")

        if base_url is not None:
            parsed_base = urlsplit(base_url)
            if parsed_base.scheme.lower() not in {"http", "https"} or not parsed_base.hostname:
                raise ValueError(f"base_url for dependency '{dependency}' must use http or https")
            if _normalize_host(parsed_base.hostname) not in hosts:
                raise ValueError(f"base_url host for dependency '{dependency}' is not allowlisted")
            if parsed_base.username or parsed_base.password or parsed_base.fragment:
                raise ValueError(f"base_url for dependency '{dependency}' contains forbidden URL components")

        policies[dependency] = DependencyPolicy(allowed_hosts=hosts, base_url=base_url)
    return policies


def _configured_dependencies() -> Any:
    for setting_name in (
        "SARAISE_HTTP_DEPENDENCIES",
        "SARAISE_RESILIENT_HTTP_DEPENDENCIES",
        "RESILIENT_HTTP_DEPENDENCIES",
        "RESILIENT_HTTP_ALLOWED_DEPENDENCIES",
    ):
        value = getattr(settings, setting_name, None)
        if value is not None:
            return value
    return None


def _resolved_addresses(host: str, port: Optional[int]) -> Set[IPAddress]:
    addresses: Set[IPAddress] = set()
    try:
        records = socket.getaddrinfo(host, port)
    except (socket.gaierror, OSError):
        return addresses
    for record in records:
        try:
            raw_address = record[4][0]
            if not isinstance(raw_address, str):
                continue
            address = ipaddress.ip_address(raw_address.split("%", 1)[0])
        except (ValueError, IndexError):
            continue
        addresses.add(address)
    return addresses


def _is_forbidden_address(address: IPAddress) -> bool:
    comparable: IPAddress = address
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        comparable = address.ipv4_mapped
    return bool(
        comparable in _METADATA_ADDRESSES
        or comparable.is_loopback
        or comparable.is_link_local
        or comparable.is_private
        or comparable.is_reserved
        or comparable.is_multicast
        or comparable.is_unspecified
    )


class ResilientHttpClient:
    """Synchronous HTTP client with dependency isolation and secure egress.

    Configuration is a mapping from dependency key to an allowed host, a list
    of allowed hosts, or ``{"base_url": ..., "allowed_hosts": [...]}``.  When
    omitted, one of the supported Django settings must contain that mapping.
    Missing, empty, or malformed configuration fails construction; there is no
    unrestricted fallback.
    """

    def __init__(
        self,
        dependency_allowlist: Optional[Mapping[str, Any]] = None,
        *,
        allowed_dependencies: Optional[Mapping[str, Any]] = None,
        connect_timeout: float = 5.0,
        read_timeout: float = 10.0,
        max_retries: int = 2,
        retry_backoff: float = 0.1,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        client: Optional[httpx.Client] = None,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        if dependency_allowlist is not None and allowed_dependencies is not None:
            raise HttpClientConfigurationError(
                "Specify dependency_allowlist or allowed_dependencies, not both",
                dependency="configuration",
            )
        configuration = dependency_allowlist if dependency_allowlist is not None else allowed_dependencies
        if configuration is None:
            configuration = _configured_dependencies()
        if not isinstance(configuration, Mapping) or not configuration:
            raise HttpClientConfigurationError(
                "A non-empty outbound dependency allowlist is required",
                dependency="configuration",
            )
        try:
            self._policies = _normalize_policies(configuration)
        except (TypeError, ValueError) as exc:
            raise HttpClientConfigurationError(
                f"Invalid outbound dependency allowlist: {exc}",
                dependency="configuration",
            ) from exc

        for name, value in (("connect_timeout", connect_timeout), ("read_timeout", read_timeout)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise HttpClientConfigurationError(
                    f"{name} must be a positive number",
                    dependency="configuration",
                )
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise HttpClientConfigurationError(
                "max_retries must be a non-negative integer",
                dependency="configuration",
            )
        if isinstance(retry_backoff, bool) or not isinstance(retry_backoff, (int, float)) or retry_backoff < 0:
            raise HttpClientConfigurationError(
                "retry_backoff must be a non-negative number",
                dependency="configuration",
            )

        self._timeout = httpx.Timeout(
            connect=float(connect_timeout),
            read=float(read_timeout),
            write=float(read_timeout),
            pool=float(connect_timeout),
        )
        self._connect_timeout = float(connect_timeout)
        self._max_retries = max_retries
        self._retry_backoff = float(retry_backoff)
        self._sleep = sleep
        self._jitter = jitter
        try:
            self._breakers = CircuitBreakerRegistry(
                failure_threshold=failure_threshold,
                reset_timeout=reset_timeout,
            )
        except ValueError as exc:
            raise HttpClientConfigurationError(
                f"Invalid circuit breaker configuration: {exc}",
                dependency="configuration",
            ) from exc
        if client is not None and transport is not None:
            raise HttpClientConfigurationError(
                "Specify client or transport, not both",
                dependency="configuration",
            )
        self._pinning_backend: Optional[_PinnedNetworkBackend] = None
        if client is None and transport is None:
            self._pinning_backend = _PinnedNetworkBackend()
            transport = _PinnedHTTPTransport(self._pinning_backend)
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=self._timeout,
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        dependency: str,
        correlation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Perform one dependency operation through its circuit breaker."""

        if not isinstance(dependency, str) or dependency not in self._policies:
            raise DependencyNotAllowedError(
                f"Dependency '{dependency}' is not configured for outbound HTTP",
                dependency=str(dependency),
                url=url,
            )
        normalized_method = str(method).upper()
        policy = self._policies[dependency]
        destination = self._absolute_url(policy, url, dependency)
        breaker = self._breakers.get(dependency)

        # Reject known-open circuits before DNS work. ``call`` remains the
        # authority for the transition and exception payload.
        if breaker.state == CircuitState.OPEN:
            return cast(httpx.Response, breaker.call(lambda: self._unreachable_response()))

        host, port = self._validate_destination(policy, destination, dependency)
        headers = dict(kwargs.pop("headers", {}) or {})
        propagated_id = correlation_id if correlation_id is not None else get_correlation_id()
        if propagated_id:
            headers = {key: value for key, value in headers.items() if key.lower() != HEADER_NAME.lower()}
            headers[HEADER_NAME] = propagated_id
        kwargs["headers"] = headers
        kwargs["follow_redirects"] = False
        if "timeout" in kwargs:
            raise HttpClientConfigurationError(
                "Per-request timeout overrides are forbidden; use the configured client timeouts",
                dependency=dependency,
                url=destination,
            )
        kwargs["timeout"] = self._timeout

        return cast(
            httpx.Response,
            breaker.call(
                self._resolve_pin_and_send,
                normalized_method,
                destination,
                dependency,
                host,
                port,
                kwargs,
            ),
        )

    @staticmethod
    def _unreachable_response() -> httpx.Response:
        """Type-only sentinel: an open breaker never executes this function."""

        raise AssertionError("open circuit admitted an operation")

    def get_breaker(self, dependency: str) -> CircuitBreaker[Any]:
        """Expose dependency state for health probes and operational telemetry."""

        if dependency not in self._policies:
            raise DependencyNotAllowedError(
                f"Dependency '{dependency}' is not configured for outbound HTTP",
                dependency=dependency,
            )
        return self._breakers.get(dependency)

    def get(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, dependency=dependency, **kwargs)

    def head(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, dependency=dependency, **kwargs)

    def options(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("OPTIONS", url, dependency=dependency, **kwargs)

    def post(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, dependency=dependency, **kwargs)

    def put(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, dependency=dependency, **kwargs)

    def patch(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, dependency=dependency, **kwargs)

    def delete(self, url: str, *, dependency: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, dependency=dependency, **kwargs)

    def close(self) -> None:
        """Release sockets owned by this wrapper."""

        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "ResilientHttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _absolute_url(self, policy: DependencyPolicy, url: str, dependency: str) -> str:
        if not isinstance(url, str) or not url.strip() or url != url.strip():
            raise UnsafeDestinationError(
                "Outbound URL must be a non-empty canonical string",
                dependency=dependency,
                url=str(url),
            )
        if urlsplit(url).scheme:
            return url
        if policy.base_url is None:
            raise UnsafeDestinationError(
                "Relative URL requires a configured dependency base_url",
                dependency=dependency,
                url=url,
            )
        return urljoin(policy.base_url, url)

    def _validate_destination(
        self,
        policy: DependencyPolicy,
        url: str,
        dependency: str,
    ) -> tuple[str, Optional[int]]:
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as exc:
            raise UnsafeDestinationError(
                "Outbound URL contains an invalid port",
                dependency=dependency,
                url=url,
            ) from exc
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise UnsafeDestinationError(
                "Outbound URL must be an absolute http or https URL",
                dependency=dependency,
                url=url,
            )
        if parsed.username or parsed.password or parsed.fragment:
            raise UnsafeDestinationError(
                "Outbound URL contains forbidden userinfo or fragment components",
                dependency=dependency,
                url=url,
            )
        host = _normalize_host(parsed.hostname)
        if host in _METADATA_HOSTS:
            raise UnsafeDestinationError(
                "Outbound URL targets a metadata service hostname",
                dependency=dependency,
                url=url,
            )
        if host not in policy.allowed_hosts:
            raise UnsafeDestinationError(
                f"Host '{host}' is not allowlisted for dependency '{dependency}'",
                dependency=dependency,
                url=url,
            )
        return host, port

    def _resolve_pin_and_send(
        self,
        method: str,
        url: str,
        dependency: str,
        host: str,
        port: Optional[int],
        kwargs: Mapping[str, Any],
    ) -> httpx.Response:
        future = _DNS_EXECUTOR.submit(_resolved_addresses, host, port)
        try:
            addresses = future.result(timeout=self._connect_timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise DependencyTimeoutError(
                f"DNS resolution timed out for dependency '{dependency}'",
                dependency=dependency,
                url=url,
            ) from exc
        if not addresses:
            raise DependencyConnectionError(
                f"Allowlisted host '{host}' could not be resolved for dependency '{dependency}'",
                dependency=dependency,
                url=url,
            )
        if any(_is_forbidden_address(address) for address in addresses):
            raise UnsafeDestinationError(
                f"Allowlisted host '{host}' resolves to an internal or non-routable address",
                dependency=dependency,
                url=url,
            )
        if self._pinning_backend is not None:
            self._pinning_backend.pin(host, addresses)
        return self._send_with_retries(method, url, dependency, kwargs)

    def _send_with_retries(
        self,
        method: str,
        url: str,
        dependency: str,
        kwargs: Mapping[str, Any],
    ) -> httpx.Response:
        attempts = self._max_retries + 1 if method in IDEMPOTENT_METHODS else 1
        last_transport_error: Optional[ResilientHttpError] = None
        for attempt in range(attempts):
            try:
                response = self._client.request(method, url, **dict(kwargs))
            except httpx.TimeoutException as exc:
                last_transport_error = DependencyTimeoutError(
                    f"Dependency '{dependency}' timed out during {method}",
                    dependency=dependency,
                    url=url,
                )
                last_transport_error.__cause__ = exc
            except httpx.TransportError as exc:
                last_transport_error = DependencyConnectionError(
                    f"Dependency '{dependency}' transport failed during {method}: {type(exc).__name__}",
                    dependency=dependency,
                    url=url,
                )
                last_transport_error.__cause__ = exc
            else:
                if response.status_code not in RETRYABLE_STATUS_CODES and not 500 <= response.status_code <= 599:
                    return response
                if attempt + 1 >= attempts:
                    raise DependencyResponseError(dependency=dependency, url=url, response=response)
                response.close()

            if attempt + 1 < attempts:
                delay = self._retry_backoff * (2**attempt)
                delay += self._jitter(0.0, self._retry_backoff)
                self._sleep(delay)

        assert last_transport_error is not None
        raise last_transport_error


__all__ = [
    "ConfigurationError",
    "DependencyConnectionError",
    "DependencyNotAllowedError",
    "DependencyPolicy",
    "DependencyResponseError",
    "DependencyTimeoutError",
    "HttpClientConfigurationError",
    "HttpTimeoutError",
    "ResilientHttpClient",
    "ResilientHttpError",
    "UnsafeDestinationError",
]
