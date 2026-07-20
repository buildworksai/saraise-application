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
        """Register process-boundary observability signal handlers."""
        from src.core.observability import correlation  # noqa: F401
