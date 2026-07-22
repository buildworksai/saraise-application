# Human Resources v2 migration runbook

Apply migrations in order: `0001_initial`, `0002_expand_and_backfill`,
`0003_constraints_and_indexes`, then `0004_enable_rls`. The expand migration
adds nullable relationship state first, validates existing references and
normalizes known employment-type aliases before the contract migration adds
the final checks and partial uniqueness constraints.

Legacy leave requests require explicit allocation input. `0002` deliberately
aborts when any legacy request exists because entitlement, period, and consumed
amount cannot be inferred honestly. Import reviewed `LeaveBalance` allocations
and map requests in a deployment-specific data migration before applying this
sequence; never bypass the preflight or synthesize entitlement.

Graph writes serialize hierarchy/reporting-line reads, balance creation locks
the employee, and balance/request mutations lock affected rows in deterministic
order. Keep application writers drained during expand/contract deployment so a
v1 writer cannot recreate a relationship after preflight and before constraints.

Validate each release on PostgreSQL 17 with `MigrationExecutor`: execute the
full forward/reverse/forward sequence (`0004` to `0001` to `0004`). RLS
enforcement tests must use a
dedicated role created with `NOSUPERUSER NOBYPASSRLS`; table owners and
superusers do not provide valid isolation evidence. Verify every HR table has
RLS enabled, forced, and a `tenant_isolation_<table>` policy.

Before rollback, export all v2 leave allocations, transition histories, audit
ownership, cancellation/rejection metadata, attendance source/notes, and
manager relationships. The migration is mechanically reversible, including a
deterministic UUID5 compatibility mapping for non-UUID approval actors, but v1
has nowhere to retain these v2 facts. Rollback without that export is a
deliberate destructive data-loss operation.
