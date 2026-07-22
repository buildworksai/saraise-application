from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader


@pytest.mark.django_db
def test_additive_migration_chain_is_complete() -> None:
    loader = MigrationLoader(connection, ignore_no_migrations=True)
    for name in (
        "0001_initial",
        "0002_domain_foundation",
        "0003_domain_constraints",
        "0004_domain_rls",
        "0005_contract_registration",
    ):
        assert ("bank_reconciliation", name) in loader.disk_migrations


@pytest.mark.postgresql
@pytest.mark.django_db(transaction=True)
def test_rls_migration_is_present_on_postgresql() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-only RLS evidence")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM pg_policies WHERE tablename = ANY(%s)",
            [["bank_accounts", "bank_statements", "bank_transactions"]],
        )
        assert cursor.fetchone()[0] >= 3
