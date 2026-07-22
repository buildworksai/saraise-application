# Project Management

The open-source project execution module provides tenant-safe projects, tasks,
team allocation, milestones, time entry, immutable activity, and versioned
runtime configuration. All frontend traffic uses the governed
`/api/v2/project-management/` envelope; endpoint strings live only in
`contracts.ts`.

## User experience

Routes are discovered from `routes.ts`. The sidebar exposes Dashboard,
Projects, Tasks, My Work, Time, and permission-gated Settings. Contextual routes
cover list/detail/create/edit workflows for all five resources and configuration
history. Pages use design tokens, responsive grids, keyboard-focus styles,
skeleton, empty, error/correlation, and mutation-pending states. My Work refuses
to guess a user-to-employee relationship when the optional HR adapter is absent.

## Configuration

Settings are tenant and environment scoped. Operators create immutable drafts,
simulate effects, publish, export/import versioned documents, inspect history,
and roll back by creating a new active version. The server owns safe limits,
regex/schema validation, RBAC, audit, and correlation evidence; the UI is only a
client of that API.

## Extension boundary

Paid modules integrate through the versioned backend protocols in
`backend/src/modules/project_management/extensions.py`. Core stays functional
with zero providers. Provider absence is explicit and providers cannot bypass
tenant isolation, access decisions, lifecycle guards, or audit.

## Verification

Backend module tests use the command documented in `UNIT_BRIEF.md`. Frontend
verification uses `npm run typecheck`, `npm test`, and `npm run build` when the
repository dependencies are available.
