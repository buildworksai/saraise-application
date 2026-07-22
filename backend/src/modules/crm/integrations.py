"""Typed, resilient CRM provider ports and paid-module extension contracts.

No adapter receives a URL from request data. Network destinations come only
from Django settings and are revalidated by :class:`ResilientHttpClient`.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from django.conf import settings

from src.core.resilience import (
    CircuitBreakerError,
    DependencyConnectionError,
    DependencyResponseError,
    DependencyTimeoutError,
    HttpClientConfigurationError,
    ResilientHttpClient,
    ResilientHttpError,
    UnsafeDestinationError,
)

logger = logging.getLogger("saraise.crm.integrations")

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class CRMIntegrationError(RuntimeError):
    """Base class carrying a stable code safe for clients and telemetry."""

    code = "INTEGRATION_FAILURE"

    def __init__(self, message: str, *, dependency: str | None = None) -> None:
        self.dependency = dependency
        super().__init__(message)


class IntegrationUnavailable(CRMIntegrationError):
    code = "INTEGRATION_UNAVAILABLE"


class IntegrationTimeout(IntegrationUnavailable):
    code = "INTEGRATION_TIMEOUT"


class IntegrationCircuitOpen(IntegrationUnavailable):
    code = "INTEGRATION_CIRCUIT_OPEN"


class InvalidIntegrationResponse(CRMIntegrationError):
    code = "INVALID_PROVIDER_RESPONSE"


class ExtensionConflictError(CRMIntegrationError):
    code = "EXTENSION_CONFLICT"


Primitive = str | int | bool | Decimal | None


def _safe_factors(value: object) -> Mapping[str, Primitive]:
    if not isinstance(value, Mapping):
        raise InvalidIntegrationResponse("Provider factors must be an object")
    if len(value) > 50:
        raise InvalidIntegrationResponse("Provider returned too many evidence factors")
    factors: dict[str, Primitive] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if not _SAFE_IDENTIFIER.fullmatch(key):
            raise InvalidIntegrationResponse("Provider returned an invalid evidence factor name")
        if isinstance(raw_value, float):
            raw_value = Decimal(str(raw_value))
        if not isinstance(raw_value, (str, int, bool, Decimal)) and raw_value is not None:
            raise InvalidIntegrationResponse("Provider evidence factors must contain scalar values")
        if isinstance(raw_value, str) and len(raw_value) > 500:
            raise InvalidIntegrationResponse("Provider evidence factor is too long")
        factors[key] = raw_value
    return factors


def _required_string(value: object, field: str, *, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise InvalidIntegrationResponse(f"Provider {field} must be a bounded non-empty string")
    return value.strip()


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidIntegrationResponse(f"Provider {field} must be a decimal") from exc
    if not parsed.is_finite():
        raise InvalidIntegrationResponse(f"Provider {field} must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class LeadScoreResult:
    provider: str
    model: str
    score: int
    grade: str
    factors: Mapping[str, Primitive]
    provider_request_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "score": self.score,
            "grade": self.grade,
            "factors": dict(self.factors),
            "provider_request_id": self.provider_request_id,
        }


@dataclass(frozen=True, slots=True)
class RevenuePredictionResult:
    provider: str
    model: str
    amount: Decimal
    currency: str
    confidence: Decimal | None
    factors: Mapping[str, Primitive]
    as_of: str
    provider_request_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "amount": str(self.amount),
            "currency": self.currency,
            "confidence": str(self.confidence) if self.confidence is not None else None,
            "factors": dict(self.factors),
            "as_of": self.as_of,
            "provider_request_id": self.provider_request_id,
        }


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    configured: bool
    available: bool
    code: str
    circuit_state: str


@dataclass(frozen=True, slots=True)
class _ProviderConfiguration:
    dependency: str
    endpoint: str
    provider: str
    model: str


def _configuration(setting_name: str) -> _ProviderConfiguration:
    value = getattr(settings, setting_name, None)
    if not isinstance(value, Mapping):
        raise IntegrationUnavailable(f"{setting_name} is not configured", dependency=setting_name)
    required = {key: value.get(key) for key in ("dependency", "endpoint", "provider", "model")}
    if any(not isinstance(item, str) or not item.strip() for item in required.values()):
        raise IntegrationUnavailable(f"{setting_name} is incomplete", dependency=setting_name)
    endpoint = str(required["endpoint"]).strip()
    if not endpoint.startswith("/"):
        raise IntegrationUnavailable(f"{setting_name}.endpoint must be a relative path", dependency=setting_name)
    return _ProviderConfiguration(
        dependency=str(required["dependency"]).strip(),
        endpoint=endpoint,
        provider=str(required["provider"]).strip(),
        model=str(required["model"]).strip(),
    )


def _correlation(value: str) -> str:
    if not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError("correlation_id must be a bounded safe identifier")
    return value


class _JsonProviderClient:
    setting_name: str
    operation: str

    def __init__(self, configuration: _ProviderConfiguration, client: ResilientHttpClient) -> None:
        self.configuration = configuration
        self.client = client

    def _post(self, payload: Mapping[str, object], correlation_id: str) -> Mapping[str, object]:
        if not isinstance(payload, Mapping):
            raise TypeError("provider payload must be a mapping")
        correlation = _correlation(correlation_id)
        dependency = self.configuration.dependency
        try:
            response = self.client.post(
                self.configuration.endpoint,
                dependency=dependency,
                correlation_id=correlation,
                headers={"Idempotency-Key": correlation, "Accept": "application/json"},
                json=dict(payload),
            )
        except DependencyTimeoutError as exc:
            self._log("unavailable", IntegrationTimeout.code, dependency)
            raise IntegrationTimeout("Provider request timed out", dependency=dependency) from exc
        except CircuitBreakerError as exc:
            self._log("unavailable", IntegrationCircuitOpen.code, dependency)
            raise IntegrationCircuitOpen("Provider circuit is open", dependency=dependency) from exc
        except (DependencyConnectionError, DependencyResponseError) as exc:
            self._log("unavailable", IntegrationUnavailable.code, dependency)
            raise IntegrationUnavailable("Provider is unavailable", dependency=dependency) from exc
        except (UnsafeDestinationError, HttpClientConfigurationError) as exc:
            self._log("failure", "EGRESS_POLICY_FAILURE", dependency)
            raise IntegrationUnavailable("Provider egress policy is unavailable", dependency=dependency) from exc
        except ResilientHttpError as exc:
            self._log("failure", CRMIntegrationError.code, dependency)
            raise CRMIntegrationError("Provider request failed", dependency=dependency) from exc

        if not 200 <= response.status_code < 300:
            self._log("failure", "PROVIDER_REJECTED_REQUEST", dependency)
            raise CRMIntegrationError("Provider rejected the request", dependency=dependency)
        try:
            decoded = response.json()
        except (TypeError, ValueError) as exc:
            self._log("failure", InvalidIntegrationResponse.code, dependency)
            raise InvalidIntegrationResponse("Provider returned malformed JSON", dependency=dependency) from exc
        if not isinstance(decoded, Mapping):
            raise InvalidIntegrationResponse("Provider response must be an object", dependency=dependency)
        return decoded

    def health(self) -> DependencyHealth:
        try:
            state = self.client.get_breaker(self.configuration.dependency).state
            value = str(getattr(state, "value", state))
            return DependencyHealth(True, value != "open", "ready" if value != "open" else "circuit_open", value)
        except Exception:
            return DependencyHealth(True, False, "configuration_unavailable", "unknown")

    def _log(self, outcome: str, code: str, dependency: str) -> None:
        logger.warning(
            "crm dependency operation",
            extra={
                "event": "crm.dependency.operation",
                "module_name": "crm",
                "operation": self.operation,
                "outcome": outcome,
                "dependency": dependency,
                "attempt_count": 1,
                "error_code": code,
            },
        )


class LeadScoringClient(_JsonProviderClient):
    setting_name = "CRM_LEAD_SCORING_PROVIDER"
    operation = "lead_scoring"

    def score_lead(self, payload: Mapping[str, object], *, correlation_id: str) -> LeadScoreResult:
        body = self._post(payload, correlation_id)
        raw_score = body.get("score")
        if isinstance(raw_score, bool) or not isinstance(raw_score, int) or not 0 <= raw_score <= 100:
            raise InvalidIntegrationResponse("Provider score must be an integer from 0 to 100")
        grade = "A" if raw_score >= 80 else "B" if raw_score >= 60 else "C" if raw_score >= 40 else "D"
        supplied_grade = body.get("grade")
        if supplied_grade is not None and supplied_grade != grade:
            raise InvalidIntegrationResponse("Provider grade does not correspond to score")
        provider_request_id = body.get("provider_request_id")
        if provider_request_id is not None:
            provider_request_id = _required_string(provider_request_id, "provider_request_id", maximum=128)
        return LeadScoreResult(
            provider=self.configuration.provider,
            model=self.configuration.model,
            score=raw_score,
            grade=grade,
            factors=_safe_factors(body.get("factors")),
            provider_request_id=provider_request_id,
        )


class RevenuePredictionClient(_JsonProviderClient):
    setting_name = "CRM_REVENUE_PREDICTION_PROVIDER"
    operation = "revenue_prediction"

    def predict_revenue(self, payload: Mapping[str, object], *, correlation_id: str) -> RevenuePredictionResult:
        body = self._post(payload, correlation_id)
        amount = _decimal(body.get("amount"), "amount")
        if amount < 0:
            raise InvalidIntegrationResponse("Provider amount cannot be negative")
        currency = _required_string(body.get("currency"), "currency", maximum=3).upper()
        if not _CURRENCY.fullmatch(currency):
            raise InvalidIntegrationResponse("Provider currency must be ISO-4217 alpha-3")
        raw_confidence = body.get("confidence")
        confidence = None if raw_confidence is None else _decimal(raw_confidence, "confidence")
        if confidence is not None and not Decimal("0") <= confidence <= Decimal("1"):
            raise InvalidIntegrationResponse("Provider confidence must be from 0 to 1")
        as_of = _required_string(body.get("as_of"), "as_of", maximum=64)
        provider_request_id = body.get("provider_request_id")
        if provider_request_id is not None:
            provider_request_id = _required_string(provider_request_id, "provider_request_id", maximum=128)
        return RevenuePredictionResult(
            provider=self.configuration.provider,
            model=self.configuration.model,
            amount=amount,
            currency=currency,
            confidence=confidence,
            factors=_safe_factors(body.get("factors")),
            as_of=as_of,
            provider_request_id=provider_request_id,
        )


def _client(setting_name: str, client_type: type[_JsonProviderClient]) -> _JsonProviderClient:
    configuration = _configuration(setting_name)
    try:
        resilient_client = ResilientHttpClient()
    except HttpClientConfigurationError as exc:
        raise IntegrationUnavailable(
            "Outbound dependency allowlist is not configured", dependency=configuration.dependency
        ) from exc
    return client_type(configuration, resilient_client)


def get_scoring_client() -> LeadScoringClient:
    """Return a configured scoring adapter or raise explicit unavailability."""

    return _client("CRM_LEAD_SCORING_PROVIDER", LeadScoringClient)  # type: ignore[return-value]


def get_revenue_prediction_client() -> RevenuePredictionClient:
    """Return a configured prediction adapter or raise explicit unavailability."""

    return _client("CRM_REVENUE_PREDICTION_PROVIDER", RevenuePredictionClient)  # type: ignore[return-value]


# ----- Stable paid-module service ABI -------------------------------------


@dataclass(frozen=True, slots=True)
class ExtensionContext:
    tenant_id: UUID
    actor_id: str | None
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class QualificationSignal:
    namespace: str
    value: Decimal
    evidence_code: str


@dataclass(frozen=True, slots=True)
class AccountMatch:
    external_reference: str
    confidence: Decimal | None
    evidence_codes: Sequence[str]


@dataclass(frozen=True, slots=True)
class ProductReference:
    product_id: UUID
    active: bool
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class TerritoryAssignment:
    territory_id: UUID
    owner_id: UUID | None
    evidence_code: str


@dataclass(frozen=True, slots=True)
class FulfillmentRequest:
    opportunity_id: UUID
    account_id: UUID
    amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class FulfillmentAcknowledgement:
    accepted: bool
    external_order_id: UUID | None
    acknowledgement_id: UUID
    code: str
    tenant_id: UUID | None = None
    opportunity_id: UUID | None = None
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class SalesOrderAcknowledgement:
    """Verified internal event evidence used to link a won opportunity."""

    event_id: UUID
    tenant_id: UUID
    opportunity_id: UUID
    order_id: UUID
    correlation_id: str


def parse_sales_order_acknowledgement(
    event: Mapping[str, object],
    *,
    expected_tenant_id: UUID,
    verified_delivery: bool,
) -> SalesOrderAcknowledgement:
    """Validate the event ABI after the trusted bus verifies its delivery."""

    if verified_delivery is not True:
        raise InvalidIntegrationResponse("Sales-order acknowledgement delivery is not verified")
    if not isinstance(event, Mapping) or event.get("event_type") != "sales_management.order.created.v1":
        raise InvalidIntegrationResponse("Unexpected sales-order acknowledgement event type")

    def event_uuid(field: str) -> UUID:
        try:
            return UUID(str(event[field]))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise InvalidIntegrationResponse(f"Sales-order acknowledgement requires UUID {field}") from exc

    tenant_id = event_uuid("tenant_id")
    if tenant_id != expected_tenant_id:
        raise InvalidIntegrationResponse("Sales-order acknowledgement belongs to another tenant")
    correlation_id = event.get("correlation_id")
    if not isinstance(correlation_id, str) or not _SAFE_IDENTIFIER.fullmatch(correlation_id):
        raise InvalidIntegrationResponse("Sales-order acknowledgement correlation_id is invalid")
    return SalesOrderAcknowledgement(
        event_id=event_uuid("event_id"),
        tenant_id=tenant_id,
        opportunity_id=event_uuid("opportunity_id"),
        order_id=event_uuid("order_id"),
        correlation_id=correlation_id,
    )


def verify_fulfillment_acknowledgement(
    event: Mapping[str, object],
) -> FulfillmentAcknowledgement:
    """Verify trusted-bus evidence and decode a successful order link.

    The event dispatcher sets ``delivery_verified`` only after authenticating
    the producer and schema. CRM never infers verification from an order ID.
    """

    if not isinstance(event, Mapping) or event.get("delivery_verified") is not True:
        raise InvalidIntegrationResponse("Fulfillment acknowledgement delivery is not verified")
    if event.get("event_type") != "sales_management.order.created.v1":
        raise InvalidIntegrationResponse("Unexpected fulfillment acknowledgement event type")

    def event_uuid(field: str) -> UUID:
        try:
            return UUID(str(event[field]))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise InvalidIntegrationResponse(f"Fulfillment acknowledgement requires UUID {field}") from exc

    correlation_id = event.get("correlation_id")
    if not isinstance(correlation_id, str) or not _SAFE_IDENTIFIER.fullmatch(correlation_id):
        raise InvalidIntegrationResponse("Fulfillment acknowledgement correlation_id is invalid")
    return FulfillmentAcknowledgement(
        accepted=True,
        external_order_id=event_uuid("order_id"),
        acknowledgement_id=event_uuid("event_id"),
        code="order_created",
        tenant_id=event_uuid("tenant_id"),
        opportunity_id=event_uuid("opportunity_id"),
        correlation_id=correlation_id,
    )


@runtime_checkable
class QualificationSignalProvider(Protocol):
    schema_version: str

    def signals(self, context: ExtensionContext, lead_id: UUID) -> Sequence[QualificationSignal]: ...


@runtime_checkable
class AccountEnrichmentProvider(Protocol):
    schema_version: str

    def find_matches(
        self, context: ExtensionContext, *, normalized_name: str, website_domain: str | None
    ) -> Sequence[AccountMatch]: ...


@runtime_checkable
class ProductReferenceResolver(Protocol):
    schema_version: str

    def resolve(self, context: ExtensionContext, product_ids: Sequence[UUID]) -> Sequence[ProductReference]: ...


@runtime_checkable
class TerritoryAssignmentProvider(Protocol):
    schema_version: str

    def assign(self, context: ExtensionContext, account_id: UUID) -> TerritoryAssignment | None: ...


@runtime_checkable
class PostWinFulfillmentProvider(Protocol):
    schema_version: str

    def request_fulfillment(
        self, context: ExtensionContext, request: FulfillmentRequest
    ) -> FulfillmentAcknowledgement: ...


ExtensionProvider = TypeVar("ExtensionProvider")


class CRMExtensionRegistry:
    """Deterministic registration/arbitration with explicit uninstall lifecycle."""

    _capabilities: Final = frozenset(
        {"qualification", "account_enrichment", "product_reference", "territory", "fulfillment"}
    )

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], tuple[int, object]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        capability: str,
        provider_key: str,
        provider: ExtensionProvider,
        *,
        priority: int = 100,
    ) -> ExtensionProvider:
        if capability not in self._capabilities:
            raise ValueError("unknown CRM extension capability")
        if not _SAFE_IDENTIFIER.fullmatch(provider_key):
            raise ValueError("provider_key must be a stable identifier")
        if getattr(provider, "schema_version", None) != "1.0":
            raise ValueError("CRM extension schema_version must be 1.0")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 10_000:
            raise ValueError("priority must be an integer from 0 to 10000")
        key = (capability, provider_key)
        with self._lock:
            if key in self._entries:
                raise ExtensionConflictError(f"Extension {provider_key!r} is already registered")
            self._entries[key] = (priority, provider)
        return provider

    def resolve(self, capability: str) -> tuple[object, ...]:
        if capability not in self._capabilities:
            raise ValueError("unknown CRM extension capability")
        with self._lock:
            values = [
                (priority, key, provider)
                for (registered_capability, key), (priority, provider) in self._entries.items()
                if registered_capability == capability
            ]
        return tuple(provider for _, _, provider in sorted(values, key=lambda item: (item[0], item[1])))

    def unregister(self, capability: str, provider_key: str) -> object | None:
        with self._lock:
            value = self._entries.pop((capability, provider_key), None)
        return value[1] if value else None


extension_registry: Final = CRMExtensionRegistry()


__all__ = [
    "AccountEnrichmentProvider",
    "AccountMatch",
    "CRMExtensionRegistry",
    "CRMIntegrationError",
    "DependencyHealth",
    "ExtensionConflictError",
    "ExtensionContext",
    "FulfillmentAcknowledgement",
    "FulfillmentRequest",
    "IntegrationCircuitOpen",
    "IntegrationTimeout",
    "IntegrationUnavailable",
    "InvalidIntegrationResponse",
    "LeadScoreResult",
    "LeadScoringClient",
    "PostWinFulfillmentProvider",
    "ProductReference",
    "ProductReferenceResolver",
    "QualificationSignal",
    "QualificationSignalProvider",
    "RevenuePredictionClient",
    "RevenuePredictionResult",
    "SalesOrderAcknowledgement",
    "TerritoryAssignment",
    "TerritoryAssignmentProvider",
    "extension_registry",
    "get_revenue_prediction_client",
    "get_scoring_client",
    "parse_sales_order_acknowledgement",
    "verify_fulfillment_acknowledgement",
]
