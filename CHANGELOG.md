<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

All notable changes to SARAISE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- Pinned the mutation-testing toolchain's transitive `qs` dependency to `6.15.3`, removing the
  `GHSA-q8mj-m7cp-5q26` denial-of-service advisory introduced with StrykerJS.
- **data-migration (CRITICAL):** Closed a cross-tenant read. The external-database source path executed a
  caller-controlled query/DSN against the application's own primary database with no tenant scoping, so a
  privileged tenant user could read another tenant's rows. Caller-supplied connection strings are removed
  entirely: a migration job now references an operator-registered `ExternalConnection` by opaque id, the
  connection is built from server-side parameters (never a caller string), the validated IP is pinned via
  `hostaddr` to defeat DNS rebinding, and connections to the primary/internal network are denied fail-closed.
  Connection registration is restricted to platform operators (#9).

### Changed
- Replaced broad per-module MyPy exemptions with a pinned, fingerprint-based ratchet that preserves the
  repository's existing type-checking debt while rejecting every new or changed finding (#14).
- **BREAKING (data-migration):** A database migration source's `source_config` no longer accepts
  `connection_string` (or any raw connection/SQL field); it must supply a `connection_id` referencing an
  operator-registered `ExternalConnection`. Existing jobs that still carry a `connection_string` fail closed
  with a migration-required error and must be re-registered (#9).

### Fixed
- Application boot failure: removed an orphaned `ModeAuthMiddleware` registration that referenced a
  module which never existed, and reordered the mode-aware session middleware to run after Django's
  authentication middleware. Added a middleware-import smoke test to prevent regressions (#8).

### Changed
- Enforced Control Plane / Runtime Plane separation: removed Control Plane mutation calls from the
  Runtime Plane frontend (#11).
- Adopted the cross-lab agent contract and a machine-enforced commit policy — author identity is
  enforced and AI attribution is rejected by a `commit-msg` hook (#12).

### Added
- Incremental mutation-testing gates require a mutation score of at least 90% for changed Python and
  TypeScript source files, with source-only path filters keeping unrelated pull requests out of the workflow.
- Envelope encryption with pluggable key-management backends and master-key rewrapping
- Reversible initial migrations for the notifications module
- Policy-backed tenant-management permission declarations
- Initial changelog
- Phase 7.5: Licensing subsystem for self-hosted deployments
  - 14-day trial period for new installations
  - License validation (connected and isolated modes)
  - Soft lock (read-only) for expired licenses
  - 30-day grace period for connected mode
  - Module access control (Foundation/Core/Industry)
- Phase 7.6: Mode-aware authentication
  - Dual-mode authentication support (self-hosted vs SaaS)
  - Self-hosted mode: Django built-in authentication
  - SaaS mode: Delegation to saraise-auth service
  - Mode-aware session middleware
  - Mode detection utilities

### Changed
- **License**: SARAISE is licensed under Apache License 2.0
  - SARAISE is free and open source software
  - Commercial use, modification, and distribution are allowed under Apache 2.0 terms
  - See [LICENSE](LICENSE) for full license text
- Phase 7.7: Open source preparation
  - Repository verified for public release
  - All documentation verified public-friendly
  - CI/CD workflows configured for open source
  - Release workflow created

### Deprecated

### Removed
- Unused direct PyJWT dependency and committed backend test/coverage/migration-backup artifacts
- Nine unfinished scaffold modules from the always-enabled foundation entitlement list

### Fixed
- Authenticated tenant and security health endpoints retain their 200/503 readiness semantics
- Authorized tenant-scoped platform and security requests now reach row-level isolation checks
- User-bound AI executions now validate active sessions on every execution transition
- AI approval separation-of-duties checks now use attributed tool invocations
- Provider base URLs can now be overridden through deployment configuration
- Placeholder workflow triggers, AI revenue predictions, and module lifecycle operations fail explicitly

### Security
- Policy Engine circuit breaking now counts HTTP 429 and 5xx responses as dependency failures
- Policy evaluation fails closed in SaaS when configuration or the Policy Engine is unavailable
- Login rejects the unsupported MFA field instead of silently ignoring it
- Phase 7.5: License validation prevents unauthorized module access
- Phase 7.6: Mode-aware authentication ensures proper session validation per deployment mode

---

## [0.1.0] - 2025-01-03

### Added
- Initial release of SARAISE
- Foundation modules (Platform Management, Tenant Management, Billing & Subscriptions)
- Metadata Modeling system
- Customization Framework
- CRM module
- Accounting module
- HR module (employee, attendance, leave, payroll, performance, learning management)
- Project Management module (projects, tasks, resources, budgets, milestones, time entries)
- Purchase & Procurement module (suppliers, requisitions, RFQs, POs, GRNs, invoices with three-way matching)
- Inventory Management module (stock, warehouse, batch/serial, QC, GRN, forecasting)
- Manufacturing module (BOMs, work orders, production planning)
- Retail module (omnichannel retail operations)
- Hospitality module (restaurant and hotel operations)
- AI Agent Management module
- Workflow Automation module
- Session-based authentication
- Role-Based Access Control (RBAC)
- Multi-tenant architecture
- Audit logging system
- Module architecture framework

### Security
- Session-based authentication with HTTP-only cookies
- RBAC with deny-by-default enforcement
- Row-level multitenancy (tenant_id filtering)
- Immutable audit logging
- Input validation and sanitization
- SQL injection prevention
- XSS prevention

---

## Types of Changes

- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for security improvements and vulnerability fixes

---

## Version Format

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for functionality added in a backwards compatible manner
- **PATCH** version for backwards compatible bug fixes

---

## Release Notes

For detailed release notes, see:
- [GitHub Releases](https://github.com/buildworksai/saraise.release/releases)
- [Documentation](docs/architecture/)

---

**Last Updated**: 2026-01-07

---

SARAISE - Secure and Reliable AI Symphony ERP
Visit us at: [www.saraise.com](https://www.saraise.com)
