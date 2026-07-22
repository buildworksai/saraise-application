# Asset Management backend

This module owns the tenant-safe operational asset register and an immutable
depreciation-preview history. `fixed_assets` remains the financial authority
for capitalization, posting, transfer, impairment, disposal, and journal
reversal. Integrations must map the two stable UUIDs explicitly; neither module
imports the other's ORM.

## Runtime contract

- `GET|POST /api/v1/asset-management/assets/`
- `GET|PATCH|DELETE /api/v1/asset-management/assets/{id}/`
- `POST /api/v1/asset-management/assets/{id}/calculate-depreciation/`
- `GET /api/v1/asset-management/depreciation-entries/`
- `GET /api/v1/asset-management/depreciation-entries/{id}/`
- `GET /api/v1/asset-management/health/`

Every collection is bounded and tenant-filtered. Asset writes pass through
`AssetService`; depreciation writes pass through `DepreciationService`.
`DELETE` archives an asset and retains its protected history. Depreciation is
idempotent for an exact asset/date request, limited to one entry per accounting
month, chronological, row-locked, and capped at residual value.

Manifest permissions are mapped per ViewSet action. Browser mutations use
Django session authentication with normal CSRF enforcement. Errors include a
stable `error_code` and preserve correlation metadata when available.

## Schema migration

`0002_production_asset_domain` preserves UUIDs, values, and history while
adding residual value, governed methods, archival state, constraints, and
indexes. It deliberately stops when legacy financial values, useful lives,
tenant relationships, or duplicate periods cannot be migrated truthfully.
Correct those records and rerun; the migration never guesses financial data.

`0003_tenant_database_guards` adds reversible same-tenant relationship guards.
On PostgreSQL it also enables and forces row-level security through the shared
`app.tenant_id` transaction context and protects ledger rows from update or
delete. Both migrations have reversible MigrationExecutor coverage.

## Paid-module SPI

`extensions.py` is the versioned boundary for industry modules. It supports
detail tabs, actions, schema fields, and barcode/QR/RFID/telemetry identity
providers. A contribution supplies a `CapabilityDescriptor`, a protocol-
conforming implementation, and an optional tenant-eligibility predicate.

Registration rejects incompatible SemVer ranges and duplicates. Discovery
returns descriptors plus explicit availability—not implementation objects.
Entitlement denial, missing resolvers, and resolver failures fail closed. Call
`AssetExtensionRegistry.resolve` immediately before invocation so current
tenant and entitlement checks are applied.

## Verification

```bash
cd backend
pytest -q src/modules/asset_management/tests
```

The suite covers action authorization, complete two-tenant CRUD isolation,
database relationship guards, immutable/idempotent calculations, rollback,
health failure sanitization, reversible migrations, and SPI compatibility.
