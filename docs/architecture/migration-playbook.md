# SARAISE Migration Playbook

**Status:** Draft v0.1 (authoritative, enforced)

This document defines **how schema, data, and behavior change over time** in SARAISE without outages, corruption, or cross-tenant incidents.

If you treat migrations as “just Django migrations”, you will destroy the platform.

---

## 0) Absolute Laws (Read This Twice)

1. **Migrations are production incidents waiting to happen.** Treat them as such.
2. **Schema and code are deployed independently.** They are never assumed to be in lockstep.
3. **Subscriptions do not control schema.** Schema is global per product version.
4. **No migration is allowed to block production traffic.** Ever.
5. **Roll forward > roll back.** Downgrades are last-resort damage control.

Any migration that violates these laws is rejected.

---

## 1) Migration Types

### 1.1 Schema Migrations
- Table creation
- Column addition
- Index creation

### 1.2 Data Migrations (Backfills)
- Populating new columns
- Transforming existing data
- Repairing historical inconsistencies

### 1.3 Behavioral Migrations
- Changes in interpretation of existing data
- Workflow or policy changes

**All three must be planned together.**

---

## 2) Expand / Contract Pattern (Mandatory)

### 2.1 Expand Phase
Allowed operations:
- Add nullable columns
- Add new tables
- Add indexes **concurrently**
- Add triggers/functions that do not block

Forbidden operations:
- Dropping columns
- Renaming columns
- Changing column types
- Adding NOT NULL constraints

### 2.2 Compatibility Window
After expand:
- Old code continues to function
- New code must tolerate old + new schema
- Dual-write may be required

### 2.2A Schema Compatibility Guarantees

The platform guarantees schema compatibility across versions as follows:

- Runtime code must support:
  - current schema
  - previous expanded schema

- Minimum compatibility window:
  - **2 consecutive minor versions** or **30 days**, whichever is longer

- Isolated tenants may lag upgrades only within this window

After the window expires, forward-fix is mandatory.

### 2.3 Backfill Phase
- Runs asynchronously
- Chunked and resumable
- Rate-limited per shard
- Progress is tracked centrally

### 2.4 Contract Phase
Only after:
- Backfill completion
- Metrics show no fallback reads

Allowed:
- Remove old columns
- Remove old indexes

Contract is **never urgent**. Delay it if uncertain.

---

## 3) What Is Explicitly Forbidden

The following will **never** be approved:
- Table rewrites on large tables
- Blocking index creation
- Long-running transactions
- Per-tenant schema divergence
- “Quick fixes” in production

Violations here justify immediate rollback and incident declaration.

---

## 4) Shard-Aware Migration Orchestration

### 4.1 Control Plane Responsibility
The control plane:
- Selects shard batches
- Applies migrations per batch
- Enforces health gates
- Pauses rollout on error

### 4.2 Rollout Waves
Typical rollout:
1. Canary shard
2. Small batch (5–10%)
3. Majority
4. Long-tail shards

No skipping steps.

### 4.3 Health Gates
Migration halts if:
- p95 latency spikes
- error rate exceeds threshold
- DB lock time exceeds budget

### 4.4 Lock Budgets (Hard Limits)

Lock budgets are enforced, not advisory.

For Postgres:
- Hot tables (high QPS):
  - Max lock hold time per statement: **≤ 50ms**
  - ACCESS EXCLUSIVE locks during business hours: **FORBIDDEN**

- Warm tables:
  - Max lock hold time: **≤ 200ms**

- Cold tables:
  - Max lock hold time: **≤ 1s** (still monitored)

Index rules:
- `CREATE INDEX CONCURRENTLY` is mandatory on non-empty tables
- Any migration generating ACCESS EXCLUSIVE locks on hot tables is rejected

Lock budget violations automatically pause rollout.

---

## 5) Module Migration Rules

### 5.1 Ownership
- Modules own migration definitions
- Platform owns execution order

### 5.2 Dependency Ordering
- Module dependencies define migration order
- Cyclic dependencies are forbidden

### 5.2A Module Ordering Enforcement

Migration execution order is derived from the module dependency DAG defined in the Module Framework.

Rules:
- Core modules migrate first
- Domain modules next
- Industry modules next
- Integration modules last

If a dependency migration fails:
- the failing module is blocked
- dependent modules are not executed
- shard rollout pauses automatically

### 5.3 Failure Semantics
If a module migration fails:
- Dependent modules are blocked
- Partial progress is preserved
- No forced retries without investigation

---

## 6) Backfills (Where Most Teams Screw Up)

### 6.1 Mandatory Properties
Every backfill must be:
- idempotent
- resumable
- tenant-aware
- rate-limited

### 6.2 Execution Model
- Background workers only
- No inline backfills during API requests

### 6.3 Observability
- Progress per shard
- Progress per tenant (where applicable)
- Error counts and retries

---

## 6A) Backfill Safety Tests (Mandatory)

Every backfill must pass the following tests before merge:

- Dry-run on production-like dataset
- Estimated runtime calculation per shard
- Verification of idempotency markers
- Checkpoint persistence test
- Rate-limit enforcement test

Backfills without safety tests are rejected.

---

## 7) Downgrades (The Ugly Truth)

### 7.1 Code Downgrades
- Allowed within compatibility window
- Must tolerate expanded schema

### 7.2 Schema Downgrades
- Discouraged
- Only allowed for:
  - unused columns
  - feature-flagged additions

**Default strategy:** forward fix.

---

## 8) Multi-Region Considerations

### 8.1 Region-Pinned Tenants
- Migrations run in-region
- No cross-region schema drift

### 8.2 Failover Windows
- Migrations do not run during failover
- Backfills pause during regional instability

---

## 9) Data Safety & Compliance

- Backfills respect retention rules
- No resurrection of deleted data
- Audit events emitted for migration actions

---

## 10) Pre-Merge Checklist (Release Blocker)

A migration cannot be merged unless:
- Expand/contract plan documented
- Backfill strategy defined
- Lock impact analyzed
- Rollout wave defined
- Rollback story written
- Lock budget classification (hot/warm/cold)
- Schema compatibility window impact assessed
- Backfill runtime estimate documented
- Module dependency order validated

---

## 11) Incident Response for Migrations

If a migration causes impact:
1. Freeze rollout
2. Preserve state
3. Communicate
4. Forward-fix
5. Postmortem is mandatory

---

## 11A) Migration Failure Modes & Safe Degradation

The platform must degrade safely under migration failure.

Allowed degradations:
- Switch affected modules to `read_only`
- Block dependent modules
- Pause background jobs for affected tables

Forbidden actions:
- Forced retries without analysis
- Manual schema edits
- Bypassing expand/contract discipline

All degradations are audited events.

---

## 12) Final Warning

Most platforms don’t fail because of code. They fail because of **migrations done casually**.

This playbook exists so you don’t learn that lesson the hard way.

---

**End of document**

---
