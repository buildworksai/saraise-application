# SARAISE Security Model

**Status:** Draft v0.1 (authoritative baseline)

This document defines the *security architecture, threat model, and enforcement controls* for SARAISE.

This is not a marketing document. It is a **design constraint**. If a feature violates this model, the feature does not ship.

---

## 0) Non‑Negotiable Security Principles

1. **Assume breach.** Design so that blast radius is limited by tenant, shard, role, and policy.
2. **Authorization > Authentication.** Knowing *who* someone is means nothing if you cannot strictly control *what they can do*.
3. **Deny by default.** Every permission, role, integration, and agent action must be explicitly allowed.
4. **No hidden privilege.** There are no “implicit admin” paths, no bypasses for AI, no developer shortcuts in production.
5. **Everything is auditable.** If it isn’t logged, it didn’t happen.
6. **Security is layered.** Failure of one control must not equal compromise.

---

## 1) Threat Model (What We Are Defending Against)

### 1.1 External Threats
- Credential theft / phishing
- Token/session replay
- API abuse (rate flooding, enumeration)
- Injection attacks (SQL, template, prompt injection)
- Supply chain attacks (dependencies, images)
- Misconfigured tenant integrations (IdP, SCIM, webhooks)

### 1.2 Internal / Tenant‑Side Threats
- Privilege escalation by tenant admins
- Lateral data access across org units or regions
- SoD violations (fraud risk)
- Excessive standing privileges
- Misuse of AI agents as privilege amplifiers

### 1.3 Platform‑Side Threats
- Cross‑tenant data leakage
- Migration or rollout mistakes
- Mis-scoped background jobs
- Debug or admin tooling exposure

---

## 2) Identity & Authentication

### 2.1 Authentication Methods (Authoritative)

SARAISE uses **server-managed, stateful sessions** as the primary authentication mechanism.

- Web UI and ERP application access:
  - Session-based authentication only
  - Secure, HTTP-only cookies
  - Server-side session validation

- JSON Web Tokens (JWTs) are **NOT** used for interactive user sessions.
- JWTs are permitted **only** for:
  - External API access
  - Service-to-service communication
  - Short-lived, scope-restricted integration tokens

Any feature that assumes client-trusted, long-lived tokens is forbidden.

### 2.2 Authentication Hard Rules
- Authentication establishes identity only; it grants **zero permissions**.
- All authenticated access requires:
  - a valid server-side session
  - tenant binding
  - continuous server validation
- Sessions are:
  - server-issued
  - server-invalidatable
  - tenant-scoped
  - bound to an authenticated identity

Stateless authentication for core application access is forbidden.

### 2.3 Session Security (Mandatory)

- Sessions are stored and validated server-side
- Session identifiers are opaque and non-derivable
- Secure cookie attributes are mandatory:
  - HttpOnly
  - Secure
  - SameSite=strict (or lax where integrations require)

Mandatory controls:
- Short TTL with rolling rotation
- Explicit session invalidation on:
  - logout
  - role or policy change
  - JIT privilege grant or expiry
  - suspicious activity
- Forced re-authentication on privilege elevation

Session replay or fixation is treated as a security incident.

### 2.4 Session Is NOT an Authorization Cache (Hard Invariant)

A session establishes **identity only**.

- Sessions MUST NOT store effective permissions
- Sessions MUST NOT cache role resolutions
- Sessions MUST NOT cache ABAC evaluations

All authorization decisions are evaluated at request time via the Policy Engine.

Treating a session as an authorization cache is a security defect.

---

## 3) Authorization Model (The Core of Security)

### 3.1 Entities
- **User** (local or federated)
- **Group / Security Group**
- **Role**
- **Permission** (`resource:action`)
- **Policy** (RBAC + ABAC conditions)

All authorization objects are **tenant‑scoped**.

### 3.2 DRBAC (Dynamic RBAC)
- Roles are defined by permissions
- Platform ships role templates
- Tenants may clone/modify roles within guardrails
- No role implicitly inherits “superuser” rights
- Role changes require audit logging

### 3.3 ABAC (Attribute‑Based Access Control)
Policies may include conditions on:
- org_unit
- site / plant / branch
- project
- cost_center
- region / residency zone
- classification (data sensitivity)
- time window
- device posture / risk score

ABAC is **evaluated at runtime** and cannot be cached blindly.

### 3.4 Enforcement Layers (All Required)

1. **API Layer** – reject unauthorized requests immediately
2. **Query Layer** – enforce row‑level filters
3. **Action Layer** – validate side‑effects (workflows, postings, approvals)

Bypassing any layer is a security bug.

---

## 4) Row‑Level Protection (RLP)

### 4.1 Default Strategy
- Mandatory `tenant_id` scoping in all queries
- App‑layer row filtering based on ABAC context

### 4.2 Database‑Enforced RLS (Selective)
- Enabled only for **highest‑risk domains** (e.g., payroll, ledger)
- Used as *defense‑in‑depth*, not as the primary mechanism

Reason: blanket RLS everywhere kills performance and developer velocity.

---

## 5) Segregation of Duties (SoD)

SoD is enforced, not documented.

### 5.1 SoD Rules
- Defined per tenant
- Expressed as conflicting role or action pairs

Examples:
- Creator ≠ Approver
- Approver ≠ Poster
- Poster ≠ Auditor

### 5.2 Enforcement Point
- Workflow transition validation
- Blocking, not warning
- Violations are auditable events

---

## 6) Just‑In‑Time (JIT) Privileges

Standing privilege is a liability.

### 6.1 JIT Model
- Privileged roles granted:
  - for a fixed TTL
  - with justification
  - via approval workflow

### 6.2 Mandatory Controls

- Forced re‑authentication is required on **privilege elevation**, defined as:
  - acquisition of any role not previously held
  - transition from non-privileged to privileged role
  - elevation into SoD-sensitive actions (e.g., approval, posting)

Enforcement:
- Existing sessions are invalidated
- User must re-authenticate
- New session reflects updated authority

Privilege elevation without re-authentication is forbidden.

---

## 7) AI Agent Security Model

AI is not a user. It is not trusted.

### 7.1 Identity of Agents
- Agents act **on behalf of a user or system role**
- Every agent execution carries:
  - initiating identity
  - effective permissions
  - scope limits

### 7.2 Hard Constraints
- Agents cannot bypass authorization checks
- Agents cannot escalate privileges
- Agents cannot access data outside the caller’s scope

### 7.3 Audit Requirements
- All agent actions are logged to the audit/event store
- Tool calls include:
  - input parameters
  - output summary
  - affected resources

---

## 8) Audit & Event Logging

### 8.1 What Is Logged (Mandatory)
- Auth events (session creation, rotation, invalidation, logout, failure)
- Role, policy, and permission changes
- Data mutations
- Workflow transitions
- JIT grants and expirations
- AI agent actions
- Integration calls

### 8.2 Properties
- Append‑only
- Tenant‑scoped
- Retention is policy‑driven
- Queryable for compliance and forensics

---

## 9) Secrets & Key Management

- No secrets in code or images
- All secrets stored in:
  - cloud KMS
  - or Vault (where portability is required)
- Regular rotation
- Separate keys per environment and per tenant tier where required

---

## 10) Network & Infrastructure Security

- TLS everywhere
- WAF at ingress
- Network policies between services
- No direct DB access from the internet
- Bastion access is audited and time‑bound

---

## 11) Application Security Controls

- Input validation at all boundaries
- Strict serialization/deserialization
- Rate limiting per tenant and per identity
- Protection against prompt injection in AI flows
- Feature flags are **not** a security boundary
- CSRF protection is mandatory for all session-authenticated endpoints

---

## 12) Supply Chain Security

- Minimal base images
- SBOM generation
- Signed Docker images
- Dependency scanning
- Reproducible builds where possible

---

## 13) Compliance & Tenant Isolation

### 13.1 Tenant Isolation
- Logical isolation by default
- Optional dedicated DB or dedicated stack

### 13.2 Compliance Controls
- Data residency enforcement
- Retention and deletion workflows
- Export controls
- Audit access segregation

---

## 14) Incident Response Expectations

- Detection via logs, metrics, alerts
- Kill‑switches for:
  - tenants
  - integrations
  - modules
- Forensic audit logs preserved
- Post‑incident review is mandatory

---

## 15) Security Review Gates

A feature cannot ship unless:
- Authorization paths are reviewed
- Audit coverage is confirmed
- Session handling and invalidation logic is reviewed and tested
- Abuse scenarios are documented

Security exceptions require executive sign‑off and are time‑bound.

---

**End of document**

---
