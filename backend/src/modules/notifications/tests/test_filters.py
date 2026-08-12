"""Bounded query filter tests for notification collections."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from src.modules.notifications import filters


@dataclass
class RecordingQuerySet:
    filters: list[object] = field(default_factory=list)
    ordering: tuple[str, ...] = ()

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def order_by(self, *fields):
        self.ordering = tuple(fields)
        return self


def test_base_filter_set_rejects_unsupported_query_missing_queryset_and_bad_ordering():
    unsupported = filters.BaseNotificationFilterSet({"unexpected": "value"}, RecordingQuerySet())
    assert unsupported.is_valid() is False
    assert unsupported.errors == {"query": "Unsupported filters: unexpected."}

    missing = filters.BaseNotificationFilterSet({})
    with pytest.raises(ValueError, match="requires a queryset"):
        missing.is_valid()

    invalid_ordering = filters.BaseNotificationFilterSet({"ordering": "created_at,password"}, RecordingQuerySet())
    assert invalid_ordering.is_valid() is False
    assert invalid_ordering.errors == {"ordering": "Ordering field is not allowed."}


def test_base_filter_set_applies_search_and_stable_ordering():
    queryset = RecordingQuerySet()

    class SearchFilter(filters.BaseNotificationFilterSet):
        search_fields = ("title", "message")

    filter_set = SearchFilter({"search": " outage ", "ordering": "created_at"}, queryset)

    assert filter_set.is_valid() is True
    assert filter_set.qs is queryset
    assert queryset.ordering == ("created_at", "id")
    assert len(queryset.filters) == 1

    too_long = SearchFilter({"search": "x" * 201}, RecordingQuerySet())
    assert too_long.is_valid() is False
    assert too_long.errors == {"search": "Search is limited to 200 characters."}


def test_validation_helpers_normalize_and_fail_closed():
    identifier = uuid.uuid4()

    assert filters._uuid(str(identifier), "recipient_user") == identifier
    assert filters._uuid("", "recipient_user") is None
    with pytest.raises(filters.FilterValidationError) as uuid_error:
        filters._uuid("bad", "recipient_user")
    assert uuid_error.value.errors == {"recipient_user": "Must be a valid UUID."}

    assert filters._choice(" EMAIL ", "channel", filters.CHANNELS) == "email"
    with pytest.raises(filters.FilterValidationError) as choice_error:
        filters._choice("ftp", "channel", filters.CHANNELS)
    assert choice_error.value.errors == {"channel": "Value is not allowed."}

    assert filters._bounded_identifier(" general ", "category", 10) == "general"
    with pytest.raises(filters.FilterValidationError) as identifier_error:
        filters._bounded_identifier("x" * 11, "category", 10)
    assert identifier_error.value.errors == {"category": "Must not exceed 10 characters."}

    assert filters._datetime("2026-08-03", "created_after").hour == 0
    assert filters._datetime("2026-08-03", "created_before", upper=True).hour == 23
    with pytest.raises(filters.FilterValidationError) as datetime_error:
        filters._datetime("not-a-date", "created_after")
    assert datetime_error.value.errors == {"created_after": "Must be an ISO-8601 date or datetime."}


def test_inbox_filter_applies_allowed_fields_and_date_range():
    queryset = RecordingQuerySet()
    filter_set = filters.InboxFilterSet(
        {
            "status": "read",
            "type": "security",
            "category": "alerts",
            "created_after": "2026-08-01",
            "created_before": "2026-08-03",
        },
        queryset,
    )

    assert filter_set.is_valid() is True
    assert ("-created_at", "id") == queryset.ordering
    applied = [kwargs for _args, kwargs in queryset.filters]
    assert {"status": "read"} in applied
    assert {"notification_type": "security"} in applied
    assert {"category": "alerts"} in applied
    assert any("created_at__gte" in item for item in applied)
    assert any("created_at__lte" in item for item in applied)

    invalid_range = filters.InboxFilterSet(
        {"created_after": "2026-08-04", "created_before": "2026-08-03"},
        RecordingQuerySet(),
    )
    assert invalid_range.is_valid() is False
    assert invalid_range.errors == {"created_after": "Range start must not exceed its end."}


def test_template_delivery_attempt_endpoint_and_history_filters_apply_allowed_fields():
    template_qs = RecordingQuerySet()
    template = filters.TemplateFilterSet(
        {"channel": "email", "category": "billing", "locale": "en-US", "status": "active"},
        template_qs,
    )
    assert template.is_valid() is True
    assert template_qs.filters[-1][1] == {
        "channel": "email",
        "category": "billing",
        "locale": "en-US",
        "status": "active",
    }

    recipient = uuid.uuid4()
    delivery_qs = RecordingQuerySet()
    delivery = filters.DeliveryFilterSet(
        {
            "status": "sent",
            "channel": "push",
            "category": "workflow",
            "recipient_user": str(recipient),
            "ordering": "-sent_at",
        },
        delivery_qs,
    )
    assert delivery.is_valid() is True
    assert delivery_qs.ordering == ("-sent_at", "id")
    assert {"recipient_user_id": recipient} in [kwargs for _args, kwargs in delivery_qs.filters]

    attempt_qs = RecordingQuerySet()
    attempt = filters.DeliveryAttemptFilterSet({"outcome": "timeout", "adapter_key": "smtp"}, attempt_qs)
    assert attempt.is_valid() is True
    assert attempt_qs.filters[-1][1] == {"outcome": "timeout", "adapter_key": "smtp"}
    assert attempt_qs.ordering == ("attempt_number", "id")

    endpoint_qs = RecordingQuerySet()
    endpoint = filters.EndpointFilterSet({"kind": "webhook", "active": "false"}, endpoint_qs)
    assert endpoint.is_valid() is True
    assert {"kind": "webhook"} in [kwargs for _args, kwargs in endpoint_qs.filters]
    assert {"is_active": False} in [kwargs for _args, kwargs in endpoint_qs.filters]

    bad_endpoint = filters.EndpointFilterSet({"active": "sometimes"}, RecordingQuerySet())
    assert bad_endpoint.is_valid() is False
    assert bad_endpoint.errors == {"active": "Must be true or false."}

    history_qs = RecordingQuerySet()
    history = filters.ConfigurationHistoryFilterSet({"ordering": "-version"}, history_qs)
    assert history.is_valid() is True
    assert history_qs.ordering == ("-version", "id")
