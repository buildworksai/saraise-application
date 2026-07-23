"""Force typed PostgreSQL RLS and relational tenant integrity."""

from django.db import migrations

TABLES = (
    "notifications_templates", "notifications_template_versions",
    "notifications_notifications", "notifications_deliveries",
    "notifications_delivery_attempts", "notifications_preferences",
    "notifications_endpoints", "notifications_configurations",
    "notifications_configuration_versions", "notifications_configuration_audits",
)


def apply_security(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"SELECT saraise_enable_rls('{table}'::REGCLASS)")
    schema_editor.execute(r"""
        CREATE OR REPLACE FUNCTION notifications_same_tenant_fk()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE related_tenant UUID; related_id UUID;
        BEGIN
          related_id := NULLIF(to_jsonb(NEW)->>TG_ARGV[1], '')::UUID;
          IF related_id IS NULL THEN RETURN NEW; END IF;
          EXECUTE format('SELECT tenant_id FROM %I WHERE id = $1', TG_ARGV[0])
            INTO related_tenant USING related_id;
          IF related_tenant IS NULL OR related_tenant <> NEW.tenant_id THEN
            RAISE EXCEPTION 'cross-tenant relationship rejected' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
    """)
    relationships = (
        ("notifications_template_versions", "notifications_templates", "template_id"),
        ("notifications_templates", "notifications_template_versions", "active_version_id"),
        ("notifications_deliveries", "notifications_template_versions", "template_version_id"),
        ("notifications_deliveries", "async_jobs", "job_id"),
        ("notifications_notifications", "notifications_deliveries", "delivery_id"),
        ("notifications_delivery_attempts", "notifications_deliveries", "delivery_id"),
        ("notifications_configuration_versions", "notifications_configurations", "configuration_id"),
        ("notifications_configuration_audits", "notifications_configurations", "configuration_id"),
        ("notifications_configuration_audits", "notifications_configuration_versions", "version_id"),
    )
    for index, (table, related, column) in enumerate(relationships):
        schema_editor.execute(
            f'CREATE TRIGGER notifications_tenant_fk_{index} BEFORE INSERT OR UPDATE ON "{table}" '
            f"FOR EACH ROW EXECUTE FUNCTION notifications_same_tenant_fk('{related}', '{column}')"
        )
    schema_editor.execute(r"""
        CREATE OR REPLACE FUNCTION notifications_active_version_owner()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE owner_id UUID;
        BEGIN
          IF NEW.active_version_id IS NULL THEN RETURN NEW; END IF;
          SELECT template_id INTO owner_id FROM notifications_template_versions
           WHERE id = NEW.active_version_id AND tenant_id = NEW.tenant_id;
          IF owner_id IS DISTINCT FROM NEW.id THEN
            RAISE EXCEPTION 'active version does not belong to template' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER notifications_active_version_owner_trg
          BEFORE INSERT OR UPDATE ON notifications_templates
          FOR EACH ROW EXECUTE FUNCTION notifications_active_version_owner();
    """)


def remove_security(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS notifications_active_version_owner_trg ON notifications_templates")
    schema_editor.execute("DROP FUNCTION IF EXISTS notifications_active_version_owner()")
    relationships = (
        "notifications_template_versions", "notifications_templates", "notifications_deliveries",
        "notifications_deliveries", "notifications_notifications", "notifications_delivery_attempts",
        "notifications_configuration_versions", "notifications_configuration_audits",
        "notifications_configuration_audits",
    )
    for index, table in reversed(tuple(enumerate(relationships))):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS notifications_tenant_fk_{index} ON "{table}"')
    schema_editor.execute("DROP FUNCTION IF EXISTS notifications_same_tenant_fk()")
    for table in reversed(TABLES):
        schema_editor.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial_notifications_v2"),
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("async_jobs", "0001_initial"),
    ]
    operations = [migrations.RunPython(apply_security, remove_security)]
