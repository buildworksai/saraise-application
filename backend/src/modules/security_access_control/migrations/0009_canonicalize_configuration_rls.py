"""Canonicalize security configuration RLS to the typed tenant context."""

from __future__ import annotations

from django.db import migrations

TENANT_TABLES = (
    "security_configurations",
    "security_configuration_versions",
    "security_mutation_replays",
)


def install_canonical_security_configuration_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f'SELECT saraise_enable_rls(\'"{table}"\'::REGCLASS)')


def restore_legacy_security_configuration_rls(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f'DROP POLICY IF EXISTS "tenant_isolation_{table}" ON "{table}"')
        schema_editor.execute(
            f"""CREATE POLICY "{table}_tenant_isolation" ON "{table}"
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)"""
        )


class Migration(migrations.Migration):
    dependencies = [
        ("security_access_control", "0008_configurable_policy_bounds"),
    ]

    operations = [
        migrations.RunPython(install_canonical_security_configuration_rls, restore_legacy_security_configuration_rls),
    ]
