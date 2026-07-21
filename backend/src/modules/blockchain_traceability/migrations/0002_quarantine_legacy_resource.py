"""Quarantine the generic legacy table without altering a single row."""

from django.db import migrations


def quarantine_legacy_resource(apps, schema_editor):
    """Install a FORCE RLS deny-all policy on PostgreSQL."""

    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name("blockchain_traceability_resources")
    policy = schema_editor.quote_name("bct_legacy_deny_all")
    schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
    schema_editor.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
    schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
    schema_editor.execute(f"CREATE POLICY {policy} ON {table} USING (FALSE) WITH CHECK (FALSE);")


def restore_legacy_resource(apps, schema_editor):
    """Remove only the quarantine policy and flags owned by this migration."""

    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name("blockchain_traceability_resources")
    policy = schema_editor.quote_name("bct_legacy_deny_all")
    schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
    schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
    schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [("blockchain_traceability", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(quarantine_legacy_resource, restore_legacy_resource)],
            state_operations=[
                migrations.RenameModel(
                    old_name="BlockchainTraceabilityResource",
                    new_name="LegacyBlockchainTraceabilityResource",
                )
            ],
        )
    ]
