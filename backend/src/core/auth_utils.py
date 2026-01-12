"""
Authentication utilities for getting user tenant_id and roles.
"""

from typing import Optional

from django.contrib.auth import get_user_model

from src.core.user_models import UserProfile

User = get_user_model()


def get_user_tenant_id(user) -> Optional[str]:
    """Get tenant_id from user profile."""
    try:
        return user.profile.tenant_id
    except (UserProfile.DoesNotExist, AttributeError):
        return None


def get_user_platform_role(user) -> Optional[str]:
    """Get platform role from user profile."""
    try:
        return user.profile.platform_role
    except (UserProfile.DoesNotExist, AttributeError):
        return None


def get_user_tenant_role(user) -> Optional[str]:
    """Get tenant role from user profile."""
    try:
        return user.profile.tenant_role
    except (UserProfile.DoesNotExist, AttributeError):
        return None


def get_user_id(user) -> Optional[str]:
    """Get user ID as string."""
    if user and hasattr(user, "id"):
        return str(user.id)
    return None
