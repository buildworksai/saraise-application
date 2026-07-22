# Multi-Company

Multi-Company is the open-source, tenant-isolated control plane for registering
legal entities and operating intercompany accounting. Version 2 adds dual-side
approval, durable journal posting, reconciliation, consolidation, elimination,
transfer pricing, and versioned runtime configuration. Industry modules extend
these capabilities through `multi-company-spi-v1`; the core paths remain usable
without a paid module.

## Domain and invariants

- `Company` forms a cycle-safe hierarchy and can be deactivated without losing
  history. Codes are unique within a tenant and normalized to uppercase.
- `CompanyAccessGrant` adds company scope after the module-level access decision.
- `IntercompanyTransaction` uses guarded transitions: draft, approval, posting,
  posted, disputed, eliminated, cancelled, and expired states. Posting records a
  durable job before returning HTTP 202 and never fabricates ledger evidence.
- `IntercompanyApproval` and `EliminationEntry` are immutable evidence.
- `ConsolidationRun` persists the reconciled snapshot used for approval and
  publication. Generated and manual eliminations remain traceable.
- `TransferPricingRule` is versioned; historical transactions retain the applied
  rule snapshot.
- `MultiCompanyConfigurationVersion` is tenant- and environment-specific. Drafts
  can be validated and previewed; activation and rollback create immutable audit
  evidence with actor and correlation identifiers.

Every tenant-owned table has UUID ownership, explicit tenant scoping, PostgreSQL
RLS, and tenant-qualified indexes. Every mutation is performed by `services.py`.
Controllers never call `serializer.save()` for v2 domain writes.

## APIs

The governed API is mounted at `/api/v2/multi-company/`. Successful JSON uses
`{"data": ..., "meta": {"correlation_id": ..., "timestamp": ...}}`; lists add
bounded page metadata (25 by default, 100 maximum). Session authentication keeps
DRF CSRF enforcement, and action metadata is deny-by-default.

Resources:

- `companies/`, `company-access/`, `transactions/`, and `reconciliation/`
- `consolidation-runs/`, nested `eliminations/` and `report/`, and `eliminations/`
- `transfer-pricing-rules/`, `transfer-pricing/calculate/`, and `transfer-pricing/preview/`
- `configuration/versions/`, `configuration/export/`, and `configuration/import/`
- `jobs/{id}/` and `health/`

The deprecated `/api/v1/multi-company/companies/` response shape remains during
the sunset period. Its writes call `CompanyRegistryService`; every response has
`Deprecation`, `Sunset`, and successor `Link` headers. No new capability is added
to v1.

## State machines and failure behavior

Transaction and consolidation transitions are defined in `state_machines.py`.
Replayable commands require transition or idempotency keys and use row locking.
Optimistic writes require `expected_version`. Cross-tenant identifiers resolve to
404 without existence disclosure.

Ledger, exchange-rate, workflow, notification, and report dependencies enter only
through protocols in `integrations.py`. A missing required ledger/rate adapter,
timeout, open circuit, malformed response, rejected journal, or incomplete dual
post produces stable failure evidence and an explicit unavailable response. A
partial post is compensated; it is never reported as success. Optional notification
failure degrades to durable retry evidence.

Readiness checks database access, tenant/RLS context, migrations, job/outbox
persistence, handler registration, stale jobs, required providers, and circuit
states. It returns HTTP 503 for critical unavailability and never exposes raw
exceptions or tenant data.

## Runtime configuration

The versioned settings document controls expiry, approval sides, amount limits,
translation and pricing allow-lists, consolidation overlap, feature rollout,
extension enablement, notification policy, job retry/timeout limits, rounding,
and stale-job readiness bounds. `MultiCompanyConfigurationService` validates the
versioned schema server-side. Import creates a draft and never activates it.

## Extension interface

`extensions.py` publishes immutable DTO contracts for consolidation contributors,
elimination providers, pricing methods, company validators, transaction enrichers,
and company detail panels. Registration keys are namespaced and collision-failing.
Provider execution requires manifest dependency, entitlement, feature enablement,
and an access decision; provider failures cannot mutate core financial state.

## Migrations and verification

Do not edit `0001_initial.py`. Additive migrations backfill legacy legal names,
normalized codes, configured currency, and audit fields before enforcing checks;
then create the domain tables and force PostgreSQL RLS. Migration verification must
run forward, reverse to `0001`, and forward again on PostgreSQL 17.

Focused module tests in this worktree:

```bash
cd backend
DJANGO_USE_SQLITE_FOR_TESTS=1 SARAISE_MODE=development SECRET_KEY=test-only-secret LOG_LEVEL=CRITICAL \
  /Users/raghunath/code/saraise-application/.venv/bin/python -m pytest \
  src/modules/multi_company/ -q --no-header -p no:cacheprovider
```

SQLite is useful for the focused suite but cannot prove PostgreSQL RLS or the
forward/reverse migration contract. Those gates require PostgreSQL 17.
