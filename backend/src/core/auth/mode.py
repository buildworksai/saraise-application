"""
Mode detection utilities for authentication routing.

Per AGENTS.md: Mode determines authentication behavior:
- self-hosted: Django built-in auth
- saas: Delegated to saraise-auth
- development: Relaxed auth for testing
"""

from typing import Literal

from django.conf import settings


def get_saraise_mode() -> Literal["development", "self-hosted", "saas"]:
    """Get current SARAISE mode."""
    return getattr(settings, "SARAISE_MODE", "development")


def is_self_hosted() -> bool:
    """Check if running in self-hosted mode."""
    return get_saraise_mode() == "self-hosted"


def is_saas() -> bool:
    """Check if running in SaaS mode."""
    return get_saraise_mode() == "saas"


def is_development() -> bool:
    """Check if running in development mode."""
    return get_saraise_mode() == "development"
