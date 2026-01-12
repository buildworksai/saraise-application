"""
Authentication API endpoints.

Handles login, logout, session management, and current user retrieval.

Per authentication-and-session-management-spec.md Section 9:
- CSRF protection is MANDATORY for all session-authenticated endpoints
- Login endpoint uses CsrfExemptSessionAuthentication (cannot have token before auth)
- All other endpoints use standard SessionAuthentication with CSRF enforcement

Phase 7.6: Mode-aware authentication routing:
- Self-hosted: Django built-in authentication
- SaaS: Delegation to saraise-auth service
- Development: Django built-in authentication (same as self-hosted)
"""

import uuid

from django.contrib.auth import get_user_model, login, logout
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from src.core.auth.mode import is_saas
from src.core.auth.saas import delegate_login
from src.core.authentication import CsrfExemptSessionAuthentication, RelaxedCsrfSessionAuthentication
from src.core.user_models import UserProfile

User = get_user_model()


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([CsrfExemptSessionAuthentication])
@ensure_csrf_cookie
def login_view(request):
    """
    Login endpoint.

    Phase 7.6: Mode-aware authentication routing:
    - Self-hosted/Development: Django built-in authentication
    - SaaS: Delegation to saraise-auth service

    Creates a session for authenticated users.
    """
    email = request.data.get("email")
    password = request.data.get("password")
    mfa_token = request.data.get("mfa_token")

    if not email or not password:
        return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Phase 7.6: Route based on mode
    if is_saas():
        # SaaS mode: Delegate to saraise-auth service
        session_data = delegate_login(email, password)
        if not session_data:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        # In SaaS mode, the platform handles session creation
        # We return the session data from the platform
        return Response(
            {
                "user": session_data.get("user", {}),
                "session_id": session_data.get("session_id"),
                "message": "Login successful (SaaS mode)",
            },
            status=status.HTTP_200_OK,
        )

    # Self-hosted or Development mode: Use Django built-in authentication
    # Authenticate user
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # Check password
    if not user.check_password(password):
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    # TODO: MFA validation (for now, skip if mfa_token provided)
    if mfa_token:
        # Placeholder for MFA validation
        pass

    # Login user (creates session)
    login(request, user)

    # Ensure session is saved (important for cookie to be set)
    request.session.save()

    # Get user profile
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist
        profile = UserProfile.objects.create(user=user)

    # Guardrail: block sessions for misconfigured identity (no orphan tenant_id, no mixed roles)
    try:
        profile.full_clean()
    except ValidationError as e:
        # Invalidate session immediately
        logout(request)
        return Response(
            {"error": "User profile is misconfigured", "details": e.message_dict},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Build user response
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "tenant_id": profile.tenant_id,
        "platform_role": profile.platform_role,
        "tenant_role": profile.tenant_role,
    }

    # CRITICAL: Create response and ensure session cookie is included
    # Django's login() and session.save() should set the cookie via middleware,
    # but DRF's Response class may not trigger middleware processing.
    # We explicitly set the cookie to ensure it's included in the response.
    response = Response(
        {
            "user": user_data,
            "session_id": request.session.session_key or str(uuid.uuid4()),
        },
        status=status.HTTP_200_OK,
    )

    # CRITICAL: Explicitly set session cookie to ensure it's sent to the client
    # Django's session middleware should do this automatically, but when using DRF's Response,
    # we need to ensure the cookie is set explicitly
    from django.conf import settings

    session_cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
    if request.session.session_key:
        cookie_path = getattr(settings, "SESSION_COOKIE_PATH", "/")
        # CRITICAL: Set cookie with exact same settings as Django's session middleware
        # This ensures consistency and that the cookie is properly set
        response.set_cookie(
            session_cookie_name,
            request.session.session_key,
            max_age=settings.SESSION_COOKIE_AGE,
            path=cookie_path,
            domain=settings.SESSION_COOKIE_DOMAIN,  # None for localhost
            secure=settings.SESSION_COOKIE_SECURE,  # False for development
            httponly=settings.SESSION_COOKIE_HTTPONLY,  # True for security
            samesite=settings.SESSION_COOKIE_SAMESITE,  # 'Lax' for same-origin
        )

    return response


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Logout endpoint.

    Invalidates the current session.
    """
    logout(request)
    return Response({"message": "Logged out successfully"}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([RelaxedCsrfSessionAuthentication])  # GET requests don't need CSRF
@permission_classes([IsAuthenticated])
@ensure_csrf_cookie  # Ensure CSRF cookie is set for subsequent requests
def current_user_view(request):
    """
    Get current authenticated user.

    Note: DRF's IsAuthenticated will return 403 if user is not authenticated.
    This happens before this function is called, so if we reach here, user is authenticated.

    CRITICAL: This endpoint must always allow access if user is authenticated,
    as it's used by the frontend to verify authentication status on route changes.
    """

    user = request.user

    # Get user profile
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        # Create profile if it doesn't exist
        profile = UserProfile.objects.create(user=user)

    # Guardrail: if the profile is misconfigured, do not leak a session-bound identity
    try:
        profile.full_clean()
    except ValidationError as e:
        logout(request)
        return Response(
            {"error": "User profile is misconfigured", "details": e.message_dict},
            status=status.HTTP_403_FORBIDDEN,
        )

    user_data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "tenant_id": profile.tenant_id,
        "platform_role": profile.platform_role,
        "tenant_role": profile.tenant_role,
    }

    return Response({"user": user_data}, status=status.HTTP_200_OK)


@api_view(["PATCH", "PUT"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def update_profile_view(request):
    """
    Update current user profile.

    Allows updating:
    - username
    - email
    - password (requires current_password)
    """
    user = request.user

    # Get user profile
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)

    # Update username if provided
    if "username" in request.data:
        username = request.data["username"]
        if username and username != user.username:
            # Check if username is already taken
            if User.objects.filter(username=username).exclude(pk=user.pk).exists():
                return Response({"error": "Username already taken"}, status=status.HTTP_400_BAD_REQUEST)
            user.username = username
            user.save(update_fields=["username"])

    # Update email if provided
    if "email" in request.data:
        email = request.data["email"]
        if email and email != user.email:
            # Check if email is already taken
            if User.objects.filter(email=email).exclude(pk=user.pk).exists():
                return Response({"error": "Email already taken"}, status=status.HTTP_400_BAD_REQUEST)
            user.email = email
            user.save(update_fields=["email"])

    # Update password if provided
    if "password" in request.data:
        new_password = request.data["password"]
        current_password = request.data.get("current_password")

        if not current_password:
            return Response(
                {"error": "Current password is required to change password"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Verify current password
        if not user.check_password(current_password):
            return Response({"error": "Current password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

        # Validate new password
        if not new_password or len(new_password) < 8:
            return Response(
                {"error": "Password must be at least 8 characters long"}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save(update_fields=["password"])

    # Refresh user from database
    user.refresh_from_db()
    profile.refresh_from_db()

    # Build updated user response
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "tenant_id": profile.tenant_id,
        "platform_role": profile.platform_role,
        "tenant_role": profile.tenant_role,
    }

    return Response({"user": user_data}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def refresh_session_view(request):
    """
    Refresh session validity.
    """
    # Django sessions are automatically refreshed on access
    # This endpoint just validates the session is still valid
    return Response({"message": "Session refreshed"}, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([CsrfExemptSessionAuthentication])
@ensure_csrf_cookie
def register_view(request):
    """
    User registration endpoint.

    Phase 7.5: In self-hosted mode, initializes 14-day trial on first registration.
    In development mode, allows registration without license validation.
    """
    from django.conf import settings

    from src.core.licensing.models import License, Organization
    from src.core.licensing.services import LicenseService

    email = request.data.get("email")
    password = request.data.get("password")
    # Frontend contract (auth-contracts.ts) defines 'company_name' as the field name
    # Backend MUST match the frontend contract per architectural guidelines
    company_name = request.data.get("company_name") or "My Organization"

    if not email or not password:
        return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    # Check if user already exists
    if User.objects.filter(email=email).exists():
        return Response({"error": "User with this email already exists"}, status=status.HTTP_400_BAD_REQUEST)

    # Only allow registration in self-hosted or development mode
    mode = getattr(settings, "SARAISE_MODE", "development")
    if mode == "saas":
        return Response(
            {"error": "Registration is handled by the platform in SaaS mode"}, status=status.HTTP_403_FORBIDDEN
        )

    # Create user
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )

    # Create user profile (get_or_create to handle edge cases)
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Phase 7.5: Initialize trial if this is the first registration (self-hosted mode)
    # In development mode, create organization without license validation
    if mode in ["self-hosted", "development"]:
        # Check if this is the first registration (no license exists)
        existing_license = License.objects.first()
        if not existing_license:
            # First registration - create organization and start trial (self-hosted) or just create org (development)
            # Organization model uses 'name' field, populated from frontend's 'company_name'
            organization = Organization.objects.create(
                name=company_name,
                domain=email.split("@")[1] if "@" in email else "",
            )

            # Only initialize trial in self-hosted mode (not in development)
            if mode == "self-hosted":
                try:
                    LicenseService.initialize_trial(organization)
                except Exception as e:
                    # If license initialization fails (e.g., database constraint issue),
                    # log the error but continue with registration
                    import logging

                    logger = logging.getLogger("saraise.auth")
                    logger.warning(f"Failed to initialize trial license: {e}")
                    # Continue without license - user can still register and use the system
                    # License can be initialized later via admin or migration fix

            # Set tenant_id for self-hosted/development mode (single tenant)
            # In self-hosted/development mode, all users belong to the same organization
            profile.tenant_id = str(organization.id)
            profile.tenant_role = "tenant_admin"  # First user is admin
        else:
            # Subsequent registration - use existing organization
            organization = existing_license.organization
            profile.tenant_id = str(organization.id)
            profile.tenant_role = "tenant_user"

    # Validate profile before saving (triggers clean() method)
    try:
        profile.full_clean()
        profile.save()
    except ValidationError as e:
        # If validation fails, delete the user and return error
        user.delete()
        return Response({"error": "Registration failed", "details": e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

    # Auto-login after registration
    login(request, user)

    # CRITICAL: Ensure session is saved and cookie is set
    # This is required for the session cookie to be sent with subsequent requests
    request.session.save()

    user_data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "tenant_id": profile.tenant_id,
        "platform_role": profile.platform_role,
        "tenant_role": profile.tenant_role,
    }

    # CRITICAL: Create response and ensure session cookie is included
    # DRF's Response class may not automatically include Set-Cookie headers
    response = Response(
        {
            "user": user_data,
            "session_id": request.session.session_key or str(uuid.uuid4()),
            "message": "Registration successful",
        },
        status=status.HTTP_201_CREATED,
    )

    # Ensure session cookie is set in response
    # Django's login() sets the cookie, but we need to ensure it's in the response
    from django.conf import settings

    session_cookie_name = getattr(settings, "SESSION_COOKIE_NAME", "sessionid")
    if request.session.session_key:
        # Use getattr with default '/' for SESSION_COOKIE_PATH (may not be defined)
        cookie_path = getattr(settings, "SESSION_COOKIE_PATH", "/")
        response.set_cookie(
            session_cookie_name,
            request.session.session_key,
            max_age=settings.SESSION_COOKIE_AGE,
            path=cookie_path,
            domain=settings.SESSION_COOKIE_DOMAIN,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=settings.SESSION_COOKIE_HTTPONLY,
            samesite=settings.SESSION_COOKIE_SAMESITE,
        )

    return response
