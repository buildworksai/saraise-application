"""Backfill canonical version-one schemas for every legacy entity."""

import hashlib
import json
import uuid

from django.db import migrations, models


def _canonical(document):
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def backfill_schema_versions(apps, schema_editor):
    EntityDefinition = apps.get_model("metadata_modeling", "EntityDefinition")
    EntitySchemaVersion = apps.get_model("metadata_modeling", "EntitySchemaVersion")
    FieldDefinition = apps.get_model("metadata_modeling", "FieldDefinition")
    DynamicResource = apps.get_model("metadata_modeling", "DynamicResource")

    bad_fields = list(
        FieldDefinition.objects.exclude(tenant_id=models.F("entity_definition__tenant_id")).values_list(
            "id", flat=True
        )[:20]
    )
    bad_resources = list(
        DynamicResource.objects.exclude(tenant_id=models.F("entity_definition__tenant_id")).values_list(
            "id", flat=True
        )[:20]
    )
    if bad_fields or bad_resources:
        raise RuntimeError(
            "metadata_modeling 0004 rejected legacy cross-tenant relations; "
            f"field ids={bad_fields!r}, resource ids={bad_resources!r}"
        )

    duplicate_orders = list(
        FieldDefinition.objects.values("tenant_id", "entity_definition_id", "order")
        .annotate(row_count=models.Count("id"))
        .filter(row_count__gt=1)[:20]
    )
    if duplicate_orders:
        raise RuntimeError("metadata_modeling 0004 rejected duplicate field orders; " f"conflicts={duplicate_orders!r}")

    for entity in EntityDefinition.objects.order_by("id").iterator():
        fields = list(FieldDefinition.objects.filter(entity_definition_id=entity.id).order_by("order", "key"))
        normalized_fields = [
            {
                "name": field.name,
                "key": field.key,
                "field_type": field.field_type,
                "is_required": field.is_required,
                "is_read_only": field.is_read_only,
                "is_searchable": field.is_searchable,
                "default_value": field.default_value,
                "validation_rules": field.validation_rules,
                "options": field.options,
                "reference_entity_code": field.reference_entity_code,
                "help_text": field.help_text,
                "placeholder": field.placeholder,
                "order": field.order,
            }
            for field in fields
        ]
        schema = {"fields": normalized_fields}
        schema_hash = hashlib.sha256(_canonical(schema).encode("utf-8")).hexdigest()
        version = EntitySchemaVersion.objects.create(
            tenant_id=entity.tenant_id,
            entity_definition_id=entity.id,
            version=1,
            status="published",
            schema=schema,
            schema_hash=schema_hash,
            change_summary="Generated from the legacy unversioned schema.",
            compatibility="compatible",
            validation_report={"valid": True, "source": "legacy_backfill"},
            published_at=entity.updated_at,
            published_by=entity.updated_by,
            created_by=entity.created_by,
        )
        FieldDefinition.objects.filter(entity_definition_id=entity.id).update(schema_version_id=version.id)
        resources = DynamicResource.objects.filter(entity_definition_id=entity.id)
        for resource in resources.iterator():
            resource.schema_version_id = version.id
            if not resource.record_key:
                resource.record_key = str(resource.id)
            if not resource.display_name:
                resource.display_name = f"{entity.name} {str(resource.id)[:8]}"
            resource.save(update_fields=["schema_version", "record_key", "display_name"])
        entity.active_version_id = version.id
        entity.status = "published"
        if not entity.plural_name:
            entity.plural_name = entity.name
        entity.save(update_fields=["active_version", "status", "plural_name"])


def reverse_schema_versions(apps, schema_editor):
    EntityDefinition = apps.get_model("metadata_modeling", "EntityDefinition")
    EntitySchemaVersion = apps.get_model("metadata_modeling", "EntitySchemaVersion")
    FieldDefinition = apps.get_model("metadata_modeling", "FieldDefinition")
    DynamicResource = apps.get_model("metadata_modeling", "DynamicResource")

    EntityDefinition.objects.update(active_version=None, status="draft")
    FieldDefinition.objects.update(schema_version=None)
    DynamicResource.objects.update(schema_version=None)
    EntitySchemaVersion.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("metadata_modeling", "0003_schema_versions_and_sequences")]

    operations = [migrations.RunPython(backfill_schema_versions, reverse_schema_versions)]
