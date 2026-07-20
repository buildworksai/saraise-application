"""
Core app configuration.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Core app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.core"
    verbose_name = "SARAISE Core"

    def ready(self) -> None:
        """Register core model checks and observability signal handlers."""
        from .tenancy import registry  # noqa: F401
        from src.core.observability import correlation  # noqa: F401
