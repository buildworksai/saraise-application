"""Bounded, allowlisted collection filters for DMS API v2."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time
from typing import Any, ClassVar
from uuid import UUID

from django.db import connection
from django.db.models import Q, QuerySet, TextField
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime


class FilterValidationError(ValueError):
    """Stable validation evidence consumed by governed API error envelopes."""

    def __init__(self, errors: Mapping[str, str]) -> None:
        self.errors = dict(errors)
        super().__init__("Invalid collection filters")


class BaseFilterSet:
    """Small django-filter-compatible boundary without an optional dependency."""

    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering", "search"})
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[tuple[str, ...]] = ("-created_at", "id")
    search_limit: ClassVar[int] = 200

    def __init__(self, data: object | None = None, queryset: QuerySet[Any] | None = None) -> None:
        self.data = data or {}
        self.queryset = queryset
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def _get(self, key: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(key) if callable(getter) else None

    def _getlist(self, key: str) -> list[object]:
        getter = getattr(self.data, "getlist", None)
        if callable(getter):
            return list(getter(key))
        value = self._get(key)
        if value in (None, ""):
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def is_valid(self) -> bool:
        keys = set(getattr(self.data, "keys", lambda: ())())
        unsupported = keys - self.allowed
        if unsupported:
            self.errors["query"] = f"Unsupported filters: {', '.join(sorted(unsupported))}."
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
        result = self.apply_fields(queryset)
        search = self._get("search")
        if search not in (None, ""):
            normalized_search = str(search).strip()
            if len(normalized_search) > self.search_limit:
                raise FilterValidationError({"search": "Search is limited to 200 characters."})
            if normalized_search:
                result = self.apply_search(result, normalized_search)
        return self.apply_ordering(result)

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        del search
        return queryset

    def apply_ordering(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        raw = self._get("ordering")
        ordering = (
            [field.strip() for field in str(raw).split(",") if field.strip()] if raw else list(self.default_ordering)
        )
        if not ordering or any(field.lstrip("-") not in self.ordering_fields | {"id"} for field in ordering):
            raise FilterValidationError({"ordering": "Ordering field is not allowed."})
        if "id" not in {field.lstrip("-") for field in ordering}:
            ordering.append("id")
        return queryset.order_by(*ordering)


def _optional_uuid(value: object | None, name: str) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise FilterValidationError({name: "Must be a valid UUID."}) from exc


def _datetime(value: object | None, name: str, *, end_of_day: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        date_value = parse_date(str(value))
        if date_value is not None:
            parsed = datetime.combine(date_value, time.max if end_of_day else time.min)
    if parsed is None:
        raise FilterValidationError({name: "Must be an ISO-8601 date or datetime."})
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


class FolderFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset({"parent_id"})
    ordering_fields = frozenset({"sort_order", "name", "path", "depth", "created_at", "updated_at"})
    default_ordering = ("sort_order", "name", "id")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        parent = self._get("parent_id")
        if parent in (None, "", "root"):
            return queryset.filter(parent_id__isnull=True) if parent == "root" else queryset
        return queryset.filter(parent_id=_optional_uuid(parent, "parent_id"))

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(Q(name__icontains=search) | Q(description__icontains=search) | Q(path__icontains=search))


class DocumentFilterSet(BaseFilterSet):
    allowed = BaseFilterSet.allowed | frozenset(
        {"folder", "mime_type", "creator", "tags", "modified_after", "modified_before"}
    )
    ordering_fields = frozenset({"name", "created_at", "updated_at", "version_count"})
    default_ordering = ("-updated_at", "name", "id")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        folder = self._get("folder")
        if folder == "root":
            result = result.filter(folder_id__isnull=True)
        elif folder not in (None, ""):
            result = result.filter(folder_id=_optional_uuid(folder, "folder"))
        mime_type = self._get("mime_type")
        if mime_type not in (None, ""):
            normalized_mime = str(mime_type).strip().lower()
            if len(normalized_mime) > 255 or "/" not in normalized_mime:
                raise FilterValidationError({"mime_type": "Must be a bounded MIME type."})
            result = result.filter(current_version__mime_type=normalized_mime)
        creator = _optional_uuid(self._get("creator"), "creator")
        if creator is not None:
            result = result.filter(created_by=creator)
        tags = [str(value).strip().casefold() for value in self._getlist("tags") if str(value).strip()]
        if len(tags) > 10 or any(len(tag) > 64 for tag in tags):
            raise FilterValidationError({"tags": "At most 10 tags of 64 characters may be filtered."})
        for tag in tags:
            if connection.features.supports_json_field_contains:
                result = result.filter(tags__contains=[tag])
            else:
                # SQLite is supported for local/self-hosted development. The
                # quotes preserve exact JSON array element matching.
                result = result.filter(tags__icontains=f'"{tag}"')
        modified_after = _datetime(self._get("modified_after"), "modified_after")
        modified_before = _datetime(self._get("modified_before"), "modified_before", end_of_day=True)
        if modified_after is not None:
            result = result.filter(updated_at__gte=modified_after)
        if modified_before is not None:
            result = result.filter(updated_at__lte=modified_before)
        if modified_after and modified_before and modified_after > modified_before:
            raise FilterValidationError({"modified_after": "Modified range start must not exceed its end."})
        return result

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        # Casting JSON to text is portable across supported SQL backends and
        # keeps search bounded without pulling metadata into Python.
        searchable = queryset.annotate(
            _dms_tags_text=Cast("tags", output_field=TextField()),
            _dms_metadata_text=Cast("metadata", output_field=TextField()),
        )
        return searchable.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(folder__path__icontains=search)
            | Q(_dms_tags_text__icontains=search)
            | Q(_dms_metadata_text__icontains=search)
        )


class RequiredDocumentFilterSet(BaseFilterSet):
    """Base for version, permission, and share collections."""

    allowed = BaseFilterSet.allowed | frozenset({"document_id"})

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        document_id = _optional_uuid(self._get("document_id"), "document_id")
        if document_id is None:
            raise FilterValidationError({"document_id": "This filter is required."})
        return queryset.filter(document_id=document_id)


class DocumentVersionFilterSet(RequiredDocumentFilterSet):
    ordering_fields = frozenset({"version_number", "created_at", "size_bytes"})
    default_ordering = ("-version_number", "id")


class DocumentPermissionFilterSet(RequiredDocumentFilterSet):
    ordering_fields = frozenset({"created_at", "principal_type", "permission"})


class DocumentShareFilterSet(RequiredDocumentFilterSet):
    ordering_fields = frozenset({"created_at", "expires_at", "access_count"})


__all__ = [
    "BaseFilterSet",
    "DocumentFilterSet",
    "DocumentPermissionFilterSet",
    "DocumentShareFilterSet",
    "DocumentVersionFilterSet",
    "FilterValidationError",
    "FolderFilterSet",
    "RequiredDocumentFilterSet",
]
