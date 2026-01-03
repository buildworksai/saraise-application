# SARAISE Multi-Region Data Semantics & Compliance Matrix

**Status:** Draft v0.1 (authoritative, enforced)

This document defines **how SARAISE handles data across regions** while meeting regulatory, contractual, and operational guarantees.

Multi-region is not a performance feature. It is a **compliance and risk boundary**. If semantics are unclear, the platform is unsafe.

---

## 0) Ruthless Principles

1. **Region is a hard boundary.** Data does not move unless explicitly allowed.
2. **Compliance beats convenience.** Latency optimizations never override law.
3. **Tenants choose residency, not engineers.** Defaults are conservative.
4. **Replication is explicit.** Nothing is “eventually global” by accident.
5. **Isolation scales down as well as up.** Single-region is the safest default.

---

## 1) Region, Zone, and Residency Definitions

### 1.1 Region
A cloud provider region (e.g., `us-east-1`, `eu-central-1`).

### 1.2 Residency Zone
A logical grouping of regions that share legal data-transfer allowances.

Examples:
- `EU` (EU member states only)
- `US`
- `APAC`

### 1.3 Tenant Residency Policy
Every tenant has exactly one **primary residency region**.

Optional:
- one or more **secondary regions** (only if compliant)

---

## 2) Tenant Deployment Models

### 2.1 Single-Region (Default)

- All data stored and processed in one region
- No cross-region replication
- Lowest cost, lowest risk

### 2.2 Active–Passive Multi-Region

- Primary region handles all writes
- Secondary region receives replicated data
- Used for DR, not active workloads

### 2.3 Active–Active Multi-Region (Restricted)

- Multiple regions accept writes
- Allowed **only** for tenants that:
  - explicitly contract for it
  - accept higher cost and complexity
  - have compatible compliance requirements

---

## 3) Data Classification (Mandatory)

Every data element is classified. Unclassified data defaults to **restricted**.

| Class | Description | Cross-Region Allowed |
|-----|------------|----------------------|
| Public | Non-sensitive | Yes |
| Internal | Business internal | Conditional |
| Confidential | Customer data | Rare |
| Regulated | PII, financial, health | No (by default) |

Classification drives replication rules.

---

## 4) Data Movement Rules

### 4.1 Hard Rules

- Regulated data **never** leaves residency region unless law explicitly allows
- No silent replication
- No ad-hoc engineer-driven data copies

### 4.2 Replication Approval Matrix

| Data Class | Single → Multi | EU → Non-EU | Non-EU → EU |
|-----------|----------------|-------------|-------------|
| Public | Allowed | Allowed | Allowed |
| Internal | Allowed | Restricted | Restricted |
| Confidential | Approval required | Forbidden | Forbidden |
| Regulated | Forbidden | Forbidden | Forbidden |

---

## 5) Storage Semantics by Region

### 5.1 OLTP Databases

- Region-bound
- No cross-region writes
- Read replicas allowed only within residency zone

### 5.2 Audit & Event Stores

- Primary copy stays in-region
- Redacted or hashed replicas allowed for global monitoring

### 5.3 Object Storage (S3 / GCS)

- Buckets are region-specific
- Cross-region replication disabled by default

### 5.4 Search Indexes

- Indexes are region-scoped
- No global search across restricted data

---

## 6) Backup, DR, and RPO/RTO Tiers

### 6.1 Backup Rules

- Backups stored in same residency zone
- Encryption mandatory
- Retention driven by tenant policy

### 6.2 RPO/RTO Tiers

| Tier | RPO | RTO | Notes |
|----|-----|-----|------|
| Standard | 24h | 24h | Default |
| Enhanced | 1h | 4h | Higher cost |
| Premium | Minutes | <1h | Dedicated infra |

---

## 7) Control Plane vs Runtime Plane Responsibilities

### Control Plane

- Enforces residency policy
- Validates region placement
- Orchestrates replication
- Blocks illegal configurations

### Runtime Plane

- Executes within assigned region
- Refuses cross-region data access
- Emits residency violations as security events

---

## 8) Tenant Isolation & Compliance Escalation

Triggers for stronger isolation:
- Regulatory change
- Tenant compliance audit findings
- Data breach or near miss

Escalation options:
- Dedicated region
- Dedicated shard
- Dedicated encryption keys

---

## 9) Observability & Audit

Mandatory signals:
- Cross-region access attempts (blocked or allowed)
- Replication lag
- Residency violations

All events are tenant-scoped and immutable.

---

## 10) What Is Explicitly Forbidden

- Global databases spanning regions
- Engineer-initiated data exports
- Bypassing residency via analytics or AI
- “Temporary” compliance exceptions

---

## 11) Final Warning

Multi-region failures are rarely technical — they are **governance failures**.

This matrix exists to ensure SARAISE never violates trust, law, or contract under pressure.

---

**End of document**

---
