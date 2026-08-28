"""Force typed PostgreSQL tenant RLS across all domain tables."""

from django.db import migrations

TABLE_POLICIES = (
    ("document_intelligence_extractions", "docintel_tenant_extractions_policy"),
    ("document_intelligence_extraction_pages", "docintel_tenant_extraction_pages_policy"),
    ("document_intelligence_classifications", "docintel_tenant_classifications_policy"),
    ("document_intelligence_classification_scores", "docintel_tenant_classification_scores_policy"),
    ("document_intelligence_classifier_training_jobs", "docintel_tenant_training_jobs_policy"),
    ("document_intelligence_classifier_model_versions", "docintel_tenant_model_versions_policy"),
    ("document_intelligence_extraction_templates", "docintel_tenant_templates_policy"),
    ("document_intelligence_extraction_template_zones", "docintel_tenant_template_zones_policy"),
)


def enable_domain_rls(apps, schema_editor):
    """Install independent USING/WITH CHECK tenant policies."""
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, policy in TABLE_POLICIES:
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(policy)
        schema_editor.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"""
            CREATE POLICY {quoted_policy} ON {quoted_table}
            USING (tenant_id = saraise_current_tenant_id())
            WITH CHECK (tenant_id = saraise_current_tenant_id());
            """)


def disable_domain_rls(apps, schema_editor):
    """Undo only the policies and table flags owned by this migration."""
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, policy in reversed(TABLE_POLICIES):
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(policy)
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("document_intelligence", "0003_domain_schema"),
    ]

    operations = [migrations.RunPython(enable_domain_rls, disable_domain_rls)]
