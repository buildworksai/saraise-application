"""Django application configuration for governed business intelligence."""

from django.apps import AppConfig
from django.core.signals import request_started


def _freeze_extension_registries(**kwargs: object) -> None:
    """Freeze contributions after every installed app has completed ``ready``."""

    del kwargs
    from .datasets import dataset_registry, template_registry, visualization_registry

    dataset_registry.freeze()
    template_registry.freeze()
    visualization_registry.freeze()


class BusinessIntelligenceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.business_intelligence"
    label = "business_intelligence"
    verbose_name = "Business Intelligence"

    def ready(self) -> None:
        from src.core.tenancy import TENANT_SCOPED, register_model_scope

        from .jobs import register_job_handlers
        from .models import Dashboard, DashboardShare, DashboardWidget, QueryDefinition, QueryExecution, Report

        register_job_handlers()
        for model in (QueryDefinition, Report, Dashboard, DashboardWidget, DashboardShare, QueryExecution):
            register_model_scope(model, TENANT_SCOPED)
        request_started.connect(
            _freeze_extension_registries,
            dispatch_uid="business_intelligence.freeze_extension_registries",
            weak=False,
        )


__all__ = ["BusinessIntelligenceConfig"]
