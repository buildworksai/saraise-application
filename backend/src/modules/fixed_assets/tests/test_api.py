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
from src.modules.fixed_assets.models import (
    AssetCategory,
    AssetTransaction,
    DepreciationLine,
    DepreciationSchedule,
    FixedAsset,
)
from src.modules.fixed_assets.permissions import PERMISSIONS
from src.modules.fixed_assets.services import FixedAssetServiceError, StaleVersionError

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


@pytest.mark.parametrize(
    "query",
    (
        "?currency=US1",
        "?capitalized_from=not-a-date",
        "?capitalized_to=2026-02-31",
        "?status=retired",
        "?method=accelerated",
        "?page_size=0",
    ),
)
def test_asset_collection_rejects_unsafe_filter_values(authenticated_tenant_a_client, query) -> None:
    response = authenticated_tenant_a_client.get(f"/api/v2/fixed-assets/assets/{query}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
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


def test_category_update_and_delete_are_tenant_scoped_service_delegations(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    category = create_category(tenant_a.id, "delegation")
    update_calls: list[tuple] = []
    delete_calls: list[tuple] = []

    def update_category(*args):
        update_calls.append(args)
        category.name = args[3]["name"]
        return category

    def deactivate_category(*args):
        delete_calls.append(args)
        category.is_active = False
        return category

    monkeypatch.setattr("src.modules.fixed_assets.api.AssetCategoryService.update_category", update_category)
    monkeypatch.setattr("src.modules.fixed_assets.api.AssetCategoryService.deactivate_category", deactivate_category)

    patch_response = authenticated_tenant_a_client.patch(
        f"/api/v2/fixed-assets/categories/{category.id}/",
        {"name": "Delegated", "expected_version": category.version},
        format="json",
    )
    delete_response = authenticated_tenant_a_client.delete(f"/api/v2/fixed-assets/categories/{category.id}/")

    assert patch_response.status_code == status.HTTP_200_OK
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert update_calls[0][0] == tenant_a.id
    assert update_calls[0][1] == category.id
    assert delete_calls[0][0] == tenant_a.id
    assert delete_calls[0][1] == category.id


def test_asset_lifecycle_preview_validates_payload_and_does_not_require_idempotency(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    category = create_category(tenant_a.id, "preview")
    asset = create_asset(tenant_a.id, category, "preview")
    calls: list[tuple] = []

    def preview_capitalization(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "command": "capitalize",
            "asset_version": asset.version,
            "as_of": kwargs["effective_date"],
            "opening_net_book_value": Decimal("1200.00"),
            "closing_net_book_value": Decimal("1200.00"),
            "currency": "USD",
            "warnings": [],
            "blockers": [],
            "journal_effect": {"status": "ready", "entries": []},
            "schedule_effect": {"status": "created", "description": "A draft depreciation schedule may be created."},
        }

    monkeypatch.setattr("src.modules.fixed_assets.api.FixedAssetService.preview_capitalization", preview_capitalization)

    response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/assets/{asset.id}/preview-capitalize/",
        {
            "effective_date": "2025-01-01",
            "depreciation_start_date": "2025-01-01",
            "expected_version": asset.version,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert calls[0][0] == (tenant_a.id, asset.id)
    assert response.json()["data"]["command"] == "capitalize"


def test_schedule_filters_and_transitions_delegate_with_transition_keys(
    authenticated_tenant_a_client, tenant_a
) -> None:
    category = create_category(tenant_a.id, "schedule-filter")
    asset = create_asset(tenant_a.id, category, "schedule-filter")
    target = create_schedule(tenant_a.id, asset, "active", status="active")
    create_schedule(tenant_a.id, asset, "draft", status="draft", book_code="SECONDARY")

    list_response = authenticated_tenant_a_client.get(
        f"/api/v2/fixed-assets/depreciation-schedules/?asset_id={asset.id}&status=active&method=straight_line"
    )
    transition_response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/depreciation-schedules/{target.id}/supersede/",
        {"transition_key": "supersede-schedule", "reason": "replacement"},
        format="json",
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in list_response.json()["data"]] == [str(target.id)]
    assert transition_response.status_code == status.HTTP_200_OK
    target.refresh_from_db()
    assert target.status == "superseded"
    assert transition_response.json()["data"]["denial_reasons"]["supersede"] == "SCHEDULE_STATE_SUPERSEDED"


def test_depreciation_line_filters_and_due_posting_enqueue_durable_job(
    monkeypatch, authenticated_tenant_a_client, tenant_a, tenant_a_user
) -> None:
    category = create_category(tenant_a.id, "line-filter")
    asset = create_asset(tenant_a.id, category, "line-filter")
    schedule = create_schedule(tenant_a.id, asset, "line-filter")
    target = create_line(tenant_a.id, asset, schedule, period_end=date(2025, 2, 28), sequence=2)
    create_line(tenant_a.id, asset, schedule, period_end=date(2025, 3, 31), sequence=3, status="posted")
    job = AsyncJob.objects.create(
        tenant_id=tenant_a.id,
        actor_id=str(tenant_a_user.id),
        command="fixed_assets.post_due",
        idempotency_key="post-due",
        payload={"through_date": "2025-02-28"},
        correlation_id="post-due-correlation",
    )
    calls: list[tuple] = []

    def enqueue_due_posting(*args):
        calls.append(args)
        return job

    list_response = authenticated_tenant_a_client.get(
        f"/api/v2/fixed-assets/depreciation-lines/?asset_id={asset.id}&schedule_id={schedule.id}"
        "&status=planned&period_from=2025-02-01&period_to=2025-02-28"
    )
    monkeypatch.setattr("src.modules.fixed_assets.api.DepreciationService.enqueue_due_posting", enqueue_due_posting)
    post_response = authenticated_tenant_a_client.post(
        "/api/v2/fixed-assets/depreciation-lines/post-due/",
        {"through_date": "2025-02-28"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="post-due",
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert [row["id"] for row in list_response.json()["data"]] == [str(target.id)]
    assert post_response.status_code == status.HTTP_202_ACCEPTED
    assert calls[0][0] == tenant_a.id
    assert calls[0][1] == date(2025, 2, 28)
    assert calls[0][3] == "post-due"


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


def test_dashboard_aggregates_only_current_tenant_values(authenticated_tenant_a_client, tenant_a) -> None:
    category = create_category(tenant_a.id, "dashboard")
    active_asset = create_asset(
        tenant_a.id,
        category,
        "dashboard-a",
        status="active",
        purchase_cost=Decimal("900.00"),
        net_book_value=Decimal("900.00"),
    )
    disposed_asset = create_asset(
        tenant_a.id,
        category,
        "dashboard-b",
        status="disposed",
        purchase_cost=Decimal("100.00"),
        net_book_value=Decimal("100.00"),
    )
    schedule = create_schedule(tenant_a.id, active_asset, "dashboard")
    create_line(tenant_a.id, active_asset, schedule, status="planned")
    AssetTransaction.objects.create(
        tenant_id=tenant_a.id,
        asset=active_asset,
        transaction_type="depreciation",
        effective_date=date.today(),
        amount=Decimal("100.00"),
        currency="USD",
        opening_net_book_value=Decimal("1000.00"),
        closing_net_book_value=Decimal("900.00"),
        actor_id="dashboard-test",
        correlation_id="dashboard-correlation",
        source_type="depreciation_line",
        source_id=uuid4(),
        idempotency_key="dashboard-depreciation",
        request_fingerprint="a" * 64,
    )
    AssetTransaction.objects.create(
        tenant_id=tenant_a.id,
        asset=disposed_asset,
        transaction_type="disposal",
        effective_date=date.today(),
        amount=Decimal("100.00"),
        currency="USD",
        opening_net_book_value=Decimal("100.00"),
        closing_net_book_value=Decimal("0.00"),
        actor_id="dashboard-test",
        correlation_id="dashboard-correlation",
        source_type="asset_disposal",
        source_id=uuid4(),
        idempotency_key="dashboard-disposal",
        request_fingerprint="b" * 64,
    )

    response = authenticated_tenant_a_client.get("/api/v2/fixed-assets/dashboard/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["asset_counts"]["active"] == 1
    assert data["asset_counts"]["disposed"] == 1
    assert data["pending_postings"] == 1
    assert data["book_value_by_currency"] == [{"currency": "USD", "amount": "900.00"}]


def test_service_errors_return_stable_operation_failure_envelope(
    monkeypatch, authenticated_tenant_a_client, tenant_a
) -> None:
    category = create_category(tenant_a.id, "error")
    asset = create_asset(tenant_a.id, category, "error")

    def reject(*_args, **_kwargs):
        raise FixedAssetServiceError("no transfer", code="TRANSFER_NOT_ALLOWED")

    monkeypatch.setattr("src.modules.fixed_assets.api.FixedAssetService.transfer", reject)

    response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/assets/{asset.id}/transfer/",
        {"effective_date": "2025-01-01", "to_location": "Mumbai"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="transfer-error",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["error"]["code"] == "TRANSFER_NOT_ALLOWED"


def test_stale_version_error_returns_reload_contract(monkeypatch, authenticated_tenant_a_client, tenant_a) -> None:
    category = create_category(tenant_a.id, "stale")
    asset = create_asset(tenant_a.id, category, "stale")

    def reject(*_args, **_kwargs):
        raise StaleVersionError(expected=asset.version, actual=asset.version + 1)

    monkeypatch.setattr("src.modules.fixed_assets.api.FixedAssetService.update_draft", reject)

    response = authenticated_tenant_a_client.patch(
        f"/api/v2/fixed-assets/assets/{asset.id}/",
        {"asset_name": "Stale update", "expected_version": asset.version},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    error = response.json()["error"]
    assert error["code"] == "STALE_VERSION"
    assert error["detail"] == {"expected_version": asset.version, "actual_version": asset.version + 1}


def test_asset_detail_prefetches_only_active_schedules(authenticated_tenant_a_client, tenant_a) -> None:
    category = create_category(tenant_a.id, "prefetch")
    asset = create_asset(tenant_a.id, category, "prefetch")
    active = create_schedule(tenant_a.id, asset, "prefetch-active", status="active")
    create_schedule(tenant_a.id, asset, "prefetch-draft", status="draft", revision=2)

    response = authenticated_tenant_a_client.get(f"/api/v2/fixed-assets/assets/{asset.id}/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["active_schedule"]["id"] == str(active.id)


def test_legacy_v1_adapter_creates_lists_updates_and_deletes_draft_assets(authenticated_tenant_a_client) -> None:
    create_response = authenticated_tenant_a_client.post(
        "/api/v1/fixed-assets/assets/",
        {
            "asset_code": "legacy-1",
            "asset_name": "Legacy laptop",
            "asset_category": "it-equipment",
            "purchase_date": "2025-01-01",
            "purchase_cost": "1500.00",
            "useful_life_years": 3,
            "depreciation_method": "straight_line",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="legacy-create-1",
    )
    assert create_response.status_code == status.HTTP_201_CREATED, create_response.content
    asset_id = create_response.json()["id"]
    assert create_response.json()["asset_code"] == "LEGACY-1"
    assert create_response.json()["asset_category"] == "IT-EQUIPMENT"
    assert create_response.json()["useful_life_years"] == 3
    assert create_response.json()["is_active"] is True

    listed = authenticated_tenant_a_client.get("/api/v1/fixed-assets/assets/")
    detail = authenticated_tenant_a_client.get(f"/api/v1/fixed-assets/assets/{asset_id}/")
    patched = authenticated_tenant_a_client.patch(
        f"/api/v1/fixed-assets/assets/{asset_id}/",
        {"asset_name": "Legacy laptop updated", "useful_life_years": 4},
        format="json",
    )
    deleted = authenticated_tenant_a_client.delete(f"/api/v1/fixed-assets/assets/{asset_id}/")
    missing = authenticated_tenant_a_client.get(f"/api/v1/fixed-assets/assets/{asset_id}/")

    assert listed.status_code == status.HTTP_200_OK
    assert [row["id"] for row in listed.json()] == [asset_id]
    assert detail.status_code == status.HTTP_200_OK
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["asset_name"] == "Legacy laptop updated"
    assert patched.json()["useful_life_years"] == 4
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert missing.status_code == status.HTTP_404_NOT_FOUND
