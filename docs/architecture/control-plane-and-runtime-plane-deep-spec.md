# SARAISE Control Plane & Runtime Plane Deep Specification

**Status:** Draft v0.1 (authoritative, enforced)

This document defines the **operational heart of SARAISE**: how tenants are provisioned, governed, upgraded, isolated, and terminated.

If this boundary is weak, the platform becomes ungovernable regardless of how good the runtime code is.

---

## 0) Ruthless First Principles

1. **The control plane is the brain.** The runtime plane never makes policy decisions.
2. **The runtime plane is dumb by design.** It executes, enforces, and reports.
3. **All lifecycle actions are explicit.** No implicit creation, upgrade, or deletion.
4. **Global safety > tenant convenience.** The platform must protect itself.
5. **Everything is reversible where legally possible.** Destruction is deliberate.

---

## 1) Plane Responsibilities (Non-Overlapping)

### 1.1 Control Plane (Authoritative)

The control plane owns:
- tenant lifecycle (create, upgrade, suspend, terminate)
- shard provisioning and placement
- policy definition and distribution
- module enablement and versioning
- migration orchestration
- isolation decisions
- quota and entitlement enforcement
- kill-switch execution

The control plane **never serves end-user traffic**.

### 1.2 Runtime Plane (Enforcement-Only)

The runtime plane owns:
- request handling
- authorization enforcement (via Policy Engine)
- workflow execution
- data persistence
- search indexing
- audit emission
- server-side session validation and enforcement (no client-trusted identity)

### 1.3 Authentication Boundary (Explicit)

- Authentication for interactive access is **session-based only**.
- Sessions are:
  - issued by the authentication subsystem
  - stored and validated server-side
  - bound to tenant_id and subject_id

The runtime plane:
- validates session existence and validity on every request
- never trusts client-supplied identity claims
- never accepts JWTs for interactive user authentication

The control plane:
- does not perform request-time authentication
- relies only on authenticated administrative access

---

## 2) Tenant Lifecycle State Machine

Every tenant exists in exactly one lifecycle state:

- `requested`
- `provisioning`
- `active`
- `restricted`
- `suspended`
- `isolating`
- `terminated`

All transitions are:
- explicit
- validated
- audited

### 2.1 State Semantics

- `requested`: tenant record created, no resources
- `provisioning`: shard + resources being created
- `active`: full access
- `restricted`: read-only or limited access (billing, incident)
- `suspended`: access blocked, data retained
- `isolating`: tenant being moved to dedicated infra
- `terminated`: access removed, data retained or destroyed per policy

---

## 3) Tenant Provisioning Workflow

Provisioning is **idempotent and resumable**.

Steps:
1. Validate tenant request
2. Resolve residency & compliance constraints
3. Select shard (or create dedicated shard)
4. Provision runtime resources
5. Apply baseline policies
5.5 Bind authentication context (tenant_id, identity realm, session domain)
6. Enable subscribed modules
7. Verify health gates
8. Transition tenant to `active`

Failure at any step pauses provisioning safely.

---

## 4) Shard Placement & Routing

### 4.1 Placement Inputs

Shard placement decisions use:
- tenant class (XS–XL)
- compliance & residency
- current shard saturation
- isolation flags

### 4.2 Routing Model

- Control plane maintains tenant → shard mapping
- Runtime receives routing config as signed, versioned data
- Runtime refuses traffic for unknown or mismatched tenants

---

## 5) Policy Distribution Model

### 5.1 Source of Truth

- Policies are authored and stored in the control plane
- Policy versions are immutable

### 5.2 Distribution

- Policies compiled into signed bundles
- Bundles pushed to runtime shards
- Runtime treats policies as read-only

### 5.3 Consistency Guarantees

- Eventual consistency within defined SLA
- Policy version included in every audit event

---

## 6) Module Enablement & Version Control

### 6.1 Enablement Rules

- Modules enabled per tenant via control plane
- Enablement validates dependencies
- Partial enablement is forbidden

### 6.2 Version Strategy

- Platform defines allowed module versions
- Tenants cannot pin arbitrary versions
- Upgrades are orchestrated, not ad-hoc

---

## 7) Upgrade & Migration Orchestration

The control plane orchestrates:
- schema migrations
- backfills
- module upgrades
- shard rollouts

Runtime nodes:
- never initiate migrations
- report health only

Upgrade waves respect shard and tenant isolation boundaries.

---

## 8) Quotas, Entitlements, and Throttling

### 8.1 Entitlements

Control plane defines:
- API quotas
- job quotas
- AI usage quotas
- storage limits

### 8.2 Enforcement

- Runtime enforces quotas locally
- Violations are reported back
- Persistent abuse triggers control plane actions

---

## 9) Isolation & Rebalancing

Isolation decisions are made only by the control plane.

Triggers include:
- capacity thresholds
- compliance requirements
- SLA upgrades

Rebalancing process:
1. Mark tenant as `isolating`
2. Provision target shard
3. Migrate data safely
4. Switch routing
5. Resume access

---

## 10) Kill Switches & Emergency Controls

The control plane can:
- disable modules globally or per tenant
- force tenants into `restricted` or `suspended`
- terminate AI agents
- throttle or block traffic to shards

All kill actions are audited and reversible where possible.

---

## 11) Observability & Feedback Loop

### 11.1 Runtime Signals

Runtime must emit:
- health metrics
- saturation signals
- policy evaluation stats
- quota violations

### 11.2 Control Plane Actions

Control plane reacts by:
- adjusting placement
- throttling tenants
- triggering isolation
- scheduling upgrades

---

## 12) Failure Semantics

### 12.1 Control Plane Failure

- Runtime continues serving last known-good config
- No new lifecycle actions allowed
- Session validation and authorization continue to function using last known-good policy and config

### 12.2 Runtime Failure

- Tenant traffic rerouted (if possible)
- Control plane marks shard unhealthy

Fail closed on ambiguity.

---

## 13) Security Boundaries

- Runtime has no credentials to mutate control plane state
- Control plane access is tightly restricted
- All plane-to-plane communication is authenticated and signed
- Runtime cannot mint, extend, or forge authentication sessions

---

## 14) What Is Explicitly Forbidden

- Runtime-initiated provisioning
- Runtime-side policy mutation
- Manual shard placement overrides
- Undocumented lifecycle states
- Runtime-side acceptance of JWTs or client assertions for interactive authentication

---

## 15) Final Warning

Most platforms collapse because **control and execution blur over time**.

This spec exists to ensure SARAISE never loses that boundary — even under pressure.

---

**End of document**

---
