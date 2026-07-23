"""
Security & Access Control App Configuration
"""

from django.apps import AppConfig


class SecurityAccessControlConfig(AppConfig):
    """App configuration for Security & Access Control module."""

    name = "src.modules.security_access_control"
    label = "security_access_control"
    verbose_name = "Security & Access Control"

    def ready(self) -> None:
        """Verify the security logger cannot emit unstructured records."""
        from .observability import enforce_security_json_logging

        enforce_security_json_logging()
