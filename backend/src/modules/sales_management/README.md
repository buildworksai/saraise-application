# Sales Management backend

This module owns the open-source `Customer → Quotation → Sales Order → Delivery
Note` funnel under `/api/v2/sales-management/`. Business mutations go through
`services.py`; clients and extensions must not write lifecycle state, calculated
money, tenant ownership, audit fields, or sequence counters directly.

## Extension boundary

[`integrations.py`](integrations.py) is the stable `sales-management-spi` v1
boundary. It publishes immutable request/result DTOs and protocols for CRM
opportunities, inventory availability, accounting invoices, tax calculation,
shipping, and document rendering/dispatch. Providers register through
`SalesIntegrationRegistry`; duplicate registrations fail, provider selection is
deterministic, and unregistering removes the provider cleanly.

Capability discovery distinguishes `available`, `not_installed`,
`not_entitled`, `not_configured`, and `temporarily_unavailable`. A required
capability that is absent raises `IntegrationUnavailable`, which API callers
map to an explicit 503 result. Empty inventory, zero tax, invoice identifiers,
tracking numbers, or dispatch acknowledgements are never synthesized.

HTTP provider implementations must use the foundation
`src.core.resilience.ResilientHttpClient` with a declared destination
allow-list, configured connect/read timeouts, circuit breaker, bounded retries,
SSRF protection, and correlation propagation. Mutation requests are not
automatically retried; provider idempotency keys or durable jobs are required.

## Health

The public diagnostic exception at `/api/v2/sales-management/health/` is
declared in `manifest.yaml`. It returns non-sensitive readiness only. Database
schema/RLS and durable outbox failures return 503; optional extension absence
returns a sanitized `degraded` or `not_configured` component and does not make
the core funnel unhealthy. Responses contain no row counts, tenant records,
credentials, dependency URLs, raw exception text, or provider bodies.

## Manifest contracts

`manifest.yaml` is validated by `src.core.module_manifest_schema`. It declares
the complete permission vocabulary, the order-creator/delivery-creator
segregation rule, versioned domain events, configuration guarantees, diagnostic
exception, capability states, gateway protocols, and frontend contribution
slots. SoD pair metadata is structured under `metadata` because the current
foundation schema requires the top-level `sod_actions` field to remain a flat
list of permission strings.
