# Bank reconciliation frontend

This module implements the governed `/api/v2/bank-reconciliation/` workflow for bank-account administration, durable statement imports, manual statements, deterministic matching rules, complex allocation work, certification, and evidence export.

## Routes

The module owns its navigation through `routes.ts`; `tenant-route-registry.ts` discovers it automatically. Sidebar leaves are accounts, statements, reconciliations, matching rules, and import jobs. Create, detail, edit, transaction, import, and workspace pages are contextual children of those leaves.

## Contract and service

`contracts.ts` is the only authority for DTOs, literal state unions, endpoint paths, application paths, permissions, and query-key factories. Monetary values remain fixed decimal strings. `services/bank-reconciliation-service.ts` consumes only the governed v2 envelope, preserves pagination and correlation IDs, uploads files as multipart data, treats HTTP 202 as accepted work, and bounds active-import polling.

The core UI never fabricates ledger candidates or provider results. When no ledger gateway is configured, operators can use the manual verified-balance and tenant-validated ledger-reference path. Extension rules retain their provider key and fail explicitly when the provider is unavailable.

## UX behavior

Every route provides a loading skeleton, recoverable failure state, permission-denied state, empty state where applicable, pending mutation controls, and success feedback. Account identifiers are masked in every read view. Imported transaction source values are read-only. Reconciled/finalized evidence is read-only and exportable.

The workspace groups bank lines by match state, exposes deterministic score factors, supports manual one-to-one and many-to-one allocation groups, and keeps the balance proof and certification guards visible. Arithmetic previews use integer fixed-point operations instead of floating point.

## Development

```bash
npm run typecheck
npm run lint
npm run test -- bank_reconciliation
npm run build
```

The backend must be mounted at `/api/v2/bank-reconciliation/` with strict session/CSRF authentication. Do not add v1 response fallbacks or direct route declarations in `App.tsx`.
