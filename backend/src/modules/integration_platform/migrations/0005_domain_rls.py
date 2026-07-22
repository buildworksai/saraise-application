"""Force PostgreSQL row-level security for every tenant-owned domain table."""

from django.db import migrations


TABLES = (
    "integration_platform_integrations",
    "integration_platform_credentials",
    "integration_platform_webhooks",
    "integration_platform_webhook_deliveries",
    "integration_platform_data_mappings",
)


def enable_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            policy = f"{table}_tenant_isolation"
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cursor.execute(
                f'''CREATE POLICY "{policy}" ON "{table}"
                    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
                    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)'''
            )


def disable_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(TABLES):
            policy = f"{table}_tenant_isolation"
            cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("integration_platform", "0004_domain_state_and_secrets")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
