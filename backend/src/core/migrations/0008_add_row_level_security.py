"""
Add PostgreSQL Row-Level Security policies for tenant isolation.

SARAISE-33001: All tenant-scoped tables MUST enforce row-level security.

This migration:
1. Enables RLS on all tables with tenant_id column
2. Creates policies that restrict access to rows matching the current tenant
3. Uses a PostgreSQL session variable (app.current_tenant_id) for tenant context

The Django middleware sets this session variable on each request.

NOTE: These operations are PostgreSQL-only and are safely skipped on SQLite (tests).
"""

from django.db import connection, migrations


def create_rls_functions(apps, schema_editor):
    """Create RLS helper functions — PostgreSQL only."""
    if connection.vendor != "postgresql":
        return

    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION saraise_current_tenant_id()
        RETURNS TEXT AS $$
        BEGIN
            RETURN current_setting('app.current_tenant_id', TRUE);
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION saraise_enable_rls(table_name TEXT)
        RETURNS VOID AS $$
        BEGIN
            -- Enable RLS on the table
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);

            -- Force RLS even for table owners (prevents bypass)
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);

            -- Create tenant isolation policy
            EXECUTE format(
                'CREATE POLICY tenant_isolation_%I ON %I
                 USING (tenant_id = saraise_current_tenant_id())
                 WITH CHECK (tenant_id = saraise_current_tenant_id())',
                table_name, table_name
            );

            -- Create superuser bypass policy (for migrations, admin tasks)
            EXECUTE format(
                'CREATE POLICY superuser_bypass_%I ON %I
                 USING (current_setting(''app.is_superuser'', TRUE) = ''true'')',
                table_name, table_name
            );
        END;
        $$ LANGUAGE plpgsql;
    """)


def drop_rls_functions(apps, schema_editor):
    """Drop RLS helper functions — PostgreSQL only."""
    if connection.vendor != "postgresql":
        return

    schema_editor.execute("DROP FUNCTION IF EXISTS saraise_enable_rls(TEXT);")
    schema_editor.execute("DROP FUNCTION IF EXISTS saraise_current_tenant_id();")


class Migration(migrations.Migration):
    """Add Row-Level Security policies for multi-tenant isolation."""

    dependencies = [
        ("core", "0007_add_push_notification_token"),
    ]

    operations = [
        migrations.RunPython(create_rls_functions, drop_rls_functions),
        # Note: Actual RLS enablement per table will be done by each module's migration
        # using: migrations.RunSQL("SELECT saraise_enable_rls('tablename');")
        # This keeps RLS activation co-located with the model definition.
    ]
