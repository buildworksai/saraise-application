"""Shared, explicit fixtures for Asset Management acceptance tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from src.core.access import AccessDecision, AccessDecisionPipeline, AccessReasonCode
from src.core.user_models import UserProfile
from src.modules.asset_management.models import DepreciationMethod
from src.modules.asset_management.services import AssetService


@pytest.fixture(autouse=True)
def development_mode(settings):
    """Keep licensing local while exercising real authentication and policy checks."""

    settings.SARAISE_MODE = "development"


@pytest.fixture(autouse=True)
def authorize_declared_access(monkeypatch):
    """Replace external access dependencies while preserving route metadata checks."""

    def decide(self, tenant_id, identity, required_permission, **kwargs):
        del self, required_permission, kwargs
        try:
            tenant = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        except (TypeError, ValueError):
            return AccessDecision(False, AccessReasonCode.POLICY_DENIED, "missing tenant", tenant_id=None)
        if getattr(getattr(identity, "profile", None), "tenant_role", "") == "tenant_user":
            return AccessDecision(False, AccessReasonCode.POLICY_DENIED, "test policy deny", tenant_id=tenant)
        return AccessDecision(True, AccessReasonCode.ALLOW, "test policy allow", tenant_id=tenant)

    monkeypatch.setattr(AccessDecisionPipeline, "decide", decide)


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user_factory(db):
    """Create users with isolated tenant profiles without requiring tenant fixtures."""

    serial = 0

    def create_user(*, tenant_id: UUID | str | None = None, role: str | None = "tenant_admin"):
        nonlocal serial
        serial += 1
        user = get_user_model().objects.create_user(
            username=f"asset-user-{serial}-{uuid4()}",
            email=f"asset-user-{serial}-{uuid4()}@example.test",
            password="test-password",
        )
        profile = user.profile
        profile.tenant_id = str(tenant_id) if tenant_id is not None else None
        profile.tenant_role = role
        profile.platform_role = None
        # Profile validation normally verifies a real licensed organization. These
        # module tests deliberately isolate API tenancy from licensing persistence.
        with patch.object(UserProfile, "clean"):
            profile.save()
        return get_user_model().objects.get(pk=user.pk)

    return create_user


@pytest.fixture
def tenant_a() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_b() -> UUID:
    return uuid4()


@pytest.fixture
def tenant_a_user(user_factory, tenant_a):
    return user_factory(tenant_id=tenant_a)


@pytest.fixture
def tenant_b_user(user_factory, tenant_b):
    return user_factory(tenant_id=tenant_b)


@pytest.fixture
def asset_factory(db):
    serial = 0

    def create_asset(
        tenant_id: UUID,
        *,
        asset_code: str | None = None,
        asset_name: str = "Test asset",
        purchase_cost: Decimal = Decimal("1200.00"),
        residual_value: Decimal = Decimal("0.00"),
        depreciation_method: str = DepreciationMethod.STRAIGHT_LINE,
        useful_life_years: int | None = 10,
        **kwargs,
    ):
        nonlocal serial
        serial += 1
        return AssetService.create_asset(
            tenant_id,
            asset_code=asset_code or f"ASSET-{serial:03d}",
            asset_name=asset_name,
            purchase_date=date(2024, 1, 1),
            purchase_cost=purchase_cost,
            residual_value=residual_value,
            depreciation_method=depreciation_method,
            useful_life_years=useful_life_years,
            idempotency_key=f"asset-factory-{tenant_id}-{serial}",
            **kwargs,
        )

    return create_asset


def response_items(response) -> list[dict]:
    """Extract collection rows without weakening the pagination assertion sites."""

    data = response.data
    return data["results"] if isinstance(data, dict) and "results" in data else data
