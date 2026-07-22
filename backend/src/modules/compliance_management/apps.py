"""Django lifecycle wiring for compliance management."""

from django.apps import AppConfig


class ComplianceManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.compliance_management"
    label = "compliance_management"
    verbose_name = "Compliance Management"

    def ready(self) -> None:
        # Importing tasks installs its explicitly decorated durable handlers.
        from . import tasks  # noqa: F401
        from .health import register_health_probe
        from .state_machines import register_compliance_state_machines

        register_compliance_state_machines()
        register_health_probe()


__all__ = ["ComplianceManagementConfig"]
