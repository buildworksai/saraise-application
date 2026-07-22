"""Enforce the versioned domain and add versioned runtime configuration."""

import uuid

import django.db.models.deletion
import src.modules.metadata_modeling.models
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q

UNKNOWN_ACTOR_ID = uuid.UUID(int=0)


def restore_legacy_columns(apps, schema_editor):
    EntityDefinition = apps.get_model("metadata_modeling", "EntityDefinition")
    FieldDefinition = apps.get_model("metadata_modeling", "FieldDefinition")
    EntityDefinition.objects.update(legacy_is_system=False)
    EntityDefinition.objects.filter(origin="system").update(legacy_is_system=True)
    for field in FieldDefinition.objects.select_related("schema_version").iterator():
        field.entity_definition_id = field.schema_version.entity_definition_id
        field.save(update_fields=["entity_definition"])
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".", 1)
    User = apps.get_model(user_app_label, user_model_name)
    DynamicResource = apps.get_model("metadata_modeling", "DynamicResource")
    actor_to_user = {
        uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:legacy-user:{user_id}"): user_id
        for user_id in User.objects.values_list("pk", flat=True)
    }
    for resource in DynamicResource.objects.exclude(created_by=UNKNOWN_ACTOR_ID).iterator():
        resource.legacy_created_by_id = actor_to_user.get(resource.created_by)
        resource.save(update_fields=["legacy_created_by"])


class Migration(migrations.Migration):
    dependencies = [("metadata_modeling", "0004_backfill_schema_versions")]

    operations = [
        migrations.AlterField(
            model_name="entitydefinition",
            name="legacy_is_system",
            field=models.BooleanField(default=False, null=True),
        ),
        migrations.AlterField(
            model_name="fielddefinition",
            name="entity_definition",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fields",
                to="metadata_modeling.entitydefinition",
            ),
        ),
        migrations.AlterUniqueTogether(name="fielddefinition", unique_together=set()),
        migrations.AlterField(
            model_name="fielddefinition",
            name="schema_version",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="fields",
                to="metadata_modeling.entityschemaversion",
            ),
        ),
        migrations.AlterField(
            model_name="fielddefinition", name="created_at", field=models.DateTimeField(auto_now_add=True)
        ),
        migrations.AlterField(
            model_name="dynamicresource",
            name="schema_version",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="resources",
                to="metadata_modeling.entityschemaversion",
            ),
        ),
        migrations.AlterUniqueTogether(name="entitydefinition", unique_together=set()),
        migrations.RemoveIndex(model_name="dynamicresource", name="metadata_mo_tenant__739d92_idx"),
        migrations.AlterModelOptions(name="entitydefinition", options={"ordering": ["name", "code"]}),
        migrations.AlterModelOptions(name="dynamicresource", options={"ordering": ["-created_at"]}),
        migrations.AddConstraint(
            model_name="entitydefinition",
            constraint=models.UniqueConstraint(fields=("tenant_id", "code"), name="meta_entity_tenant_code_uq"),
        ),
        migrations.AddConstraint(
            model_name="entitydefinition",
            constraint=models.CheckConstraint(condition=Q(lock_version__gte=1), name="meta_entity_lock_gte_1_ck"),
        ),
        migrations.AddConstraint(
            model_name="entitydefinition",
            constraint=models.CheckConstraint(
                condition=(
                    Q(status="archived", archived_at__isnull=False, archived_by__isnull=False)
                    | (~Q(status="archived") & Q(archived_at__isnull=True, archived_by__isnull=True))
                ),
                name="meta_entity_archive_audit_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="entitydefinition",
            constraint=models.CheckConstraint(
                condition=~Q(status="published") | Q(active_version__isnull=False),
                name="meta_entity_published_ver_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="entitydefinition",
            index=models.Index(fields=["tenant_id", "status", "name"], name="meta_entity_status_name_ix"),
        ),
        migrations.AddIndex(
            model_name="entitydefinition",
            index=models.Index(fields=["tenant_id", "owner_module", "status"], name="meta_entity_owner_status_ix"),
        ),
        migrations.AddIndex(
            model_name="entitydefinition",
            index=models.Index(fields=["tenant_id", "-updated_at"], name="meta_entity_updated_ix"),
        ),
        migrations.AddConstraint(
            model_name="entityschemaversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "entity_definition", "version"), name="meta_schema_entity_ver_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="entityschemaversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "entity_definition", "schema_hash"), name="meta_schema_entity_hash_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="entityschemaversion",
            constraint=models.UniqueConstraint(
                condition=Q(status="published"),
                fields=("tenant_id", "entity_definition"),
                name="meta_schema_one_published_uq",
            ),
        ),
        migrations.AddConstraint(
            model_name="entityschemaversion",
            constraint=models.CheckConstraint(condition=Q(version__gte=1), name="meta_schema_ver_gte_1_ck"),
        ),
        migrations.AddConstraint(
            model_name="entityschemaversion",
            constraint=models.CheckConstraint(
                condition=(
                    Q(status="published", published_at__isnull=False, published_by__isnull=False)
                    | (~Q(status="published") & Q(published_at__isnull=True, published_by__isnull=True))
                ),
                name="meta_schema_publish_audit_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="entityschemaversion",
            index=models.Index(fields=["tenant_id", "entity_definition", "-version"], name="meta_schema_entity_ver_ix"),
        ),
        migrations.AddIndex(
            model_name="entityschemaversion",
            index=models.Index(fields=["tenant_id", "status", "created_at"], name="meta_schema_status_created_ix"),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "schema_version", "key"), name="meta_field_schema_key_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "schema_version", "order"), name="meta_field_schema_order_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.CheckConstraint(
                condition=~Q(field_type="select") | ~Q(options=[]), name="meta_field_select_opts_ck"
            ),
        ),
        migrations.AddConstraint(
            model_name="fielddefinition",
            constraint=models.CheckConstraint(
                condition=(
                    (Q(field_type="reference") & Q(reference_entity_code__isnull=False) & ~Q(reference_entity_code=""))
                    | (
                        ~Q(field_type="reference")
                        & (Q(reference_entity_code__isnull=True) | Q(reference_entity_code=""))
                    )
                ),
                name="meta_field_reference_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="fielddefinition",
            index=models.Index(fields=["tenant_id", "schema_version", "order"], name="meta_field_schema_order_ix"),
        ),
        migrations.AddIndex(
            model_name="fielddefinition",
            index=models.Index(fields=["tenant_id", "reference_entity_code"], name="meta_field_reference_ix"),
        ),
        migrations.AddConstraint(
            model_name="dynamicresource",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "entity_definition", "record_key"), name="meta_resource_entity_key_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="dynamicresource",
            constraint=models.CheckConstraint(condition=Q(lock_version__gte=1), name="meta_resource_lock_gte_1_ck"),
        ),
        migrations.AddConstraint(
            model_name="dynamicresource",
            constraint=models.CheckConstraint(
                condition=(
                    Q(
                        state="draft",
                        submitted_at__isnull=True,
                        submitted_by__isnull=True,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                    )
                    | Q(
                        state="submitted",
                        submitted_at__isnull=False,
                        submitted_by__isnull=False,
                        cancelled_at__isnull=True,
                        cancelled_by__isnull=True,
                    )
                    | Q(
                        state="cancelled",
                        submitted_at__isnull=False,
                        submitted_by__isnull=False,
                        cancelled_at__isnull=False,
                        cancelled_by__isnull=False,
                    )
                ),
                name="meta_resource_state_audit_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="dynamicresource",
            constraint=models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="meta_resource_delete_audit_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="dynamicresource",
            index=models.Index(
                fields=["tenant_id", "entity_definition", "state", "-created_at"],
                name="meta_resource_state_created_ix",
            ),
        ),
        migrations.AddIndex(
            model_name="dynamicresource",
            index=models.Index(
                fields=["tenant_id", "entity_definition", "display_name"], name="meta_resource_display_ix"
            ),
        ),
        migrations.AddIndex(
            model_name="dynamicresource",
            index=models.Index(fields=["tenant_id", "-updated_at"], name="meta_resource_updated_ix"),
        ),
        migrations.AddConstraint(
            model_name="dynamicresourceversion",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "resource", "version"), name="meta_resver_resource_ver_uq"
            ),
        ),
        migrations.AddConstraint(
            model_name="dynamicresourceversion",
            constraint=models.CheckConstraint(condition=Q(version__gte=1), name="meta_resver_ver_gte_1_ck"),
        ),
        migrations.AddIndex(
            model_name="dynamicresourceversion",
            index=models.Index(fields=["tenant_id", "resource", "-version"], name="meta_resver_resource_ver_ix"),
        ),
        migrations.AddIndex(
            model_name="dynamicresourceversion",
            index=models.Index(fields=["tenant_id", "operation", "-changed_at"], name="meta_resver_operation_ix"),
        ),
        migrations.AddConstraint(
            model_name="namingsequence",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "entity_definition", "sequence_key", "period_key"),
                name="meta_sequence_period_uq",
            ),
        ),
        migrations.AddConstraint(
            model_name="namingsequence",
            constraint=models.CheckConstraint(condition=Q(next_value__gte=1), name="meta_sequence_next_gte_1_ck"),
        ),
        migrations.AddConstraint(
            model_name="namingsequence",
            constraint=models.CheckConstraint(
                condition=Q(padding__gte=1, padding__lte=12), name="meta_sequence_padding_ck"
            ),
        ),
        migrations.CreateModel(
            name="MetadataModelingConfiguration",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.SlugField(default="production", max_length=32)),
                ("version", models.PositiveIntegerField(default=1)),
                ("synchronous_validation_limit", models.PositiveIntegerField(default=100)),
                ("max_fields_per_schema", models.PositiveIntegerField(default=250)),
                ("max_schema_bytes", models.PositiveIntegerField(default=1048576)),
                ("max_record_data_bytes", models.PositiveIntegerField(default=1048576)),
                ("max_regex_length", models.PositiveIntegerField(default=4096)),
                ("default_page_size", models.PositiveSmallIntegerField(default=25)),
                ("max_page_size", models.PositiveSmallIntegerField(default=100)),
                (
                    "allowed_field_types",
                    models.JSONField(default=src.modules.metadata_modeling.models._default_allowed_field_types),
                ),
                (
                    "feature_flags",
                    models.JSONField(default=src.modules.metadata_modeling.models._default_feature_flags),
                ),
                ("rollout", models.JSONField(default=src.modules.metadata_modeling.models._default_rollout)),
                ("created_by", models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)),
                ("updated_by", models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False)),
            ],
            options={
                "ordering": ["environment"],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "environment"), name="meta_config_tenant_env_uq"),
                    models.CheckConstraint(condition=Q(version__gte=1), name="meta_config_ver_gte_1_ck"),
                    models.CheckConstraint(
                        condition=Q(synchronous_validation_limit__gte=1, synchronous_validation_limit__lte=10000),
                        name="meta_config_sync_limit_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(max_fields_per_schema__gte=1, max_fields_per_schema__lte=1000),
                        name="meta_config_fields_limit_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(max_schema_bytes__gte=1024, max_schema_bytes__lte=10485760),
                        name="meta_config_schema_bytes_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(max_record_data_bytes__gte=128, max_record_data_bytes__lte=10485760),
                        name="meta_config_record_bytes_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(max_regex_length__gte=1, max_regex_length__lte=4096),
                        name="meta_config_regex_limit_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(default_page_size__gte=1) & Q(default_page_size__lte=models.F("max_page_size")),
                        name="meta_config_default_page_ck",
                    ),
                    models.CheckConstraint(
                        condition=Q(max_page_size__gte=1, max_page_size__lte=1000),
                        name="meta_config_max_page_ck",
                    ),
                ],
                "indexes": [
                    models.Index(fields=["tenant_id", "environment", "-version"], name="meta_config_env_ver_ix")
                ],
            },
        ),
        migrations.CreateModel(
            name="MetadataConfigurationAudit",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                (
                    "operation",
                    models.CharField(
                        choices=[
                            ("create", "Create"),
                            ("update", "Update"),
                            ("rollback", "Rollback"),
                            ("import", "Import"),
                        ],
                        max_length=16,
                    ),
                ),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField()),
                ("changed_by", models.UUIDField()),
                ("correlation_id", models.CharField(db_index=True, max_length=64)),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "configuration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="audit_history",
                        to="metadata_modeling.metadatamodelingconfiguration",
                    ),
                ),
            ],
            options={
                "ordering": ["-version"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenant_id", "configuration", "version"), name="meta_cfgaudit_config_ver_uq"
                    ),
                    models.CheckConstraint(condition=Q(version__gte=1), name="meta_cfgaudit_ver_gte_1_ck"),
                ],
                "indexes": [
                    models.Index(fields=["tenant_id", "configuration", "-version"], name="meta_cfgaudit_config_ix")
                ],
            },
        ),
        # Reverse operations re-create these nullable columns before invoking
        # restore_legacy_columns, which reconstructs the exact 0001 relations.
        migrations.RunPython(migrations.RunPython.noop, restore_legacy_columns),
        migrations.RemoveField(model_name="entitydefinition", name="legacy_is_system"),
        migrations.RemoveField(model_name="fielddefinition", name="entity_definition"),
        migrations.RemoveField(model_name="dynamicresource", name="legacy_created_by"),
    ]
