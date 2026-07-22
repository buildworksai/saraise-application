# Bank Reconciliation backend

This module implements tenant-isolated bank accounts, durable statement import,
transparent deterministic matching, complex allocations, reconciliation review,
certification, and exportable financial evidence under `/api/v2/bank-reconciliation/`.

The core file workflow supports CSV, OFX, QIF, BAI2, MT940, and CAMT.053 without
a proprietary provider. Parser and candidate-provider registries are stable
extension points; optional ledger and adjustment integrations use tenant-first
protocols and ordinary UUID references, never cross-module ORM imports.

## Support contracts

- `adapters.get_parser(format_key)` resolves a built-in or registered statement
  parser and fails explicitly when unavailable.
- `matching.get_candidate_provider("core")` resolves the transparent scorer.
  Every proposal includes amount, normalized-reference, date-distance, and
  counterparty factors.
- `tasks` registers `bank_reconciliation.import_statement` and
  `bank_reconciliation.generate_candidates` with the durable async-job registry.
- `state_machines` registers audited import and reconciliation lifecycle graphs.
- `events.publish_domain_event(...)` writes allowlisted version-1 envelopes to
  the transactional outbox in the caller's transaction.
- `filters` exposes strict FilterSet-compatible collection query boundaries.
- `health.get_module_health()` reports sanitized readiness for database/RLS,
  parsers, state machines, async jobs, outbox, candidate matching, and the
  optional ledger gateway.

Extensions must use stable registration keys, return the published immutable
DTOs, retain bounded provenance, and fail closed when entitlement, readiness, or
output validation fails. They must not remove the core file workflow.

## Validation

Run focused backend checks from `backend/`:

```bash
python -m compileall -q src/modules/bank_reconciliation
pytest src/modules/bank_reconciliation/tests -q
```
