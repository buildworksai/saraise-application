"""Enable canonical typed and forced PostgreSQL RLS for every HR table."""

from django.db import migrations


TENANT_TABLES = (
    "hr_departments",
    "hr_employees",
    "hr_attendances",
    "hr_leave_balances",
    "hr_leave_requests",
)


def enable_hr_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")


def disable_hr_rls(apps, schema_editor) -> None:
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
        ("human_resources", "0003_constraints_and_indexes"),
    ]

    operations = [migrations.RunPython(enable_hr_rls, disable_hr_rls)]
