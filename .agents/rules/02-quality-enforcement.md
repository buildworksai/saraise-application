---
description: Quality gates, rule registry, git workflow, and MCP enforcement (authoritative)
globs: **/*
alwaysApply: true
---

# SARAISE Quality Enforcement & Standards

**Rule IDs**: SARAISE-01001 to SARAISE-01008, SARAISE-05001 to SARAISE-05999, SARAISE-06003, SARAISE-06005
**Consolidates**: `02-rule-registry.md`, `03-quality-gates.md`, `08-git-workflow.md`, `09-mcp-enforcement.md`

---

## Master Rule Registry

**Numbering**: `SARAISE-00001..99999` immutable IDs

| ID Range | Category | File Location(s) |
|----------|----------|------------------|
| 00001–00999 | Getting Started & Project Setup | `01-getting-started.md` |
| 01000–01999 | Quality Gates | `02-quality-enforcement.md` |
| 02000–02999 | Python Coding Standards | `04-backend-standards.md` |
| 03000–03999 | TypeScript Coding Standards | `05-frontend-standards.md` |
| 04000–04999 | Automated Enforcement (Hooks/CI) | `06-automated-enforcement.md` |
| 05000–05999 | Git Workflow | `02-quality-enforcement.md` |
| 06000–06999 | MCP Enforcement | `02-quality-enforcement.md` (SARAISE-06003, 06005) |
| 07000–07999 | Authentication & RBAC | `07-rbac-security.md`, `10-session-auth.md`, `12-auth-enforcement.md` |
| 08000–08999 | Secrets Management | `08-secrets-management.md` |
| 09000–09999 | Ports & CORS | `09-infrastructure-config.md` |
| 10000–10999 | Audit Logging | `11-audit-logging.md` |
| 11000–11999 | UI Terminology & Branding | `16-frontend.md` |
| 12000–12999 | Technology Stack | `03-tech-stack.md` |
| 14000–14999 | Error Handling & Troubleshooting | `05-frontend-standards.md` |
| 15000–15999 | Deployment & DevOps | `09-infrastructure-config.md` |
| 16000–16999 | Service Integration | `19-service-monitoring.md` |
| 17000–17999 | Monitoring & Observability | `19-service-monitoring.md` |
| 18000–18999 | Performance Optimization | `13-performance-optimization.md` |
| 19000–19999 | Troubleshooting & Debugging | `14-troubleshooting.md` |
| 26000–26999 | Module Architecture & Framework | `15-module-architecture.md` |
| 27000–27999 | Module Development Standards | `20-module-development.md` |
| 28000–28999 | Module Dependencies & Integration | `15-module-architecture.md` |
| 29000–29999 | Module Lifecycle Management | `17-module-lifecycle-metadata.md` |
| 30000–30999 | Metadata Modeling & Customization | `17-module-lifecycle-metadata.md` |
| 31000–31999 | Customization Framework | `17-module-lifecycle-metadata.md` |
| 32000–32999 | Platform Management | `21-platform-tenant.md` |
| 33000–33999 | Tenant Management | `21-platform-tenant.md` |
| 34000–34999 | Billing & Subscriptions | `22-billing.md` |
| 35000–35999 | Subscription Plans | `22-billing.md` |
| 36000–36999 | Discounts & Offers | `18-pricing.md` |
| 37000–37999 | Coupon Management | `18-pricing.md` |
| 38000–38999 | Partner Management | `23-resource-quotas.md` |
| 39000–39999 | Rate Limiting | `23-resource-quotas.md` |
| 40000–40999 | User Quotas | `23-resource-quotas.md` |

### Cross-Reference Examples
- "See SARAISE-07001 for session-based authentication" → multi-tenant authentication
- "See SARAISE-08001 for environment variables" → centralized secrets management
- "See SARAISE-09001 for port configuration" → development environment setup

### Technology Stack Authority
- **SARAISE-12001 through SARAISE-12006** supersede all conflicting standards. See `03-tech-stack.md` for complete details.

### Module Architecture Authority
- **SARAISE-26001 through SARAISE-26010** define modular architecture patterns. See `15-module-architecture.md` for details.
- **SARAISE-30001 through SARAISE-30010** define metadata modeling patterns. See `19-module-lifecycle-metadata.md` for details.

### Enterprise SaaS Authority
- **SARAISE-32001 through SARAISE-40010** define Enterprise SaaS modules. See `21-platform-tenant.md` through `23-resource-quotas.md` for details.

---

## Quality Gates

**Related Documentation:**
- Application Architecture: `docs/architecture/application-architecture.md`
- Engineering Governance: `docs/architecture/engineering-governance-and-pr-controls.md`

### SARAISE-01001 Quality Gate Configuration

**SECURITY WARNING**: Never hardcode credentials in rules files.
- For development: See `08-secrets-management.md` for proper credential management
- SARAISE project must be configured via automated deployment scripts

```yaml
quality_gates:
  code_coverage: 90            # SARAISE-01002
  duplicated_lines: 3
  maintainability_rating: A
  reliability_rating: A
  security_rating: A           # SARAISE-01003
  security_hotspots: 0
  vulnerabilities: 0           # SARAISE-01004
  code_smells: 0
  bugs: 0
  technical_debt: 5            # minutes per file (SARAISE-01005)
  cognitive_complexity: 15     # SARAISE-01006
  cyclomatic_complexity: 10
```

### SARAISE-01002 Coverage ≥ 90%
New/changed code must maintain ≥ 90% coverage. CI blocks merges below threshold.

### SARAISE-01003 Security Rating A
Zero tolerance for security degradations. Fix BLOCKER/CRITICAL before merge.

### SARAISE-01004 Zero Vulnerabilities
Code + dependencies must report 0 vulnerabilities prior to merge/release.

### SARAISE-01005 Technical Debt ≤ 5 min/file
Maintainability guardrail for safety-critical software.

### SARAISE-01006 Cognitive Complexity ≤ 15/function
Reduce human error in reviews and maintenance.

### SARAISE-01007 Domain Ownership & TypeScript Cleanliness (CRITICAL)
Every top-level frontend domain (e.g., `frontend/src/pages/logistics`, `frontend/src/pages/manufacturing`, `frontend/src/pages/marketing-*`, `frontend/src/pages/metadata`, `frontend/src/pages/modules`) MUST have an explicit **CODEOWNER** responsible for:
- Keeping that domain at **zero TypeScript errors** and **zero ESLint errors**.
- Rejecting any PR that introduces new TS/ESLint errors in that domain.

**CI MUST**:
- Track TypeScript errors **per domain directory**.
- Fail a PR if `errors_after > errors_before` for any touched domain directory.
- New files MAY NOT be added to a domain that already has TypeScript errors unless the same PR also drives that domain's error count closer to zero.

### SARAISE-01008 Transitional Freeze for "Dirty" Frontend Domains
A frontend domain directory is considered **dirty** when any `tsc --noEmit` error originates from files under that directory.

**While a domain is dirty**:
- Only **refactor / remediation** work is allowed in that directory.
- **New features** targeting that domain are forbidden until `tsc --noEmit` reports **zero errors** for that directory.
- CI MUST enforce that net-new lines in dirty domains are exclusively associated with TS/ESLint fixes or test hardening.
- Once a domain reaches **zero TypeScript errors and zero ESLint errors**, normal feature work may resume, but SARAISE-04002 and SARAISE-04010 (global TypeScript/ESLint gates) keep it clean.

---

## Git Workflow

### Main Branch Protection
- No direct pushes; PRs only
- Require status checks: TypeScript, ESLint, Tests, Quality Gates

### Branch Naming
- `feature/<description>`
- `bugfix/<description>`
- `hotfix/<description>`
- `release/v<semver>`

### Canonical Repository
- Remote origin must be `${REPO_CANONICAL}`

---

## MCP Enforcement

**⚠️ CRITICAL**: MCP configuration must follow security and validation requirements.

### SARAISE-06003 Minimum Shape Validation

**REQUIRED:** If MCP configuration exists, it must:
- Parse as valid JSON
- Contain object `mcpServers`
- Each server must define:
  - `command`: string
  - `args`: array (may be empty)
  - `env`: object (keys only validated; values may be placeholders)

### SARAISE-06005 Security

**REQUIRED:** MCP configuration security requirements:
- No secrets or tokens stored in repository
- Environment variables must be used for sensitive values
- Configuration validation must check only keys exist; never log values

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
