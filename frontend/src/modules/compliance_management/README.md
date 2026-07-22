# Compliance Management

The open-source compliance workspace implements the complete manual compliance
loop: frameworks and requirements, policy authoring and publication, coverage
mapping, point-in-time assessments, evidence provenance, configuration
versioning, and immutable activity history.

## Extension surface

Paid industry modules register framework packages through the backend extension
registry. The open-source UI and v2 API consume those packages through the same
import and lifecycle contracts as tenant-authored frameworks; no industry logic
is embedded in this module.

## Frontend contract

- `contracts.ts` is the single source for `/api/v2/compliance-management`
  endpoint constants and payload types.
- `services/compliance-service.ts` enforces governed response envelopes and
  preserves pagination and correlation metadata.
- `routes.ts` exports every lazy route and sidebar entry.
- Every route uses shared loading, empty, failure, access-denied, and unavailable
  states, and sets a human-readable document title.

Configuration editing, preview, activation, rollback, import, and export all use
the tenant-scoped API. The UI is not a privileged configuration path.
