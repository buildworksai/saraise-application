"""Entitlement Service.

Implements subscription entitlements and runtime gating.
Task: 503.1 - Subscription Entitlements & Runtime Gating
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .entitlement_models import (
    SubscriptionPlan,
    PlanEntitlement,
    TenantSubscription,
    EntitlementCheck,
)
from .module_registry_models import TenantModuleInstallation

logger = logging.getLogger(__name__)


class EntitlementError(Exception):
    """Entitlement error."""

    pass


class EntitlementService:
    """Entitlement service.

    Manages subscription entitlements and runtime gating.
    """

    def __init__(self) -> None:
        """Initialize entitlement service."""
        pass

    def get_tenant_subscription(self, tenant_id: str) -> Optional[TenantSubscription]:
        """Get tenant subscription.

        Args:
            tenant_id: Tenant ID.

        Returns:
            TenantSubscription instance or None if not found.
        """
        return TenantSubscription.objects.filter(
            tenant_id=tenant_id, status="active"
        ).first()

    def check_module_access(
        self, tenant_id: str, module_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if tenant has access to a module.

        Args:
            tenant_id: Tenant ID.
            module_name: Module name.

        Returns:
            Tuple of (has_access, reason).
        """
        # Get tenant subscription
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            self._log_check(tenant_id, "module_access", module_name, False, "No active subscription")
            return False, "No active subscription"

        # Check if subscription is expired
        if subscription.expires_at and subscription.expires_at < timezone.now():
            self._log_check(tenant_id, "module_access", module_name, False, "Subscription expired")
            return False, "Subscription expired"

        # Check plan entitlements
        entitlement = PlanEntitlement.objects.filter(
            plan=subscription.plan,
            entitlement_type="module_access",
            resource_name=module_name,
        ).first()

        if not entitlement:
            # Check if module is installed (legacy/backward compatibility)
            installed = TenantModuleInstallation.objects.filter(
                tenant_id=tenant_id, module_name=module_name, status="installed"
            ).first()
            if installed:
                self._log_check(tenant_id, "module_access", module_name, True, "Module installed")
                return True, None
            else:
                self._log_check(tenant_id, "module_access", module_name, False, "Module not in plan")
                return False, "Module not included in subscription plan"

        # Module access granted
        self._log_check(tenant_id, "module_access", module_name, True, "Entitlement granted")
        return True, None

    def check_feature_access(
        self, tenant_id: str, feature_name: str
    ) -> Tuple[bool, Optional[str]]:
        """Check if tenant has access to a feature.

        Args:
            tenant_id: Tenant ID.
            feature_name: Feature name.

        Returns:
            Tuple of (has_access, reason).
        """
        # Get tenant subscription
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            self._log_check(tenant_id, "feature_access", feature_name, False, "No active subscription")
            return False, "No active subscription"

        # Check plan entitlements
        entitlement = PlanEntitlement.objects.filter(
            plan=subscription.plan,
            entitlement_type="feature_access",
            resource_name=feature_name,
        ).first()

        if not entitlement:
            self._log_check(tenant_id, "feature_access", feature_name, False, "Feature not in plan")
            return False, "Feature not included in subscription plan"

        # Feature access granted
        self._log_check(tenant_id, "feature_access", feature_name, True, "Entitlement granted")
        return True, None

    def check_resource_limit(
        self, tenant_id: str, resource_type: str, current_usage: int
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if tenant is within resource limits.

        Args:
            tenant_id: Tenant ID.
            resource_type: Resource type (storage_limit, user_limit, etc.).
            current_usage: Current usage.

        Returns:
            Tuple of (within_limit, reason, limit_value).
        """
        # Get tenant subscription
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            self._log_check(tenant_id, "resource_limit", resource_type, False, "No active subscription")
            return False, "No active subscription", None

        # Check plan entitlements
        entitlement = PlanEntitlement.objects.filter(
            plan=subscription.plan,
            entitlement_type="resource_limit",
            resource_name=resource_type,
        ).first()

        if not entitlement:
            # No limit defined = unlimited
            self._log_check(tenant_id, "resource_limit", resource_type, True, "Unlimited")
            return True, None, None

        limit_value = entitlement.limit_value
        if limit_value is None:
            # Unlimited
            self._log_check(tenant_id, "resource_limit", resource_type, True, "Unlimited")
            return True, None, None

        if current_usage >= limit_value:
            self._log_check(
                tenant_id,
                "resource_limit",
                resource_type,
                False,
                f"Limit exceeded: {current_usage}/{limit_value}",
            )
            return False, f"Resource limit exceeded: {current_usage}/{limit_value}", limit_value

        # Within limit
        self._log_check(
            tenant_id,
            "resource_limit",
            resource_type,
            True,
            f"Within limit: {current_usage}/{limit_value}",
        )
        return True, None, limit_value

    def check_api_rate_limit(
        self, tenant_id: str, current_rate: float
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """Check if tenant is within API rate limits.

        Args:
            tenant_id: Tenant ID.
            current_rate: Current request rate (requests per second).

        Returns:
            Tuple of (within_limit, reason, limit_value).
        """
        # Get tenant subscription
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            self._log_check(tenant_id, "api_rate_limit", "api", False, "No active subscription")
            return False, "No active subscription", None

        # Check plan entitlements
        entitlement = PlanEntitlement.objects.filter(
            plan=subscription.plan,
            entitlement_type="api_rate_limit",
            resource_name="api",
        ).first()

        if not entitlement:
            # No limit defined = unlimited
            self._log_check(tenant_id, "api_rate_limit", "api", True, "Unlimited")
            return True, None, None

        limit_value = entitlement.limit_value
        if limit_value is None:
            # Unlimited
            self._log_check(tenant_id, "api_rate_limit", "api", True, "Unlimited")
            return True, None, None

        if current_rate >= limit_value:
            self._log_check(
                tenant_id,
                "api_rate_limit",
                "api",
                False,
                f"Rate limit exceeded: {current_rate}/{limit_value}",
            )
            return False, f"API rate limit exceeded: {current_rate}/{limit_value}", limit_value

        # Within limit
        self._log_check(
            tenant_id,
            "api_rate_limit",
            "api",
            True,
            f"Within limit: {current_rate}/{limit_value}",
        )
        return True, None, limit_value

    @transaction.atomic
    def create_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        expires_at: Optional[datetime] = None,
    ) -> TenantSubscription:
        """Create a tenant subscription.

        Args:
            tenant_id: Tenant ID.
            plan_id: Plan ID.
            expires_at: Optional expiration date.

        Returns:
            Created TenantSubscription instance.

        Raises:
            EntitlementError: If subscription creation fails.
        """
        # Check if subscription already exists
        existing = TenantSubscription.objects.filter(tenant_id=tenant_id).first()
        if existing:
            raise EntitlementError(f"Tenant {tenant_id} already has a subscription")

        # Get plan
        plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
        if not plan:
            raise EntitlementError(f"Plan {plan_id} not found or inactive")

        # Create subscription
        subscription = TenantSubscription.objects.create(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            expires_at=expires_at,
        )

        logger.info(f"Created subscription for tenant {tenant_id} - Plan: {plan.name}")

        return subscription

    @transaction.atomic
    def update_subscription(
        self,
        tenant_id: str,
        plan_id: str,
        expires_at: Optional[datetime] = None,
    ) -> TenantSubscription:
        """Update tenant subscription.

        Args:
            tenant_id: Tenant ID.
            plan_id: New plan ID.
            expires_at: Optional expiration date.

        Returns:
            Updated TenantSubscription instance.

        Raises:
            EntitlementError: If subscription update fails.
        """
        subscription = TenantSubscription.objects.filter(tenant_id=tenant_id).first()
        if not subscription:
            raise EntitlementError(f"Tenant {tenant_id} has no subscription")

        # Get plan
        plan = SubscriptionPlan.objects.filter(id=plan_id, is_active=True).first()
        if not plan:
            raise EntitlementError(f"Plan {plan_id} not found or inactive")

        # Update subscription
        subscription.plan = plan
        if expires_at:
            subscription.expires_at = expires_at
        subscription.save()

        logger.info(f"Updated subscription for tenant {tenant_id} - Plan: {plan.name}")

        return subscription

    def get_tenant_entitlements(self, tenant_id: str) -> Dict[str, Any]:
        """Get all entitlements for a tenant.

        Args:
            tenant_id: Tenant ID.

        Returns:
            Dictionary of entitlements.
        """
        subscription = self.get_tenant_subscription(tenant_id)
        if not subscription:
            return {}

        entitlements = PlanEntitlement.objects.filter(plan=subscription.plan)

        result: Dict[str, Any] = {
            "plan": subscription.plan.name,
            "plan_type": subscription.plan.plan_type,
            "status": subscription.status,
            "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
            "entitlements": {},
        }

        for entitlement in entitlements:
            key = f"{entitlement.entitlement_type}:{entitlement.resource_name}"
            result["entitlements"][key] = {
                "limit_value": entitlement.limit_value,
                "limit_unit": entitlement.limit_unit,
                "metadata": entitlement.metadata,
            }

        return result

    def _log_check(
        self,
        tenant_id: str,
        entitlement_type: str,
        resource_name: str,
        allowed: bool,
        reason: Optional[str] = None,
    ) -> None:
        """Log entitlement check.

        Args:
            tenant_id: Tenant ID.
            entitlement_type: Entitlement type.
            resource_name: Resource name.
            allowed: Whether access was allowed.
            reason: Optional reason.
        """
        EntitlementCheck.objects.create(
            tenant_id=tenant_id,
            entitlement_type=entitlement_type,
            resource_name=resource_name,
            allowed=allowed,
            reason=reason,
            metadata={},
        )


# Global entitlement service instance
entitlement_service = EntitlementService()

