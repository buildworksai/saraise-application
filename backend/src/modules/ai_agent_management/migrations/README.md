# AI Agent Management migrations

`0001_initial.py` and `0002_approvalrequest_ai_approval_tenant__15d886_idx.py`
are immutable applied history. They created the original 21 runtime tables with
string UUID columns. Never edit them; their imported `generate_uuid` shims are
part of the historical migration ABI.

The production conversion is an expand/backfill/contract chain:

1. `0003_expand_foundation_schema.py` adds canonical lifecycle, correlation,
   async-job, evidence, and secret-envelope fields. It deterministically
   backfills existing rows, preserves ordered audit links, and aborts on
   malformed UUIDs or incomplete egress evidence.
2. `0004_backfill_uuid_and_state.py` validates that every UUID identity and
   deterministic execution/schedule/invocation key was converted.
3. `0005_switch_uuid_relations.py` makes the execution async-job UUID required
   and unique after the data validation boundary.
4. `0006_access_quota_projection.py` projects legacy quotas into
   `core.access.Quota` without overwriting conflicting canonical authority.
5. `0007_constraints_and_indexes.py` completes financial/numeric checks and
   validates tenant-leading query indexes.
6. `0008_tenant_guards_and_rls.py` enables and forces PostgreSQL RLS on every
   module table and installs same-tenant triggers for every tenant relation.
7. `0009_contract_legacy_columns.py` removes compatibility fields from Django
   state. Physical columns remain nullable during the rollback window and are
   repopulated before reverse migration restores the legacy constraints.

Every data or security operation has an explicit reverse. Migration acceptance
must cover `0002 -> 0009 -> 0002 -> 0009`, malformed UUID rejection, evidence
identity checksums, quota reconstruction, and PostgreSQL RLS using the non-owner
application role. SQLite is useful for ORM portability but is not RLS evidence.

Useful validation commands:

```bash
cd backend
python manage.py makemigrations ai_agent_management --check --dry-run
python manage.py migrate ai_agent_management
pytest src/modules/ai_agent_management/tests/test_migrations.py -v
```
