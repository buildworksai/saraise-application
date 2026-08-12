"""Focused serializer coverage for tenant management contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from rest_framework import serializers

from src.modules.tenant_management.serializers import TenantListSerializer, TenantSerializer


def test_tenant_serializer_normalizes_slug_and_rejects_unsafe_slug():
    serializer = TenantSerializer()

    assert serializer.validate_slug("Acme_Tenant-01") == "acme_tenant-01"
    with pytest.raises(serializers.ValidationError, match="alphanumeric"):
        serializer.validate_slug("bad slug!")


def test_tenant_serializer_requires_domain_and_uses_instance_values_for_partial_updates():
    serializer = TenantSerializer()

    with pytest.raises(serializers.ValidationError, match="Either subdomain or custom_domain"):
        serializer.validate({"name": "No route"})

    instance = SimpleNamespace(
        subdomain="existing",
        custom_domain="",
        trial_ends_at=None,
        subscription_start_date=None,
    )
    serializer.instance = instance
    assert serializer.validate({"name": "Partial"}) == {"name": "Partial"}


def test_tenant_serializer_rejects_trial_after_subscription_start_with_instance_fallback():
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    serializer = TenantSerializer()

    with pytest.raises(serializers.ValidationError, match="Trial end date"):
        serializer.validate(
            {
                "subdomain": "trial",
                "trial_ends_at": start + timedelta(days=1),
                "subscription_start_date": start,
            }
        )

    serializer.instance = SimpleNamespace(
        subdomain="trial",
        custom_domain="",
        trial_ends_at=start + timedelta(days=2),
        subscription_start_date=start,
    )
    with pytest.raises(serializers.ValidationError, match="Trial end date"):
        serializer.validate({"subdomain": "trial"})


class _Relation:
    def __init__(self, result):
        self.result = result
        self.ordering: tuple[str, ...] | None = None

    def filter(self, **kwargs):
        self.kwargs = kwargs
        return self

    def count(self):
        return self.result

    def order_by(self, *fields):
        self.ordering = fields
        return self

    def first(self):
        return self.result


def test_tenant_list_serializer_summary_methods_use_latest_related_records():
    usage = SimpleNamespace(active_users=17)
    score = SimpleNamespace(overall_score=92)
    tenant = SimpleNamespace(
        modules=_Relation(4),
        resource_usage=_Relation(usage),
        health_scores=_Relation(score),
    )
    serializer = TenantListSerializer()

    assert serializer.get_module_count(tenant) == 4
    assert tenant.modules.kwargs == {"is_enabled": True}
    assert serializer.get_active_user_count(tenant) == 17
    assert tenant.resource_usage.ordering == ("-date",)
    assert serializer.get_current_health_score(tenant) == 92
    assert tenant.health_scores.ordering == ("-date",)


def test_tenant_list_serializer_summary_methods_default_empty_related_records():
    tenant = SimpleNamespace(
        modules=_Relation(0),
        resource_usage=_Relation(None),
        health_scores=_Relation(None),
    )
    serializer = TenantListSerializer()

    assert serializer.get_active_user_count(tenant) == 0
    assert serializer.get_current_health_score(tenant) is None
