from django.db import migrations, models
import django.db.models.deletion
import uuid


def enable_configuration_guards(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            for table in (
                "asset_management_configurations",
                "asset_management_configuration_versions",
                "asset_management_configuration_audits",
                "asset_management_idempotency_records",
            ):
                policy = f"{table}_tenant_isolation"
                cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
                cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
                cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
                cursor.execute(
                    f'CREATE POLICY "{policy}" ON "{table}" '
                    "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
                )
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION asset_config_evidence_immutable_guard()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'asset configuration evidence is immutable' USING ERRCODE = '55000';
                END;
                $$
                """
            )
            for table in ("asset_management_configuration_versions", "asset_management_configuration_audits"):
                cursor.execute(
                    f"""
                    CREATE TRIGGER {table}_immutable_guard_trigger
                    BEFORE UPDATE OR DELETE ON {table}
                    FOR EACH ROW EXECUTE FUNCTION asset_config_evidence_immutable_guard()
                    """
                )
        elif connection.vendor == "sqlite":
            for table in ("asset_management_configuration_versions", "asset_management_configuration_audits"):
                cursor.execute(
                    f"""
                    CREATE TRIGGER {table}_immutable_update
                    BEFORE UPDATE ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, 'asset configuration evidence is immutable');
                    END
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TRIGGER {table}_immutable_delete
                    BEFORE DELETE ON {table}
                    BEGIN
                        SELECT RAISE(ABORT, 'asset configuration evidence is immutable');
                    END
                    """
                )


def disable_configuration_guards(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            for table in ("asset_management_configuration_versions", "asset_management_configuration_audits"):
                cursor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_guard_trigger ON {table}")
            cursor.execute("DROP FUNCTION IF EXISTS asset_config_evidence_immutable_guard()")
            for table in (
                "asset_management_configurations",
                "asset_management_configuration_versions",
                "asset_management_configuration_audits",
                "asset_management_idempotency_records",
            ):
                policy = f"{table}_tenant_isolation"
                cursor.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')
                cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
                cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        elif connection.vendor == "sqlite":
            for table in ("asset_management_configuration_versions", "asset_management_configuration_audits"):
                cursor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_update")
                cursor.execute(f"DROP TRIGGER IF EXISTS {table}_immutable_delete")


class Migration(migrations.Migration):
    dependencies = [("asset_management", "0003_tenant_database_guards")]

    operations = [
        migrations.CreateModel(
            name="AssetManagementConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("document", models.JSONField()),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_by", models.UUIDField(db_index=True)),
            ],
            options={
                "db_table": "asset_management_configurations",
                "indexes": [models.Index(fields=["tenant_id", "updated_at"], name="asset_config_tenant_time")],
                "constraints": [models.UniqueConstraint(fields=["tenant_id"], name="asset_config_one_per_tenant")],
            },
        ),
        migrations.CreateModel(
            name="AssetIdempotencyRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=255)),
                ("fingerprint", models.CharField(max_length=64)),
                ("operation", models.CharField(max_length=64)),
                ("result_model", models.CharField(max_length=64)),
                ("result_id", models.UUIDField()),
                ("status_code", models.PositiveSmallIntegerField()),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "asset_management_idempotency_records",
                "indexes": [models.Index(fields=["tenant_id", "operation", "created_at"], name="asset_idem_operation_time")],
                "constraints": [models.UniqueConstraint(fields=["tenant_id", "key"], name="asset_idem_tenant_key_uniq")],
            },
        ),
        migrations.CreateModel(
            name="AssetManagementConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("source", models.CharField(max_length=32)),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("created_by", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="asset_management.assetmanagementconfiguration")),
            ],
            options={
                "db_table": "asset_management_configuration_versions",
                "indexes": [models.Index(fields=["tenant_id", "configuration", "version"], name="asset_config_history")],
                "constraints": [models.UniqueConstraint(fields=["tenant_id", "configuration", "version"], name="asset_config_version_uniq")],
            },
        ),
        migrations.CreateModel(
            name="AssetManagementConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("action", models.CharField(max_length=32)),
                ("previous_document", models.JSONField(blank=True)),
                ("current_document", models.JSONField()),
                ("correlation_id", models.CharField(db_index=True, max_length=128)),
                ("created_by", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("configuration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="audits", to="asset_management.assetmanagementconfiguration")),
            ],
            options={
                "db_table": "asset_management_configuration_audits",
                "indexes": [models.Index(fields=["tenant_id", "configuration", "created_at"], name="asset_config_audit_time")],
            },
        ),
        migrations.RunPython(enable_configuration_guards, disable_configuration_guards),
    ]
