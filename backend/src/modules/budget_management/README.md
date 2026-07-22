# Budget Management

Budget Management is the open-source planning and control authority for
tenant-scoped budgets, allocations, approval history, commitments, actuals,
variance analysis, and alerts. Its governed API is exposed only at
`/api/v2/budget-management/`.

## Architecture

- `models.py` owns persistence and constraints; all domain tables use canonical
  tenancy primitives and PostgreSQL forced RLS.
- `services.py` is the only mutation authority. API views validate transport
  input and delegate to `BudgetService`, `BudgetControlService`, or
  `VarianceAlertService`.
- `state_machines.py` owns lifecycle transitions and append-only transition
  recording. Every command requires a tenant and idempotency key.
- `integrations.py` is the extension surface. Optional accounting, workflow,
  and notification capabilities register typed ports without cross-module model
  imports.
- `jobs.py` registers durable, at-least-once-safe workers using the core tenant
  worker context. Success is persisted only after provider or database evidence.
- `health.py` probes database, typed tenant context, RLS, and rollback-safe job
  persistence. Optional adapters are reported as degraded when absent.

## Extension contract

Paid industry modules may implement the public protocols and subscribe to
versioned `budget.*` outbox events. They must not fork these models, mutate
budget status directly, or bypass access control. External HTTP adapters must
use `src.core.resilience.ResilientHttpClient` with allowlisted dependencies,
explicit timeouts, bounded retry/backoff, and provider idempotency keys.

## Monetary and concurrency rules

Amounts enter services as decimal strings or `Decimal` values and are rounded
to two places; binary floats are rejected. Mutable updates require the exact
`expected_updated_at` returned by the API. A stale write raises
`CONCURRENT_UPDATE` (`409`) without overwriting server state.

Missing optional capability never returns fabricated success. Operations that
require it fail with `CAPABILITY_UNAVAILABLE` (`503`), while standalone manual
planning, allocation, availability, and variance calculations remain usable.

See [API.md](API.md) for endpoint and failure semantics.
