"""Install reversible typed tenant policies on all tenant-owned tables."""

from django.db import migrations

TABLE_POLICIES = (
    ("ai_provider_configuration_resources", "aiprov_resources_tenant_policy"),
    ("ai_provider_configuration_credentials", "aiprov_credentials_tenant_policy"),
    ("ai_provider_configuration_deployments", "aiprov_deployments_tenant_policy"),
    ("ai_provider_configuration_usage_logs", "aiprov_usage_tenant_policy"),
)


def enable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, policy in TABLE_POLICIES:
        table_name = schema_editor.quote_name(table)
        policy_name = schema_editor.quote_name(policy)
        schema_editor.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        tenant_expression = (
            "saraise_current_tenant_id()::text"
            if table == "ai_provider_configuration_resources"
            else "saraise_current_tenant_id()"
        )
        schema_editor.execute(
            f"""CREATE POLICY {policy_name} ON {table_name}
            USING (tenant_id = {tenant_expression})
            WITH CHECK (tenant_id = {tenant_expression});"""
        )


def disable_rls(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, policy in reversed(TABLE_POLICIES):
        table_name = schema_editor.quote_name(table)
        policy_name = schema_editor.quote_name(policy)
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")
        schema_editor.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("ai_provider_configuration", "0002_add_ai_provider_models"),
    ]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
