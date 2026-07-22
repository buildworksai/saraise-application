"""Strict allowlisted collection filters for the email-marketing API."""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_datetime


class EmailMarketingFilterSet:
    """Small django-filter compatible boundary with reject-unknown semantics."""

    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering", "search"})
    exact_fields: ClassVar[frozenset[str]] = frozenset()
    uuid_fields: ClassVar[dict[str, str]] = {}
    boolean_fields: ClassVar[frozenset[str]] = frozenset()
    date_fields: ClassVar[dict[str, str]] = {}
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[str] = "-created_at"

    def __init__(self, data: object | None = None, queryset: QuerySet[Any] | None = None) -> None:
        self.data = data or {}
        self.queryset = queryset
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
        if self.queryset is None:
            self.errors["query"] = "A queryset is required."
            return False
        result = self.queryset
        for parameter, lookup in self.uuid_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            try:
                result = result.filter(**{lookup: UUID(str(value))})
            except (TypeError, ValueError, AttributeError):
                self.errors[parameter] = "Must be a valid UUID."
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
                self.errors[field] = "Must be a boolean."
            else:
                result = result.filter(**{field: normalized in {"true", "1"}})
        for parameter, lookup in self.date_fields.items():
            value = self._get(parameter)
            if value in (None, ""):
                continue
            parsed = parse_datetime(str(value))
            if parsed is None:
                self.errors[parameter] = "Must be an ISO-8601 datetime."
            else:
                result = result.filter(**{lookup: parsed})
        email = self._get("email")
        if email not in (None, ""):
            normalized_email = str(email).strip()
            if "@" not in normalized_email:
                self.errors["email"] = "Must be a valid email address."
            else:
                local, domain = normalized_email.rsplit("@", 1)
                result = result.filter(email=f"{local}@{domain.lower()}")
        search = self._get("search")
        if search not in (None, ""):
            if len(str(search)) > 100:
                self.errors["search"] = "Search is limited to 100 characters."
            else:
                result = self.apply_search(result, str(search).strip())
        ordering = str(self._get("ordering") or self.default_ordering)
        ordering_parts = [part.strip() for part in ordering.split(",") if part.strip()]
        if not ordering_parts or any(part.lstrip("-") not in self.ordering_fields for part in ordering_parts):
            self.errors["ordering"] = "Ordering field is not allowed."
        else:
            result = result.order_by(*ordering_parts)
        self._qs = result
        return not self.errors

    @property
    def qs(self) -> QuerySet[Any]:
        if self._qs is None:
            self.is_valid()
        if self._qs is None:
            raise ValueError("Filter set has no queryset")
        return self._qs

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        del search
        return queryset


class CampaignFilterSet(EmailMarketingFilterSet):
    allowed = EmailMarketingFilterSet.allowed | frozenset(
        {"status", "campaign_type", "template_id", "scheduled_after", "scheduled_before", "created_after", "created_before"}
    )
    exact_fields = frozenset({"status", "campaign_type"})
    uuid_fields = {"template_id": "template_id"}
    date_fields = {
        "scheduled_after": "scheduled_at__gte",
        "scheduled_before": "scheduled_at__lte",
        "created_after": "created_at__gte",
        "created_before": "created_at__lte",
    }
    ordering_fields = frozenset({"created_at", "scheduled_at", "campaign_name", "status"})

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(
            Q(campaign_code__icontains=search) | Q(campaign_name__icontains=search) | Q(subject__icontains=search)
        )


class TemplateFilterSet(EmailMarketingFilterSet):
    allowed = EmailMarketingFilterSet.allowed | frozenset({"status", "category"})
    exact_fields = frozenset({"status", "category"})
    ordering_fields = frozenset({"template_code", "template_name", "updated_at"})
    default_ordering = "template_code"

    def apply_search(self, queryset: QuerySet[Any], search: str) -> QuerySet[Any]:
        return queryset.filter(
            Q(template_code__icontains=search) | Q(template_name__icontains=search) | Q(subject__icontains=search)
        )


class RecipientFilterSet(EmailMarketingFilterSet):
    allowed = EmailMarketingFilterSet.allowed | frozenset({"campaign_id", "status", "email"})
    exact_fields = frozenset({"status"})
    uuid_fields = {"campaign_id": "campaign_id"}
    ordering_fields = frozenset({"created_at", "status"})


class DeliveryFilterSet(EmailMarketingFilterSet):
    allowed = EmailMarketingFilterSet.allowed | frozenset(
        {"campaign_id", "recipient_id", "status", "gateway_key", "created_after", "created_before"}
    )
    exact_fields = frozenset({"status", "gateway_key"})
    uuid_fields = {"campaign_id": "recipient__campaign_id", "recipient_id": "recipient_id"}
    date_fields = {"created_after": "created_at__gte", "created_before": "created_at__lte"}
    ordering_fields = frozenset({"created_at", "status", "attempt_number"})


class SuppressionFilterSet(EmailMarketingFilterSet):
    allowed = EmailMarketingFilterSet.allowed | frozenset({"active", "scope", "reason", "email"})
    exact_fields = frozenset({"scope", "reason"})
    boolean_fields = frozenset({"active"})
    ordering_fields = frozenset({"suppressed_at", "email", "reason"})
    default_ordering = "-suppressed_at"


class ConsentFilterSet(EmailMarketingFilterSet):
    allowed = EmailMarketingFilterSet.allowed | frozenset(
        {"status", "purpose", "source", "email", "captured_after", "captured_before"}
    )
    exact_fields = frozenset({"status", "purpose", "source"})
    date_fields = {"captured_after": "captured_at__gte", "captured_before": "captured_at__lte"}
    ordering_fields = frozenset({"captured_at", "email", "status"})
    default_ordering = "-captured_at"


__all__ = [
    "CampaignFilterSet",
    "ConsentFilterSet",
    "DeliveryFilterSet",
    "RecipientFilterSet",
    "SuppressionFilterSet",
    "TemplateFilterSet",
]
