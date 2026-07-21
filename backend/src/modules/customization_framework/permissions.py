"""Immutable, fail-closed access declarations for customization API v2."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Mapping


@dataclass(frozen=True, slots=True)
class AccessRequirement:
    """Complete declaration consumed by ``RequiresAccess`` for one action."""

    permission: str
    entitlement: str
    quota_resource: str
    quota_cost: int = 1


def _access(permission: str, quota: str, *, cost: int = 1) -> AccessRequirement:
    qualified = f"customization_framework.{permission}"
    return AccessRequirement(
        permission=qualified,
        entitlement=f"customization_framework.{permission.split(':', 1)[0]}",
        quota_resource=f"customization_framework.{quota}",
        quota_cost=cost,
    )


READ = "api_reads"
WRITE = "api_writes"

# Keys are ``<ViewSet basename>.<DRF action>``. Method-qualified keys are used
# where one custom DRF action intentionally serves both GET and POST.
_ACTION_ACCESS = {
    "resource-contract.list": _access("field_definition:read", READ),
    "field-definition.list": _access("field_definition:read", READ),
    "field-definition.retrieve": _access("field_definition:read", READ),
    "field-definition.create": _access("field_definition:create", WRITE),
    "field-definition.partial_update": _access("field_definition:update", WRITE),
    "field-definition.destroy": _access("field_definition:delete", WRITE),
    "field-definition.activate": _access("field_definition:publish", WRITE),
    "field-definition.deprecate": _access("field_definition:publish", WRITE),
    "field-definition.retire": _access("field_definition:publish", WRITE),
    "field-definition.impact": _access("impact:read", READ),
    "field-definition.validate_value": _access("field_value:validate", "validations"),
    "field-value.list": _access("field_value:read", READ),
    "field-value.retrieve": _access("field_value:read", READ),
    "field-value.create": _access("field_value:write", WRITE),
    "field-value.partial_update": _access("field_value:write", WRITE),
    "field-value.destroy": _access("field_value:delete", WRITE),
    "form.list": _access("form:read", READ),
    "form.retrieve": _access("form:read", READ),
    "form.create": _access("form:create", WRITE),
    "form.partial_update": _access("form:update", WRITE),
    "form.destroy": _access("form:delete", WRITE),
    "form.layout_versions:get": _access("form:read", READ),
    "form.layout_versions:post": _access("form:update", WRITE),
    "form.validate_layout": _access("form:update", "validations"),
    "form.publish": _access("form:publish", WRITE),
    "form.archive": _access("form:archive", WRITE),
    "form.render_schema": _access("form:read", READ),
    "form.impact": _access("impact:read", READ),
    "form-layout.list": _access("form:read", READ),
    "form-layout.retrieve": _access("form:read", READ),
    "rule.list": _access("rule:read", READ),
    "rule.retrieve": _access("rule:read", READ),
    "rule.create": _access("rule:create", WRITE),
    "rule.partial_update": _access("rule:update", WRITE),
    "rule.destroy": _access("rule:delete", WRITE),
    "rule.versions:get": _access("rule:read", READ),
    "rule.versions:post": _access("rule:update", WRITE),
    "rule.validate_version": _access("rule:update", "validations"),
    "rule.publish": _access("rule:publish", WRITE),
    "rule.pause": _access("rule:publish", WRITE),
    "rule.resume": _access("rule:publish", WRITE),
    "rule.retire": _access("rule:publish", WRITE),
    "rule.evaluate": _access("rule:evaluate", "rule_evaluations", cost=1),
    "rule.impact": _access("impact:read", READ),
    "rule-version.list": _access("rule:read", READ),
    "rule-version.retrieve": _access("rule:read", READ),
    "rule-execution.list": _access("execution:read", READ),
    "rule-execution.retrieve": _access("execution:read", READ),
    "health.get": _access("health:read", READ),
}

ACTION_ACCESS: Final[Mapping[str, AccessRequirement]] = MappingProxyType(_ACTION_ACCESS)
PERMISSIONS: Final[tuple[str, ...]] = tuple(sorted({item.permission for item in ACTION_ACCESS.values()}))
SOD_ACTIONS: Final[tuple[tuple[str, str], ...]] = (
    (
        "customization_framework.field_definition:create",
        "customization_framework.field_definition:publish",
    ),
    ("customization_framework.form:create", "customization_framework.form:publish"),
    ("customization_framework.rule:create", "customization_framework.rule:publish"),
    ("customization_framework.field_definition:update", "customization_framework.field_definition:delete"),
    ("customization_framework.rule:update", "customization_framework.rule:publish"),
)


def requirement_for(viewset: str, action: str, method: str | None = None) -> AccessRequirement | None:
    """Return a declaration or ``None``; callers must deny on ``None``."""

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
