"""Lifecycle, calculation, posting, and idempotency service coverage."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from src.core.async_jobs.models import JobStatus
from src.core.async_jobs.services import JobExecutionError, execute
from src.core.state_machine import IdempotencyConflictError
from src.modules.fixed_assets.integrations import (
    AccountingPostingResult,
    CapabilityUnavailable,
    DefaultAccountingAdapter,
    extension_registry,
)
from src.modules.fixed_assets.models import AssetCategory, AssetTransaction, DepreciationLine
from src.modules.fixed_assets.services import (
    AssetCategoryService,
    DepreciationService,
    FixedAssetService,
    FixedAssetServiceError,
    StaleVersionError,
)


ACCOUNT_FIELDS = (
    "asset_account_id",
    "accumulated_depreciation_account_id",
    "depreciation_expense_account_id",
    "impairment_loss_account_id",
    "disposal_gain_account_id",
    "disposal_loss_account_id",
)


class FakeAccounting:
    schema_version = "1.0"

    def __init__(self, *, failure: bool = False) -> None:
        self.failure = failure
        self.requests = []

    def validate_accounts(self, tenant_id: uuid.UUID, account_ids: tuple[uuid.UUID, ...]) -> None:
        if self.failure:
            raise CapabilityUnavailable("accounting unavailable")
        if len(account_ids) != 6:
            raise AssertionError("six mapped accounts required")

    def post_journal(self, request: object) -> AccountingPostingResult:
        if self.failure:
            raise CapabilityUnavailable("accounting unavailable")
        self.requests.append(request)
        return AccountingPostingResult("1.0", uuid.uuid4(), "2026-07-22T00:00:00Z")


class FixedAssetServiceTests(TestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.actor = "service-tester"
        self.accounting = FakeAccounting()
        extension_registry.set_accounting_port(self.accounting)
        self.category_data = {
            "code": "it",
            "name": "Information technology",
            "default_depreciation_method": "straight_line",
            "default_useful_life_months": 12,
            **{field: uuid.uuid4() for field in ACCOUNT_FIELDS},
        }

    def tearDown(self) -> None:
        extension_registry.set_accounting_port(DefaultAccountingAdapter())

    def create_category(self, key: str = "category-1"):
        return AssetCategoryService.create_category(
            self.tenant, self.actor, self.category_data, key
        )

    def create_asset(self, *, key: str = "asset-1", cost: str = "1200.00"):
        category = AssetCategory.objects.filter(tenant_id=self.tenant, code="IT").first()
        if category is None:
            category = self.create_category(f"{key}:category")
        return FixedAssetService.create_asset(
            self.tenant,
            self.actor,
            {
                "asset_code": key,
                "asset_name": "Test asset",
                "category_id": category.id,
                "purchase_date": date(2026, 1, 1),
                "purchase_cost": Decimal(cost),
                "currency": "usd",
            },
            key,
        )

    def capitalize(self, asset, key: str = "capitalize-1"):
        return FixedAssetService.capitalize(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 1, 1),
            key,
            expected_version=asset.version,
        )

    def test_create_idempotency_and_payload_conflict(self) -> None:
        category = self.create_category()
        duplicate = self.create_category()
        self.assertEqual(duplicate.id, category.id)
        changed = dict(self.category_data, name="Different")
        with self.assertRaises(IdempotencyConflictError):
            AssetCategoryService.create_category(
                self.tenant, self.actor, changed, "category-1"
            )

        asset = self.create_asset()
        duplicate_asset = FixedAssetService.create_asset(
            self.tenant,
            self.actor,
            {
                "asset_code": "asset-1",
                "asset_name": "Test asset",
                "category_id": asset.category_id,
                "purchase_date": date(2026, 1, 1),
                "purchase_cost": Decimal("1200.00"),
                "currency": "usd",
            },
            "asset-1",
        )
        self.assertEqual(duplicate_asset.id, asset.id)

    def test_draft_version_and_cross_tenant_guards(self) -> None:
        asset = self.create_asset()
        with self.assertRaises(StaleVersionError):
            FixedAssetService.update_draft(
                self.tenant, asset.id, self.actor, {"asset_name": "Changed"}, 999
            )
        with self.assertRaises(ObjectDoesNotExist):
            FixedAssetService.update_draft(
                uuid.uuid4(), asset.id, self.actor, {"asset_name": "Changed"}, 1
            )

    def test_capitalize_transfer_impair_and_dispose_are_idempotent(self) -> None:
        asset = self.capitalize(self.create_asset())
        self.assertEqual(asset.status, "active")
        self.assertEqual(asset.depreciation_start_date, date(2026, 1, 1))

        asset = FixedAssetService.transfer(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 2, 1),
            "HQ-2",
            "CC-2",
            "transfer-1",
        )
        self.assertEqual(asset.location, "HQ-2")
        asset = FixedAssetService.record_impairment(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 3, 1),
            Decimal("900.00"),
            "Damage",
            "impair-1",
        )
        self.assertEqual(asset.accumulated_impairment, Decimal("300.00"))
        asset = FixedAssetService.dispose(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 4, 1),
            Decimal("950.00"),
            "Sold",
            "dispose-1",
        )
        self.assertEqual(asset.status, "disposed")
        self.assertEqual(asset.disposal_gain_loss, Decimal("50.00"))
        duplicate = FixedAssetService.dispose(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 4, 1),
            Decimal("950.00"),
            "Sold",
            "dispose-1",
        )
        self.assertEqual(duplicate.id, asset.id)
        self.assertEqual(AssetTransaction.objects.filter(asset=asset).count(), 4)

    def test_straight_line_partial_period_reconciles_exactly(self) -> None:
        asset = self.create_asset(cost="1200.00")
        asset = FixedAssetService.capitalize(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 1, 15),
            "cap-partial",
            depreciation_start_date=date(2026, 1, 15),
            expected_version=asset.version,
        )
        schedule = DepreciationService.create_schedule_draft(
            self.tenant, asset.id, self.actor, {}, "schedule-partial"
        )
        schedule = DepreciationService.calculate_schedule(
            self.tenant, schedule.id, self.actor, {}, "calculate-partial"
        )
        lines = list(schedule.lines.order_by("sequence"))
        self.assertEqual(len(lines), 13)
        self.assertLess(lines[0].depreciation_amount, Decimal("100.00"))
        self.assertEqual(
            sum((line.depreciation_amount for line in lines), Decimal("0.00")),
            schedule.depreciable_amount,
        )
        self.assertEqual(lines[-1].closing_net_book_value, schedule.residual_value)

    def test_units_schedule_requires_complete_reconciled_input(self) -> None:
        asset = self.create_asset(cost="1000.00")
        asset.depreciation_method = "units_of_production"
        asset.expected_total_units = Decimal("100.0000")
        asset.save()
        asset = self.capitalize(asset, "cap-units")
        schedule = DepreciationService.create_schedule_draft(
            self.tenant,
            asset.id,
            self.actor,
            {"start_date": date(2026, 1, 1), "end_date": date(2026, 2, 28)},
            "schedule-units",
        )
        with self.assertRaises(FixedAssetServiceError):
            DepreciationService.calculate_schedule(
                self.tenant, schedule.id, self.actor, {}, "calculate-units-missing"
            )
        schedule = DepreciationService.calculate_schedule(
            self.tenant,
            schedule.id,
            self.actor,
            {"2026-01-01": Decimal("40"), "2026-02-01": Decimal("60")},
            "calculate-units",
        )
        self.assertEqual(schedule.lines.count(), 2)
        self.assertEqual(schedule.total_planned_depreciation, Decimal("1000.00"))

    def test_posting_worker_updates_line_asset_ledger_and_job(self) -> None:
        asset = self.capitalize(self.create_asset())
        schedule = DepreciationService.create_schedule_draft(
            self.tenant, asset.id, self.actor, {}, "schedule-post"
        )
        schedule = DepreciationService.calculate_schedule(
            self.tenant, schedule.id, self.actor, {}, "calculate-post"
        )
        schedule = DepreciationService.activate_schedule(
            self.tenant, schedule.id, self.actor, "activate-post"
        )
        line = schedule.lines.order_by("sequence").first()
        job = DepreciationService.enqueue_line_posting(
            self.tenant, line.id, self.actor, "post-line-1", "corr-post"
        )
        completed = execute(job.id, self.tenant)
        line.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(completed.status, JobStatus.SUCCEEDED)
        self.assertEqual(line.status, "posted")
        self.assertIsNotNone(line.journal_entry_id)
        self.assertEqual(asset.net_book_value, Decimal("1100.00"))
        self.assertEqual(
            AssetTransaction.objects.filter(
                asset=asset, transaction_type="depreciation"
            ).count(),
            1,
        )

    def test_accounting_failure_marks_line_and_job_without_balance_change(self) -> None:
        asset = self.capitalize(self.create_asset())
        schedule = DepreciationService.create_schedule_draft(
            self.tenant, asset.id, self.actor, {}, "schedule-fail"
        )
        schedule = DepreciationService.calculate_schedule(
            self.tenant, schedule.id, self.actor, {}, "calculate-fail"
        )
        schedule = DepreciationService.activate_schedule(
            self.tenant, schedule.id, self.actor, "activate-fail"
        )
        line: DepreciationLine = schedule.lines.order_by("sequence").first()
        job = DepreciationService.enqueue_line_posting(
            self.tenant, line.id, self.actor, "post-fail", "corr-fail"
        )
        extension_registry.set_accounting_port(FakeAccounting(failure=True))
        with self.assertRaises(JobExecutionError):
            execute(job.id, self.tenant)
        line.refresh_from_db()
        asset.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(line.status, "failed")
        self.assertEqual(line.posting_error_code, "CAPABILITY_UNAVAILABLE")
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(asset.net_book_value, Decimal("1200.00"))
