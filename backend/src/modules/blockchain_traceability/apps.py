"""Django lifecycle wiring and fail-fast module-contract validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from django.apps import AppConfig
from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured

from src.core.module_manifest_schema import manifest_validator


def _mapping_list(value: object, field_name: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ImproperlyConfigured(f"Manifest metadata.{field_name} must be a list of objects.")
    return value


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ImproperlyConfigured(f"Manifest metadata.{field_name} must be a list of non-empty strings.")
    if len(value) != len(set(value)):
        raise ImproperlyConfigured(f"Manifest metadata.{field_name} contains duplicate declarations.")
    return value


def _declared_sod_pairs(value: object) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for declaration in _mapping_list(value, "sod_pairs"):
        actions = declaration.get("actions")
        if (
            not isinstance(actions, Sequence)
            or isinstance(actions, (str, bytes))
            or len(actions) != 2
            or any(not isinstance(action, str) or not action for action in actions)
        ):
            raise ImproperlyConfigured("Every manifest metadata.sod_pairs entry must declare exactly two actions.")
        pair = (actions[0], actions[1])
        if pair[0] == pair[1]:
            raise ImproperlyConfigured("A separation-of-duties pair must contain distinct actions.")
        pairs.append(pair)
    if len(pairs) != len(set(pairs)):
        raise ImproperlyConfigured("Manifest metadata.sod_pairs contains duplicate pairs.")
    return tuple(pairs)


def validate_manifest_runtime_contract(app_config: AppConfig | None = None) -> None:
    """Reject drift between declarative claims and executable registrations.

    This is deliberately invoked from ``ready``. A mismatched permission,
    SoD pair, entity, endpoint, or AI capability prevents the application from
    starting instead of leaving a misleading compliance declaration active.
    """

    from .permissions import PERMISSIONS, SOD_ACTIONS
    from .urls import STANDALONE_ENDPOINTS, router

    manifest_path = Path(__file__).with_name("manifest.yaml")
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ImproperlyConfigured("Blockchain traceability manifest could not be loaded.") from exc
    if not isinstance(raw, Mapping):
        raise ImproperlyConfigured("Blockchain traceability manifest must be a YAML object.")

    manifest = manifest_validator.validate(dict(raw))
    if len(manifest.permissions) != len(set(manifest.permissions)):
        raise ImproperlyConfigured("Manifest permissions contain duplicate declarations.")
    if set(manifest.permissions) != set(PERMISSIONS):
        raise ImproperlyConfigured("Manifest permissions do not match executable permission policy.")

    metadata = manifest.metadata
    declared_pairs = _declared_sod_pairs(metadata.get("sod_pairs"))
    if declared_pairs != SOD_ACTIONS:
        raise ImproperlyConfigured("Manifest SoD pairs do not match executable permission policy.")
    flattened_pairs = tuple(action for pair in declared_pairs for action in pair)
    if tuple(manifest.sod_actions) != flattened_pairs:
        raise ImproperlyConfigured("Manifest sod_actions must be the ordered flattening of metadata.sod_pairs.")
    if any(action not in PERMISSIONS for action in flattened_pairs):
        raise ImproperlyConfigured("Manifest SoD policy references an undeclared permission.")

    if manifest.ai_tools:
        raise ImproperlyConfigured("Manifest declares AI tools, but this module has no AI-tool registry.")

    config = app_config
    if config is None or getattr(config, "models", None) is None:
        # Unit tests may instantiate AppConfig directly to exercise ready();
        # use the populated global registry for those equivalent instances.
        config = django_apps.get_app_config("blockchain_traceability")
    actual_entities = {model._meta.db_table for model in config.get_models()}
    declared_entities = set(_string_list(metadata.get("entities"), "entities"))
    if declared_entities != actual_entities:
        raise ImproperlyConfigured("Manifest entities do not match registered Django model tables.")

    endpoint_declarations = _mapping_list(metadata.get("endpoints"), "endpoints")
    declared_router: dict[str, tuple[str, str]] = {}
    declared_paths: dict[str, str] = {}
    for endpoint in endpoint_declarations:
        registration = endpoint.get("registration")
        if registration == "router":
            prefix = endpoint.get("prefix")
            basename = endpoint.get("basename")
            viewset = endpoint.get("viewset")
            if (
                not isinstance(prefix, str)
                or not prefix
                or not isinstance(basename, str)
                or not basename
                or not isinstance(viewset, str)
                or not viewset
            ):
                raise ImproperlyConfigured("Router endpoint declarations require prefix, basename, and viewset.")
            if prefix in declared_router:
                raise ImproperlyConfigured(f"Manifest declares router prefix '{prefix}' more than once.")
            declared_router[prefix] = (basename, viewset)
        elif registration == "path":
            route, name = endpoint.get("route"), endpoint.get("name")
            if not isinstance(route, str) or not route or not isinstance(name, str) or not name:
                raise ImproperlyConfigured("Path endpoint declarations require route and name.")
            if route in declared_paths:
                raise ImproperlyConfigured(f"Manifest declares standalone route '{route}' more than once.")
            declared_paths[route] = name
        else:
            raise ImproperlyConfigured("Endpoint registration must be either 'router' or 'path'.")

    actual_router = {str(prefix): (str(basename), viewset.__name__) for prefix, viewset, basename in router.registry}
    if len(actual_router) != len(router.registry):
        raise ImproperlyConfigured("DRF router contains duplicate endpoint prefixes.")
    if declared_router != actual_router:
        raise ImproperlyConfigured("Manifest router endpoints do not match DRF router registrations.")
    if declared_paths != STANDALONE_ENDPOINTS:
        raise ImproperlyConfigured("Manifest standalone endpoints do not match Django URL registrations.")


class BlockchainTraceabilityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "src.modules.blockchain_traceability"
    label = "blockchain_traceability"
    verbose_name = "Blockchain Traceability"

    def ready(self) -> None:
        validate_manifest_runtime_contract(self)

        from src.core.async_jobs.services import HandlerAlreadyRegistered, get_handler, register_handler

        from .providers import register_builtin_adapters
        from .services import LedgerAnchorService

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


__all__ = ["BlockchainTraceabilityConfig", "validate_manifest_runtime_contract"]
