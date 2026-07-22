"""Versioned extension surface for commercial asset-management modules.

The OSS asset domain deliberately owns this small SPI.  Commercial or industry
modules may contribute presentation tabs, lifecycle actions, additional schema
fields, and physical-identity providers without importing this module's ORM.

Registration is process-local and is expected to happen from a Django
``AppConfig.ready`` hook.  A registration is immutable, rejected when it is not
compatible with :data:`ASSET_EXTENSION_SPI_VERSION`, and can only be removed
with the opaque handle returned to its owner.  Discovery never returns an
implementation object: callers must resolve a capability again with the same
tenant and entitlement context immediately before invoking it.
"""

from __future__ import annotations

import re
import secrets
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable


class ExtensionRegistrationError(ValueError):
    """Base error for an invalid extension registration."""


class ExtensionCompatibilityError(ExtensionRegistrationError):
    """Raised when a contribution does not support the current SPI version."""


class DuplicateCapabilityError(ExtensionRegistrationError):
    """Raised when a capability identifier is already registered."""


class UnknownCapabilityError(LookupError):
    """Raised when resolving a capability that has not been registered."""


class CapabilityUnavailableError(PermissionError):
    """Raised when a known capability is unavailable for the requesting tenant."""

    def __init__(self, capability_id: str, availability: "CapabilityAvailability") -> None:
        self.capability_id = capability_id
        self.availability = availability
        super().__init__(f"{capability_id}: {availability.reason}")


@dataclass(frozen=True, order=True)
class SemanticVersion:
    """Strict SemVer core version used by the extension compatibility contract."""

    major: int
    minor: int
    patch: int

    _PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        match = cls._PATTERN.fullmatch(value.strip())
        if match is None:
            raise ExtensionRegistrationError(f"Invalid semantic version {value!r}; expected MAJOR.MINOR.PATCH")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class SpiVersionRange:
    """A deliberately small, deterministic SemVer range implementation.

    Supported syntax is a comma-separated intersection of ``>=``, ``>``,
    ``<=``, ``<`` and ``==`` comparators, or a caret range such as ``^1.2.0``.
    Caret ranges follow SemVer's left-most non-zero compatibility boundary.
    """

    source: str
    _comparators: tuple[tuple[str, SemanticVersion], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        source = self.source.strip()
        if not source:
            raise ExtensionRegistrationError("supported_spi_versions must not be empty")

        comparators: tuple[tuple[str, SemanticVersion], ...]
        if source.startswith("^"):
            lower = SemanticVersion.parse(source[1:])
            if lower.major:
                upper = SemanticVersion(lower.major + 1, 0, 0)
            elif lower.minor:
                upper = SemanticVersion(0, lower.minor + 1, 0)
            else:
                upper = SemanticVersion(0, 0, lower.patch + 1)
            comparators = ((">=", lower), ("<", upper))
        else:
            parsed: list[tuple[str, SemanticVersion]] = []
            for raw_comparator in source.split(","):
                comparator = raw_comparator.strip()
                match = re.fullmatch(r"(>=|<=|==|>|<)(.+)", comparator)
                if match is None:
                    raise ExtensionRegistrationError(
                        "Invalid SPI version range comparator " f"{comparator!r}; use for example '>=1.0.0,<2.0.0'"
                    )
                parsed.append((match.group(1), SemanticVersion.parse(match.group(2).strip())))
            comparators = tuple(parsed)

        object.__setattr__(self, "source", source)
        object.__setattr__(self, "_comparators", comparators)

    def contains(self, version: SemanticVersion) -> bool:
        operations: Mapping[str, Callable[[SemanticVersion, SemanticVersion], bool]] = {
            ">=": lambda actual, expected: actual >= expected,
            ">": lambda actual, expected: actual > expected,
            "<=": lambda actual, expected: actual <= expected,
            "<": lambda actual, expected: actual < expected,
            "==": lambda actual, expected: actual == expected,
        }
        return all(operations[operator](version, expected) for operator, expected in self._comparators)


ASSET_EXTENSION_SPI_VERSION = SemanticVersion(1, 0, 0)


class ExtensionPoint(str, Enum):
    """Stable contribution slots exposed by the asset-management core."""

    DETAIL_TAB = "asset.detail_tab"
    ACTION = "asset.action"
    SCHEMA_FIELD = "asset.schema_field"
    IDENTITY_PROVIDER = "asset.identity_provider"


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_ENTITLEMENT_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*(?::[a-z][a-z0-9_.-]*)+$")


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Serializable metadata describing one extension contribution."""

    capability_id: str
    extension_point: ExtensionPoint
    display_name: str
    description: str
    extension_version: str
    supported_spi_versions: str
    required_entitlement: str | None = None
    quota_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if _IDENTIFIER_PATTERN.fullmatch(self.capability_id) is None:
            raise ExtensionRegistrationError("capability_id must be a lowercase, namespaced identifier")
        if not self.display_name.strip() or not self.description.strip():
            raise ExtensionRegistrationError("display_name and description are required")
        SemanticVersion.parse(self.extension_version)
        SpiVersionRange(self.supported_spi_versions)
        if self.required_entitlement is not None:
            if _ENTITLEMENT_PATTERN.fullmatch(self.required_entitlement) is None:
                raise ExtensionRegistrationError("required_entitlement must be a namespaced permission-like identifier")
        if self.quota_key is not None and _IDENTIFIER_PATTERN.fullmatch(self.quota_key) is None:
            raise ExtensionRegistrationError("quota_key must be a lowercase, namespaced identifier")
        object.__setattr__(self, "display_name", self.display_name.strip())
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@runtime_checkable
class DetailTabProvider(Protocol):
    """Backend data port for an asset detail-tab contribution."""

    def get_detail(self, tenant_id: uuid.UUID, asset_id: uuid.UUID) -> Mapping[str, Any]: ...


@runtime_checkable
class AssetActionHandler(Protocol):
    """Command port for an extension-provided asset action."""

    def execute(
        self,
        tenant_id: uuid.UUID,
        asset_id: uuid.UUID,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> Mapping[str, Any]: ...


@runtime_checkable
class SchemaFieldProvider(Protocol):
    """Validation port for an industry-specific asset field."""

    def validate(self, tenant_id: uuid.UUID, value: Any) -> Any: ...


@runtime_checkable
class AssetIdentityProvider(Protocol):
    """Lookup port for barcode, QR, RFID, or telemetry identities."""

    def resolve(self, tenant_id: uuid.UUID, identity: str) -> uuid.UUID | None: ...


class EntitlementDecision(str, Enum):
    """Authoritative entitlement result supplied by the platform boundary."""

    GRANTED = "granted"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


@runtime_checkable
class EntitlementResolver(Protocol):
    """Port implemented by license/platform integration, not this module."""

    def check(self, tenant_id: uuid.UUID, entitlement: str) -> EntitlementDecision: ...


class AvailabilityCode(str, Enum):
    AVAILABLE = "available"
    ENTITLEMENT_REQUIRED = "entitlement_required"
    ENTITLEMENT_CHECK_UNAVAILABLE = "entitlement_check_unavailable"
    TENANT_NOT_ELIGIBLE = "tenant_not_eligible"
    ELIGIBILITY_CHECK_UNAVAILABLE = "eligibility_check_unavailable"


@dataclass(frozen=True)
class CapabilityAvailability:
    """Explicit discovery outcome; unavailable checks never degrade to success."""

    code: AvailabilityCode
    reason: str
    required_entitlement: str | None = None

    @property
    def available(self) -> bool:
        return self.code is AvailabilityCode.AVAILABLE


@dataclass(frozen=True)
class DiscoveredCapability:
    descriptor: CapabilityDescriptor
    availability: CapabilityAvailability


@dataclass(frozen=True)
class RegistrationHandle:
    """Opaque ownership proof used for safe deregistration."""

    capability_id: str
    _token: str = field(repr=False)


TenantEligibility = Callable[[uuid.UUID], bool]


@dataclass(frozen=True)
class _Registration:
    descriptor: CapabilityDescriptor
    implementation: object
    handle: RegistrationHandle
    tenant_eligibility: TenantEligibility | None


_IMPLEMENTATION_PROTOCOLS: Mapping[ExtensionPoint, type] = {
    ExtensionPoint.DETAIL_TAB: DetailTabProvider,
    ExtensionPoint.ACTION: AssetActionHandler,
    ExtensionPoint.SCHEMA_FIELD: SchemaFieldProvider,
    ExtensionPoint.IDENTITY_PROVIDER: AssetIdentityProvider,
}


class AssetExtensionRegistry:
    """Thread-safe registry and tenant-aware discovery service."""

    def __init__(self, *, spi_version: SemanticVersion = ASSET_EXTENSION_SPI_VERSION) -> None:
        self.spi_version = spi_version
        self._registrations: dict[str, _Registration] = {}
        self._lock = threading.RLock()

    def register(
        self,
        descriptor: CapabilityDescriptor,
        implementation: object,
        *,
        tenant_eligibility: TenantEligibility | None = None,
    ) -> RegistrationHandle:
        """Validate and atomically register a capability.

        ``tenant_eligibility`` is intended for paid modules with product or
        region restrictions.  Entitlements remain a separate authoritative
        check and cannot be bypassed by this callback.
        """

        version_range = SpiVersionRange(descriptor.supported_spi_versions)
        if not version_range.contains(self.spi_version):
            raise ExtensionCompatibilityError(
                f"Capability {descriptor.capability_id!r} supports SPI "
                f"{version_range.source}, core provides {self.spi_version}"
            )
        protocol = _IMPLEMENTATION_PROTOCOLS[descriptor.extension_point]
        if not isinstance(implementation, protocol):
            raise ExtensionRegistrationError(
                f"{descriptor.extension_point.value} implementation does not satisfy " f"{protocol.__name__}"
            )
        if tenant_eligibility is not None and not callable(tenant_eligibility):
            raise ExtensionRegistrationError("tenant_eligibility must be callable")

        with self._lock:
            if descriptor.capability_id in self._registrations:
                raise DuplicateCapabilityError(f"Capability {descriptor.capability_id!r} is already registered")
            handle = RegistrationHandle(descriptor.capability_id, secrets.token_urlsafe(32))
            self._registrations[descriptor.capability_id] = _Registration(
                descriptor=descriptor,
                implementation=implementation,
                handle=handle,
                tenant_eligibility=tenant_eligibility,
            )
            return handle

    def unregister(self, handle: RegistrationHandle) -> None:
        """Remove a registration only when the caller presents its owner handle."""

        with self._lock:
            registration = self._registrations.get(handle.capability_id)
            if registration is None:
                raise UnknownCapabilityError(handle.capability_id)
            if not secrets.compare_digest(registration.handle._token, handle._token):
                raise ExtensionRegistrationError("Registration handle does not own capability")
            del self._registrations[handle.capability_id]

    def discover(
        self,
        tenant_id: uuid.UUID | str,
        *,
        entitlement_resolver: EntitlementResolver | None = None,
        extension_points: Iterable[ExtensionPoint] | None = None,
    ) -> tuple[DiscoveredCapability, ...]:
        """Return descriptors and truthful availability for one tenant.

        Implementations are intentionally excluded, preventing a discovery
        caller from invoking a capability after an unavailable outcome.
        """

        tenant_uuid = self._tenant_uuid(tenant_id)
        selected_points = frozenset(extension_points) if extension_points is not None else None
        with self._lock:
            registrations = tuple(self._registrations.values())

        discovered = []
        for registration in registrations:
            if selected_points is not None and registration.descriptor.extension_point not in selected_points:
                continue
            discovered.append(
                DiscoveredCapability(
                    descriptor=registration.descriptor,
                    availability=self._availability(tenant_uuid, registration, entitlement_resolver),
                )
            )
        return tuple(sorted(discovered, key=lambda item: item.descriptor.capability_id))

    def resolve(
        self,
        capability_id: str,
        tenant_id: uuid.UUID | str,
        *,
        entitlement_resolver: EntitlementResolver | None = None,
    ) -> object:
        """Resolve an implementation only after current availability checks pass."""

        tenant_uuid = self._tenant_uuid(tenant_id)
        with self._lock:
            registration = self._registrations.get(capability_id)
        if registration is None:
            raise UnknownCapabilityError(capability_id)
        availability = self._availability(tenant_uuid, registration, entitlement_resolver)
        if not availability.available:
            raise CapabilityUnavailableError(capability_id, availability)
        return registration.implementation

    @staticmethod
    def _tenant_uuid(tenant_id: uuid.UUID | str) -> uuid.UUID:
        try:
            return tenant_id if isinstance(tenant_id, uuid.UUID) else uuid.UUID(str(tenant_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("tenant_id must be a valid UUID") from exc

    @staticmethod
    def _availability(
        tenant_id: uuid.UUID,
        registration: _Registration,
        entitlement_resolver: EntitlementResolver | None,
    ) -> CapabilityAvailability:
        eligibility = registration.tenant_eligibility
        if eligibility is not None:
            try:
                if not eligibility(tenant_id):
                    return CapabilityAvailability(
                        AvailabilityCode.TENANT_NOT_ELIGIBLE,
                        "Capability is not offered for this tenant",
                    )
            except Exception:
                return CapabilityAvailability(
                    AvailabilityCode.ELIGIBILITY_CHECK_UNAVAILABLE,
                    "Tenant eligibility could not be verified",
                )

        entitlement = registration.descriptor.required_entitlement
        if entitlement is None:
            return CapabilityAvailability(AvailabilityCode.AVAILABLE, "Capability is available")
        if entitlement_resolver is None:
            return CapabilityAvailability(
                AvailabilityCode.ENTITLEMENT_CHECK_UNAVAILABLE,
                "Entitlement could not be verified",
                entitlement,
            )
        try:
            decision = entitlement_resolver.check(tenant_id, entitlement)
        except Exception:
            decision = EntitlementDecision.UNAVAILABLE
        if decision is EntitlementDecision.GRANTED:
            return CapabilityAvailability(
                AvailabilityCode.AVAILABLE,
                "Capability is available",
                entitlement,
            )
        if decision is EntitlementDecision.DENIED:
            return CapabilityAvailability(
                AvailabilityCode.ENTITLEMENT_REQUIRED,
                "Tenant is not entitled to this capability",
                entitlement,
            )
        return CapabilityAvailability(
            AvailabilityCode.ENTITLEMENT_CHECK_UNAVAILABLE,
            "Entitlement could not be verified",
            entitlement,
        )


# The single module-owned registry. Paid modules register through this public
# symbol; the OSS core never imports their packages or ORM models.
asset_extension_registry = AssetExtensionRegistry()


__all__ = [
    "ASSET_EXTENSION_SPI_VERSION",
    "AssetActionHandler",
    "AssetExtensionRegistry",
    "AssetIdentityProvider",
    "AvailabilityCode",
    "CapabilityAvailability",
    "CapabilityDescriptor",
    "CapabilityUnavailableError",
    "DetailTabProvider",
    "DiscoveredCapability",
    "DuplicateCapabilityError",
    "EntitlementDecision",
    "EntitlementResolver",
    "ExtensionCompatibilityError",
    "ExtensionPoint",
    "ExtensionRegistrationError",
    "RegistrationHandle",
    "SchemaFieldProvider",
    "SemanticVersion",
    "SpiVersionRange",
    "UnknownCapabilityError",
    "asset_extension_registry",
]
