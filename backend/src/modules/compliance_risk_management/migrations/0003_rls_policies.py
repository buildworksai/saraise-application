"""Install typed, forced, fail-closed tenant RLS on every module table."""

from django.db import migrations

TENANT_TABLES = (
    "compliance_risks",
    "compliance_risk_controls",
    "compliance_risk_control_tests",
    "compliance_risk_requirements",
    "compliance_risk_calendar_entries",
    "compliance_risk_remediation_actions",
    "compliance_risk_configurations",
    "compliance_risk_configuration_versions",
)


def install_rls(apps, schema_editor) -> None:
    """Use the canonical UUID-aware helper and ``app.tenant_id`` context."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TENANT_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS);")


def remove_rls(apps, schema_editor) -> None:
    """Remove only this module's policies and table-local RLS enforcement."""

    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(TENANT_TABLES):
        policy = f"tenant_isolation_{table}"
        schema_editor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}";')
        schema_editor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;')
        schema_editor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


class Migration(migrations.Migration):
    dependencies = [
        ("compliance_risk_management", "0002_domain_completion"),
        ("core", "0011_apply_typed_rls_to_notifications"),
    ]

    operations = [migrations.RunPython(install_rls, remove_rls)]
