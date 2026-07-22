# Budget Management frontend

Production tenant UI for fiscal planning, allocation replacement, lifecycle approval, availability control, accounting actual synchronization, variance alerts, and authorized client-side reporting.

- `contracts.ts` is the authoritative v2 DTO, endpoint, route, and query-key surface.
- `services/budget-service.ts` unwraps governed envelopes, preserves pagination/correlation evidence, and translates errors into `BudgetManagementApiError`.
- `routes.ts` owns all sidebar and contextual tenant routes in every supported operating mode.
- Planning totals and variance are server-derived. Create/edit forms never submit them.
- Allocation replacement is atomic and optimistic-concurrency protected; the UI does not claim success before the server confirms it.
- CSV report export contains only data already authorized and returned to the browser.

The UI displays accounting/workflow/notification dependency failures explicitly. It never substitutes generated or hardcoded financial results.
