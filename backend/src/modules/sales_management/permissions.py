"""Fail-closed action permissions for the sales API."""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

ENTITLEMENT: Final = "sales_management"

CUSTOMER_CREATE: Final = "sales.customer:create"
CUSTOMER_READ: Final = "sales.customer:read"
CUSTOMER_UPDATE: Final = "sales.customer:update"
CUSTOMER_DELETE: Final = "sales.customer:delete"
QUOTATION_CREATE: Final = "sales.quotation:create"
QUOTATION_READ: Final = "sales.quotation:read"
QUOTATION_UPDATE: Final = "sales.quotation:update"
QUOTATION_DELETE: Final = "sales.quotation:delete"
QUOTATION_SEND: Final = "sales.quotation:send"
QUOTATION_ACCEPT: Final = "sales.quotation:accept"
QUOTATION_REJECT: Final = "sales.quotation:reject"
QUOTATION_CONVERT: Final = "sales.quotation:convert"
ORDER_CREATE: Final = "sales.sales_order:create"
ORDER_READ: Final = "sales.sales_order:read"
ORDER_UPDATE: Final = "sales.sales_order:update"
ORDER_DELETE: Final = "sales.sales_order:delete"
ORDER_CONFIRM: Final = "sales.sales_order:confirm"
ORDER_FULFILL: Final = "sales.sales_order:fulfill"
ORDER_CANCEL: Final = "sales.sales_order:cancel"
ORDER_INVOICE: Final = "sales.sales_order:invoice"
DELIVERY_CREATE: Final = "sales.delivery_note:create"
DELIVERY_READ: Final = "sales.delivery_note:read"
DELIVERY_UPDATE: Final = "sales.delivery_note:update"
DELIVERY_DELETE: Final = "sales.delivery_note:delete"
DELIVERY_COMPLETE: Final = "sales.delivery_note:complete"
DELIVERY_CANCEL: Final = "sales.delivery_note:cancel"
PRICING_OVERRIDE: Final = "sales.pricing:override"
CONFIG_READ: Final = "sales.configuration:read"
CONFIG_UPDATE: Final = "sales.configuration:update"
CONFIG_ROLLBACK: Final = "sales.configuration:rollback"
CONFIG_IMPORT: Final = "sales.configuration:import"
CONFIG_EXPORT: Final = "sales.configuration:export"

PERMISSIONS: Final = tuple(
    value
    for name, value in globals().items()
    if name.isupper() and isinstance(value, str) and value.startswith("sales.")
)
SOD_ACTIONS: Final = (ORDER_CREATE, DELIVERY_CREATE)


class SalesSessionAuthentication(RelaxedCsrfSessionAuthentication):
    """Return a real authentication challenge for unauthenticated API calls."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


class SalesAccessMixin:
    """Attach explicit action metadata and deny undeclared actions."""

    authentication_classes = (SalesSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    required_entitlement = ENTITLEMENT
    action_permissions: dict[str, str] = {}

    def get_permissions(self) -> list[object]:
        raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(raw_tenant)) if raw_tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None
        # DRF's router can assign an action name (for example ``update`` for
        # PUT) even when this deliberately narrow ViewSet does not implement
        # that handler.  Authentication still applies, but authorization must
        # not turn a protocol-level 405 into a misleading 403.  Implemented
        # actions with missing metadata continue to fail closed below.
        action_name = str(getattr(self, "action", ""))
        if action_name and not callable(getattr(self, action_name, None)):
            self.required_permission = None
            self.quota_resource = None
            self.quota_cost = 0
            return [IsAuthenticated()]
        self.required_permission = self.action_permissions.get(action_name)
        self.quota_resource = "sales.api.requests" if self.required_permission else None
        self.quota_cost = 1
        return [IsAuthenticated(), RequiresAccess()]


__all__ = [
    "SalesAccessMixin",
    "SalesSessionAuthentication",
    "PERMISSIONS",
    "SOD_ACTIONS",
    *[name for name, value in globals().items() if name.isupper() and isinstance(value, str)],
]
