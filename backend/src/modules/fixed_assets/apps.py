"""Django registration for fixed-assets state machines and workers."""

from django.apps import AppConfig


class FixedAssetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.fixed_assets"
    label = "fixed_assets"
    verbose_name = "Fixed Assets"

    def ready(self) -> None:
        from src.core.state_machine import registry

        from .models import ASSET_STATE_MACHINE, LINE_STATE_MACHINE, SCHEDULE_STATE_MACHINE
        from .workers import register_handlers

        for name, machine in (
            ("fixed_assets.asset", ASSET_STATE_MACHINE),
            ("fixed_assets.schedule", SCHEDULE_STATE_MACHINE),
            ("fixed_assets.depreciation_line", LINE_STATE_MACHINE),
        ):
            try:
                current = registry.get(name)
            except LookupError:
                registry.register(name, machine)
            else:
                if current is not machine:
                    raise RuntimeError(f"A different state machine is already registered as {name!r}.")
        register_handlers()


__all__ = ["FixedAssetsConfig"]
