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

