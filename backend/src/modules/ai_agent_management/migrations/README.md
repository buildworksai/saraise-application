# AI Agent Management Module - Migrations

## Overview

This directory contains Django migrations for the AI Agent Management module. All migrations follow SARAISE migration standards and enforce Row-Level Multitenancy.

## Creating Migrations

When Django environment is set up, create migrations using:

```bash
cd backend
python manage.py makemigrations ai_agent_management
python manage.py migrate
```

## Expected Migrations

The following migrations will be created for the 17+ models:

1. **0001_initial.py** - Creates core tables:
   - `ai_agents` (Agent model)
   - `ai_agent_executions` (AgentExecution model)
   - `ai_agent_scheduler_tasks` (AgentSchedulerTask model)

2. **0002_approval_models.py** - Creates approval tables:
   - `ai_approval_requests` (ApprovalRequest model)
   - `ai_sod_policies` (SoDPolicy model)
   - `ai_sod_violations` (SoDViolation model)

3. **0003_quota_models.py** - Creates quota tables:
   - `ai_tenant_quotas` (TenantQuota model)
   - `ai_quota_usage` (QuotaUsage model)
   - `ai_shard_saturation` (ShardSaturation model)
   - `ai_kill_switches` (KillSwitch model)

4. **0004_tool_models.py** - Creates tool tables:
   - `ai_tools` (Tool model)
   - `ai_tool_invocations` (ToolInvocation model)

5. **0005_egress_models.py** - Creates egress tables:
   - `ai_egress_rules` (EgressRule model)
   - `ai_egress_requests` (EgressRequest model)
   - `ai_secrets` (Secret model)
   - `ai_secret_accesses` (SecretAccess model)

6. **0006_audit_models.py** - Creates audit tables:
   - `ai_audit_events` (AuditEvent model)
   - `ai_audit_trails` (AuditTrail model)

7. **0007_token_models.py** - Creates token/cost tables:
   - `ai_token_usage` (TokenUsage model)
   - `ai_cost_records` (CostRecord model)
   - `ai_cost_summaries` (CostSummary model)

## Migration Requirements

All migrations MUST:

1. **Include tenant_id**: All tenant-scoped tables must have `tenant_id` column with proper indexes
2. **Create indexes**: All foreign keys and frequently queried fields must have indexes
3. **Be idempotent**: Migrations must handle concurrent execution safely
4. **Follow Expand/Contract pattern**: See `docs/architecture/migration-playbook.md`
5. **Never modify existing migrations**: Create new migrations for changes

## Critical Tables

The following tables are critical for module operation:
- `ai_agents` - Core agent definitions
- `ai_agent_executions` - Execution tracking
- `ai_approval_requests` - Human approval gates
- `ai_tenant_quotas` - Quota enforcement
- `ai_kill_switches` - Emergency controls

## Indexes

All migrations create comprehensive indexes on:
- `tenant_id` (for Row-Level Multitenancy filtering)
- Foreign keys (for join performance)
- Frequently queried fields (`state`, `status`, `is_active`, `created_at`)
- Composite indexes for common query patterns

## Migration Dependencies

- Base dependency: Core platform migrations
- No cross-module dependencies (this is a Foundation module)

## Verification

After migrations are created, verify:

```bash
# Check migration files
ls -la backend/src/modules/ai_agent_management/migrations/

# Check tables created
python manage.py dbshell
\dt ai_*

# Verify indexes
\d ai_agents
```

## Troubleshooting

If migrations fail:
1. Check `INSTALLED_APPS` includes `'src.modules.ai_agent_management'`
2. Verify database connectivity
3. Check for circular dependencies in models
4. Review migration files for syntax errors
