"""Django application configuration and collision-safe registrations."""

from django.apps import AppConfig


class ProcessMiningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.process_mining"
    label = "process_mining"
    verbose_name = "Process Mining"

    def ready(self) -> None:
        from . import state_machines, tasks
        from .adapters import register_local_adapters
        from .health import register_health_probes

        del state_machines, tasks
        register_local_adapters()
        register_health_probes()


__all__ = ["ProcessMiningConfig"]

