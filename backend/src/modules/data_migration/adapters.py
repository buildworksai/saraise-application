"""Stable extension protocols and conflict-safe adapter registries."""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping
from typing import Any, Protocol
from uuid import UUID


class SourceAdapter(Protocol):
    def validate_config(self, config: Mapping[str, object]) -> Mapping[str, object]: ...
    def inspect(self, tenant_id: UUID, artifact_id: UUID | None, config: Mapping[str, object], runtime: object) -> Mapping[str, object]: ...
    def iter_records(self, tenant_id: UUID, artifact_id: UUID | None, config: Mapping[str, object], runtime: object) -> Iterable[Mapping[str, object]]: ...


class TargetAdapter(Protocol):
    def describe_schema(self, entity: str) -> Mapping[str, object]: ...
    def validate_reference(self, entity: str, field: str, value: object, rule_type: str, config: Mapping[str, object]) -> bool: ...
    def lookup(self, tenant_id: UUID, entity: str, fields: Mapping[str, object]) -> Mapping[str, object] | None: ...
    def write(self, tenant_id: UUID, entity: str, record: Mapping[str, object], **context: object) -> Mapping[str, object]: ...
    def reverse(self, tenant_id: UUID, entity: str, record_id: str, **context: object) -> Mapping[str, object]: ...


class AdapterRegistry:
    def __init__(self, kind: str) -> None:
        self.kind = kind; self._items: dict[str, Any] = {}; self._lock = threading.RLock()

    def register(self, key: str, adapter: Any, *, replace: bool = False) -> Any:
        if not isinstance(key, str) or not key or len(key) > 100 or "." not in key: raise ValueError(f"{self.kind} adapter key must be a stable namespaced identifier")
        with self._lock:
            if key in self._items and not replace: raise RuntimeError(f"Duplicate {self.kind} adapter registration: {key}")
            self._items[key] = adapter
        return adapter

    def get(self, key: str) -> Any:
        try: return self._items[key]
        except KeyError as exc: raise LookupError(f"{self.kind} adapter {key!r} is unavailable") from exc

    def contains(self, key: str) -> bool: return key in self._items
    def catalog(self) -> tuple[str, ...]: return tuple(sorted(self._items))
    def clear(self) -> None: self._items.clear()


SOURCE_ADAPTERS = AdapterRegistry("source")
TARGET_ADAPTERS = AdapterRegistry("target")

__all__ = ["AdapterRegistry", "SOURCE_ADAPTERS", "SourceAdapter", "TARGET_ADAPTERS", "TargetAdapter"]
