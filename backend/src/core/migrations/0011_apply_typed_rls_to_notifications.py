"""Install typed tenant RLS and apply it to the core notifications table."""

from django.db import migrations

INSTALL_TYPED_RLS = r"""
DROP FUNCTION IF EXISTS saraise_enable_rls(TEXT);
DROP FUNCTION IF EXISTS saraise_enable_rls(REGCLASS);
DROP FUNCTION IF EXISTS saraise_current_tenant_id();

CREATE FUNCTION saraise_current_tenant_id()
RETURNS UUID
LANGUAGE SQL
STABLE
AS $$
    SELECT NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID
$$;

CREATE FUNCTION saraise_enable_rls(target_table REGCLASS)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    target_name TEXT;
    tenant_type REGTYPE;
BEGIN
    SELECT relation.relname
      INTO target_name
      FROM pg_class AS relation
     WHERE relation.oid = target_table;

    SELECT attribute.atttypid::REGTYPE
      INTO tenant_type
      FROM pg_attribute AS attribute
     WHERE attribute.attrelid = target_table
       AND attribute.attname = 'tenant_id'
       AND NOT attribute.attisdropped;

    IF tenant_type IS NULL THEN
        RAISE EXCEPTION 'RLS target % has no tenant_id column', target_table;
    END IF;
    IF tenant_type <> 'uuid'::REGTYPE THEN
        RAISE EXCEPTION 'RLS target %.tenant_id must be UUID, found %', target_table, tenant_type;
    END IF;

    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', target_table);
    EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', target_table);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %s', 'tenant_isolation_' || target_name, target_table);
    EXECUTE format(
        'CREATE POLICY %I ON %s USING (tenant_id = saraise_current_tenant_id()) '
        'WITH CHECK (tenant_id = saraise_current_tenant_id())',
        'tenant_isolation_' || target_name,
        target_table
    );
END;
$$;

SELECT saraise_enable_rls('notifications'::REGCLASS);
"""


REMOVE_TYPED_RLS = r"""
DROP POLICY IF EXISTS tenant_isolation_notifications ON notifications;
ALTER TABLE notifications NO FORCE ROW LEVEL SECURITY;
ALTER TABLE notifications DISABLE ROW LEVEL SECURITY;
DROP FUNCTION IF EXISTS saraise_enable_rls(REGCLASS);
DROP FUNCTION IF EXISTS saraise_current_tenant_id();

CREATE FUNCTION saraise_current_tenant_id()
RETURNS TEXT
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN current_setting('app.current_tenant_id', TRUE);
END;
$$;

CREATE FUNCTION saraise_enable_rls(table_name TEXT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
        'CREATE POLICY tenant_isolation_%I ON %I USING '
        '(tenant_id = saraise_current_tenant_id()) WITH CHECK '
        '(tenant_id = saraise_current_tenant_id())',
        table_name,
        table_name
    );
    EXECUTE format(
        'CREATE POLICY superuser_bypass_%I ON %I USING '
        '(current_setting(''app.is_superuser'', TRUE) = ''true'')',
        table_name,
        table_name
    );
END;
$$;
"""


def install_typed_rls(apps, schema_editor):
    """Install PostgreSQL-only functions and the notifications policy."""
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(INSTALL_TYPED_RLS)


def remove_typed_rls(apps, schema_editor):
    """Remove the policy and restore the schema left by migration 0008."""
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REMOVE_TYPED_RLS)


class Migration(migrations.Migration):
    """Apply the first real RLS policy after the audit immutability gate."""

    dependencies = [("core", "0010_access_entitlement_quota")]

    operations = [migrations.RunPython(install_typed_rls, remove_typed_rls)]
