"""Deny-by-default authorization metadata for CRM.

The API layer must resolve every DRF action through these immutable mappings.
There is deliberately no read/write fallback: adding a new endpoint without a
permission decision is a deployment-blocking error rather than an accidental
grant.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Final, Mapping

PERMISSIONS: Final[tuple[str, ...]] = (
    "crm.lead:create",
    "crm.lead:read",
    "crm.lead:update",
    "crm.lead:delete",
    "crm.lead:convert",
    "crm.lead:score",
    "crm.account:create",
    "crm.account:read",
    "crm.account:update",
    "crm.account:delete",
    "crm.contact:create",
    "crm.contact:read",
    "crm.contact:update",
    "crm.contact:delete",
    "crm.contact:override_domain",
    "crm.opportunity:create",
    "crm.opportunity:read",
    "crm.opportunity:update",
    "crm.opportunity:delete",
    "crm.opportunity:close",
    "crm.opportunity:reopen_stage",
    "crm.activity:create",
    "crm.activity:read",
    "crm.activity:update",
    "crm.activity:complete",
    "crm.forecasting:read",
    "crm.forecasting:predict",
    "crm.configuration:read",
    "crm.configuration:write",
    "crm.configuration:import",
    "crm.configuration:export",
    "crm.configuration:rollback",
    "crm.health:read",
)

SOD_ACTIONS: Final[tuple[str, ...]] = (
    "crm.opportunity:create",
    "crm.opportunity:close",
)


class PermissionMappingError(PermissionError):
    """Raised when a protected API action has no declared permission."""


def _mapping(values: Mapping[str, str]) -> Mapping[str, str]:
    undeclared = set(values.values()) - set(PERMISSIONS)
    if undeclared:
        raise RuntimeError(f"CRM action map contains undeclared permissions: {sorted(undeclared)!r}")
    return MappingProxyType(dict(values))


# PUT/update is intentionally absent. CRM v2 supports PATCH and guarded
# commands only, so ModelViewSet cannot accidentally expose full replacement.
LEAD_ACTION_PERMISSIONS: Final = _mapping(
    {
        "list": "crm.lead:read",
        "retrieve": "crm.lead:read",
        "create": "crm.lead:create",
        "partial_update": "crm.lead:update",
        "destroy": "crm.lead:delete",
        "transition": "crm.lead:update",
        "convert": "crm.lead:convert",
        "score": "crm.lead:score",
    }
)
ACCOUNT_ACTION_PERMISSIONS: Final = _mapping(
    {
        "list": "crm.account:read",
        "retrieve": "crm.account:read",
        "create": "crm.account:create",
        "partial_update": "crm.account:update",
        "destroy": "crm.account:delete",
        "hierarchy": "crm.account:read",
        "duplicates": "crm.account:read",
    }
)
CONTACT_ACTION_PERMISSIONS: Final = _mapping(
    {
        "list": "crm.contact:read",
        "retrieve": "crm.contact:read",
        "create": "crm.contact:create",
        "partial_update": "crm.contact:update",
        "destroy": "crm.contact:delete",
    }
)
OPPORTUNITY_ACTION_PERMISSIONS: Final = _mapping(
    {
        "list": "crm.opportunity:read",
        "retrieve": "crm.opportunity:read",
        "create": "crm.opportunity:create",
        "partial_update": "crm.opportunity:update",
        "destroy": "crm.opportunity:delete",
        "transition": "crm.opportunity:update",
        "close_won": "crm.opportunity:close",
        "close_lost": "crm.opportunity:close",
    }
)
ACTIVITY_ACTION_PERMISSIONS: Final = _mapping(
    {
        "list": "crm.activity:read",
        "retrieve": "crm.activity:read",
        "create": "crm.activity:create",
        "partial_update": "crm.activity:update",
        "complete": "crm.activity:complete",
    }
)
FORECAST_ACTION_PERMISSIONS: Final = _mapping(
    {
        "pipeline": "crm.forecasting:read",
        "win_rate": "crm.forecasting:read",
        "by_stage": "crm.forecasting:read",
        "predict": "crm.forecasting:predict",
    }
)

CONFIGURATION_ACTION_PERMISSIONS: Final = _mapping(
    {
        "list": "crm.configuration:read",
        "update": "crm.configuration:write",
        "partial_update": "crm.configuration:write",
        "preview": "crm.configuration:write",
        "versions": "crm.configuration:read",
        "rollback": "crm.configuration:rollback",
        "import_configuration": "crm.configuration:import",
        "export_configuration": "crm.configuration:export",
    }
)
# Job retrieval is command-dependent. The empty static action map deliberately
# denies generic resolution; JobViewSet must call permission_for_job_command
# after a tenant-scoped lookup.
JOB_ACTION_PERMISSIONS: Final = _mapping({})
HEALTH_ACTION_PERMISSIONS: Final = _mapping({"retrieve": "crm.health:read"})
JOB_COMMAND_PERMISSIONS: Final = _mapping(
    {
        "crm.scan_stale_deals": "crm.opportunity:read",
        "crm.score_lead": "crm.lead:score",
        "crm.sync_external_activity": "crm.activity:create",
        "crm.acknowledge_sales_order": "crm.opportunity:close",
    }
)

ACTION_PERMISSION_MAPS: Final[Mapping[str, Mapping[str, str]]] = MappingProxyType(
    {
        "lead": LEAD_ACTION_PERMISSIONS,
        "account": ACCOUNT_ACTION_PERMISSIONS,
        "contact": CONTACT_ACTION_PERMISSIONS,
        "opportunity": OPPORTUNITY_ACTION_PERMISSIONS,
        "activity": ACTIVITY_ACTION_PERMISSIONS,
        "forecasting": FORECAST_ACTION_PERMISSIONS,
        "configuration": CONFIGURATION_ACTION_PERMISSIONS,
        "job": JOB_ACTION_PERMISSIONS,
        "health": HEALTH_ACTION_PERMISSIONS,
    }
)


def permission_for_action(resource: str, action: str) -> str:
    """Resolve one API action or deny it when metadata is incomplete."""

    try:
        return ACTION_PERMISSION_MAPS[resource][action]
    except KeyError as exc:
        raise PermissionMappingError(f"No CRM permission is declared for {resource}.{action}") from exc


def permission_for_job_command(command: str) -> str:
    """Resolve the initiating capability for a tenant-scoped durable job."""

    try:
        return JOB_COMMAND_PERMISSIONS[command]
    except KeyError as exc:
        raise PermissionMappingError(f"No CRM permission is declared for job command {command!r}") from exc


__all__ = [
    "ACCOUNT_ACTION_PERMISSIONS",
    "ACTION_PERMISSION_MAPS",
    "ACTIVITY_ACTION_PERMISSIONS",
    "CONTACT_ACTION_PERMISSIONS",
    "CONFIGURATION_ACTION_PERMISSIONS",
    "FORECAST_ACTION_PERMISSIONS",
    "HEALTH_ACTION_PERMISSIONS",
    "JOB_ACTION_PERMISSIONS",
    "JOB_COMMAND_PERMISSIONS",
    "LEAD_ACTION_PERMISSIONS",
    "OPPORTUNITY_ACTION_PERMISSIONS",
    "PERMISSIONS",
    "PermissionMappingError",
    "SOD_ACTIONS",
    "permission_for_action",
    "permission_for_job_command",
]
