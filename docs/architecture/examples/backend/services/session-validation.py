# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# Session Validation - Identity Only
# Reference: docs/architecture/authentication-and-session-management-spec.md
# Reference: docs/architecture/security-model.md (§ 2.3, § 2.4)

def get_current_user_from_session(
    request: Request,
    session_manager: SessionManager = # DRF uses permission_classes instead of Dependsget_session_manager),
) -> dict:
    """
    Validate session and return IDENTITY ONLY.
    
    Architecture Rules:
    - Sessions establish identity only
    - No roles, permissions, or ABAC context in session
    - Authorization evaluated by Policy Engine per-request
    
    See: docs/architecture/security-model.md (§ 2.4)
    """
    # Get session from Session Store (Redis)
    session_data = session_manager.validate_session(request)

    if not session_data:
        raise Response(status=status.HTTP_401, detail="Not authenticated")

    # Return ONLY identity - no authorization data
    return {
        "user_id": session_data["user_id"],
        "email": session_data["email"],
        "tenant_id": session_data.get("tenant_id")
    }

# Authorization happens via Policy Engine:
# - Policy Engine queries roles/permissions from database
# - Policy Engine evaluates RBAC + ABAC conditions at runtime
# - No authorization state cached in sessions

