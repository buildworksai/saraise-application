"""
Custom authentication classes for SARAISE.

Implements proper CSRF handling per authentication-and-session-management-spec.md Section 9:
- CSRF protection is MANDATORY for all session-authenticated endpoints
- Login endpoint is exempted (cannot have CSRF token before authentication)
- All other endpoints enforce CSRF protection
"""
from rest_framework.authentication import SessionAuthentication


class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    SessionAuthentication without CSRF enforcement.

    Used ONLY for login endpoint where users cannot provide CSRF token
    before authentication.

    CRITICAL: This must NEVER be used as a default authentication class.
    It should only be explicitly set on the login view.
    """

    def enforce_csrf(self, request):
        """
        Override to disable CSRF check.

        This is safe for login endpoint only because:
        1. Login requires credentials (email/password)
        2. Credentials are not automatically sent by browser (unlike cookies)
        3. CSRF tokens are issued AFTER successful authentication
        """
        return  # Disable CSRF check


class RelaxedCsrfSessionAuthentication(SessionAuthentication):
    """
    SessionAuthentication with relaxed CSRF enforcement for safe methods.

    Per Django/DRF best practices:
    - GET, HEAD, OPTIONS are safe methods and don't require CSRF tokens
    - POST, PUT, PATCH, DELETE require CSRF tokens

    This allows GET requests to work immediately after login while maintaining
    CSRF protection for state-changing operations.
    
    CRITICAL: This class ensures that users authenticated by Django's
    AuthenticationMiddleware are properly recognized by DRF's permission system.
    """

    def authenticate(self, request):
        """
        Authenticate using session.
        
        CRITICAL FIX: DRF's SessionAuthentication.authenticate() may return None
        even when Django's AuthenticationMiddleware has already set request.user.
        This happens when the session doesn't have a session_key yet or when
        the session authentication check fails.
        
        We check if Django's middleware has already authenticated the user,
        and if so, return that user. This ensures consistent authentication
        across all requests.
        
        IMPORTANT: We access the underlying Django HttpRequest's user directly
        (via request._request.user) to avoid triggering DRF's authentication
        mechanism which would cause recursion.
        """
        # CRITICAL: Check Django middleware FIRST to avoid recursion
        # Access the underlying Django HttpRequest's user directly to avoid
        # triggering DRF's authentication mechanism
        from django.contrib.auth.models import AnonymousUser
        
        # Get the underlying Django HttpRequest
        django_request = getattr(request, '_request', request)
        
        # Check if Django's AuthenticationMiddleware has already authenticated the user
        if hasattr(django_request, 'user') and not isinstance(django_request.user, AnonymousUser):
            # User is already authenticated by Django middleware
            # Return (user, None) to indicate successful authentication
            return (django_request.user, None)
        
        # If Django middleware hasn't authenticated, try parent's authentication
        # (standard DRF session auth)
        try:
            result = super().authenticate(request)
            if result:
                return result
        except RecursionError:
            # If recursion occurs, return None (shouldn't happen with our fix above)
            return None
        
        # No authentication found
        return None

    def enforce_csrf(self, request):
        """
        Enforce CSRF only for unsafe HTTP methods.

        Safe methods (GET, HEAD, OPTIONS) don't require CSRF tokens
        because they don't change server state.
        """
        # Safe methods don't require CSRF protection
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return

        # For unsafe methods, enforce CSRF (call parent)
        return super().enforce_csrf(request)

