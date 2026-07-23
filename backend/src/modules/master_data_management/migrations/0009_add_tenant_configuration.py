"""Add the tenant-owned, versioned MDM configuration aggregate."""

import uuid

import django.db.models.deletion
from django.db import migrations, models


def enable_configuration_rls_and_immutability(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table_name in ("mdm_configurations", "mdm_configuration_versions"):
        schema_editor.execute(f"SELECT saraise_enable_rls('{table_name}'::REGCLASS);")
    schema_editor.execute(
        """
        CREATE OR REPLACE FUNCTION mdm_reject_configuration_version_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'configuration version evidence is append-only';
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER mdm_configuration_versions_append_only
        BEFORE UPDATE OR DELETE ON mdm_configuration_versions
        FOR EACH ROW EXECUTE FUNCTION mdm_reject_configuration_version_mutation();
        """
    )


def disable_configuration_rls_and_immutability(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        DROP TRIGGER IF EXISTS mdm_configuration_versions_append_only
        ON mdm_configuration_versions;
        DROP FUNCTION IF EXISTS mdm_reject_configuration_version_mutation();
        """
    )
    quote = schema_editor.quote_name
    for table_name in ("mdm_configuration_versions", "mdm_configurations"):
        table = quote(table_name)
        policy = quote(f"tenant_isolation_{table_name}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):
    dependencies = [("master_data_management", "0008_immutable_evidence")]

    operations = [
        migrations.RemoveConstraint(
            model_name="masterentitytype",
            name="mdm_type_key_format_ck",
        ),
        migrations.AlterField(
            model_name="masterentitytype",
            name="key",
            field=models.CharField(max_length=64),
        ),
        migrations.CreateModel(
            name="MasterDataConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_by", models.UUIDField(editable=False)),
                ("updated_by", models.UUIDField(blank=True, editable=False, null=True)),
                ("document", models.JSONField(default=dict)),
                ("version", models.PositiveIntegerField(default=1, editable=False)),
            ],
            options={
                "db_table": "mdm_configurations",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id",),
                        name="mdm_config_tenant_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version__gte", 1)),
                        name="mdm_config_version_gte_1_ck",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "-version"],
                        name="mdm_config_tenant_version_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="MasterDataConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("version", models.PositiveIntegerField()),
                ("prior_value", models.JSONField(blank=True)),
                ("new_value", models.JSONField(blank=True)),
                ("actor_id", models.UUIDField()),
                ("correlation_id", models.CharField(max_length=64)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("change_type", models.CharField(max_length=24)),
                ("reason", models.CharField(max_length=500)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="versions",
                        to="master_data_management.masterdataconfiguration",
                    ),
                ),
            ],
            options={
                "db_table": "mdm_configuration_versions",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "configuration", "version"),
                        name="mdm_config_version_tenant_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("tenant_id", "idempotency_key"),
                        name="mdm_config_idempotency_uniq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("version__gte", 1)),
                        name="mdm_config_audit_version_gte_1_ck",
                    ),
                ],
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "configuration", "-version"],
                        name="mdm_config_audit_desc_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="mdm_config_corr_idx",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            enable_configuration_rls_and_immutability,
            disable_configuration_rls_and_immutability,
        ),
    ]
