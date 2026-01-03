---
description: Session-based authentication architecture (identity only, no authorization cache)
globs: backend/src/**/*.py, frontend/src/**/*.{ts,tsx}
alwaysApply: true
---

# 🔒 SARAISE Session-Based Authentication Architecture

**Related Documentation:**
- Authentication & Session Management: `docs/architecture/authentication-and-session-management-spec.md`
- Security Model: `docs/architecture/security-model.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`

## SARAISE-07011 Authentication Architecture Overview

**Primary Authentication Method:** Server-managed stateful sessions

**Key Principles (FROZEN ARCHITECTURE - Authoritative):**
- HTTP-only session cookies for security
- Sessions contain **identity snapshot** (roles, groups, jit_grants, policy_version) - NOT permissions cache
- Sessions DO NOT cache effective permissions or ABAC evaluations
- Policy Engine evaluates: identity_snapshot + resource_attrs + context_attrs → allow/deny
- Session invalidation on policy changes (detected via policy_version mismatch)
- Deny-by-default authorization model

## SARAISE-07012 Backend Authentication Implementation

### Login Flow

**Authentication Subsystem Responsibilities:**
- Validate credentials
- Create server-side session
- Set HTTP-only cookie

**Key Points (FROZEN ARCHITECTURE):**
- Validate credentials using Authentication Subsystem
- Session stores identity snapshot: `user_id`, `email`, `tenant_id`, `session_id`, `policy_version`, `roles[]`, `groups[]`, `jit_grants[]`
- Session does NOT store effective permissions (e.g., "finance.ledger:post")
- Set HTTP-only cookie with session identifier

### Session Validation

**Key Points (FROZEN ARCHITECTURE):**
- Validate session identifier against Session Store (Redis)
- Verify session is valid, not expired, tenant-bound
- Verify policy_version matches runtime policy version (fail with DENY_POLICY_VERSION_STALE if mismatch)
- Return identity snapshot: `user_id`, `tenant_id`, `roles[]`, `groups[]`, `jit_grants[]`, `policy_version`
- Policy Engine uses identity snapshot for authorization evaluation

### Authorization Flow

**Policy Engine Evaluation (Every Request) (FROZEN ARCHITECTURE):**
- Extract identity snapshot from validated session (roles[], groups[], jit_grants[], policy_version)
- Validate policy_version matches runtime version (deny if stale)
- Policy Engine evaluates: `(identity_snapshot, resource, action, context) → allow/deny`
- Policy Engine maps roles → permissions (cached inside Policy Engine, NOT in session)
- RBAC + ABAC conditions evaluated at runtime using identity snapshot + resource attrs + context attrs
- No effective permissions or ABAC evaluations stored in session

## SARAISE-07013 Privilege Change Handling

**CRITICAL (FROZEN ARCHITECTURE):** When user roles, policy, or privileges change:

**Required Steps:**
1. Update roles/permissions in database
2. Increment runtime policy_version
3. Existing sessions with stale policy_version will be denied at next request (DENY_POLICY_VERSION_STALE)
4. User forced to re-authenticate, receives fresh identity snapshot with new policy_version
5. Audit log the privilege change

**Reason:** Sessions contain identity snapshot at creation time. Policy version gating ensures stale sessions are denied, forcing re-authentication with fresh identity.

## SARAISE-07014 Frontend Session Management

### Authentication Service

**Key Points:**
- Use `credentials: 'include'` to include HTTP-only cookies
- Session identifier stored in HTTP-only cookie by server
- No client-side storage of identity or authorization data

### Role-Based UI Rendering

**Key Points:**
- Frontend queries authorization state from backend API
- Backend calls Policy Engine for authorization decisions
- UI renders based on authorization response
- Never cache authorization decisions in frontend

## SARAISE-07015 Session Configuration

### Session Storage

**Key Configuration:**
- Session timeout: configurable (default 2 hours)
- Cookie: HTTP-only, secure (HTTPS only in production), SameSite=strict/lax
- Session Store: Redis or equivalent (region-local)
- Session key prefix: `saraise:session:`

### Session Data Structure (FROZEN ARCHITECTURE)

**Session contains identity snapshot (NOT a cache - authoritative identity at session creation):**
```python
{
    "session_id": "opaque_identifier",
    "user_id": "uuid",
    "email": "user@example.com",
    "tenant_id": "tenant_uuid",
    "policy_version": "v1.2.3",  # FROZEN: Policy version gating
    "roles": ["tenant_admin", "viewer"],  # Identity snapshot
    "groups": ["finance_team", "managers"],  # Identity snapshot
    "jit_grants": [{"permission": "ledger:approve", "expires_at": "timestamp"}],  # Time-bounded grants
    "created_at": "timestamp",
    "last_activity": "timestamp"
}
```

**CRITICAL DISTINCTION (FROZEN ARCHITECTURE):**
- Sessions contain **identity snapshot** (roles, groups, jit_grants, policy_version)
- This is **NOT caching permissions** - it's the authoritative identity bound to the session
- Policy Engine uses identity snapshot + resource attributes + context attributes for evaluation
- Sessions are invalidated when roles/policy changes (via policy_version mismatch)

**Sessions MUST NOT contain:**
- Effective permissions (e.g., "finance.ledger:post")
- ABAC attribute values (those are fetched at eval time)
- Cached authorization decisions

## SARAISE-07016 Security Requirements

### Password Security

**Key Requirements:**
- Use bcrypt with cost factor 12
- Add random delay to prevent timing attacks
- Constant-time comparison

### Session Security

**Key Requirements:**
- Use `secrets.token_urlsafe(32)` for 256 bits of entropy
- Never use predictable tokens

## SARAISE-07017 CORS Configuration

**Key Requirements:**
- Enable `allow_credentials` for session cookies
- Configure allowed origins explicitly (no wildcards in production)
- Set appropriate methods and headers

## SARAISE-07019 Testing Requirements

- Test session creation and validation
- Test session invalidation on logout
- Test session expiry handling
- Test CSRF protection
- Test authorization is evaluated via Policy Engine, not session cache

## SARAISE-07020 Performance Targets

- Login: < 500ms (authentication + session creation with identity snapshot)
- Session validation: < 10ms (Redis lookup + policy_version check)
- Authorization decision: < 50ms (Policy Engine evaluation: identity_snapshot + resource + context)
- Session size: ~500 bytes (identity snapshot with roles[], groups[], jit_grants[])

## SARAISE-07021 Audit Requirements

**Required Audit Events:**
- Login success/failure
- Logout
- Session invalidation
- Privilege changes
- All authentication-related operations

## SARAISE-07022 Forbidden Patterns

**Authorization Cache Violations (FROZEN ARCHITECTURE):**
- ❌ Storing effective permissions in sessions (e.g., "finance.ledger:post")
- ❌ Storing ABAC attribute values in sessions
- ❌ Caching authorization decisions in sessions
- ❌ Caching authorization decisions client-side
- ❌ Bypassing Policy Engine for authorization checks

**JWT Violations:**
- ❌ Using JWT for interactive user authentication
- ❌ Client-trusted tokens for authorization

**Correct Pattern (FROZEN ARCHITECTURE):**
- ✅ Sessions contain identity snapshot (roles[], groups[], jit_grants[], policy_version)
- ✅ Sessions DO NOT contain effective permissions or cached decisions
- ✅ Policy Engine evaluates: identity_snapshot + resource + context → allow/deny at request time
- ✅ Policy version gating ensures stale sessions are denied
- ✅ JWTs only for external API/service-to-service (not interactive users)

## Related Documentation

- Authentication Spec: `docs/architecture/authentication-and-session-management-spec.md`
- Security Model: `docs/architecture/security-model.md`
- Policy Engine: `docs/architecture/policy-engine-spec.md`
- ABAC Attributes: `docs/architecture/abac-attributes-architecture.md`
