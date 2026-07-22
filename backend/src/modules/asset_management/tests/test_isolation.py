"""End-to-end tenant isolation evidence for every public operation."""

from datetime import date

import pytest
from rest_framework import status

from src.modules.asset_management.models import Asset, DepreciationEntry
from src.modules.asset_management.services import DepreciationService

from .conftest import response_items

pytestmark = pytest.mark.django_db
ASSETS_URL = "/api/v1/asset-management/assets/"
DEPRECIATION_URL = "/api/v1/asset-management/depreciation-entries/"


def create_payload(**overrides):
    payload = {
        "asset_code": "TENANT-A-NEW",
        "asset_name": "Tenant A asset",
        "category": "fixed",
        "purchase_date": "2024-01-01",
        "purchase_cost": "1200.00",
        "depreciation_method": "straight_line",
        "useful_life_years": 10,
    }
    payload.update(overrides)
    return payload


def test_asset_list_excludes_other_tenant(api_client, tenant_a_user, asset_factory, tenant_a, tenant_b):
    own = asset_factory(tenant_a, asset_code="OWN")
    foreign = asset_factory(tenant_b, asset_code="FOREIGN")
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.get(ASSETS_URL)

    ids = {row["id"] for row in response_items(response)}
    assert response.status_code == status.HTTP_200_OK
    assert str(own.id) in ids
    assert str(foreign.id) not in ids


def test_asset_detail_cross_tenant_is_404(api_client, tenant_a_user, asset_factory, tenant_b):
    foreign = asset_factory(tenant_b)
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.get(f"{ASSETS_URL}{foreign.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_asset_create_injects_authenticated_tenant(api_client, tenant_a_user, tenant_a):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(ASSETS_URL, create_payload(), format="json")

    assert response.status_code == status.HTTP_201_CREATED
    created = Asset.objects.get(pk=response.data["id"])
    assert created.tenant_id == tenant_a


def test_asset_create_rejects_tenant_spoof(api_client, tenant_a_user, tenant_a, tenant_b):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(ASSETS_URL, create_payload(tenant_id=str(tenant_b)), format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "tenant_id" in response.data
    assert not Asset.objects.for_tenant(tenant_a).filter(asset_code="TENANT-A-NEW").exists()
    assert not Asset.objects.for_tenant(tenant_b).filter(asset_code="TENANT-A-NEW").exists()


@pytest.mark.parametrize("method", ["put", "patch"])
def test_asset_update_cross_tenant_is_404_and_unchanged(
    api_client,
    tenant_a_user,
    asset_factory,
    tenant_b,
    method,
):
    foreign = asset_factory(tenant_b, asset_name="Original")
    api_client.force_authenticate(user=tenant_a_user)

    response = getattr(api_client, method)(
        f"{ASSETS_URL}{foreign.id}/",
        {"asset_name": "Compromised"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    foreign.refresh_from_db()
    assert foreign.asset_name == "Original"


def test_asset_delete_cross_tenant_is_404_and_preserves_row(api_client, tenant_a_user, asset_factory, tenant_b):
    foreign = asset_factory(tenant_b)
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.delete(f"{ASSETS_URL}{foreign.id}/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    foreign.refresh_from_db()
    assert foreign.is_deleted is False
    assert foreign.is_active is True


def test_depreciation_list_and_detail_exclude_other_tenant(
    api_client,
    tenant_a_user,
    asset_factory,
    tenant_a,
    tenant_b,
):
    own_asset = asset_factory(tenant_a)
    foreign_asset = asset_factory(tenant_b)
    own = DepreciationService.calculate_depreciation(tenant_a, own_asset.id, date(2024, 2, 1))
    foreign = DepreciationService.calculate_depreciation(tenant_b, foreign_asset.id, date(2024, 2, 1))
    api_client.force_authenticate(user=tenant_a_user)

    listing = api_client.get(DEPRECIATION_URL)
    detail = api_client.get(f"{DEPRECIATION_URL}{foreign.id}/")

    assert listing.status_code == status.HTTP_200_OK
    ids = {row["id"] for row in response_items(listing)}
    assert str(own.id) in ids
    assert str(foreign.id) not in ids
    assert detail.status_code == status.HTTP_404_NOT_FOUND


def test_depreciation_foreign_asset_filter_cannot_expose_rows(
    api_client,
    tenant_a_user,
    asset_factory,
    tenant_a,
    tenant_b,
):
    own_asset = asset_factory(tenant_a)
    foreign_asset = asset_factory(tenant_b)
    DepreciationService.calculate_depreciation(tenant_a, own_asset.id, date(2024, 2, 1))
    DepreciationService.calculate_depreciation(tenant_b, foreign_asset.id, date(2024, 2, 1))
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.get(DEPRECIATION_URL, {"asset_id": str(foreign_asset.id)})

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    assert response_items(response) == []


def test_depreciation_filter_rejects_malformed_asset_uuid(api_client, tenant_a_user):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.get(DEPRECIATION_URL, {"asset_id": "not-a-uuid"})

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "asset_id" in response.data


def test_cross_tenant_depreciation_calculation_is_404(api_client, tenant_a_user, asset_factory, tenant_b):
    foreign = asset_factory(tenant_b)
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(
        f"{ASSETS_URL}{foreign.id}/calculate-depreciation/",
        {"entry_date": "2024-02-01"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert not DepreciationEntry.objects.filter(asset=foreign).exists()


@pytest.mark.parametrize("tenant_value", [None, "", "not-a-uuid"])
def test_missing_or_invalid_tenant_context_fails_closed(api_client, user_factory, tenant_value):
    role = None if tenant_value in (None, "") else "tenant_admin"
    user = user_factory(tenant_id=tenant_value, role=role)
    api_client.force_authenticate(user=user)

    listing = api_client.get(ASSETS_URL)
    creation = api_client.post(ASSETS_URL, create_payload(), format="json")

    # Missing or malformed profile authority denies both reads and writes.
    assert listing.status_code == status.HTTP_403_FORBIDDEN
    assert creation.status_code == status.HTTP_403_FORBIDDEN
    assert not Asset.objects.filter(asset_code="TENANT-A-NEW").exists()
