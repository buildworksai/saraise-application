"""Apply the hardened activity-evidence guard to already-migrated databases."""

from django.db import migrations

INSTALL_HARDENED_GUARD = r"""
CREATE OR REPLACE FUNCTION crm_protect_activity_evidence() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    closed_parent BOOLEAN := FALSE;
BEGIN
    IF OLD.related_to_type = 'Opportunity' THEN
        SELECT EXISTS (
            SELECT 1 FROM crm_opportunities
             WHERE id = OLD.related_to_id AND tenant_id = OLD.tenant_id AND status IN ('won', 'lost')
        ) INTO closed_parent;
    END IF;
    IF OLD.completed OR closed_parent THEN
        RAISE EXCEPTION 'completed or closed-opportunity activity is immutable' USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS crm_activity_immutable_guard ON crm_activities;
CREATE TRIGGER crm_activity_immutable_guard
BEFORE UPDATE OR DELETE ON crm_activities
FOR EACH ROW EXECUTE FUNCTION crm_protect_activity_evidence();
"""

RESTORE_PRIOR_GUARD = r"""
CREATE OR REPLACE FUNCTION crm_protect_activity_evidence() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    closed_parent BOOLEAN := FALSE;
    only_soft_delete BOOLEAN;
BEGIN
    IF OLD.related_to_type = 'Opportunity' THEN
        SELECT EXISTS (
            SELECT 1 FROM crm_opportunities
             WHERE id = OLD.related_to_id AND tenant_id = OLD.tenant_id AND status IN ('won', 'lost')
        ) INTO closed_parent;
    END IF;
    IF NOT OLD.completed AND NOT closed_parent THEN
        RETURN NEW;
    END IF;
    only_soft_delete := NOT OLD.is_deleted AND NEW.is_deleted AND NEW.deleted_at IS NOT NULL
        AND (to_jsonb(NEW) - 'is_deleted' - 'deleted_at' - 'updated_at' - 'updated_by' - 'version')
          = (to_jsonb(OLD) - 'is_deleted' - 'deleted_at' - 'updated_at' - 'updated_by' - 'version');
    IF only_soft_delete THEN
        RETURN NEW;
    END IF;
    IF to_jsonb(NEW) <> to_jsonb(OLD) THEN
        RAISE EXCEPTION 'completed or closed-opportunity activity is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS crm_activity_immutable_guard ON crm_activities;
CREATE TRIGGER crm_activity_immutable_guard
BEFORE UPDATE ON crm_activities
FOR EACH ROW EXECUTE FUNCTION crm_protect_activity_evidence();
"""


def install_hardened_guard(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(INSTALL_HARDENED_GUARD)


def restore_prior_guard(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(RESTORE_PRIOR_GUARD)


class Migration(migrations.Migration):
    dependencies = [("crm", "0009_tenant_configuration")]
    operations = [migrations.RunPython(install_hardened_guard, restore_prior_guard)]
