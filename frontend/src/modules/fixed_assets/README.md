# Fixed Assets frontend

Tenant-isolated financial fixed-asset lifecycle UI for the governed `/api/v2/fixed-assets/` contract.

The module owns its contracts, API service, 15 lazy tenant routes, accessible resource states, asset/category/schedule forms, server-authoritative lifecycle previews, depreciation posting job recovery, and immutable transaction views. Navigation is discovered through `routes.ts`; do not add fixed-asset routes to `App.tsx` or legacy sidebar arrays.

Operational inventory, RFID, maintenance, insurance appraisal, and checkout workflows intentionally remain outside this financial module and belong to the `asset_management` extension boundary.
