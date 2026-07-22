import uuid

import src.modules.api_management.models
from django.db import migrations, models


def validate_and_prepare_resource_uuids(apps, schema_editor):
    Resource = apps.get_model("api_management", "ApiManagementResource")
    for resource in Resource.objects.all().iterator():
        try:
            tenant_id = uuid.UUID(str(resource.tenant_id))
            resource_id = uuid.UUID(str(resource.id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError(
                f"Cannot migrate api_management resource {resource.pk}: tenant and resource IDs must be UUIDs."
            ) from exc
        Resource.objects.filter(pk=resource.pk).update(
            tenant_id=tenant_id.hex,
            id=resource_id.hex,
            idempotency_key=uuid.uuid4(),
        )


def restore_canonical_uuid_strings(apps, schema_editor):
    Resource = apps.get_model("api_management", "ApiManagementResource")
    for resource in Resource.objects.all().iterator():
        tenant_id = str(uuid.UUID(str(resource.tenant_id)))
        resource_id = str(uuid.UUID(str(resource.id)))
        Resource.objects.filter(pk=resource.pk).update(tenant_id=tenant_id, id=resource_id)


def create_append_only_triggers(apps, schema_editor):
    del apps
    tables = (
        "api_management_configuration_versions",
        "api_management_audit_records",
    )
    if schema_editor.connection.vendor == "sqlite":
        for table in tables:
            schema_editor.execute(
                f'CREATE TRIGGER "{table}_no_update" BEFORE UPDATE ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'append-only evidence cannot be updated'); END;"
            )
            schema_editor.execute(
                f'CREATE TRIGGER "{table}_no_delete" BEFORE DELETE ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'append-only evidence cannot be deleted'); END;"
            )
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            """
            CREATE OR REPLACE FUNCTION api_management_reject_evidence_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'append-only evidence cannot be modified';
            END;
            $$;
            """
        )
        for table in tables:
            schema_editor.execute(
                f'CREATE TRIGGER "{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION api_management_reject_evidence_mutation();"
            )


def drop_append_only_triggers(apps, schema_editor):
    del apps
    tables = (
        "api_management_configuration_versions",
        "api_management_audit_records",
    )
    if schema_editor.connection.vendor == "sqlite":
        for table in tables:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_no_update";')
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_no_delete";')
    elif schema_editor.connection.vendor == "postgresql":
        for table in tables:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_immutable" ON "{table}";')
        schema_editor.execute("DROP FUNCTION IF EXISTS api_management_reject_evidence_mutation();")


class Migration(migrations.Migration):
    dependencies = [("api_management", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="apimanagementresource",
            name="idempotency_key",
            field=models.UUIDField(null=True),
        ),
        migrations.RunPython(validate_and_prepare_resource_uuids, restore_canonical_uuid_strings),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="id",
            field=models.UUIDField(
                default=src.modules.api_management.models.generate_uuid,
                editable=False,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="idempotency_key",
            field=models.UUIDField(),
        ),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="name",
            field=models.CharField(db_index=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="is_active",
            field=models.BooleanField(db_index=True),
        ),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="created_by",
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="apimanagementresource",
            name="config",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="apimanagementresource",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="apimanagementresource",
            name="deleted_by",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="apimanagementresource",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddConstraint(
            model_name="apimanagementresource",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="api_mgmt_resource_idempotency_uniq",
            ),
        ),
        migrations.RemoveIndex(
            model_name="apimanagementresource",
            name="api_managem_tenant__333053_idx",
        ),
        migrations.AddIndex(
            model_name="apimanagementresource",
            index=models.Index(
                fields=["tenant_id", "deleted_at", "is_active"],
                name="api_mgmt_res_tenant_state_idx",
            ),
        ),
        migrations.CreateModel(
            name="ApiManagementConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.api_management.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("document", models.JSONField()),
                ("version", models.PositiveIntegerField()),
                ("updated_by", models.CharField(max_length=255)),
            ],
            options={"db_table": "api_management_configurations"},
        ),
        migrations.AddConstraint(
            model_name="apimanagementconfiguration",
            constraint=models.UniqueConstraint(fields=("tenant_id",), name="api_mgmt_config_tenant_uniq"),
        ),
        migrations.CreateModel(
            name="ApiManagementConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.api_management.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("actor_id", models.CharField(max_length=255)),
                ("correlation_id", models.CharField(db_index=True, max_length=255)),
                ("idempotency_key", models.UUIDField()),
                ("reason", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "api_management_configuration_versions",
                "ordering": ["-version"],
            },
        ),
        migrations.AddConstraint(
            model_name="apimanagementconfigurationversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "version"),
                name="api_mgmt_config_version_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="apimanagementconfigurationversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="api_mgmt_config_idempotency_uniq",
            ),
        ),
        migrations.CreateModel(
            name="ApiManagementAuditRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.api_management.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("target_type", models.CharField(max_length=32)),
                ("target_id", models.UUIDField(blank=True, null=True)),
                ("action", models.CharField(max_length=64)),
                ("actor_id", models.CharField(max_length=255)),
                ("correlation_id", models.CharField(db_index=True, max_length=255)),
                ("idempotency_key", models.UUIDField()),
                ("before_value", models.JSONField(blank=True, null=True)),
                ("after_value", models.JSONField(blank=True, null=True)),
                ("version", models.PositiveIntegerField()),
            ],
            options={
                "db_table": "api_management_audit_records",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="apimanagementauditrecord",
            index=models.Index(
                fields=["tenant_id", "target_type", "target_id"],
                name="api_mgmt_audit_target_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="apimanagementauditrecord",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="api_mgmt_audit_idempotency_uniq",
            ),
        ),
        migrations.RunPython(create_append_only_triggers, drop_append_only_triggers),
    ]
