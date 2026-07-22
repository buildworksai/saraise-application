"""Django registration for the Human Resources domain."""

from django.apps import AppConfig


class HumanResourcesConfig(AppConfig):
    """Register HR state machines and critical readiness probes."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.human_resources"
    label = "human_resources"
    verbose_name = "Human Resources"

    def ready(self) -> None:
        from .health import register_health_probes
        from .state_machines import register_state_machines

        register_state_machines()
        register_health_probes()


__all__ = ["HumanResourcesConfig"]
