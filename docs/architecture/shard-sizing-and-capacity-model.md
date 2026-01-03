# SARAISE Shard Sizing & Capacity Model

**Status:** Draft v0.1 (authoritative, enforced)

This document defines **how SARAISE scales safely**: shard boundaries, capacity envelopes, saturation signals, and split mechanics.

If you do not quantify capacity, you are not designing a platform — you are guessing.

---

## 0) Ruthless Principles

1. **Shards are operational units, not abstractions.** Everything scales by shards.
2. **No shard grows unbounded.** Every shard has hard ceilings.
3. **Saturation is detected early.** We split *before* failure.
4. **Capacity math beats optimism.** Numbers win arguments.
5. **Isolation tiers reuse the same model.** Dedicated tenants are just shards of size 1.

---

## 1) What a Shard Is (Precisely)

A shard is the **smallest independently operable unit** of the runtime plane.

A shard contains:
- Runtime API services
- Background workers
- Redis (or logical Redis allocation)
- Postgres OLTP database
- Postgres Audit/Event database
- OpenSearch index allocation

A shard is:
- deployed
- upgraded
- migrated
- throttled
- split

**as a unit**.

---

## 2) Tenant Classes (Capacity Drivers)

Tenants are not equal. Capacity modeling starts by classifying them.

### 2.1 Tenant Size Classes

| Class | Provisioned Users | Peak Concurrent | Notes |
|-----|-------------------|-----------------|-------|
| XS  | < 100             | < 10            | long tail |
| S   | 100–1k            | 10–50           | SMB |
| M   | 1k–5k             | 50–200          | core market |
| L   | 5k–20k            | 200–800         | enterprise |
| XL  | >20k              | >800            | usually isolated |

**Rule:** XL tenants never live on shared shards.

---

## 3) Capacity Dimensions (What Actually Breaks First)

Shards are constrained by multiple independent limits.

### 3.1 Primary Dimensions

1. **Concurrent requests** (API threads + DB connections)
2. **Database size** (OLTP + audit)
3. **Write IOPS** (transactions, events)
4. **Background job throughput** (backfills, workflows)
5. **Search index size & query rate**
6. **Network egress** (integrations, exports)

A shard is considered *full* when **any one** dimension hits its ceiling.

### 3.2 AI & Agent Execution Capacity (First-Class Dimension)

AI workloads are treated as a separate, non-negotiable capacity dimension.

AI capacity is constrained by:
- concurrent agent executions
- LLM token throughput (input + output)
- tool invocation rate
- external egress bandwidth

AI capacity exhaustion MUST NOT impact core transactional workloads.
---

## 4) Default Shared Shard Envelope (Baseline)

This is the *maximum allowed* envelope for a shared shard.

### 4.1 OLTP Postgres (per shard)
- Max DB size: **2 TB**
- Max tables >100GB: **0** (partition instead)
- Max sustained TPS: **5,000**
- Max concurrent connections: **500**

### 4.1A Connection Pool Budgeting (Hard Allocation)

Database connections are a finite, aggressively managed resource.

Given:
- Max concurrent connections per shard: **500**

Mandatory reserves:
- Migration & online DDL reserve: **30**
- Admin / break-glass reserve: **10**
- Replication / maintenance reserve: **variable (cloud-managed)**

Usable connection budget (default): **460**

Allocation model:
- API services: **60%** of usable budget
- Background workers: **40%** of usable budget

Per-pod allocation is computed deterministically:

```
max_connections_per_pod = floor(service_pool_budget / number_of_pods)
```

CI validation fails if cumulative configured pools exceed shard allocation.

Connection starvation is treated as a shard saturation signal.

### 4.2 Audit/Event Postgres
- Append-only
- Max DB size before archive/rollover: **3 TB**
- Write-optimized; read is secondary

### 4.3 Runtime API
- Max sustained RPS: **8,000**
- p95 latency SLO: **< 200ms**

### 4.4 Background Workers
- Max concurrent jobs: **10,000**
- Backfills are throttled separately

### 4.5 OpenSearch Allocation
- Max index size per shard allocation: **1 TB**
- Max query rate: **2,000 QPS**

These numbers are **ceilings**, not targets.

## 4.6 Session Store Capacity (Mandatory)

Because SARAISE uses server-managed sessions, session storage is a first-class capacity dimension.

### Assumptions
- Session TTL (base): 30 minutes
- Rolling renewal on activity
- Peak login storms: up to 3× normal concurrent users

### Capacity Model (per shard)
- Peak concurrent users: derived from tenant mix
- Active sessions ≈ peak concurrent users × 1.2
- Login storm buffer: × 3

Session store must sustain:
- session reads on every request
- write bursts during login and rotation

Session storage is:
- region-bound
- encrypted at rest
- capacity-monitored

Session exhaustion is treated as a **SEV-1** event.

---

## 4.7 AI Agent Capacity Envelope (Per Shard)

This defines the maximum AI workload allowed on a shared shard.

### Per-Shard Ceilings
- Max concurrent AI agents: **500**
- Max LLM tokens / minute (aggregate): **5 million**
- Max tool invocations / second: **1,000**
- Max external egress (AI-driven): **200 Mbps**

AI workloads are throttled independently from API traffic.

Once any AI ceiling reaches 70%, the shard is marked **AI-saturated**.

## 5) Tenant Density Targets (Shared Shards)

Based on real-world ERP usage patterns:

| Tenant Class | Target Count / Shard |
|-------------|----------------------|
| XS          | 5,000–10,000         |
| S           | 500–1,000            |
| M           | 100–300              |
| L           | 10–30                |

**Mixing rule:**
- Shards must not contain >20% L-class tenants
- M-class tenants dominate shared shards

---

## 5A) Per-Tenant Fairness & Quota Enforcement

Shard math assumes tenants behave within class boundaries. This is enforced.

Per-tenant quotas are mandatory across three layers:

### API Layer
- Sustained RPS cap per tenant
- Burst RPS cap per tenant
- Concurrent request cap

### Background Job Layer
- Max queued jobs per tenant
- Max concurrent jobs per tenant
- Backfill throughput cap

### Search Layer
- Query QPS cap per tenant
- Result window size limits
- Aggregation and query complexity limits

Quota violations trigger throttling, not failure, and emit audit events.

Tenants that consistently exceed quotas are candidates for isolation.

## 5B) Default Per-Tenant Quota Numbers (Authoritative)

These are enforced defaults. Overrides require isolation or commercial approval.

### API Layer (per tenant)

| Class | Sustained RPS | Burst RPS | Concurrent Requests |
|------|---------------|-----------|---------------------|
| XS   | 5             | 20        | 10                  |
| S    | 20            | 100       | 50                  |
| M    | 50            | 250       | 150                 |
| L    | 200           | 800       | 500                 |

### Background Jobs (per tenant)

| Class | Max Concurrent Jobs | Queue Depth |
|------|---------------------|-------------|
| XS   | 5                   | 100         |
| S    | 20                  | 500         |
| M    | 50                  | 2,000       |
| L    | 200                 | 10,000      |

### Search Layer (per tenant)

| Class | QPS | Max Window | Complexity |
|------|-----|------------|------------|
| XS   | 2   | 1,000      | Low        |
| S    | 10  | 5,000      | Medium     |
| M    | 25  | 10,000     | Medium     |
| L    | 100 | 20,000     | High       |

Tenants exceeding these limits are throttled and flagged for isolation review.

---

## 5C) Default Per-Tenant AI Quotas (Authoritative)

AI quotas are enforced per tenant and per shard.

### AI Agent Execution

| Class | Max Concurrent Agents | Max Tokens / Minute |
|------|----------------------|---------------------|
| XS   | 2                    | 10,000              |
| S    | 10                   | 50,000              |
| M    | 25                   | 200,000             |
| L    | 100                  | 1,000,000           |

### Tool Invocation Rate

| Class | Max Tool Calls / Min |
|------|----------------------|
| XS   | 200                  |
| S    | 1,000                |
| M    | 5,000                |
| L    | 20,000               |

Quota violations result in:
- AI throttling
- agent queueing
- audit events

Repeated violations trigger isolation review.

## 6) Saturation Signals (Split Triggers)

A shard enters **pre-split** state when any of the following holds for sustained periods:

- OLTP DB size > **70%** of max
- Sustained TPS > **65%** of ceiling
- p95 latency > **150ms** for 15 min
- Background job queue depth growing
- OpenSearch index > **70%** allocation

- AI agent concurrency > **70%** of shard ceiling
- Sustained LLM token throughput > **65%** of shard ceiling
- Tool invocation backlog growth

**At 85%**, shard is **hard-blocked** from new tenants.

---

## 7) Shard Split Strategy

### 7.1 Split Types

1. **Horizontal split** (tenant reassignment)
   - Move subset of tenants to new shard

2. **Vertical split** (service separation)
   - Rare; only for extreme workloads (ledger, analytics)

### 7.2 Split Process (Horizontal)

1. Freeze tenant placement
2. Select tenant set to move
3. Provision new shard
4. Migrate tenant data (controlled, audited)
5. Update routing in control plane
6. Resume writes

No tenant is split across shards.

### 7.3 Shard Split Mechanics (Operational)

Split execution rules:
- Writes are paused per-tenant during cutover
- No dual-write logic is permitted
- Data migration is verified using:
  - row counts
  - checksums
  - application-level invariants

Rollback:
- Routing is reverted
- Source shard resumes ownership
- Partial migrations are discarded

Shard splits are designed to be **routine, not exceptional**.

---

## 8) Dedicated & Isolated Tenants

### 8.1 Dedicated DB (Shared Compute)
- One tenant
- One DB
- Shared runtime

### 8.2 Dedicated Shard (Full Isolation)
- One tenant
- One shard
- Custom capacity envelope

Dedicated shards follow the **same rules**, just with different ceilings.

---

## 8A) Isolation Decision Triggers (Non-Negotiable)

A tenant is forcibly moved to isolated infrastructure if ANY condition below is met.

### Performance Triggers
- Tenant contributes > **15%** of shard TPS for 30 minutes
- Tenant contributes > **20%** of shard CPU for 30 minutes
- Tenant OLTP DB footprint > **200 GB** on shared shard
- Tenant audit/event footprint > **500 GB**
- Tenant search index footprint > **150 GB**
- Tenant repeatedly causes p95 latency SLO breaches

### Compliance Triggers
- Regulatory requirement for physical or logical isolation
- Customer-managed encryption keys (CMK)
- Restricted cross-tenant blast radius requirement

### Commercial Triggers
- Enterprise isolation SLA tier
- Contractual noisy-neighbor protection clauses

Isolation decisions are made by the control plane and are auditable.

### AI-Specific Triggers

- Tenant consumes > **20%** of shard AI token budget for 30 minutes
- Tenant runs > **25%** of concurrent agents on shard
- Tenant AI workload causes API latency degradation

AI-driven isolation decisions are audited and irreversible without review.

---

## 9) Multi-Region Considerations (Preview)

- Shard is region-bound
- Tenant data never spans shards across regions
- Replication/failover handled outside shard sizing

(Full semantics defined in Multi-Region Compliance doc.)

## 9A) Session & Auth Implications

- Sessions are region-affined
- Shards do not share session stores across regions
- Cross-region access requires re-authentication

Auth capacity must be provisioned per-region and per-shard.

---

## 10) Capacity Planning Workflow

1. Estimate tenant mix
2. Project per-tenant load
3. Compute shard count
4. Add 30% headroom
5. Continuously re-evaluate

Capacity plans are revisited **quarterly** at minimum.

---

## 10A) Shard Demand Forecast Model (1M+ Tenants)

Capacity forecasting is based on tenant mix, not total tenant count.

### Required Inputs (per tenant class)
- Peak concurrent users
- Peak RPS
- Monthly OLTP DB growth (GB)
- Monthly audit/event growth (GB)
- Monthly search index growth (GB)

### Forecast Calculation

For each dimension:

- Shards_by_RPS = total_peak_rps / shard_rps_ceiling
- Shards_by_DB  = total_db_size / shard_db_ceiling
- Shards_by_Search = total_search_size / shard_search_ceiling

Final required shard count:

```
required_shards = max(all_dimensions) * (1 + headroom)
```

Default headroom: **30%**.

Forecasts are reviewed quarterly and drive provisioning automation.

## 10B) Deterministic Shard Placement Algorithm

Shard selection is algorithmic, not discretionary.

Placement score inputs:
- available headroom across all dimensions
- tenant class compatibility
- compliance constraints
- session capacity headroom

Shards failing ANY constraint are excluded.

The shard with the highest composite score is selected.

Manual placement is forbidden.

---

## 11) What Is Explicitly Forbidden

- Unlimited shard growth
- Manual tenant placement
- Emergency over-allocation “just this once”
- Ignoring saturation signals
- Overriding isolation triggers for commercial convenience
- Allowing tenants to exceed quotas without isolation review
- Operating shards without explicit session capacity monitoring

---

## 12) Final Warning

Most platforms fail not because they cannot scale — but because they scale **too late**.

This model exists to ensure SARAISE scales *before* it hurts.

---

**End of document**

---
