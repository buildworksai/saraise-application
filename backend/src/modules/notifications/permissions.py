"""Fail-closed, action-specific authorization for notification APIs."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id

PERMISSIONS: Final[tuple[str, ...]] = (
    "notifications.inbox:read",
    "notifications.inbox:update",
    "notifications.template:read",
    "notifications.template:create",
    "notifications.template:update",
    "notifications.template:activate",
    "notifications.template:archive",
    "notifications.delivery:read",
    "notifications.delivery:dispatch",
    "notifications.delivery:dispatch_bulk",
    "notifications.delivery:dispatch_urgent",
    "notifications.delivery:retry",
    "notifications.delivery:cancel",
    "notifications.preference:read",
    "notifications.preference:update",
    "notifications.endpoint:read",
    "notifications.endpoint:create",
    "notifications.endpoint:verify",
    "notifications.endpoint:update",
    "notifications.endpoint:delete",
    "notifications.configuration:read",
    "notifications.configuration:update",
    "notifications.configuration:import",
    "notifications.configuration:export",
    "notifications.configuration:rollback",
    "notifications.health:read",
)

READ_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "list",
        "retrieve",
        "unread_count",
        "versions",
        "attempts",
        "history",
        "export_document",
        "live",
        "ready",
    }
)

INBOX_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "notifications.inbox:read",
    "retrieve": "notifications.inbox:read",
    "unread_count": "notifications.inbox:read",
    "mark_read": "notifications.inbox:update",
    "mark_unread": "notifications.inbox:update",
    "archive": "notifications.inbox:update",
    "mark_all_read": "notifications.inbox:update",
}
TEMPLATE_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "notifications.template:read",
    "retrieve": "notifications.template:read",
    "create": "notifications.template:create",
    "partial_update": "notifications.template:update",
    "destroy": "notifications.template:archive",
    "versions": "notifications.template:read",
    "create_version": "notifications.template:update",
    "preview": "notifications.template:read",
    "activate": "notifications.template:activate",
    "restore": "notifications.template:update",
    "rollback": "notifications.template:activate",
}
DELIVERY_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "notifications.delivery:read",
    "retrieve": "notifications.delivery:read",
    "attempts": "notifications.delivery:read",
    "create": "notifications.delivery:dispatch",
    "preview": "notifications.delivery:dispatch",
    "bulk": "notifications.delivery:dispatch_bulk",
    "urgent": "notifications.delivery:dispatch_urgent",
    "retry": "notifications.delivery:retry",
    "cancel": "notifications.delivery:cancel",
}
PREFERENCE_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "retrieve": "notifications.preference:read",
    "list": "notifications.preference:read",
    "update": "notifications.preference:update",
    "reset": "notifications.preference:update",
}
ENDPOINT_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "list": "notifications.endpoint:read",
    "retrieve": "notifications.endpoint:read",
    "create": "notifications.endpoint:create",
    "partial_update": "notifications.endpoint:update",
    "destroy": "notifications.endpoint:delete",
    "verify": "notifications.endpoint:verify",
    "rotate_secret_ref": "notifications.endpoint:update",
}
CONFIGURATION_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "retrieve": "notifications.configuration:read",
    "partial_update": "notifications.configuration:update",
    "simulate": "notifications.configuration:update",
    "history": "notifications.configuration:read",
    "rollback": "notifications.configuration:rollback",
    "import_document": "notifications.configuration:import",
    "export_document": "notifications.configuration:export",
}
HEALTH_ACTION_PERMISSIONS: Final[dict[str, str]] = {
    "ready": "notifications.health:read",
}


class StrictSessionAuthentication(SessionAuthentication):
    """Preserve CSRF checks and return an explicit session challenge."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class NotificationActionAccessMixin:
    """Bind each DRF action to policy, entitlement, and atomic quota.

    Missing mappings remain ``None`` and are rejected by ``RequiresAccess``.
    Controllers can override ``action_permissions`` but cannot inherit an
    allow-by-default fallback.
    """

    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_entitlements: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    action_quota_costs: dict[str, int] = {}

    def get_permissions(self) -> list[object]:
        action = str(getattr(self, "action", ""))
        tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(tenant)) if tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None

        permission = self.action_permissions.get(action)
        self.required_permission = permission
        self.required_entitlement = self.action_entitlements.get(action, permission)
        self.quota_resource = self.action_quotas.get(
            action,
            "notifications.api_reads" if action in READ_ACTIONS else "notifications.api_writes",
        )
        self.quota_cost = self.action_quota_costs.get(action, 1)
        return [IsAuthenticated(), RequiresAccess()]


class InboxAccessMixin(NotificationActionAccessMixin):
    action_permissions = INBOX_ACTION_PERMISSIONS


class TemplateAccessMixin(NotificationActionAccessMixin):
    action_permissions = TEMPLATE_ACTION_PERMISSIONS


class DeliveryAccessMixin(NotificationActionAccessMixin):
    action_permissions = DELIVERY_ACTION_PERMISSIONS
    action_entitlements = {
        "create": "notifications.delivery",
        "preview": "notifications.delivery",
        "bulk": "notifications.delivery",
        "urgent": "notifications.delivery",
        "retry": "notifications.delivery",
        "cancel": "notifications.delivery",
    }
    action_quotas = {
        "bulk": "notifications.delivery.dispatch_bulk",
        "urgent": "notifications.delivery.dispatch_urgent",
    }


class PreferenceAccessMixin(NotificationActionAccessMixin):
    action_permissions = PREFERENCE_ACTION_PERMISSIONS


class EndpointAccessMixin(NotificationActionAccessMixin):
    action_permissions = ENDPOINT_ACTION_PERMISSIONS


class ConfigurationAccessMixin(NotificationActionAccessMixin):
    action_permissions = CONFIGURATION_ACTION_PERMISSIONS


# Concise compatibility name for controllers that declare their own mapping.
ActionAccessMixin = NotificationActionAccessMixin


__all__ = [
    "ActionAccessMixin",
    "CONFIGURATION_ACTION_PERMISSIONS",
    "ConfigurationAccessMixin",
    "DELIVERY_ACTION_PERMISSIONS",
    "DeliveryAccessMixin",
    "ENDPOINT_ACTION_PERMISSIONS",
    "EndpointAccessMixin",
    "HEALTH_ACTION_PERMISSIONS",
    "INBOX_ACTION_PERMISSIONS",
    "InboxAccessMixin",
    "NotificationActionAccessMixin",
    "PERMISSIONS",
    "PREFERENCE_ACTION_PERMISSIONS",
    "PreferenceAccessMixin",
    "READ_ACTIONS",
    "StrictSessionAuthentication",
    "TEMPLATE_ACTION_PERMISSIONS",
    "TemplateAccessMixin",
]
