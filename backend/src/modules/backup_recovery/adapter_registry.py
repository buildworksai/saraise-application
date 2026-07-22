"""Explicit registries for capture adapters and paid-module extensions."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from src.core.api.results import CapabilityUnavailable

from .ports import BackupCaptureAdapter, BackupType

T = TypeVar("T")


class DuplicateRegistration(ValueError):
    """Raised when an extension attempts silent replacement."""


class ExtensionRegistry(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}
        self._lock = threading.RLock()

    def register(self, key: str, value: T, *, replace: bool = False) -> T:
        normalized = _key(key)
        with self._lock:
            if normalized in self._items and not replace:
                raise DuplicateRegistration(f"{normalized!r} is already registered")
            self._items[normalized] = value
        return value

    def get(self, key: str) -> T:
        normalized = _key(key)
        with self._lock:
            try:
                return self._items[normalized]
            except KeyError as exc:
                raise CapabilityUnavailable(capability=f"backup-capture-adapter:{normalized}") from exc

    def keys(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._items))

    def unregister(self, key: str) -> T | None:
        with self._lock:
            return self._items.pop(_key(key), None)


@dataclass(frozen=True, slots=True)
class BackupScopeProvider:
    key: str
    owning_module: str
    display_label: str
    supported_backup_types: tuple[BackupType, ...]
    selector_schema: dict[str, object]
    entitlement_capability: str
    validate: Callable[[str], None]


capture_adapters: ExtensionRegistry[BackupCaptureAdapter] = ExtensionRegistry()
scope_providers: ExtensionRegistry[BackupScopeProvider] = ExtensionRegistry()
retention_policy_presets: ExtensionRegistry[object] = ExtensionRegistry()
provider_health_probes: ExtensionRegistry[Callable[[], object]] = ExtensionRegistry()


def _key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("registration key must be a non-empty string")
    return value.strip()
