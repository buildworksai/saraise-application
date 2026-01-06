# OAuth/OIDC/SAML Architecture Compliance Assessment

**Date**: January 5, 2026  
**Status**: ⚠️ **DEFERRED TO PHASE 7**  
**Reason**: Identity federation not yet implemented in Phase 6  

---

## Architecture Requirements

Per `authentication-and-session-management-spec.md` and `security-model.md`:

### ✅ Mandatory Requirements

1. **Primary Authentication**: Server-managed stateful sessions (HTTP-only cookies)
2. **Identity Federation**: OIDC (primary) + SAML 2.0 (enterprise)
3. **JWT Prohibition**: JWTs **forbidden** for interactive user authentication
4. **Local Auth**: Allowed only for SMB tenants and break-glass access

### ⚠️ Current Phase 6 Status

**Backend Search Results**:
- ❌ No OIDC endpoints found in `backend/src/core/`
- ❌ No SAML endpoints found in `backend/src/core/`
- ❌ No OAuth provider integration found

**Conclusion**: Identity federation (OIDC/SAML) is **not implemented** in Phase 6.

---

## Decision: Defer OAuth to Phase 7

### Rationale

1. **Phase 6 Scope**: Focus on **core authentication** (login, logout, session management)
2. **Identity Federation**: Requires dedicated subsystem implementation
3. **Architecture Compliance**: Cannot implement OAuth without proper OIDC/SAML backend
4. **User Expectation**: User confirmed backends exist for register/reset, but OAuth requires "strict architecture guidelines"

### What This Means for UI

**MVP's `SocialProviders.tsx` component will be DEFERRED** because:
- It expects OAuth endpoints (`/api/v1/auth/oauth/{provider}/login`)
- Phase 6 backend does not have these endpoints
- Implementing UI without backend violates "no backend changes" principle

---

## Phase 7 Implementation Plan

### Backend Requirements (Phase 7)

1. **OIDC Provider Integration**:
   ```python
   # backend/src/core/oidc_provider.py
   - Google OAuth 2.0
   - Microsoft Azure AD
   - Generic OIDC provider support
   ```

2. **SAML 2.0 Integration** (Enterprise):
   ```python
   # backend/src/core/saml_provider.py
   - SAML SSO flow
   - Metadata exchange
   - Assertion validation
   ```

3. **API Endpoints**:
   ```
   POST /api/v1/auth/oauth/{provider}/login
   GET  /api/v1/auth/oauth/{provider}/callback
   POST /api/v1/auth/saml/login
   POST /api/v1/auth/saml/acs
   ```

### Frontend Implementation (Phase 7)

1. **Copy `SocialProviders.tsx`** from MVP
2. **Adapt to Phase 6 API** (when backend ready)
3. **Add to LoginForm** (below email/password form)

---

## Current Auth Flow (Phase 6)

### ✅ Implemented

1. **Local Authentication**:
   - Email + Password
   - Session-based (HTTP-only cookies)
   - CSRF protection (exempted for login only)

2. **Registration**:
   - `/api/v1/auth/register/` endpoint exists ✅
   - Will implement RegisterForm UI

3. **Password Reset**:
   - `/api/v1/auth/forgot-password/` exists ✅
   - `/api/v1/auth/reset-password/` exists ✅
   - Will implement ForgotPassword/ResetPassword UI

### ⏸️ Deferred to Phase 7

1. **Identity Federation**:
   - OIDC (Google, Microsoft, Azure AD)
   - SAML 2.0 (Enterprise SSO)
   - OAuth provider buttons in UI

---

## Compliance Status

| Requirement | Phase 6 Status | Notes |
|-------------|----------------|-------|
| **Session-based auth** | ✅ Implemented | HTTP-only cookies, CSRF protected |
| **Local auth (email/password)** | ✅ Implemented | Login, register, password reset |
| **OIDC federation** | ⏸️ Deferred | Phase 7 - requires backend subsystem |
| **SAML 2.0 federation** | ⏸️ Deferred | Phase 7 - enterprise feature |
| **JWT prohibition** | ✅ Compliant | No JWTs for interactive users |
| **Session invalidation** | ✅ Implemented | Logout endpoint, Redis session store |

---

## Recommendation

**Proceed with Phase 6 Auth UI completion**:
1. ✅ **RegisterForm** - Backend ready, implement UI
2. ✅ **ForgotPassword** - Backend ready, implement UI
3. ✅ **ResetPassword** - Backend ready, implement UI
4. ⏸️ **OAuth/OIDC/SAML** - Defer to Phase 7 (backend not ready)

**LoginForm**: Remove "Create account" link was correct decision (now we'll add it back since register backend exists).

---

**Approved by**: Architecture Compliance Agent  
**Date**: January 5, 2026  
**Next Review**: Phase 7 (Identity Federation Implementation)

