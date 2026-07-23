"""Add tenant CRM configuration, version history, and immutable audit evidence."""

import uuid

from django.db import migrations, models

import src.modules.crm.models


EVIDENCE_TABLES = ("crm_configuration_versions", "crm_configuration_audits")
CONFIGURATION_TABLES = ("crm_configurations", *EVIDENCE_TABLES, "crm_idempotency_records")


def protect_evidence(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION crm_reject_configuration_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'CRM configuration evidence is immutable';
        END;
        $$;
        """
    )
    for table in EVIDENCE_TABLES:
        schema_editor.execute(
            f'CREATE TRIGGER "{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION crm_reject_configuration_evidence_mutation();"
        )
    for table in CONFIGURATION_TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS)")


def unprotect_evidence(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(CONFIGURATION_TABLES):
        if table in EVIDENCE_TABLES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_immutable" ON "{table}";')
        schema_editor.execute(
            f'DROP POLICY IF EXISTS "tenant_isolation_{table}" ON "{table}";'
            f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY;'
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;'
        )
    schema_editor.execute("DROP FUNCTION IF EXISTS crm_reject_configuration_evidence_mutation();")


class Migration(migrations.Migration):
    dependencies = [("crm", "0008_enable_crm_rls")]
    operations = [
        migrations.CreateModel(
            name="CRMConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=32)),
                ("document", models.JSONField(default=dict, validators=[src.modules.crm.models.validate_metadata])),
                (
                    "feature_flags",
                    models.JSONField(default=dict, validators=[src.modules.crm.models.validate_metadata]),
                ),
                ("rollout", models.JSONField(default=dict, validators=[src.modules.crm.models.validate_metadata])),
                ("version", models.PositiveBigIntegerField(default=1, editable=False)),
                ("updated_by", models.CharField(editable=False, max_length=255)),
            ],
            options={"db_table": "crm_configurations"},
        ),
        migrations.CreateModel(
            name="CRMConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=32)),
                ("version", models.PositiveBigIntegerField()),
                ("actor_id", models.CharField(editable=False, max_length=255)),
                ("correlation_id", models.CharField(editable=False, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("document", models.JSONField(validators=[src.modules.crm.models.validate_metadata])),
                ("feature_flags", models.JSONField(validators=[src.modules.crm.models.validate_metadata])),
                ("rollout", models.JSONField(validators=[src.modules.crm.models.validate_metadata])),
                ("change_type", models.CharField(max_length=32)),
                ("rollback_of_version", models.PositiveBigIntegerField(blank=True, null=True)),
            ],
            options={"db_table": "crm_configuration_versions"},
        ),
        migrations.CreateModel(
            name="CRMConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=32)),
                ("version", models.PositiveBigIntegerField()),
                ("actor_id", models.CharField(editable=False, max_length=255)),
                ("correlation_id", models.CharField(editable=False, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, editable=False)),
                ("prior_value", models.JSONField(validators=[src.modules.crm.models.validate_metadata])),
                ("new_value", models.JSONField(validators=[src.modules.crm.models.validate_metadata])),
                ("changed_fields", models.JSONField(default=list)),
                ("action", models.CharField(max_length=32)),
            ],
            options={"db_table": "crm_configuration_audits"},
        ),
        migrations.CreateModel(
            name="CRMIdempotencyRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=180)),
                ("method", models.CharField(max_length=16)),
                ("path", models.CharField(max_length=512)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("response_status", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("response_body", models.JSONField(blank=True, null=True)),
                ("completed", models.BooleanField(default=False)),
            ],
            options={"db_table": "crm_idempotency_records"},
        ),
        migrations.AddConstraint(
            model_name="crmconfiguration",
            constraint=models.UniqueConstraint(fields=("tenant_id", "environment"), name="crm_cfg_tenant_env_uniq"),
        ),
        migrations.AddConstraint(
            model_name="crmconfiguration",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gte", 1)), name="crm_cfg_version_positive_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="crmconfigurationversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment", "version"), name="crm_config_version_tenant_env_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="crmconfiguration",
            index=models.Index(fields=["tenant_id", "environment"], name="crm_config_tenant_env_idx"),
        ),
        migrations.AddIndex(
            model_name="crmconfigurationversion",
            index=models.Index(fields=["tenant_id", "environment", "-version"], name="crm_config_version_lookup_idx"),
        ),
        migrations.AddIndex(
            model_name="crmconfigurationaudit",
            index=models.Index(fields=["tenant_id", "environment", "-created_at"], name="crm_config_audit_lookup_idx"),
        ),
        migrations.AddConstraint(
            model_name="crmidempotencyrecord",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="crm_idem_tenant_key_uniq"
            ),
        ),
        migrations.AddIndex(
            model_name="crmidempotencyrecord",
            index=models.Index(fields=["tenant_id", "-created_at"], name="crm_idem_tenant_created_idx"),
        ),
        migrations.AddIndex(
            model_name="crmconfigurationaudit",
            index=models.Index(fields=["tenant_id", "correlation_id"], name="crm_config_audit_corr_idx"),
        ),
        migrations.RunPython(protect_evidence, unprotect_evidence),
    ]
