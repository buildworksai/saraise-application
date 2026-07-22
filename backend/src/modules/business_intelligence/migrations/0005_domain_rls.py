"""Install fail-closed PostgreSQL row-level security for every BI table."""

from django.db import migrations

TABLES = (
    "bi_query_definitions",
    "bi_reports",
    "bi_dashboards",
    "bi_dashboard_widgets",
    "bi_dashboard_shares",
    "bi_query_executions",
)


def enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    predicate = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            policy = f"{table}_tenant_policy"
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
            cursor.execute(f'CREATE POLICY "{policy}" ON "{table}" USING ({predicate}) WITH CHECK ({predicate})')


def disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in reversed(TABLES):
            policy = f"{table}_tenant_policy"
            cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [("business_intelligence", "0004_domain_constraints")]
    operations = [migrations.RunPython(enable_rls, disable_rls)]
