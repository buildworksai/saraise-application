"""Django application configuration for the customization framework."""

from django.apps import AppConfig


class CustomizationFrameworkConfig(AppConfig):
    """Declare stable Django metadata for the foundation module."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.customization_framework"
    label = "customization_framework"
    verbose_name = "Customization Framework"

    def ready(self) -> None:
        """Register lifecycle machines even when API URL loading is deferred."""

        from . import services

        del services


__all__ = ["CustomizationFrameworkConfig"]
