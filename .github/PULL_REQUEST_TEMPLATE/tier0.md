# Tier 0 — Critical Path Changes

**⚠️ MANDATORY CHECKLIST — This PR modifies Tier 0 critical paths**

This PR modifies one or more of the following critical paths:
- `/backend/src/core/*`
- Authentication/Session Management
- Policy Engine
- Control Plane Integration
- Runtime Plane
- Security Core (SoD, Role Hierarchy)

## Pre-Merge Checklist

**ALL items must be checked before merge approval:**

- [ ] **No authentication changes** — This PR does not modify authentication logic, session management, or auth-related core infrastructure
- [ ] **No policy semantic changes** — This PR does not modify Policy Engine semantics, permission evaluation logic, or authorization rules
- [ ] **No session behavior changes** — This PR does not modify session creation, validation, expiration, or revocation behavior
- [ ] **No ABAC violations** — This PR does not introduce attribute-based access control violations or bypass authorization checks
- [ ] **Architecture compliance statement** — This PR does not introduce architectural changes (or references approved ACP: `#ACP-XXX`)

## Review Requirements

**This PR requires:**
- [ ] **2 senior reviewers** (one MUST be repo owner: @saraise/security-team or @saraise/platform-owners)
- [ ] **Explicit approval** from both reviewers
- [ ] **All CI checks passing** (no exceptions)

## Architecture Change Proposal (ACP)

If this PR introduces architectural changes:
- [ ] ACP document created: `architecture/acp-proposals/ACP-XXX.md`
- [ ] ACP approved by Architecture Board
- [ ] ACP linked in PR description: `#ACP-XXX`

---

**PRs lacking this checklist completion will be REJECTED.**
