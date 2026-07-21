"""Enable typed, forced PostgreSQL tenant RLS on all domain tables."""

from django.db import migrations


TENANT_TABLES = (
    "customization_field_definitions",
    "customization_field_values",
    "customization_form_definitions",
    "customization_form_layout_versions",
    "customization_business_rules",
    "customization_business_rule_versions",
    "customization_rule_executions",
)


def enable_domain_rls(apps, schema_editor) -> None:
    """Use the canonical helper that verifies UUID ownership before policy creation."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        # The core helper rejects missing/non-UUID tenant columns, enables and
        # forces RLS, then creates one policy with typed USING and WITH CHECK:
        # tenant_id = saraise_current_tenant_id().
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_domain_rls(apps, schema_editor) -> None:
    """Drop module policies and completely undo forced RLS in reverse order."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in reversed(TENANT_TABLES):
        quoted_table = schema_editor.quote_name(table_name)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("customization_framework", "0002_domain_models"),
    ]

    operations = [migrations.RunPython(enable_domain_rls, disable_domain_rls)]
