"""
Mode-aware session middleware.

Per authentication-and-session-management-spec.md:
- Self-hosted: Validate sessions locally
- SaaS: Validate sessions with saraise-auth service
- Development: Relaxed validation
"""

from django.utils.deprecation import MiddlewareMixin

from .mode import is_development, is_saas
from .saas import validate_session


class ModeAwareSessionMiddleware(MiddlewareMixin):
    """
    Middleware that validates sessions based on operating mode.

    In SaaS mode, delegates session validation to saraise-auth.
    In self-hosted mode, uses Django's built-in session validation.
    """

    def process_request(self, request):
        """Validate session based on mode."""
        # Skip for development mode
        if is_development():
            return None

        # Skip for unauthenticated requests
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return None

        # SaaS mode: Validate with platform
        if is_saas():
            session_id = request.session.session_key
            if session_id:
                session_data = validate_session(session_id)
                if not session_data:
                    # Session invalid - clear it
                    request.session.flush()
                    # Set user to anonymous
                    from django.contrib.auth.models import AnonymousUser

                    request.user = AnonymousUser()
                    return None

                # Update user from session data
                # (session_data contains user info from platform)
                # Note: In SaaS mode, user object is managed by platform
                # We trust the session data from saraise-auth

        # Self-hosted mode: Django handles session validation automatically
        return None
