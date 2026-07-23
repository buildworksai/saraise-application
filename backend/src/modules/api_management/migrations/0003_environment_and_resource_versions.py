import copy

import src.modules.api_management.models
from django.db import migrations, models


GOVERNED_DOCUMENT_ADDITIONS = {
    "environment_registry": ["development", "staging", "production"],
    "validation_limits": {
        "list_max_items": 64,
        "list_item_max_length": 128,
        "resource_name_minimum_floor": 1,
        "resource_name_minimum_ceiling": 128,
        "resource_name_maximum_floor": 1,
        "resource_name_maximum_ceiling": 255,
        "resource_description_max_length": 4_000,
        "page_size_minimum": 1,
        "page_size_maximum": 100,
        "deletion_confirmation_max_length": 512,
        "health_cache_ttl_minimum": 1,
        "health_cache_ttl_maximum": 300,
        "table_skeleton_rows_minimum": 1,
        "table_skeleton_rows_maximum": 20,
        "form_description_rows_minimum": 2,
        "form_description_rows_maximum": 20,
        "rollout_percentage_minimum": 0,
        "rollout_percentage_maximum": 100,
        "configuration_history_page_size": 25,
        "configuration_history_max_page_size": 100,
        "configuration_history_max_page": 10_000,
        "configuration_version_reason_max_length": 64,
        "resource_version_reason_max_length": 64,
        "audit_target_type_max_length": 32,
        "audit_action_max_length": 64,
    },
    "configuration_version_reasons": ["bootstrap", "update", "rollback", "import"],
    "resource_version_reasons": [
        "create",
        "update",
        "archive",
        "restore",
        "activate",
        "deactivate",
        "rollback",
        "migration_backfill",
    ],
    "audit_target_types": ["configuration", "resource"],
    "audit_actions": [
        "bootstrap",
        "update",
        "rollback",
        "import",
        "create",
        "archive",
        "restore",
        "activate",
        "deactivate",
    ],
    "rollout_strategy": "tenant_uuid_modulo",
    "rollout_bucket_count": 100,
    "quota_cost": 1,
    "navigation": {
        "resources_list": {"order": 340},
        "resources_create": {"order": 341},
        "resources_detail": {"order": 342},
        "configuration": {"order": 343},
    },
}
LEGACY_DOCUMENT_KEYS = {
    "environment",
    "resource_name_min_length",
    "resource_name_max_length",
    "resource_description_default",
    "resource_config_default",
    "resource_initially_active",
    "writable_fields",
    "filter_fields",
    "search_fields",
    "ordering_fields",
    "default_ordering",
    "page_size",
    "max_page_size",
    "deletion_confirmation_message",
    "activation_enabled",
    "deactivation_enabled",
    "health_cache_ttl_seconds",
    "table_skeleton_rows",
    "form_description_rows",
    "feature_enabled",
    "rollout_percentage",
    "rollout_roles",
    "rollout_cohorts",
    "allowed_resource_config_keys",
}


def populate_environments(apps, schema_editor):
    del schema_editor
    Configuration = apps.get_model("api_management", "ApiManagementConfiguration")
    ConfigurationVersion = apps.get_model("api_management", "ApiManagementConfigurationVersion")
    for model in (Configuration, ConfigurationVersion):
        for row in model.objects.all().iterator():
            document = copy.deepcopy(row.document) if isinstance(row.document, dict) else {}
            environment = document.get("environment", "production")
            upgraded_document = copy.deepcopy(GOVERNED_DOCUMENT_ADDITIONS)
            upgraded_document.update(document)
            registry = upgraded_document["environment_registry"]
            if environment not in registry:
                registry.append(environment)
            model.objects.filter(pk=row.pk).update(
                environment=str(environment),
                document=upgraded_document,
            )


def restore_legacy_documents(apps, schema_editor):
    del schema_editor
    Configuration = apps.get_model("api_management", "ApiManagementConfiguration")
    ConfigurationVersion = apps.get_model("api_management", "ApiManagementConfigurationVersion")
    for model in (Configuration, ConfigurationVersion):
        for row in model.objects.all().iterator():
            document = row.document if isinstance(row.document, dict) else {}
            legacy_document = {
                key: copy.deepcopy(value)
                for key, value in document.items()
                if key in LEGACY_DOCUMENT_KEYS
            }
            model.objects.filter(pk=row.pk).update(document=legacy_document)


def drop_configuration_version_trigger(apps, schema_editor):
    del apps
    table = "api_management_configuration_versions"
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_no_update";')
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_no_delete";')
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_immutable" ON "{table}";')


def create_configuration_version_trigger(apps, schema_editor):
    del apps
    table = "api_management_configuration_versions"
    if schema_editor.connection.vendor == "sqlite":
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
            f'CREATE TRIGGER "{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION api_management_reject_evidence_mutation();"
        )


def create_resource_version_triggers(apps, schema_editor):
    del apps
    table = "api_management_resource_versions"
    if schema_editor.connection.vendor == "sqlite":
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
            f'CREATE TRIGGER "{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION api_management_reject_evidence_mutation();"
        )


def drop_resource_version_triggers(apps, schema_editor):
    del apps
    table = "api_management_resource_versions"
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_no_update";')
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_no_delete";')
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{table}_immutable" ON "{table}";')


def backfill_resource_versions(apps, schema_editor):
    del schema_editor
    Resource = apps.get_model("api_management", "ApiManagementResource")
    ResourceVersion = apps.get_model("api_management", "ApiManagementResourceVersion")
    for resource in Resource.objects.all().iterator():
        ResourceVersion.objects.create(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            version=resource.version,
            snapshot={
                "id": str(resource.id),
                "name": resource.name,
                "description": resource.description,
                "is_active": resource.is_active,
                "config": resource.config,
                "version": resource.version,
                "deleted_at": resource.deleted_at.isoformat() if resource.deleted_at else None,
                "deleted_by": resource.deleted_by,
            },
            actor_id=resource.created_by,
            correlation_id="migration-0003-resource-version-backfill",
            idempotency_key=resource.idempotency_key,
            reason="migration_backfill",
        )


class Migration(migrations.Migration):
    dependencies = [("api_management", "0002_configuration_governance")]

    operations = [
        migrations.AddField(
            model_name="apimanagementconfiguration",
            name="environment",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="apimanagementconfigurationversion",
            name="environment",
            field=models.CharField(max_length=64, null=True),
        ),
        migrations.RunPython(drop_configuration_version_trigger, create_configuration_version_trigger),
        migrations.RunPython(populate_environments, restore_legacy_documents),
        migrations.RunPython(create_configuration_version_trigger, drop_configuration_version_trigger),
        migrations.AlterField(
            model_name="apimanagementconfiguration",
            name="environment",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="apimanagementconfigurationversion",
            name="environment",
            field=models.CharField(max_length=64),
        ),
        migrations.RemoveConstraint(
            model_name="apimanagementconfiguration",
            name="api_mgmt_config_tenant_uniq",
        ),
        migrations.RemoveConstraint(
            model_name="apimanagementconfigurationversion",
            name="api_mgmt_config_version_uniq",
        ),
        migrations.RemoveConstraint(
            model_name="apimanagementconfigurationversion",
            name="api_mgmt_config_idempotency_uniq",
        ),
        migrations.AddConstraint(
            model_name="apimanagementconfiguration",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment"),
                name="api_mgmt_config_tenant_env_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="apimanagementconfigurationversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment", "version"),
                name="api_mgmt_config_env_version_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="apimanagementconfigurationversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "environment", "idempotency_key"),
                name="api_mgmt_config_env_idem_uniq",
            ),
        ),
        migrations.CreateModel(
            name="ApiManagementResourceVersion",
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
                ("resource_id", models.UUIDField(db_index=True)),
                ("version", models.PositiveIntegerField()),
                ("snapshot", models.JSONField()),
                ("actor_id", models.CharField(max_length=255)),
                ("correlation_id", models.CharField(db_index=True, max_length=255)),
                ("idempotency_key", models.UUIDField()),
                ("reason", models.CharField(max_length=64)),
                ("source_version", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "db_table": "api_management_resource_versions",
                "ordering": ["-version"],
            },
        ),
        migrations.AddConstraint(
            model_name="apimanagementresourceversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "resource_id", "version"),
                name="api_mgmt_res_version_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="apimanagementresourceversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"),
                name="api_mgmt_res_version_idem_uniq",
            ),
        ),
        migrations.RunPython(backfill_resource_versions, migrations.RunPython.noop),
        migrations.RunPython(create_resource_version_triggers, drop_resource_version_triggers),
    ]
