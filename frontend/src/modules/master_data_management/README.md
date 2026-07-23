# Master Data Management

This module provides the tenant master-data stewardship UI for entity types,
entities and immutable versions, quality rules and issues, deterministic
matching, merge provenance and reversal, and durable scan jobs.

Tenant administrators manage all runtime policy at
`/master-data/configuration`. The page is a client of the governed v2
configuration API and supports:

- server-side validation and a pre-apply change preview;
- immutable version and correlation evidence;
- rollback by creating a new version;
- complete JSON document import and export;
- tenant feature rollout, safe limits, operational polling, and UI defaults.

Pages fail closed when the tenant configuration or a required safety-preview
capability is unavailable. All module endpoints and application paths are
declared in `contracts.ts`; the frontend does not maintain a parallel URL map.

See: saraise-documentation/modules/02-core/master-data-management/README.md
