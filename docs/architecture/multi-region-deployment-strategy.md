# SARAISE Multi-Region Deployment Strategy

**Status:** Draft v0.1 (authoritative, enforced)

This document defines the deployment topology, routing, and operational rules for multi-region SARAISE deployments. It is subordinate to the compliance matrix in `docs/architecture/multi-region-data-semantics-and-compliance-matrix.md`.

---

## 1) Default Model

- **Single-region is default** for all tenants.
- Multi-region is an **explicit, contract-bound** configuration.
- No cross-region writes unless approved by residency policy.

---

## 2) Supported Topologies

### 2.1 Active-Passive (Default for Multi-Region)
- Primary region handles all writes.
- Secondary region is warm standby.
- Failover is manual or policy-driven, never automatic without approval.

### 2.2 Active-Active (Restricted)
- Allowed only with explicit compliance approval.
- Writes are partitioned by tenant or data class.
- Conflict resolution is prohibited for regulated data.

---

## 3) Control Plane Responsibilities

- Enforce residency rules before deployment.
- Validate region placement and replication settings.
- Block any configuration that violates the compliance matrix.

---

## 4) Runtime Plane Responsibilities

- Enforce region-bound data access.
- Emit residency violations as security events.
- Fail closed on cross-region access attempts.

---

## 5) Traffic Routing

- Global DNS routes traffic to the tenant's primary region.
- Regional load balancers distribute traffic within region.
- Failover routing requires control plane authorization.

---

## 6) Session Semantics

- Sessions are region-bound by default.
- Session validation must not cross region unless permitted by tenancy policy.

Reference: `docs/architecture/authentication-and-session-management-spec.md`

---

## 7) Data Replication Rules

- Replication is **explicit** and policy-governed.
- Regulated data does not replicate cross-region.
- Audit logs remain in-region; redacted replicas may exist for global monitoring.

Reference: `docs/architecture/multi-region-data-semantics-and-compliance-matrix.md`

---

## 8) Failover Process (Active-Passive)

1. Freeze writes in primary region.
2. Promote secondary region for reads.
3. Validate data consistency and replication lag.
4. Switch primary designation via control plane.
5. Resume write traffic after verification.

---

## 9) Observability Requirements

- Region-specific dashboards for latency, error rate, and replication lag.
- Alerts must include region and tenant context.
- Cross-region access attempts are SEV-1 events.

---

## 10) What Is Forbidden

- Global databases spanning regions
- Silent data replication
- Region changes without control plane approval
- Cross-region session validation for regulated tenants

---

**End of document**
