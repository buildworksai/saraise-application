"""Strict allowlisted collection filters for the email-marketing API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_datetime


class EmailMarketingFilterSet:
    """Small django-filter compatible boundary with reject-unknown semantics."""

    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering"})
    exact_fields: ClassVar[frozenset[str]] = frozenset()
    uuid_fields: ClassVar[dict[str, str]] = {}
    boolean_fields: ClassVar[frozenset[str]] = frozenset()
    date_fields: ClassVar[dict[str, str]] = {}
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    search_field_allowlist: ClassVar[frozenset[str]] = frozenset()
    resource_key: ClassVar[str]

    def __init__(
        self,
        data: object | None = None,
        queryset: QuerySet[Any] | None = None,
        *,
        tenant_id: UUID | None = None,
    ) -> None:
        self.data = data or {}
        self.queryset = queryset
        self.tenant_id = tenant_id
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def _get(self, key: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(key) if callable(getter) else None

    def _runtime_document(self) -> Mapping[str, object]:
        if not isinstance(self.tenant_id, UUID):
            raise ValueError("tenant_id is required to evaluate configured filters")
        # Lazy import avoids a services -> filters dependency cycle.
        from .services import get_runtime_configuration

        configuration = get_runtime_configuration(self.tenant_id)
        document = getattr(configuration, "document", None)
        if not isinstance(document, Mapping):
            raise ValueError("email marketing runtime configuration is unavailable")
        return document

    def _configured_section(self, name: str) -> Mapping[str, object]:
        policy = self._runtime_document().get(name)
        if not isinstance(policy, Mapping):
            raise ValueError(f"email marketing {name} configuration is unavailable")
        return policy

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
            limits = self._configured_section("limits")
            maximum = limits.get("search_max_length")
            if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
                raise ValueError("configured search_max_length is invalid")
            if len(str(search)) > maximum:
                self.errors["search"] = f"Search is limited to {maximum} characters."
            else:
                result = self.apply_search(result, str(search).strip())
        policy = self._configured_section("filters")
        defaults = policy.get("default_ordering_by_resource")
        if not isinstance(defaults, Mapping):
            raise ValueError("configured default orderings are invalid")
        default_ordering = defaults.get(self.resource_key)
        if not isinstance(default_ordering, str) or not default_ordering:
            raise ValueError(f"configured default ordering for {self.resource_key} is unavailable")
        ordering = str(self._get("ordering") or default_ordering)
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
        policy = self._configured_section("filters")
        configured_by_resource = policy.get("search_fields_by_resource")
        if not isinstance(configured_by_resource, Mapping):
            raise ValueError("configured search fields are invalid")
        raw_fields = configured_by_resource.get(self.resource_key)
        if not isinstance(raw_fields, (list, tuple)) or not raw_fields:
            raise ValueError(f"configured search fields for {self.resource_key} are unavailable")
        fields = tuple(str(field) for field in raw_fields)
        if any(field not in self.search_field_allowlist for field in fields):
            raise ValueError(f"configured search field for {self.resource_key} is not allowlisted")
        predicate = Q()
        for field in fields:
            predicate |= Q(**{f"{field}__icontains": search})
        return queryset.filter(predicate)


class CampaignFilterSet(EmailMarketingFilterSet):
    resource_key = "campaigns"
    allowed = EmailMarketingFilterSet.allowed | frozenset(
        {
            "search",
            "status",
            "campaign_type",
            "template_id",
            "scheduled_after",
            "scheduled_before",
            "created_after",
            "created_before",
        }
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
    search_field_allowlist = frozenset({"campaign_code", "campaign_name", "subject"})


class TemplateFilterSet(EmailMarketingFilterSet):
    resource_key = "templates"
    allowed = EmailMarketingFilterSet.allowed | frozenset({"search", "status", "category"})
    exact_fields = frozenset({"status", "category"})
    ordering_fields = frozenset({"template_code", "template_name", "updated_at"})
    search_field_allowlist = frozenset({"template_code", "template_name", "subject"})


class RecipientFilterSet(EmailMarketingFilterSet):
    resource_key = "recipients"
    allowed = EmailMarketingFilterSet.allowed | frozenset({"search", "campaign_id", "status", "email"})
    exact_fields = frozenset({"status"})
    uuid_fields = {"campaign_id": "campaign_id"}
    ordering_fields = frozenset({"created_at", "status"})
    search_field_allowlist = frozenset({"email", "display_name", "recipient_key"})


class DeliveryFilterSet(EmailMarketingFilterSet):
    resource_key = "deliveries"
    allowed = EmailMarketingFilterSet.allowed | frozenset(
        {
            "search",
            "campaign_id",
            "recipient_id",
            "status",
            "gateway_key",
            "created_after",
            "created_before",
        }
    )
    exact_fields = frozenset({"status", "gateway_key"})
    uuid_fields = {
        "campaign_id": "recipient__campaign_id",
        "recipient_id": "recipient_id",
    }
    date_fields = {
        "created_after": "created_at__gte",
        "created_before": "created_at__lte",
    }
    ordering_fields = frozenset({"created_at", "status", "attempt_number"})
    search_field_allowlist = frozenset({"provider_status_code", "error_code"})


class SuppressionFilterSet(EmailMarketingFilterSet):
    resource_key = "suppressions"
    allowed = EmailMarketingFilterSet.allowed | frozenset({"search", "active", "scope", "reason", "email"})
    exact_fields = frozenset({"scope", "reason"})
    boolean_fields = frozenset({"active"})
    ordering_fields = frozenset({"suppressed_at", "email", "reason"})
    search_field_allowlist = frozenset({"email"})


class ConsentFilterSet(EmailMarketingFilterSet):
    resource_key = "consents"
    allowed = EmailMarketingFilterSet.allowed | frozenset(
        {
            "search",
            "status",
            "purpose",
            "source",
            "email",
            "captured_after",
            "captured_before",
        }
    )
    exact_fields = frozenset({"status", "purpose", "source"})
    date_fields = {
        "captured_after": "captured_at__gte",
        "captured_before": "captured_at__lte",
    }
    ordering_fields = frozenset({"captured_at", "email", "status"})
    search_field_allowlist = frozenset({"email", "notice_version"})


__all__ = [
    "CampaignFilterSet",
    "ConsentFilterSet",
    "DeliveryFilterSet",
    "RecipientFilterSet",
    "SuppressionFilterSet",
    "TemplateFilterSet",
]
