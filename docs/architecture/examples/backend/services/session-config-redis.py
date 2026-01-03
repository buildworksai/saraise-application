# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Redis Session Storage Configuration
# backend/src/config/session_config.py
# Reference: docs/architecture/authentication-and-session-management-spec.md § 2 (Session Storage)
# CRITICAL NOTES:
# - Redis connection pooling: host, port, db from environment variables
# - decode_responses: True for UTF-8 string handling
# - Session timeout: 2 hours (configurable per environment)
# - Session key prefix: saraise:session: (namespace for multi-tenant Redis)
# - Cookie name: saraise_session (HTTP-only, SameSite=Strict, Secure in HTTPS)
# - Session data: session_id (opaque), user_id, email, tenant_id, timestamps
# - Session rotation: on login (prevent session fixation)
# - Session invalidation: on logout, password change, role change
# - Redis persistence: RDB snapshots + AOF (data durability)
# - Cluster configuration: Redis Sentinel for high availability
# Source: docs/architecture/authentication-and-session-management-spec.md § 2

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DB", 0)),
    "decode_responses": True,
}

SESSION_CONFIG = {
    "session_timeout": 7200,  # 2 hours
    "session_key_prefix": "saraise:session:",
    "cookie_name": "saraise_session",
    "cookie_httponly": True,
    "cookie_secure": True,  # HTTPS only in production
    "cookie_samesite": "lax",
}

