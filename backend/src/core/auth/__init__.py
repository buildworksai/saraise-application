"""
SARAISE Authentication Module

Provides mode-aware authentication:
- Self-hosted: Django built-in authentication
- SaaS: Delegation to saraise-auth service
- Development: Relaxed authentication for testing
"""

from .mode import get_saraise_mode, is_development, is_saas, is_self_hosted

__all__ = [
    "get_saraise_mode",
    "is_self_hosted",
    "is_saas",
    "is_development",
]
