

# Engineering Governance & PR Controls

**Status:** ENFORCED (Post-Architecture Freeze)

This document defines the **non-negotiable engineering governance rules** for SARAISE after architecture freeze. Its purpose is to ensure that execution does not erode architectural integrity, security posture, or scale guarantees.

---

## 1) Governance Objectives

Engineering governance exists to:
- Enforce frozen architectural domains
- Prevent silent scope creep
- Ensure security- and scale-critical code is reviewed correctly
- Provide deterministic escalation paths

Speed without governance is a liability.

---

## 2) Repository Classification

All repositories are classified into governance tiers.

### Tier 0 — Critical (Highest Control)

Repositories:
- `saraise-auth`
- `saraise-policy-engine`
- `saraise-runtime`
- `saraise-control-plane`
- `saraise-platform-core`

Characteristics:
- Direct impact on security, isolation, or correctness
- Changes can affect all tenants

---

### Tier 1 — Platform Supporting

Repositories:
- Observability tooling
- Infrastructure automation
- CI/CD tooling

---

### Tier 2 — Application & Modules

Repositories:
- ERP modules
- Industry packages
- UI applications

---

## 3) Ownership Rules

### 3.1 Mandatory Ownership

Each repository MUST have:
- One **Primary Owner** (accountable)
- One **Secondary Owner** (backup)

Tier 0 owners must be senior engineers approved by leadership.

---

### 3.2 Ownership Responsibilities

Owners are responsible for:
- Reviewing architectural compliance
- Blocking unsafe changes
- Escalating violations

Ownership is not honorary.

---

## 4) Pull Request (PR) Controls

### 4.1 Mandatory PR Rules (All Repos)

- No direct commits to protected branches
- All changes via PRs only
- CI must pass before merge

---

### 4.2 Tier 0 PR Requirements (Strict)

Additional requirements for Tier 0 repos:

- Minimum **2 senior reviewers**
- One reviewer MUST be the repo owner
- Explicit checklist confirming:
  - no auth changes
  - no policy semantic changes
  - no session behavior changes
  - no ABAC violations

PRs lacking this checklist MUST be rejected.

---

### 4.3 Frozen Domain Protection

Any PR touching frozen domains MUST:
- Reference the relevant architecture spec
- Explicitly state: "No architectural change introduced"

If this cannot be stated truthfully, an ACP is required.

---

## 5) CI Enforcement (Non-Bypassable)

Mandatory CI checks for Tier 0 repos:
- Static checks preventing JWT auth usage
- Lint rules blocking session mutation of permissions
- Tests enforcing deny-by-default behavior
- Policy-version validation tests

CI bypass is forbidden.

---

## 6) Violation Handling & Escalation

### 6.1 What Constitutes a Violation

- Modifying frozen domains without ACP
- Bypassing PR review requirements
- Introducing auth or policy shortcuts
- Circumventing CI controls

---

### 6.2 Escalation Path

1. Repo Owner
2. Architecture Lead
3. Architecture Board
4. Executive Review (if repeated)

Violations are tracked and audited.

---

## 7) Emergency Changes

Emergency fixes:
- Are allowed ONLY for production outages
- Must still go through PR
- Must be reviewed post-facto within 24 hours

Emergency does NOT bypass architecture.

---

## 8) Final Warning

Most platform failures occur when governance weakens under delivery pressure.

This document exists to ensure that does not happen.

---

**End of document**

---