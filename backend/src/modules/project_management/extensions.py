"""Versioned, explicit extension SPI for paid industry modules.

Providers receive immutable identifiers/data and return typed availability
results. They never receive ORM objects and cannot replace core authorization,
tenant isolation, workflow guards, or audit.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol, Sequence
from uuid import UUID

SPI_VERSION = "1.0"

@dataclass(frozen=True, slots=True)
class ProjectExtensionContext:
    tenant_id: UUID; project_id: UUID; project_version: int; actor_id: UUID; correlation_id: str

@dataclass(frozen=True, slots=True)
class ExtensionResult:
    status: str
    data: Mapping[str, object] | None = None
    code: str | None = None
    @classmethod
    def unavailable(cls, code="PROVIDER_UNAVAILABLE"): return cls("unavailable", None, code)

class ProjectValidator(Protocol):
    key: str
    def validate(self, context: ProjectExtensionContext, operation: str, changes: Mapping[str, object]) -> ExtensionResult: ...
class TaskSchedulingProvider(Protocol):
    key: str
    def recommend(self, context: ProjectExtensionContext, task_ids: Sequence[UUID]) -> ExtensionResult: ...
class ProjectCostProvider(Protocol):
    key: str
    def project_cost(self, context: ProjectExtensionContext, currency: str) -> ExtensionResult: ...
class ResourceAvailabilityProvider(Protocol):
    key: str
    def availability(self, context: ProjectExtensionContext, employee_ids: Sequence[UUID]) -> ExtensionResult: ...
class ProjectInsightProvider(Protocol):
    key: str
    def insights(self, context: ProjectExtensionContext) -> ExtensionResult: ...
class ProjectLifecycleSubscriber(Protocol):
    key: str
    def consume(self, event: Mapping[str, object]) -> None: ...
@dataclass(frozen=True, slots=True)
class ProjectDetailPanel:
    key: str; title: str; slot: str; module: str; minimum_spi_version: str = SPI_VERSION; permission: str | None = None; entitlement: str | None = None

class ExtensionRegistry:
    def __init__(self): self._providers: dict[str, object] = {}
    def register(self, provider):
        key = str(getattr(provider, "key", "")).strip()
        if not key: raise ValueError("Extension provider key is required.")
        if key in self._providers: raise ValueError(f"Duplicate extension provider key: {key}")
        self._providers[key] = provider; return provider
    def get(self, key): return self._providers.get(key)
    def all(self): return tuple(self._providers[k] for k in sorted(self._providers))
    def clear(self): self._providers.clear()

registry = ExtensionRegistry()
