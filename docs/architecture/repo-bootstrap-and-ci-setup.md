# Repository Bootstrap & CI Setup

**Status:** EXECUTION READY  
**Applies To:** All Phase 1 Repositories

This document defines how repositories are created, protected, and enforced.

---

## 1) Repository Initialization
- Create repo from approved template
- Enforce branch protection on `main`
- Disable force-pushes
- Require PRs for all changes

---

## 2) Branch Protection Rules
- Minimum 2 approvals for Tier-0 repos
- CI checks mandatory before merge
- No direct commits to protected branches

---

## 3) Required CI Pipelines

### Mandatory Checks (Tier-0)
- Auth invariants (no JWT usage)
- Session integrity tests
- Policy-version validation tests
- ABAC contract validation
- Lint + static analysis

CI bypass is forbidden.

---

## 4) PR Templates
All PRs must include:
- Affected repos/modules
- Frozen-domain impact statement
- Security impact assessment
- Rollback plan (if applicable)

---

## 5) Secrets & Credentials
- No secrets in code or CI logs
- Use approved secret manager only
- Short-lived credentials for CI

---

## 6) Repo Ownership Enforcement
- CODEOWNERS file mandatory
- Owners auto-requested for PRs
- Owner approval required for merge

---

## 7) Final Warning
Governance failures scale faster than bugs.  
This document exists to prevent that.

---
