"""Losslessly map legacy string types to tenant-owned type rows."""

import re
import uuid

from django.db import migrations
from django.utils import timezone


KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
SYSTEM_ACTOR_NAMESPACE = uuid.UUID("56edcf59-5d8e-4bee-88ec-95c93891b95c")


def _system_actor(tenant_id):
    """Return a stable audit UUID identifying this exact migration actor."""
    return uuid.uuid5(SYSTEM_ACTOR_NAMESPACE, f"mdm-migration-0003:{tenant_id}")


def backfill_entity_types(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    EntityType = apps.get_model("master_data_management", "MasterEntityType")
    alias = schema_editor.connection.alias
    pairs = list(
        Entity.objects.using(alias)
        .order_by("tenant_id", "entity_type")
        .values_list("tenant_id", "entity_type")
        .distinct()
    )
    invalid = sorted({str(key) for _, key in pairs if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key)})
    if invalid:
        raise RuntimeError(f"Invalid legacy MDM entity type keys; migration aborted: {', '.join(invalid)}")

    identities = [(tenant_id, key) for tenant_id, key in pairs]
    if len(identities) != len(set(identities)):
        raise RuntimeError("Colliding tenant/entity-type keys detected; migration aborted")

    now = timezone.now()
    for tenant_id, key in pairs:
        actor_id = _system_actor(tenant_id)
        entity_type, _ = EntityType.objects.using(alias).get_or_create(
            tenant_id=tenant_id,
            key=key,
            defaults={
                "display_name": key.replace("_", " ").title(),
                "description": "Migrated from the legacy master-data type key.",
                "json_schema": {"type": "object", "properties": {}, "additionalProperties": True},
                "schema_version": 1,
                "required_fields": [],
                "sensitive_fields": [],
                "searchable_fields": [],
                "owner_module": "master_data_management",
                "is_system": False,
                "is_active": True,
                "metadata": {"migration": "0003_backfill_entity_types", "legacy_key": key},
                "created_by": actor_id,
                "updated_by": actor_id,
            },
        )
        active_ids = Entity.objects.using(alias).filter(
            tenant_id=tenant_id,
            entity_type=key,
            is_active=True,
        )
        inactive_ids = Entity.objects.using(alias).filter(
            tenant_id=tenant_id,
            entity_type=key,
            is_active=False,
        )
        active_ids.update(
            entity_type_ref_id=entity_type.pk,
            status="active",
            is_deleted=False,
            deleted_at=None,
            source_system="manual",
            quality_score="0.00",
            version=1,
            created_by=actor_id,
            updated_by=actor_id,
        )
        inactive_ids.update(
            entity_type_ref_id=entity_type.pk,
            status="archived",
            is_deleted=True,
            deleted_at=now,
            source_system="manual",
            quality_score="0.00",
            version=1,
            created_by=actor_id,
            updated_by=actor_id,
        )

    if Entity.objects.using(alias).filter(entity_type_ref__isnull=True).exists():
        raise RuntimeError("Entity-type backfill was incomplete; migration aborted")


def restore_legacy_values(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    alias = schema_editor.connection.alias
    for entity in Entity.objects.using(alias).select_related("entity_type_ref").iterator():
        Entity.objects.using(alias).filter(pk=entity.pk).update(
            entity_type=entity.entity_type_ref.key,
            is_active=not entity.is_deleted and entity.status != "archived",
        )


class Migration(migrations.Migration):
    dependencies = [("master_data_management", "0002_add_entity_types_and_entity_evolution")]

    operations = [migrations.RunPython(backfill_entity_types, restore_legacy_values)]
