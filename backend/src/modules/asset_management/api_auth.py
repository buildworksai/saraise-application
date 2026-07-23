"""Authentication helpers for Asset Management API controllers."""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication


class StrictSessionAuthentication(SessionAuthentication):
    """Enforce Django's CSRF validation and advertise a 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


__all__ = ["StrictSessionAuthentication"]
