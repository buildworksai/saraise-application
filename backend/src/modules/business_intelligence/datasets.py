"""Typed extension registry for governed Business Intelligence datasets.

Industry modules register providers through :data:`dataset_registry`; BI never
imports their models.  Descriptors are immutable and a key cannot be replaced,
which makes the registry a stable extension ABI rather than a mutable service
locator.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from uuid import UUID

from django.db import DatabaseError, connection, models

JSONScalar = None | bool | int | float | str
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class DatasetRegistrationError(RuntimeError):
    """Raised when a provider violates registry identity or lifecycle rules."""


class DatasetUnavailableError(RuntimeError):
    """Raised when a real provider cannot safely supply data."""


class ScalarType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    UUID = "uuid"


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class DependencyStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DimensionDescriptor:
    key: str
    label: str
    scalar_type: ScalarType
    filter_operators: tuple[str, ...]
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    required_permission: str = ""


@dataclass(frozen=True, slots=True)
class MeasureDescriptor:
    key: str
    label: str
    result_type: ScalarType
    aggregation: str
    formatting: str = "number"


@dataclass(frozen=True, slots=True)
class DatasetDescriptor:
    key: str
    module: str
    label: str
    description: str
    version: str
    dimensions: tuple[DimensionDescriptor, ...]
    measures: tuple[MeasureDescriptor, ...]
    supported_grouping: tuple[str, ...]
    supported_ordering: tuple[str, ...]
    required_permission: str
    required_entitlement: str
    max_row_limit: int
    data_freshness: str
    upgrade_url: str | None = None

    @property
    def schema_fingerprint(self) -> str:
        """Return a deterministic fingerprint used for lineage and cache keys."""

        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ValidatedQuery:
    dataset_key: str
    dimensions: tuple[str, ...]
    measures: tuple[Mapping[str, JSONValue], ...]
    filters: tuple[Mapping[str, JSONValue], ...]
    grouping: tuple[str, ...]
    ordering: tuple[Mapping[str, JSONValue], ...]
    row_limit: int
    fingerprint: str


@dataclass(frozen=True, slots=True)
class DatasetResult:
    columns: tuple[Mapping[str, JSONValue], ...]
    rows: tuple[Mapping[str, JSONValue], ...]
    row_count: int
    truncated: bool
    freshness_token: str
    data_as_of: datetime | None = None


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    status: DependencyStatus
    summary: str


@runtime_checkable
class DatasetProvider(Protocol):
    """Provider ABI implemented by open-source and paid dataset owners."""

    def describe(self) -> DatasetDescriptor: ...

    def validate(self, tenant_id: UUID, query_spec: Mapping[str, Any]) -> ValidatedQuery: ...

    def execute(
        self,
        tenant_id: UUID,
        validated_query: ValidatedQuery,
        parameters: Mapping[str, JSONValue],
    ) -> DatasetResult: ...

    def freshness_token(self, tenant_id: UUID) -> str: ...

    def health(self) -> DependencyHealth: ...


@dataclass(frozen=True, slots=True)
class TemplateDescriptor:
    """Metadata-only ABI for installable query, report, or dashboard starters."""

    key: str
    module: str
    label: str
    description: str
    version: str
    resource_type: str
    required_entitlement: str = "business_intelligence.core"
    upgrade_url: str | None = None


@runtime_checkable
class TemplateProvider(Protocol):
    def describe(self) -> TemplateDescriptor: ...

    def instantiate(self, tenant_id: UUID, actor_id: str) -> Mapping[str, JSONValue]: ...


@dataclass(frozen=True, slots=True)
class VisualizationDescriptor:
    """Stable renderer contribution metadata; rendering remains frontend-owned."""

    key: str
    module: str
    label: str
    version: str
    compatible_result_types: tuple[str, ...]
    required_entitlement: str = "business_intelligence.core"


@runtime_checkable
class VisualizationProvider(Protocol):
    def describe(self) -> VisualizationDescriptor: ...

    def validate(self, configuration: Mapping[str, JSONValue], columns: Sequence[Mapping[str, JSONValue]]) -> None: ...


class ContributionRegistry:
    """Immutable-after-startup registry shared by template and renderer ABIs."""

    def __init__(self) -> None:
        self._providers: dict[str, object] = {}
        self._frozen = False
        self._lock = RLock()

    def register(self, provider: object) -> object:
        descriptor = provider.describe()  # type: ignore[attr-defined]
        key = str(getattr(descriptor, "key", "")).strip()
        if not key:
            raise DatasetRegistrationError("Contribution keys must not be empty")
        with self._lock:
            if self._frozen:
                raise DatasetRegistrationError("Contribution registrations are frozen")
            if key in self._providers:
                raise DatasetRegistrationError(f"Duplicate contribution key: {key}")
            self._providers[key] = provider
        return provider

    def get(self, key: str) -> object:
        try:
            return self._providers[key]
        except KeyError as exc:
            raise DatasetUnavailableError(f"Contribution is not registered: {key}") from exc

    def providers(self) -> Mapping[str, object]:
        return MappingProxyType(self._providers)

    def freeze(self) -> None:
        with self._lock:
            self._frozen = True


class DatasetRegistry:
    """Thread-safe, duplicate-resistant registry of immutable providers."""

    def __init__(self) -> None:
        self._providers: dict[str, DatasetProvider] = {}
        self._frozen = False
        self._lock = RLock()

    def register(self, provider: DatasetProvider) -> DatasetProvider:
        descriptor = provider.describe()
        self._validate_descriptor(descriptor)
        with self._lock:
            if self._frozen:
                raise DatasetRegistrationError("Dataset registrations are frozen")
            if descriptor.key in self._providers:
                raise DatasetRegistrationError(f"Duplicate dataset key: {descriptor.key}")
            self._providers[descriptor.key] = provider
        return provider

    def freeze(self) -> None:
        """Prevent any registration after application startup is complete."""

        with self._lock:
            self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    def get(self, key: str) -> DatasetProvider:
        try:
            return self._providers[key]
        except KeyError as exc:
            raise DatasetUnavailableError(f"Dataset is not registered: {key}") from exc

    def descriptors(self) -> tuple[DatasetDescriptor, ...]:
        return tuple(sorted((provider.describe() for provider in self._providers.values()), key=lambda item: item.key))

    def providers(self) -> Mapping[str, DatasetProvider]:
        return MappingProxyType(self._providers)

    def validate_integrity(self) -> None:
        for key, provider in self._providers.items():
            descriptor = provider.describe()
            self._validate_descriptor(descriptor)
            if descriptor.key != key:
                raise DatasetRegistrationError(f"Provider key changed after registration: {key}")

    @staticmethod
    def _validate_descriptor(descriptor: DatasetDescriptor) -> None:
        if not descriptor.key or descriptor.key != descriptor.key.lower():
            raise DatasetRegistrationError("Dataset keys must be non-empty lowercase identifiers")
        if not descriptor.module or not descriptor.label or not descriptor.version:
            raise DatasetRegistrationError("Dataset module, label, and version are required")
        if descriptor.max_row_limit < 1 or descriptor.max_row_limit > 10_000:
            raise DatasetRegistrationError("Dataset maximum row limit must be between 1 and 10,000")
        dimension_keys = [dimension.key for dimension in descriptor.dimensions]
        measure_keys = [measure.key for measure in descriptor.measures]
        if len(dimension_keys) != len(set(dimension_keys)) or len(measure_keys) != len(set(measure_keys)):
            raise DatasetRegistrationError("Dataset dimension and measure keys must be unique")


class ExecutionAuditDatasetProvider:
    """Bundled, real OSS dataset for auditing BI execution outcomes.

    The provider reads only this module's public execution history and applies
    the tenant boundary itself, so a clean install delivers immediate analytics
    without fabricated sample records.
    """

    KEY = "business_intelligence.execution_audit"
    _DIMENSIONS = {"created_at", "status", "dataset_key", "actor_id", "cache_hit", "truncated"}
    _MEASURES = {"execution_count", "average_duration_ms", "total_rows"}
    _OPERATORS = {"eq", "neq", "in", "gte", "lte"}

    def describe(self) -> DatasetDescriptor:
        common_ops = ("eq", "neq", "in")
        return DatasetDescriptor(
            key=self.KEY,
            module="business_intelligence",
            label="BI execution audit",
            description="Tenant-scoped execution volume, reliability, duration, and cache evidence.",
            version="1.0.0",
            dimensions=(
                DimensionDescriptor("created_at", "Created at", ScalarType.DATETIME, ("eq", "gte", "lte")),
                DimensionDescriptor("status", "Status", ScalarType.STRING, common_ops),
                DimensionDescriptor("dataset_key", "Dataset", ScalarType.STRING, common_ops),
                DimensionDescriptor("actor_id", "Actor", ScalarType.STRING, common_ops, Sensitivity.RESTRICTED),
                DimensionDescriptor("cache_hit", "Cache hit", ScalarType.BOOLEAN, ("eq",)),
                DimensionDescriptor("truncated", "Truncated", ScalarType.BOOLEAN, ("eq",)),
            ),
            measures=(
                MeasureDescriptor("execution_count", "Executions", ScalarType.INTEGER, "count", "integer"),
                MeasureDescriptor(
                    "average_duration_ms", "Average duration", ScalarType.NUMBER, "average", "duration_ms"
                ),
                MeasureDescriptor("total_rows", "Rows returned", ScalarType.INTEGER, "sum", "integer"),
            ),
            supported_grouping=tuple(sorted(self._DIMENSIONS)),
            supported_ordering=tuple(sorted(self._DIMENSIONS | self._MEASURES)),
            required_permission="bi.execution:read",
            required_entitlement="business_intelligence.core",
            max_row_limit=1_000,
            data_freshness="Live durable execution history",
        )

    def validate(self, tenant_id: UUID, query_spec: Mapping[str, Any]) -> ValidatedQuery:
        del tenant_id  # Tenant is deliberately accepted; execution applies it independently.
        dimensions = tuple(query_spec.get("dimensions", ()))
        measures_raw = tuple(query_spec.get("measures", ()))
        filters = tuple(query_spec.get("filters", ()))
        grouping = tuple(query_spec.get("grouping", ()))
        ordering_raw = tuple(query_spec.get("ordering", ()))
        row_limit = int(query_spec.get("row_limit", 500))
        measures = tuple(item if isinstance(item, Mapping) else {"key": str(item)} for item in measures_raw)
        ordering = tuple(
            item if isinstance(item, Mapping) else {"field": str(item), "direction": "asc"} for item in ordering_raw
        )

        invalid_dimensions = (set(dimensions) | set(grouping)) - self._DIMENSIONS
        invalid_measures = {str(item.get("key", "")) for item in measures} - self._MEASURES
        if invalid_dimensions or invalid_measures:
            raise ValueError("Query references unsupported execution-audit fields")
        for expression in filters:
            if not isinstance(expression, Mapping):
                raise ValueError("Filters must be objects")
            if expression.get("field") not in self._DIMENSIONS or expression.get("operator") not in self._OPERATORS:
                raise ValueError("Query contains an unsupported filter")
        for expression in ordering:
            if expression.get("field") not in self._DIMENSIONS | self._MEASURES:
                raise ValueError("Ordering references an unsupported field")
            if expression.get("direction", "asc") not in {"asc", "desc"}:
                raise ValueError("Ordering direction must be asc or desc")
        if row_limit < 1 or row_limit > self.describe().max_row_limit:
            raise ValueError("Row limit exceeds the execution-audit dataset maximum")
        canonical = json.dumps(query_spec, sort_keys=True, separators=(",", ":"), default=str)
        return ValidatedQuery(
            dataset_key=self.KEY,
            dimensions=dimensions,
            measures=measures,
            filters=filters,
            grouping=grouping,
            ordering=ordering,
            row_limit=row_limit,
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def execute(
        self,
        tenant_id: UUID,
        validated_query: ValidatedQuery,
        parameters: Mapping[str, JSONValue],
    ) -> DatasetResult:
        from .models import QueryExecution

        queryset = QueryExecution.objects.for_tenant(tenant_id)
        lookups = {"eq": "exact", "neq": "exact", "in": "in", "gte": "gte", "lte": "lte"}
        for expression in validated_query.filters:
            field = str(expression["field"])
            operator = str(expression["operator"])
            lookup = lookups[operator]
            parameter_name = expression.get("parameter")
            value = parameters.get(str(parameter_name)) if parameter_name else expression.get("value")
            clause = {f"{field}__{lookup}": value}
            queryset = queryset.exclude(**clause) if operator == "neq" else queryset.filter(**clause)

        dimension_fields = tuple(dict.fromkeys(validated_query.grouping or validated_query.dimensions))
        annotations: dict[str, models.Aggregate] = {}
        for selection in validated_query.measures:
            key = str(selection["key"])
            if key == "execution_count":
                annotations[key] = models.Count("id")
            elif key == "average_duration_ms":
                annotations[key] = models.Avg("duration_ms")
            elif key == "total_rows":
                annotations[key] = models.Sum("row_count")

        if annotations:
            queryset = queryset.values(*dimension_fields).annotate(**annotations)
        else:
            queryset = queryset.values(*dimension_fields)
        order_fields: list[str] = []
        for item in validated_query.ordering:
            field = str(item.get("field", ""))
            if field not in self._DIMENSIONS | self._MEASURES:
                raise ValueError("Ordering references an unsupported field")
            order_fields.append(f"-{field}" if item.get("direction") == "desc" else field)
        if order_fields:
            queryset = queryset.order_by(*order_fields)

        records = list(queryset[: validated_query.row_limit + 1])
        truncated = len(records) > validated_query.row_limit
        rows = tuple(records[: validated_query.row_limit])
        column_keys = (*dimension_fields, *(str(item["key"]) for item in validated_query.measures))
        columns = tuple({"key": key, "label": key.replace("_", " ").title()} for key in column_keys)
        latest = (
            QueryExecution.objects.for_tenant(tenant_id)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        return DatasetResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            freshness_token=latest.isoformat() if latest else "empty",
            data_as_of=latest,
        )

    def freshness_token(self, tenant_id: UUID) -> str:
        """Return a tenant-partitioned token which changes with execution evidence."""

        from .models import QueryExecution

        latest = (
            QueryExecution.objects.for_tenant(tenant_id)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        return latest.isoformat() if latest else "empty"

    def health(self) -> DependencyHealth:
        try:
            if "bi_query_executions" not in connection.introspection.table_names():
                return DependencyHealth(DependencyStatus.UNAVAILABLE, "Execution history storage unavailable")
        except DatabaseError:
            return DependencyHealth(DependencyStatus.UNAVAILABLE, "Execution history storage unavailable")
        return DependencyHealth(DependencyStatus.HEALTHY, "Execution history storage available")


dataset_registry = DatasetRegistry()
dataset_registry.register(ExecutionAuditDatasetProvider())
template_registry = ContributionRegistry()
visualization_registry = ContributionRegistry()

# Concise compatibility alias for extension modules.
registry = dataset_registry


__all__ = [
    "DatasetDescriptor",
    "DatasetProvider",
    "DatasetRegistry",
    "DatasetRegistrationError",
    "DatasetResult",
    "DatasetUnavailableError",
    "DependencyHealth",
    "DependencyStatus",
    "DimensionDescriptor",
    "ExecutionAuditDatasetProvider",
    "MeasureDescriptor",
    "ScalarType",
    "Sensitivity",
    "ValidatedQuery",
    "TemplateDescriptor",
    "TemplateProvider",
    "VisualizationDescriptor",
    "VisualizationProvider",
    "dataset_registry",
    "registry",
    "template_registry",
    "visualization_registry",
]
