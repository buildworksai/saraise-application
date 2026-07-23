"""Configuration-first hardening for Regional.

The preflight deliberately stops the migration if historical tenant/resource
identifiers are not UUIDs. Guessing a replacement would silently reassign
tenant data, which is a data leak.
"""

import uuid

import django.db.models.deletion
import src.modules.regional.models
from django.db import migrations, models


def validate_uuid_data(apps, schema_editor):
    del schema_editor
    resource_model = apps.get_model("regional", "RegionalResource")
    invalid = []
    for resource_id, tenant_id in resource_model.objects.values_list("id", "tenant_id").iterator():
        try:
            uuid.UUID(str(resource_id))
            uuid.UUID(str(tenant_id))
        except (AttributeError, TypeError, ValueError):
            invalid.append({"resource_id": str(resource_id), "tenant_id": str(tenant_id)})
            if len(invalid) == 10:
                break
    if invalid:
        raise RuntimeError(
            "Regional UUID conversion stopped: invalid historical identifiers "
            f"must be corrected before retrying: {invalid}"
        )


def reverse_uuid_preflight(apps, schema_editor):
    del apps, schema_editor


class Migration(migrations.Migration):
    dependencies = [("regional", "0001_initial")]

    operations = [
        migrations.RunPython(validate_uuid_data, reverse_uuid_preflight),
        migrations.AlterField(
            model_name="regionalresource",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="regionalresource",
            name="id",
            field=models.UUIDField(
                default=src.modules.regional.models.generate_uuid,
                editable=False,
                primary_key=True,
                serialize=False,
            ),
        ),
        migrations.AlterField(
            model_name="regionalresource",
            name="name",
            field=models.CharField(db_index=True, max_length=512),
        ),
        migrations.AlterField(
            model_name="regionalresource",
            name="is_active",
            field=models.BooleanField(db_index=True),
        ),
        migrations.AlterField(
            model_name="regionalresource",
            name="config",
            field=models.JSONField(
                default=src.modules.regional.models.empty_resource_configuration,
                help_text="Typed regional resource configuration validated by RegionalService.",
            ),
        ),
        migrations.AlterField(
            model_name="regionalresource",
            name="created_by",
            field=models.CharField(db_index=True, max_length=128),
        ),
        migrations.AddField(
            model_name="regionalresource",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="regionalresource",
            name="deleted_by",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddIndex(
            model_name="regionalresource",
            index=models.Index(
                fields=["tenant_id", "deleted_at"],
                name="regional_re_tenant__deleted_idx",
            ),
        ),
        migrations.CreateModel(
            name="RegionalConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.regional.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("environment", models.CharField(max_length=32)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("updated_by", models.CharField(max_length=128)),
                ("correlation_id", models.UUIDField()),
            ],
            options={
                "db_table": "regional_configurations",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "environment"],
                        name="regional_co_tenant__env_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment"),
                        name="regional_config_tenant_environment_uniq",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="RegionalConfigurationVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.regional.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("environment", models.CharField(max_length=32)),
                ("version", models.PositiveIntegerField()),
                ("document", models.JSONField()),
                ("operation", models.CharField(max_length=32)),
                ("actor_id", models.CharField(max_length=128)),
                ("correlation_id", models.UUIDField()),
                ("previous_version", models.PositiveIntegerField(blank=True, null=True)),
            ],
            options={
                "db_table": "regional_configuration_versions",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "environment", "-version"],
                        name="regional_cv_tenant__version_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="regional_cv_tenant__corr_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "environment", "version"),
                        name="regional_config_version_uniq",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="RegionalAuditRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.regional.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor_id", models.CharField(max_length=128)),
                ("correlation_id", models.UUIDField()),
                ("operation", models.CharField(max_length=64)),
                ("entity_type", models.CharField(max_length=64)),
                ("entity_id", models.UUIDField(blank=True, null=True)),
                ("before_value", models.JSONField()),
                ("after_value", models.JSONField()),
            ],
            options={
                "db_table": "regional_audit_records",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "entity_type", "entity_id"],
                        name="regional_ar_tenant__entity_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "correlation_id"],
                        name="regional_ar_tenant__corr_idx",
                    ),
                    models.Index(
                        fields=["tenant_id", "-created_at"],
                        name="regional_ar_tenant__created_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RegionalIdempotencyRecord",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                (
                    "id",
                    models.UUIDField(
                        default=src.modules.regional.models.generate_uuid,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("operation", models.CharField(max_length=64)),
                ("idempotency_key", models.CharField(max_length=255)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("correlation_id", models.UUIDField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "resource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="idempotency_records",
                        to="regional.regionalresource",
                    ),
                ),
            ],
            options={
                "db_table": "regional_idempotency_records",
                "indexes": [
                    models.Index(
                        fields=["tenant_id", "operation", "idempotency_key"],
                        name="regional_idem_tenant__key_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "operation", "idempotency_key"),
                        name="regional_idempotency_uniq",
                    )
                ],
            },
        ),
    ]
