# SARAISE Policy Engine Specification

**Status:** Draft v0.1 (authoritative, enforced)

This document defines the **single source of truth** for authorization decisions in SARAISE.

If two teams can interpret authorization differently, the system is already insecure.

---

## 0) Non‑Negotiable Principles

1. **Authorization is deterministic.** Same inputs → same decision, always.
2. **Explicit deny always wins.** No exceptions, no overrides.
3. **Default deny.** Absence of permission is denial.
4. **Fail closed.** Engine failure, timeout, or partial context → deny.
5. **Policy evaluation is centralized.** No module implements its own auth logic.
6. **Performance is a contract.** Budgets are defined and enforced; caching is scoped and safe.
7. **Every decision is explainable.** Decisions emit reason codes suitable for audit and debugging.

---

## 1) Scope of the Policy Engine

The Policy Engine evaluates **every access decision** for:
- API requests
- Query filtering (row-level access)
- Workflow transitions
- Background jobs
- AI agent tool execution

If a code path bypasses the Policy Engine, it is a **security bug**.

### 1.1 Policy Definition Language (Source of Truth)

Policies are defined using the SARAISE Policy Definition Language and storage model.

- This spec defines **how** policies are evaluated.
- `Policy Definition Language & Storage Model.md` defines **what** a policy looks like (schema, operators, storage, versioning).

If a policy cannot be expressed in the Policy Definition Language, it does not exist.

---

## 2) Core Concepts

### 2.1 Entities

- **Subject**: the acting principal (user or system role)
- **Resource**: the object being accessed
- **Action**: the operation attempted
- **Context**: runtime attributes (ABAC inputs)

### 2.2 Identity Inputs

Every evaluation receives:
- `tenant_id`
- `subject_id`
- `subject_type` (user | system | agent)
- `roles[]`
- `groups[]`
- `session_context` (server‑validated session only; client‑provided identity is never trusted)
- `policy_version` (effective policy version bound to the authenticated session)

---

## 2A) Evaluation Interface (Inputs/Outputs)

### 2A.1 Required Inputs

Every authorization decision MUST provide:
- `tenant_id`
- `subject`:
  - `id`
  - `type` (user | system | agent)
- `resource`:
  - `type` (string)
  - `id` (string, optional)
  - `tenant_id` (must match request tenant)
  - `attributes` (optional key/value map)
- `action` (string)
- `context`:
  - `request_id`
  - `ip` (optional)
  - `device_posture` (optional)
  - `risk_score` (optional)
  - `time` (UTC timestamp)
  - `org_scope` (org_unit/site/project/cost_center as applicable)
- `identity_snapshot`:
  - `session_id` (opaque, server‑issued, tenant‑bound)
  - `policy_version`
  - `roles[]`
  - `groups[]`
  - `jit_grants[]` (time-bounded grants)

### 2A.2 Output Contract

The engine returns:
- `decision`: allow | deny
- `reason_codes[]`: one or more stable reason codes
- `applied_policies[]`: identifiers of policies evaluated (for audit/debug)
- `row_filters[]`: (optional) composable filter expressions for query-level enforcement

No caller may “reinterpret” these outputs.

---

## 3) Permission Model (RBAC)

### 3.1 Permission Format

```
<module>.<resource>:<action>

finance.ledger:post
inventory.stock:adjust
```

Rules:
- No wildcards
- No implicit inheritance
- Permissions are immutable identifiers

### 3.2 Role Model

- Roles are named permission bundles
- Roles are tenant‑scoped
- Roles may be assigned to users or groups

Roles **never** evaluate conditions. They only grant capabilities.

---

## 4) ABAC Model (Policy Conditions)

### 4.1 Attributes

ABAC conditions may reference:
- org_unit
- site
- project
- cost_center
- region
- data_classification
- time_window
- device_posture
- risk_score

### 4.2 Evaluation Rules

- ABAC conditions are evaluated **at runtime**
- Missing attribute → condition fails
- Conditions are AND‑ed unless explicitly declared OR

---

## 5) Segregation of Duties (SoD)

### 5.1 SoD Definition

SoD rules are defined as **conflicting action sets**.

Example:
```
create_invoice ↔ approve_invoice
approve_invoice ↔ post_invoice
```

### 5.2 Enforcement Point

SoD is enforced:
- at workflow transitions
- before side‑effects occur

SoD violations **block execution**, not warn.

---

## 6) Just‑In‑Time (JIT) Privileges

### 6.1 JIT Grant Model

JIT grants are:
- time‑bound
- scoped to specific permissions
- approval‑gated

### 6.2 Evaluation

Expired JIT grants are ignored automatically.

---

## 7) Evaluation Order (This Is Critical)

Authorization evaluation follows **exactly this order**:

1. **Tenant Boundary Validation**
   - `tenant_id` must be present
   - `resource.tenant_id` must match `tenant_id` (if present)
2. **Subject & Session Validation**
   - subject must be resolved (no anonymous)
   - session must exist, be server‑issued, and be valid
   - session must be bound to the same tenant_id
2A. **Policy Version Validation**
    - session.policy_version must be equal to runtime.current_policy_version
    - mismatch results in deny with reason code `DENY_POLICY_VERSION_STALE`
3. **Explicit Deny Policies**
4. **SoD Constraints** (for workflow/action-layer decisions)
5. **JIT Validity**
   - expired or unapproved grants are ignored
6. **RBAC Permission Match**
   - required permission exists in effective permission set
7. **ABAC Conditions**
   - policy conditions evaluated against runtime context
8. **Final Allow**

If any step fails → **DENY**.

This order is not configurable.

---

## 8) Query‑Level Enforcement (Row‑Level Access)

### 8.1 Required Inputs

For row‑level filtering, the engine returns:
- `allow: boolean`
- `row_filters: expression[]`

### 8.2 Rules

- Filters are additive
- Absence of filters means **deny all rows**
- Filters must be composable into ORM queries

---

## 9) AI Agent Evaluation

### 9.1 Identity Resolution

AI agents execute as:
- the initiating user
- or a bounded system role

No anonymous agent execution is allowed.

### 9.2 Tool Execution

Before a tool executes:
- Policy Engine evaluates permission
- Context includes tool input parameters

---

## 10) Caching Strategy (Performance Without Lying)

Caching is allowed only inside the Policy Engine runtime and MUST NEVER be stored in sessions.
Caching must not change the truth of an authorization decision.

### 10.1 Cacheable Elements

- Role → permission mappings
- Group → role mappings
- Static policy definitions (compiled form)

These caches exist only in runtime memory or short‑TTL infrastructure caches and are never embedded in session state.

### 10.2 Non-Cacheable Elements

- ABAC evaluations (must use current context)
- JIT grants (time-bounded)
- SoD constraints (workflow state dependent)
- Session validity (MUST be checked server‑side on every request; no long‑lived caching)

### 10.3 Cache Scope

- Cache is **tenant-scoped**.
- Cache keys must include: `tenant_id` and a version/etag.

### 10.4 Invalidation Rules

Cache is invalidated on:
- role change
- policy change
- group membership change
- SCIM sync updates affecting identity_snapshot

### 10.5 Staleness Budget

- RBAC caches may have a short staleness window (configurable) but MUST be bounded.
- Default staleness target: **≤ 60 seconds**.
- Any privileged-role grant or removal MUST trigger immediate invalidation.

If you cannot guarantee bounded staleness, you cannot cache it.

---

## 11) Failure Semantics

Fail closed is mandatory.

### 11.1 Hard Deny Conditions

Return **deny** if:
- Policy Engine is unavailable
- Evaluation times out
- Identity snapshot is missing/partial
- Required ABAC attributes are missing
- Resource tenant boundary cannot be validated
- Session is missing, expired, revoked, or fails server validation
- Session policy_version is stale or mismatched

### 11.2 Timeouts

- Callers MUST apply a hard timeout.
- On timeout → deny + reason code `ENGINE_TIMEOUT`.

### 11.3 Partial Outages

During partial outages, the platform may degrade:
- from allow-by-row-filters to deny-all-rows
- from optional features to safe failure

Degradation is allowed only if it reduces access, never if it expands access.

---

## 12) Audit Requirements

Every evaluation emits:
- subject
- resource
- action
- decision (allow/deny)
- reason codes

Audit volume is expected. Optimize storage, not logging.

---

## 12A) Reason Codes (Stable Taxonomy)

Reason codes are stable identifiers. They are not free-form strings.

Minimum required set:
- `ALLOW`
- `DENY_DEFAULT`
- `DENY_EXPLICIT`
- `DENY_TENANT_MISMATCH`
- `DENY_SUBJECT_INVALID`
- `DENY_SESSION_INVALID`
- `DENY_RBAC_MISSING`
- `DENY_ABAC_CONDITION`
- `DENY_SOD_VIOLATION`
- `DENY_JIT_EXPIRED`
- `DENY_JIT_NOT_APPROVED`
- `ENGINE_TIMEOUT`
- `ENGINE_UNAVAILABLE`
- `DENY_POLICY_VERSION_STALE`

All denies MUST include at least one deny reason code.

---

## 12B) Governance at Scale (Linting, Simulation, Drift Detection)

At 1M+ tenants, policy misconfiguration is inevitable. Governance is not optional.

### 12B.1 Policy Linting (CI Gate)

Policies MUST be linted for:
- over-broad permissions (e.g., roles with extreme permission counts)
- missing explicit denies where required by templates
- conflicting ABAC rules
- SoD conflicts not represented in workflows

### 12B.2 Policy Simulation

The platform MUST support simulation queries:
- “What can this role do?”
- “What resources are reachable under context X?”

Simulation is read-only and produces signed reports for audit.

### 12B.3 Drift Detection

The control plane MUST detect and alert on:
- high-privilege role creation
- permission explosion
- frequent JIT grants (standing privilege workaround)
- repeated SoD violations

These signals drive admin alerts and optional auto-remediation policies.

---

## 13) Testing Requirements

Every permission and policy path must have:
- allow test
- deny test
- ABAC missing-attribute deny test
- SoD violation test (where applicable)
- JIT expired/invalid deny test (where applicable)
- tenant boundary mismatch deny test

No tests → no merge.

---

## 14) What Is Explicitly Forbidden

- Module‑level auth logic
- Wildcard permissions
- Bypass flags
- “Trusted internal calls”
- Unbounded caching of authorization decisions
- Any “temporary allow” feature flags
- Trusting client‑supplied tokens or claims for interactive authorization decisions

---

## 15) Final Warning

If authorization is inconsistent, **nothing else matters** — not scale, not AI, not features.

This spec exists so that never happens.

---

**End of document**

---
