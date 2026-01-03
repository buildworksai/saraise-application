# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Session Data Structure - Identity Only
# backend/src/core/session_manager.py structures
# Reference: docs/architecture/authentication-and-session-management-spec.md
# Reference: docs/architecture/security-model.md § 2.4

# APPROVED: Sessions contain identity only
APPROVED_SESSION_STRUCTURE = {
    "session_id": "opaque_server_issued_identifier",
    "user_id": "uuid-string",
    "email": "user@example.com",
    "tenant_id": "tenant-uuid",
    "created_at": "2026-01-03T10:00:00Z",
    "last_activity": "2026-01-03T10:30:00Z",
}

# FORBIDDEN: Sessions MUST NOT contain:
# ❌ roles (direct or effective)
# ❌ permissions
# ❌ group memberships
# ❌ ABAC attributes
# ❌ any authorization state

# Hard Invariant: "Session Is NOT an Authorization Cache"
# See docs/architecture/security-model.md § 2.4

# Authorization Architecture:
# 1. Session → Identity only (user_id, email, tenant_id)
# 2. Request arrives with session cookie
# 3. Policy Engine evaluates at request time:
#    - Queries roles, permissions, group memberships from database
#    - Evaluates RBAC (role-based) rules
#    - Evaluates ABAC (attribute-based) rules
#    - Returns authorization decision
# 4. Route handler receives decision and acts accordingly
#
# References:
# - docs/architecture/policy-engine-spec.md § 1 (Runtime Decisions)
# - docs/architecture/policy-engine-spec.md § 4 (Authorization Flow)
# - docs/architecture/security-model.md § 2.4 (Session Invariant)
    "abac_context": {
        "data_classification_clearance": ["public", "internal", "confidential"],
        "allowed_ip_ranges": ["192.168.1.0/24"],
        "allowed_time_ranges": [{"start": "09:00", "end": "17:00"}],
        "department": "finance",
        "location": "US-East",
    }
}

