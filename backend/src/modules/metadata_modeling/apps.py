"""Django application configuration for metadata modeling."""

from django.apps import AppConfig


class MetadataModelingConfig(AppConfig):
    """Load extension system checks without importing persistence models early."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.metadata_modeling"

    def ready(self) -> None:
        # Importing registers the checks through Django's check registry.
        from . import registry  # noqa: F401
        from .state_machine import register_entity_state_machine
        from .handlers import register_handlers

        register_entity_state_machine()
        register_handlers()
