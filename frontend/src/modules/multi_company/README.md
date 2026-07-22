# Multi-company frontend

The open-source multi-company workspace consumes the governed `/api/v2/multi-company/`
API exclusively. `contracts.ts` owns DTOs and endpoint construction;
`services/multi-company-service.ts` rejects malformed response envelopes and preserves
correlation IDs for support.

`routes.ts` publishes all company, access, transaction, reconciliation, consolidation,
elimination, transfer-pricing, simulator, and configuration pages through the tenant
route registry. Six sidebar destinations are available in development, self-hosted,
and SaaS modes. Contextual pages inherit those destinations and every route supplies a
human-readable browser title.

The UI uses the repository's semantic design tokens and persisted light/dark/system
theme. Financial and destructive commands use accessible impact dialogs; no page uses
browser confirmation. Configuration is versioned, validated server-side, previewable,
auditable, importable/exportable, and rollback-capable.
