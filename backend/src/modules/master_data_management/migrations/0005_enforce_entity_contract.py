"""Contract the expanded entity table only after lossless verification."""

import decimal

import django.db.models.deletion
from django.db import migrations, models


def verify_canonical_entity_values(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    alias = schema_editor.connection.alias
    if Entity.objects.using(alias).filter(entity_type__isnull=True).exists():
        raise RuntimeError("Cannot enforce MDM entity contract: untyped rows remain")
    if Entity.objects.using(alias).filter(created_by__isnull=True).exists():
        raise RuntimeError("Cannot enforce MDM entity contract: actor audit rows remain null")
    mismatches = Entity.objects.using(alias).exclude(legacy_entity_type=models.F("entity_type__key"))
    if mismatches.exists():
        raise RuntimeError("Cannot remove legacy entity type: canonical mapping does not preserve its value")


def reconstruct_removed_legacy_columns(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    alias = schema_editor.connection.alias
    for entity in Entity.objects.using(alias).select_related("entity_type").iterator():
        Entity.objects.using(alias).filter(pk=entity.pk).update(
            legacy_entity_type=entity.entity_type.key,
            is_active=not entity.is_deleted and entity.status != "archived",
        )


class Migration(migrations.Migration):
    dependencies = [("master_data_management", "0004_add_quality_matching_merge_versions")]

    operations = [
        migrations.RemoveConstraint(model_name="masterdataentity", name="unique_entity_per_tenant"),
        migrations.RemoveIndex(model_name="masterdataentity", name="mdm_entitie_tenant__0e5009_idx"),
        migrations.RemoveIndex(model_name="masterdataentity", name="mdm_entitie_tenant__0b9645_idx"),
        migrations.RenameField(model_name="masterdataentity", old_name="entity_type", new_name="legacy_entity_type"),
        migrations.RenameField(model_name="masterdataentity", old_name="entity_type_ref", new_name="entity_type"),
        migrations.RunPython(verify_canonical_entity_values, reconstruct_removed_legacy_columns),
        migrations.AlterField(
            model_name="masterdataentity",
            name="created_by",
            field=models.UUIDField(editable=False),
        ),
        migrations.AlterField(
            model_name="masterdataentity",
            name="entity_type",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="entities", to="master_data_management.masterentitytype"),
        ),
        migrations.RemoveField(model_name="masterdataentity", name="legacy_entity_type"),
        migrations.RemoveField(model_name="masterdataentity", name="is_active"),
        migrations.AlterField(model_name="masterdataentity", name="created_at", field=models.DateTimeField(auto_now_add=True)),
        migrations.AlterField(model_name="masterdataentity", name="entity_code", field=models.CharField(max_length=100)),
        migrations.AlterField(model_name="masterdataentity", name="data", field=models.JSONField(default=dict)),
        migrations.AlterModelOptions(name="masterdataentity", options={"ordering": ("entity_code",)}),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.UniqueConstraint(condition=models.Q(("is_deleted", False)), fields=("tenant_id", "entity_type", "entity_code"), name="mdm_entity_live_business_key_uniq"),
        ),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.CheckConstraint(condition=models.Q(("quality_score__gte", decimal.Decimal("0.00")), ("quality_score__lte", decimal.Decimal("100.00"))), name="mdm_entity_quality_0_100_ck"),
        ),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.CheckConstraint(condition=models.Q(("version__gte", 1)), name="mdm_entity_version_gte_1_ck"),
        ),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.CheckConstraint(condition=~models.Q(("id", models.F("golden_record_id"))), name="mdm_entity_golden_not_self_ck"),
        ),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.CheckConstraint(condition=models.Q(("is_golden", False)) | models.Q(("golden_record__isnull", True)), name="mdm_entity_golden_has_no_parent_ck"),
        ),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.CheckConstraint(condition=models.Q(("golden_record__isnull", False), ("status", "merged")) | ~models.Q(("golden_record__isnull", True), ("status", "merged")), name="mdm_entity_merged_has_golden_ck"),
        ),
        migrations.AddConstraint(
            model_name="masterdataentity",
            constraint=models.CheckConstraint(condition=models.Q(("status", "merged")) | models.Q(("golden_record__isnull", True)), name="mdm_entity_nonmerged_no_golden_ck"),
        ),
    ]
