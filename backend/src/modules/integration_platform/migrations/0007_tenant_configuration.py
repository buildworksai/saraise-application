from django.db import migrations, models
import django.db.models.deletion
import uuid


def protect_immutable_evidence(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in (
        "integration_platform_configuration_versions",
        "integration_platform_configuration_audits",
        "integration_platform_webhook_delivery_attempts",
    ):
        function = f"{table}_reject_mutation"
        schema_editor.execute(
            f"""
            CREATE FUNCTION {function}() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'immutable integration platform evidence cannot be mutated';
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {function}();
            """
        )


def unprotect_immutable_evidence(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in (
        "integration_platform_configuration_versions",
        "integration_platform_configuration_audits",
        "integration_platform_webhook_delivery_attempts",
    ):
        function = f"{table}_reject_mutation"
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table};")
        schema_editor.execute(f"DROP FUNCTION IF EXISTS {function}();")


class Migration(migrations.Migration):
    dependencies = [("integration_platform", "0006_optional_json_validation")]

    operations = [
        migrations.AddField(
            model_name="connector",
            name="access_policy",
            field=models.CharField(
                choices=[("public", "Public"), ("entitlement_required", "Entitlement required")],
                default="public",
                max_length=32,
            ),
        ),
        migrations.RemoveField(
            model_name="webhookdelivery",
            name="response_body_excerpt",
        ),
        migrations.CreateModel(
            name="IntegrationPlatformConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(default="default", max_length=64)),
                ("version", models.PositiveIntegerField(default=1)),
                ("document", models.JSONField()),
                ("updated_by", models.UUIDField()),
            ],
            options={"db_table": "integration_platform_configuration"},
        ),
        migrations.CreateModel(
            name="IntegrationPlatformConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=64)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("created_by", models.UUIDField()),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="integration_platform.integrationplatformconfiguration")),
            ],
            options={"db_table": "integration_platform_configuration_versions"},
        ),
        migrations.CreateModel(
            name="IntegrationPlatformConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=64)),
                ("action", models.CharField(max_length=32)),
                ("from_version", models.PositiveIntegerField(null=True)),
                ("to_version", models.PositiveIntegerField()),
                ("before", models.JSONField(null=True)),
                ("after", models.JSONField()),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audits", to="integration_platform.integrationplatformconfiguration")),
            ],
            options={"db_table": "integration_platform_configuration_audits", "ordering": ("-created_at", "-to_version", "id")},
        ),
        migrations.CreateModel(
            name="WebhookDeliveryAttempt",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("attempt_number", models.PositiveSmallIntegerField()),
                ("outcome", models.CharField(max_length=32)),
                ("response_code", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("error_code", models.CharField(blank=True, max_length=100)),
                ("duration_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("job_id", models.UUIDField(db_index=True)),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("delivery", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="attempts", to="integration_platform.webhookdelivery")),
            ],
            options={
                "db_table": "integration_platform_webhook_delivery_attempts",
                "ordering": ("attempt_number", "occurred_at", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="integrationplatformconfiguration",
            constraint=models.UniqueConstraint(fields=("tenant_id", "environment"), name="intplat_config_tenant_env_uniq"),
        ),
        migrations.AddIndex(
            model_name="integrationplatformconfiguration",
            index=models.Index(fields=["tenant_id", "environment", "version"], name="intplat_config_tenant_ver_idx"),
        ),
        migrations.AddConstraint(
            model_name="integrationplatformconfigurationversion",
            constraint=models.UniqueConstraint(fields=("tenant_id", "environment", "version"), name="intplat_config_version_uniq"),
        ),
        migrations.AddIndex(
            model_name="integrationplatformconfigurationversion",
            index=models.Index(fields=["tenant_id", "configuration", "-version"], name="intplat_config_version_idx"),
        ),
        migrations.AddIndex(
            model_name="integrationplatformconfigurationaudit",
            index=models.Index(fields=["tenant_id", "configuration", "-created_at"], name="intplat_config_audit_idx"),
        ),
        migrations.AddConstraint(
            model_name="webhookdeliveryattempt",
            constraint=models.UniqueConstraint(fields=("tenant_id", "delivery", "attempt_number"), name="intplat_delivery_attempt_uniq"),
        ),
        migrations.AddIndex(
            model_name="webhookdeliveryattempt",
            index=models.Index(fields=["tenant_id", "delivery", "attempt_number"], name="intplat_delivery_attempt_idx"),
        ),
        migrations.RunPython(protect_immutable_evidence, unprotect_immutable_evidence),
    ]
