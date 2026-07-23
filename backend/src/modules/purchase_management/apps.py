from django.apps import AppConfig


class PurchaseManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.purchase_management"

    def ready(self):
        from .jobs import register_job_handlers
        from .state_machines import register_state_machines

        register_state_machines()
        register_job_handlers()
