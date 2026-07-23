"""Enforce CRM logical references and immutable activity evidence in PostgreSQL."""

from django.db import migrations

INSTALL_GUARDS = r"""
CREATE FUNCTION crm_require_account_parent() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    ancestor_count INTEGER;
    descendant_depth INTEGER;
BEGIN
    IF NEW.parent_account_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.parent_account_id = NEW.id THEN
        RAISE EXCEPTION 'account cannot be its own parent' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM crm_accounts
         WHERE id = NEW.parent_account_id AND tenant_id = NEW.tenant_id AND NOT is_deleted
    ) THEN
        RAISE EXCEPTION 'active same-tenant parent account required' USING ERRCODE = '23514';
    END IF;
    WITH RECURSIVE ancestors AS (
        SELECT id, parent_account_id, 1 AS depth
          FROM crm_accounts WHERE id = NEW.parent_account_id AND tenant_id = NEW.tenant_id
        UNION ALL
        SELECT parent.id, parent.parent_account_id, child.depth + 1
          FROM crm_accounts AS parent JOIN ancestors AS child ON parent.id = child.parent_account_id
         WHERE parent.tenant_id = NEW.tenant_id AND child.depth < 4
    )
    SELECT COUNT(*) INTO ancestor_count FROM ancestors;
    WITH RECURSIVE descendants AS (
        SELECT id, 1 AS depth FROM crm_accounts
         WHERE parent_account_id = NEW.id AND tenant_id = NEW.tenant_id AND NOT is_deleted
        UNION ALL
        SELECT child.id, parent.depth + 1
          FROM crm_accounts AS child JOIN descendants AS parent ON child.parent_account_id = parent.id
         WHERE child.tenant_id = NEW.tenant_id AND NOT child.is_deleted AND parent.depth < 4
    )
    SELECT COALESCE(MAX(depth), 0) INTO descendant_depth FROM descendants;
    IF ancestor_count + descendant_depth + 1 > 3 THEN
        RAISE EXCEPTION 'account hierarchy cannot exceed three nodes' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_account_id FROM crm_accounts
             WHERE id = NEW.parent_account_id AND tenant_id = NEW.tenant_id
            UNION ALL
            SELECT parent.id, parent.parent_account_id
              FROM crm_accounts AS parent JOIN ancestors AS child ON parent.id = child.parent_account_id
             WHERE parent.tenant_id = NEW.tenant_id
        ) SELECT 1 FROM ancestors WHERE id = NEW.id
    ) THEN
        RAISE EXCEPTION 'account hierarchy must be acyclic' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION crm_require_contact_account() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM crm_accounts
         WHERE id = NEW.account_id AND tenant_id = NEW.tenant_id AND NOT is_deleted
    ) THEN
        RAISE EXCEPTION 'active same-tenant contact account required' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION crm_require_opportunity_references() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM crm_accounts
         WHERE id = NEW.account_id AND tenant_id = NEW.tenant_id AND NOT is_deleted
    ) THEN
        RAISE EXCEPTION 'active same-tenant opportunity account required' USING ERRCODE = '23514';
    END IF;
    IF NEW.primary_contact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM crm_contacts
         WHERE id = NEW.primary_contact_id AND tenant_id = NEW.tenant_id
           AND account_id = NEW.account_id AND NOT is_deleted
    ) THEN
        RAISE EXCEPTION 'active same-account opportunity contact required' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND NEW.close_date < CURRENT_DATE THEN
        RAISE EXCEPTION 'opportunity close date cannot be in the past at creation' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION crm_require_activity_reference() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    target_table REGCLASS;
    found BOOLEAN;
BEGIN
    target_table := CASE NEW.related_to_type
        WHEN 'Lead' THEN 'crm_leads'::REGCLASS
        WHEN 'Contact' THEN 'crm_contacts'::REGCLASS
        WHEN 'Account' THEN 'crm_accounts'::REGCLASS
        WHEN 'Opportunity' THEN 'crm_opportunities'::REGCLASS
        ELSE NULL
    END;
    IF target_table IS NULL THEN
        RAISE EXCEPTION 'unsupported activity relation type' USING ERRCODE = '23514';
    END IF;
    EXECUTE format('SELECT EXISTS (SELECT 1 FROM %s WHERE id = $1 AND tenant_id = $2 AND NOT is_deleted)', target_table)
       INTO found USING NEW.related_to_id, NEW.tenant_id;
    IF NOT found THEN
        RAISE EXCEPTION 'active same-tenant activity parent required' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' AND NEW.activity_type = 'task' AND NEW.due_date IS NOT NULL
       AND NEW.due_date <= CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'new task due date must be in the future' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION crm_protect_activity_evidence() RETURNS TRIGGER LANGUAGE plpgsql AS $$
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

CREATE TRIGGER crm_account_parent_guard
BEFORE INSERT OR UPDATE OF tenant_id, parent_account_id ON crm_accounts
FOR EACH ROW EXECUTE FUNCTION crm_require_account_parent();

CREATE TRIGGER crm_contact_account_guard
BEFORE INSERT OR UPDATE OF tenant_id, account_id ON crm_contacts
FOR EACH ROW EXECUTE FUNCTION crm_require_contact_account();

CREATE TRIGGER crm_opportunity_reference_guard
BEFORE INSERT OR UPDATE OF tenant_id, account_id, primary_contact_id ON crm_opportunities
FOR EACH ROW EXECUTE FUNCTION crm_require_opportunity_references();

CREATE TRIGGER crm_activity_reference_guard
BEFORE INSERT OR UPDATE OF tenant_id, related_to_type, related_to_id ON crm_activities
FOR EACH ROW EXECUTE FUNCTION crm_require_activity_reference();

CREATE TRIGGER crm_activity_immutable_guard
BEFORE UPDATE OR DELETE ON crm_activities
FOR EACH ROW EXECUTE FUNCTION crm_protect_activity_evidence();
"""


REMOVE_GUARDS = r"""
DROP TRIGGER IF EXISTS crm_activity_immutable_guard ON crm_activities;
DROP TRIGGER IF EXISTS crm_activity_reference_guard ON crm_activities;
DROP TRIGGER IF EXISTS crm_opportunity_reference_guard ON crm_opportunities;
DROP TRIGGER IF EXISTS crm_contact_account_guard ON crm_contacts;
DROP TRIGGER IF EXISTS crm_account_parent_guard ON crm_accounts;
DROP FUNCTION IF EXISTS crm_protect_activity_evidence();
DROP FUNCTION IF EXISTS crm_require_activity_reference();
DROP FUNCTION IF EXISTS crm_require_opportunity_references();
DROP FUNCTION IF EXISTS crm_require_contact_account();
DROP FUNCTION IF EXISTS crm_require_account_parent();
"""


def install_guards(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(INSTALL_GUARDS)


def remove_guards(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REMOVE_GUARDS)


class Migration(migrations.Migration):
    dependencies = [("crm", "0006_validate_constraints_and_indexes")]
    operations = [migrations.RunPython(install_guards, remove_guards)]
