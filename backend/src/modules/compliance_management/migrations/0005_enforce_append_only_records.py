"""Install database-level append-only enforcement for immutable records."""

from django.db import migrations


APPEND_ONLY_TABLES = (
    "compliance_policy_versions",
    "compliance_assessments",
    "compliance_activity",
)
FUNCTION_NAME = "compliance_reject_append_only_mutation"


def install_triggers(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    quoted_function = schema_editor.quote_name(FUNCTION_NAME)
    schema_editor.execute(
        f"""
        CREATE FUNCTION {quoted_function}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'append-only compliance record cannot be %', TG_OP
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    for table in APPEND_ONLY_TABLES:
        trigger = schema_editor.quote_name(f"{table}_append_only"[:63])
        quoted_table = schema_editor.quote_name(table)
        schema_editor.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {quoted_table} "
            f"FOR EACH ROW EXECUTE FUNCTION {quoted_function}();"
        )


def remove_triggers(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in reversed(APPEND_ONLY_TABLES):
        trigger = schema_editor.quote_name(f"{table}_append_only"[:63])
        quoted_table = schema_editor.quote_name(table)
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {quoted_table};")
    quoted_function = schema_editor.quote_name(FUNCTION_NAME)
    schema_editor.execute(f"DROP FUNCTION IF EXISTS {quoted_function}();")


class Migration(migrations.Migration):
    dependencies = [("compliance_management", "0004_enforce_compliance_rls")]
    operations = [migrations.RunPython(install_triggers, remove_triggers)]
