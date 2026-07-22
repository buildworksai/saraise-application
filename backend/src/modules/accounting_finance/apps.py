"""Django bootstrap for accounting jobs and readiness registration."""

from django.apps import AppConfig


class AccountingFinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.accounting_finance"
    label = "accounting_finance"
    verbose_name = "Accounting & Finance"

    def ready(self) -> None:
        from .health import register_health_probe
        from .jobs import register_handlers

        register_handlers()
        register_health_probe()


__all__ = ["AccountingFinanceConfig"]
