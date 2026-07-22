"""Install fail-closed PostgreSQL RLS, tenant guards, and evidence guards."""

from django.db import migrations

TABLES = (
    "metadata_modeling_entitydefinition",
    "metadata_modeling_entityschemaversion",
    "metadata_modeling_fielddefinition",
    "metadata_modeling_dynamicresource",
    "metadata_modeling_dynamicresourceversion",
    "metadata_modeling_namingsequence",
    "metadata_modeling_metadatamodelingconfiguration",
    "metadata_modeling_metadataconfigurationaudit",
)

RELATIONS = (
    ("metadata_modeling_entitydefinition", "active_version_id", "metadata_modeling_entityschemaversion"),
    ("metadata_modeling_entityschemaversion", "entity_definition_id", "metadata_modeling_entitydefinition"),
    ("metadata_modeling_entityschemaversion", "based_on_version_id", "metadata_modeling_entityschemaversion"),
    ("metadata_modeling_fielddefinition", "schema_version_id", "metadata_modeling_entityschemaversion"),
    ("metadata_modeling_dynamicresource", "entity_definition_id", "metadata_modeling_entitydefinition"),
    ("metadata_modeling_dynamicresource", "schema_version_id", "metadata_modeling_entityschemaversion"),
    ("metadata_modeling_dynamicresourceversion", "resource_id", "metadata_modeling_dynamicresource"),
    ("metadata_modeling_dynamicresourceversion", "schema_version_id", "metadata_modeling_entityschemaversion"),
    ("metadata_modeling_namingsequence", "entity_definition_id", "metadata_modeling_entitydefinition"),
    (
        "metadata_modeling_metadataconfigurationaudit",
        "configuration_id",
        "metadata_modeling_metadatamodelingconfiguration",
    ),
)

IMMUTABLE_TABLES = (
    "metadata_modeling_fielddefinition",
    "metadata_modeling_dynamicresourceversion",
    "metadata_modeling_metadataconfigurationaudit",
)


def _guard_names(child, column):
    stem = f"{child.removeprefix('metadata_modeling_')}_{column.removesuffix('_id')}"
    return f"meta_tenant_guard_{stem}"[:63], f"meta_tenant_guard_fn_{stem}"[:63]


def install_security(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    qn = connection.ops.quote_name
    tenant_predicate = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    with connection.cursor() as cursor:
        for table in TABLES:
            policy = f"meta_tenant_{table.removeprefix('metadata_modeling_')}"[:63]
            cursor.execute(f"ALTER TABLE {qn(table)} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {qn(table)} FORCE ROW LEVEL SECURITY")
            cursor.execute(f"DROP POLICY IF EXISTS {qn(policy)} ON {qn(table)}")
            cursor.execute(
                f"CREATE POLICY {qn(policy)} ON {qn(table)} "
                f"USING ({tenant_predicate}) WITH CHECK ({tenant_predicate})"
            )

        for child, column, parent in RELATIONS:
            trigger, function = _guard_names(child, column)
            cursor.execute(f"""
                CREATE OR REPLACE FUNCTION {qn(function)}() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.{qn(column)} IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM {qn(parent)} parent_row
                        WHERE parent_row.id = NEW.{qn(column)}
                          AND parent_row.tenant_id = NEW.tenant_id
                    ) THEN
                        RAISE EXCEPTION 'cross-tenant metadata relation rejected: %.%', TG_TABLE_NAME, '{column}'
                            USING ERRCODE = '23503';
                    END IF;
                    RETURN NEW;
                END;
                $$
                """)
            cursor.execute(f"DROP TRIGGER IF EXISTS {qn(trigger)} ON {qn(child)}")
            cursor.execute(
                f"CREATE TRIGGER {qn(trigger)} BEFORE INSERT OR UPDATE OF tenant_id, {qn(column)} "
                f"ON {qn(child)} FOR EACH ROW EXECUTE FUNCTION {qn(function)}()"
            )

        cursor.execute("""
            CREATE OR REPLACE FUNCTION meta_schema_snapshot_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'schema version snapshots are retained evidence' USING ERRCODE = '55000';
                END IF;
                IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                   OR NEW.entity_definition_id IS DISTINCT FROM OLD.entity_definition_id
                   OR NEW.version IS DISTINCT FROM OLD.version
                   OR NEW.schema IS DISTINCT FROM OLD.schema
                   OR NEW.schema_hash IS DISTINCT FROM OLD.schema_hash
                   OR NEW.change_summary IS DISTINCT FROM OLD.change_summary
                   OR NEW.based_on_version_id IS DISTINCT FROM OLD.based_on_version_id
                   OR NEW.created_by IS DISTINCT FROM OLD.created_by
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                    RAISE EXCEPTION 'schema version content is immutable' USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END;
            $$
            """)
        cursor.execute(
            "CREATE TRIGGER meta_schema_snapshot_immutable BEFORE UPDATE OR DELETE "
            "ON metadata_modeling_entityschemaversion FOR EACH ROW EXECUTE FUNCTION meta_schema_snapshot_guard()"
        )

        cursor.execute("""
            CREATE OR REPLACE FUNCTION meta_append_only_guard() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'metadata evidence is append-only' USING ERRCODE = '55000';
            END;
            $$
            """)
        for table in IMMUTABLE_TABLES:
            trigger = f"meta_append_only_{table.removeprefix('metadata_modeling_')}"[:63]
            cursor.execute(
                f"CREATE TRIGGER {qn(trigger)} BEFORE UPDATE OR DELETE ON {qn(table)} "
                "FOR EACH ROW EXECUTE FUNCTION meta_append_only_guard()"
            )


def remove_security(apps, schema_editor):
    del apps
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    qn = connection.ops.quote_name
    with connection.cursor() as cursor:
        for table in reversed(IMMUTABLE_TABLES):
            trigger = f"meta_append_only_{table.removeprefix('metadata_modeling_')}"[:63]
            cursor.execute(f"DROP TRIGGER IF EXISTS {qn(trigger)} ON {qn(table)}")
        cursor.execute(
            "DROP TRIGGER IF EXISTS meta_schema_snapshot_immutable " "ON metadata_modeling_entityschemaversion"
        )
        cursor.execute("DROP FUNCTION IF EXISTS meta_append_only_guard()")
        cursor.execute("DROP FUNCTION IF EXISTS meta_schema_snapshot_guard()")
        for child, column, _parent in reversed(RELATIONS):
            trigger, function = _guard_names(child, column)
            cursor.execute(f"DROP TRIGGER IF EXISTS {qn(trigger)} ON {qn(child)}")
            cursor.execute(f"DROP FUNCTION IF EXISTS {qn(function)}()")
        for table in reversed(TABLES):
            policy = f"meta_tenant_{table.removeprefix('metadata_modeling_')}"[:63]
            cursor.execute(f"DROP POLICY IF EXISTS {qn(policy)} ON {qn(table)}")
            cursor.execute(f"ALTER TABLE {qn(table)} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {qn(table)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("metadata_modeling", "0005_enforce_version_constraints")]
    operations = [migrations.RunPython(install_security, remove_security)]
