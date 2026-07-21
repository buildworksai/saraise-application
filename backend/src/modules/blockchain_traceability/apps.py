"""Django lifecycle wiring for durable traceability commands."""

from django.apps import AppConfig


class BlockchainTraceabilityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.blockchain_traceability"
    label = "blockchain_traceability"
    verbose_name = "Blockchain Traceability"

    def ready(self) -> None:
        from src.core.async_jobs.services import HandlerAlreadyRegistered, get_handler, register_handler

        from .services import LedgerAnchorService
        from .providers import register_builtin_adapters

        register_builtin_adapters()
        candidate = LedgerAnchorService().submit_anchor_job
        try:
            register_handler("blockchain_traceability.submit_anchor", candidate)
        except HandlerAlreadyRegistered:
            existing = get_handler("blockchain_traceability.submit_anchor")

            def identity(handler: object) -> tuple[str, str]:
                function = getattr(handler, "__func__", handler)
                return (str(getattr(function, "__module__", "")), str(getattr(function, "__qualname__", "")))

            # Django's autoreloader may create a new bound service instance. A
            # different function owner remains a hard registration failure.
            if identity(existing) != identity(candidate):
                raise


__all__ = ["BlockchainTraceabilityConfig"]
