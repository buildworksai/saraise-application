"""Public extension-point contract for SARAISE paid modules.

The SPI deliberately has no Django dependency.  A paid module can therefore be
validated before Django starts, and the host application can adapt any
licensing implementation (connected or isolated) through
:class:`EntitlementResolver`.

Extensions move through an explicit ``register -> validate -> activate``
lifecycle.  Activation is tenant-specific.  Entitlements are checked both when
an extension is activated and immediately before it executes so that a revoked
or expired entitlement cannot continue to grant access.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from types import MappingProxyType
from typing import Callable, Dict, FrozenSet, Generic, Mapping, Optional, Protocol, Tuple, TypeVar, Union, cast
from uuid import UUID

SPI_VERSION = "1.0.0"
"""Semantic version of the public SARAISE extension contract."""


class ExtensionPoint(str, Enum):
    """Stable, versioned identifiers understood by the SARAISE runtime."""

    PROVIDER = "saraise.spi.provider.v1"
    ENGINE = "saraise.spi.engine.v1"
    CAPABILITY = "saraise.spi.capability.v1"


PROVIDER_EXTENSION_POINT = ExtensionPoint.PROVIDER.value
ENGINE_EXTENSION_POINT = ExtensionPoint.ENGINE.value
CAPABILITY_EXTENSION_POINT = ExtensionPoint.CAPABILITY.value
EXTENSION_POINT_IDS: FrozenSet[str] = frozenset(point.value for point in ExtensionPoint)


class ExtensionState(str, Enum):
    """Lifecycle state of a registered extension."""

    REGISTERED = "registered"
    VALIDATED = "validated"
    ACTIVE = "active"


class SPIError(Exception):
    """Base class for errors exposed by the public SPI."""


class RegistrationError(SPIError):
    """Raised when an extension cannot be registered."""


class UnknownExtensionError(RegistrationError):
    """Raised when an extension identifier is not registered."""


class ExtensionValidationError(SPIError):
    """Raised when extension metadata or implementation violates the SPI."""


class ExtensionActivationError(SPIError):
    """Raised when an extension's activation hook fails."""


class ExtensionLifecycleError(SPIError):
    """Raised when lifecycle methods are called out of order."""


class EntitlementServiceUnavailableError(SPIError):
    """Raised when entitlement status cannot be established reliably."""


class EntitlementDeniedError(SPIError):
    """Raised when a tenant lacks one or more required entitlements."""

    def __init__(
        self,
        extension_id: str,
        tenant_id: UUID,
        missing_entitlements: Tuple[str, ...],
        reasons: Mapping[str, str],
    ) -> None:
        self.extension_id = extension_id
        self.tenant_id = tenant_id
        self.missing_entitlements = missing_entitlements
        self.reasons = MappingProxyType(dict(reasons))
        missing = ", ".join(missing_entitlements)
        super().__init__(f"Tenant {tenant_id} is not entitled to {extension_id}: {missing}")


@dataclass(frozen=True)
class EntitlementDecision:
    """Auditable answer returned by an :class:`EntitlementResolver`.

    ``source`` identifies the authority that made the decision, for example an
    online license service or a locally verified offline license.  A denial
    requires a reason so callers never receive an unexplained false result.
    """

    granted: bool
    source: str
    reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.source or not self.source.strip():
            raise ValueError("Entitlement decision source must not be blank")
        if not self.granted and (not self.reason or not self.reason.strip()):
            raise ValueError("A denied entitlement decision must include a reason")


class EntitlementResolver(Protocol):
    """Host-supplied bridge to connected or offline entitlement data."""

    def check(self, *, tenant_id: UUID, entitlement_id: str) -> EntitlementDecision:
        """Return the current authoritative decision for one entitlement."""


@dataclass(frozen=True)
class ExecutionContext:
    """Tenant and request identity supplied to every extension invocation."""

    tenant_id: UUID
    correlation_id: str
    entitlement_resolver: EntitlementResolver
    principal_id: Optional[str] = None
    attributes: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID):
            raise TypeError("tenant_id must be a UUID")
        if not self.correlation_id or not self.correlation_id.strip():
            raise ValueError("correlation_id must not be blank")
        if not callable(getattr(self.entitlement_resolver, "check", None)):
            raise TypeError("entitlement_resolver must implement check()")
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True)
class ExtensionMetadata:
    """Immutable discovery and compatibility metadata for an extension."""

    extension_id: str
    extension_point: ExtensionPoint
    module_id: str
    module_version: str
    display_name: str
    required_entitlements: FrozenSet[str] = field(default_factory=frozenset)
    spi_version: str = SPI_VERSION
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_entitlements", frozenset(self.required_entitlements))


RequestT = TypeVar("RequestT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class _ExtensionLifecycle(Protocol):
    @property
    def metadata(self) -> ExtensionMetadata:
        """Describe this extension and its entitlement requirements."""

    def validate(self) -> None:
        """Raise an exception if module-specific configuration is invalid."""

    def activate(self, context: ExecutionContext) -> None:
        """Prepare the extension for one tenant or raise on failure."""


class ProviderExtension(_ExtensionLifecycle, Protocol, Generic[RequestT, ResultT]):
    """Typed contract for adapters that provide data or external services."""

    def provide(self, context: ExecutionContext, request: RequestT) -> ResultT:
        """Fulfil a provider request for the context's tenant."""


class EngineExtension(_ExtensionLifecycle, Protocol, Generic[RequestT, ResultT]):
    """Typed contract for engines that execute domain processing."""

    def execute(self, context: ExecutionContext, request: RequestT) -> ResultT:
        """Execute domain processing for the context's tenant."""


class CapabilityExtension(_ExtensionLifecycle, Protocol, Generic[RequestT, ResultT]):
    """Typed contract for user-facing paid capabilities."""

    def invoke(self, context: ExecutionContext, request: RequestT) -> ResultT:
        """Invoke the capability for the context's tenant."""


ExtensionImplementation = Union[
    ProviderExtension[object, object],
    EngineExtension[object, object],
    CapabilityExtension[object, object],
]


@dataclass(frozen=True)
class RegistrationSnapshot:
    """Read-only view of registry state, suitable for diagnostics."""

    metadata: ExtensionMetadata
    state: ExtensionState
    active_tenants: Tuple[UUID, ...]


@dataclass
class _Registration:
    extension: ExtensionImplementation
    state: ExtensionState = ExtensionState.REGISTERED
    active_tenants: set[UUID] = field(default_factory=set)


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def is_spi_compatible(requested_version: str, host_version: str = SPI_VERSION) -> bool:
    """Return whether a requested SPI version is supported by this host.

    The SPI follows semantic-version compatibility: versions must be valid and
    share a major version, while the host minor version must be at least the
    requested minor version.
    """

    requested = _SEMVER_PATTERN.fullmatch(requested_version)
    host = _SEMVER_PATTERN.fullmatch(host_version)
    if requested is None or host is None:
        return False
    requested_major = int(requested["major"])
    host_major = int(host["major"])
    return host_major == requested_major and int(host["minor"]) >= int(requested["minor"])


class ExtensionRegistry:
    """Thread-safe registry and entitlement-aware lifecycle coordinator."""

    def __init__(self) -> None:
        self._registrations: Dict[str, _Registration] = {}
        self._lock = RLock()

    def register(self, extension: ExtensionImplementation) -> RegistrationSnapshot:
        """Register an extension without claiming that it is valid or usable."""

        metadata = getattr(extension, "metadata", None)
        if not isinstance(metadata, ExtensionMetadata):
            raise RegistrationError("Extension metadata must be an ExtensionMetadata instance")
        extension_id = metadata.extension_id
        if not isinstance(extension_id, str) or not extension_id:
            raise RegistrationError("Extension metadata must include an extension_id")

        with self._lock:
            if extension_id in self._registrations:
                raise RegistrationError(f"Extension {extension_id!r} is already registered")
            registration = _Registration(extension=extension)
            self._registrations[extension_id] = registration
            return self._snapshot(registration)

    def validate(self, extension_id: str) -> RegistrationSnapshot:
        """Validate the public contract and the extension's own configuration."""

        with self._lock:
            registration = self._get_registration(extension_id)
            if registration.state is not ExtensionState.REGISTERED:
                return self._snapshot(registration)

            metadata = registration.extension.metadata
            self._validate_metadata(metadata)
            self._validate_implementation(registration.extension, metadata.extension_point)
            try:
                result = registration.extension.validate()
            except Exception as exc:
                raise ExtensionValidationError(f"Extension {extension_id!r} rejected its configuration") from exc
            if result is not None:
                raise ExtensionValidationError(
                    f"Extension {extension_id!r} validate() must signal success by returning None"
                )

            registration.state = ExtensionState.VALIDATED
            return self._snapshot(registration)

    def activate(self, extension_id: str, context: ExecutionContext) -> RegistrationSnapshot:
        """Entitle and activate a previously validated extension for a tenant."""

        with self._lock:
            registration = self._get_registration(extension_id)
            if registration.state is ExtensionState.REGISTERED:
                raise ExtensionLifecycleError(f"Extension {extension_id!r} must be validated before activation")

            self._authorize(registration.extension.metadata, context)
            if context.tenant_id in registration.active_tenants:
                return self._snapshot(registration)

            try:
                result = registration.extension.activate(context)
            except Exception as exc:
                raise ExtensionActivationError(
                    f"Extension {extension_id!r} failed activation for tenant {context.tenant_id}"
                ) from exc
            if result is not None:
                raise ExtensionActivationError(
                    f"Extension {extension_id!r} activate() must signal success by returning None"
                )

            registration.active_tenants.add(context.tenant_id)
            registration.state = ExtensionState.ACTIVE
            return self._snapshot(registration)

    def provide(self, extension_id: str, context: ExecutionContext, request: object) -> object:
        """Execute a provider after enforcing activation and current entitlement."""

        extension = self._prepare_execution(extension_id, ExtensionPoint.PROVIDER, context)
        provider = cast(ProviderExtension[object, object], extension)
        return provider.provide(context, request)

    def execute(self, extension_id: str, context: ExecutionContext, request: object) -> object:
        """Execute an engine after enforcing activation and current entitlement."""

        extension = self._prepare_execution(extension_id, ExtensionPoint.ENGINE, context)
        engine = cast(EngineExtension[object, object], extension)
        return engine.execute(context, request)

    def invoke(self, extension_id: str, context: ExecutionContext, request: object) -> object:
        """Invoke a capability after enforcing activation and current entitlement."""

        extension = self._prepare_execution(extension_id, ExtensionPoint.CAPABILITY, context)
        capability = cast(CapabilityExtension[object, object], extension)
        return capability.invoke(context, request)

    def snapshot(self, extension_id: str) -> RegistrationSnapshot:
        """Return current state for one extension."""

        with self._lock:
            return self._snapshot(self._get_registration(extension_id))

    def registrations(self) -> Tuple[RegistrationSnapshot, ...]:
        """Return stable, identifier-sorted snapshots of all registrations."""

        with self._lock:
            return tuple(self._snapshot(self._registrations[key]) for key in sorted(self._registrations))

    def _prepare_execution(
        self,
        extension_id: str,
        expected_point: ExtensionPoint,
        context: ExecutionContext,
    ) -> ExtensionImplementation:
        with self._lock:
            registration = self._get_registration(extension_id)
            metadata = registration.extension.metadata
            if metadata.extension_point is not expected_point:
                mismatch = f"{metadata.extension_point.value}, not {expected_point.value}"
                raise ExtensionLifecycleError(f"Extension {extension_id!r} belongs to {mismatch}")
            if context.tenant_id not in registration.active_tenants:
                raise ExtensionLifecycleError(
                    f"Extension {extension_id!r} is not active for tenant {context.tenant_id}"
                )
            self._authorize(metadata, context)
            return registration.extension

    def _authorize(self, metadata: ExtensionMetadata, context: ExecutionContext) -> None:
        denied: Dict[str, str] = {}
        for entitlement_id in sorted(metadata.required_entitlements):
            try:
                decision = context.entitlement_resolver.check(
                    tenant_id=context.tenant_id,
                    entitlement_id=entitlement_id,
                )
            except Exception as exc:
                raise EntitlementServiceUnavailableError(
                    f"Could not verify entitlement {entitlement_id!r} for tenant {context.tenant_id}"
                ) from exc
            if not isinstance(decision, EntitlementDecision):
                raise EntitlementServiceUnavailableError(
                    f"Entitlement resolver returned an invalid decision for {entitlement_id!r}"
                )
            if not decision.granted:
                denied[entitlement_id] = cast(str, decision.reason)

        if denied:
            raise EntitlementDeniedError(
                extension_id=metadata.extension_id,
                tenant_id=context.tenant_id,
                missing_entitlements=tuple(denied),
                reasons=denied,
            )

    def _get_registration(self, extension_id: str) -> _Registration:
        try:
            return self._registrations[extension_id]
        except KeyError as exc:
            raise UnknownExtensionError(f"Extension {extension_id!r} is not registered") from exc

    @staticmethod
    def _snapshot(registration: _Registration) -> RegistrationSnapshot:
        tenants = tuple(sorted(registration.active_tenants, key=str))
        return RegistrationSnapshot(
            metadata=registration.extension.metadata,
            state=registration.state,
            active_tenants=tenants,
        )

    @staticmethod
    def _validate_metadata(metadata: ExtensionMetadata) -> None:
        values = {
            "extension_id": metadata.extension_id,
            "module_id": metadata.module_id,
        }
        for label, value in values.items():
            if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
                raise ExtensionValidationError(
                    f"{label} must be a lowercase namespaced identifier (received {value!r})"
                )
        if not isinstance(metadata.extension_point, ExtensionPoint):
            raise ExtensionValidationError("extension_point must be a supported ExtensionPoint")
        if not metadata.display_name or not metadata.display_name.strip():
            raise ExtensionValidationError("display_name must not be blank")
        if _SEMVER_PATTERN.fullmatch(metadata.module_version) is None:
            raise ExtensionValidationError(f"module_version {metadata.module_version!r} is not semantic versioning")
        if not is_spi_compatible(metadata.spi_version):
            raise ExtensionValidationError(
                f"SPI version {metadata.spi_version!r} is not compatible with host version {SPI_VERSION!r}"
            )
        for entitlement_id in metadata.required_entitlements:
            if not isinstance(entitlement_id, str) or _IDENTIFIER_PATTERN.fullmatch(entitlement_id) is None:
                raise ExtensionValidationError(
                    f"Entitlement {entitlement_id!r} must be a lowercase namespaced identifier"
                )

    @classmethod
    def _validate_implementation(
        cls,
        extension: ExtensionImplementation,
        extension_point: ExtensionPoint,
    ) -> None:
        cls._validate_method(extension, "validate", ())
        cls._validate_method(extension, "activate", (object(),))
        operation = {
            ExtensionPoint.PROVIDER: "provide",
            ExtensionPoint.ENGINE: "execute",
            ExtensionPoint.CAPABILITY: "invoke",
        }[extension_point]
        cls._validate_method(extension, operation, (object(), object()))

    @staticmethod
    def _validate_method(extension: object, name: str, arguments: Tuple[object, ...]) -> None:
        method = getattr(extension, name, None)
        if not callable(method):
            raise ExtensionValidationError(f"Extension must implement callable {name}()")
        callable_method = cast(Callable[..., object], method)
        try:
            inspect.signature(callable_method).bind(*arguments)
        except (TypeError, ValueError) as exc:
            raise ExtensionValidationError(f"Extension {name}() has an incompatible signature") from exc
