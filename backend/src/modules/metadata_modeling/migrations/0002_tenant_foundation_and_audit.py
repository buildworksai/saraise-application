"""Expand legacy rows with tenant-safe lifecycle and audit foundations."""

import uuid

from django.db import migrations, models

UNKNOWN_ACTOR_ID = uuid.UUID(int=0)


def map_legacy_origin(apps, schema_editor):
    EntityDefinition = apps.get_model("metadata_modeling", "EntityDefinition")
    EntityDefinition.objects.filter(legacy_is_system=True).update(origin="system", owner_module="system")


def restore_legacy_origin(apps, schema_editor):
    EntityDefinition = apps.get_model("metadata_modeling", "EntityDefinition")
    EntityDefinition.objects.update(legacy_is_system=False)
    EntityDefinition.objects.filter(origin="system").update(legacy_is_system=True)


def seed_actor_uuids(apps, schema_editor):
    DynamicResource = apps.get_model("metadata_modeling", "DynamicResource")
    for resource in DynamicResource.objects.all().iterator():
        if resource.legacy_created_by_id is not None:
            resource.created_by = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:legacy-user:{resource.legacy_created_by_id}")
            resource.updated_by = resource.created_by
            resource.save(update_fields=["created_by", "updated_by"])


class Migration(migrations.Migration):
    dependencies = [("metadata_modeling", "0001_initial")]

    operations = [
        migrations.RenameField(model_name="entitydefinition", old_name="is_system", new_name="legacy_is_system"),
        migrations.RenameField(model_name="dynamicresource", old_name="created_by", new_name="legacy_created_by"),
        migrations.AlterField(model_name="entitydefinition", name="name", field=models.CharField(max_length=160)),
        migrations.AlterField(model_name="entitydefinition", name="code", field=models.SlugField(max_length=100)),
        migrations.AddField(
            model_name="entitydefinition",
            name="plural_name",
            field=models.CharField(default="", max_length=160),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="owner_module",
            field=models.SlugField(default="metadata_modeling", max_length=100),
        ),
        migrations.AddField(
            model_name="entitydefinition", name="icon", field=models.CharField(blank=True, max_length=100)
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="origin",
            field=models.CharField(
                choices=[("custom", "Custom"), ("system", "System"), ("extension", "Extension")],
                default="custom",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="entitydefinition", name="is_submittable", field=models.BooleanField(default=False)
        ),
        migrations.AddField(
            model_name="entitydefinition", name="track_changes", field=models.BooleanField(default=True)
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="naming_strategy",
            field=models.CharField(
                choices=[("uuid", "UUID"), ("sequence", "Sequence"), ("field", "Field")],
                default="uuid",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="entitydefinition", name="naming_config", field=models.JSONField(blank=True, default=dict)
        ),
        migrations.AddField(
            model_name="entitydefinition", name="lock_version", field=models.PositiveIntegerField(default=1)
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="created_by",
            field=models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False),
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="updated_by",
            field=models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False),
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="archived_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="entitydefinition",
            name="archived_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(model_name="fielddefinition", name="name", field=models.CharField(max_length=160)),
        migrations.AlterField(model_name="fielddefinition", name="key", field=models.SlugField(max_length=100)),
        migrations.AlterField(
            model_name="fielddefinition",
            name="field_type",
            field=models.CharField(
                choices=[
                    ("text", "Text"),
                    ("number", "Number"),
                    ("date", "Date"),
                    ("boolean", "Boolean"),
                    ("select", "Select"),
                    ("reference", "Reference"),
                    ("json", "JSON"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(model_name="fielddefinition", name="order", field=models.PositiveIntegerField()),
        migrations.AddField(
            model_name="fielddefinition", name="is_read_only", field=models.BooleanField(default=False)
        ),
        migrations.AddField(
            model_name="fielddefinition", name="is_searchable", field=models.BooleanField(default=False)
        ),
        migrations.AddField(
            model_name="fielddefinition",
            name="reference_entity_code",
            field=models.SlugField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(model_name="fielddefinition", name="help_text", field=models.TextField(blank=True)),
        migrations.AddField(
            model_name="fielddefinition",
            name="placeholder",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="fielddefinition", name="created_at", field=models.DateTimeField(auto_now_add=True, null=True)
        ),
        migrations.AlterField(
            model_name="dynamicresource",
            name="entity_definition",
            field=models.ForeignKey(
                on_delete=models.PROTECT,
                related_name="resources",
                to="metadata_modeling.entitydefinition",
            ),
        ),
        migrations.AlterField(
            model_name="dynamicresource", name="data", field=models.JSONField(blank=True, default=dict)
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="record_key",
            field=models.CharField(default="", max_length=160),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="display_name",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="state",
            field=models.CharField(
                choices=[("draft", "Draft"), ("submitted", "Submitted"), ("cancelled", "Cancelled")],
                default="draft",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="dynamicresource", name="lock_version", field=models.PositiveIntegerField(default=1)
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="created_by",
            field=models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="updated_by",
            field=models.UUIDField(default=UNKNOWN_ACTOR_ID, editable=False),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="submitted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="submitted_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="cancelled_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="dynamicresource",
            name="deleted_by",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(map_legacy_origin, restore_legacy_origin),
        migrations.RunPython(seed_actor_uuids, migrations.RunPython.noop),
    ]
