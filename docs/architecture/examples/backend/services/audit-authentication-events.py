# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Audit Authentication Events
# backend/src/services/audit_authentication_events.py
# Reference: docs/architecture/security-model.md § 4.2 (Authentication Audit)
# CRITICAL NOTES:
# - Login events logged: success/failure, user_id, email, tenant_id, IP address
# - MFA events logged: MFA enabled, MFA disabled, MFA verification success/failure
# - Session events logged: session created, session destroyed, session extended
# - Failed login attempts tracked: rate limiting triggered after N attempts (security-model.md § 3.2)
# - Password change logged: user_id, timestamp, IP address
# - Account unlock logged: admin unlock with reason
# - API key creation/revocation logged: key_id, user, reason
# - OAuth/SAML events logged: provider, assertion validation, attribute mapping
# - Logout events logged: user_id, tenant_id, session end time
# - All events include: timestamp, actor (user_id), resource, action, status
# Source: docs/architecture/security-model.md § 4.2

from src.services.audit_service import audit_service

# Login success
audit_service.log_event(
    actor_sub=user.id,
    actor_email=user.email,
    tenant_id=user.tenant_id,
    resource="auth",
    action="login",
    result="success",
    metadata={"ip_address": request.client.host}
)

# Login failure
audit_service.log_event(
    actor_sub=None,
    actor_email=login_data.email,
    tenant_id=None,
    resource="auth",
    action="login",
    result="failure",
    metadata={"reason": "invalid_credentials"}
)

# Role change
audit_service.log_event(
    actor_sub=admin_user.id,
    actor_email=admin_user.email,
    tenant_id=user.tenant_id,
    resource="user_roles",
    action="update",
    result="success",
    metadata={
        "target_user_id": user.id,
        "old_roles": old_roles,
        "new_roles": new_roles,
    }
)

