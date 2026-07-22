"""Build large legacy-entity indexes without blocking PostgreSQL writes."""

from django.db import migrations, models


INDEXES = (
    models.Index(fields=("tenant_id", "entity_type", "status", "entity_code"), name="mdm_entity_type_stat_code_idx"),
    models.Index(fields=("tenant_id", "entity_type", "quality_score"), name="mdm_entity_type_quality_idx"),
    models.Index(fields=("tenant_id", "golden_record"), name="mdm_entity_golden_idx"),
    models.Index(fields=("tenant_id", "source_system", "source_record_id"), name="mdm_entity_source_idx"),
    models.Index(fields=("tenant_id", "is_deleted", "updated_at"), name="mdm_entity_deleted_upd_idx"),
)

POSTGRES_COLUMNS = {
    "mdm_entity_type_stat_code_idx": ("tenant_id", "entity_type_id", "status", "entity_code"),
    "mdm_entity_type_quality_idx": ("tenant_id", "entity_type_id", "quality_score"),
    "mdm_entity_golden_idx": ("tenant_id", "golden_record_id"),
    "mdm_entity_source_idx": ("tenant_id", "source_system", "source_record_id"),
    "mdm_entity_deleted_upd_idx": ("tenant_id", "is_deleted", "updated_at"),
}


def create_indexes(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    if schema_editor.connection.vendor != "postgresql":
        for index in INDEXES:
            schema_editor.add_index(Entity, index)
        return
    quote = schema_editor.quote_name
    table = quote(Entity._meta.db_table)
    for index in INDEXES:
        columns = ", ".join(quote(column) for column in POSTGRES_COLUMNS[index.name])
        schema_editor.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {quote(index.name)} ON {table} ({columns})")


def drop_indexes(apps, schema_editor):
    Entity = apps.get_model("master_data_management", "MasterDataEntity")
    if schema_editor.connection.vendor != "postgresql":
        for index in reversed(INDEXES):
            schema_editor.remove_index(Entity, index)
        return
    quote = schema_editor.quote_name
    for index in reversed(INDEXES):
        schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {quote(index.name)}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("master_data_management", "0005_enforce_entity_contract")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(create_indexes, drop_indexes, atomic=False)],
            state_operations=[
                migrations.AddIndex(model_name="masterdataentity", index=index)
                for index in INDEXES
            ],
        )
    ]
