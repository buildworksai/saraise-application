"""Allowlisted server-side filters for document-intelligence collections.

The project base currently does not install ``django-filter``.  These classes
provide the same narrow FilterSet boundary (``data``, ``queryset``, ``is_valid``,
``errors``, and ``qs``) without moving query parsing into ViewSets.  They can be
replaced by django-filter subclasses without changing controllers or services.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_datetime


class FilterValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("Invalid collection filters")


class BaseFilterSet:
    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering", "search"})
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[str] = "-created_at"
    uuid_fields: ClassVar[frozenset[str]] = frozenset()
    exact_fields: ClassVar[frozenset[str]] = frozenset()
    boolean_fields: ClassVar[frozenset[str]] = frozenset()
    date_fields: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        data: object | None = None,
        queryset: QuerySet[Any] | None = None,
        *,
        search_max_length: int | None = None,
    ) -> None:
        if search_max_length is None:
            from .services import default_configuration_document

            search_max_length = int(default_configuration_document()["limits"]["search_max_length"])
        if isinstance(search_max_length, bool) or search_max_length <= 0:
            raise ValueError("search_max_length must be a positive integer")
        self.data = data or {}
        self.queryset = queryset
        self.search_max_length = search_max_length
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def _get(self, key: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(key) if callable(getter) else None

    def is_valid(self) -> bool:
        keys = set(getattr(self.data, "keys", lambda: ())())
        unknown = keys - self.allowed
        if unknown:
            self.errors["query"] = f"Unsupported filters: {', '.join(sorted(unknown))}."
            return False
        try:
            self._qs = self.apply(self.queryset)
        except FilterValidationError as exc:
            self.errors.update(exc.errors)
        return not self.errors

    @property
    def qs(self) -> QuerySet[Any]:
        if self._qs is None and not self.is_valid():
            raise FilterValidationError(self.errors)
        if self._qs is None:
            raise ValueError("FilterSet requires a queryset")
        return self._qs

    def apply(self, queryset: QuerySet[Any] | None) -> QuerySet[Any]:
        if queryset is None:
            raise ValueError("FilterSet requires a queryset")
        result = queryset
        errors: dict[str, str] = {}
        for field in self.uuid_fields:
            value = self._get(field)
            if value in (None, ""):
                continue
            try:
                parsed = UUID(str(value))
            except (TypeError, ValueError, AttributeError):
                errors[field] = "Must be a valid UUID."
            else:
                result = result.filter(**{field: parsed})
        for field in self.exact_fields:
            value = self._get(field)
            if value not in (None, ""):
                result = result.filter(**{field: value})
        for field in self.boolean_fields:
            value = self._get(field)
            if value in (None, ""):
                continue
            normalized = str(value).lower()
            if normalized not in {"true", "false", "1", "0"}:
                errors[field] = "Must be a boolean."
            else:
                result = result.filter(**{field: normalized in {"true", "1"}})
        for parameter, lookup in self.date_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            parsed = parse_datetime(str(value))
            if parsed is None:
                errors[parameter] = "Must be an ISO-8601 datetime."
            else:
                result = result.filter(**{lookup: parsed})
        search = self._get("search")
        if search not in (None, ""):
            if len(str(search)) > self.search_max_length:
                errors["search"] = f"Search is limited to {self.search_max_length} characters."
            else:
                result = self.apply_search(result, str(search))
        ordering = str(self._get("ordering") or self.default_ordering)
        fields = [part.strip() for part in ordering.split(",") if part.strip()]
        if not fields or any(field.lstrip("-") not in self.ordering_fields for field in fields):
            errors["ordering"] = "Ordering field is not allowed."
        else:
            result = result.order_by(*fields)
        if errors:
            raise FilterValidationError(errors)
        return self.apply_extra(result)

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        del search
        return queryset

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset


class DocumentExtractionFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {
            "document_id",
            "status",
            "engine",
            "extraction_type",
            "template_id",
            "created_after",
            "created_before",
            "confidence_min",
        }
    )
    uuid_fields = frozenset({"document_id", "template_id"})
    exact_fields = frozenset({"status", "engine", "extraction_type"})
    date_fields = {"created_after": "created_at__gte", "created_before": "created_at__lte"}
    ordering_fields = frozenset({"created_at", "confidence", "processing_time_ms"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        try:
            document_id = UUID(search)
        except ValueError:
            return queryset.none()
        return queryset.filter(document_id=document_id)

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        value = self._get("confidence_min")
        if value in (None, ""):
            return queryset
        try:
            confidence = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise FilterValidationError({"confidence_min": "Must be a decimal between zero and one."})
        if not confidence.is_finite() or confidence < 0 or confidence > 1:
            raise FilterValidationError({"confidence_min": "Must be a decimal between zero and one."})
        return queryset.filter(confidence__gte=confidence)


class DocumentClassificationFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {
            "document_id",
            "status",
            "category",
            "needs_review",
            "review_status",
            "confidence_min",
            "confidence_max",
            "created_after",
            "created_before",
        }
    )
    uuid_fields = frozenset({"document_id"})
    exact_fields = frozenset({"status", "category", "review_status"})
    boolean_fields = frozenset({"needs_review"})
    date_fields = {"created_after": "created_at__gte", "created_before": "created_at__lte"}
    ordering_fields = frozenset({"created_at", "confidence", "processing_time_ms"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        try:
            identifier = UUID(search)
        except ValueError:
            return queryset.filter(category__icontains=search)
        return queryset.filter(Q(document_id=identifier) | Q(id=identifier))

    def apply_extra(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        filters: dict[str, Decimal] = {}
        errors: dict[str, str] = {}
        parsed: dict[str, Decimal] = {}
        for parameter, lookup in (("confidence_min", "confidence__gte"), ("confidence_max", "confidence__lte")):
            value = self._get(parameter)
            if value in (None, ""):
                continue
            try:
                confidence = Decimal(str(value))
            except (InvalidOperation, ValueError):
                errors[parameter] = "Must be a finite decimal between zero and one."
                continue
            if not confidence.is_finite() or confidence < 0 or confidence > 1:
                errors[parameter] = "Must be a finite decimal between zero and one."
                continue
            parsed[parameter] = confidence
            filters[lookup] = confidence
        if not errors and parsed.get("confidence_min", Decimal("0")) > parsed.get("confidence_max", Decimal("1")):
            errors["confidence_max"] = "Must be greater than or equal to confidence_min."
        if errors:
            raise FilterValidationError(errors)
        return queryset.filter(**filters)


class ExtractionTemplateFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"status", "engine", "document_category"})
    exact_fields = frozenset({"status", "engine", "document_category"})
    ordering_fields = frozenset({"created_at", "name", "version", "status"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))


class TemplateZoneFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"template_id", "page_number", "zone_type"})
    uuid_fields = frozenset({"template_id"})
    exact_fields = frozenset({"page_number", "zone_type"})
    ordering_fields = frozenset({"page_number", "zone_name", "created_at"})
    default_ordering = "page_number,zone_name"

    def is_valid(self) -> bool:
        if self._get("template_id") in (None, ""):
            self.errors["template_id"] = "This filter is required."
            return False
        return super().is_valid()


class ClassifierTrainingJobFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"status", "requested_version", "created_after", "created_before"})
    exact_fields = frozenset({"status", "requested_version"})
    date_fields = {"created_after": "created_at__gte", "created_before": "created_at__lte"}
    ordering_fields = frozenset({"created_at", "training_data_count", "accuracy", "status"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(Q(name__icontains=search) | Q(requested_version__icontains=search))


class ClassifierModelVersionFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"status", "provider_key"})
    exact_fields = frozenset({"status", "provider_key"})
    ordering_fields = frozenset({"created_at", "accuracy", "version", "status"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(version__icontains=search)


__all__ = [name for name in globals() if name.endswith("FilterSet")]
