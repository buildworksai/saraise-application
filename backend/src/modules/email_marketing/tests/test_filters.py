"""Truthful, resource-specific configured filter contracts."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.modules.email_marketing import filters, services


class RecordingQuerySet:
    def __init__(self) -> None:
        self.predicates: list[object] = []
        self.keyword_filters: list[dict[str, object]] = []
        self.orderings: list[tuple[str, ...]] = []

    def filter(self, *predicates: object, **kwargs: object) -> "RecordingQuerySet":
        self.predicates.extend(predicates)
        self.keyword_filters.append(kwargs)
        return self

    def order_by(self, *fields: str) -> "RecordingQuerySet":
        self.orderings.append(fields)
        return self


@pytest.fixture
def configured_filters(monkeypatch):
    document = services.get_platform_runtime_defaults()
    monkeypatch.setattr(
        services,
        "get_runtime_configuration",
        lambda tenant_id: SimpleNamespace(tenant_id=tenant_id, document=document),
    )
    return document


@pytest.mark.parametrize(
    ("filter_class", "expected_fields"),
    [
        (
            filters.CampaignFilterSet,
            {"campaign_code", "campaign_name", "subject"},
        ),
        (
            filters.TemplateFilterSet,
            {"template_code", "template_name", "subject"},
        ),
        (
            filters.RecipientFilterSet,
            {"email", "display_name", "recipient_key"},
        ),
        (filters.DeliveryFilterSet, {"provider_status_code", "error_code"}),
        (filters.SuppressionFilterSet, {"email"}),
        (filters.ConsentFilterSet, {"email", "notice_version"}),
    ],
)
def test_search_is_real_and_resource_specific(
    filter_class,
    expected_fields: set[str],
    configured_filters: dict[str, object],
) -> None:
    queryset = RecordingQuerySet()
    value = filter_class(
        {"search": "needle"},
        queryset=queryset,
        tenant_id=uuid4(),
    )

    assert value.is_valid(), value.errors
    assert len(queryset.predicates) == 1
    rendered = repr(queryset.predicates[0])
    assert all(f"{field}__icontains" in rendered for field in expected_fields)
    assert queryset.orderings


def test_search_limit_and_unknown_parameters_are_rejected(
    configured_filters: dict[str, object],
) -> None:
    limits = configured_filters["limits"]
    assert isinstance(limits, dict)
    limits["search_max_length"] = 4
    over_limit = filters.CampaignFilterSet(
        {"search": "12345"},
        queryset=RecordingQuerySet(),
        tenant_id=uuid4(),
    )
    unknown = filters.CampaignFilterSet(
        {"unsupported": "value"},
        queryset=RecordingQuerySet(),
        tenant_id=uuid4(),
    )

    assert not over_limit.is_valid()
    assert over_limit.errors == {"search": "Search is limited to 4 characters."}
    assert not unknown.is_valid()
    assert unknown.errors == {"query": "Unsupported filters: unsupported."}


def test_filtering_fails_closed_without_tenant_configuration() -> None:
    value = filters.CampaignFilterSet(
        {},
        queryset=RecordingQuerySet(),
    )

    with pytest.raises(ValueError, match="tenant_id is required"):
        value.is_valid()
