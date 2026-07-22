"""Fail-closed access metadata for the inventory API.

Every HTTP action must be present in ``action_permissions``.  Missing metadata
is intentionally passed to :class:`RequiresAccess` as ``None`` and denied.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from rest_framework.permissions import IsAuthenticated

from src.core.access.permissions import RequiresAccess
from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

ENTITLEMENT: Final = "inventory_management"
API_QUOTA: Final = "inventory.api.requests"
POST_QUOTA: Final = "inventory.stock.post"
BULK_QUOTA: Final = "inventory.bulk.rows"


class InventorySessionAuthentication(RelaxedCsrfSessionAuthentication):
    """Retain production CSRF checks while distinguishing missing auth as 401."""

    def authenticate_header(self, request: object) -> str:
        del request
        return "Session"


def _permission(resource: str, operation: str) -> str:
    return f"inventory.{resource}:{operation}"


WAREHOUSE_CREATE = _permission("warehouse", "create")
WAREHOUSE_READ = _permission("warehouse", "read")
WAREHOUSE_UPDATE = _permission("warehouse", "update")
WAREHOUSE_DELETE = _permission("warehouse", "delete")
LOCATION_CREATE = _permission("location", "create")
LOCATION_READ = _permission("location", "read")
LOCATION_UPDATE = _permission("location", "update")
LOCATION_DELETE = _permission("location", "delete")
ITEM_CREATE = _permission("item", "create")
ITEM_READ = _permission("item", "read")
ITEM_UPDATE = _permission("item", "update")
ITEM_DELETE = _permission("item", "delete")
BATCH_CREATE = _permission("batch", "create")
BATCH_READ = _permission("batch", "read")
BATCH_UPDATE = _permission("batch", "update")
BATCH_TRANSITION = _permission("batch", "transition")
SERIAL_CREATE = _permission("serial", "create")
SERIAL_READ = _permission("serial", "read")
SERIAL_UPDATE = _permission("serial", "update")
STOCK_ENTRY_CREATE = _permission("stock_entry", "create")
STOCK_ENTRY_READ = _permission("stock_entry", "read")
STOCK_ENTRY_UPDATE = _permission("stock_entry", "update")
STOCK_ENTRY_DELETE = _permission("stock_entry", "delete")
STOCK_ENTRY_SUBMIT = _permission("stock_entry", "submit")
STOCK_ENTRY_APPROVE = _permission("stock_entry", "approve")
STOCK_ENTRY_REJECT = _permission("stock_entry", "reject")
STOCK_ENTRY_POST = _permission("stock_entry", "post")
STOCK_ENTRY_CANCEL = _permission("stock_entry", "cancel")
STOCK_ENTRY_REVERSE = _permission("stock_entry", "reverse")
STOCK_BALANCE_READ = _permission("stock_balance", "read")
STOCK_LEDGER_READ = _permission("stock_ledger", "read")
RESERVATION_CREATE = _permission("reservation", "create")
RESERVATION_READ = _permission("reservation", "read")
RESERVATION_UPDATE = _permission("reservation", "update")
RESERVATION_TRANSITION = _permission("reservation", "transition")
CYCLE_COUNT_CREATE = _permission("cycle_count", "create")
CYCLE_COUNT_READ = _permission("cycle_count", "read")
CYCLE_COUNT_UPDATE = _permission("cycle_count", "update")
CYCLE_COUNT_START = _permission("cycle_count", "start")
CYCLE_COUNT_SUBMIT = _permission("cycle_count", "submit")
CYCLE_COUNT_APPROVE = _permission("cycle_count", "approve")
CYCLE_COUNT_REJECT = _permission("cycle_count", "reject")
CYCLE_COUNT_POST = _permission("cycle_count", "post")
CYCLE_COUNT_CANCEL = _permission("cycle_count", "cancel")
CONFIGURATION_READ = _permission("configuration", "read")
CONFIGURATION_UPDATE = _permission("configuration", "update")
CONFIGURATION_PREVIEW = _permission("configuration", "preview")
CONFIGURATION_ACTIVATE = _permission("configuration", "activate")
CONFIGURATION_ROLLBACK = _permission("configuration", "rollback")
CONFIGURATION_IMPORT = _permission("configuration", "import")
CONFIGURATION_EXPORT = _permission("configuration", "export")
CONFIGURATION_AUDIT = _permission("configuration", "audit")
REPORT_READ = _permission("report", "read")
BULK_IMPORT = _permission("bulk", "import")
HEALTH_READ = _permission("health", "read")

PERMISSIONS: Final = (
    WAREHOUSE_CREATE, WAREHOUSE_READ, WAREHOUSE_UPDATE, WAREHOUSE_DELETE,
    LOCATION_CREATE, LOCATION_READ, LOCATION_UPDATE, LOCATION_DELETE,
    ITEM_CREATE, ITEM_READ, ITEM_UPDATE, ITEM_DELETE,
    BATCH_CREATE, BATCH_READ, BATCH_UPDATE, BATCH_TRANSITION,
    SERIAL_CREATE, SERIAL_READ, SERIAL_UPDATE,
    STOCK_ENTRY_CREATE, STOCK_ENTRY_READ, STOCK_ENTRY_UPDATE, STOCK_ENTRY_DELETE,
    STOCK_ENTRY_SUBMIT, STOCK_ENTRY_APPROVE, STOCK_ENTRY_REJECT, STOCK_ENTRY_POST,
    STOCK_ENTRY_CANCEL, STOCK_ENTRY_REVERSE, STOCK_BALANCE_READ, STOCK_LEDGER_READ,
    RESERVATION_CREATE, RESERVATION_READ, RESERVATION_UPDATE, RESERVATION_TRANSITION,
    CYCLE_COUNT_CREATE, CYCLE_COUNT_READ, CYCLE_COUNT_UPDATE, CYCLE_COUNT_START,
    CYCLE_COUNT_SUBMIT, CYCLE_COUNT_APPROVE, CYCLE_COUNT_REJECT, CYCLE_COUNT_POST,
    CYCLE_COUNT_CANCEL, CONFIGURATION_READ, CONFIGURATION_UPDATE,
    CONFIGURATION_PREVIEW, CONFIGURATION_ACTIVATE, CONFIGURATION_ROLLBACK,
    CONFIGURATION_IMPORT, CONFIGURATION_EXPORT, CONFIGURATION_AUDIT, REPORT_READ,
    BULK_IMPORT, HEALTH_READ,
)

SOD_ACTIONS: Final = (STOCK_ENTRY_CREATE, STOCK_ENTRY_APPROVE)


class InventoryAccessMixin:
    """Resolve one explicit permission and quota for every inventory action."""

    authentication_classes = (InventorySessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    action_permissions: dict[str, str] = {}
    action_quotas: dict[str, str] = {}
    required_entitlement = ENTITLEMENT

    def get_permissions(self) -> list[object]:
        raw_tenant = get_user_tenant_id(getattr(self.request, "user", None))
        try:
            self.request.tenant_id = UUID(str(raw_tenant)) if raw_tenant else None
        except (TypeError, ValueError, AttributeError):
            self.request.tenant_id = None

        action = str(getattr(self, "action", ""))
        self.required_permission = self.action_permissions.get(action)
        self.quota_resource = self.action_quotas.get(action, API_QUOTA) if self.required_permission else None
        self.quota_cost = self.get_quota_cost(action)
        return [IsAuthenticated(), RequiresAccess()]

    def get_quota_cost(self, action: str) -> int:
        """Return a positive quota cost; bulk views override after typed validation."""

        del action
        return 1


# Compatibility name retained for imports while enforcing the governed policy.
IsInventoryUser = RequiresAccess


__all__ = [
    "InventoryAccessMixin",
    "InventorySessionAuthentication",
    "IsInventoryUser",
    "PERMISSIONS",
    "SOD_ACTIONS",
    *[name for name, value in globals().items() if name.isupper() and isinstance(value, str)],
]
