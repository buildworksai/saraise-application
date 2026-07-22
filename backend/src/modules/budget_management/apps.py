"""Django application configuration for budget management."""

from django.apps import AppConfig


class BudgetManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.budget_management"
    label = "budget_management"

    def ready(self) -> None:
        # Importing registers durable job handlers with the shared executor.
        from . import jobs  # noqa: F401

