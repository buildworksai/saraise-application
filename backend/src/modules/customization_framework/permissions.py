"""Fail-closed access policy loaded from the authoritative module manifest."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

import yaml
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Complete declaration consumed by ``RequiresAccess`` for one action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1


def _load_manifest() -> Mapping[str, object]:
    path = Path(__file__).with_name("manifest.yaml")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ImproperlyConfigured("Customization framework manifest could not be loaded.") from exc
    if not isinstance(document, Mapping):
        raise ImproperlyConfigured("Customization framework manifest must be a YAML object.")
    return document


def _load_access_policy(
    manifest: Mapping[str, object],
) -> tuple[Mapping[str, AccessRequirement], tuple[str, ...], tuple[tuple[str, str], ...]]:
    raw_permissions = manifest.get("permissions")
    metadata = manifest.get("metadata")
    if not isinstance(raw_permissions, list) or any(not isinstance(item, str) for item in raw_permissions):
        raise ImproperlyConfigured("Manifest permissions must be a list of strings.")
    if len(raw_permissions) != len(set(raw_permissions)):
        raise ImproperlyConfigured("Manifest permissions contain duplicate declarations.")
    if not isinstance(metadata, Mapping):
        raise ImproperlyConfigured("Manifest metadata must be an object.")

    raw_policy = metadata.get("access_policy")
    if not isinstance(raw_policy, Mapping) or not raw_policy:
        raise ImproperlyConfigured("Manifest metadata.access_policy must be a non-empty object.")
    policy: dict[str, AccessRequirement] = {}
    for action_key, declaration in raw_policy.items():
        if not isinstance(action_key, str) or not action_key or not isinstance(declaration, Mapping):
            raise ImproperlyConfigured("Every access policy entry must map an action key to an object.")
        permission = declaration.get("permission")
        entitlement = declaration.get("entitlement")
        quota_resource = declaration.get("quota_resource")
        quota_cost = declaration.get("quota_cost")
        if (
            not isinstance(permission, str)
            or permission not in raw_permissions
            or not isinstance(entitlement, str)
            or not entitlement
            or not isinstance(quota_resource, str)
            or not quota_resource
            or not isinstance(quota_cost, int)
            or isinstance(quota_cost, bool)
            or quota_cost < 1
        ):
            raise ImproperlyConfigured(f"Manifest access policy entry '{action_key}' is invalid.")
        policy[action_key] = AccessRequirement(permission, entitlement, quota_resource, quota_cost)

    used_permissions = {requirement.permission for requirement in policy.values()}
    if used_permissions != set(raw_permissions):
        raise ImproperlyConfigured("Every manifest permission must be used by the access policy.")

    raw_pairs = metadata.get("sod_pairs")
    if not isinstance(raw_pairs, list):
        raise ImproperlyConfigured("Manifest metadata.sod_pairs must be a list.")
    pairs: list[tuple[str, str]] = []
    for declaration in raw_pairs:
        actions = declaration.get("actions") if isinstance(declaration, Mapping) else None
        if (
            not isinstance(actions, Sequence)
            or isinstance(actions, (str, bytes))
            or len(actions) != 2
            or any(not isinstance(action, str) or action not in raw_permissions for action in actions)
            or actions[0] == actions[1]
        ):
            raise ImproperlyConfigured("Every SoD declaration must contain two distinct manifest permissions.")
        pairs.append((actions[0], actions[1]))
    if len(pairs) != len(set(pairs)):
        raise ImproperlyConfigured("Manifest metadata.sod_pairs contains duplicate declarations.")

    flattened = [action for pair in pairs for action in pair]
    if manifest.get("sod_actions") != flattened:
        raise ImproperlyConfigured("Manifest sod_actions must be the ordered flattening of metadata.sod_pairs.")
    return MappingProxyType(policy), tuple(raw_permissions), tuple(pairs)


_MANIFEST = _load_manifest()
ACTION_ACCESS, PERMISSIONS, SOD_ACTIONS = _load_access_policy(_MANIFEST)
ACTION_ACCESS: Final[Mapping[str, AccessRequirement]]
PERMISSIONS: Final[tuple[str, ...]]
SOD_ACTIONS: Final[tuple[tuple[str, str], ...]]


def requirement_for(viewset: str, action: str, method: str | None = None) -> AccessRequirement | None:
    """Return a manifest declaration or ``None`` so callers deny unknown actions."""

    if method is not None:
        qualified = ACTION_ACCESS.get(f"{viewset}.{action}:{method.lower()}")
        if qualified is not None:
            return qualified
    return ACTION_ACCESS.get(f"{viewset}.{action}")


__all__ = [
    "ACTION_ACCESS",
    "AccessRequirement",
    "PERMISSIONS",
    "SOD_ACTIONS",
    "requirement_for",
]
