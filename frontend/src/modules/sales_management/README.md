# Sales Management frontend

Production React/TypeScript client for the open-source quote-to-delivery funnel:

`Customer → Quotation → Sales Order → Delivery Note`

The module owns its governed v2 contracts, runtime-validated gateway, TanStack Query keys,
route descriptors, accessible workflow pages, and tenant sales configuration UI. The shared
tenant route registry auto-discovers `routes.ts`; no parallel router or sidebar wiring is needed.

## Extension boundary

CRM, inventory, accounting, tax, shipping, document, CPQ, payment, and industry capabilities
remain integrations. UI capability states and explicit 503 errors are displayed as unavailable;
the frontend never invents stock, tax, invoice, tracking, forecast, or AI results.

## Verification

Run `npm run typecheck` and `npm test -- --run src/modules/sales_management`. Route tests cover
titles, paths, parentage, sidebar parity, static route precedence, and all supported runtime modes.
