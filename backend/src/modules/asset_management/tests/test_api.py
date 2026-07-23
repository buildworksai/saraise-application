"""Public API, authorization, validation, and failure-contract tests."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework import status

from src.modules.asset_management.models import Asset, DepreciationEntry
from src.modules.asset_management.services import DEFAULT_CONFIGURATION, DepreciationService

from .conftest import response_items

pytestmark = pytest.mark.django_db
ASSETS_URL = "/api/v1/asset-management/assets/"
DEPRECIATION_URL = "/api/v1/asset-management/depreciation-entries/"
HEALTH_URL = "/api/v1/asset-management/health/"
CONFIG_URL = "/api/v1/asset-management/configuration/"


def valid_asset_payload(**overrides):
    payload = {
        "asset_code": "AST-001",
        "asset_name": "Production press",
        "category": "fixed",
        "purchase_date": "2024-01-01",
        "purchase_cost": "1200.00",
        "residual_value": "0.00",
        "depreciation_method": "straight_line",
        "useful_life_years": 10,
        "location": "Plant 1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("url", [ASSETS_URL, DEPRECIATION_URL])
def test_unauthenticated_collections_return_401(api_client, url):
    response = api_client.get(url)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.parametrize(
    ("method", "url", "data"),
    [
        ("get", ASSETS_URL, None),
        ("post", ASSETS_URL, valid_asset_payload()),
        ("get", DEPRECIATION_URL, None),
    ],
)
def test_authenticated_user_without_manifest_permission_gets_403(api_client, user_factory, tenant_a, method, url, data):
    user = user_factory(tenant_id=tenant_a, role="tenant_user")
    api_client.force_authenticate(user=user)

    response = (
        getattr(api_client, method)(url, data, format="json") if data is not None else getattr(api_client, method)(url)
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_create_persists_server_derived_current_value(api_client, tenant_a_user, tenant_a):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(ASSETS_URL, valid_asset_payload(purchase_cost="2500.00"), format="json", HTTP_IDEMPOTENCY_KEY="api-create-success")

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["current_value"] == "2500.00"
    created = Asset.objects.get(pk=response.data["id"])
    assert created.tenant_id == tenant_a
    assert created.current_value == Decimal("2500.00")
    assert response["Location"].endswith(f"{created.id}/")


@pytest.mark.parametrize("server_field", ["tenant_id", "current_value", "is_deleted", "deleted_at", "is_active"])
def test_create_rejects_server_owned_field_spoofing(api_client, tenant_a_user, server_field, tenant_b):
    api_client.force_authenticate(user=tenant_a_user)
    value = {
        "tenant_id": str(tenant_b),
        "current_value": "1.00",
        "is_deleted": True,
        "deleted_at": "2024-01-01T00:00:00Z",
        "is_active": False,
    }[server_field]

    response = api_client.post(ASSETS_URL, valid_asset_payload(**{server_field: value}), format="json", HTTP_IDEMPOTENCY_KEY=f"api-spoof-{server_field}")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert server_field in response.data
    assert not Asset.objects.filter(asset_code="AST-001").exists()


def test_create_rejects_unknown_fields_instead_of_silently_ignoring_them(api_client, tenant_a_user):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(
        ASSETS_URL,
        valid_asset_payload(uncontracted_financial_field="100.00"),
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-unknown-field",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "uncontracted_financial_field" in response.data


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"purchase_date": "not-a-date"}, "purchase_date"),
        ({"purchase_cost": "not-money"}, "purchase_cost"),
        ({"purchase_cost": "0.00"}, "purchase_cost"),
        ({"residual_value": "1200.01"}, "residual_value"),
        ({"depreciation_method": "sum_of_years_digits"}, "depreciation_method"),
        ({"useful_life_years": 0}, "useful_life_years"),
        ({"useful_life_years": 101}, "useful_life_years"),
        ({"useful_life_years": None}, "useful_life_years"),
    ],
)
def test_create_rejects_malformed_or_invalid_payloads(api_client, tenant_a_user, changes, field):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(ASSETS_URL, valid_asset_payload(**changes), format="json", HTTP_IDEMPOTENCY_KEY=f"api-invalid-{field}")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data


def test_duplicate_code_returns_validation_error_without_overwrite(api_client, tenant_a_user, asset_factory, tenant_a):
    existing = asset_factory(tenant_a, asset_code="AST-001", asset_name="Existing")
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(ASSETS_URL, valid_asset_payload(asset_name="Replacement"), format="json", HTTP_IDEMPOTENCY_KEY="api-duplicate-code")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "asset_code" in response.data
    existing.refresh_from_db()
    assert existing.asset_name == "Existing"


def test_list_is_paginated_searchable_filterable_and_ordered(api_client, tenant_a_user, asset_factory, tenant_a):
    asset_factory(tenant_a, asset_code="Z-LAST", asset_name="Excluded", location="Mumbai")
    matching = asset_factory(tenant_a, asset_code="A-FIRST", asset_name="Press", location="Pune")
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.get(
        ASSETS_URL,
        {"search": "Pune", "category": "fixed", "is_active": "true", "ordering": "asset_code", "page_size": 1},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    assert [row["id"] for row in response_items(response)] == [str(matching.id)]


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ({"category": "unknown"}, "category"),
        ({"is_active": "sometimes"}, "is_active"),
        ({"purchase_date_after": "yesterday"}, "purchase_date_after"),
        ({"purchase_date_before": "31/12/2024"}, "purchase_date_before"),
    ],
)
def test_list_rejects_malformed_filters(api_client, tenant_a_user, query, field):
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.get(ASSETS_URL, query)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert field in response.data


def test_update_rejects_ownership_spoof_and_updates_through_domain(
    api_client, tenant_a_user, asset_factory, tenant_a, tenant_b
):
    asset = asset_factory(tenant_a)
    api_client.force_authenticate(user=tenant_a_user)

    spoof = api_client.patch(f"{ASSETS_URL}{asset.id}/", {"tenant_id": str(tenant_b)}, format="json", HTTP_IDEMPOTENCY_KEY="api-update-spoof")
    updated = api_client.patch(
        f"{ASSETS_URL}{asset.id}/",
        {"asset_name": "Updated press", "location": "Plant 2"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-update-success",
    )

    assert spoof.status_code == status.HTTP_400_BAD_REQUEST
    assert updated.status_code == status.HTTP_200_OK
    asset.refresh_from_db()
    assert asset.tenant_id == tenant_a
    assert asset.asset_name == "Updated press"


def test_delete_soft_deletes_and_preserves_depreciation_history(api_client, tenant_a_user, asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    entry = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.delete(f"{ASSETS_URL}{asset.id}/", HTTP_IDEMPOTENCY_KEY="api-archive-success")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    asset.refresh_from_db()
    assert asset.is_deleted and not asset.is_active
    assert DepreciationEntry.objects.filter(pk=entry.pk).exists()
    assert api_client.get(f"{ASSETS_URL}{asset.id}/").status_code == status.HTTP_404_NOT_FOUND


def test_activate_and_deactivate_are_explicit_authorized_commands(api_client, tenant_a_user, asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    api_client.force_authenticate(user=tenant_a_user)

    deactivated = api_client.post(f"{ASSETS_URL}{asset.id}/deactivate/", HTTP_IDEMPOTENCY_KEY="api-deactivate")
    activated = api_client.post(f"{ASSETS_URL}{asset.id}/activate/", HTTP_IDEMPOTENCY_KEY="api-activate")

    assert deactivated.status_code == status.HTTP_200_OK
    assert deactivated.data["is_active"] is False
    assert activated.status_code == status.HTTP_200_OK
    assert activated.data["is_active"] is True


def test_calculate_depreciation_endpoint_is_real_and_idempotent(api_client, tenant_a_user, asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    api_client.force_authenticate(user=tenant_a_user)
    url = f"{ASSETS_URL}{asset.id}/calculate-depreciation/"

    first = api_client.post(url, {"entry_date": "2024-02-01"}, format="json")
    repeated = api_client.post(url, {"entry_date": "2024-02-01"}, format="json")

    assert first.status_code == status.HTTP_201_CREATED
    assert repeated.status_code == status.HTTP_201_CREATED
    assert repeated.data["id"] == first.data["id"]
    assert repeated.data["asset_code"] == asset.asset_code
    assert DepreciationEntry.objects.filter(asset=asset).count() == 1


def test_calculate_depreciation_rejects_malformed_date(api_client, tenant_a_user, asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    api_client.force_authenticate(user=tenant_a_user)

    response = api_client.post(
        f"{ASSETS_URL}{asset.id}/calculate-depreciation/",
        {"entry_date": "not-a-date"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "entry_date" in response.data


def test_failure_envelope_carries_stable_code_and_correlation_id(api_client, tenant_a_user):
    api_client.force_authenticate(user=tenant_a_user)
    correlation_id = "12345678-1234-4234-9234-123456789abc"

    response = api_client.post(
        ASSETS_URL,
        valid_asset_payload(purchase_date="invalid"),
        format="json",
        HTTP_X_CORRELATION_ID=correlation_id,
        HTTP_IDEMPOTENCY_KEY="api-invalid-correlation",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error_code"]
    assert response.data["correlation_id"] == correlation_id


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_depreciation_collection_is_read_only(api_client, tenant_a_user, method):
    api_client.force_authenticate(user=tenant_a_user)

    response = getattr(api_client, method)(DEPRECIATION_URL, {}, format="json")

    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_database_health_failure_is_503_and_sanitized(api_client, tenant_a_user):
    api_client.force_authenticate(user=tenant_a_user)
    secret = "postgresql://admin:top-secret@internal-db/assets"
    with patch("src.modules.asset_management.health.connection.cursor", side_effect=RuntimeError(secret)):
        response = api_client.get(HEALTH_URL, HTTP_X_CORRELATION_ID="corr-123")

    body = response.content.decode()
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["error_code"] == "DATABASE_UNAVAILABLE"
    assert secret not in body
    assert "top-secret" not in body


def test_database_health_requires_authentication(api_client):
    # Health is an authenticated, explicitly authorized module endpoint.
    response = api_client.get(HEALTH_URL)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_database_health_success_is_verified_for_authorized_user(api_client, tenant_a_user):
    api_client.force_authenticate(user=tenant_a_user)
    response = api_client.get(HEALTH_URL)

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "status": "healthy",
        "module": "asset_management",
        "database": "connected",
    }


def test_configuration_api_preview_update_history_export_import_and_rollback(api_client, tenant_a_user):
    api_client.force_authenticate(user=tenant_a_user)

    current = api_client.get(CONFIG_URL)
    document = dict(current.data["document"])
    document["asset_list_page_size"] = 31
    preview = api_client.post(f"{CONFIG_URL}preview/", {"document": document}, format="json")
    updated = api_client.patch(f"{CONFIG_URL}update/", {"document": document}, format="json", HTTP_X_CORRELATION_ID="corr-config-api")
    history = api_client.get(f"{CONFIG_URL}history/")
    exported = api_client.get(f"{CONFIG_URL}export/")
    imported_document = dict(DEFAULT_CONFIGURATION)
    imported_document["asset_list_page_size"] = 29
    imported = api_client.post(
        f"{CONFIG_URL}import/",
        {"configuration": {"schema_version": "1.0", "module": "asset_management", "document": imported_document}},
        format="json",
    )
    rolled_back = api_client.post(f"{CONFIG_URL}rollback/", {"version": 1}, format="json")

    assert current.status_code == status.HTTP_200_OK
    assert preview.status_code == status.HTTP_200_OK
    assert preview.data["changes"]["asset_list_page_size"]["to"] == 31
    assert updated.status_code == status.HTTP_200_OK
    assert updated.data["version"] == 2
    assert history.status_code == status.HTTP_200_OK
    assert exported.status_code == status.HTTP_200_OK
    assert exported.data["module"] == "asset_management"
    assert imported.status_code == status.HTTP_200_OK
    assert imported.data["document"]["asset_list_page_size"] == 29
    assert rolled_back.status_code == status.HTTP_200_OK
    assert rolled_back.data["document"]["asset_list_page_size"] == DEFAULT_CONFIGURATION["asset_list_page_size"]
