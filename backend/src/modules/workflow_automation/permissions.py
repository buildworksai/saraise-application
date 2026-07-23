"""Authoritative access metadata for workflow automation routes."""

from __future__ import annotations

from typing import Final

MODULE_ENTITLEMENT: Final = "module.workflow_automation"

PERMISSIONS: list[str] = [
    "workflow_automation.workflow:read",
    "workflow_automation.workflow:create",
    "workflow_automation.workflow:update",
    "workflow_automation.workflow:delete",
    "workflow_automation.workflow:publish",
    "workflow_automation.workflow:archive",
    "workflow_automation.instance:read",
    "workflow_automation.instance:start",
    "workflow_automation.instance:cancel",
    "workflow_automation.task:read",
    "workflow_automation.task:complete",
    "workflow_automation.task:reject",
    "workflow_automation.catalog:read",
    "workflow_automation.configuration:read",
    "workflow_automation.configuration:write",
    "workflow_automation.configuration:rollback",
    "workflow_automation.configuration:import",
    "workflow_automation.configuration:export",
    "workflow_automation.health:read",
]

# Policy-only grants used for object-sensitive task decisions.  These do not
# replace action permissions and are never inferred from authorship.
POLICY_PERMISSIONS: list[str] = [
    "workflow_automation.task:manage",
    "workflow_automation.task:self_approve",
]

SOD_ACTIONS: list[str] = [
    "workflow_automation.workflow:publish",
    "workflow_automation.workflow:delete",
]

ACTION_ACCESS: dict[str, tuple[str, str]] = {
    "workflow_list": ("workflow_automation.workflow:read", "workflow_automation.api_reads"),
    "workflow_retrieve": ("workflow_automation.workflow:read", "workflow_automation.api_reads"),
    "workflow_create": ("workflow_automation.workflow:create", "workflow_automation.api_writes"),
    "workflow_partial_update": ("workflow_automation.workflow:update", "workflow_automation.api_writes"),
    "workflow_destroy": ("workflow_automation.workflow:delete", "workflow_automation.api_writes"),
    "workflow_validate": ("workflow_automation.workflow:create", "workflow_automation.api_writes"),
    "workflow_publish": ("workflow_automation.workflow:publish", "workflow_automation.api_writes"),
    "workflow_archive": ("workflow_automation.workflow:archive", "workflow_automation.api_writes"),
    "workflow_clone": ("workflow_automation.workflow:create", "workflow_automation.api_writes"),
    "instance_list": ("workflow_automation.instance:read", "workflow_automation.api_reads"),
    "instance_retrieve": ("workflow_automation.instance:read", "workflow_automation.api_reads"),
    "instance_create": ("workflow_automation.instance:start", "workflow_automation.executions"),
    "instance_cancel": ("workflow_automation.instance:cancel", "workflow_automation.executions"),
    "task_list": ("workflow_automation.task:read", "workflow_automation.api_reads"),
    "task_retrieve": ("workflow_automation.task:read", "workflow_automation.api_reads"),
    "task_complete": ("workflow_automation.task:complete", "workflow_automation.task_decisions"),
    "task_reject": ("workflow_automation.task:reject", "workflow_automation.task_decisions"),
    "catalog": ("workflow_automation.catalog:read", "workflow_automation.api_reads"),
    "catalog_actions": ("workflow_automation.catalog:read", "workflow_automation.api_reads"),
    "catalog_conditions": ("workflow_automation.catalog:read", "workflow_automation.api_reads"),
    "catalog_subjects": ("workflow_automation.catalog:read", "workflow_automation.api_reads"),
    "catalog_assignees": ("workflow_automation.catalog:read", "workflow_automation.api_reads"),
    "catalog_lookup": ("workflow_automation.catalog:read", "workflow_automation.api_reads"),
    "configuration_list": ("workflow_automation.configuration:read", "workflow_automation.api_reads"),
    "configuration_update": ("workflow_automation.configuration:write", "workflow_automation.api_writes"),
    "configuration_preview": ("workflow_automation.configuration:write", "workflow_automation.api_reads"),
    "configuration_history": ("workflow_automation.configuration:read", "workflow_automation.api_reads"),
    "configuration_rollback": ("workflow_automation.configuration:rollback", "workflow_automation.api_writes"),
    "configuration_import_configuration": (
        "workflow_automation.configuration:import",
        "workflow_automation.api_writes",
    ),
    "configuration_export_configuration": (
        "workflow_automation.configuration:export",
        "workflow_automation.api_reads",
    ),
    "health": ("workflow_automation.health:read", "workflow_automation.api_reads"),
}


def access_metadata(action_key: str) -> tuple[str, str]:
    """Return permission/quota metadata or fail closed for an unknown action."""

    try:
        return ACTION_ACCESS[action_key]
    except KeyError as exc:
        raise KeyError(f"No access metadata is declared for {action_key!r}") from exc


__all__ = [
    "ACTION_ACCESS",
    "MODULE_ENTITLEMENT",
    "PERMISSIONS",
    "POLICY_PERMISSIONS",
    "SOD_ACTIONS",
    "access_metadata",
]
