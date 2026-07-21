"""PostgreSQL policy proofs independent of ORM tenant filtering."""

from __future__ import annotations

import importlib
import uuid

import pytest
from django.db import DatabaseError, connection, transaction

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.postgresql]


def tenant_tables() -> tuple[str, ...]:
    module = importlib.import_module(
        "src.modules.security_access_control.migrations.0005_constraints_indexes_rls"
    )
    return module.TENANT_TABLES


def test_every_tenant_table_has_forced_typed_using_and_with_check_policy() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL RLS execution runs in the dedicated PostgreSQL 17 gate")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   pg_get_expr(p.polqual, p.polrelid),
                   pg_get_expr(p.polwithcheck, p.polrelid)
              FROM pg_class c
              JOIN pg_policy p ON p.polrelid = c.oid
             WHERE c.relname = ANY(%s)
            """,
            [list(tenant_tables())],
        )
        policies = {row[0]: row[1:] for row in cursor.fetchall()}
    assert set(policies) == set(tenant_tables())
    for table, (enabled, forced, using, checking) in policies.items():
        assert enabled and forced, table
        assert "tenant_id" in using and "saraise_current_tenant_id" in using, table
        assert "tenant_id" in checking and "saraise_current_tenant_id" in checking, table


def test_non_owner_cannot_observe_or_spoof_role_tenant_without_orm_filtering() -> None:
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL RLS execution runs in the dedicated PostgreSQL 17 gate")
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    row_a, row_b = uuid.uuid4(), uuid.uuid4()
    db_role = f"sac_rls_{uuid.uuid4().hex[:12]}"
    quoted_role = connection.ops.quote_name(db_role)
    insert = """
        INSERT INTO security_roles
          (id, tenant_id, name, code, description, role_type, hierarchy_level,
           is_active, is_system, created_at, updated_at, is_deleted)
        VALUES (%s, %s, %s, %s, '', 'custom', 0, TRUE, FALSE, NOW(), NOW(), FALSE)
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
        cursor.execute(insert, [str(row_a), str(tenant_a), "Tenant A", f"a_{row_a.hex}"])
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_b)])
        cursor.execute(insert, [str(row_b), str(tenant_b), "Tenant B", f"b_{row_b.hex}"])
        cursor.execute(f"CREATE ROLE {quoted_role} NOLOGIN")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON security_roles TO {quoted_role}")
        try:
            cursor.execute(f"SET LOCAL ROLE {quoted_role}")
            cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_a)])
            cursor.execute("SELECT id FROM security_roles WHERE id IN (%s, %s) ORDER BY id", [str(row_a), str(row_b)])
            assert cursor.fetchall() == [(row_a,)]
            cursor.execute("UPDATE security_roles SET name = 'Owned' WHERE id = %s", [str(row_b)])
            assert cursor.rowcount == 0
            cursor.execute("DELETE FROM security_roles WHERE id = %s", [str(row_b)])
            assert cursor.rowcount == 0
            with pytest.raises(DatabaseError), transaction.atomic():
                cursor.execute(insert, [str(uuid.uuid4()), str(tenant_b), "Spoof", f"spoof_{uuid.uuid4().hex}"])
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP ROLE IF EXISTS {quoted_role}")
