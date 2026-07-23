"""Fail-closed purchase-management access declarations."""

from src.core.access import RequiresAccess
from src.core.auth_utils import get_user_tenant_id


class PurchaseRequiresAccess(RequiresAccess):
    """Populate the canonical request tenant before the access pipeline runs."""

    def has_permission(self, request, view):
        if not getattr(request, "tenant_id", None):
            request.tenant_id = get_user_tenant_id(getattr(request, "user", None))
        return super().has_permission(request, view)


ACTION_ACCESS = {
    "list": "read",
    "retrieve": "read",
    "create": "create",
    "update": "update",
    "partial_update": "update",
    "destroy": "delete",
    "submit": "submit",
    "approve": "approve",
    "reject": "reject",
    "revise": "update",
    "cancel": "cancel",
    "activate": "archive",
    "deactivate": "archive",
    "convert_to_order": "convert",
    "publish": "publish",
    "close": "close",
    "compare_quotes": "compare",
    "award": "award",
    "withdraw": "submit",
    "dispatch": "dispatch",
    "acknowledge": "acknowledge",
    "complete": "complete",
    "preview": "preview",
    "active": "read",
    "versions": "read",
    "activate_version": "activate",
    "rollback": "rollback",
    "export_configuration": "export",
    "import_configuration": "import",
}
