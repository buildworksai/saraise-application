

# SARAISE AI Agent Execution & Safety Specification

**Status:** Draft v0.1 (authoritative, enforced)

This document defines **how AI agents are allowed to exist, execute, and fail** inside SARAISE.

AI agents are the *highest-risk subsystem* in the platform. This spec exists to ensure they create leverage, not liability.

If an agent cannot operate within this model, it does not ship.

---

## 0) Ruthless First Principles

1. **Agents are not users.** They never have independent authority.
2. **Agents are not trusted.** All actions are constrained and verified.
3. **Agents do not improvise.** They execute bounded tools only.
4. **Agents cannot escalate privilege.** Ever.
5. **Agents must be interruptible.** Kill-switches are mandatory.
6. **Every agent action is attributable.** No anonymous execution.

---

## 1) What an AI Agent Is (and Is Not)

### 1.1 Definition
An AI agent is a **runtime execution entity** that:
- receives a goal or task
- reasons internally
- invokes **explicitly registered tools**
- acts **on behalf of a bounded principal**

### 1.2 An Agent Is NOT
- Not a superuser
- Not a background cron replacement
- Not allowed to call arbitrary code
- Not allowed to directly access databases
- Not allowed to bypass workflows

---

## 2) Agent Identity & Authority Model

### 2.1 Identity Resolution

Every agent execution resolves to exactly one of:
- **User-bound agent** (acts on behalf of a human user)
- **System-bound agent** (acts on behalf of a constrained system role)

No other identity types are allowed.

Agent identity is always evaluated in the context of an authentication boundary.

### 2.2 Authority Inheritance

Agents inherit:
- tenant_id
- subject_id
- effective roles
- active JIT grants

Agents inherit **nothing else**.

### 2.3 Authority Constraints

- Agents cannot add roles
- Agents cannot request JIT grants
- Agents cannot extend JIT TTLs
- Agents cannot cross tenant boundaries

---

### 2.4 Session Binding Semantics (Mandatory)

#### User-Bound Agents
- Must be created from an active, valid user session
- Session ID is bound to the agent execution
- Session validity is checked continuously
- Session expiration or invalidation immediately terminates the agent

#### System-Bound Agents
- Do not use user sessions
- Execute under tightly scoped system identities
- Are forbidden from impersonating users

Agents cannot persist authority beyond the lifetime of their bound session.

---

## 3) Agent Lifecycle

### 3.1 Lifecycle States

- `created`
- `validated`
- `running`
- `paused`
- `completed`
- `failed`
- `terminated`

All transitions are audited.

### 3.2 Creation Gate

An agent may be created only if:
- initiating principal is authenticated
- initiating principal has `agent:execute` permission
- task definition is validated

---

## 4) Tool-Centric Execution Model

### 4.1 Tool Registration

Agents may invoke **only tools** registered by modules.

Each tool must declare:
- name
- owning module
- required permissions
- input schema
- output schema
- side-effect classification

All tool schemas are validated at runtime.
Invalid inputs or outputs result in immediate tool invocation failure.

### 4.2 Tool Invocation Rules

Before every tool call:
1. Policy Engine evaluates permission
2. ABAC context is applied
3. SoD constraints are checked (if applicable)

If any check fails → tool call is denied.

### 4.3 Side-Effect Classes

Tools are classified as:
- `read_only`
- `workflow_transition`
- `data_mutation`
- `external_integration`

Higher-risk classes require stricter review and quotas.

---

### 4.4 Human Approval Gates (Non-Negotiable)

The following tool classes require human approval via workflow before execution:

- `data_mutation` affecting financial, HR, or compliance domains
- `external_integration` with write or destructive capability

Approval rules:
- Approval authority is governed by SoD policies
- Agents may propose actions but cannot self-approve
- Approval decisions are audited

---

## 5) Workflow Binding (Non-Negotiable)

Agents **cannot** directly mutate business-critical data.

Rules:
- All state changes must go through workflows
- Workflow engine enforces approvals and SoD
- Agents may propose actions, not bypass gates

This applies especially to:
- finance
- HR
- compliance

---

## 6) Hallucination Containment

### 6.1 Hard Constraints

Agents:
- cannot invent identifiers
- cannot fabricate entities
- cannot assume state without tool confirmation

### 6.2 Validation Loop

For every action proposal:
- agent must cite tool output or system state
- unverified assumptions are rejected

---

## 7) Execution Limits & Quotas

### 7.1 Time & Step Limits

- Max execution time per agent: **configurable, bounded**
- Max reasoning steps per agent: **bounded**

### 7.2 Resource Quotas

Per agent execution:
- tool call count limit
- external API call limit
- data volume limit

### 7.3 Tenant-Level Quotas

Agent activity counts against:
- tenant API quotas
- tenant job quotas
- tenant cost budgets

---

## 8) Kill Switches & Interruptibility

Agents must be stoppable at all times.

Kill mechanisms:
- manual terminate (admin)
- timeout expiry
- quota breach
- incident response trigger

Termination is immediate and audited.

---

## 9) Failure Modes & Safe Degradation

### 9.1 Allowed Failures

- agent fails closed
- partial task completion with rollback
- transition to human review

### 9.2 Forbidden Behaviors

- retry loops without bounds
- silent partial execution
- bypassing validation on retry

---

## 10) Audit & Explainability

Every agent execution emits:
- initiating principal
- agent identity
- task description
- tools invoked (with inputs/outputs summary)
- policy decisions
- workflow transitions
- final outcome

Audit records are tenant-scoped and immutable.

---

## 11) Security Controls

### 11.1 Prompt Injection Defense

- Strict separation of instructions vs data
- User-provided data never treated as instructions

### 11.2 Data Exposure Controls

- Agents receive only minimum required context
- No unrestricted memory access

---

### 11.3 Agent Memory & Retention Rules

- Agent memory is task-scoped and ephemeral
- No long-term cross-task memory is permitted by default
- Any retained context must be:
  - explicitly declared
  - tenant-scoped
  - compliance-reviewed

Logs and prompts:
- Do not store raw prompts containing sensitive data
- Redact PII and regulated data
- Retention follows tenant data retention policy

---

## 11A) External Egress Controls

- All external integrations must be explicitly allowlisted
- Per-tenant egress policies are enforced
- Credentials used by agents:
  - are short-lived
  - are scoped
  - are never exposed to the agent reasoning layer

Unauthorized egress attempts are blocked and audited.

---

## 12) Cost Attribution & Billing

Agent execution costs are attributed to:
- tenant
- module
- tool

Costs feed:
- billing
- quota enforcement
- abuse detection

---

## 13) Testing & Certification

An agent or tool cannot ship unless:
- permission checks tested
- failure paths tested
- quota enforcement tested
- audit completeness verified

---

## 14) What Is Explicitly Forbidden

- Autonomous self-improving agents
- Agents with write access outside workflows
- Agents with wildcard permissions
- Agents running without audit

- Agents continuing execution after session invalidation
- Agents approving their own actions
- Persistent cross-task agent memory without explicit approval
- Unrestricted external network access

Violations are treated as security incidents.

---

## 15) Final Warning

AI agents multiply both capability and blast radius.

This spec exists to ensure SARAISE gets the former without suffering the latter.

---

**End of document**

---