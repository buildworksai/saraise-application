"""Add tenant-owned, versioned DMS configuration and upload idempotency."""

import uuid
import importlib

import django.db.models.deletion
from django.db import migrations, models

TENANT_TABLES = (
    "dms_configurations",
    "dms_configuration_versions",
    "dms_configuration_audit",
    "dms_upload_idempotency",
)

RELATIONSHIPS = (
    ("dms_configuration_versions", "configuration_id", "dms_configurations"),
    ("dms_configuration_audit", "configuration_id", "dms_configurations"),
    ("dms_upload_idempotency", "document_id", "dms_documents"),
    ("dms_upload_idempotency", "version_id", "dms_document_versions"),
)


def enable_configuration_isolation(apps, schema_editor) -> None:
    del apps
    base = importlib.import_module("src.modules.dms.migrations.0006_enable_dms_rls")
    backend = base._backend(schema_editor.connection)
    if backend == "postgresql":
        for table_name in TENANT_TABLES:
            schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")
        return
    for table_name in TENANT_TABLES:
        schema_editor.execute(f"""
            CREATE TRIGGER {table_name}_tenant_id_immutable
            BEFORE UPDATE OF tenant_id ON {table_name}
            FOR EACH ROW WHEN NEW.tenant_id <> OLD.tenant_id
            BEGIN SELECT RAISE(ABORT, 'DMS tenant ownership is immutable'); END
        """)
    for table_name, column_name, related_table in RELATIONSHIPS:
        for operation, timing in (("insert", "BEFORE INSERT"), ("update", f"BEFORE UPDATE OF {column_name}, tenant_id")):
            schema_editor.execute(f"""
                CREATE TRIGGER {table_name}_{column_name}_same_tenant_{operation}
                {timing} ON {table_name}
                FOR EACH ROW WHEN NEW.{column_name} IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM {related_table} AS related
                    WHERE related.id = NEW.{column_name} AND related.tenant_id = NEW.tenant_id
                )
                BEGIN SELECT RAISE(ABORT, 'DMS relationship crosses tenant boundary'); END
            """)


def disable_configuration_isolation(apps, schema_editor) -> None:
    del apps
    base = importlib.import_module("src.modules.dms.migrations.0006_enable_dms_rls")
    backend = base._backend(schema_editor.connection)
    if backend == "postgresql":
        for table_name in reversed(TENANT_TABLES):
            quoted_table = schema_editor.quote_name(table_name)
            quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table_name}")
            schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table};")
            schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY;")
            schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY;")
        return
    for table_name, column_name, _related_table in reversed(RELATIONSHIPS):
        for operation in ("update", "insert"):
            schema_editor.execute(
                f"DROP TRIGGER IF EXISTS {table_name}_{column_name}_same_tenant_{operation};"
            )
    for table_name in reversed(TENANT_TABLES):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table_name}_tenant_id_immutable;")


class Migration(migrations.Migration):
    dependencies = [("dms", "0006_enable_dms_rls")]

    operations = [
        migrations.CreateModel(
            name="DmsConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(default="default", max_length=64)),
                ("values", models.JSONField(default=dict)),
                ("version", models.PositiveIntegerField(default=1)),
                ("updated_by", models.UUIDField()),
            ],
            options={
                "db_table": "dms_configurations",
                "indexes": [
                    models.Index(fields=["tenant_id", "environment"], name="dms_config_tenant_env_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment"),
                        name="dms_config_tenant_env_uq",
                    ),
                    models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="dms_config_version_gte1"),
                ],
            },
        ),
        migrations.CreateModel(
            name="DmsUploadIdempotency",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("key_digest", models.CharField(max_length=64)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("state", models.CharField(default="pending", max_length=16)),
                (
                    "document",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="dms.document",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="dms.documentversion",
                    ),
                ),
            ],
            options={
                "db_table": "dms_upload_idempotency",
                "indexes": [
                    models.Index(fields=["tenant_id", "key_digest"], name="dms_upload_idem_lookup_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "key_digest"),
                        name="dms_upload_idem_tenant_key_uq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DmsConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField()),
                ("environment", models.CharField(max_length=64)),
                ("values", models.JSONField()),
                ("created_by", models.UUIDField()),
                ("correlation_id", models.UUIDField()),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="dms.dmsconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "dms_configuration_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "configuration", "-version"],
                        name="dms_cfg_ver_history_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "configuration", "version"),
                        name="dms_config_version_uq",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="DmsConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("action", models.CharField(max_length=32)),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.UUIDField()),
                ("from_version", models.PositiveIntegerField(null=True)),
                ("to_version", models.PositiveIntegerField()),
                ("before", models.JSONField()),
                ("after", models.JSONField()),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_records",
                        to="dms.dmsconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "dms_configuration_audit",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "configuration", "-created_at"],
                        name="dms_cfg_audit_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(enable_configuration_isolation, disable_configuration_isolation),
    ]
