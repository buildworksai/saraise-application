"""Django configuration for the backup capture and catalog authority."""

from django.apps import AppConfig


class BackupRecoveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.backup_recovery"
    label = "backup_recovery"
    verbose_name = "Backup & Recovery"

    def ready(self) -> None:
        # Importing constructs and validates the named machines.  The module
        # exports them directly so services do not depend on registry order.
        from . import state_machines  # noqa: F401
        from .tasks import register_handlers

        register_handlers()
