"""Django application configuration for the customization framework."""

from collections.abc import Mapping
from pathlib import Path

import yaml
from django.apps import AppConfig
from django.core.exceptions import ImproperlyConfigured


def validate_manifest_runtime_contract(app_config: AppConfig) -> None:
    """Stop startup when the manifest and executable inventory diverge."""

    from .permissions import ACTION_ACCESS, PERMISSIONS, SOD_ACTIONS
    from .urls import router

    try:
        manifest = yaml.safe_load(Path(__file__).with_name("manifest.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ImproperlyConfigured("Customization framework manifest could not be loaded.") from exc
    if not isinstance(manifest, Mapping) or not isinstance(manifest.get("metadata"), Mapping):
        raise ImproperlyConfigured("Customization framework manifest must contain metadata.")
    metadata = manifest["metadata"]

    actual_entities = {model._meta.db_table for model in app_config.get_models()}
    if set(metadata.get("entities", ())) != actual_entities:
        raise ImproperlyConfigured("Customization manifest entities do not match Django models.")

    declared_router = {
        item.get("prefix"): (item.get("basename"), item.get("viewset"))
        for item in metadata.get("endpoints", ())
        if isinstance(item, Mapping) and item.get("registration") == "router"
    }
    actual_router = {prefix: (basename, viewset.__name__) for prefix, viewset, basename in router.registry}
    if declared_router != actual_router:
        raise ImproperlyConfigured("Customization manifest endpoints do not match DRF routes.")
    declared_paths = {
        (item.get("route"), item.get("name"))
        for item in metadata.get("endpoints", ())
        if isinstance(item, Mapping) and item.get("registration") == "path"
    }
    if declared_paths != {("health/", "health")}:
        raise ImproperlyConfigured("Customization manifest standalone endpoints are incomplete.")

    if tuple(manifest.get("permissions", ())) != PERMISSIONS:
        raise ImproperlyConfigured("Customization manifest permissions do not match runtime policy.")
    if set(metadata.get("access_policy", ())) != set(ACTION_ACCESS):
        raise ImproperlyConfigured("Customization manifest action access does not match runtime policy.")
    declared_pairs = tuple(
        tuple(item.get("actions", ())) for item in metadata.get("sod_pairs", ()) if isinstance(item, Mapping)
    )
    if declared_pairs != SOD_ACTIONS:
        raise ImproperlyConfigured("Customization manifest SoD policy does not match runtime policy.")


class CustomizationFrameworkConfig(AppConfig):
    """Declare stable Django metadata for the foundation module."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.customization_framework"
    label = "customization_framework"
    verbose_name = "Customization Framework"

    def ready(self) -> None:
        """Register lifecycle machines even when API URL loading is deferred."""

        from . import services

        del services
        validate_manifest_runtime_contract(self)


__all__ = ["CustomizationFrameworkConfig", "validate_manifest_runtime_contract"]
