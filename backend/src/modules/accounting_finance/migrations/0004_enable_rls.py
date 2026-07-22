"""Enable forced tenant RLS and tenant-qualified relationship guards."""

from django.db import migrations


TABLES = (
    "accounting_accounts",
    "accounting_posting_periods",
    "accounting_journal_entries",
    "accounting_journal_lines",
    "accounting_ap_invoices",
    "accounting_ap_invoice_lines",
    "accounting_ar_invoices",
    "accounting_ar_invoice_lines",
    "accounting_payments",
)

RELATIONSHIPS = (
    ("accounting_accounts", "parent_account_id", "accounting_accounts"),
    ("accounting_journal_entries", "posting_period_id", "accounting_posting_periods"),
    ("accounting_journal_entries", "reversed_entry_id", "accounting_journal_entries"),
    ("accounting_journal_lines", "journal_entry_id", "accounting_journal_entries"),
    ("accounting_journal_lines", "account_id", "accounting_accounts"),
    ("accounting_ap_invoices", "journal_entry_id", "accounting_journal_entries"),
    ("accounting_ap_invoice_lines", "invoice_id", "accounting_ap_invoices"),
    ("accounting_ap_invoice_lines", "account_id", "accounting_accounts"),
    ("accounting_ar_invoices", "journal_entry_id", "accounting_journal_entries"),
    ("accounting_ar_invoice_lines", "invoice_id", "accounting_ar_invoices"),
    ("accounting_ar_invoice_lines", "account_id", "accounting_accounts"),
    ("accounting_payments", "ap_invoice_id", "accounting_ap_invoices"),
    ("accounting_payments", "ar_invoice_id", "accounting_ar_invoices"),
)


def _trigger_name(child: str, column: str) -> str:
    return f"acct_tenant_{child.removeprefix('accounting_')[:16]}_{column[:18]}"


def enable_security(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table}")
        schema_editor.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted_table} FORCE ROW LEVEL SECURITY")
        schema_editor.execute(
            f"CREATE POLICY {quoted_policy} ON {quoted_table} FOR ALL "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )

    schema_editor.execute(
        """
        CREATE FUNCTION accounting_require_same_tenant()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        DECLARE
            related_id UUID;
            related_tenant UUID;
        BEGIN
            related_id := (to_jsonb(NEW) ->> TG_ARGV[0])::UUID;
            IF related_id IS NULL THEN
                RETURN NEW;
            END IF;
            EXECUTE format('SELECT tenant_id FROM %I WHERE id = $1', TG_ARGV[1])
                INTO related_tenant USING related_id;
            IF related_tenant IS NULL OR related_tenant <> NEW.tenant_id THEN
                RAISE EXCEPTION 'cross-tenant accounting relationship rejected'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for child, column, parent in RELATIONSHIPS:
        trigger = schema_editor.quote_name(_trigger_name(child, column))
        schema_editor.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER INSERT OR UPDATE OF "
            f"{schema_editor.quote_name('tenant_id')}, {schema_editor.quote_name(column)} "
            f"ON {schema_editor.quote_name(child)} DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW "
            f"EXECUTE FUNCTION accounting_require_same_tenant('{column}', '{parent}')"
        )


def disable_security(apps, schema_editor) -> None:
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for child, column, _parent in reversed(RELATIONSHIPS):
        schema_editor.execute(
            f"DROP TRIGGER IF EXISTS {schema_editor.quote_name(_trigger_name(child, column))} "
            f"ON {schema_editor.quote_name(child)}"
        )
    schema_editor.execute("DROP FUNCTION IF EXISTS accounting_require_same_tenant()")
    for table in reversed(TABLES):
        quoted_table = schema_editor.quote_name(table)
        quoted_policy = schema_editor.quote_name(f"tenant_isolation_{table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS {quoted_policy} ON {quoted_table}")
        schema_editor.execute(f"ALTER TABLE {quoted_table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {quoted_table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("accounting_finance", "0003_v2_constraints_and_indexes"),
    ]

    operations = [migrations.RunPython(enable_security, disable_security)]
