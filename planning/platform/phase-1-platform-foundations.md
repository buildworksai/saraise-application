# Phase 1 — Platform Foundations
Status: EXECUTION READY

Authoritative execution document for Phase 1.
Refer to architecture-freeze-and-change-control.md for constraints.

# Phase 1 — Platform Foundations

**Status:** EXECUTION READY (Post-Architecture Freeze)

Phase 1 establishes the **non-negotiable technical foundations** of the SARAISE platform. It is strictly focused on correctness, security, isolation, and governance — **not features**.

No architectural changes are permitted in this phase.

---

## 1) Phase 1 Objectives (Authoritative)

Phase 1 exists to:

- Instantiate control plane and runtime plane skeletons
- Implement the Authentication Subsystem baseline
- Implement the Policy Engine baseline with policy-version gating
- Wire tenant isolation and shard assignment end-to-end
- Establish CI, PR, and governance guardrails

If work does not directly support these objectives, it is **out of scope**.

---

## 2) Explicitly Out of Scope

The following are NOT allowed in Phase 1:

- ERP business modules or workflows
- Industry-specific logic
- End-user UI (beyond minimal admin bootstrap)
- AI agents, tools, or workflows
- Performance optimization beyond correctness
- Multi-region deployments (only architecture readiness)

Violations require escalation.

---

## 3) Foundational Services to Be Built

### 3.1 Control Plane

**Repository:** `saraise-control-plane`

Responsibilities:
- Tenant lifecycle management (create, suspend, delete)
- Deterministic shard assignment
- Policy distribution to runtime
- Identity sync orchestration

Explicitly forbidden:
- Request-time authentication
- Business logic execution

---

### 3.2 Runtime Plane

**Repository:** `saraise-runtime`

Responsibilities:
- Request handling framework
- Session validation middleware
- Policy enforcement hook
- Module execution sandbox (empty scaffold only)

Explicitly forbidden:
- Session issuance
- Policy mutation
- Direct control-plane dependencies

---

### 3.3 Authentication Subsystem

**Repository:** `saraise-auth`

Responsibilities:
- Login and logout
- Session issuance, rotation, and invalidation
- Identity federation scaffolding (OIDC / SAML)
- Session store integration (Redis, region-local)

Must comply strictly with:
- authentication-and-session-management-spec.md

---

### 3.4 Policy Engine

**Repository:** `saraise-policy-engine`

Responsibilities:
- Policy evaluation engine
- ABAC input contract enforcement
- Policy-version validation
- Deterministic deny reasons

No business policies in Phase 1.

---

### 3.5 Platform Core Libraries

**Repository:** `saraise-platform-core`

Responsibilities:
- Identity snapshot models
- Tenant context propagation
- Policy decision contracts
- Shared audit primitives

---

## 4) Governance & Guardrails (Mandatory)

Phase 1 execution is governed by:

- architecture-freeze-and-change-control.md
- engineering-governance-and-pr-controls.md

Mandatory rules:
- Tier-0 PR controls enforced from day one
- CI checks blocking frozen-domain violations
- No bypasses, even for "temporary" code

---

## 5) Phase 1 Milestones

1. Repositories bootstrapped with CI + branch protection
2. Control plane provisions a tenant deterministically
3. Auth subsystem issues sessions with policy_version
4. Runtime validates sessions and enforces deny-by-default
5. Policy engine evaluates sample policies with version gating
6. Shard assignment wired end-to-end

---

## 6) Phase 1 Exit Criteria (ALL REQUIRED)

Phase 1 is complete only when:

- A tenant can be provisioned end-to-end
- Login → session issuance → runtime validation works
- Policy-version mismatch reliably denies access
- No request bypasses policy evaluation
- No violations of frozen domains detected
- All Tier-0 repos pass governance checks

---

## 7) Phase 1 Deliverables

- Control plane skeleton (production-safe)
- Runtime plane skeleton (deny-by-default)
- Authentication subsystem baseline
- Policy engine baseline
- Platform core shared contracts
- CI + PR governance enforcement

---

## 8) Final Warning

Phase 1 failures are almost always discipline failures, not technical ones.

This document exists to prevent that outcome.

---

**End of document**

---