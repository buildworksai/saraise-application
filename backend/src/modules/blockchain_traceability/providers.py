"""Versioned provider-neutral extension surface for traceability connectors.

Foundation code never chooses a simulated fallback.  Paid modules register
real ledger, issuer, or inventory adapters during their own application
lifecycle and may unregister them cleanly during tests or hot replacement.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable
from uuid import UUID

from django.conf import settings

from .hashing import canonical_json, sha256_hex


class ProviderError(RuntimeError):
    """Base class for sanitized provider failures."""


class ProviderUnavailableError(ProviderError):
    """Raised when a configured dependency cannot currently execute."""


class ProviderTimeoutError(ProviderUnavailableError):
    """Raised when a bounded provider call exceeds its deadline."""


class ProviderCircuitOpenError(ProviderUnavailableError):
    """Raised when the shared dependency circuit is open."""


class InvalidProviderResponseError(ProviderError):
    """Raised when provider evidence is malformed or unverifiable."""


class AdapterRegistrationError(ValueError):
    """Raised when extension registration would be ambiguous."""


class AdapterNotRegisteredError(ProviderUnavailableError):
    """Raised when an explicitly requested adapter is absent."""


@dataclass(frozen=True, slots=True)
class CapabilityMetadata:
    key: str
    display_name: str
    version: str = "1.0"
    capabilities: tuple[str, ...] = ()
    option_schema: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = False


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    available: bool
    code: str
    message: str = ""
    checked_at: datetime | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = False


@dataclass(frozen=True, slots=True)
class SubmissionReceipt:
    accepted: bool
    provider_transaction_id: str = ""
    transaction_hash: str = ""
    submitted_at: datetime | None = None
    receipt: Mapping[str, Any] = field(default_factory=dict)
    failure_code: str = ""
    failure_message: str = ""
    simulated: bool = False

    def __post_init__(self) -> None:
        if self.accepted and not (self.provider_transaction_id or self.transaction_hash):
            raise InvalidProviderResponseError("accepted submissions require transaction identity")


@dataclass(frozen=True, slots=True)
class AnchorReceipt:
    provider_transaction_id: str
    transaction_hash: str = ""
    block_number: int | None = None
    block_hash: str = ""
    confirmations: int = 0
    final: bool = False
    observed_at: datetime | None = None
    receipt: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = False

    def __post_init__(self) -> None:
        if self.confirmations < 0:
            raise InvalidProviderResponseError("confirmations cannot be negative")
        if self.final and (self.block_number is None or not self.block_hash):
            raise InvalidProviderResponseError("final receipts require block evidence")


@dataclass(frozen=True, slots=True)
class ProofResult:
    verified: bool
    reason_code: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = False

    def __post_init__(self) -> None:
        if self.verified and self.simulated:
            raise InvalidProviderResponseError("simulated providers cannot return verified proof")
        if self.verified and not self.evidence:
            raise InvalidProviderResponseError("verified proof requires concrete evidence")


@dataclass(frozen=True, slots=True)
class SignatureResult:
    signature_algorithm: str
    signature: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    simulated: bool = False

    def __post_init__(self) -> None:
        if not self.signature_algorithm.strip() or not self.signature:
            raise InvalidProviderResponseError("signature results require an algorithm and signature")


@dataclass(frozen=True, slots=True)
class InventoryReferenceResult:
    valid: bool
    reason_code: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InventoryReferenceSnapshot:
    product_ref: str
    batch_ref: str
    display_name: str = ""
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentReferenceResult:
    valid: bool
    reason_code: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class LedgerProviderAdapter(Protocol):
    provider_type: str

    def capability_metadata(self) -> CapabilityMetadata: ...

    def validate_options(self, options: Mapping[str, Any]) -> None: ...

    def health(self, network: Any) -> ProviderHealth: ...

    def submit_anchor(self, network: Any, anchor: Any, idempotency_key: str) -> SubmissionReceipt: ...

    def get_receipt(self, network: Any, provider_transaction_id: str) -> AnchorReceipt: ...

    def verify_anchor(self, network: Any, anchor: Any) -> ProofResult: ...


@runtime_checkable
class CredentialIssuerAdapter(Protocol):
    issuer_type: str

    def capability_metadata(self) -> CapabilityMetadata: ...

    def sign_claims(self, tenant_id: UUID, issuer_key_ref: str, canonical_claims: bytes) -> SignatureResult: ...

    def verify_signature(self, tenant_id: UUID, credential: Any) -> ProofResult: ...


@runtime_checkable
class InventoryReferenceResolver(Protocol):
    resolver_type: str

    def capability_metadata(self) -> CapabilityMetadata: ...

    def validate_reference(self, tenant_id: UUID, product_ref: str, batch_ref: str) -> InventoryReferenceResult: ...

    def display_snapshot(self, tenant_id: UUID, product_ref: str, batch_ref: str) -> InventoryReferenceSnapshot: ...


@runtime_checkable
class DocumentReferenceResolver(Protocol):
    resolver_type: str

    def capability_metadata(self) -> CapabilityMetadata: ...

    def validate_reference(self, tenant_id: UUID, document_ref: UUID) -> DocumentReferenceResult: ...


AdapterT = TypeVar("AdapterT")


class AdapterRegistry(Generic[AdapterT]):
    """Thread-safe deterministic registry used by foundation and paid modules."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: dict[str, AdapterT] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _key(value: str) -> str:
        key = value.strip().lower()
        if not key:
            raise AdapterRegistrationError("adapter key must not be blank")
        return key

    def register(self, key: str, adapter: AdapterT) -> AdapterT:
        normalized = self._key(key)
        with self._lock:
            if normalized in self._items:
                raise AdapterRegistrationError(f"{self.kind} adapter {normalized!r} is already registered")
            self._items[normalized] = adapter
        return adapter

    def unregister(self, key: str) -> AdapterT | None:
        with self._lock:
            return self._items.pop(self._key(key), None)

    def get(self, key: str) -> AdapterT:
        normalized = self._key(key)
        with self._lock:
            try:
                return self._items[normalized]
            except KeyError as exc:
                raise AdapterNotRegisteredError(f"No {self.kind} adapter is registered for {normalized!r}") from exc

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._items))

    def descriptors(self) -> tuple[CapabilityMetadata, ...]:
        with self._lock:
            adapters = tuple(self._items[key] for key in sorted(self._items))
        descriptors: list[CapabilityMetadata] = []
        for adapter in adapters:
            descriptor = getattr(adapter, "capability_metadata", None)
            if not callable(descriptor):
                raise AdapterRegistrationError(f"{self.kind} adapter does not expose capability metadata")
            metadata = descriptor()
            if not isinstance(metadata, CapabilityMetadata):
                raise AdapterRegistrationError(f"{self.kind} adapter returned invalid capability metadata")
            descriptors.append(metadata)
        return tuple(descriptors)

    def clear(self) -> None:
        """Remove every adapter; intended for deterministic test teardown."""

        with self._lock:
            self._items.clear()


ledger_provider_registry: AdapterRegistry[LedgerProviderAdapter] = AdapterRegistry("ledger provider")
credential_issuer_registry: AdapterRegistry[CredentialIssuerAdapter] = AdapterRegistry("credential issuer")
inventory_resolver_registry: AdapterRegistry[InventoryReferenceResolver] = AdapterRegistry("inventory resolver")
document_resolver_registry: AdapterRegistry[DocumentReferenceResolver] = AdapterRegistry("document resolver")


def get_ledger_provider(provider_type: str) -> LedgerProviderAdapter:
    return ledger_provider_registry.get(provider_type)


def get_credential_issuer(issuer_type: str) -> CredentialIssuerAdapter:
    return credential_issuer_registry.get(issuer_type)


def get_inventory_resolver(resolver_type: str = "default") -> InventoryReferenceResolver:
    return inventory_resolver_registry.get(resolver_type)


def get_document_resolver(resolver_type: str = "default") -> DocumentReferenceResolver:
    return document_resolver_registry.get(resolver_type)


def list_provider_capabilities() -> dict[str, tuple[CapabilityMetadata, ...]]:
    """Return stable, secret-free catalogs for UI configuration and health."""

    return {
        "ledger_providers": ledger_provider_registry.descriptors(),
        "credential_issuers": credential_issuer_registry.descriptors(),
        "inventory_resolvers": inventory_resolver_registry.descriptors(),
        "document_resolvers": document_resolver_registry.descriptors(),
    }


class DjangoSigningCredentialIssuer:
    """Real OSS credential issuer backed by Django's tenant-salted HMAC signer.

    The adapter stores only a stable key reference.  The configured SECRET_KEY
    is never returned, persisted, or logged, and every tenant receives a
    distinct signing salt.
    """

    issuer_type = "django_signing_v1"
    issuer_key_ref = "django:secret-key:v1"

    def capability_metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            key=self.issuer_type,
            display_name="Built-in Django signing",
            capabilities=("claims.sign", "claims.verify"),
            simulated=False,
        )

    @staticmethod
    def _signer(tenant_id: UUID, issuer_key_ref: str) -> Any:
        from django.core.signing import Signer

        if issuer_key_ref != DjangoSigningCredentialIssuer.issuer_key_ref:
            raise ProviderUnavailableError("the issuer key reference is not available")
        return Signer(
            key=settings.SECRET_KEY,
            salt=f"saraise.blockchain_traceability.{tenant_id}.{issuer_key_ref}",
            algorithm="sha256",
        )

    def sign_claims(self, tenant_id: UUID, issuer_key_ref: str, canonical_claims: bytes) -> SignatureResult:
        if not canonical_claims:
            raise InvalidProviderResponseError("canonical claims cannot be empty")
        value = canonical_claims.decode("utf-8")
        signature = self._signer(tenant_id, issuer_key_ref).signature(value)
        return SignatureResult(
            signature_algorithm="hmac-sha256",
            signature=signature,
            evidence={"claims_hash": sha256_hex(canonical_claims), "issuer_key_ref": issuer_key_ref},
        )

    def verify_signature(self, tenant_id: UUID, credential: Any) -> ProofResult:
        try:
            canonical_claims = canonical_json(credential.claims)
            expected_claims_hash = sha256_hex(canonical_claims)
            expected_signature = self._signer(tenant_id, credential.issuer_key_ref).signature(
                canonical_claims.decode("utf-8")
            )
            import hmac

            verified = hmac.compare_digest(expected_claims_hash, credential.claims_hash) and hmac.compare_digest(
                expected_signature, credential.signature
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidProviderResponseError("credential signing evidence is malformed") from exc
        return ProofResult(
            verified=verified,
            reason_code="SIGNATURE_VALID" if verified else "SIGNATURE_INVALID",
            evidence={"claims_hash": expected_claims_hash, "signature_algorithm": "hmac-sha256"},
        )


def register_builtin_adapters() -> None:
    """Register foundation adapters without masking a competing owner."""

    candidate = DjangoSigningCredentialIssuer()
    try:
        existing = credential_issuer_registry.get(candidate.issuer_type)
    except AdapterNotRegisteredError:
        credential_issuer_registry.register(candidate.issuer_type, candidate)
        return
    identity = lambda value: (type(value).__module__, type(value).__qualname__)
    if identity(existing) != identity(candidate):
        raise AdapterRegistrationError(
            f"credential issuer {candidate.issuer_type!r} is owned by a competing adapter"
        )
