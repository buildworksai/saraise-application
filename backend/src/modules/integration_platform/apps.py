"""Django startup for the integration platform extension surface."""

from django.apps import AppConfig


class IntegrationPlatformConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.integration_platform"
    label = "integration_platform"
    verbose_name = "Integration Platform"

    def ready(self) -> None:
        # No connector adapters are bundled implicitly.  Open and paid modules
        # register reviewed adapters from their own AppConfig.ready().
        from .jobs import register_job_handlers

        register_job_handlers()


__all__ = ["IntegrationPlatformConfig"]
