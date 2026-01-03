# SARAISE Policy Definition Language & Storage Model

**Status:** Draft v0.1 (authoritative, enforced)

This document defines the **only allowed way** to express, store, version, evaluate, and audit authorization policies in SARAISE.

If a policy cannot be represented in this language, it does not exist.

---

## 0) Ruthless Principles

1. **Policies are data, not code.** No executable logic inside policies.
2. **Policies are deterministic.** Same inputs → same result.
3. **Policies are auditable artifacts.** Human-readable, diffable, versioned.
4. **Policies are tenant-scoped.** No cross-tenant bleed.
5. **Explicit deny is first-class.** Deny rules are not optional.

---

## 1) Policy Types

SARAISE supports exactly four policy types:

1. **RBAC Grant Policy** – maps roles to permissions
2. **ABAC Condition Policy** – constrains permissions with attributes
3. **Explicit Deny Policy** – hard blocks regardless of grants
4. **SoD Constraint Policy** – prevents conflicting actions

Anything else is forbidden.

---

## 2) Canonical Policy Envelope

Every policy, regardless of type, is wrapped in the same envelope.

```json
{
  "policy_id": "uuid",
  "policy_type": "RBAC | ABAC | DENY | SOD",
  "tenant_id": "tenant-uuid",
  "version": 3,
  "status": "active | disabled",
  "created_at": "2026-01-01T00:00:00Z",
  "created_by": "user|system",
  "description": "Human readable explanation",
  "spec": { }
}
```

Rules:
- `policy_id` is immutable
- `version` increments monotonically
- Disabled policies are retained (never deleted)

---

## 3) RBAC Grant Policy

### 3.1 Purpose
Defines which permissions a role grants.

### 3.2 Schema

```json
{
  "role": "finance_manager",
  "permissions": [
    "finance.ledger:create",
    "finance.ledger:post"
  ]
}
```

Rules:
- Permissions must exist in the global permission registry
- No wildcards
- No conditions here (RBAC is unconditional)

---

## 4) ABAC Condition Policy

### 4.1 Purpose
Constrains RBAC permissions based on runtime attributes.

### 4.2 Condition Language

Supported operators:
- `eq`, `neq`
- `in`, `not_in`
- `contains`
- `lt`, `lte`, `gt`, `gte`
- `between`

Logical composition:
- `and`, `or`, `not`

### 4.3 Schema

```json
{
  "applies_to_permissions": ["finance.ledger:post"],
  "conditions": {
    "and": [
      { "org_unit": { "in": ["APAC", "EMEA"] } },
      { "amount": { "lte": 100000 } }
    ]
  }
}
```

Rules:
- Missing attribute → condition fails
- All attributes are read-only inputs

---

## 5) Explicit Deny Policy

### 5.1 Purpose
Overrides all grants and conditions.

### 5.2 Schema

```json
{
  "denied_permissions": ["finance.ledger:post"],
  "conditions": {
    "eq": { "region": "EU" }
  }
}
```

Rules:
- Deny always wins
- Conditions optional; unconditional deny allowed

---

## 6) SoD Constraint Policy

### 6.1 Purpose
Prevents conflicting actions across workflows.

### 6.2 Schema

```json
{
  "conflicting_actions": [
    "finance.ledger:create",
    "finance.ledger:post"
  ]
}
```

Rules:
- Evaluated at workflow transition time
- Violations block execution

---

## 7) Policy Storage Model

### 7.1 Primary Store

- Policies stored in **PostgreSQL** (control plane)
- Indexed by `tenant_id`, `policy_type`, `status`

### 7.2 Versioning

- New version = new row
- Old versions retained
- Active version pointer maintained per policy_id

### 7.3 Distribution to Runtime

- Policies replicated to runtime shards
- Versioned, signed payloads
- Runtime treats policies as read-only

---

## 8) Policy Lifecycle

1. Draft
2. Validate (schema + lint)
3. Approve (optional workflow)
4. Activate
5. Monitor
6. Disable (never delete)

All transitions are audited.

---

## 9) Policy Linting (Mandatory)

Lint rules include:
- Over-broad permissions
- Missing deny rules where templates require them
- Conflicting ABAC conditions
- SoD gaps

Lint failures block activation.

---

## 10) Policy Evaluation Binding

- Policy Engine consumes compiled policies
- No dynamic execution
- Evaluation order is defined in `policy-engine-spec.md`

---

## 11) Audit & Explainability

For every decision:
- policy_ids evaluated
- version numbers
- condition outcomes
- final decision

This data feeds compliance and forensics.

---

## 12) What Is Explicitly Forbidden

- Embedding code or scripts in policies
- Tenant-specific schema logic
- Hidden implicit denies or allows
- Deleting policies

---

## 13) Final Warning

This language exists to prevent creative but unsafe authorization logic.

If someone says “the policy language is limiting,” that is a feature, not a bug.

---

**End of document**

---
