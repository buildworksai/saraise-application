# SARAISE Implementation Sequencing & Build Order

**Status:** FROZEN v1.0 (Architecture Board & Org Board Approved)

This document defines **how SARAISE must be built** so that scale, security, and operability are achieved deliberately — not accidentally.

This is not a roadmap for features. It is a **risk-controlled execution plan**.

## Architecture Freeze Declaration

This document is now in **execution-only mode**.

The following architectural domains are **FROZEN** and MUST NOT be changed without formal Architecture Board re-approval:

- Authentication & Session Management (no JWT-based auth)
- Policy Engine & Policy Version Gating
- ABAC Attribute Architecture & Freshness SLAs
- Control Plane vs Runtime Plane boundaries
- Shard Sizing, Capacity Envelopes, and Isolation Triggers
- AI Agent Safety, Quotas, and Kill Switches

Post-freeze work is limited to **implementation within these constraints**.

---

## 0) Ruthless Execution Principles

1. **Foundations before features.** Anything built on sand will be rebuilt.
2. **No parallelism without contracts.** Teams move only when interfaces are locked.
3. **Security and governance ship first.** UI and AI come later.
4. **Stub is acceptable. Broken is not.**
5. **No phase exits without hard criteria.** Opinions do not advance phases.

---

## 1) Build Phases (Non-Negotiable Order)

Implementation proceeds in the following phases. Skipping or reordering is forbidden.

1. Platform Foundations
2. Control Plane Core
3. Runtime Core
4. Security & Authorization Enforcement
5. Module Framework & Core ERP Primitives
6. Migration & Upgrade Automation
7. AI Agent Infrastructure (No Business Autonomy)
8. Industry Modules & Packaging
9. Multi-Region & DR Enablement
10. Production Hardening & Launch Readiness

Phase order is now locked. Any proposal to reorder, merge, or skip phases requires Architecture Board review.

---

## 2) Phase 1 — Platform Foundations

### Scope
- Repo structure
- Build system
- CI/CD
- Observability baseline

### Deliverables
- Monorepo or clearly defined multi-repo with version contracts
- CI gates for lint, tests, security checks
- Central logging + metrics skeleton

### Exit Criteria
- Every commit is built and tested
- No manual deploys exist

---

## 3) Phase 2 — Control Plane Core

### Scope
- Tenant lifecycle state machine
- Shard registry
- Placement engine
- Policy storage & distribution

### Deliverables
- Control plane API (internal)
- Persistent state for tenants, shards, policies
- Signed config distribution mechanism

### Exit Criteria
- Tenants can be provisioned end-to-end (even if runtime is stubbed)
- Illegal tenant states are impossible

---

## 4) Phase 3 — Runtime Core

### Scope
- Request routing
- Runtime configuration ingestion
- Health reporting
- Basic workflow engine

### Deliverables
- Runtime service that boots from control-plane config
- Health & saturation signals emitted

### Exit Criteria
- Runtime refuses traffic without valid config
- Control plane can mark runtime unhealthy

---

## 5) Phase 4 — Security & Authorization Enforcement

### Scope
- Policy engine
- Policy language enforcement
- Authentication & Session Management Subsystem (login, logout, session issuance, rotation, invalidation)
- RBAC + ABAC + SoD + JIT

### Deliverables
- Deterministic policy evaluation
- Audit-grade decision logging

### Exit Criteria
- Authentication & session flows are implemented, tested, and enforced platform-wide
- Every API call is authorized
- Failures are fail-closed
- Explainability is complete
- No architectural changes to auth, policy, or session semantics are permitted beyond this phase

---

## 6) Phase 5 — Module Framework & Core ERP Primitives

### Scope
- Module loader
- Dependency DAG
- Core primitives (ledger, workflow, identity hooks)

### Deliverables
- Module lifecycle management
- Permission registry enforcement

### Exit Criteria
- Modules can be enabled/disabled safely
- Dependency violations are blocked

---

## 7) Phase 6 — Migration & Upgrade Automation

### Scope
- Schema migration engine
- Backfill orchestration
- Upgrade waves

### Deliverables
- Expand/contract automation
- Rollback & read-only fallback

### Exit Criteria
- Migrations run without downtime on test shards
- Lock budgets enforced

---

## 8) Phase 7 — AI Agent Infrastructure (Constrained)

### Scope
- Agent runtime
- Tool registry
- Quotas, kill switches, audit

### Explicitly Excluded
- Autonomous business decisions
- Financial posting
- Compliance actions

### Exit Criteria
- Agents cannot bypass workflows
- Agents are fully attributable and stoppable

---

## 9) Phase 8 — Industry Modules & Packaging

### Scope
- Industry-specific modules
- Subscription packaging

### Deliverables
- Industry bundles
- Tenant-level module selection

### Exit Criteria
- Modules respect all governance constraints
- Package enablement is atomic

---

## 10) Phase 9 — Multi-Region & DR Enablement

### Scope
- Region-aware provisioning
- Replication (where allowed)
- RPO/RTO tiers

### Exit Criteria
- Residency violations are impossible
- DR failover tested per tier

---

## 11) Phase 10 — Production Hardening & Launch Readiness

### Scope
- Load testing
- Chaos testing
- Incident drills

### Exit Criteria (Launch Blockers)

ALL must be true:
- Upgrade rollback tested
- Isolation triggers tested
- Policy misconfig fails closed
- AI agent kill tested
- Shard saturation handled automatically

No exceptions.

---

## 12) What Is Explicitly Forbidden

- Feature-driven sequencing
- Parallel implementation without locked interfaces
- Shipping AI before governance
- Launching without rollback proof

---

## 12A) Post-Freeze Change Control

Any change request affecting frozen domains MUST:
1. Be documented as a formal Architecture Change Proposal (ACP)
2. Include security, scale, and migration impact analysis
3. Be approved by the Architecture Board

Implementation teams are not permitted to "interpret" or "simplify" frozen architecture.

---

## 13) Final Warning

Most platforms fail during execution, not design.

This document is now a binding execution contract. Violations are treated as delivery risks.

---

**End of document**

---
