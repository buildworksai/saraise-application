"""Governed API v2 contract tests for financial fixed assets."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.async_jobs.models import AsyncJob
from src.core.testing.factories import TEST_PASSWORD
from src.modules.fixed_assets import serializers
from src.modules.fixed_assets.api import (
    AssetCategoryViewSet,
    AssetTransactionViewSet,
    DepreciationLineViewSet,
    DepreciationScheduleViewSet,
    FixedAssetDashboardViewSet,
    FixedAssetJobViewSet,
    FixedAssetViewSet,
)
from src.modules.fixed_assets.health import ModuleHealthReport
from src.modules.fixed_assets.models import AssetCategory, DepreciationLine, DepreciationSchedule, FixedAsset
from src.modules.fixed_assets.permissions import PERMISSIONS

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep real session/CSRF handling while replacing remote policy I/O."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, required_permission, kwargs
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="test policy allows declared fixed-asset permission",
            tenant_id=UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


def create_category(tenant_id: UUID, suffix: str, **overrides) -> AssetCategory:
    values = {
        "tenant_id": tenant_id,
        "code": f"CAT-{suffix}-{uuid4().hex[:6]}".upper(),
        "name": f"Category {suffix}",
        "default_depreciation_method": "straight_line",
        "default_useful_life_months": 60,
        "default_residual_value_percent": Decimal("0.00"),
    }
    values.update(overrides)
    return AssetCategory.objects.create(**values)


def create_asset(tenant_id: UUID, category: AssetCategory, suffix: str, **overrides) -> FixedAsset:
    values = {
        "tenant_id": tenant_id,
        "asset_code": f"FA-{suffix}-{uuid4().hex[:6]}".upper(),
        "asset_name": f"Asset {suffix}",
        "category": category,
        "purchase_date": date(2025, 1, 1),
        "purchase_cost": Decimal("1200.00"),
        "currency": "USD",
        "residual_value": Decimal("0.00"),
        "depreciation_method": "straight_line",
        "useful_life_months": 12,
        "net_book_value": Decimal("1200.00"),
        "created_by": "api-test",
        "updated_by": "api-test",
    }
    values.update(overrides)
    return FixedAsset.objects.create(**values)


def create_schedule(tenant_id: UUID, asset: FixedAsset, suffix: str, **overrides) -> DepreciationSchedule:
    values = {
        "tenant_id": tenant_id,
        "asset": asset,
        "schedule_number": f"SCH-{suffix}-{uuid4().hex[:6]}".upper(),
        "method": "straight_line",
        "frequency": "monthly",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 12, 31),
        "cost_basis": Decimal("1200.00"),
        "residual_value": Decimal("0.00"),
        "depreciable_amount": Decimal("1200.00"),
        "total_planned_depreciation": Decimal("1200.00"),
        "created_by": "api-test",
        "updated_by": "api-test",
    }
    values.update(overrides)
    return DepreciationSchedule.objects.create(**values)


def create_line(tenant_id: UUID, asset: FixedAsset, schedule: DepreciationSchedule, **overrides) -> DepreciationLine:
    values = {
        "tenant_id": tenant_id,
        "asset": asset,
        "schedule": schedule,
        "sequence": 1,
        "period_start": date(2025, 1, 1),
        "period_end": date(2025, 1, 31),
        "opening_net_book_value": Decimal("1200.00"),
        "depreciation_amount": Decimal("100.00"),
        "accumulated_depreciation": Decimal("100.00"),
        "closing_net_book_value": Decimal("1100.00"),
    }
    values.update(overrides)
    return DepreciationLine.objects.create(**values)


REQUIRED_SERIALIZERS = {
    "CategoryListSerializer",
    "CategoryDetailSerializer",
    "CategoryCreateSerializer",
    "CategoryUpdateSerializer",
    "AssetListSerializer",
    "AssetDetailSerializer",
    "AssetCreateSerializer",
    "AssetDraftUpdateSerializer",
    "CapitalizeCommandSerializer",
    "TransferCommandSerializer",
    "ImpairmentCommandSerializer",
    "DisposalCommandSerializer",
    "ScheduleListSerializer",
    "ScheduleDetailSerializer",
    "ScheduleCreateSerializer",
    "ScheduleUpdateSerializer",
    "ScheduleCalculateSerializer",
    "ScheduleTransitionSerializer",
    "DepreciationLineListSerializer",
    "DepreciationLineDetailSerializer",
    "LinePostingSerializer",
    "DuePostingSerializer",
    "TransactionListSerializer",
    "TransactionDetailSerializer",
    "DashboardSerializer",
    "HealthResponseSerializer",
}


def test_every_required_operation_serializer_exists() -> None:
    assert REQUIRED_SERIALIZERS.issubset(set(dir(serializers)))


def test_request_serializers_reject_tenant_spoof_state_and_excess_precision(tenant_b) -> None:
    category = serializers.CategoryCreateSerializer(
        data={
            "tenant_id": str(tenant_b.id),
            "status": "active",
            "code": "test",
            "name": "Test",
            "default_depreciation_method": "straight_line",
            "default_useful_life_months": 60,
            "default_residual_value_percent": "0.00",
        }
    )
    assert not category.is_valid()
    assert set(category.errors) == {"tenant_id", "status"}

    asset = serializers.AssetCreateSerializer(
        data={
            "asset_code": "fa-1",
            "asset_name": "Precision",
            "category_id": str(uuid4()),
            "purchase_date": "2025-01-01",
            "purchase_cost": "1.001",
            "currency": "usd",
        }
    )
    assert not asset.is_valid()
    assert "purchase_cost" in asset.errors


def test_normalization_occurs_before_service_invocation() -> None:
    serializer = serializers.AssetCreateSerializer(
        data={
            "asset_code": " fa-001 ",
            "asset_name": "Normalized",
            "category_id": str(uuid4()),
            "purchase_date": "2025-01-01",
            "purchase_cost": "100.00",
            "currency": "inr",
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["asset_code"] == "FA-001"
    assert serializer.validated_data["currency"] == "INR"


def test_unauthenticated_protected_routes_return_governed_401(api_client) -> None:
    for path in (
        "categories/",
        "assets/",
        "depreciation-schedules/",
        "depreciation-lines/",
        f"transactions/{uuid4()}/",
        f"jobs/{uuid4()}/",
        "dashboard/",
    ):
        response = api_client.get(f"/api/v2/fixed-assets/{path}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_session_authentication_enforces_csrf(tenant_a_user) -> None:
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(username=tenant_a_user.username, password=TEST_PASSWORD)
    response = client.post(
        "/api/v2/fixed-assets/categories/",
        {
            "code": "CSRF",
            "name": "CSRF",
            "default_depreciation_method": "straight_line",
            "default_useful_life_months": 60,
            "default_residual_value_percent": "0.00",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="csrf-test",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"


def test_every_router_action_declares_a_manifest_permission() -> None:
    viewsets = (
        AssetCategoryViewSet,
        FixedAssetViewSet,
        DepreciationScheduleViewSet,
        DepreciationLineViewSet,
        AssetTransactionViewSet,
        FixedAssetJobViewSet,
        FixedAssetDashboardViewSet,
    )
    for viewset in viewsets:
        assert viewset.action_permissions
        assert set(viewset.action_permissions.values()).issubset(set(PERMISSIONS))
        assert all(viewset.action_permissions.values())


@pytest.mark.parametrize(
    ("method", "path", "permission"),
    [
        ("get", "categories/", "fixed_asset.category:read"),
        ("post", "categories/", "fixed_asset.category:create"),
        ("patch", f"categories/{uuid4()}/", "fixed_asset.category:update"),
        ("delete", f"categories/{uuid4()}/", "fixed_asset.category:delete"),
        ("get", "assets/", "fixed_asset.asset:read"),
        ("post", "assets/", "fixed_asset.asset:create"),
        ("post", f"assets/{uuid4()}/capitalize/", "fixed_asset.asset:capitalize"),
        ("post", f"assets/{uuid4()}/transfer/", "fixed_asset.asset:transfer"),
        ("post", f"assets/{uuid4()}/impair/", "fixed_asset.asset:impair"),
        ("post", f"assets/{uuid4()}/dispose/", "fixed_asset.asset:dispose"),
        ("get", f"assets/{uuid4()}/transactions/", "fixed_asset.transaction:read"),
        ("get", "depreciation-schedules/", "fixed_asset.depreciation:read"),
        ("post", "depreciation-schedules/", "fixed_asset.depreciation:calculate"),
        ("post", f"depreciation-lines/{uuid4()}/post/", "fixed_asset.depreciation:post"),
        ("post", "depreciation-lines/post-due/", "fixed_asset.depreciation:post"),
        ("get", f"transactions/{uuid4()}/", "fixed_asset.transaction:read"),
        ("get", f"jobs/{uuid4()}/", "fixed_asset.depreciation:post"),
        ("get", "dashboard/", "fixed_asset.asset:read"),
    ],
)
def test_every_permission_branch_fails_closed(
    monkeypatch, authenticated_tenant_a_client, tenant_a, method, path, permission
) -> None:
    decisions: list[str] = []

    def deny(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, kwargs
        decisions.append(required_permission)
        return AccessDecision.deny(
            AccessReasonCode.POLICY_DENIED,
            "denied by test policy",
            tenant_id=UUID(str(tenant_id)),
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", deny)
    response = getattr(authenticated_tenant_a_client, method)(f"/api/v2/fixed-assets/{path}", {}, format="json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["error"]["code"] == "POLICY_DENIED"
    assert decisions == [permission]


def test_category_list_has_envelope_pagination_filter_search_order_and_correlation(
    authenticated_tenant_a_client, tenant_a
) -> None:
    for index in range(30):
        create_category(tenant_a.id, f"{index:03d}", is_active=index % 2 == 0)
    correlation = str(uuid4())
    response = authenticated_tenant_a_client.get(
        "/api/v2/fixed-assets/categories/"
        "?is_active=true&method=straight_line&search=Category"
        "&ordering=-name&page_size=500",
        HTTP_X_CORRELATION_ID=correlation,
    )
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["correlation_id"] == correlation
    assert payload["meta"]["pagination"]["page_size"] == 100
    assert payload["meta"]["pagination"]["count"] == 15
    assert [row["name"] for row in payload["data"]] == sorted((row["name"] for row in payload["data"]), reverse=True)


def test_asset_filters_search_ordering_and_detail_reconciliation(authenticated_tenant_a_client, tenant_a) -> None:
    category = create_category(tenant_a.id, "assets")
    target = create_asset(tenant_a.id, category, "target", location="Pune", cost_center="CC-1")
    create_asset(tenant_a.id, category, "other", currency="EUR")
    response = authenticated_tenant_a_client.get(
        f"/api/v2/fixed-assets/assets/?category_id={category.id}"
        "&currency=USD&location=Pune&search=target&ordering=-net_book_value"
    )
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["data"]] == [str(target.id)]

    detail = authenticated_tenant_a_client.get(f"/api/v2/fixed-assets/assets/{target.id}/")
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["allowed_commands"] == ["update", "delete", "capitalize"]
    assert data["balance_reconciliation"]["reconciled"] is True
    assert data["as_of"]


@pytest.mark.parametrize(
    "query",
    ("?ordering=tenant_id", "?is_active=maybe"),
)
def test_invalid_collection_parameters_use_validation_envelope(authenticated_tenant_a_client, query) -> None:
    path = "assets" if "ordering" in query else "categories"
    response = authenticated_tenant_a_client.get(f"/api/v2/fixed-assets/{path}/{query}")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_asset_create_requires_idempotency_and_delegates_to_service(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    category = create_category(tenant_a.id, "create")
    payload = {
        "asset_code": "FA-CREATE",
        "asset_name": "Created",
        "category_id": str(category.id),
        "purchase_date": "2025-01-01",
        "purchase_cost": "1200.00",
        "currency": "usd",
    }
    missing = authenticated_tenant_a_client.post("/api/v2/fixed-assets/assets/", payload, format="json")
    assert missing.status_code == 400

    asset = create_asset(tenant_a.id, category, "returned")
    calls: list[tuple] = []

    def create(*args):
        calls.append(args)
        return asset

    monkeypatch.setattr("src.modules.fixed_assets.api.FixedAssetService.create_asset", create)
    response = authenticated_tenant_a_client.post(
        "/api/v2/fixed-assets/assets/", payload, format="json", HTTP_IDEMPOTENCY_KEY="asset-create-1"
    )
    assert response.status_code == 201
    assert calls and calls[0][0] == tenant_a.id
    assert calls[0][2]["asset_code"] == "FA-CREATE"
    assert calls[0][2]["currency"] == "USD"


def test_line_post_returns_sanitized_durable_job(
    monkeypatch, authenticated_tenant_a_client, tenant_a, tenant_a_user
) -> None:
    category = create_category(tenant_a.id, "job")
    asset = create_asset(tenant_a.id, category, "job")
    schedule = create_schedule(tenant_a.id, asset, "job")
    line = create_line(tenant_a.id, asset, schedule)
    job = AsyncJob.objects.create(
        tenant_id=tenant_a.id,
        actor_id=str(tenant_a_user.id),
        command="fixed_assets.post_line",
        idempotency_key="line-job",
        payload={"line_id": str(line.id)},
        correlation_id="correlation-job",
    )
    monkeypatch.setattr(
        "src.modules.fixed_assets.api.DepreciationService.enqueue_line_posting",
        lambda *args: job,
    )
    response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/depreciation-lines/{line.id}/post/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="line-job",
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["data"]["id"] == str(job.id)
    assert "error_message" not in response.json()["data"]


@pytest.mark.parametrize("health_status,http_status", (("healthy", 200), ("degraded", 200), ("unhealthy", 503)))
def test_health_states_are_sanitized_and_unauthenticated(monkeypatch, api_client, health_status, http_status) -> None:
    report = ModuleHealthReport(
        health_status,
        {
            "status": health_status,
            "checks": [
                {
                    "name": "accounting_adapter",
                    "status": "degraded" if health_status == "degraded" else health_status,
                    "code": "CAPABILITY_UNAVAILABLE" if health_status == "degraded" else "READY",
                }
            ],
        },
    )
    monkeypatch.setattr("src.modules.fixed_assets.api.get_module_health", lambda: report)
    response = api_client.get("/api/v2/fixed-assets/health/")
    assert response.status_code == http_status
    body = response.json()
    assert "exception" not in str(body).lower()
    if http_status == 200:
        assert body["data"]["status"] == health_status
    else:
        assert body["error"]["code"] == "FIXED_ASSETS_UNHEALTHY"
