"""Persistence invariants for fixed-assets financial evidence."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from src.modules.fixed_assets.models import (
    AssetCategory,
    AssetTransaction,
    DepreciationLine,
    DepreciationSchedule,
    FixedAsset,
    ImmutableTransactionError,
    money,
)


class FixedAssetModelTests(TestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.category = AssetCategory.objects.create(
            tenant_id=self.tenant,
            code=" it ",
            name="Information technology",
            default_depreciation_method="straight_line",
            default_useful_life_months=12,
        )
        self.asset = FixedAsset.objects.create(
            tenant_id=self.tenant,
            asset_code=" lap-1 ",
            asset_name="Laptop",
            category=self.category,
            purchase_date=date(2026, 1, 1),
            purchase_cost=Decimal("1200.01"),
            currency="usd",
            residual_value=Decimal("0"),
            depreciation_method="straight_line",
            useful_life_months=12,
            net_book_value=Decimal("1200.01"),
            created_by="tester",
            updated_by="tester",
        )

    def test_normalization_rounding_and_string_representation(self) -> None:
        self.category.refresh_from_db()
        self.asset.refresh_from_db()
        self.assertEqual(self.category.code, "IT")
        self.assertEqual(self.asset.asset_code, "LAP-1")
        self.assertEqual(self.asset.currency, "USD")
        self.assertEqual(self.asset.purchase_cost, Decimal("1200.01"))
        self.assertEqual(money(Decimal("1200.005")), Decimal("1200.01"))
        self.assertEqual(str(self.asset), "LAP-1 - Laptop")

    def test_cross_tenant_category_is_rejected(self) -> None:
        foreign = AssetCategory.objects.create(
            tenant_id=uuid.uuid4(),
            code="FOREIGN",
            name="Foreign",
            default_depreciation_method="straight_line",
            default_useful_life_months=12,
        )
        self.asset.category = foreign
        with self.assertRaises(ValidationError):
            self.asset.save()

    def test_direct_status_assignment_is_rejected(self) -> None:
        self.asset.status = "active"
        with self.assertRaisesMessage(ValidationError, "state machine"):
            self.asset.save()

    def test_category_code_is_immutable_after_asset_use(self) -> None:
        self.category.code = "OTHER"
        with self.assertRaisesMessage(ValidationError, "immutable"):
            self.category.save()

    def test_posted_line_and_transaction_are_append_only(self) -> None:
        schedule = DepreciationSchedule.objects.create(
            tenant_id=self.tenant,
            asset=self.asset,
            schedule_number="LAP-1-corporate-R1",
            method="straight_line",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            cost_basis=Decimal("1200.01"),
            residual_value=Decimal("0"),
            depreciable_amount=Decimal("1200.01"),
            created_by="tester",
            updated_by="tester",
        )
        line = DepreciationLine.objects.create(
            tenant_id=self.tenant,
            schedule=schedule,
            asset=self.asset,
            sequence=1,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            opening_net_book_value=Decimal("1200.01"),
            depreciation_amount=Decimal("1200.01"),
            accumulated_depreciation=Decimal("1200.01"),
            closing_net_book_value=Decimal("0"),
            status="posted",
        )
        with self.assertRaisesMessage(ValidationError, "immutable"):
            line.save()

        entry = AssetTransaction.objects.create(
            tenant_id=self.tenant,
            asset=self.asset,
            transaction_type="capitalization",
            effective_date=date(2026, 1, 1),
            amount=Decimal("1200.01"),
            currency="USD",
            opening_net_book_value=Decimal("0"),
            closing_net_book_value=Decimal("1200.01"),
            source_type="asset",
            source_id=self.asset.id,
            idempotency_key="model-ledger",
            request_fingerprint="a" * 64,
            actor_id="tester",
            correlation_id="corr-model",
        )
        entry.metadata = {"tampered": True}
        with self.assertRaises(ImmutableTransactionError):
            entry.save()
        with self.assertRaises(ImmutableTransactionError):
            AssetTransaction.objects.filter(pk=entry.pk).delete()
