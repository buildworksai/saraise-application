from django.db import migrations

TABLE_NAME = "hr_mutation_commands"
OLD_POLICY_NAME = "hr_mutation_commands_tenant_isolation"


def canonicalize_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name(TABLE_NAME)
    old_policy = schema_editor.quote_name(OLD_POLICY_NAME)
    # Static migration identifiers are quoted by Django; DDL identifiers cannot be parameterized.
    schema_editor.execute(f"DROP POLICY IF EXISTS {old_policy} ON {table};")  # nosemgrep
    # TABLE_NAME is a static migration constant and must be cast as REGCLASS inside PostgreSQL.
    schema_editor.execute(f"SELECT saraise_enable_rls('{TABLE_NAME}'::REGCLASS);")  # nosemgrep


def restore_legacy_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name(TABLE_NAME)
    old_policy = schema_editor.quote_name(OLD_POLICY_NAME)
    # Static migration identifiers are quoted by Django; DDL identifiers cannot be parameterized.
    schema_editor.execute(f"DROP POLICY IF EXISTS tenant_isolation_{TABLE_NAME} ON {table};")  # nosemgrep
    # Static migration identifiers are quoted by Django; DDL identifiers cannot be parameterized.
    schema_editor.execute(
        f"""CREATE POLICY {old_policy} ON {table}
            USING (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
            )
            WITH CHECK (
                tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
            );"""
    )  # nosemgrep


class Migration(migrations.Migration):
    dependencies = [
        ("human_resources", "0006_humanresourcesmutationcommand"),
    ]

    operations = [
        migrations.RunPython(canonicalize_rls, restore_legacy_rls),
    ]
