"""Stable, collision-safe extension registry for paid industry modules.

Extensions contribute descriptors and adapters; they never import or mutate
private ORM state.  Registry keys are globally namespaced (``vendor.name``),
which allows the open-source core to expose availability without fabricating a
capability or coupling entitlements to core workflows.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
EXTENSION_API_VERSION = "1.0"


class ExtensionCollision(ValueError):
    pass


class ConfigurationValidator(Protocol):
    def __call__(self, document: object) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class ExtensionDescriptor:
    key: str
    display_name: str
    provider: str
    capability: str
    api_version: str = EXTENSION_API_VERSION
    entitlement: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.key):
            raise ValueError("Extension keys must be namespaced lowercase identifiers.")
        if self.capability not in {
            "risk_category",
            "control_catalog",
            "regulation_pack",
            "score_suggestion",
            "reporting_projection",
            "integration_adapter",
            "configuration_schema",
        }:
            raise ValueError("Unsupported extension capability.")
        if self.api_version != EXTENSION_API_VERSION:
            raise ValueError("Incompatible compliance-risk extension API version.")
        if not self.display_name.strip() or not self.provider.strip():
            raise ValueError("Extension display name and provider are required.")


class ExtensionRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._descriptors: dict[str, ExtensionDescriptor] = {}
        self._validators: dict[str, ConfigurationValidator] = {}

    def register(self, descriptor: ExtensionDescriptor, *, validator: ConfigurationValidator | None = None) -> None:
        with self._lock:
            current = self._descriptors.get(descriptor.key)
            if current is not None and current != descriptor:
                raise ExtensionCollision(f"Extension key {descriptor.key!r} is already registered.")
            if descriptor.capability == "configuration_schema" and validator is None:
                raise ValueError("Configuration schema extensions require a validator.")
            self._descriptors[descriptor.key] = descriptor
            if validator is not None:
                self._validators[descriptor.key] = validator

    def descriptors(self) -> tuple[ExtensionDescriptor, ...]:
        with self._lock:
            return tuple(sorted(self._descriptors.values(), key=lambda item: item.key))

    def validators(self) -> Mapping[str, ConfigurationValidator]:
        with self._lock:
            return MappingProxyType(dict(self._validators))

    def validate_fragment(self, key: str, document: object) -> Mapping[str, object]:
        validator = self.validators().get(key)
        if validator is None:
            raise KeyError(f"No configuration schema extension is registered for {key!r}.")
        return MappingProxyType(dict(validator(document)))


registry = ExtensionRegistry()


__all__ = ["EXTENSION_API_VERSION", "ExtensionCollision", "ExtensionDescriptor", "ExtensionRegistry", "registry"]
