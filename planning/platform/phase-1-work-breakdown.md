# Phase 1 — Work Breakdown Structure

**Status:** EXECUTION READY  
**Scope:** Platform Foundations (Post-Architecture Freeze)

This document decomposes Phase 1 into executable epics, deliverables, ownership, and exit criteria.  
No architectural changes are permitted.

---

## 1) Phase 1 Goals
- Establish core platform services
- Enforce frozen architecture invariants
- Enable safe parallel team execution

---

## 2) Epics & Deliverables

### EPIC-01: Control Plane Skeleton
**Repos:** saraise-control-plane  
**Deliverables:**
- Tenant lifecycle APIs (create/suspend/delete)
- Shard assignment service
- Policy distribution pipeline
- Health & readiness endpoints

**Exit Criteria:**
- Tenant can be provisioned end-to-end
- Policy version distributed to runtime

---

### EPIC-02: Runtime Plane Skeleton
**Repos:** saraise-runtime  
**Deliverables:**
- Request handling framework
- Session validation middleware
- Policy enforcement hook
- Module execution sandbox

**Exit Criteria:**
- Deny-by-default enforced
- Policy engine invoked on every request

---

### EPIC-03: Authentication Subsystem
**Repos:** saraise-auth  
**Deliverables:**
- Login/logout endpoints
- Session issuance & invalidation
- OIDC/SAML federation scaffolding
- Redis session store integration

**Exit Criteria:**
- Sessions issued & validated
- Policy version embedded in session

---

### EPIC-04: Policy Engine Baseline
**Repos:** saraise-policy-engine  
**Deliverables:**
- Policy evaluation engine
- ABAC input contract
- Policy-version gating
- Deterministic deny reasons

**Exit Criteria:**
- Sample policies evaluated correctly
- Stale policy sessions denied

---

### EPIC-05: Platform Core Libraries
**Repos:** saraise-platform-core  
**Deliverables:**
- Identity snapshot models
- Tenant context propagation
- Shared error & audit contracts

**Exit Criteria:**
- All services consume shared contracts

---

## 3) Ownership & Staffing
- Each Epic has a Primary + Secondary owner
- Auth / Policy / Runtime owners must be senior engineers
- No shared ownership across Tier-0 repos

---

## 4) Phase 1 Exit Checklist (ALL REQUIRED)
- Control plane provisions tenant
- Auth subsystem issues sessions
- Runtime validates sessions + policies
- Policy engine enforces version gating
- No frozen-domain violations detected

---

## 5) Final Warning
Phase 1 success is measured by **correctness and discipline**, not velocity.

---
