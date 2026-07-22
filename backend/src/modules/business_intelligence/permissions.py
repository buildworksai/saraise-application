"""Fail-closed, action-aware access controls for BI API endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from rest_framework.authentication import SessionAuthentication

from src.core.access import RequiresAccess

CORE_ENTITLEMENT = "business_intelligence.core"
EXECUTION_QUOTA = "business_intelligence.executions"


@dataclass(frozen=True)
class _NonConsumingQuotaResult:
    allowed: bool = True
    remaining: int = 0


class _NonConsumingQuota:
    """Pipeline adapter for operations that must never decrement a quota."""

    def consume(self, tenant_id: object, resource: str, *, cost: int = 1) -> _NonConsumingQuotaResult:
        del tenant_id, resource, cost
        return _NonConsumingQuotaResult()


class StrictSessionAuthentication(SessionAuthentication):
    """Normal CSRF-enforced sessions with an explicit 401 challenge."""

    def authenticate_header(self, request: object) -> str:
        return 'Session realm="api"'


class BIActionPermission(RequiresAccess):
    """Resolve permission metadata from the concrete action and deny omissions."""

    def has_permission(self, request: object, view: object) -> bool:
        mapping = getattr(view, "permission_map", {})
        action = getattr(view, "action", None) or getattr(view, "permission_action", None)
        required = mapping.get(action) if isinstance(mapping, dict) else None
        self.required_permission = required
        setattr(view, "required_permission", required)
        setattr(view, "required_entitlement", CORE_ENTITLEMENT)
        consumes_execution_quota = action in {"execute"}
        if consumes_execution_quota:
            setattr(view, "quota_resource", EXECUTION_QUOTA)
            return super().has_permission(request, view)

        # Core access currently always invokes a quota consumer.  Supply an
        # explicitly non-consuming adapter so reads and definition mutations
        # still receive policy + entitlement decisions without charging usage.
        original_quota_service = self.pipeline.quota_service
        self.pipeline.quota_service = _NonConsumingQuota()
        setattr(view, "quota_resource", required or "business_intelligence.non_consuming")
        try:
            return super().has_permission(request, view)
        finally:
            self.pipeline.quota_service = original_quota_service


__all__ = ["BIActionPermission", "CORE_ENTITLEMENT", "EXECUTION_QUOTA", "StrictSessionAuthentication"]
