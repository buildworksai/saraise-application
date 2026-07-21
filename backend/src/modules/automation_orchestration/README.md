# Automation Orchestration

This foundation module runs tenant-isolated technical dependency graphs. It
owns immutable-versioned definitions, durable schedules, runs, task attempts,
retries, and append-only execution evidence. Human approvals and business
document state machines remain in `workflow_automation`.

## Runtime contract

- Governed API: `/api/v2/automation-orchestration/`
- Durable commands: `automation_orchestration.execute_run`,
  `automation_orchestration.execute_task`, and
  `automation_orchestration.scan_schedules`
- Every service accepts a UUID `tenant_id` first and every query applies
  `.for_tenant(tenant_id)`. PostgreSQL FORCE RLS provides defense in depth.
- Definitions are editable only as drafts. Publication stores the installed
  node contract versions; later edits require cloning a new version.
- A run is idempotent by `(tenant_id, idempotency_key)`. A task-stable operation
  token survives physical retry deliveries so external side effects can be
  deduplicated safely.
- The durable async job and outbox event are committed with run/attempt state.
  Missing handlers, queue failures, cancellation, timeout, and executor contract
  errors are persisted as explicit non-success outcomes.

## Node extension SPI

Industry modules register an immutable `NodeDescriptor` and `NodeExecutor` from
their `AppConfig.ready()` method. The public context contains typed IDs,
validated JSON, correlation/cancellation data, and separate operation/delivery
tokens. It contains no ORM object. Executors return only `NodeExecutionResult`;
they cannot mutate orchestration state.

Registration collisions fail. Replacement is restricted to explicit debug/test
runs. Published graphs pin the descriptor SPI/module/executor version and schema
fingerprint so a module upgrade cannot silently change an immutable workflow.

Core open source ships a real `core.passthrough` node. Paid descriptors remain
subject to the same validation, tenancy, policy, entitlement, quota, retry,
cancellation, audit, and observability machinery.

## Failure and security behavior

The module uses normal CSRF-enforcing Django sessions and fail-closed access
metadata per action. Cross-tenant object identifiers resolve to 404. Secret-like
configuration is rejected; arbitrary scripts/import paths are unsupported.
Readiness returns 503 when the database, durable handlers, outbox freshness,
schedule scanner, or workflow adapter is unavailable, without exposing tenant
counts, URLs, payloads, or raw exceptions.
