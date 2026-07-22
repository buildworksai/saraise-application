"""Enforce tenant ownership below the ORM boundary.

PostgreSQL receives FORCE ROW LEVEL SECURITY plus an immutable ledger trigger.
SQLite receives the same-tenant relationship guard so local development and
tests exercise the most important relational invariant as well.
"""

from django.db import migrations


POSTGRES_TABLES = ("asset_assets", "asset_depreciation_entries")


def enable_tenant_guards(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            for table in POSTGRES_TABLES:
                policy = f"{table}_tenant_isolation"
                cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
                cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
                cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
                cursor.execute(
                    f'CREATE POLICY "{policy}" ON "{table}" '
                    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
                )

            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION asset_depreciation_tenant_guard()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM asset_assets
                        WHERE id = NEW.asset_id AND tenant_id = NEW.tenant_id
                    ) THEN
                        RAISE EXCEPTION 'asset and depreciation entry must belong to the same tenant'
                            USING ERRCODE = '23514';
                    END IF;
                    RETURN NEW;
                END;
                $$
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER asset_depreciation_tenant_guard_trigger
                BEFORE INSERT OR UPDATE ON asset_depreciation_entries
                FOR EACH ROW EXECUTE FUNCTION asset_depreciation_tenant_guard()
                """
            )
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION asset_depreciation_immutable_guard()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'depreciation history is immutable' USING ERRCODE = '55000';
                END;
                $$
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER asset_depreciation_immutable_guard_trigger
                BEFORE UPDATE OR DELETE ON asset_depreciation_entries
                FOR EACH ROW EXECUTE FUNCTION asset_depreciation_immutable_guard()
                """
            )
        elif connection.vendor == "sqlite":
            cursor.execute(
                """
                CREATE TRIGGER asset_depreciation_tenant_guard_insert
                BEFORE INSERT ON asset_depreciation_entries
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1 FROM asset_assets
                    WHERE id = NEW.asset_id AND tenant_id = NEW.tenant_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'asset and depreciation entry must belong to the same tenant');
                END
                """
            )
            cursor.execute(
                """
                CREATE TRIGGER asset_depreciation_tenant_guard_update
                BEFORE UPDATE OF asset_id, tenant_id ON asset_depreciation_entries
                FOR EACH ROW
                WHEN NOT EXISTS (
                    SELECT 1 FROM asset_assets
                    WHERE id = NEW.asset_id AND tenant_id = NEW.tenant_id
                )
                BEGIN
                    SELECT RAISE(ABORT, 'asset and depreciation entry must belong to the same tenant');
                END
                """
            )


def disable_tenant_guards(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                "DROP TRIGGER IF EXISTS asset_depreciation_immutable_guard_trigger "
                "ON asset_depreciation_entries"
            )
            cursor.execute(
                "DROP TRIGGER IF EXISTS asset_depreciation_tenant_guard_trigger "
                "ON asset_depreciation_entries"
            )
            cursor.execute("DROP FUNCTION IF EXISTS asset_depreciation_immutable_guard()")
            cursor.execute("DROP FUNCTION IF EXISTS asset_depreciation_tenant_guard()")
            for table in POSTGRES_TABLES:
                policy = f"{table}_tenant_isolation"
                cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
                cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
                cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        elif connection.vendor == "sqlite":
            cursor.execute("DROP TRIGGER IF EXISTS asset_depreciation_tenant_guard_update")
            cursor.execute("DROP TRIGGER IF EXISTS asset_depreciation_tenant_guard_insert")


class Migration(migrations.Migration):
    dependencies = [("asset_management", "0002_production_asset_domain")]

    operations = [migrations.RunPython(enable_tenant_guards, disable_tenant_guards)]
