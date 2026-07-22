"""Reversible migration evidence for legacy financial records and guards."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)
APP = "asset_management"
LEGACY = (APP, "0001_initial")
LATEST = (APP, "0003_tenant_database_guards")


def _sqlite_guard_names() -> set[str]:
    if connection.vendor != "sqlite":
        return set()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE %s",
            ["asset_depreciation_tenant_guard_%"],
        )
        return {row[0] for row in cursor.fetchall()}


def test_forward_and_reverse_preserve_ids_values_history_and_guards():
    """Migrate real legacy rows forward, reverse, and restore latest state."""

    tenant_id = uuid4()
    asset_id = uuid4()
    entry_id = uuid4()
    executor = MigrationExecutor(connection)
    try:
        executor.migrate([LEGACY])
        legacy_apps = executor.loader.project_state([LEGACY]).apps
        LegacyAsset = legacy_apps.get_model(APP, "Asset")
        LegacyEntry = legacy_apps.get_model(APP, "DepreciationEntry")
        LegacyAsset.objects.create(
            id=asset_id,
            tenant_id=tenant_id,
            asset_code="MIGRATION-1",
            asset_name="Preserved asset",
            purchase_date=date(2024, 1, 1),
            purchase_cost=Decimal("1200.00"),
            current_value=Decimal("1190.00"),
            depreciation_method="straight_line",
            useful_life_years=10,
        )
        LegacyEntry.objects.create(
            id=entry_id,
            tenant_id=tenant_id,
            asset_id=asset_id,
            entry_date=date(2024, 2, 1),
            depreciation_amount=Decimal("10.00"),
            accumulated_depreciation=Decimal("10.00"),
            book_value=Decimal("1190.00"),
        )
        assert not _sqlite_guard_names()

        executor = MigrationExecutor(connection)
        executor.migrate([LATEST])
        latest_apps = executor.loader.project_state([LATEST]).apps
        Asset = latest_apps.get_model(APP, "Asset")
        Entry = latest_apps.get_model(APP, "DepreciationEntry")
        asset = Asset.objects.get(pk=asset_id)
        entry = Entry.objects.get(pk=entry_id)
        assert asset.tenant_id == tenant_id
        assert asset.purchase_cost == Decimal("1200.00")
        assert asset.current_value == Decimal("1190.00")
        assert asset.residual_value == Decimal("0.00")
        assert entry.asset_id == asset_id
        assert entry.book_value == Decimal("1190.00")
        constraints = {constraint.name for constraint in Asset._meta.constraints}
        indexes = {index.name for index in Asset._meta.indexes}
        assert "asset_code_tenant_uniq" in constraints
        assert "asset_current_value_valid" in constraints
        assert "asset_tenant_code_idx" in indexes
        if connection.vendor == "sqlite":
            assert _sqlite_guard_names() == {
                "asset_depreciation_tenant_guard_insert",
                "asset_depreciation_tenant_guard_update",
            }

        executor = MigrationExecutor(connection)
        executor.migrate([LEGACY])
        reversed_apps = executor.loader.project_state([LEGACY]).apps
        ReversedAsset = reversed_apps.get_model(APP, "Asset")
        ReversedEntry = reversed_apps.get_model(APP, "DepreciationEntry")
        assert ReversedAsset.objects.get(pk=asset_id).current_value == Decimal("1190.00")
        assert ReversedEntry.objects.get(pk=entry_id).asset_id == asset_id
        assert not _sqlite_guard_names()
    finally:
        # Never leak a historical schema into subsequent tests, including after
        # an assertion failure in the forward or reverse verification.
        MigrationExecutor(connection).migrate([LATEST])
