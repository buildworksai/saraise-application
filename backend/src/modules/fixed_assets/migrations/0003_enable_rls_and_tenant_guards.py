"""Install fail-closed PostgreSQL RLS and tenant-qualified relationship guards."""

from django.db import migrations


TABLES = (
    "fixed_asset_categories",
    "fixed_assets",
    "fixed_asset_depreciation_schedules",
    "fixed_asset_depreciation_lines",
    "fixed_asset_transactions",
)

RELATIONSHIPS = (
    ("fixed_assets", "category_id", "fixed_asset_categories"),
    ("fixed_asset_depreciation_schedules", "asset_id", "fixed_assets"),
    ("fixed_asset_depreciation_schedules", "superseded_by_id", "fixed_asset_depreciation_schedules"),
    ("fixed_asset_depreciation_lines", "schedule_id", "fixed_asset_depreciation_schedules"),
    ("fixed_asset_depreciation_lines", "asset_id", "fixed_assets"),
    ("fixed_asset_transactions", "asset_id", "fixed_assets"),
)


def enable_security(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        quoted = schema_editor.quote_name(table)
        policy = schema_editor.quote_name(f"tenant_isolation_{table}")
        schema_editor.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {policy} ON {quoted} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID)"
        )

    schema_editor.execute(
        """
        CREATE FUNCTION fixed_assets_require_same_tenant() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE parent_id UUID; parent_tenant UUID;
        BEGIN
            parent_id := (to_jsonb(NEW) ->> TG_ARGV[0])::UUID;
            IF parent_id IS NULL THEN RETURN NEW; END IF;
            EXECUTE format('SELECT tenant_id FROM %I WHERE id = $1', TG_ARGV[1])
                INTO parent_tenant USING parent_id;
            IF parent_tenant IS NULL OR parent_tenant <> NEW.tenant_id THEN
                RAISE EXCEPTION 'cross-tenant fixed-assets relationship rejected' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    for child, column, parent in RELATIONSHIPS:
        trigger = schema_editor.quote_name(f"fa_same_tenant_{child[-8:]}_{column[:10]}")
        schema_editor.execute(
            f"CREATE TRIGGER {trigger} BEFORE INSERT OR UPDATE OF tenant_id, {schema_editor.quote_name(column)} "
            f"ON {schema_editor.quote_name(child)} FOR EACH ROW "
            f"EXECUTE FUNCTION fixed_assets_require_same_tenant('{column}', '{parent}')"
        )


def disable_security(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for child, column, _parent in reversed(RELATIONSHIPS):
        trigger = schema_editor.quote_name(f"fa_same_tenant_{child[-8:]}_{column[:10]}")
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {schema_editor.quote_name(child)}")
    schema_editor.execute("DROP FUNCTION IF EXISTS fixed_assets_require_same_tenant()")
    for table in reversed(TABLES):
        quoted = schema_editor.quote_name(table)
        policy = schema_editor.quote_name(f"tenant_isolation_{table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {quoted}")
        schema_editor.execute(f"ALTER TABLE {quoted} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("fixed_assets", "0002_financial_lifecycle"),
    ]

    operations = [migrations.RunPython(enable_security, disable_security)]
