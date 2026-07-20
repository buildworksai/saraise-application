"""Stable public extension API for SARAISE paid industry modules.

Paid modules should import their contracts from this package rather than from
the application's private ``src`` tree.  Public names are re-exported here so
minor releases can reorganize internals without breaking module authors.
"""

from .extension_points import (
    CAPABILITY_EXTENSION_POINT,
    ENGINE_EXTENSION_POINT,
    EXTENSION_POINT_IDS,
    PROVIDER_EXTENSION_POINT,
    SPI_VERSION,
    CapabilityExtension,
    EngineExtension,
    EntitlementDecision,
    EntitlementDeniedError,
    EntitlementResolver,
    EntitlementServiceUnavailableError,
    ExecutionContext,
    ExtensionActivationError,
    ExtensionLifecycleError,
    ExtensionMetadata,
    ExtensionPoint,
    ExtensionRegistry,
    ExtensionState,
    ExtensionValidationError,
    ProviderExtension,
    RegistrationError,
    RegistrationSnapshot,
    SPIError,
    UnknownExtensionError,
    is_spi_compatible,
)

__all__ = [
    "CAPABILITY_EXTENSION_POINT",
    "ENGINE_EXTENSION_POINT",
    "EXTENSION_POINT_IDS",
    "PROVIDER_EXTENSION_POINT",
    "SPI_VERSION",
    "CapabilityExtension",
    "EngineExtension",
    "EntitlementDecision",
    "EntitlementDeniedError",
    "EntitlementResolver",
    "EntitlementServiceUnavailableError",
    "ExecutionContext",
    "ExtensionActivationError",
    "ExtensionLifecycleError",
    "ExtensionMetadata",
    "ExtensionPoint",
    "ExtensionRegistry",
    "ExtensionState",
    "ExtensionValidationError",
    "ProviderExtension",
    "RegistrationError",
    "RegistrationSnapshot",
    "SPIError",
    "UnknownExtensionError",
    "is_spi_compatible",
]
