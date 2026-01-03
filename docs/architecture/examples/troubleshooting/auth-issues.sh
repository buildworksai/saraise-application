#!/bin/bash
# ✅ APPROVED: Authentication Troubleshooting Commands
# Reference: docs/architecture/authentication-and-session-management-spec.md § 2 (Session Lifecycle)
# Also: docs/architecture/operational-runbooks.md § 2 (Troubleshooting)
# 
# CRITICAL NOTES:
# - Sessions are IDENTITY ONLY (user_id, email, tenant_id, timestamps)
# - Sessions are NEVER authorization cache (security-model.md § 2.4)
# - All authorization decisions evaluated per-request by Policy Engine
# - Session validation failures indicate identity verification issues
# - HTTP-only cookies prevent XSS token theft

# Problem: User cannot log in
# Symptoms
# - 401 Unauthorized errors
# - "Invalid authentication credentials" messages
# - Session validation failures

# Diagnosis
# 1. Check Redis session storage
# 2. Verify session configuration
# 3. Check session expiration
# 4. Validate session cookies

# Solutions
# Check Redis status
docker ps | grep redis
redis-cli ping

# Check session data in Redis
redis-cli KEYS "saraise:session:*"

# Check application logs
docker logs saraise-api | grep -i auth

# Restart Redis
docker-compose restart redis

# Problem: Session tokens not working
# Symptoms
# - 401 errors after successful login
# - "Invalid session token" messages
# - Users getting logged out unexpectedly

# Diagnosis
# 1. Check session cookie format
# 2. Verify session secret key
# 3. Check session expiration settings
# 4. Validate Redis storage

# Solutions
# Check session secret in environment
echo $SESSION_SECRET_KEY

# Check session timeout settings
grep -r "session_timeout" backend/src/

# Check session cookies
# In browser DevTools: Application > Cookies > localhost

# Clear invalid sessions
redis-cli KEYS "saraise:session:*" | xargs redis-cli DEL

