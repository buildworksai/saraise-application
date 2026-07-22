"""Django registration for the CRM domain module."""

from django.apps import AppConfig


class CRMConfig(AppConfig):
    """Register CRM's guarded workflows, workers, and readiness probes."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.crm"
    label = "crm"
    verbose_name = "Customer Relationship Management"

    def ready(self) -> None:
        # Importing jobs installs the durable command handlers. State-machine
        # registration is explicit and idempotent for autoreload/test safety.
        from . import jobs
        from .health import register_health_probes
        from .state_machines import register_state_machines

        del jobs
        register_state_machines()
        register_health_probes()


__all__ = ["CRMConfig"]
