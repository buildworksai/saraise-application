# Compliance Risk Management

`compliance_risk_management` is SARAISE's open-source, tenant-safe risk and
compliance domain. It connects risks to controls, control-test history,
regulatory requirements, calendar obligations, and remediation while keeping
configuration and operational history governed.

## API contract

The module is served at `/api/v2/compliance-risk-management/`. All endpoints
use the governed v2 success/error envelope, session authentication with CSRF,
tenant context, and action-specific `RequiresAccess` decisions. Unknown
actions, missing permission metadata, and cross-tenant identifiers fail
closed.

The permission catalog and action declarations live in `permissions.py` and
must remain identical to `manifest.yaml`. Query filtering and ordering are
strictly allow-listed in `filters.py`; unsupported query parameters are errors,
not ignored hints.

## Configuration

Risk scales, score thresholds, review and acceptance limits, reminder
defaults, overdue processing, and feature rollout are tenant/environment
configuration. Publication creates an immutable version. Preview, optimistic
version checks, history, rollback-as-a-new-version, and versioned JSON
import/export all use the same service and API paths as the UI.

Do not introduce thresholds or workflow rules as source literals. New
namespaced configuration fragments must be registered and validated through
the public configuration extension surface.

## Durable operations

`jobs.py` registers these commands with the foundation async-job registry:

- `compliance_risk.mark_calendar_overdue`
- `compliance_risk.mark_remediation_overdue`
- `compliance_risk.dispatch_reminders`
- `compliance_risk.generate_recurring_control_tests`

Submission persists the job and outbox request atomically. Handlers require a
tenant, actor, correlation ID, job ID, deterministic `as_of` date, and
idempotency identity. Delivery, retry, timeout, cancellation, and terminal
outcomes are recorded by the durable-job foundation.

## Events and extensions

Domain mutations write allow-listed, versioned events through `events.py` in
the mutation transaction. Event payloads contain operational identifiers and
state only—never descriptions, findings, mitigation text, evidence, personal
data, credentials, or raw dependency responses.

Paid modules extend the core through public services, typed adapters, namespaced
configuration fragments, and versioned events such as `risk.created.v1`,
`risk.level_changed.v1`, `control_test.completed.v1`,
`requirement.status_changed.v1`, and `remediation.overdue.v1`. Extensions must
not import private model internals or fork core tables.

## Optional integrations

`integrations.py` provides typed adapters for workflow automation,
notifications, audit projection, DMS, and reporting projections. Adapters use
the foundation resilient HTTP client, which enforces destination allow-lists,
SSRF protection, explicit timeouts, bounded retry/backoff, correlation
propagation, and named circuit breakers.

An unconfigured or unavailable optional dependency is reported as unavailable;
the module never fabricates delivery. Core risk CRUD and scoring remain
available. DMS verification fails closed whenever evidence is supplied and the
document/version/tenant/checksum cannot be verified.

## Health

- `/health/live/` checks process responsiveness only.
- `/health/ready/` verifies the domain schema, forced PostgreSQL RLS metadata,
  bounded database access, durable outbox availability, and configured
  integration circuit state.

Required database/outbox failure returns 503. Optional dependency failure
returns 200 with `degraded`. Responses contain stable component codes and no
row counts, credentials, raw exceptions, or internal response bodies.

## Verification

From `backend/`, run the module suite with the repository-provided interpreter:

```bash
DJANGO_USE_SQLITE_FOR_TESTS=1 SARAISE_MODE=development SECRET_KEY=test-only-secret LOG_LEVEL=CRITICAL \
  /Users/raghunath/code/saraise-application/.venv/bin/python -m pytest \
  src/modules/compliance_risk_management/ -q --no-header -p no:cacheprovider
```

PostgreSQL migration/RLS verification additionally requires the repository's
PostgreSQL 17 test environment. Mutation testing is not currently wired and no
mutation score should be claimed.
