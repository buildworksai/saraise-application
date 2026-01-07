"""
Authentication API endpoints.

Handles login, logout, session management, and current user retrieval.

Per authentication-and-session-management-spec.md Section 9:
- CSRF protection is MANDATORY for all session-authenticated endpoints
- Login endpoint uses CsrfExemptSessionAuthentication (cannot have token before auth)
- All other endpoints use standard SessionAuthentication with CSRF enforcement
"""
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from django.core.exceptions import ValidationError
from django.contrib.auth import login, logout
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import ensure_csrf_cookie
from src.core.authentication import CsrfExemptSessionAuthentication, RelaxedCsrfSessionAuthentication
from src.core.user_models import UserProfile
import uuid

User = get_user_model()


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([CsrfExemptSessionAuthentication])
@ensure_csrf_cookie
def login_view(request):
    """
    Login endpoint.

    Creates a session for authenticated users.
    """
    email = request.data.get('email')
    password = request.data.get('password')
    mfa_token = request.data.get('mfa_token')

    if not email or not password:
        return Response(
            {'error': 'Email and password are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Authenticate user
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Check password
    if not user.check_password(password):
        return Response(
            {'error': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # TODO: MFA validation (for now, skip if mfa_token provided)
    if mfa_token:
        # Placeholder for MFA validation
        pass

    # Login user (creates session)
    login(request, user)
    
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
            {'error': 'User profile is misconfigured', 'details': e.message_dict},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Build user response
    user_data = {
        'id': str(user.id),
        'email': user.email,
        'username': user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'tenant_id': profile.tenant_id,
        'platform_role': profile.platform_role,
        'tenant_role': profile.tenant_role,
    }
    
    return Response({
        'user': user_data,
        'session_id': request.session.session_key or str(uuid.uuid4()),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Logout endpoint.

    Invalidates the current session.
    """
    logout(request)
    return Response({'message': 'Logged out successfully'}, status=status.HTTP_200_OK)


@api_view(['GET'])
@authentication_classes([RelaxedCsrfSessionAuthentication])  # GET requests don't need CSRF
@permission_classes([IsAuthenticated])
def current_user_view(request):
    """
    Get current authenticated user.
    """
    # Debug: Check authentication state
    if not request.user or not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated', 'user_type': str(type(request.user))},
            status=status.HTTP_401_UNAUTHORIZED
        )

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
            {'error': 'User profile is misconfigured', 'details': e.message_dict},
            status=status.HTTP_403_FORBIDDEN,
        )

    user_data = {
        'id': str(user.id),
        'email': user.email,
        'username': user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'tenant_id': profile.tenant_id,
        'platform_role': profile.platform_role,
        'tenant_role': profile.tenant_role,
    }
    
    return Response({'user': user_data}, status=status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([IsAuthenticated])
def refresh_session_view(request):
    """
    Refresh session validity.
    """
    # Django sessions are automatically refreshed on access
    # This endpoint just validates the session is still valid
    return Response({'message': 'Session refreshed'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
@authentication_classes([CsrfExemptSessionAuthentication])
@ensure_csrf_cookie
def register_view(request):
    """
    User registration endpoint.

    Phase 7.5: In self-hosted mode, initializes 14-day trial on first registration.
    """
    from django.conf import settings
    from src.core.licensing.models import Organization, License
    from src.core.licensing.services import LicenseService

    email = request.data.get('email')
    password = request.data.get('password')
    organization_name = request.data.get('organization_name', 'My Organization')
    
    if not email or not password:
        return Response(
            {'error': 'Email, password, and organization name are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if user already exists
    if User.objects.filter(email=email).exists():
        return Response(
            {'error': 'User with this email already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Only allow registration in self-hosted mode
    mode = getattr(settings, 'SARAISE_MODE', 'development')
    if mode == 'saas':
        return Response(
            {'error': 'Registration is handled by the platform in SaaS mode'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Create user
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
    )
    
    # Create user profile
    profile = UserProfile.objects.create(user=user)
    
    # Phase 7.5: Initialize trial if this is the first registration (self-hosted mode)
    if mode == 'self-hosted':
        # Check if this is the first registration (no license exists)
        existing_license = License.objects.first()
        if not existing_license:
            # First registration - create organization and start trial
            organization = Organization.objects.create(
                name=organization_name,
                domain=email.split('@')[1] if '@' in email else '',
            )
            LicenseService.initialize_trial(organization)
            
            # Set tenant_id for self-hosted mode (single tenant)
            # In self-hosted mode, all users belong to the same organization
            profile.tenant_id = str(organization.id)
            profile.tenant_role = 'tenant_admin'  # First user is admin
            profile.save()
        else:
            # Subsequent registration - use existing organization
            organization = existing_license.organization
            profile.tenant_id = str(organization.id)
            profile.tenant_role = 'tenant_user'
            profile.save()

    # Auto-login after registration
    login(request, user)
    
    user_data = {
        'id': str(user.id),
        'email': user.email,
        'username': user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'tenant_id': profile.tenant_id,
        'platform_role': profile.platform_role,
        'tenant_role': profile.tenant_role,
    }
    
    return Response({
        'user': user_data,
        'session_id': request.session.session_key or str(uuid.uuid4()),
        'message': 'Registration successful',
    }, status=status.HTTP_201_CREATED)

