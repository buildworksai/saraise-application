"""Application registration for bank-reconciliation support contracts."""

from django.apps import AppConfig


class BankReconciliationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.bank_reconciliation"
    label = "bank_reconciliation"

    def ready(self) -> None:
        # Imports perform explicit, validated registry registration. Django
        # invokes ready once per process after every model is loaded.
        from . import state_machines, tasks
        from .health import register_health_probes

        del state_machines, tasks
        register_health_probes()


__all__ = ["BankReconciliationConfig"]
