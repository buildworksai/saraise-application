# ABAC Attributes Architecture

> **Verification Note (Architecture Board)**
> This document is readable, authoritative, and freeze-blocking.
> It explicitly defines:
> - ABAC attribute categories
> - Authoritative attribute sources
> - Freshness SLAs
> - Embedding vs lookup rules
> - Forbidden behaviors
> 
> Any implementation MUST comply with this specification.

**Status:** Authoritative – Freeze Blocking

This document defines the **only allowed architecture** for Attribute-Based Access Control (ABAC) attributes in SARAISE.

Its purpose is to eliminate ambiguity around **where attributes come from**, **how fresh they must be**, and **how they are evaluated at scale**.

If this document is violated, authorization correctness and platform performance will fail.

---

## 0) Non-Negotiable Principles

1. **Attributes are data, not logic**
2. **Attribute freshness is explicit**
3. **No unbounded lookups during request-time authorization**
4. **Attributes never imply permissions**
5. **Attribute sourcing is deterministic and auditable**

---

## 1) Attribute Categories (Exhaustive)

All ABAC attributes MUST belong to exactly one of the following categories.

### 1.1 Subject Attributes

Attributes describing the authenticated subject.

Examples:
- org_unit
- department
- cost_center
- employment_type
- clearance_level

Characteristics:
- Relatively static
- Changes are infrequent
- High reuse across requests

---

### 1.2 Resource Attributes

Attributes describing the resource being accessed.

Examples:
- data_classification
- owner_org
- record_state
- sensitivity_level

Characteristics:
- Stored with the resource
- Indexed where used in policy conditions
- Evaluated per-request

---

### 1.3 Contextual Attributes

Attributes derived from request context or environment.

Examples:
- request_time
- request_region
- ip_risk_score
- device_trust_level

Characteristics:
- Computed at request time
- Never stored in sessions
- Bounded computation only

---

### 1.4 Derived Attributes

Attributes computed from other attributes.

Examples:
- is_manager
- is_cross_region_access
- is_high_risk_context

Characteristics:
- Deterministic
- Pure functions only
- No I/O allowed

---

## 2) Authoritative Attribute Sources

### 2.1 Subject Attribute Sources

| Attribute Type | Source | Update Mechanism |
|---------------|--------|------------------|
| Org structure | Identity service / HR sync | Event-driven |
| Employment data | SCIM / Directory | Event-driven |
| Clearance | Governance service | Manual + audit |

Rules:
- Subject attributes are resolved **at authentication time**
- Embedded into the **identity snapshot**, not permissions

---

### 2.2 Resource Attribute Sources

| Attribute Type | Source |
|---------------|--------|
| Business data | Application DB |
| Compliance flags | Governance DB |

Rules:
- Resource attributes are loaded with the resource
- Must be queryable without N+1 lookups

---

### 2.3 Contextual Attribute Sources

| Attribute | Source |
|----------|--------|
| Time | Runtime clock |
| Region | Request routing |
| Risk score | Security service |

Rules:
- Contextual attributes are computed inline
- External calls during evaluation are forbidden

---

## 3) Attribute Freshness SLAs

| Attribute Category | Freshness SLA |
|-------------------|---------------|
| Subject | ≤ 5 minutes |
| Resource | Immediate |
| Contextual | Real-time |
| Derived | Real-time |

Violations of freshness SLAs result in **deny-by-default**.

---

## 4) Embedding vs Lookup Rules

### 4.1 Embedded Attributes

Allowed:
- Subject attributes

Rules:
- Embedded into identity snapshot
- Invalidated via policy_version change

---

### 4.2 Lookup Attributes

Allowed:
- Resource attributes

Rules:
- Loaded as part of resource access
- Indexed and queryable

---

### 4.3 Computed Attributes

Allowed:
- Contextual and derived attributes

Rules:
- Must be pure
- Must be deterministic
- Must be bounded in time

---

## 5) Runtime Evaluation Model

Authorization evaluation receives:
- identity snapshot (subject attributes)
- resource attributes
- contextual attributes
- derived attributes

The Policy Engine:
- evaluates policies
- does not fetch attributes dynamically
- does not mutate attribute state

---

## 6) Caching Rules

- Subject attributes may be cached inside the Policy Engine
- Resource attribute caches must respect data ownership boundaries
- Contextual attributes are never cached

No attribute cache may outlive its freshness SLA.

---

## 7) Multi-Region Considerations

- Subject attributes are region-replicated via identity sync
- Resource attributes follow data residency rules
- Contextual attributes are region-local

Cross-region attribute reads are forbidden unless explicitly approved.

---

## 8) What Is Explicitly Forbidden

- Database lookups inside policy evaluation
- Fetching attributes from external systems at request time
- Storing attributes in sessions as permissions
- Inferring attributes implicitly from roles
- Using stale attributes beyond SLA

Violations are treated as authorization defects.

---

## 9) Audit & Observability

Mandatory logging:
- attribute source used
- attribute freshness status
- deny due to attribute unavailability or staleness

These logs are tenant-scoped and immutable.

---

## 10) Final Warning

ABAC correctness fails silently when attribute sourcing is ambiguous.

This document exists to prevent that failure mode at scale.

---

**Verification Checksum**
- Document: abac-attributes-architecture.md
- Purpose: ABAC sourcing, freshness, evaluation rules
- Status: Freeze-ready

---

**End of document**

---
