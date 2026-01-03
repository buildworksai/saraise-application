# SARAISE Authentication & Session Management Specification

**Status:** Draft v0.1 (authoritative, enforced)

This document defines the **single, non-negotiable authentication strategy** for SARAISE.

If authentication and session semantics are ambiguous, everything built on top of them becomes unsafe. This spec removes that ambiguity.

---

## 0) Ruthless Principles

1. **Authentication is stateful.** SARAISE does not trust stateless identity for interactive access.
2. **Sessions are server-owned.** Clients never control identity or authority.
3. **Authentication ≠ Authorization.** Sessions establish identity only.
4. **Session invalidation is immediate and global.** Stale authority is unacceptable.
5. **Auth failures fail closed.** Availability never overrides correctness.

---

## 1) Authentication Strategy (Authoritative)

### 1.1 Interactive User Access

All interactive access (Web UI, ERP UI, admin consoles) uses **server-managed sessions**.

- Secure, HTTP-only cookies
- Opaque session identifiers
- Continuous server-side validation

JWTs are **explicitly forbidden** for interactive user authentication.

### 1.2 Non-Interactive Access

JWTs are permitted **only** for:
- External API consumers
- Service-to-service communication
- Short-lived, scope-restricted integration tokens

These tokens:
- are never stored in browsers
- never grant UI access
- are always tenant-scoped

---

## 2) Authentication Service Ownership

Authentication is provided by a **dedicated Authentication Subsystem**.

Responsibilities:
- Login
- Logout
- Session creation
- Session rotation
- Session invalidation
- Federation handling (OIDC, SAML)

The runtime plane:
- validates sessions
- never issues or mutates them

The control plane:
- does not perform request-time authentication

---

## 2A) Authentication Subsystem Architecture (Authoritative)

This section defines **where the Authentication Subsystem runs**, **how it scales**, and **how it integrates with runtime and session storage**.

### 2A.1 Logical Placement

The Authentication Subsystem is a **dedicated stateless service tier**, deployed independently from:
- Runtime plane services
- Control plane services

It is NOT:
- embedded inside runtime services
- implemented at an API gateway
- shared with control-plane workflows

### 2A.2 High-Level Request Flow

```
[ Client / Browser ]
        |
        v
[ Authentication Subsystem ]
        |
        v
[ Session Store (Redis, Multi-AZ, Region-Local) ]
        |
        v
[ Runtime Plane Services ]
```

Flow semantics:
1. Client performs login against Authentication Subsystem
2. Authentication Subsystem validates identity (OIDC / SAML / Local)
3. Session is created and written to Session Store
4. Session ID is returned to client as secure cookie
5. Runtime services validate session on every request against Session Store

---

### 2A.3 Scaling Model

- Authentication Subsystem:
  - stateless
  - horizontally scalable
  - fronted by regional load balancer

- Session Store:
  - Redis (or equivalent)
  - one cluster per region
  - Multi-AZ with automatic failover

There is **no central global session store**.

---

### 2A.4 Session Validation Path

Runtime services perform:
- local request handling
- remote session lookup against region-local session store

Optional optimizations:
- short-lived in-memory cache (≤ 60 seconds)
- used only under degraded-mode rules

Runtime services:
- never call the Authentication Subsystem during request handling
- never issue or mutate sessions

---

### 2A.5 Network & Trust Boundaries

- Authentication Subsystem ↔ Session Store: private network only
- Runtime ↔ Session Store: private network only
- Clients never communicate directly with Session Store

All inter-service traffic is:
- authenticated
- encrypted
- audited

---

### 2A.6 Failure Isolation

- Authentication Subsystem failure:
  - blocks new logins
  - does NOT invalidate existing sessions

- Session Store failure:
  - triggers degraded-mode semantics (see Section 6A)

This architecture ensures authentication failures do not cascade into data corruption or authorization bypass.

---

## 3) Login & Logout Semantics

### 3.1 Login Flow

1. User authenticates via:
   - OIDC (primary)
   - SAML 2.0 (enterprise)
   - Local credentials (restricted)
2. Identity is resolved and tenant-scoped
3. Session is created server-side
4. Session ID is returned as secure cookie

### 3.2 Logout Flow

- Session is invalidated server-side
- Cookie is cleared
- All derived authority is revoked

Logout is always global for that session.

---

## 4) Session Model

### 4.1 Session Properties

Each session is:
- opaque
- server-generated
- tenant-bound
- subject-bound
- time-limited
- policy_version (monotonic identifier of the effective policy set at session issuance)

### 4.2 Session Storage

- Primary store: Redis (or equivalent) in Multi-AZ configuration
- One session cluster per region
- Automatic leader election and failover

Optional:
- Write-through persistence to relational DB for audit and forensics

Hard rules:
- No cross-region session store sharing
- Session stores are encrypted at rest
- Session stores are capacity- and health-monitored
## 4A) Policy Version Gating (Fail-Safe)

- Each session carries a `policy_version` issued at authentication time
- Runtime maintains a `current_policy_version` per tenant

Enforcement rules:
- If session.policy_version < runtime.current_policy_version:
  - request is denied
  - user is forced to re-authenticate
- This check is mandatory on every request

This guarantees immediate policy invalidation without synchronous dependency on the control plane.
## 6A) Session Store Failure & Degradation Semantics

Session store outages are security-critical events.

### Normal Mode
- All session validation is performed against the session store

### Degraded Mode (Session Store Unhealthy)
- Duration: strictly bounded (≤ 60 seconds)
- Allowed only for read-only endpoints
- Uses short-lived in-memory cache of previously validated sessions

Forbidden during degradation:
- privilege elevation
- write operations
- approvals
- agent execution

All degraded-mode access is:
- explicitly logged
- tenant-scoped
- audited post-incident

If session integrity cannot be guaranteed, the system fails closed.

---

## 5) Session Lifetime & Rotation

- Short base TTL (configurable)
- Rolling renewal on activity
- Absolute maximum lifetime enforced

Rotation triggers:
- privilege elevation
- policy or role change
- suspicious activity

---

## 6) Session Invalidation (Hard Rules)

Sessions are invalidated immediately on:
- logout
- role or group change
- policy change affecting the user
- JIT grant expiry or revocation
- tenant suspension
- security incident

Invalidation propagates globally within defined SLA.

---

## 7) Multi-Region Session Semantics

- Sessions are **region-affined** by default
- Cross-region session reuse is forbidden unless explicitly enabled
- Global tenants may have per-region sessions

Session replication across regions is:
- disabled by default
- allowed only for compliant tiers

---

## 8) Agent & Automation Binding

### 8.1 User-Bound Agents

- Require an active user session
- Session must remain valid for execution
- Session revocation terminates agent

### 8.2 System-Bound Agents

- Use system identity
- Do not use user sessions
- Are tightly permission-scoped

---

## 9) CSRF & Browser Security

Mandatory controls:
- CSRF protection on all session-auth endpoints
- SameSite cookie enforcement
- Secure cookie flags

CSRF bypasses are forbidden.

---

## 10) Capacity & Scaling Considerations

Auth subsystem must handle:
- login storms
- session churn
- rotation spikes

Session capacity planning is tied to:
- shard sizing
- tenant concurrency models

---

## 11) Audit & Observability

Mandatory logs:
- login attempts (success/failure)
- session creation
- session rotation
- session invalidation

- policy_version mismatch denials
- degraded-mode access events

All logs are tenant-scoped and immutable.

---

## 12) What Is Explicitly Forbidden

- Client-managed sessions
- Long-lived browser tokens
- JWTs for interactive auth
- Silent session extension
- Partial session invalidation

Violations are treated as security incidents.

---

## 13) Final Warning

Authentication errors compound silently.

This specification exists to ensure SARAISE never loses control of identity — even under scale, stress, or attack.

---

**End of document**

---