"""Versioned, ORM-free notification channel adapter contract.

Provider extensions depend on the immutable DTOs and registry in this module,
never on notification persistence models.  The two open-source adapters turn
only authoritative acknowledgements into success: a locked durable delivery
accepted by the inbox service for ``in_app`` and a positive Django email
backend send count for ``django_email``.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from src.core.api.results import CapabilityUnavailable
from src.core.resilience.http import ResilientHttpClient

SPI_VERSION: Final[str] = "1.0"
SUPPORTED_CHANNELS: Final[frozenset[str]] = frozenset(
    {"in_app", "email", "sms", "push", "webhook"}
)
SUPPORTED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {"text/plain", "text/html", "application/json"}
)
_ADAPTER_KEY = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_EXTENSION_KEY = re.compile(r"^extensions\.[a-z][a-z0-9_]{0,63}$")
_HEALTH_DETAIL_KEYS: Final[frozenset[str]] = frozenset(
    {
        "backend_configured",
        "circuit_state",
        "enabled",
        "last_success_at",
        "latency_ms",
        "persistence",
    }
)


def _frozen_mapping(value: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return MappingProxyType(dict(value))


def _required_text(value: object, field_name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} must not exceed {maximum} characters")
    return normalized


def _validate_extensions(metadata: Mapping[str, object]) -> None:
    for namespace, document in metadata.items():
        if not isinstance(namespace, str) or _EXTENSION_KEY.fullmatch(namespace) is None:
            raise ValueError("extension metadata keys must use extensions.<module_name>")
        if not isinstance(document, Mapping):
            raise ValueError(f"{namespace} extension metadata must be an object")


@dataclass(frozen=True, slots=True)
class AdapterHealth:
    """Sanitized adapter readiness evidence."""

    healthy: bool
    status: str
    code: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in {"ready", "disabled", "unavailable"}:
            raise ValueError("adapter health status is invalid")
        object.__setattr__(self, "code", _required_text(self.code, "code", 100))
        details = _frozen_mapping(self.details, "details")
        if set(details) - _HEALTH_DETAIL_KEYS:
            raise ValueError("adapter health details contain non-public fields")
        object.__setattr__(self, "details", details)


@dataclass(frozen=True, slots=True)
class DeliveryCommand:
    """Secret-minimal command passed to one channel adapter.

    ``recipient_address`` and rendered content exist only in worker memory and
    must never be logged or persisted by an adapter.  Durable jobs carry only
    the IDs needed to reconstruct this command.
    """

    tenant_id: UUID
    delivery_id: UUID
    idempotency_token: str
    recipient: str
    subject: str
    body: str
    configuration: Mapping[str, object]
    correlation_id: UUID
    channel: str = ""
    recipient_type: str = ""
    content_type: str = "text/plain"
    extension_metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.delivery_id, UUID):
            raise TypeError("tenant_id and delivery_id must be UUID values")
        if not isinstance(self.correlation_id, UUID):
            raise TypeError("correlation_id must be a UUID value")
        channel = str(self.channel).strip().lower()
        if channel and channel not in SUPPORTED_CHANNELS:
            raise ValueError("channel is not supported")
        object.__setattr__(self, "channel", channel)
        recipient_type = str(self.recipient_type).strip().lower()
        if len(recipient_type) > 20:
            raise ValueError("recipient_type must not exceed 20 characters")
        object.__setattr__(self, "recipient_type", recipient_type)
        object.__setattr__(self, "recipient", _required_text(self.recipient, "recipient", 4096))
        object.__setattr__(self, "idempotency_token", _required_text(self.idempotency_token, "idempotency_token", 255))
        if self.content_type not in SUPPORTED_CONTENT_TYPES:
            raise ValueError("content_type is not supported")
        object.__setattr__(self, "configuration", _frozen_mapping(self.configuration, "configuration"))
        extension_metadata = _frozen_mapping(self.extension_metadata, "extension_metadata")
        _validate_extensions(extension_metadata)
        object.__setattr__(self, "extension_metadata", extension_metadata)

    @property
    def recipient_address(self) -> str:
        """Compatibility alias that keeps the public DTO provider-neutral."""

        return self.recipient


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Authoritative acknowledgement returned by an adapter."""

    accepted: bool
    provider_message_id: str = ""
    retryable: bool = False
    error_code: str = ""
    confirmation_supported: bool = True
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.accepted and self.retryable:
            raise ValueError("an accepted delivery cannot be retryable")
        if self.accepted and not self.evidence:
            raise ValueError("acknowledged delivery requires durable evidence")
        if not self.accepted and not self.error_code:
            raise ValueError("rejected delivery requires a stable error_code")
        if len(self.provider_message_id) > 255:
            raise ValueError("provider_message_id must not exceed 255 characters")
        object.__setattr__(self, "evidence", _frozen_mapping(self.evidence, "evidence"))

    @property
    def acknowledged(self) -> bool:
        return self.accepted


@dataclass(frozen=True, slots=True)
class EndpointVerificationCommand:
    tenant_id: UUID
    endpoint_id: UUID
    address: str
    correlation_id: UUID
    configuration: Mapping[str, object]
    kind: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.endpoint_id, UUID):
            raise TypeError("tenant_id and endpoint_id must be UUID values")
        if not isinstance(self.correlation_id, UUID):
            raise TypeError("correlation_id must be a UUID value")
        kind = str(self.kind).strip().lower()
        if len(kind) > 20:
            raise ValueError("kind must not exceed 20 characters")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "address", _required_text(self.address, "address", 4096))
        object.__setattr__(self, "configuration", _frozen_mapping(self.configuration, "configuration"))


@dataclass(frozen=True, slots=True)
class VerificationResult:
    verified: bool
    code: str
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _required_text(self.code, "code", 100))
        if self.verified and not self.evidence:
            raise ValueError("verified endpoints require evidence")
        object.__setattr__(self, "evidence", _frozen_mapping(self.evidence, "evidence"))

    @property
    def error_code(self) -> str:
        return "" if self.verified else self.code


@runtime_checkable
class NotificationChannelAdapter(Protocol):
    key: str
    channel: str

    def health(self, tenant_id: UUID, configuration: Mapping[str, object]) -> AdapterHealth: ...

    def send(self, command: DeliveryCommand) -> DeliveryResult: ...

    def verify_endpoint(self, command: EndpointVerificationCommand) -> VerificationResult: ...


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    """Immutable discovery record safe for capability catalogues."""

    key: str
    channel: str
    spi_version: str = SPI_VERSION
    owner: str = "notifications"

    def __post_init__(self) -> None:
        key = _required_text(self.key, "key", 100)
        if _ADAPTER_KEY.fullmatch(key) is None:
            raise ValueError("adapter key must be a lowercase dotted identifier")
        channel = _required_text(self.channel, "channel", 20).lower()
        if channel not in SUPPORTED_CHANNELS:
            raise ValueError("adapter channel is unsupported")
        if self.spi_version != SPI_VERSION:
            raise ValueError(f"adapter SPI version must be {SPI_VERSION}")
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "channel", channel)
        object.__setattr__(self, "owner", _required_text(self.owner, "owner", 100))


class AdapterRegistrationError(RuntimeError):
    """Base registry ownership error."""


class AdapterAlreadyRegistered(AdapterRegistrationError):
    """Raised when a key already has an owner."""


class AdapterNotRegistered(LookupError):
    """Raised when configuration refers to an unavailable adapter."""


class AdapterRegistry:
    """Thread-safe registry that never silently replaces ownership."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[AdapterDescriptor, NotificationChannelAdapter]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        descriptor: AdapterDescriptor,
        adapter: NotificationChannelAdapter,
    ) -> NotificationChannelAdapter:
        if not isinstance(adapter, NotificationChannelAdapter):
            raise TypeError("adapter does not implement NotificationChannelAdapter")
        if adapter.key != descriptor.key or adapter.channel != descriptor.channel:
            raise ValueError("adapter identity does not match its descriptor")
        with self._lock:
            if descriptor.key in self._entries:
                raise AdapterAlreadyRegistered(f"adapter {descriptor.key!r} is already registered")
            self._entries[descriptor.key] = (descriptor, adapter)
        return adapter

    def unregister(self, key: str) -> NotificationChannelAdapter | None:
        canonical = str(key).strip().lower()
        with self._lock:
            entry = self._entries.pop(canonical, None)
        return entry[1] if entry else None

    def get(self, key: str) -> NotificationChannelAdapter:
        canonical = str(key).strip().lower()
        with self._lock:
            entry = self._entries.get(canonical)
        if entry is None:
            raise AdapterNotRegistered(f"adapter {canonical!r} is not registered")
        return entry[1]

    def descriptor(self, key: str) -> AdapterDescriptor:
        canonical = str(key).strip().lower()
        with self._lock:
            entry = self._entries.get(canonical)
        if entry is None:
            raise AdapterNotRegistered(f"adapter {canonical!r} is not registered")
        return entry[0]

    def descriptors(self) -> tuple[AdapterDescriptor, ...]:
        with self._lock:
            return tuple(self._entries[key][0] for key in sorted(self._entries))


InboxWriter = Callable[[DeliveryCommand], Mapping[str, object]]


def _default_inbox_writer(command: DeliveryCommand) -> Mapping[str, object]:
    """Verify the durable row the dispatch service will project to the inbox."""

    from django.apps import apps

    delivery_model = apps.get_model("notifications", "NotificationDelivery")
    delivery = delivery_model.objects.for_tenant(command.tenant_id).get(pk=command.delivery_id)
    if delivery.channel != "in_app" or not delivery.recipient_user_id or delivery.status != "sending":
        raise ValueError("delivery is not eligible for inbox projection")
    return {
        "delivery_id": str(command.delivery_id),
        "recipient_bound": True,
        "inbox_projection": "dispatch_service",
    }


class InAppAdapter:
    key = "in_app"
    channel = "in_app"

    def __init__(self, writer: InboxWriter = _default_inbox_writer) -> None:
        self._writer = writer

    def health(self, tenant_id: UUID, configuration: Mapping[str, object]) -> AdapterHealth:
        del tenant_id, configuration
        return AdapterHealth(True, "ready", "ready", {"persistence": "configured"})

    def send(self, command: DeliveryCommand) -> DeliveryResult:
        if command.channel and command.channel != self.channel:
            raise ValueError("in-app adapter received a command for another channel")
        evidence = dict(self._writer(command))
        if not evidence.get("delivery_id") and not evidence.get("notification_id"):
            raise RuntimeError("in-app persistence returned no durable delivery evidence")
        return DeliveryResult(
            True,
            provider_message_id=str(evidence.get("notification_id") or evidence["delivery_id"]),
            confirmation_supported=False,
            evidence=evidence,
        )

    def verify_endpoint(self, command: EndpointVerificationCommand) -> VerificationResult:
        del command
        raise CapabilityUnavailable(capability="notifications.endpoint.in_app")


class DjangoEmailAdapter:
    key = "django_email"
    channel = "email"

    def health(self, tenant_id: UUID, configuration: Mapping[str, object]) -> AdapterHealth:
        del tenant_id
        enabled = configuration.get("enabled", True)
        if enabled is False:
            return AdapterHealth(True, "disabled", "disabled", {"enabled": False})
        backend = getattr(settings, "EMAIL_BACKEND", "")
        if not isinstance(backend, str) or not backend.strip():
            return AdapterHealth(False, "unavailable", "email_backend_missing")
        return AdapterHealth(True, "ready", "ready", {"backend_configured": True})

    def send(self, command: DeliveryCommand) -> DeliveryResult:
        if command.channel and command.channel != self.channel:
            raise ValueError("Django email adapter received a command for another channel")
        try:
            validate_email(command.recipient_address)
        except ValidationError as exc:
            raise ValueError("email recipient is invalid") from exc
        from_email = command.configuration.get("sender_ref") or command.configuration.get("from_email") or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        try:
            validate_email(str(from_email))
        except ValidationError as exc:
            raise CapabilityUnavailable(
                capability="notifications.email.sender",
                message="The configured email sender is unavailable.",
            ) from exc
        message_id = f"notification-{command.delivery_id}@saraise.local"
        message = EmailMultiAlternatives(
            subject=command.subject,
            body=command.body,
            from_email=str(from_email),
            to=[command.recipient_address],
            headers={
                "X-Correlation-ID": str(command.correlation_id),
                "X-Notification-Idempotency-Key": command.idempotency_token,
                "Message-ID": f"<{message_id}>",
            },
        )
        if command.content_type == "text/html":
            message.attach_alternative(command.body, "text/html")
        accepted_count = message.send(fail_silently=False)
        if accepted_count != 1:
            raise CapabilityUnavailable(
                capability="notifications.email.delivery",
                message="The email backend did not acknowledge the message.",
            )
        return DeliveryResult(
            True,
            provider_message_id=message_id,
            confirmation_supported=False,
            evidence={"backend_acknowledged": True, "accepted_count": accepted_count},
        )

    def verify_endpoint(self, command: EndpointVerificationCommand) -> VerificationResult:
        if command.kind and command.kind != "email":
            raise ValueError("Django email adapter can verify only email endpoints")
        try:
            validate_email(command.address)
        except ValidationError as exc:
            raise ValueError("email endpoint is invalid") from exc
        health = self.health(command.tenant_id, command.configuration)
        if not health.healthy:
            raise CapabilityUnavailable(capability="notifications.email.delivery")
        return VerificationResult(True, "verified", {"syntax": "valid", "backend": "configured"})


class UnavailableAdapter:
    """Explicit placeholder for channels with no installed provider."""

    def __init__(self, key: str, channel: str) -> None:
        self.key = AdapterDescriptor(key=key, channel=channel).key
        self.channel = channel

    def health(self, tenant_id: UUID, configuration: Mapping[str, object]) -> AdapterHealth:
        del tenant_id, configuration
        return AdapterHealth(False, "unavailable", "adapter_unavailable")

    def send(self, command: DeliveryCommand) -> DeliveryResult:
        del command
        raise CapabilityUnavailable(capability=f"notifications.adapter.{self.key}")

    def verify_endpoint(self, command: EndpointVerificationCommand) -> VerificationResult:
        del command
        raise CapabilityUnavailable(capability=f"notifications.adapter.{self.key}")


def validate_action_url(url: str, allowed_hosts: frozenset[str] = frozenset()) -> str:
    """Allow internal paths or an explicitly allowlisted HTTPS destination."""

    value = str(url).strip()
    if not value:
        return ""
    if len(value) > 500 or any(ord(character) < 32 for character in value):
        raise ValueError("action URL is invalid")
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".").lower()
    canonical_hosts = {candidate.rstrip(".").lower() for candidate in allowed_hosts}
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or host not in canonical_hosts
    ):
        raise ValueError("action URL must be internal or an allowlisted HTTPS URL")
    return value


def resilient_http_client(
    dependency: str,
    configuration: Mapping[str, object],
) -> ResilientHttpClient:
    """Build the mandatory egress boundary from validated channel settings.

    HTTP adapters must call this factory rather than constructing ``httpx`` or
    ``requests`` clients.  The shared client performs DNS/IP validation,
    address pinning, redirect denial, correlation propagation, jittered
    retries, configured timeouts, and per-dependency circuit breaking.
    """

    key = _required_text(dependency, "dependency", 100)
    hosts = configuration.get("allowed_hosts")
    if not isinstance(hosts, (list, tuple)) or not hosts or any(
        not isinstance(host, str) or not host.strip() for host in hosts
    ):
        raise CapabilityUnavailable(
            capability=f"notifications.egress.{key}",
            message="The provider hostname allowlist is not configured.",
        )
    timeout = configuration.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
        raise ValueError("timeout_seconds must be between 1 and 120")
    retry = configuration.get("retry")
    circuit = configuration.get("circuit")
    if not isinstance(retry, Mapping) or not isinstance(circuit, Mapping):
        raise ValueError("retry and circuit configuration objects are required")
    attempts = retry.get("max_attempts")
    backoff = retry.get("base_seconds")
    threshold = circuit.get("failure_threshold")
    reset = circuit.get("reset_seconds")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 1 <= attempts <= 10:
        raise ValueError("retry.max_attempts must be between 1 and 10")
    if isinstance(backoff, bool) or not isinstance(backoff, (int, float)) or not 0 <= backoff <= 3600:
        raise ValueError("retry.base_seconds must be between 0 and 3600")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 100:
        raise ValueError("circuit.failure_threshold must be between 1 and 100")
    if isinstance(reset, bool) or not isinstance(reset, (int, float)) or not 1 <= reset <= 86400:
        raise ValueError("circuit.reset_seconds must be between 1 and 86400")
    policy: dict[str, object] = {"allowed_hosts": list(hosts)}
    base_url = configuration.get("base_url")
    if base_url not in (None, ""):
        policy["base_url"] = _required_text(base_url, "base_url", 2048)
    return ResilientHttpClient(
        {key: policy},
        connect_timeout=float(timeout),
        read_timeout=float(timeout),
        max_retries=attempts - 1,
        retry_backoff=float(backoff),
        failure_threshold=threshold,
        reset_timeout=float(reset),
    )


adapter_registry = AdapterRegistry()


def get_adapter(key: str) -> NotificationChannelAdapter:
    """Resolve configured adapter ownership or fail explicitly."""

    try:
        return adapter_registry.get(key)
    except AdapterNotRegistered as exc:
        raise CapabilityUnavailable(capability=f"notifications.adapter.{str(key).strip().lower()}") from exc


def register_builtin_adapters() -> None:
    """Register OSS adapters idempotently without permitting replacement."""

    for descriptor, adapter in (
        (AdapterDescriptor("in_app", "in_app"), InAppAdapter()),
        (AdapterDescriptor("django_email", "email"), DjangoEmailAdapter()),
    ):
        try:
            current = adapter_registry.get(descriptor.key)
        except AdapterNotRegistered:
            adapter_registry.register(descriptor, adapter)
        else:
            registered_descriptor = adapter_registry.descriptor(descriptor.key)
            if type(current) is not type(adapter) or registered_descriptor != descriptor:
                raise AdapterAlreadyRegistered(f"adapter {descriptor.key!r} has a different owner")


register_builtin_adapters()


__all__ = [
    "AdapterAlreadyRegistered",
    "AdapterDescriptor",
    "AdapterHealth",
    "AdapterNotRegistered",
    "AdapterRegistry",
    "CapabilityUnavailable",
    "DeliveryCommand",
    "DeliveryResult",
    "DjangoEmailAdapter",
    "EndpointVerificationCommand",
    "InAppAdapter",
    "NotificationChannelAdapter",
    "SPI_VERSION",
    "UnavailableAdapter",
    "VerificationResult",
    "adapter_registry",
    "get_adapter",
    "register_builtin_adapters",
    "resilient_http_client",
    "validate_action_url",
]
