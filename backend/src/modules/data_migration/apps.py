"""Data-migration startup registration."""

from django.apps import AppConfig


class DataMigrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.data_migration"
    label = "data_migration"

    def ready(self) -> None:
        # Importing tasks performs duplicate-safe durable-handler registration.
        from . import tasks  # noqa: F401
