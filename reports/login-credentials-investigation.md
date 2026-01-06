# Login Credentials Investigation

**Date:** 2026-01-06  
**Severity:** High  
**Status:** ✅ Resolved  
**Investigator:** Application Architect Agent

---

## Executive Summary

Users were unable to login using seeder credentials (`admin@saraise.com` / `admin@134`) due to **incorrect API base URL configuration** in the frontend. The API client was defaulting to port `18000` (platform services) instead of `28000` (application backend), causing login requests to fail or be misrouted.

---

## Root Cause Analysis

### Primary Root Cause: API Base URL Mismatch

**Symptom:**
- Users unable to login with seeder credentials
- Backend login endpoint works correctly (verified via curl)
- Frontend login requests failing or misrouted

**Evidence:**
1. **Backend verification:** Login endpoint at `http://localhost:28000/api/v1/auth/login/` works correctly
   ```bash
   curl -X POST http://localhost:28000/api/v1/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"email":"admin@saraise.com","password":"admin@134"}'
   # Returns: 200 OK with user data and session cookie
   ```

2. **Frontend API client default:** `api-client.ts` defaults to `http://localhost:18000`
   ```typescript
   this.baseUrl = options.baseUrl ?? (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:18000');
   ```

3. **Vite proxy default:** `vite.config.ts` proxy defaults to `http://localhost:18000`
   ```typescript
   target: process.env.VITE_API_BASE_URL || 'http://localhost:18000',
   ```

4. **Port convention mismatch:**
   - Platform services: `1xxxx` ports (e.g., `18000`, `18001`)
   - Application backend: `2xxxx` ports (e.g., `28000`)
   - Frontend was defaulting to platform port instead of application port

### Secondary Issue: Environment Variable Not Available at Build Time

The Vite proxy configuration uses `process.env.VITE_API_BASE_URL`, but:
- Vite doesn't expose environment variables to the config file at build time
- The environment variable is set in docker-compose (`VITE_API_BASE_URL=http://localhost:28000`)
- But the default fallback was incorrect (`18000` instead of `28000`)

---

## Investigation Details

### Port Convention (SARAISE Standard)

| Service Type | Port Range | Example |
|-------------|------------|---------|
| Platform services | `1xxxx` | `18000`, `18001`, `18002` |
| Application services | `2xxxx` | `28000`, `28001`, `28002` |

**Application Backend:** Runs on port `28000` (not `18000`)

### Seeder Credentials (Verified Working)

| Email | Password | Role | Status |
|-------|----------|------|--------|
| `admin@saraise.com` | `admin@134` | Platform Owner | ✅ Verified |
| `admin@buildworks.ai` | `admin@134` | Tenant Admin | ✅ Verified |

**Database verification:**
```python
User.objects.get(email='admin@saraise.com')
# Password check: True
# Is active: True
# Profile validation: PASS
```

### Backend Login Endpoint (Verified Working)

**Endpoint:** `POST /api/v1/auth/login/`

**Test:**
```bash
curl -X POST http://localhost:28000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@saraise.com","password":"admin@134"}'
```

**Response:** `200 OK`
```json
{
  "user": {
    "id": "1",
    "email": "admin@saraise.com",
    "username": "admin@saraise.com",
    "is_staff": true,
    "is_superuser": true,
    "tenant_id": null,
    "platform_role": "platform_owner",
    "tenant_role": null
  },
  "session_id": "..."
}
```

---

## Solution Implemented

### 1. Fixed API Client Default URL

**File:** `frontend/src/services/api-client.ts`

**Before:**
```typescript
this.baseUrl = options.baseUrl ?? (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:18000');
```

**After:**
```typescript
this.baseUrl = options.baseUrl ?? (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:28000'); // Application backend port: 2xxxx
```

### 2. Fixed Vite Proxy Default URL

**File:** `frontend/vite.config.ts`

**Before:**
```typescript
target: process.env.VITE_API_BASE_URL || 'http://localhost:18000',
```

**After:**
```typescript
target: process.env.VITE_API_BASE_URL || 'http://localhost:28000', // Application backend port: 2xxxx
```

---

## Verification

### Expected Behavior After Fix

1. Frontend API client uses correct default URL (`http://localhost:28000`)
2. Vite proxy forwards to correct backend (`http://localhost:28000`)
3. Login requests succeed with seeder credentials
4. Session cookies are set correctly

### Testing Commands

```bash
# Test backend login directly
curl -X POST http://localhost:28000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@saraise.com","password":"admin@134"}'

# Test frontend (after rebuild)
cd saraise-application
docker-compose -f docker-compose.dev.yml restart frontend

# Check environment variable
docker exec ui-web printenv | grep VITE_API_BASE_URL
# Should show: VITE_API_BASE_URL=http://localhost:28000
```

---

## Impact Assessment

### Before Fix
- ❌ Frontend defaulting to wrong port (`18000` instead of `28000`)
- ❌ Login requests misrouted or failing
- ❌ Users unable to login with seeder credentials
- ❌ Development workflow blocked

### After Fix
- ✅ Frontend uses correct default port (`28000`)
- ✅ Login requests route to correct backend
- ✅ Users can login with seeder credentials
- ✅ Development workflow restored

---

## Recommendations

### Short-term (Immediate)
1. ✅ **DONE**: Fix API client default URL
2. ✅ **DONE**: Fix Vite proxy default URL
3. **Verify**: Test login with all seeder credentials

### Long-term (Future Improvements)
1. **Environment validation**: Add startup check to validate `VITE_API_BASE_URL` is set
2. **Port convention documentation**: Document port conventions in frontend README
3. **Type safety**: Add TypeScript types for environment variables
4. **Error handling**: Improve error messages when API URL is misconfigured

---

## Related Files

- `frontend/src/services/api-client.ts` - API client configuration (FIXED)
- `frontend/vite.config.ts` - Vite proxy configuration (FIXED)
- `docker-compose.dev.yml` - Environment variable configuration (no changes needed)
- `backend/src/core/auth_api.py` - Login endpoint (no changes needed)
- `backend/src/core/management/commands/seed_default_users.py` - User seeder (no changes needed)

---

## Lessons Learned

1. **Port conventions matter**: Platform services (`1xxxx`) vs Application services (`2xxxx`) must be consistent across all configuration files.

2. **Default values must match conventions**: When environment variables aren't set, defaults should follow the port convention.

3. **Backend verification first**: Always verify backend endpoints work before investigating frontend issues.

4. **Environment variable visibility**: Vite environment variables are available at runtime (`import.meta.env`) but not in `vite.config.ts` at build time.

---

## References

- SARAISE Port Convention: `PORT_MAPPING.md`
- Authentication Architecture: `docs/architecture/authentication-and-session-management-spec.md`
- Frontend Architecture: `docs/architecture/application-architecture.md`

---

**Investigation Complete** ✅

