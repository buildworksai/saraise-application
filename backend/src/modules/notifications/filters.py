"""Bounded, allowlisted filters for notification collections."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time
from typing import Any, ClassVar
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

CHANNELS = frozenset({"in_app", "email", "sms", "push", "webhook"})
INBOX_STATUSES = frozenset({"unread", "read", "archived"})
NOTIFICATION_TYPES = frozenset({"info", "success", "warning", "error", "workflow", "approval", "system", "security"})
TEMPLATE_STATUSES = frozenset({"draft", "active", "archived"})
DELIVERY_STATUSES = frozenset(
    {"pending", "queued", "sending", "sent", "delivered", "retry_wait", "failed", "cancelled", "skipped"}
)
ATTEMPT_OUTCOMES = frozenset(
    {"accepted", "retryable_failure", "permanent_failure", "circuit_open", "timeout"}
)


class FilterValidationError(ValueError):
    """Stable field errors for the governed exception envelope."""

    def __init__(self, errors: Mapping[str, str]) -> None:
        self.errors = dict(errors)
        super().__init__("Invalid notification collection filters")


class BaseNotificationFilterSet:
    allowed: ClassVar[frozenset[str]] = frozenset({"page", "page_size", "ordering", "search"})
    ordering_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})
    default_ordering: ClassVar[tuple[str, ...]] = ("-created_at", "id")
    search_fields: ClassVar[tuple[str, ...]] = ()
    search_limit: ClassVar[int] = 200

    def __init__(self, data: object | None = None, queryset: QuerySet[Any] | None = None) -> None:
        self.data = data or {}
        self.queryset = queryset
        self.errors: dict[str, str] = {}
        self._qs: QuerySet[Any] | None = None

    def get(self, name: str) -> object | None:
        getter = getattr(self.data, "get", None)
        return getter(name) if callable(getter) else None

    def is_valid(self) -> bool:
        keys = set(getattr(self.data, "keys", lambda: ())())
        unsupported = keys - self.allowed
        if unsupported:
            self.errors["query"] = f"Unsupported filters: {', '.join(sorted(unsupported))}."
            return False
        try:
            if self.queryset is None:
                raise ValueError("FilterSet requires a queryset")
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
            raise ValueError("FilterSet requires a queryset")
        return self._qs

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset

    def apply_search(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        raw = self.get("search")
        if raw in (None, ""):
            return queryset
        value = str(raw).strip()
        if len(value) > self.search_limit:
            raise FilterValidationError({"search": "Search is limited to 200 characters."})
        if not value or not self.search_fields:
            return queryset
        expression = Q()
        for field_name in self.search_fields:
            expression |= Q(**{f"{field_name}__icontains": value})
        return queryset.filter(expression)

    def apply_ordering(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        raw = self.get("ordering")
        ordering = (
            [part.strip() for part in str(raw).split(",") if part.strip()]
            if raw
            else list(self.default_ordering)
        )
        if not ordering or any(item.lstrip("-") not in self.ordering_fields | {"id"} for item in ordering):
            raise FilterValidationError({"ordering": "Ordering field is not allowed."})
        if "id" not in {item.lstrip("-") for item in ordering}:
            ordering.append("id")
        return queryset.order_by(*ordering)

    def exact(self, queryset: QuerySet[Any], *names: str) -> QuerySet[Any]:
        result = queryset
        for name in names:
            value = self.get(name)
            if value not in (None, ""):
                result = result.filter(**{name: str(value).strip()})
        return result


def _uuid(value: object | None, field_name: str) -> UUID | None:
    if value in (None, ""):
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FilterValidationError({field_name: "Must be a valid UUID."}) from exc


def _choice(value: object | None, field_name: str, choices: frozenset[str]) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if normalized not in choices:
        raise FilterValidationError({field_name: "Value is not allowed."})
    return normalized


def _bounded_identifier(value: object | None, field_name: str, maximum: int) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip()
    if not normalized or len(normalized) > maximum:
        raise FilterValidationError({field_name: f"Must not exceed {maximum} characters."})
    return normalized


def _datetime(value: object | None, field_name: str, *, upper: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        parsed_date = parse_date(str(value))
        if parsed_date is not None:
            parsed = datetime.combine(parsed_date, time.max if upper else time.min)
    if parsed is None:
        raise FilterValidationError({field_name: "Must be an ISO-8601 date or datetime."})
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def _date_range(
    queryset: QuerySet[Any],
    data: BaseNotificationFilterSet,
    *,
    field: str = "created_at",
) -> QuerySet[Any]:
    after = _datetime(data.get("created_after"), "created_after")
    before = _datetime(data.get("created_before"), "created_before", upper=True)
    if after and before and after > before:
        raise FilterValidationError({"created_after": "Range start must not exceed its end."})
    if after:
        queryset = queryset.filter(**{f"{field}__gte": after})
    if before:
        queryset = queryset.filter(**{f"{field}__lte": before})
    return queryset


class InboxFilterSet(BaseNotificationFilterSet):
    allowed = BaseNotificationFilterSet.allowed | frozenset(
        {"status", "type", "category", "created_after", "created_before"}
    )
    ordering_fields = frozenset({"created_at", "updated_at", "status", "notification_type", "category"})
    search_fields = ("title", "message", "category")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        status = _choice(self.get("status"), "status", INBOX_STATUSES)
        category = _bounded_identifier(self.get("category"), "category", 100)
        notification_type = _choice(self.get("type"), "type", NOTIFICATION_TYPES)
        if status:
            result = result.filter(status=status)
        if category:
            result = result.filter(category=category)
        if notification_type:
            result = result.filter(notification_type=notification_type)
        return _date_range(result, self)


class TemplateFilterSet(BaseNotificationFilterSet):
    allowed = BaseNotificationFilterSet.allowed | frozenset({"channel", "category", "locale", "status"})
    ordering_fields = frozenset({"created_at", "updated_at", "code", "name", "channel", "locale", "status"})
    search_fields = ("code", "name", "category")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        values = {
            "channel": _choice(self.get("channel"), "channel", CHANNELS),
            "category": _bounded_identifier(self.get("category"), "category", 100),
            "locale": _bounded_identifier(self.get("locale"), "locale", 16),
            "status": _choice(self.get("status"), "status", TEMPLATE_STATUSES),
        }
        return result.filter(**{key: value for key, value in values.items() if value is not None})


class DeliveryFilterSet(BaseNotificationFilterSet):
    allowed = BaseNotificationFilterSet.allowed | frozenset(
        {"status", "channel", "category", "recipient_user", "created_after", "created_before"}
    )
    ordering_fields = frozenset(
        {"created_at", "updated_at", "status", "channel", "category", "priority", "scheduled_at", "sent_at"}
    )
    search_fields = ("recipient_display", "failure_code", "provider_message_id")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        status = _choice(self.get("status"), "status", DELIVERY_STATUSES)
        channel = _choice(self.get("channel"), "channel", CHANNELS)
        category = _bounded_identifier(self.get("category"), "category", 100)
        if status:
            result = result.filter(status=status)
        if channel:
            result = result.filter(channel=channel)
        if category:
            result = result.filter(category=category)
        recipient_user = _uuid(self.get("recipient_user"), "recipient_user")
        if recipient_user is not None:
            result = result.filter(recipient_user_id=recipient_user)
        return _date_range(result, self)


class DeliveryAttemptFilterSet(BaseNotificationFilterSet):
    allowed = BaseNotificationFilterSet.allowed | frozenset({"outcome", "adapter_key"})
    ordering_fields = frozenset({"attempt_number", "started_at", "completed_at", "latency_ms"})
    default_ordering = ("attempt_number", "id")

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        outcome = _choice(self.get("outcome"), "outcome", ATTEMPT_OUTCOMES)
        adapter_key = _bounded_identifier(self.get("adapter_key"), "adapter_key", 100)
        values = {"outcome": outcome, "adapter_key": adapter_key}
        return queryset.filter(**{key: value for key, value in values.items() if value is not None})


class EndpointFilterSet(BaseNotificationFilterSet):
    allowed = BaseNotificationFilterSet.allowed | frozenset({"kind", "active"})
    ordering_fields = frozenset({"created_at", "updated_at", "kind", "display_name", "last_verified_at"})
    search_fields = ("display_name",)

    def apply_fields(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        result = queryset
        kind = _choice(self.get("kind"), "kind", frozenset({"push", "webhook"}))
        if kind:
            result = result.filter(kind=kind)
        active = self.get("active")
        if active not in (None, ""):
            normalized = str(active).strip().lower()
            if normalized not in {"true", "false"}:
                raise FilterValidationError({"active": "Must be true or false."})
            result = result.filter(is_active=normalized == "true")
        return result


class ConfigurationHistoryFilterSet(BaseNotificationFilterSet):
    ordering_fields = frozenset({"version", "created_at"})
    default_ordering = ("-version", "id")


__all__ = [
    "BaseNotificationFilterSet",
    "ConfigurationHistoryFilterSet",
    "DeliveryAttemptFilterSet",
    "DeliveryFilterSet",
    "EndpointFilterSet",
    "FilterValidationError",
    "InboxFilterSet",
    "TemplateFilterSet",
]
