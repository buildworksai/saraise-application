"""Install PostgreSQL guards for immutable evidence and transition history."""

from django.db import migrations

APPEND_ONLY_TABLES = (
    "document_intelligence_extraction_pages",
    "document_intelligence_classification_scores",
    "document_intelligence_configuration_versions",
    "document_intelligence_configuration_audits",
)


def install_guards(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION document_intelligence_reject_evidence_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'immutable document-intelligence evidence cannot be modified'
                USING ERRCODE = 'integrity_constraint_violation';
        END;
        $$;
        """)
    for table in APPEND_ONLY_TABLES:
        schema_editor.execute(f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION document_intelligence_reject_evidence_mutation();
            """)
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION document_intelligence_guard_terminal_history()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'document_intelligence_extractions'
               AND OLD.status IN ('completed', 'needs_review')
               AND NEW.transition_history IS DISTINCT FROM OLD.transition_history THEN
                RAISE EXCEPTION 'completed extraction transition evidence is immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF TG_TABLE_NAME = 'document_intelligence_classifications'
               AND OLD.status = 'completed'
               AND NEW.transition_history IS DISTINCT FROM OLD.transition_history THEN
                RAISE EXCEPTION 'completed classification transition evidence is immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER document_intelligence_extraction_history_immutable
        BEFORE UPDATE ON document_intelligence_extractions
        FOR EACH ROW EXECUTE FUNCTION document_intelligence_guard_terminal_history();
        CREATE TRIGGER document_intelligence_classification_history_immutable
        BEFORE UPDATE ON document_intelligence_classifications
        FOR EACH ROW EXECUTE FUNCTION document_intelligence_guard_terminal_history();
        """)


def remove_guards(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in APPEND_ONLY_TABLES:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    schema_editor.execute("""
        DROP TRIGGER IF EXISTS document_intelligence_extraction_history_immutable
            ON document_intelligence_extractions;
        DROP TRIGGER IF EXISTS document_intelligence_classification_history_immutable
            ON document_intelligence_classifications;
        DROP FUNCTION IF EXISTS document_intelligence_guard_terminal_history();
        DROP FUNCTION IF EXISTS document_intelligence_reject_evidence_mutation();
        """)


class Migration(migrations.Migration):
    dependencies = [("document_intelligence", "0006_configuration_governance")]
    operations = [migrations.RunPython(install_guards, remove_guards)]
