# Inventory Management

The inventory frontend is a registry-discovered, governed API v2 client. It
provides dashboard, warehouse/location/item masters, valued stock entries,
balances and immutable ledger views, reservations, cycle counts, batch/serial
trace, bulk import, and versioned environment-specific configuration.

All endpoint and route literals live in `contracts.ts`. `routes.ts` is the
single navigation source and is discovered by the tenant route registry; the
module must not add inventory entries directly to the application sidebar.
Every request validates the governed envelope, preserves the correlation ID,
uses tenant-rooted query keys, and treats malformed responses as failures.

Optional industry modules integrate through core inventory capabilities and
outbox contracts. An unavailable optional capability is displayed explicitly;
it is never represented as an empty successful result.
