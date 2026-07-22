"""Strict, bounded query filters for governed data-migration collections."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, ClassVar

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


class FilterValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("Invalid collection filters")


class BaseFilterSet:
    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "search", "ordering"})
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[tuple[str, ...]] = ("-created_at", "id")

    def __init__(self, data: object, queryset: QuerySet[Any]) -> None:
        self.data = data
        self.queryset = queryset
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def get(self, key: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(key) if callable(getter) else None

    def is_valid(self) -> bool:
        keys = set(getattr(self.data, "keys", lambda: ())())
        unsupported = keys - self.allowed
        if unsupported:
            self.errors["query"] = f"Unsupported filters: {', '.join(sorted(unsupported))}."
            return False
        try:
            result = self.apply_fields(self.queryset)
            result = self.apply_search(result)
            self._qs = self.apply_ordering(result)
        except FilterValidationError as exc:
            self.errors.update(exc.errors)
        return not self.errors

    @property
    def qs(self) -> QuerySet[Any]:
        if self._qs is None and not self.is_valid():
            raise FilterValidationError(self.errors)
        if self._qs is None:
            raise RuntimeError("FilterSet produced no queryset")
        return self._qs

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset

    def apply_search(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset

    def apply_ordering(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        raw = self.get("ordering")
        ordering = [part.strip() for part in str(raw).split(",") if part.strip()] if raw else list(self.default_ordering)
        if not ordering or any(item.removeprefix("-") not in self.ordering_fields | {"id"} for item in ordering):
            raise FilterValidationError({"ordering": "Unsupported ordering field."})
        if "id" not in {item.removeprefix("-") for item in ordering}:
            ordering.append("id")
        return queryset.order_by(*ordering)

    def exact(self, queryset: QuerySet[Any], fields: tuple[str, ...]) -> QuerySet[Any]:
        result = queryset
        for field in fields:
            value = self.get(field)
            if value not in (None, ""):
                result = result.filter(**{field: value})
        return result


class MigrationJobFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"status", "source_type", "target_adapter", "target_entity"})
    ordering_fields = frozenset({"name", "status", "source_type", "created_at", "updated_at", "configuration_version"})
    default_ordering = ("-created_at", "id")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return self.exact(queryset, ("status", "source_type", "target_adapter", "target_entity"))

    def apply_search(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        search = self.get("search")
        if search in (None, ""):
            return queryset
        value = str(search).strip()
        if len(value) > 200:
            raise FilterValidationError({"search": "Search is limited to 200 characters."})
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value) | Q(target_entity__icontains=value))


def _date_time(value: object, field: str, *, upper: bool = False) -> datetime:
    parsed = parse_datetime(str(value))
    if parsed is None:
        date = parse_date(str(value))
        if date is not None:
            parsed = datetime.combine(date, time.max if upper else time.min)
    if parsed is None:
        raise FilterValidationError({field: "Must be an ISO-8601 date or datetime."})
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


class MigrationRunFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"mode", "status", "created_after", "created_before"})
    ordering_fields = frozenset({"created_at", "status", "processed_records", "completed_at"})

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = self.exact(queryset, ("mode", "status"))
        after = self.get("created_after")
        before = self.get("created_before")
        after_dt = _date_time(after, "created_after") if after not in (None, "") else None
        before_dt = _date_time(before, "created_before", upper=True) if before not in (None, "") else None
        if after_dt and before_dt and after_dt > before_dt:
            raise FilterValidationError({"created_after": "Range start must not exceed its end."})
        if after_dt:
            result = result.filter(created_at__gte=after_dt)
        if before_dt:
            result = result.filter(created_at__lte=before_dt)
        return result


class MigrationRunIssueFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"severity", "stage", "code", "row_number"})
    ordering_fields = frozenset({"created_at", "row_number", "severity", "stage", "code"})
    default_ordering = ("row_number", "created_at", "id")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = self.exact(queryset, ("severity", "stage", "code"))
        row = self.get("row_number")
        if row not in (None, ""):
            try:
                number = int(str(row))
            except ValueError as exc:
                raise FilterValidationError({"row_number": "Must be a positive integer."}) from exc
            if number < 1:
                raise FilterValidationError({"row_number": "Must be a positive integer."})
            result = result.filter(row_number=number)
        return result


__all__ = [
    "FilterValidationError",
    "MigrationJobFilterSet",
    "MigrationRunFilterSet",
    "MigrationRunIssueFilterSet",
]
