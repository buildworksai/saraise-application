"""Django application configuration for Master Data Management."""

from django.apps import AppConfig


class MasterDataManagementConfig(AppConfig):
    """Load durable job handlers in web and worker processes."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.master_data_management"

    def ready(self) -> None:
        # Importing the module performs idempotent handler registration.  This
        # hook is reached by every Django process, unlike the HTTP URL module.
        from .jobs import register_handlers

        register_handlers()

