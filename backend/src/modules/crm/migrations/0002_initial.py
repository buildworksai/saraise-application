"""Compatibility node retained for databases that already applied former 0002.

The real initial schema now lives in 0001. Existing databases have both names
recorded and do not replay either migration; new databases create the schema in
0001 and traverse this no-op node before later migrations.
"""

from django.db import migrations

INITIAL_TABLES = {
    "crm_accounts",
    "crm_activities",
    "crm_contacts",
    "crm_leads",
    "crm_opportunities",
}


def verify_initial_schema(apps, schema_editor):
    """Stop a partially applied legacy chain instead of silently advancing."""

    del apps
    existing = set(schema_editor.connection.introspection.table_names())
    missing = sorted(INITIAL_TABLES - existing)
    if missing:
        raise RuntimeError(
            "CRM 0001 history repair found missing initial tables; restore the "
            f"pre-migration snapshot and repair the migration ledger: {missing!r}"
        )


class Migration(migrations.Migration):
    dependencies = [("crm", "0001_initial")]
    operations = [migrations.RunPython(verify_initial_schema, migrations.RunPython.noop)]
