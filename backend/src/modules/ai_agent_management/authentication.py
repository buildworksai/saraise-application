"""Authentication policy for the governed AI Agent Management API."""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication


class GovernedSessionAuthentication(SessionAuthentication):
    """Enforce normal session/CSRF checks and advertise a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"
