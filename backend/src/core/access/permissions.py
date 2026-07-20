"""DRF integration for the unified access decision pipeline.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from .decision import AccessDecision, AccessDecisionPipeline, AccessReasonCode


class RequiresAccess(BasePermission):
    """Require a fail-closed access decision for a DRF route.

    Supported declaration styles::

        permission_classes = [RequiresAccess("finance.ledger:post")]

    or::

        permission_classes = [RequiresAccess]
        required_permission = "finance.ledger:post"

    Instances are callable so DRF can instantiate entries in
    ``permission_classes`` even when the first declaration style is used.
    """

    message = "Access denied."
    code = "permission_denied"

    def __init__(
        self,
        required_permission: str | None = None,
        *,
        pipeline: AccessDecisionPipeline | None = None,
    ) -> None:
        self.required_permission = required_permission
        self.pipeline = pipeline or AccessDecisionPipeline()

    def __call__(self) -> RequiresAccess:
        """Return this configured permission when DRF instantiates it."""

        return self

    def has_permission(self, request: Request, view: object) -> bool:
        """Delegate the route decision and retain it on the request."""

        required_permission = self.required_permission or getattr(view, "required_permission", None)
        if not required_permission or not isinstance(required_permission, str):
            decision = AccessDecision.deny(
                AccessReasonCode.DENY_DEFAULT,
                "Access metadata does not declare a required permission.",
            )
            setattr(request, "access_decision", decision)
            return False

        entitlement = getattr(view, "required_entitlement", required_permission)
        quota = getattr(view, "quota_resource", required_permission)
        quota_cost = getattr(view, "quota_cost", 1)
        tenant_id = getattr(request, "tenant_id", None)

        decision = self.pipeline.decide(
            tenant_id,
            getattr(request, "user", None),
            required_permission,
            entitlement=entitlement,
            quota=quota,
            quota_cost=quota_cost,
            request=request,
        )
        setattr(request, "access_decision", decision)
        return decision.allowed

    def has_object_permission(self, request: Request, view: object, obj: object) -> bool:
        """Enforce the request tenant boundary without consuming quota twice."""

        decision = getattr(request, "access_decision", None)
        if not isinstance(decision, AccessDecision) or not decision.allowed or decision.tenant_id is None:
            return False
        object_tenant = getattr(obj, "tenant_id", None)
        if object_tenant is None:
            return False
        return str(object_tenant) == str(decision.tenant_id)


__all__ = ["RequiresAccess"]
