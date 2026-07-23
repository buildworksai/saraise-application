from django.db import migrations, models
import django.db.models.deletion
import uuid


TENANT_TABLES = (
    "ai_agent_management_configuration",
    "ai_agent_management_configuration_versions",
    "ai_secret_rotation_records",
)


def install_tenant_security(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    qn = connection.ops.quote_name
    tenant_expression = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    with connection.cursor() as cursor:
        for table in TENANT_TABLES:
            policy = f"{table}_tenant_isolation"[:63]
            cursor.execute(f"ALTER TABLE {qn(table)} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {qn(table)} FORCE ROW LEVEL SECURITY")
            cursor.execute(f"DROP POLICY IF EXISTS {qn(policy)} ON {qn(table)}")
            cursor.execute(
                f"CREATE POLICY {qn(policy)} ON {qn(table)} "
                f"USING ({tenant_expression}) WITH CHECK ({tenant_expression})"
            )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION ai_tenant_guard_fn_secret_rotation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM ai_secrets parent_row
                    WHERE parent_row.id = NEW.secret_id
                      AND parent_row.tenant_id = NEW.tenant_id
                ) THEN
                    RAISE EXCEPTION 'cross-tenant relation rejected: ai_secret_rotation_records.secret_id'
                        USING ERRCODE = '23503';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        cursor.execute(
            """
            DROP TRIGGER IF EXISTS ai_tenant_guard_secret_rotation
            ON ai_secret_rotation_records
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER ai_tenant_guard_secret_rotation
            BEFORE INSERT OR UPDATE OF secret_id, tenant_id
            ON ai_secret_rotation_records FOR EACH ROW
            EXECUTE FUNCTION ai_tenant_guard_fn_secret_rotation()
            """
        )


def remove_tenant_security(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    qn = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            "DROP TRIGGER IF EXISTS ai_tenant_guard_secret_rotation ON ai_secret_rotation_records"
        )
        cursor.execute("DROP FUNCTION IF EXISTS ai_tenant_guard_fn_secret_rotation()")
        for table in reversed(TENANT_TABLES):
            policy = f"{table}_tenant_isolation"[:63]
            cursor.execute(f"DROP POLICY IF EXISTS {qn(policy)} ON {qn(table)}")
            cursor.execute(f"ALTER TABLE {qn(table)} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {qn(table)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("ai_agent_management", "0010_allow_empty_json_objects")]

    operations = [
        migrations.CreateModel(
            name="AgentManagementConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(default="production", max_length=32)),
                ("version", models.PositiveIntegerField(default=1)),
                ("document", models.JSONField(default=dict)),
            ],
            options={"db_table": "ai_agent_management_configuration"},
        ),
        migrations.CreateModel(
            name="AgentManagementConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(max_length=32)),
                ("version", models.PositiveIntegerField()),
                ("previous_document", models.JSONField(blank=True, default=dict)),
                ("document", models.JSONField(default=dict)),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.UUIDField()),
                (
                    "change_type",
                    models.CharField(
                        choices=[
                            ("update", "Update"),
                            ("import", "Import"),
                            ("rollback", "Rollback"),
                            ("bootstrap", "Bootstrap"),
                        ],
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "ai_agent_management_configuration_versions",
                "ordering": ("-version", "id"),
            },
        ),
        migrations.CreateModel(
            name="SecretRotationRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("rotated_by", models.UUIDField()),
                ("correlation_id", models.UUIDField()),
                ("previous_ciphertext", models.TextField(editable=False)),
                ("previous_wrapped_data_key", models.TextField(editable=False)),
                ("previous_key_id", models.CharField(editable=False, max_length=255)),
                ("resulting_rotated_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "secret",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rotation_records",
                        to="ai_agent_management.secret",
                    ),
                ),
            ],
            options={"db_table": "ai_secret_rotation_records"},
        ),
        migrations.AddConstraint(
            model_name="agentmanagementconfiguration",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                name="ai_config_tenant_environment_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentmanagementconfiguration",
            constraint=models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="ai_config_version_positive"),
        ),
        migrations.AddIndex(
            model_name="agentmanagementconfiguration",
            index=models.Index(fields=["tenant_id", "environment"], name="ai_config_tenant_env_idx"),
        ),
        migrations.AddConstraint(
            model_name="agentmanagementconfigurationversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment", "version"),
                name="ai_config_version_tenant_env_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="agentmanagementconfigurationversion",
            constraint=models.CheckConstraint(
                condition=models.Q(("version__gte", 1)),
                name="ai_config_history_version_positive",
            ),
        ),
        migrations.AddIndex(
            model_name="agentmanagementconfigurationversion",
            index=models.Index(
                fields=["tenant_id", "environment", "-version"],
                name="ai_config_history_t_env_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="agentmanagementconfigurationversion",
            index=models.Index(fields=["tenant_id", "correlation_id"], name="ai_config_history_corr_idx"),
        ),
        migrations.AddConstraint(
            model_name="secretrotationrecord",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="ai_secret_rotation_t_idem_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="secretrotationrecord",
            index=models.Index(
                fields=["tenant_id", "secret", "-created_at"],
                name="ai_secret_rotation_t_sec_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="secretrotationrecord",
            index=models.Index(fields=["tenant_id", "correlation_id"], name="ai_secret_rotation_corr_idx"),
        ),
        migrations.RunPython(install_tenant_security, remove_tenant_security),
    ]
