"""Django registration for multi-company domain infrastructure."""

from django.apps import AppConfig


class MultiCompanyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.multi_company"
    label = "multi_company"
    verbose_name = "Multi-Company Management"

    def ready(self) -> None:
        # Imports register state-machine definitions and durable job handlers.
        from . import jobs, state_machines

        del jobs, state_machines


__all__ = ["MultiCompanyConfig"]
