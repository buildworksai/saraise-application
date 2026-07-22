"""Forward, reverse, and PostgreSQL RLS evidence for fixed-assets migrations."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

LEGACY = ("fixed_assets", "0001_initial")
LATEST = ("fixed_assets", "0003_enable_rls_and_tenant_guards")


def _migrate(target: tuple[str, str]):
    executor = MigrationExecutor(connection)
    executor.migrate([target])
    return executor.loader.project_state([target]).apps


@pytest.mark.django_db(transaction=True)
def test_legacy_backfill_and_reverse_restore_exact_values() -> None:
    tenant_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    try:
        legacy_apps = _migrate(LEGACY)
        LegacyAsset = legacy_apps.get_model("fixed_assets", "FixedAsset")
        LegacyAsset.objects.create(
            id=asset_id,
            tenant_id=tenant_id,
            asset_code="LEG-001",
            asset_name="Legacy press",
            asset_category="heavy-machinery",
            purchase_date="2024-01-15",
            purchase_cost=Decimal("12000.00"),
            current_value=Decimal("9000.00"),
            depreciation_method="straight_line",
            useful_life_years=10,
            location="Plant A",
            is_active=True,
        )

        current_apps = _migrate(LATEST)
        Asset = current_apps.get_model("fixed_assets", "FixedAsset")
        Category = current_apps.get_model("fixed_assets", "AssetCategory")
        migrated = Asset.objects.get(pk=asset_id)
        assert migrated.tenant_id == tenant_id
        assert migrated.category_id is not None
        assert migrated.useful_life_months == 120
        assert migrated.net_book_value == Decimal("9000.00")
        assert migrated.accumulated_depreciation == Decimal("3000.00")
        assert migrated.status == "draft"
        assert Category.objects.filter(tenant_id=tenant_id, pk=migrated.category_id).count() == 1

        restored_apps = _migrate(LEGACY)
        RestoredAsset = restored_apps.get_model("fixed_assets", "FixedAsset")
        restored = RestoredAsset.objects.get(pk=asset_id)
        assert restored.tenant_id == tenant_id
        assert restored.asset_category == "heavy-machinery"
        assert restored.current_value == Decimal("9000.00")
        assert restored.useful_life_years == 10
        assert restored.is_active is True
    finally:
        _migrate(LATEST)


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_postgresql_rls_policies_are_forced_and_fail_closed() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL policy evidence requires PostgreSQL")
    _migrate(LATEST)
    tables = {
        "fixed_asset_categories",
        "fixed_assets",
        "fixed_asset_depreciation_schedules",
        "fixed_asset_depreciation_lines",
        "fixed_asset_transactions",
    }
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   p.qual, p.with_check
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_policies p ON p.tablename = c.relname AND p.schemaname = n.nspname
            WHERE n.nspname = current_schema() AND c.relname = ANY(%s)
            """,
            [sorted(tables)],
        )
        evidence = {row[0]: row[1:] for row in cursor.fetchall()}
    assert set(evidence) == tables
    for enabled, forced, using_expression, check_expression in evidence.values():
        assert enabled is True
        assert forced is True
        assert "app.tenant_id" in using_expression
        assert "app.tenant_id" in check_expression
