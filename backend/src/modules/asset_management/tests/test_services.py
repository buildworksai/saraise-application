"""Transactional service contracts for the Asset Management authority."""

from datetime import date
from decimal import Decimal
import pytest
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError

from src.modules.asset_management.models import Asset, DepreciationEntry, DepreciationMethod
from src.modules.asset_management.services import AssetManagementError, AssetService, DepreciationService

pytestmark = pytest.mark.django_db


def test_create_derives_opening_book_value_and_normalizes_code(tenant_a):
    asset = AssetService.create_asset(
        tenant_a,
        asset_code="  mac-001 ",
        asset_name="Developer laptop",
        purchase_date=date(2024, 1, 1),
        purchase_cost="1234.567",
        depreciation_method=DepreciationMethod.NONE,
    )

    assert asset.asset_code == "MAC-001"
    assert asset.purchase_cost == Decimal("1234.57")
    assert asset.current_value == Decimal("1234.57")
    assert asset.tenant_id == tenant_a


def test_create_rejects_invalid_tenant_and_malformed_money(tenant_a):
    common = {
        "asset_code": "BAD",
        "asset_name": "Bad input",
        "purchase_date": date(2024, 1, 1),
        "purchase_cost": "100.00",
        "depreciation_method": DepreciationMethod.NONE,
    }
    with pytest.raises(AssetManagementError) as tenant_error:
        AssetService.create_asset("not-a-uuid", **common)
    assert tenant_error.value.domain_code == "INVALID_TENANT"

    common["purchase_cost"] = "not-money"
    with pytest.raises(AssetManagementError) as money_error:
        AssetService.create_asset(tenant_a, **common)
    assert money_error.value.domain_code == "INVALID_MONEY"


def test_duplicate_asset_codes_are_rejected_only_within_tenant(asset_factory, tenant_a, tenant_b):
    asset_factory(tenant_a, asset_code="DUPLICATE")
    asset_factory(tenant_b, asset_code="DUPLICATE")

    with pytest.raises((AssetManagementError, ValidationError)):
        asset_factory(tenant_a, asset_code="DUPLICATE")


def test_list_and_detail_are_tenant_authoritative(asset_factory, tenant_a, tenant_b):
    own = asset_factory(tenant_a)
    foreign = asset_factory(tenant_b)

    assert list(AssetService.list_assets(tenant_a)) == [own]
    assert AssetService.get_asset(tenant_a, own.id) == own
    with pytest.raises(ObjectDoesNotExist):
        AssetService.get_asset(tenant_a, foreign.id)


def test_update_cannot_cross_tenants(asset_factory, tenant_a, tenant_b):
    foreign = asset_factory(tenant_b)

    with pytest.raises(ObjectDoesNotExist):
        AssetService.update_asset(tenant_a, foreign.id, {"asset_name": "Stolen"})

    foreign.refresh_from_db()
    assert foreign.asset_name == "Test asset"


def test_update_purchase_cost_rederives_book_value_before_history(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)

    updated = AssetService.update_asset(tenant_a, asset.id, {"purchase_cost": "2400.00"})

    assert updated.purchase_cost == Decimal("2400.00")
    assert updated.current_value == Decimal("2400.00")


def test_update_rejects_duplicate_code_with_stable_error(asset_factory, tenant_a):
    asset_factory(tenant_a, asset_code="TAKEN")
    target = asset_factory(tenant_a, asset_code="AVAILABLE")

    with pytest.raises(AssetManagementError) as exc_info:
        AssetService.update_asset(tenant_a, target.id, {"asset_code": "TAKEN"})

    assert exc_info.value.domain_code == "DUPLICATE_ASSET_CODE"


def test_soft_delete_preserves_asset_and_financial_history(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    entry = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    archived = AssetService.delete_asset(tenant_a, asset.id)

    assert archived.is_deleted is True
    assert archived.is_active is False
    assert archived.deleted_at is not None
    assert Asset.objects.filter(pk=asset.pk).exists()
    assert DepreciationEntry.objects.filter(pk=entry.pk).exists()
    assert not AssetService.list_assets(tenant_a).filter(pk=asset.pk).exists()
    with pytest.raises(ObjectDoesNotExist):
        AssetService.get_asset(tenant_a, asset.pk)
    assert AssetService.get_asset(tenant_a, asset.pk, include_deleted=True).pk == asset.pk


def test_financial_terms_cannot_change_after_depreciation_history(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    with pytest.raises(AssetManagementError) as exc_info:
        AssetService.update_asset(tenant_a, asset.id, {"purchase_cost": "900.00"})

    assert exc_info.value.domain_code == "ASSET_HAS_DEPRECIATION_HISTORY"


def test_straight_line_depreciation_updates_book_value(asset_factory, tenant_a):
    asset = asset_factory(tenant_a, purchase_cost=Decimal("1200.00"), useful_life_years=10)

    entry = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert entry.depreciation_amount == Decimal("10.00")
    assert entry.accumulated_depreciation == Decimal("10.00")
    assert entry.book_value == Decimal("1190.00")
    asset.refresh_from_db()
    assert asset.current_value == Decimal("1190.00")


def test_depreciation_is_idempotent_for_same_asset_and_date(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)

    first = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))
    repeated = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert repeated.pk == first.pk
    assert DepreciationEntry.objects.for_tenant(tenant_a).filter(asset=asset).count() == 1
    asset.refresh_from_db()
    assert asset.current_value == first.book_value


def test_depreciation_requires_chronological_dates(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 3, 1))

    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert exc_info.value.domain_code == "NON_CHRONOLOGICAL_ENTRY"
    assert DepreciationEntry.objects.for_tenant(tenant_a).filter(asset=asset).count() == 1


def test_depreciation_rejects_second_date_in_same_accounting_period(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)
    DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 29))

    assert exc_info.value.domain_code == "DUPLICATE_DEPRECIATION_PERIOD"
    assert DepreciationEntry.objects.for_tenant(tenant_a).filter(asset=asset).count() == 1


def test_depreciation_is_capped_at_residual_and_never_negative(asset_factory, tenant_a):
    asset = asset_factory(
        tenant_a,
        purchase_cost=Decimal("1200.00"),
        residual_value=Decimal("100.00"),
        useful_life_years=1,
    )
    Asset.objects.filter(pk=asset.pk).update(current_value=Decimal("100.01"))

    entry = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert entry.depreciation_amount == Decimal("0.01")
    assert entry.book_value == Decimal("100.00")
    assert entry.book_value >= 0
    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 3, 1))
    assert exc_info.value.domain_code == "FULLY_DEPRECIATED"


def test_declining_balance_uses_configured_annual_rate(asset_factory, tenant_a):
    asset = asset_factory(
        tenant_a,
        depreciation_method=DepreciationMethod.DECLINING_BALANCE,
        declining_balance_rate=Decimal("24.0000"),
        useful_life_years=5,
    )

    entry = DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert entry.depreciation_amount == Decimal("24.00")
    assert entry.book_value == Decimal("1176.00")


@pytest.mark.parametrize(
    ("asset_changes", "entry_date", "expected_code"),
    [
        ({"is_active": False}, date(2024, 2, 1), "ASSET_INACTIVE"),
        ({}, date(2023, 12, 31), "ENTRY_BEFORE_PURCHASE"),
        (
            {"depreciation_method": DepreciationMethod.NONE, "useful_life_years": None},
            date(2024, 2, 1),
            "ASSET_NOT_DEPRECIABLE",
        ),
    ],
)
def test_depreciation_rejects_invalid_lifecycle_states(
    asset_factory, tenant_a, asset_changes, entry_date, expected_code
):
    asset = asset_factory(tenant_a)
    Asset.objects.filter(pk=asset.pk).update(**asset_changes)

    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, entry_date)

    assert exc_info.value.domain_code == expected_code


def test_depreciation_rejects_cross_tenant_asset(asset_factory, tenant_a, tenant_b):
    foreign = asset_factory(tenant_b)

    with pytest.raises(ObjectDoesNotExist):
        DepreciationService.calculate_depreciation(tenant_a, foreign.id, date(2024, 2, 1))


def test_depreciation_rejects_non_date_service_input(asset_factory, tenant_a):
    asset = asset_factory(tenant_a)

    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, "2024-02-01")

    assert exc_info.value.domain_code == "INVALID_ENTRY_DATE"


def test_depreciation_rejects_amount_below_currency_precision(asset_factory, tenant_a):
    asset = asset_factory(
        tenant_a,
        purchase_cost=Decimal("0.01"),
        useful_life_years=100,
    )

    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert exc_info.value.domain_code == "DEPRECIATION_BELOW_PRECISION"


def test_depreciation_persistence_failure_rolls_back_asset_value(asset_factory, tenant_a, monkeypatch):
    asset = asset_factory(tenant_a)

    def fail_save(*args, **kwargs):
        raise IntegrityError("simulated write conflict")

    monkeypatch.setattr(DepreciationEntry, "save", fail_save)
    with pytest.raises(AssetManagementError) as exc_info:
        DepreciationService.calculate_depreciation(tenant_a, asset.id, date(2024, 2, 1))

    assert exc_info.value.domain_code == "DUPLICATE_DEPRECIATION_DATE"
    asset.refresh_from_db()
    assert asset.current_value == Decimal("1200.00")
    assert not DepreciationEntry.objects.for_tenant(tenant_a).filter(asset=asset).exists()


def test_depreciation_list_and_detail_are_tenant_isolated(asset_factory, tenant_a, tenant_b):
    own_asset = asset_factory(tenant_a)
    foreign_asset = asset_factory(tenant_b)
    own = DepreciationService.calculate_depreciation(tenant_a, own_asset.id, date(2024, 2, 1))
    foreign = DepreciationService.calculate_depreciation(tenant_b, foreign_asset.id, date(2024, 2, 1))

    assert list(DepreciationService.list_entries(tenant_a)) == [own]
    assert DepreciationService.get_entry(tenant_a, own.id) == own
    with pytest.raises(ObjectDoesNotExist):
        DepreciationService.get_entry(tenant_a, foreign.id)
