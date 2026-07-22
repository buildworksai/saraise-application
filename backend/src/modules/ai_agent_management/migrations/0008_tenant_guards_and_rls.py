"""Install fail-closed PostgreSQL RLS and same-tenant FK guards."""

from __future__ import annotations

from django.db import migrations

TABLES = (
    "ai_agents",
    "ai_agent_executions",
    "ai_agent_scheduler_tasks",
    "ai_approval_requests",
    "ai_sod_policies",
    "ai_sod_violations",
    "ai_tools",
    "ai_tool_invocations",
    "ai_egress_rules",
    "ai_egress_requests",
    "ai_secrets",
    "ai_secret_accesses",
    "ai_quota_usage",
    "ai_shard_saturation",
    "ai_kill_switches",
    "ai_token_usage",
    "ai_cost_records",
    "ai_cost_summaries",
    "ai_audit_events",
    "ai_audit_trails",
    "ai_audit_trail_events",
)

# (child table, FK column, parent table). These database guards complement
# ORM validation and protect bulk SQL, workers, and future extension modules.
TENANT_RELATIONS = (
    ("ai_agent_executions", "agent_id", "ai_agents"),
    ("ai_agent_scheduler_tasks", "agent_id", "ai_agents"),
    ("ai_agent_scheduler_tasks", "execution_id", "ai_agent_executions"),
    ("ai_approval_requests", "tool_id", "ai_tools"),
    ("ai_approval_requests", "agent_execution_id", "ai_agent_executions"),
    ("ai_approval_requests", "tool_invocation_id", "ai_tool_invocations"),
    ("ai_sod_violations", "policy_id", "ai_sod_policies"),
    ("ai_sod_violations", "agent_execution_id", "ai_agent_executions"),
    ("ai_sod_violations", "tool_invocation_id", "ai_tool_invocations"),
    ("ai_tool_invocations", "tool_id", "ai_tools"),
    ("ai_tool_invocations", "agent_execution_id", "ai_agent_executions"),
    ("ai_tool_invocations", "approval_request_id", "ai_approval_requests"),
    ("ai_egress_requests", "agent_execution_id", "ai_agent_executions"),
    ("ai_egress_requests", "matched_rule_id", "ai_egress_rules"),
    ("ai_secret_accesses", "secret_id", "ai_secrets"),
    ("ai_secret_accesses", "agent_execution_id", "ai_agent_executions"),
    ("ai_quota_usage", "agent_execution_id", "ai_agent_executions"),
    ("ai_token_usage", "agent_execution_id", "ai_agent_executions"),
    ("ai_cost_records", "agent_execution_id", "ai_agent_executions"),
    ("ai_cost_records", "tool_invocation_id", "ai_tool_invocations"),
    ("ai_audit_events", "agent_execution_id", "ai_agent_executions"),
    ("ai_audit_events", "tool_invocation_id", "ai_tool_invocations"),
    ("ai_audit_events", "approval_request_id", "ai_approval_requests"),
    ("ai_audit_trails", "agent_execution_id", "ai_agent_executions"),
    ("ai_audit_trail_events", "audit_trail_id", "ai_audit_trails"),
    ("ai_audit_trail_events", "audit_event_id", "ai_audit_events"),
)


def _names(child, column):
    stem = f"{child}_{column}".replace("ai_", "", 1)
    return f"ai_tenant_guard_{stem}"[:63], f"ai_tenant_guard_fn_{stem}"[:63]


def install_tenant_security(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    qn = connection.ops.quote_name
    tenant_expression = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    with connection.cursor() as cursor:
        for table in TABLES:
            policy = f"{table}_tenant_isolation"[:63]
            cursor.execute(f"ALTER TABLE {qn(table)} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {qn(table)} FORCE ROW LEVEL SECURITY")
            cursor.execute(f"DROP POLICY IF EXISTS {qn(policy)} ON {qn(table)}")
            cursor.execute(
                f"CREATE POLICY {qn(policy)} ON {qn(table)} "
                f"USING ({tenant_expression}) WITH CHECK ({tenant_expression})"
            )

        for child, column, parent in TENANT_RELATIONS:
            trigger, function = _names(child, column)
            cursor.execute(f"""
                CREATE OR REPLACE FUNCTION {qn(function)}() RETURNS trigger
                LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.{qn(column)} IS NOT NULL AND NOT EXISTS (
                        SELECT 1 FROM {qn(parent)} parent_row
                        WHERE parent_row.id = NEW.{qn(column)}
                          AND parent_row.tenant_id = NEW.tenant_id
                    ) THEN
                        RAISE EXCEPTION 'cross-tenant relation rejected: %.%', TG_TABLE_NAME, '{column}'
                            USING ERRCODE = '23503';
                    END IF;
                    RETURN NEW;
                END;
                $$
                """)
            cursor.execute(f"DROP TRIGGER IF EXISTS {qn(trigger)} ON {qn(child)}")
            cursor.execute(
                f"CREATE TRIGGER {qn(trigger)} BEFORE INSERT OR UPDATE OF {qn(column)}, tenant_id "
                f"ON {qn(child)} FOR EACH ROW EXECUTE FUNCTION {qn(function)}()"
            )


def remove_tenant_security(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    qn = connection.ops.quote_name
    with connection.cursor() as cursor:
        for child, column, _parent in reversed(TENANT_RELATIONS):
            trigger, function = _names(child, column)
            cursor.execute(f"DROP TRIGGER IF EXISTS {qn(trigger)} ON {qn(child)}")
            cursor.execute(f"DROP FUNCTION IF EXISTS {qn(function)}()")
        for table in reversed(TABLES):
            policy = f"{table}_tenant_isolation"[:63]
            cursor.execute(f"DROP POLICY IF EXISTS {qn(policy)} ON {qn(table)}")
            cursor.execute(f"ALTER TABLE {qn(table)} NO FORCE ROW LEVEL SECURITY")
            cursor.execute(f"ALTER TABLE {qn(table)} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [("ai_agent_management", "0007_constraints_and_indexes")]

    operations = [migrations.RunPython(install_tenant_security, remove_tenant_security)]
