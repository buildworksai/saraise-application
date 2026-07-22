"""Typed, collision-safe extension contracts for email delivery.

The core domain depends only on the protocols and immutable result objects in
this module. Industry and provider modules register adapters by key; they never
replace consent, suppression, tenant, or lifecycle enforcement.
"""

from __future__ import annotations

import hashlib
import re
import threading
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import make_msgid
from html.parser import HTMLParser
from typing import Final, Generic, Protocol, TypeVar, runtime_checkable
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.template import Context, Engine, TemplateSyntaxError
from django.utils import timezone

from src.core.resilience import CircuitBreaker, CircuitBreakerError

SPI_VERSION: Final = "1.0"
MAX_PERSONALIZATION_KEYS: Final = 100
MAX_PERSONALIZATION_BYTES: Final = 32_768
MAX_RECIPIENTS_PER_DEFINITION: Final = 100_000
SAFE_DJANGO_BACKENDS: Final = frozenset(
    {
        "django.core.mail.backends.smtp.EmailBackend",
    }
)
SIMULATED_DJANGO_BACKENDS: Final = frozenset(
    {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
        "django.core.mail.backends.filebased.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
    }
)
_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:@+-]{1,255}$")
_TEMPLATE_VARIABLE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*}}")


class AdapterError(RuntimeError):
    """Base class for stable adapter failures."""


class AdapterNotRegistered(AdapterError):
    """Raised when a selected extension key is unavailable."""


class AdapterAlreadyRegistered(AdapterError):
    """Raised when registration would silently replace an extension."""


class InvalidAdapterOutput(AdapterError):
    """Raised when provider output cannot be accepted as evidence."""


class DeliveryConfigurationError(AdapterError):
    """Raised when no real delivery transport is safely configured."""


class RenderingError(AdapterError):
    """Raised when content cannot be rendered without missing variables."""


class _AmbiguousDeliveryTimeout(AdapterError):
    """Sanitized exception recorded by the circuit breaker."""


class _DeliveryTransportFailure(AdapterError):
    """Sanitized exception recorded by the circuit breaker."""


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class OperationResult(Generic[T]):
    """Explicit outcome; a value is present only after real acknowledgement."""

    successful: bool
    code: str
    value: T | None = None
    retryable: bool = False
    ambiguous: bool = False
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.code or len(self.code) > 64 or not _SAFE_KEY.fullmatch(self.code):
            raise ValueError("operation result code must be a bounded stable identifier")
        if self.successful and self.value is None:
            raise ValueError("successful operation result requires evidence")
        if not self.successful and self.value is not None:
            raise ValueError("failed operation result cannot contain a value")
        if self.successful and (self.retryable or self.ambiguous):
            raise ValueError("successful operation cannot be retryable or ambiguous")
        if len(self.detail) > 500:
            raise ValueError("operation detail exceeds the safe bound")

    @classmethod
    def success(cls, value: T, *, code: str = "accepted") -> "OperationResult[T]":
        return cls(True, code, value=value)

    @classmethod
    def failure(
        cls,
        code: str,
        *,
        retryable: bool = False,
        ambiguous: bool = False,
        detail: str = "",
    ) -> "OperationResult[T]":
        return cls(False, code, retryable=retryable, ambiguous=ambiguous, detail=detail)

    def unwrap(self) -> T:
        if not self.successful or self.value is None:
            raise AdapterError(f"operation failed with code {self.code}")
        return self.value


def normalize_email(value: object) -> str:
    """Validate an address and lower-case only its domain component."""

    if not isinstance(value, str):
        raise ValueError("email must be a string")
    candidate = value.strip()
    try:
        validate_email(candidate)
    except ValidationError as exc:
        raise ValueError("email is invalid") from exc
    local, domain = candidate.rsplit("@", 1)
    return f"{local}@{domain.lower()}"


def _bounded_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    if len(value) > MAX_PERSONALIZATION_KEYS:
        raise ValueError(f"{field_name} contains too many keys")
    total = 0
    normalized: dict[str, object] = {}
    for raw_key, item in value.items():
        key = str(raw_key)
        if not _SAFE_KEY.fullmatch(key):
            raise ValueError(f"{field_name} contains an invalid key")
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"{field_name} values must be scalar")
        total += len(key.encode()) + len(str(item).encode())
        normalized[key] = item
    if total > MAX_PERSONALIZATION_BYTES:
        raise ValueError(f"{field_name} exceeds the byte limit")
    return normalized


@dataclass(frozen=True, slots=True)
class AudienceCandidate:
    email: str
    recipient_key: str | None = None
    display_name: str = ""
    personalization: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "email", normalize_email(self.email))
        if self.recipient_key is not None and not 0 < len(self.recipient_key) <= 255:
            raise ValueError("recipient_key exceeds the allowed bound")
        if len(self.display_name) > 255 or "\r" in self.display_name or "\n" in self.display_name:
            raise ValueError("display_name is invalid")
        object.__setattr__(self, "personalization", _bounded_mapping(self.personalization, "personalization"))

    @property
    def personalization_data(self) -> Mapping[str, object]:
        """Compatibility spelling used by the persistence service."""
        return self.personalization


@dataclass(frozen=True, slots=True)
class AudienceResolutionResult:
    candidates: tuple[AudienceCandidate, ...]
    resolver_key: str
    schema_version: str = SPI_VERSION
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != SPI_VERSION:
            raise InvalidAdapterOutput("audience resolver schema version is incompatible")
        if not _SAFE_KEY.fullmatch(self.resolver_key):
            raise InvalidAdapterOutput("audience resolver key is invalid")
        if len(self.candidates) > MAX_RECIPIENTS_PER_DEFINITION:
            raise InvalidAdapterOutput("audience resolver returned too many candidates")
        if not isinstance(self.evidence, Mapping):
            raise InvalidAdapterOutput("audience evidence must be an object")


@dataclass(frozen=True, slots=True)
class EligibilityDecision:
    """Consent/suppression evaluation evidence returned by domain services."""

    eligible: bool
    code: str
    consent_record_id: UUID | None = None
    suppression_id: UUID | None = None

    def __post_init__(self) -> None:
        if not _SAFE_KEY.fullmatch(self.code):
            raise ValueError("eligibility code must be a bounded stable identifier")
        if self.eligible and self.suppression_id is not None:
            raise ValueError("eligible decision cannot reference an active suppression")


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    html: str
    text: str
    preview_text: str = ""

    def __post_init__(self) -> None:
        if not self.subject.strip() or len(self.subject) > 500 or "\r" in self.subject or "\n" in self.subject:
            raise InvalidAdapterOutput("rendered subject is invalid")
        if not self.html.strip() and not self.text.strip():
            raise InvalidAdapterOutput("rendered email requires HTML or text content")
        if len(self.preview_text) > 255:
            raise InvalidAdapterOutput("preview text exceeds the allowed bound")


@dataclass(frozen=True, slots=True)
class DeliveryMessage:
    recipient: str
    from_email: str
    from_name: str
    reply_to: str | None
    rendered: RenderedEmail
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipient", normalize_email(self.recipient))
        object.__setattr__(self, "from_email", normalize_email(self.from_email))
        if self.reply_to:
            object.__setattr__(self, "reply_to", normalize_email(self.reply_to))
        if len(self.from_name) > 255 or any(char in self.from_name for char in "\r\n"):
            raise ValueError("from_name is invalid")
        allowed = {"List-Unsubscribe", "List-Unsubscribe-Post", "X-SARAISE-Campaign-ID"}
        if set(self.headers) - allowed:
            raise ValueError("delivery message contains non-allowlisted headers")
        if any("\r" in value or "\n" in value for value in self.headers.values()):
            raise ValueError("delivery message header is invalid")


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    provider_message_id: str
    gateway_key: str
    acknowledgement: str
    accepted_at: datetime
    evidence: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.provider_message_id or len(self.provider_message_id) > 255:
            raise InvalidAdapterOutput("gateway acknowledgement requires a provider message id")
        if not _SAFE_KEY.fullmatch(self.gateway_key):
            raise InvalidAdapterOutput("gateway key is invalid")
        if self.acknowledgement not in {
            "transport_accepted",
            "provider_accepted",
            "provider_delivered",
            "accepted",
            "delivered",
            "failed",
            "bounced",
        }:
            raise InvalidAdapterOutput("gateway acknowledgement class is invalid")
        if timezone.is_naive(self.accepted_at):
            raise InvalidAdapterOutput("gateway acknowledgement time must be timezone-aware")
        if not isinstance(self.evidence, Mapping):
            raise InvalidAdapterOutput("gateway evidence must be an object")


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    available: bool
    code: str
    checked_at: datetime
    circuit_state: str = "unknown"
    reconciliation_supported: bool = False

    def __post_init__(self) -> None:
        if not _SAFE_KEY.fullmatch(self.code):
            raise ValueError("dependency health code is invalid")
        if timezone.is_naive(self.checked_at):
            raise ValueError("dependency health time must be timezone-aware")
        if self.circuit_state not in {"closed", "open", "half_open", "unknown", "not_applicable"}:
            raise ValueError("dependency circuit state is invalid")


@dataclass(frozen=True, slots=True)
class VerifiedDeliveryEvent:
    provider_event_id: str
    provider_message_id: str
    event_type: str
    occurred_at: datetime
    metadata: Mapping[str, object] = field(default_factory=dict)
    bounce_class: str = ""
    link_url_hash: str = ""

    def __post_init__(self) -> None:
        if not self.provider_event_id or len(self.provider_event_id) > 255:
            raise InvalidAdapterOutput("provider event id is invalid")
        if not self.provider_message_id or len(self.provider_message_id) > 255:
            raise InvalidAdapterOutput("provider message id is invalid")
        allowed = {"accepted", "delivered", "opened", "clicked", "deferred", "bounced", "complained", "unsubscribed"}
        if self.event_type not in allowed:
            raise InvalidAdapterOutput("provider event type is unsupported")
        if timezone.is_naive(self.occurred_at):
            raise InvalidAdapterOutput("provider event timestamp must be timezone-aware")
        if self.bounce_class not in {"", "hard", "soft", "block"}:
            raise InvalidAdapterOutput("bounce class is invalid")
        if self.link_url_hash and not re.fullmatch(r"[a-f0-9]{64}", self.link_url_hash):
            raise InvalidAdapterOutput("link URL hash must be SHA-256")
        object.__setattr__(self, "metadata", _bounded_mapping(self.metadata, "event metadata"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "VerifiedDeliveryEvent":
        raw_time = value.get("occurred_at")
        if not isinstance(raw_time, str):
            raise InvalidAdapterOutput("provider event requires occurred_at")
        try:
            occurred_at = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidAdapterOutput("provider event timestamp is invalid") from exc
        metadata = value.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise InvalidAdapterOutput("provider event metadata must be an object")
        return cls(
            provider_event_id=str(value.get("provider_event_id", "")),
            provider_message_id=str(value.get("provider_message_id", "")),
            event_type=str(value.get("event_type", "")),
            occurred_at=occurred_at,
            metadata=metadata,
            bounce_class=str(value.get("bounce_class", "")),
            link_url_hash=str(value.get("link_url_hash", "")),
        )

    def as_mapping(self) -> dict[str, object]:
        return {
            "provider_event_id": self.provider_event_id,
            "provider_message_id": self.provider_message_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "metadata": dict(self.metadata),
            "bounce_class": self.bounce_class,
            "link_url_hash": self.link_url_hash,
        }


@runtime_checkable
class AudienceResolver(Protocol):
    schema_version: str
    resolver_key: str

    def resolve(self, tenant_id: UUID, definition: Mapping[str, object]) -> AudienceResolutionResult: ...


@runtime_checkable
class EmailRenderer(Protocol):
    schema_version: str
    renderer_key: str

    def render(
        self, template_snapshot: Mapping[str, object], personalization: Mapping[str, object]
    ) -> RenderedEmail: ...


@runtime_checkable
class EmailDeliveryGateway(Protocol):
    schema_version: str
    gateway_key: str

    def submit(
        self, message: DeliveryMessage, idempotency_key: str, correlation_id: str
    ) -> OperationResult[DeliveryReceipt]: ...

    def lookup(self, provider_message_id: str) -> OperationResult[DeliveryReceipt]: ...

    def health(self) -> DependencyHealth: ...


@runtime_checkable
class ProviderEventVerifier(Protocol):
    schema_version: str
    verifier_key: str

    def verify(self, headers: Mapping[str, str], body: bytes) -> VerifiedDeliveryEvent: ...


ProviderT = TypeVar("ProviderT")


class ExtensionRegistry(Generic[ProviderT]):
    """Deterministic registry with explicit lifecycle and collision rejection."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._providers: dict[str, ProviderT] = {}
        self._lock = threading.RLock()

    def register(self, key: str, provider: ProviderT) -> ProviderT:
        if not _SAFE_KEY.fullmatch(key):
            raise ValueError(f"{self.kind} key is invalid")
        if getattr(provider, "schema_version", None) != SPI_VERSION:
            raise ValueError(f"{self.kind} schema_version must be {SPI_VERSION}")
        with self._lock:
            existing = self._providers.get(key)
            if existing is not None and existing is not provider:
                raise AdapterAlreadyRegistered(f"{self.kind} {key!r} is already registered")
            self._providers[key] = provider
        return provider

    def unregister(self, key: str) -> ProviderT | None:
        with self._lock:
            return self._providers.pop(key, None)

    def get(self, key: str) -> ProviderT:
        with self._lock:
            try:
                return self._providers[key]
            except KeyError as exc:
                raise AdapterNotRegistered(f"{self.kind} {key!r} is not registered") from exc

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._providers))


class InlineAudienceResolver:
    """Built-in OSS resolver for explicit, versioned recipient snapshots."""

    schema_version = SPI_VERSION
    resolver_key = "manual"

    def resolve(self, tenant_id: UUID, definition: Mapping[str, object]) -> AudienceResolutionResult:
        if not isinstance(tenant_id, UUID):
            raise ValueError("tenant_id must be a UUID")
        if definition.get("schema_version") not in {1, "1"}:
            raise ValueError("inline audience schema_version must be 1")
        if definition.get("resolver", "manual") not in {"manual", "inline"}:
            raise ValueError("audience definition selects a different resolver")
        raw_recipients = definition.get("recipients")
        if not isinstance(raw_recipients, Sequence) or isinstance(raw_recipients, (str, bytes)):
            raise ValueError("inline audience recipients must be an array")
        if len(raw_recipients) > MAX_RECIPIENTS_PER_DEFINITION:
            raise ValueError("inline audience exceeds the recipient limit")
        candidates: list[AudienceCandidate] = []
        for raw in raw_recipients:
            if not isinstance(raw, Mapping):
                raise ValueError("inline audience recipient must be an object")
            personalization = raw.get("personalization", raw.get("personalization_data", {}))
            candidates.append(
                AudienceCandidate(
                    email=str(raw.get("email", "")),
                    recipient_key=str(raw["recipient_key"]) if raw.get("recipient_key") is not None else None,
                    display_name=str(raw.get("display_name", "")),
                    personalization=_bounded_mapping(personalization, "personalization"),
                )
            )
        return AudienceResolutionResult(
            tuple(candidates),
            self.resolver_key,
            evidence={"source": "manual", "candidate_count": len(candidates)},
        )


class _EmailHTMLSanitizer(HTMLParser):
    """Small allowlist sanitizer suitable for already-authored email HTML."""

    ALLOWED_TAGS = frozenset(
        {
            "a",
            "b",
            "blockquote",
            "br",
            "div",
            "em",
            "h1",
            "h2",
            "h3",
            "hr",
            "img",
            "li",
            "ol",
            "p",
            "span",
            "strong",
            "table",
            "tbody",
            "td",
            "th",
            "thead",
            "tr",
            "u",
            "ul",
        }
    )
    VOID_TAGS = frozenset({"br", "hr", "img"})
    ALLOWED_ATTRS = frozenset({"alt", "class", "height", "href", "rel", "src", "style", "target", "title", "width"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object"}:
            self.blocked_depth += 1
            return
        if self.blocked_depth or tag not in self.ALLOWED_TAGS:
            return
        rendered_attrs: list[str] = []
        for name, value in attrs:
            name = name.lower()
            if value is None or name not in self.ALLOWED_ATTRS or name.startswith("on"):
                continue
            if name in {"href", "src"}:
                parsed = urlsplit(value)
                if parsed.scheme.lower() not in {"http", "https", "mailto", "cid", ""}:
                    continue
            escaped = value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
            rendered_attrs.append(f' {name}="{escaped}"')
        suffix = " /" if tag in self.VOID_TAGS else ""
        self.output.append(f"<{tag}{''.join(rendered_attrs)}{suffix}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object"}:
            self.blocked_depth = max(0, self.blocked_depth - 1)
            return
        if not self.blocked_depth and tag in self.ALLOWED_TAGS and tag not in self.VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.output.append(data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def sanitize_email_html(value: str) -> str:
    parser = _EmailHTMLSanitizer()
    parser.feed(value)
    parser.close()
    return "".join(parser.output)


class DjangoTemplateEmailRenderer:
    """Strict renderer: missing variables fail instead of silently blanking."""

    schema_version = SPI_VERSION
    renderer_key = "default"
    _missing = "__SARAISE_MISSING_VARIABLE__"

    def __init__(self) -> None:
        self._engine = Engine(debug=False, string_if_invalid=f"{self._missing}%s")

    def _render(self, source: str, values: Mapping[str, object], *, autoescape: bool) -> str:
        try:
            result = self._engine.from_string(source).render(Context(dict(values), autoescape=autoescape))
        except TemplateSyntaxError as exc:
            raise RenderingError("email template syntax is invalid") from exc
        if self._missing in result:
            raise RenderingError("email template contains an unresolved variable")
        return result

    def render(self, template_snapshot: Mapping[str, object], personalization: Mapping[str, object]) -> RenderedEmail:
        values = _bounded_mapping(personalization, "personalization")
        subject_source = str(template_snapshot.get("subject", ""))
        html_source = str(template_snapshot.get("body_html", template_snapshot.get("html", "")))
        text_source = str(template_snapshot.get("body_text", template_snapshot.get("text", "")))
        preview_source = str(template_snapshot.get("preview_text", ""))
        declared = set(
            _TEMPLATE_VARIABLE.findall("\n".join((subject_source, html_source, text_source, preview_source)))
        )
        if any(name.split(".", 1)[0] not in values for name in declared):
            raise RenderingError("email template contains an unresolved variable")
        return RenderedEmail(
            subject=self._render(subject_source, values, autoescape=False),
            html=sanitize_email_html(self._render(html_source, values, autoescape=True)),
            text=self._render(text_source, values, autoescape=False),
            preview_text=self._render(preview_source, values, autoescape=False),
        )


class DjangoEmailDeliveryGateway:
    """Real Django mail transport protected by timeout and circuit breaker."""

    schema_version = SPI_VERSION
    gateway_key = "django"

    def __init__(self, *, timeout: float | None = None, breaker: CircuitBreaker[object] | None = None) -> None:
        configured = timeout
        if configured is None:
            configured = getattr(settings, "EMAIL_MARKETING_TIMEOUT", None)
        if configured is None:
            configured = getattr(settings, "EMAIL_TIMEOUT", None)
        if configured is None:
            configured = 10.0
        if isinstance(configured, bool) or not isinstance(configured, (int, float)) or configured <= 0:
            raise DeliveryConfigurationError("EMAIL_TIMEOUT must be a positive number")
        self.timeout = float(configured)
        self.breaker = breaker or CircuitBreaker("email_marketing.django_mail", failure_threshold=3, reset_timeout=60)

    @property
    def backend_path(self) -> str:
        return str(getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"))

    def _configuration_code(self) -> str | None:
        if self.backend_path in SIMULATED_DJANGO_BACKENDS:
            return "simulated_backend"
        if self.backend_path not in SAFE_DJANGO_BACKENDS and not bool(
            getattr(settings, "EMAIL_MARKETING_ALLOW_CUSTOM_BACKEND", False)
        ):
            return "custom_backend_not_allowlisted"
        return None

    def submit(
        self, message: DeliveryMessage, idempotency_key: str, correlation_id: str
    ) -> OperationResult[DeliveryReceipt]:
        if not _SAFE_IDENTIFIER.fullmatch(idempotency_key) or not _SAFE_IDENTIFIER.fullmatch(correlation_id):
            raise ValueError("idempotency and correlation identifiers must be bounded and safe")
        configuration_error = self._configuration_code()
        if configuration_error:
            return OperationResult.failure(configuration_error, detail="A real delivery backend is not configured")
        message_id = make_msgid(domain="saraise.local")
        headers = {
            **dict(message.headers),
            "Message-ID": message_id,
            "X-SARAISE-Idempotency-Key": idempotency_key,
            "X-Correlation-ID": correlation_id,
        }
        display_from = f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email

        def deliver() -> int:
            try:
                connection = get_connection(fail_silently=False, timeout=self.timeout)
                email = EmailMultiAlternatives(
                    subject=message.rendered.subject,
                    body=message.rendered.text,
                    from_email=display_from,
                    to=[message.recipient],
                    reply_to=[message.reply_to] if message.reply_to else None,
                    headers=headers,
                    connection=connection,
                )
                if message.rendered.html:
                    email.attach_alternative(message.rendered.html, "text/html")
                return email.send(fail_silently=False)
            except (TimeoutError, OSError) as exc:
                raise _AmbiguousDeliveryTimeout("delivery acknowledgement unavailable") from exc
            except Exception as exc:
                raise _DeliveryTransportFailure("delivery transport failed") from exc

        try:
            sent = self.breaker.call(deliver)
        except CircuitBreakerError:
            return OperationResult.failure(
                "circuit_open", retryable=True, detail="Delivery gateway is temporarily unavailable"
            )
        except _AmbiguousDeliveryTimeout:
            # SMTP timeouts after DATA may be ambiguous. Never blind-retry.
            return OperationResult.failure(
                "transport_timeout",
                retryable=False,
                ambiguous=True,
                detail="Delivery acknowledgement was not received",
            )
        except _DeliveryTransportFailure:
            return OperationResult.failure("transport_failure", retryable=True, detail="Delivery transport failed")
        if sent != 1:
            return OperationResult.failure(
                "not_acknowledged", retryable=True, detail="Delivery backend did not acknowledge one message"
            )
        receipt = DeliveryReceipt(
            provider_message_id=message_id,
            gateway_key=self.gateway_key,
            acknowledgement="transport_accepted",
            accepted_at=timezone.now(),
            evidence={"backend": self.backend_path, "messages_accepted": 1},
        )
        return OperationResult.success(receipt, code="transport_accepted")

    def lookup(self, provider_message_id: str) -> OperationResult[DeliveryReceipt]:
        if not provider_message_id or len(provider_message_id) > 255:
            raise ValueError("provider_message_id is invalid")
        return OperationResult.failure(
            "lookup_unsupported",
            ambiguous=True,
            detail="The configured Django transport cannot reconcile provider delivery state",
        )

    def health(self) -> DependencyHealth:
        now = timezone.now()
        configuration_error = self._configuration_code()
        if configuration_error:
            return DependencyHealth(False, configuration_error, now, self.breaker.state.value, False)

        def probe() -> bool:
            connection = get_connection(fail_silently=False, timeout=self.timeout)
            opened = bool(connection.open())
            connection.close()
            return opened

        try:
            available = bool(self.breaker.call(probe))
            return DependencyHealth(
                available, "ready" if available else "connection_rejected", now, self.breaker.state.value, False
            )
        except CircuitBreakerError:
            return DependencyHealth(False, "circuit_open", now, "open", False)
        except Exception:
            return DependencyHealth(False, "dependency_unavailable", now, self.breaker.state.value, False)


audience_resolver_registry: ExtensionRegistry[AudienceResolver] = ExtensionRegistry("audience resolver")
renderer_registry: ExtensionRegistry[EmailRenderer] = ExtensionRegistry("email renderer")
delivery_gateway_registry: ExtensionRegistry[EmailDeliveryGateway] = ExtensionRegistry("delivery gateway")
provider_event_verifier_registry: ExtensionRegistry[ProviderEventVerifier] = ExtensionRegistry(
    "provider event verifier"
)

_INLINE_RESOLVER = InlineAudienceResolver()
_DJANGO_RENDERER = DjangoTemplateEmailRenderer()
_DJANGO_GATEWAY: DjangoEmailDeliveryGateway | None = None


def register_builtin_adapters() -> None:
    """Install OSS adapters idempotently without permitting replacement."""
    global _DJANGO_GATEWAY
    audience_resolver_registry.register(_INLINE_RESOLVER.resolver_key, _INLINE_RESOLVER)
    renderer_registry.register(_DJANGO_RENDERER.renderer_key, _DJANGO_RENDERER)
    if _DJANGO_GATEWAY is None:
        _DJANGO_GATEWAY = DjangoEmailDeliveryGateway()
    delivery_gateway_registry.register(_DJANGO_GATEWAY.gateway_key, _DJANGO_GATEWAY)


def get_audience_resolver(key: str = "manual") -> AudienceResolver:
    return audience_resolver_registry.get(key)


def get_renderer(key: str = "default") -> EmailRenderer:
    return renderer_registry.get(key)


def get_delivery_gateway(key: str = "django") -> EmailDeliveryGateway:
    return delivery_gateway_registry.get(key)


def get_provider_event_verifier(key: str) -> ProviderEventVerifier:
    return provider_event_verifier_registry.get(key)


def hash_link_url(url: str) -> str:
    """Create analytics evidence without storing a recipient's destination URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


__all__ = [
    "AdapterAlreadyRegistered",
    "AdapterError",
    "AdapterNotRegistered",
    "AudienceCandidate",
    "AudienceResolutionResult",
    "AudienceResolver",
    "DeliveryConfigurationError",
    "DeliveryMessage",
    "DeliveryReceipt",
    "DependencyHealth",
    "DjangoEmailDeliveryGateway",
    "DjangoTemplateEmailRenderer",
    "EmailDeliveryGateway",
    "EmailRenderer",
    "EligibilityDecision",
    "ExtensionRegistry",
    "InlineAudienceResolver",
    "InvalidAdapterOutput",
    "OperationResult",
    "ProviderEventVerifier",
    "RenderedEmail",
    "RenderingError",
    "SPI_VERSION",
    "VerifiedDeliveryEvent",
    "audience_resolver_registry",
    "delivery_gateway_registry",
    "get_audience_resolver",
    "get_delivery_gateway",
    "get_provider_event_verifier",
    "get_renderer",
    "hash_link_url",
    "normalize_email",
    "provider_event_verifier_registry",
    "register_builtin_adapters",
    "renderer_registry",
    "sanitize_email_html",
]
