# Asset Management frontend

Production tenant UI for the asset register and append-only depreciation history.

The module provides:

- responsive asset search, filters, ordering, and pagination;
- accessible create, detail, and edit workflows with client and server validation;
- server-controlled current values and residual-value safeguards;
- explicit depreciation calculation with immutable history; and
- module-owned route descriptors consumed by the tenant route/sidebar registry.

`contracts.ts` owns all public types and API endpoints. `services/asset-service.ts`
validates direct DRF responses and governed envelopes, and rejects malformed
payloads instead of rendering fabricated empty states.
