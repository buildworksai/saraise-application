# CRM

Tenant-isolated customer relationship management for leads, accounts, contacts,
opportunities, activities, forecasting, and asynchronous scoring.

The module owns its typed API contract in `contracts.ts`, its route inventory in
`routes.ts`, and its governed API client in `services/crm-service.ts`. All pages
are registered through the tenant route registry.

Tenant behavior is loaded from the CRM configuration API. The configuration page
at `/crm/configuration` provides server-validated preview, version history,
rollback, import/export, feature flags, and phased rollout controls. Runtime
components fail visibly when configuration is unavailable; they do not fall back
to duplicated client-side business defaults.

The canonical backend contract and permissions are declared in
`backend/src/modules/crm/manifest.yaml`.
