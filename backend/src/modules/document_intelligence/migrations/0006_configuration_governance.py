"""Add governed tenant configuration and repair the retained legacy UUID columns."""

from __future__ import annotations

import uuid

from django.db import migrations, models


CONFIGURATION_TABLES = (
    ("document_intelligence_configurations", "docintel_tenant_config_policy"),
    ("document_intelligence_configuration_versions", "docintel_tenant_cfgver_policy"),
    ("document_intelligence_configuration_audits", "docintel_tenant_cfgaudit_policy"),
)
IMMUTABLE_TABLES = (
    "document_intelligence_configuration_versions",
    "document_intelligence_configuration_audits",
)


def convert_legacy_identifiers_to_uuid(apps, schema_editor):
    """Validate and convert every retained legacy identifier to PostgreSQL UUID."""
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name("document_intelligence_resources")
    for column in ("id", "tenant_id", "created_by"):
        quoted = schema_editor.quote_name(column)
        # PostgreSQL's UUID cast is the validation gate: an invalid legacy
        # identifier aborts the migration instead of silently re-keying data.
        schema_editor.execute(
            f"ALTER TABLE {table} ALTER COLUMN {quoted} TYPE uuid USING {quoted}::uuid;"
        )


def restore_legacy_identifier_text(apps, schema_editor):
    """Restore the exact legacy storage contract on migration reversal."""
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    table = schema_editor.quote_name("document_intelligence_resources")
    for column in ("id", "tenant_id", "created_by"):
        quoted = schema_editor.quote_name(column)
        schema_editor.execute(
            f"ALTER TABLE {table} ALTER COLUMN {quoted} TYPE varchar(36) USING {quoted}::text;"
        )


def install_configuration_guards(apps, schema_editor):
    """Force tenant RLS and database-level append-only evidence semantics."""
    del apps
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        for table, policy in CONFIGURATION_TABLES:
            quoted_table = schema_editor.quote_name(table)
            quoted_policy = schema_editor.quote_name(policy)
            schema_editor.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY;")
            schema_editor.execute(f"ALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY;")
            schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
            schema_editor.execute(
                f"""
                CREATE POLICY {quoted_policy} ON {quoted_table}
                USING (tenant_id = saraise_current_tenant_id())
                WITH CHECK (tenant_id = saraise_current_tenant_id());
                """
            )
        schema_editor.execute(
            """
            CREATE FUNCTION document_intelligence_reject_config_evidence_mutation()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'document intelligence configuration evidence is append-only'
                    USING ERRCODE = '55000';
            END;
            $$;
            """
        )
        for table in IMMUTABLE_TABLES:
            trigger = f"docintel_append_only_{table.rsplit('_', 1)[-1]}"
            schema_editor.execute(
                f"""
                CREATE TRIGGER {schema_editor.quote_name(trigger)}
                BEFORE UPDATE OR DELETE ON {schema_editor.quote_name(table)}
                FOR EACH ROW EXECUTE FUNCTION document_intelligence_reject_config_evidence_mutation();
                """
            )


def remove_configuration_guards(apps, schema_editor):
    """Remove only guards and policies owned by this migration."""
    del apps
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        for table in reversed(IMMUTABLE_TABLES):
            trigger = f"docintel_append_only_{table.rsplit('_', 1)[-1]}"
            schema_editor.execute(
                f"DROP TRIGGER IF EXISTS {schema_editor.quote_name(trigger)} "
                f"ON {schema_editor.quote_name(table)};"
            )
        schema_editor.execute(
            "DROP FUNCTION IF EXISTS document_intelligence_reject_config_evidence_mutation();"
        )
        for table, policy in reversed(CONFIGURATION_TABLES):
            quoted_table = schema_editor.quote_name(table)
            quoted_policy = schema_editor.quote_name(policy)
            schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
            schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
            schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [
        ("document_intelligence", "0005_register_domain_contract"),
    ]

    operations = [
        migrations.RunPython(convert_legacy_identifiers_to_uuid, restore_legacy_identifier_text),
        migrations.CreateModel(
            name="DocumentIntelligenceConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("environment", models.CharField(max_length=20)),
                ("version", models.PositiveIntegerField(default=1)),
                ("document", models.JSONField()),
                ("updated_by", models.UUIDField(editable=False)),
            ],
            options={
                "db_table": "document_intelligence_configurations",
                "indexes": [models.Index(fields=["tenant_id", "environment"], name="di_config_tenant_env")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment"), name="docintel_config_tenant_env_uniq"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version__gt", 0)), name="docintel_config_version_gt_zero"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("environment", models.CharField(max_length=20)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("change_reason", models.CharField(max_length=500)),
            ],
            options={
                "db_table": "document_intelligence_configuration_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "environment", "-version"], name="di_cfgver_tenant_env_ver"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment", "version"),
                        name="docintel_cfgver_tenant_env_ver_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version__gt", 0)), name="docintel_cfgver_version_gt_zero"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_by", models.UUIDField(editable=False)),
                ("environment", models.CharField(max_length=20)),
                ("version", models.PositiveIntegerField()),
                (
                    "operation",
                    models.CharField(
                        choices=[
                            ("initialize", "Initialize"),
                            ("update", "Update"),
                            ("import", "Import"),
                            ("rollback", "Rollback"),
                        ],
                        max_length=16,
                    ),
                ),
                ("previous_document", models.JSONField(null=True)),
                ("new_document", models.JSONField()),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("change_reason", models.CharField(max_length=500)),
            ],
            options={
                "db_table": "document_intelligence_configuration_audits",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "environment", "-version"], name="di_cfgaudit_tenant_env_ver"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment", "version"),
                        name="docintel_cfgaudit_tenant_env_ver_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version__gt", 0)), name="docintel_cfgaudit_version_gt_zero"
                    ),
                ],
            },
        ),
        migrations.RunPython(install_configuration_guards, remove_configuration_guards),
    ]
