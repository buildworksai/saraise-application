"""Application lifecycle registration for compliance risk management."""

from django.apps import AppConfig


class ComplianceRiskManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.compliance_risk_management"

    def ready(self) -> None:
        # Importing jobs performs idempotent handler registration. Health
        # registration is explicit so application readiness sees this module.
        from . import jobs  # noqa: F401
        from .health import register_health_probes

        register_health_probes()
