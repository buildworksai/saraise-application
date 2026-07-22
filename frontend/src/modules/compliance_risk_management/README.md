# Compliance Risk Management frontend

The module is a governed v2 client for the open-source risk register, controls and
testing, regulatory requirements, compliance calendar, remediation, dashboard,
heatmap, and tenant configuration lifecycle.

## Architecture

- `contracts.ts` is the single DTO and endpoint registry. It intentionally has no
  v1 fallbacks or alternate response shapes.
- `services/compliance-risk-service.ts` unwraps governed envelopes, preserves
  stable error/correlation data, URL-encodes typed filters, and defines
  tenant-separated TanStack Query keys.
- `routes.ts` is auto-discovered by the tenant route registry. Seven sidebar
  routes own all detail, create, edit, execution, history, and import/export
  contextual routes.
- `components/ComplianceRiskUI.tsx` provides the shared accessible loading,
  empty, forbidden, not-found, retry, status, pagination, and audit states.
- `pages/` implements complete vertical workflows. Mutations call the same v2
  APIs available to integrations; the browser has no privileged persistence path.

Every page sets a human-readable title and uses semantic design tokens for
system, light, and dark themes. Destructive and irreversible operations use
accessible dialogs. Configuration changes require server preview before publish,
and import requires an explicit dry-run.

## Verification

Focused contracts, service, route/sidebar, shared-component, and page-state tests
are colocated in this module. `tsconfig.json` provides a module-only strict typecheck
target for isolated development while the repository-wide build remains the final
integration gate.
