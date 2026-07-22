"""Django integration registration for the email-marketing runtime."""

from django.apps import AppConfig


class EmailMarketingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.email_marketing"
    label = "email_marketing"
    verbose_name = "Email Marketing"

    def ready(self) -> None:
        from .adapters import register_builtin_adapters
        from .health import register_health_probes
        from .jobs import register_job_handlers
        from .state_machines import ensure_state_machines_registered

        register_builtin_adapters()
        ensure_state_machines_registered()
        register_job_handlers()
        register_health_probes()


__all__ = ["EmailMarketingConfig"]
