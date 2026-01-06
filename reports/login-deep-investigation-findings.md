# Login Deep Investigation - Findings and Fixes

**Date:** 2026-01-06  
**Status:** 🔄 In Progress  
**Investigator:** Application Architect Agent

---

## Executive Summary

Investigated login failures for both platform and application frontends. Identified multiple root causes and implemented fixes. Some issues remain requiring further investigation.

---

## Issues Identified and Fixed

### ✅ Issue 1: API Base URL Mismatch (FIXED)

**Problem:**
- Application frontend defaulted to `http://localhost:18000` (wrong port)
- Platform frontend defaulted to `http://localhost:18004` (control plane, not auth endpoint)

**Root Cause:**
- Port convention mismatch: Application backend runs on `28000` (2xxxx), not `18000` (1xxxx)
- Platform frontend was pointing to control plane instead of application backend

**Fix Applied:**
1. Updated `frontend/src/services/api-client.ts` default to `http://localhost:28000`
2. Updated `frontend/vite.config.ts` proxy default to `http://localhost:28000`
3. Updated `saraise-platform/frontend/src/services/api-client.ts` default to `http://localhost:28000`
4. Updated `saraise-platform/frontend/vite.config.ts` proxy default to `http://localhost:28000`
5. Updated `saraise-platform/docker-compose.dev.yml` environment variable to `VITE_API_BASE_URL=http://localhost:28000`

**Status:** ✅ FIXED

---

### ✅ Issue 2: CORS Configuration (FIXED)

**Problem:**
- CORS allowed origins didn't include frontend ports `25173` and `17000`
- Requests were being blocked by CORS policy

**Root Cause:**
- CORS configuration only allowed `15173` and `5173`, not the actual container ports

**Fix Applied:**
- Updated `backend/saraise_backend/settings.py`:
  - Added `http://localhost:25173` (Application frontend)
  - Added `http://localhost:17000` (Platform frontend)
  - Added corresponding `127.0.0.1` entries
  - Updated `CSRF_TRUSTED_ORIGINS` with same origins

**Status:** ✅ FIXED

---

### ✅ Issue 3: Missing Authentication Classes (FIXED)

**Problem:**
- `current_user_view`, `logout_view`, and `refresh_session_view` didn't explicitly specify authentication classes
- Relied on default which might not handle sessions correctly

**Root Cause:**
- DRF endpoints need explicit `@authentication_classes([SessionAuthentication])` for session-based auth

**Fix Applied:**
- Added `@authentication_classes([SessionAuthentication])` to all authenticated endpoints in `backend/src/core/auth_api.py`

**Status:** ✅ FIXED

---

### ✅ Issue 4: Missing CSRF Token Handling (FIXED)

**Problem:**
- Frontend API clients weren't sending CSRF tokens with authenticated requests
- DRF's SessionAuthentication requires CSRF tokens for all authenticated requests (except login)

**Root Cause:**
- API clients didn't read CSRF token from cookie and include it in `X-CSRFToken` header

**Fix Applied:**
- Added `getCsrfToken()` method to both frontend API clients
- Modified `request()` method to include `X-CSRFToken` header for authenticated requests
- Applied to both `saraise-application/frontend` and `saraise-platform/frontend`

**Status:** ✅ FIXED

---

## Remaining Issues

### ❌ Issue 5: 403 Forbidden on `/api/v1/auth/me/` (INVESTIGATING)

**Symptom:**
- Login succeeds (200 OK)
- First `/api/v1/auth/me/` call sometimes succeeds (200 OK)
- Subsequent `/api/v1/auth/me/` calls fail with 403 Forbidden
- Error occurs before view code executes (DRF authentication layer)

**Evidence:**
```
[POST] http://localhost:28000/api/v1/auth/login/ => [200] OK
[GET] http://localhost:28000/api/v1/auth/me/ => [403] Forbidden
```

**Possible Causes:**
1. **Session cookie not being sent properly** - Cookie domain/path mismatch
2. **CSRF token validation failing** - DRF's SessionAuthentication CSRF check
3. **Session not persisting** - Session middleware issue
4. **Cookie SameSite policy** - Browser blocking cross-origin cookies

**Debug Steps Taken:**
- Added debug logging to `current_user_view` (not reached - 403 happens earlier)
- Verified CSRF token is being sent in header
- Verified session cookie is being set during login
- Checked CORS and CSRF trusted origins

**Next Steps:**
1. Check if session cookie is actually being sent with requests (browser DevTools)
2. Verify DRF SessionAuthentication CSRF enforcement logic
3. Check if SameSite cookie policy is blocking cookies
4. Test with curl to isolate browser vs backend issue

---

## Test Results

### Application Frontend Login
- **URL:** `http://localhost:25173/login`
- **Credentials:** `admin@buildworks.ai` / `admin@134`
- **Status:** ⚠️ PARTIAL
  - Login POST: ✅ 200 OK
  - `/api/v1/auth/me/`: ❌ 403 Forbidden (intermittent)

### Platform Frontend Login
- **URL:** `http://localhost:17000/login`
- **Credentials:** `admin@saraise.com` / `admin@134`
- **Status:** ⚠️ PARTIAL
  - Login POST: ✅ 200 OK
  - Navigation: ✅ Redirects to `/platform/dashboard`
  - `/api/v1/auth/me/`: ❌ 403 Forbidden (intermittent)

---

## Files Modified

### Application Repository
1. `backend/saraise_backend/settings.py` - CORS configuration
2. `backend/src/core/auth_api.py` - Authentication classes, debug logging
3. `frontend/src/services/api-client.ts` - CSRF token handling, API base URL
4. `frontend/vite.config.ts` - Proxy target URL

### Platform Repository
1. `frontend/src/services/api-client.ts` - CSRF token handling, API base URL
2. `frontend/vite.config.ts` - Proxy target URL
3. `docker-compose.dev.yml` - Environment variable

---

## Recommendations

### Immediate Actions
1. **Investigate session cookie transmission** - Verify cookies are being sent with requests
2. **Check DRF SessionAuthentication CSRF logic** - May need custom authentication class
3. **Test with browser DevTools** - Inspect actual request/response headers
4. **Verify SameSite cookie policy** - May need to adjust for development

### Long-term Improvements
1. **Add request logging middleware** - Log all authentication attempts
2. **Implement session debugging endpoint** - Expose session state for troubleshooting
3. **Add integration tests** - Test full login flow with browser automation
4. **Document CSRF handling** - Clear documentation for frontend developers

---

## Architecture Compliance

All fixes maintain compliance with:
- `docs/architecture/authentication-and-session-management-spec.md`
- `docs/architecture/security-model.md`
- Session-based authentication (no JWT for interactive users)
- CSRF protection on all authenticated endpoints
- CORS policy enforcement

---

**Investigation Status:** 🔄 Ongoing - 403 issue requires deeper investigation

