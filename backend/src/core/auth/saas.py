"""
SaaS mode authentication delegation to saraise-auth service.

Per authentication-and-session-management-spec.md Section 2A:
- Authentication is delegated to saraise-auth service
- Runtime validates sessions but never issues them
- Sessions are stored in shared Redis cluster
"""

from typing import Any, Dict, Optional

import requests
from django.conf import settings

from .mode import is_saas


def get_platform_url() -> str:
    """Get platform URL for SaaS mode."""
    return getattr(settings, "SARAISE_PLATFORM_URL", "http://localhost:18000")


def validate_session(session_id: str) -> Optional[Dict[str, Any]]:
    """
    Validate session with saraise-auth service.

    Returns session data if valid, None otherwise.
    """
    if not is_saas():
        return None

    try:
        response = requests.post(
            f"{get_platform_url()}/api/v1/auth/validate-session", json={"session_id": session_id}, timeout=5
        )

        if response.status_code == 200:
            return response.json()
        return None
    except requests.RequestException:
        return None


def delegate_login(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Delegate login to saraise-auth service.

    Returns session data if successful, None otherwise.
    """
    if not is_saas():
        return None

    try:
        response = requests.post(
            f"{get_platform_url()}/api/v1/auth/login", json={"email": email, "password": password}, timeout=10
        )

        if response.status_code == 200:
            return response.json()
        return None
    except requests.RequestException:
        return None
