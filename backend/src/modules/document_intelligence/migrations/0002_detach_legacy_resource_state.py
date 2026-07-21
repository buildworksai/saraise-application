"""Detach the legacy scaffold model while preserving its physical table."""

from django.db import migrations


def make_legacy_table_read_only(apps, schema_editor):
    """Block writes without altering or reclassifying any legacy row."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(r"""
        CREATE FUNCTION document_intelligence_legacy_reject_write()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'legacy document intelligence resources are read-only'
                USING ERRCODE = '55000';
        END;
        $$;

        CREATE TRIGGER document_intelligence_legacy_read_only
        BEFORE INSERT OR UPDATE OR DELETE ON document_intelligence_resources
        FOR EACH ROW EXECUTE FUNCTION document_intelligence_legacy_reject_write();
        """)


def restore_legacy_table_writes(apps, schema_editor):
    """Reverse only the write guard introduced above."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(r"""
        DROP TRIGGER IF EXISTS document_intelligence_legacy_read_only
            ON document_intelligence_resources;
        DROP FUNCTION IF EXISTS document_intelligence_legacy_reject_write();
        """)


class Migration(migrations.Migration):
    dependencies = [("document_intelligence", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(make_legacy_table_read_only, restore_legacy_table_writes)],
            state_operations=[migrations.DeleteModel(name="DocumentIntelligenceResource")],
        )
    ]
