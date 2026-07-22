"""Enable and force typed PostgreSQL RLS on every compliance table."""

from django.db import migrations


COMPLIANCE_TABLES = (
    "compliance_frameworks",
    "compliance_requirements",
    "compliance_policies",
    "compliance_policy_versions",
    "compliance_requirement_policy_mappings",
    "compliance_assessments",
    "compliance_evidence",
    "compliance_evidence_requirement_links",
    "compliance_configuration_revisions",
    "compliance_activity",
)


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in COMPLIANCE_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(COMPLIANCE_TABLES):
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table}"[:63])
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [("compliance_management", "0003_migrate_legacy_compliance_data")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
