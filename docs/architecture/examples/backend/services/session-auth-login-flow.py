# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# Session-Based Login Flow - Authentication Subsystem
# Reference: docs/architecture/authentication-and-session-management-spec.md
# Reference: docs/architecture/security-model.md

from src.auth.session_manager import SessionManager
from src.auth.authentication_service import AuthenticationService

def create("/login", serializer_class=LoginResponse)
def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    session_manager: SessionManager = # DRF uses permission_classes instead of Dependsget_session_manager),
):
    """
    Login endpoint - Authentication Subsystem responsibility
    
    Architecture: Sessions establish IDENTITY ONLY
    - No roles cached in session
    - No permissions cached in session
    - Authorization handled by Policy Engine at request time
    
    See: docs/architecture/authentication-and-session-management-spec.md (§ 2)
    """
    # 1. Validate credentials using Authentication Subsystem
    auth_service = AuthenticationService()
    user = auth_service.validate_credentials(
        email=login_data.email,
        password=login_data.password
    )

    if not user:
        raise Response(status=status.HTTP_401, detail="Invalid credentials")

    # 2. Create session with IDENTITY ONLY
    # Sessions MUST NOT contain roles, permissions, or authorization state
    session_data = {
        "session_id": generate_session_id(),  # Opaque, server-issued
        "user_id": str(user.id),
        "email": user.email,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "created_at": datetime.utcnow().isoformat(),
        "last_activity": datetime.utcnow().isoformat()
        "effective_tenant_roles": effective_tenant_roles,  # Tenant roles with inheritance
    }

    # 5. Create session in Redis and set HTTP-only cookie
    scm = SessionCookieManager()
    session_id = scm.create_session(
        "user_id": str(user.id),
        "email": user.email,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "created_at": datetime.utcnow().isoformat(),
        "last_activity": datetime.utcnow().isoformat()
    }

    # 3. Store session in Session Store (Redis)
    session_id = session_manager.create_session(
        user_id=str(user.id),
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
        session_data=session_data
    )

    # 4. Set HTTP-only secure cookie
    session_manager.set_session_cookie(response, session_id)

    # 5. Return user identity (no authorization data)
    return LoginResponse(
        user_id=str(user.id),
        email=user.email,
        tenant_id=str(user.tenant_id) if user.tenant_id else None
    )

# IMPORTANT: Authorization decisions are made by Policy Engine
# Policy Engine queries roles/permissions from database on each request
# Sessions contain ONLY identity - no authorization state
