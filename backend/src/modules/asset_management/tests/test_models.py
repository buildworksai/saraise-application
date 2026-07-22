"""Persistence invariants for assets and their immutable financial history."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from src.modules.asset_management.models import Asset, DepreciationEntry, DepreciationMethod

pytestmark = pytest.mark.django_db


def test_tenant_fields_are_indexed_uuid_fields():
    for model in (Asset, DepreciationEntry):
        field = model._meta.get_field("tenant_id")
        assert field.get_internal_type() == "UUIDField"
        assert field.db_index is True


def test_asset_clean_normalizes_human_entered_fields(asset_factory, tenant_a):
    asset = asset_factory(
        tenant_a,
        asset_code="  laptop-1 ",
        asset_name="  Field laptop  ",
        location="  Pune office  ",
    )

    assert asset.asset_code == "LAPTOP-1"
    assert asset.asset_name == "Field laptop"
    assert asset.location == "Pune office"


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"asset_code": "   "}, "asset_code"),
        ({"asset_name": "   "}, "asset_name"),
        ({"depreciation_method": DepreciationMethod.STRAIGHT_LINE, "useful_life_years": None}, "useful_life_years"),
        (
            {"depreciation_method": DepreciationMethod.NONE, "declining_balance_rate": Decimal("20")},
            "declining_balance_rate",
        ),
        ({"category": "current", "depreciation_method": DepreciationMethod.STRAIGHT_LINE}, "depreciation_method"),
    ],
)
def test_asset_cross_field_validation_rejects_invalid_domain_state(changes, field):
    values = {
        "tenant_id": uuid4(),
        "asset_code": "VALID",
        "asset_name": "Valid asset",
        "purchase_date": date(2024, 1, 1),
        "purchase_cost": Decimal("100.00"),
        "current_value": Decimal("100.00"),
        "depreciation_method": DepreciationMethod.NONE,
        "useful_life_years": None,
    }
    values.update(changes)
    asset = Asset(**values)

    with pytest.raises(ValidationError) as exc_info:
        asset.full_clean()

    assert field in exc_info.value.message_dict


def test_asset_code_is_unique_per_tenant_but_reusable_between_tenants(asset_factory, tenant_a, tenant_b):
    asset_factory(tenant_a, asset_code="SHARED")
    asset_factory(tenant_b, asset_code="SHARED")

    with pytest.raises(ValidationError):
        duplicate = Asset(
            tenant_id=tenant_a,
            asset_code="SHARED",
            asset_name="Duplicate",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("10.00"),
            current_value=Decimal("10.00"),
            depreciation_method=DepreciationMethod.NONE,
        )
        duplicate.full_clean()


def test_depreciation_entry_validates_same_tenant_parent(asset_factory, tenant_a, tenant_b):
    foreign_asset = asset_factory(tenant_b)
    entry = DepreciationEntry(
        tenant_id=tenant_a,
        asset=foreign_asset,
        entry_date=date(2024, 2, 1),
        depreciation_amount=Decimal("10.00"),
        accumulated_depreciation=Decimal("10.00"),
        book_value=Decimal("1190.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        entry.full_clean()

    assert "asset" in exc_info.value.message_dict


def test_database_rejects_cross_tenant_depreciation_relationship(asset_factory, tenant_a, tenant_b):
    foreign_asset = asset_factory(tenant_b)

    with pytest.raises(IntegrityError), transaction.atomic():
        DepreciationEntry.objects.create(
            tenant_id=tenant_a,
            asset=foreign_asset,
            entry_date=date(2024, 2, 1),
            depreciation_amount=Decimal("10.00"),
            accumulated_depreciation=Decimal("10.00"),
            book_value=Decimal("1190.00"),
        )


def test_depreciation_history_is_immutable(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    entry = DepreciationEntry.objects.create(
        tenant_id=tenant_a,
        asset=asset,
        entry_date=date(2024, 2, 1),
        depreciation_amount=Decimal("10.00"),
        accumulated_depreciation=Decimal("10.00"),
        book_value=Decimal("1190.00"),
    )

    entry.book_value = Decimal("1.00")
    with pytest.raises(ValidationError, match="immutable"):
        entry.save()
    with pytest.raises(ValidationError, match="immutable"):
        entry.delete()
    with pytest.raises(ValidationError, match="immutable"):
        DepreciationEntry.objects.filter(pk=entry.pk).update(book_value=Decimal("1.00"))
    with pytest.raises(ValidationError, match="immutable"):
        DepreciationEntry.objects.filter(pk=entry.pk).delete()


def test_asset_database_constraints_reject_invalid_financial_values(tenant_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        Asset.objects.create(
            tenant_id=tenant_a,
            asset_code="INVALID-COST",
            asset_name="Invalid cost",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("0.00"),
            current_value=Decimal("0.00"),
            depreciation_method=DepreciationMethod.NONE,
        )
