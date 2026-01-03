# SARAISE Module Framework

**Status:** Draft v0.1 (authoritative, non-negotiable)

This document defines how **modules are built, versioned, secured, migrated, and operated** inside SARAISE.

If you violate this framework, you do not have a “custom module” — you have a **platform defect**.

---

## 0) Ruthless Truths About Modules

1. Modules are the **largest attack surface** in the platform.
2. Modules are the **primary source of migration failures**.
3. Modules are where RBAC, ABAC, SoD, and AI safety most often break.

Therefore:
- Modules do **not** get architectural freedom.
- Modules conform to the platform — the platform does not bend for modules.

---

## 1) What a Module Is (and Is Not)

### 1.1 A Module *Is*
A module is a **versioned capability unit** that:
- exposes APIs
- defines permissions
- owns specific data models
- integrates with workflows
- participates in audit, search, and AI execution

### 1.2 A Module Is *Not*
- Not a microservice
- Not a separate deployment
- Not a schema fork
- Not a tenant-specific customization
- Not allowed to implement authentication, login, logout, session management, identity federation, or credential handling of any kind

There is **one codebase**, **one schema discipline**, **one runtime**.

---

## 2) Module Types

### 2.1 Core Modules
- Always present
- Form the platform spine
- Examples: Identity, Workflow, Audit, Document, Search

### 2.2 Domain Modules
- ERP functional domains
- Examples: Inventory, Procurement, Finance, HR, Projects

### 2.3 Industry Modules
- Industry-specific logic layered on domain modules
- Examples: Manufacturing MRP, Healthcare Billing Rules, Construction BOQ

### 2.4 Integration Modules
- External systems
- Examples: SAP, Salesforce, Banking APIs

---

## 3) Module Contract (Mandatory)

Every module MUST implement this contract.

### 3.1 Module Manifest
Each module provides a manifest:

```
name: finance-ledger
version: 1.3.0
description: General Ledger and posting engine
type: domain
lifecycle: managed   # managed | core | integration
dependencies:
  - core-identity >=1.0
  - core-workflow >=1.0
permissions:
  - finance.ledger:create
  - finance.ledger:post
  - finance.ledger:view
sod_actions:
  - finance.ledger:create
  - finance.ledger:approve
  - finance.ledger:post
search_indexes:
  - finance_ledger_entries
ai_tools:
  - post_journal_entry
```

### 3.2 Code Structure (per module)

```
/module_finance_ledger/
  __init__.py
  manifest.yaml
  models.py
  api.py
  permissions.py
  policies.py
  workflows.py
  ai_tools.py
  search.py
  migrations/
  backfills/
```

No file here is optional.

---

## 4) Permissions & Security Rules

### 4.1 Permission Declaration
- Permissions are declared explicitly and immutably
- Naming format is mandatory: `<module>.<resource>:<action>`
- Permission identifiers are globally unique
- No wildcards, no implicit inheritance

---

## 4A) Permission Registry & Collision Prevention

- All permissions are registered in a global permission registry at build time.
- Duplicate permission identifiers across modules are a hard failure.
- Registry validation runs in CI and blocks merge on collision.

Permission collisions are treated as security defects.

---

### 4.2 Role Binding
- Modules do NOT assign roles
- Modules only declare permissions
- Control plane binds permissions to roles

### 4.3 ABAC Integration
- Modules must declare ABAC attributes they support
- Policies are evaluated by the platform engine
- Modules cannot short-circuit policy evaluation

### 4.4 SoD Awareness
- Modules must declare SoD-relevant actions
- Workflow engine enforces SoD constraints

---

## 5) Data Models & Schema Discipline

### 5.1 Tenant Discipline
- All tenant-scoped tables include `tenant_id`
- No cross-tenant joins

### 5.2 Schema Evolution Rules
- No breaking changes
- No destructive migrations
- Expand/Contract pattern only

### 5.3 High-Risk Tables
- Ledger, payroll, compliance tables may require:
  - immutability
  - append-only patterns
  - optional DB-level RLS

---

## 6) Migrations & Backfills (Module-Owned, Platform-Orchestrated)

### 6.1 Migrations
- Modules own their migrations
- Platform orchestrates execution
- Migrations must be idempotent

### 6.2 Backfills
- All non-trivial migrations require backfills
- Backfills run asynchronously
- Backfills must be resumable and rate-limited

### 6.3 Subscription Reality
- Subscriptions do NOT control schema
- Subscriptions control access only

---

## 6A) Dependency Resolution & Ordering

### 6A.1 Deterministic Ordering

- Module dependencies form a directed acyclic graph (DAG).
- The platform computes a topological sort for:
  - migrations
  - backfills
  - enable/disable operations

### 6A.2 Ordering Rules

Execution order is fixed:
1. Core modules
2. Domain modules
3. Industry modules
4. Integration modules

Cyclic dependencies are forbidden and block release.

---

## 7) Search Integration

### 7.1 Index Declaration
- Modules declare search indexes
- Index schema must include:
  - tenant_id
  - object_type
  - access tags

### 7.2 Indexing Pipeline
- Writes emit events
- Background workers update indexes
- Search is eventually consistent

---

## 8) Workflow Integration

### 8.1 Workflow Hooks
- Modules define valid states
- Modules define transitions
- Workflow engine enforces approvals and SoD

### 8.2 Side Effects
- No side effects outside workflow transitions
- Direct writes that bypass workflows are forbidden

---

## 9) AI Integration (Non-Negotiable Constraints)

### 9.1 AI Tools
- Modules may expose AI tools
- Tools declare:
  - required permissions
  - input/output schema

### 9.2 Execution Rules
- AI tools execute under caller identity
- All actions are audited
- AI cannot bypass workflows or SoD

---

## 10) Module Versioning & Compatibility

### 10.1 Versioning
- Semantic versioning required
- Breaking changes are forbidden in minor versions

### 10.2 Compatibility Window
- Platform defines compatibility windows
- Old versions supported only within window

---

## 10A) Module State Machine (Operational Control)

Each module instance per tenant exists in exactly one state:

- `enabled`       : fully operational
- `read_only`     : reads allowed, mutations blocked
- `blocked`       : dependency failure or migration in progress
- `quarantined`   : security or data integrity violation detected
- `disabled`      : administratively turned off

### State Transition Rules

- `enabled → read_only` : during migrations or incident mitigation
- `enabled → blocked`  : dependency failure
- `enabled → quarantined` : security violation
- `read_only → enabled` : safe recovery

Transitions are platform-controlled and audited.

---

## 10B) Safe Module Disable Semantics

Disabling a module must not cause outages or data corruption.

When a module is disabled:
- In-flight workflows are:
  - completed if safe, or
  - paused in a recoverable state
- APIs return explicit "module disabled" errors
- Data becomes read-only unless explicitly allowed
- AI tools exposed by the module are de-registered
- Dependent modules transition to `blocked`

Module disable operations are reversible unless quarantined.

---

## 11) Industry Packages

Industry packages are:
- curated collections of modules
- configuration presets
- workflow templates

They are NOT forks.

---

## 12) Operational Guarantees

Every module must:
- be observable (metrics + logs)
- emit audit events
- respect rate limits
- fail safely

---

## 13) Module Review Gate (Release Blocker)

A module cannot ship unless:
- manifest validated
- permissions reviewed
- migrations reviewed
- SoD impact reviewed
- AI tools reviewed

No exceptions.

---

## 14) Consequences of Non-Compliance

If a module violates this framework:
- it is transitioned to `quarantined`
- any attempt to implement or bypass platform authentication is treated as a security violation
- it is removed from all industry packages
- dependent modules are blocked
- release pipelines are halted

This is deliberate and enforced.

---

**End of document**

---
