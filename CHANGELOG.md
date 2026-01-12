<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

All notable changes to SARAISE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
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

### Fixed

### Security
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
