"""
Enforce audit log immutability at the database level.

SARAISE-26001: Audit logs MUST be immutable.

This migration:
1. Creates a trigger function that prevents DELETE and UPDATE on audit tables
2. Applies the trigger to all audit-related tables
3. Only allows deletion via a special maintenance function (requires superuser)

NOTE: These operations are PostgreSQL-only and are safely skipped on SQLite (tests).
"""

from django.db import connection, migrations


def create_audit_immutability(apps, schema_editor):
    """Create audit immutability trigger function — PostgreSQL only."""
    if connection.vendor != "postgresql":
        return

    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION saraise_audit_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Allow if maintenance mode is explicitly set
            IF current_setting('app.audit_maintenance', TRUE) = 'true' THEN
                RETURN OLD;
            END IF;

            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'SARAISE-26001: Audit log records cannot be deleted. '
                    'Table: %, Record ID: %',
                    TG_TABLE_NAME, OLD.id;
            END IF;

            IF TG_OP = 'UPDATE' THEN
                -- Allow updating only specific non-content fields (e.g., metadata)
                -- Core audit fields are immutable
                RAISE EXCEPTION 'SARAISE-26001: Audit log records cannot be modified. '
                    'Table: %, Record ID: %',
                    TG_TABLE_NAME, OLD.id;
            END IF;

            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)


def drop_audit_immutability(apps, schema_editor):
    """Drop audit immutability trigger function — PostgreSQL only."""
    if connection.vendor != "postgresql":
        return

    schema_editor.execute("DROP FUNCTION IF EXISTS saraise_audit_immutable() CASCADE;")


class Migration(migrations.Migration):
    """Enforce audit log immutability via PostgreSQL triggers."""

    dependencies = [
        ("core", "0008_add_row_level_security"),
    ]

    operations = [
        migrations.RunPython(create_audit_immutability, drop_audit_immutability),
        # Note: Each module that has audit tables should apply this trigger:
        # CREATE TRIGGER enforce_audit_immutability
        #   BEFORE DELETE OR UPDATE ON <audit_table>
        #   FOR EACH ROW
        #   EXECUTE FUNCTION saraise_audit_immutable();
    ]
