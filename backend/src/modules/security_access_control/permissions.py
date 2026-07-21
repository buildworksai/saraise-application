"""Fail-closed API permission adapter for non-metered security administration."""

from __future__ import annotations

from uuid import UUID

from src.core.access import AccessDecision, AccessReasonCode, RequiresAccess

from .models import Permission
from .services import AccessEvaluationService


def _identity_tenant(identity: object) -> UUID | None:
    raw = getattr(identity, "tenant_id", None)
    if raw is None:
        raw = getattr(getattr(identity, "profile", None), "tenant_id", None)
    try:
        return raw if isinstance(raw, UUID) else UUID(str(raw))
    except (TypeError, ValueError, AttributeError):
        return None


class SecurityAdministrationPipeline:
    """Run policy evaluation without commercial entitlement or quota mutation.

    Security administration is an OSS foundation capability. The pipeline still
    validates authentication and tenant match, then delegates to the real
    local/remote evaluator selected by application mode.
    """

    def decide(
        self,
        tenant_id: UUID | str | None,
        identity: object,
        required_permission: str | None,
        **kwargs: object,
    ) -> AccessDecision:
        request = kwargs.get("request")
        if not bool(getattr(identity, "is_authenticated", False)):
            return AccessDecision.deny(AccessReasonCode.AUTHENTICATION_REQUIRED, "Authentication is required.")
        try:
            tenant = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        except (TypeError, ValueError, AttributeError):
            return AccessDecision.deny(AccessReasonCode.DENY_TENANT_MISMATCH, "Tenant context is invalid.")
        if _identity_tenant(identity) != tenant:
            return AccessDecision.deny(
                AccessReasonCode.DENY_TENANT_MISMATCH,
                "The authenticated identity does not belong to this tenant.",
                tenant_id=tenant,
            )
        if not required_permission:
            return AccessDecision.deny(
                AccessReasonCode.DENY_DEFAULT, "Required permission is absent.", tenant_id=tenant
            )
        evaluation = AccessEvaluationService.evaluate(tenant, identity, required_permission, request=request)
        if not evaluation.allowed:
            return AccessDecision(
                allowed=False,
                reason_code=AccessReasonCode.POLICY_DENIED,
                reason="The authoritative security policy denied this operation.",
                tenant_id=tenant,
                applied_policies=evaluation.applied_policies,
            )
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="The authoritative security policy allowed this operation.",
            tenant_id=tenant,
            applied_policies=evaluation.applied_policies,
        )


class PermissionCatalogAccess(RequiresAccess):
    """Permit object checks only for global immutable catalog entries."""

    def has_object_permission(self, request: object, view: object, obj: object) -> bool:
        decision = getattr(request, "access_decision", None)
        return isinstance(obj, Permission) and isinstance(decision, AccessDecision) and decision.allowed


def requires_access(code: str, *, catalog: bool = False) -> RequiresAccess:
    permission_type = PermissionCatalogAccess if catalog else RequiresAccess
    return permission_type(code, pipeline=SecurityAdministrationPipeline())


__all__ = ["PermissionCatalogAccess", "SecurityAdministrationPipeline", "requires_access"]
