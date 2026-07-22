"""Black-box isolation for every fixed-assets entity and command boundary."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.db import connection
from rest_framework import status

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.async_jobs.models import AsyncJob
from src.core.testing.tenant_contract import TenantIsolationContract
from src.core.tenancy import tenant_context
from src.modules.fixed_assets.models import (
    AssetCategory,
    AssetTransaction,
    DepreciationLine,
    DepreciationSchedule,
    FixedAsset,
)

pytest_plugins = ["src.core.testing"]
pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def allow_declared_access(monkeypatch: pytest.MonkeyPatch) -> None:
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


def category(tenant_id, suffix: str) -> AssetCategory:
    # Keep generated fixture identifiers within the governed 30-character code
    # limit even when a parametrized action name is used as the suffix.
    code_suffix = "".join(character for character in suffix if character.isalnum())[:12]
    return AssetCategory.objects.create(
        tenant_id=tenant_id,
        code=f"ISO-CAT-{code_suffix}-{uuid4().hex[:6]}".upper(),
        name=f"Isolation Category {suffix}",
        default_depreciation_method="straight_line",
        default_useful_life_months=60,
        default_residual_value_percent=Decimal("0.00"),
    )


def asset(tenant_id, category_value: AssetCategory, suffix: str, **overrides) -> FixedAsset:
    values = {
        "tenant_id": tenant_id,
        "asset_code": f"ISO-FA-{suffix}-{uuid4().hex[:6]}".upper(),
        "asset_name": f"Isolation Asset {suffix}",
        "category": category_value,
        "purchase_date": date(2025, 1, 1),
        "purchase_cost": Decimal("1200.00"),
        "currency": "USD",
        "residual_value": Decimal("0.00"),
        "depreciation_method": "straight_line",
        "useful_life_months": 12,
        "net_book_value": Decimal("1200.00"),
        "created_by": "isolation-test",
        "updated_by": "isolation-test",
    }
    values.update(overrides)
    return FixedAsset.objects.create(**values)


def schedule(tenant_id, asset_value: FixedAsset, suffix: str, **overrides) -> DepreciationSchedule:
    values = {
        "tenant_id": tenant_id,
        "asset": asset_value,
        "schedule_number": f"ISO-SCH-{suffix}-{uuid4().hex[:6]}".upper(),
        "method": "straight_line",
        "frequency": "monthly",
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 12, 31),
        "cost_basis": Decimal("1200.00"),
        "residual_value": Decimal("0.00"),
        "depreciable_amount": Decimal("1200.00"),
        "total_planned_depreciation": Decimal("1200.00"),
        "created_by": "isolation-test",
        "updated_by": "isolation-test",
    }
    values.update(overrides)
    return DepreciationSchedule.objects.create(**values)


def line(tenant_id, asset_value: FixedAsset, schedule_value: DepreciationSchedule, suffix: int = 1) -> DepreciationLine:
    return DepreciationLine.objects.create(
        tenant_id=tenant_id,
        asset=asset_value,
        schedule=schedule_value,
        sequence=suffix,
        period_start=date(2025, suffix, 1),
        period_end=date(2025, suffix, 28),
        opening_net_book_value=Decimal("1200.00"),
        depreciation_amount=Decimal("100.00"),
        accumulated_depreciation=Decimal("100.00"),
        closing_net_book_value=Decimal("1100.00"),
    )


class V2IsolationContract(TenantIsolationContract):
    read_denial_statuses = frozenset({status.HTTP_404_NOT_FOUND})

    def get_list_items(self, response):
        return response.json()["data"]


class TestCategoryIsolation(V2IsolationContract):
    model = AssetCategory
    list_url = "/api/v2/fixed-assets/categories/"
    detail_url_template = "/api/v2/fixed-assets/categories/{pk}/"
    create_payload = {
        "code": "SPOOF-CATEGORY",
        "name": "Spoof category",
        "default_depreciation_method": "straight_line",
        "default_useful_life_months": 60,
        "default_residual_value_percent": "0.00",
    }
    update_payload = {"name": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        self.tenant_a_row = category(tenant_a.id, "a")
        self.tenant_b_row = category(tenant_b.id, "b")


class TestFixedAssetIsolation(V2IsolationContract):
    model = FixedAsset
    list_url = "/api/v2/fixed-assets/assets/"
    detail_url_template = "/api/v2/fixed-assets/assets/{pk}/"
    update_payload = {"asset_name": "Cross-tenant overwrite", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        category_a = category(tenant_a.id, "asset-a")
        category_b = category(tenant_b.id, "asset-b")
        self.tenant_a_row = asset(tenant_a.id, category_a, "a")
        self.tenant_b_row = asset(tenant_b.id, category_b, "b")
        self.create_payload = {
            "asset_code": "SPOOF-ASSET",
            "asset_name": "Spoof asset",
            "category_id": str(category_a.id),
            "purchase_date": "2025-01-01",
            "purchase_cost": "1200.00",
            "currency": "USD",
        }


class TestScheduleIsolation(V2IsolationContract):
    model = DepreciationSchedule
    list_url = "/api/v2/fixed-assets/depreciation-schedules/"
    detail_url_template = "/api/v2/fixed-assets/depreciation-schedules/{pk}/"
    update_payload = {"start_date": "2025-02-01", "expected_version": 1}

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        asset_a = asset(tenant_a.id, category(tenant_a.id, "schedule-a"), "schedule-a")
        asset_b = asset(tenant_b.id, category(tenant_b.id, "schedule-b"), "schedule-b")
        self.tenant_a_row = schedule(tenant_a.id, asset_a, "a")
        self.tenant_b_row = schedule(tenant_b.id, asset_b, "b")
        self.create_payload = {"asset_id": str(asset_a.id)}


class TestDepreciationLineIsolation(V2IsolationContract):
    model = DepreciationLine
    list_url = "/api/v2/fixed-assets/depreciation-lines/"
    detail_url_template = "/api/v2/fixed-assets/depreciation-lines/{pk}/"
    create_payload = {"sequence": 99}
    update_payload = {"depreciation_amount": "0.00"}
    # Generic line mutation is intentionally unsupported. A 405 is a complete
    # rejection; the fail-closed action map may deny it before routing with
    # 403, while exposed detail and line commands are asserted as strict 404s.
    read_denial_statuses = frozenset(
        {status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED}
    )
    write_denial_statuses = frozenset(
        {
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        }
    )

    @pytest.fixture(autouse=True)
    def isolation_context(self, authenticated_tenant_a_client, tenant_a, tenant_b):
        self.client = authenticated_tenant_a_client
        asset_a = asset(tenant_a.id, category(tenant_a.id, "line-a"), "line-a")
        asset_b = asset(tenant_b.id, category(tenant_b.id, "line-b"), "line-b")
        schedule_a = schedule(tenant_a.id, asset_a, "line-a")
        schedule_b = schedule(tenant_b.id, asset_b, "line-b")
        self.tenant_a_row = line(tenant_a.id, asset_a, schedule_a)
        self.tenant_b_row = line(tenant_b.id, asset_b, schedule_b)


def test_spoofed_create_with_idempotency_header_is_rejected_before_service(
    authenticated_tenant_a_client, tenant_a, tenant_b
) -> None:
    before = AssetCategory.objects.filter(tenant_id=tenant_b.id).count()
    response = authenticated_tenant_a_client.post(
        "/api/v2/fixed-assets/categories/",
        {
            "tenant_id": str(tenant_b.id),
            "code": "EXPLICIT-SPOOF",
            "name": "Explicit spoof",
            "default_depreciation_method": "straight_line",
            "default_useful_life_months": 60,
            "default_residual_value_percent": "0.00",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="explicit-spoof",
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert AssetCategory.objects.filter(tenant_id=tenant_b.id).count() == before
    assert not AssetCategory.objects.filter(tenant_id=tenant_a.id, code="EXPLICIT-SPOOF").exists()


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        ("capitalize/", {"effective_date": "2025-02-01", "expected_version": 1}),
        ("transfer/", {"effective_date": "2025-02-01", "to_location": "Mumbai"}),
        (
            "impair/",
            {"effective_date": "2025-02-01", "recoverable_amount": "900.00", "reason": "Damage"},
        ),
        ("dispose/", {"effective_date": "2025-02-01", "proceeds": "800.00", "reason": "Sale"}),
        ("preview-capitalize/", {"effective_date": "2025-02-01", "expected_version": 1}),
        ("preview-transfer/", {"effective_date": "2025-02-01", "to_location": "Mumbai"}),
        (
            "preview-impair/",
            {"effective_date": "2025-02-01", "recoverable_amount": "900.00", "reason": "Damage"},
        ),
        ("preview-dispose/", {"effective_date": "2025-02-01", "proceeds": "800.00", "reason": "Sale"}),
    ],
)
def test_asset_commands_return_strict_404_for_cross_tenant_target(
    authenticated_tenant_a_client, tenant_a, tenant_b, suffix, payload
) -> None:
    target = asset(tenant_b.id, category(tenant_b.id, "command"), "command")
    before = FixedAsset.objects.filter(pk=target.pk).values().get()
    response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/assets/{target.id}/{suffix}",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=f"cross-{uuid4()}",
    )
    assert response.status_code == 404
    assert FixedAsset.objects.filter(pk=target.pk).values().get() == before


@pytest.mark.parametrize(
    ("suffix", "payload"),
    [
        ("calculate/", {"transition_key": "cross-calculate", "units_by_period": {}}),
        ("activate/", {"transition_key": "cross-activate"}),
        ("supersede/", {"transition_key": "cross-supersede", "reason": "test"}),
    ],
)
def test_schedule_commands_return_strict_404_for_cross_tenant_target(
    authenticated_tenant_a_client, tenant_b, suffix, payload
) -> None:
    asset_b = asset(tenant_b.id, category(tenant_b.id, "schcmd"), "schcmd")
    target = schedule(tenant_b.id, asset_b, "schcmd")
    before = DepreciationSchedule.objects.filter(pk=target.pk).values().get()
    response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/depreciation-schedules/{target.id}/{suffix}", payload, format="json"
    )
    assert response.status_code == 404
    assert DepreciationSchedule.objects.filter(pk=target.pk).values().get() == before


def test_line_post_returns_strict_404_for_cross_tenant_target(authenticated_tenant_a_client, tenant_b) -> None:
    asset_b = asset(tenant_b.id, category(tenant_b.id, "post"), "post")
    schedule_b = schedule(tenant_b.id, asset_b, "post")
    target = line(tenant_b.id, asset_b, schedule_b)
    before = DepreciationLine.objects.filter(pk=target.pk).values().get()
    response = authenticated_tenant_a_client.post(
        f"/api/v2/fixed-assets/depreciation-lines/{target.id}/post/",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY="cross-post",
    )
    assert response.status_code == 404
    assert DepreciationLine.objects.filter(pk=target.pk).values().get() == before


def test_post_due_is_bound_to_authenticated_tenant(
    monkeypatch, authenticated_tenant_a_client, tenant_a, tenant_b, tenant_a_user
) -> None:
    asset_b = asset(tenant_b.id, category(tenant_b.id, "post-due"), "post-due")
    schedule_b = schedule(tenant_b.id, asset_b, "post-due")
    target = line(tenant_b.id, asset_b, schedule_b)
    before = DepreciationLine.objects.filter(pk=target.pk).values().get()
    job = AsyncJob.objects.create(
        tenant_id=tenant_a.id,
        actor_id=str(tenant_a_user.id),
        command="fixed_assets.post_due_lines",
        idempotency_key="tenant-a-post-due",
        payload={"through_date": "2025-12-31"},
        correlation_id=f"correlation-{uuid4()}",
    )
    calls: list[tuple] = []

    def enqueue(*args):
        calls.append(args)
        return job

    monkeypatch.setattr(
        "src.modules.fixed_assets.api.DepreciationService.enqueue_due_posting",
        enqueue,
    )
    response = authenticated_tenant_a_client.post(
        "/api/v2/fixed-assets/depreciation-lines/post-due/",
        {"through_date": "2025-12-31"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="tenant-a-post-due",
    )
    assert response.status_code == 202
    assert calls and calls[0][0] == tenant_a.id
    assert DepreciationLine.objects.filter(pk=target.pk).values().get() == before


def test_transactions_and_jobs_do_not_leak(authenticated_tenant_a_client, tenant_b, tenant_b_user) -> None:
    asset_b = asset(tenant_b.id, category(tenant_b.id, "history"), "history")
    transaction = AssetTransaction.objects.create(
        tenant_id=tenant_b.id,
        asset=asset_b,
        transaction_type="transfer",
        effective_date=date(2025, 2, 1),
        amount=Decimal("0.00"),
        currency="USD",
        opening_net_book_value=Decimal("1200.00"),
        closing_net_book_value=Decimal("1200.00"),
        source_type="fixed_asset",
        idempotency_key=f"transaction-{uuid4()}",
        request_fingerprint=uuid4().hex,
        actor_id=str(tenant_b_user.id),
        correlation_id=f"correlation-{uuid4()}",
        metadata={"source": "isolation-test"},
    )
    job = AsyncJob.objects.create(
        tenant_id=tenant_b.id,
        actor_id=str(tenant_b_user.id),
        command="fixed_assets.post_line",
        idempotency_key=f"job-{uuid4()}",
        payload={},
        correlation_id=f"correlation-{uuid4()}",
    )
    for url in (
        f"/api/v2/fixed-assets/assets/{asset_b.id}/transactions/",
        f"/api/v2/fixed-assets/transactions/{transaction.id}/",
        f"/api/v2/fixed-assets/jobs/{job.id}/",
    ):
        response = authenticated_tenant_a_client.get(url)
        assert response.status_code == 404


@pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL RLS evidence requires PostgreSQL")
def test_rls_blocks_unscoped_orm_and_direct_sql_under_tenant_context(tenant_a, tenant_b) -> None:
    row_a = category(tenant_a.id, "rls-a")
    row_b = category(tenant_b.id, "rls-b")
    with tenant_context(tenant_a.id):
        visible = set(AssetCategory.objects.values_list("id", flat=True))
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM fixed_asset_categories")
            direct = {row[0] for row in cursor.fetchall()}
    assert row_a.id in visible and row_b.id not in visible
    assert row_a.id in direct and row_b.id not in direct
