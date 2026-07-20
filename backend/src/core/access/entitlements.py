"""Tenant entitlement and atomic quota persistence.

SPDX-License-Identifier: Apache-2.0

These models are runtime projections of authoritative commercial state.  They
do not create subscriptions or infer access from module installation.  Missing
records always represent no access and a zero quota.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone


class Entitlement(models.Model):
    """A tenant's explicit grant to execute one capability."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    capability = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "access_entitlements"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "capability"],
                name="access_ent_tenant_cap_uniq",
            ),
            models.CheckConstraint(
                condition=Q(expires_at__isnull=True) | Q(starts_at__isnull=True) | Q(expires_at__gt=F("starts_at")),
                name="access_ent_valid_window_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "enabled"],
                name="access_ent_tenant_enabled_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.capability}"


class Quota(models.Model):
    """A tenant's remaining units for one metered resource.

    ``limit`` and ``remaining`` are deliberately non-null.  There is no
    sentinel for unlimited usage; a missing row or a zero limit denies usage.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(db_index=True)
    resource = models.CharField(max_length=255)
    limit = models.PositiveBigIntegerField(default=0)
    remaining = models.PositiveBigIntegerField(default=0)
    reset_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "access_quotas"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_id", "resource"],
                name="access_quota_tenant_res_uniq",
            ),
            models.CheckConstraint(
                condition=Q(remaining__lte=F("limit")),
                name="access_quota_remaining_lte_ck",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "resource", "reset_at"],
                name="access_quota_tenant_res_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.resource} ({self.remaining}/{self.limit})"


@dataclass(frozen=True)
class EntitlementResult:
    """Typed result of an explicit entitlement lookup."""

    entitled: bool


@dataclass(frozen=True)
class QuotaResult:
    """Typed result of an atomic quota consumption attempt."""

    allowed: bool
    limit: int
    remaining: int


class EntitlementService:
    """Read explicit tenant entitlement projections."""

    def check(
        self,
        tenant_id: uuid.UUID,
        capability: str,
        *,
        at: datetime | None = None,
    ) -> EntitlementResult:
        """Return whether an enabled entitlement is effective at ``at``.

        BR-ACCESS-001: An absent, disabled, not-yet-active, or expired grant
        denies execution.  Installed module state is intentionally irrelevant.
        """

        if not capability or not capability.strip():
            return EntitlementResult(entitled=False)

        effective_at = at or timezone.now()
        entitled = (
            Entitlement.objects.filter(
                tenant_id=tenant_id,
                capability=capability,
                enabled=True,
            )
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=effective_at))
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=effective_at))
            .exists()
        )
        return EntitlementResult(entitled=entitled)

    def is_entitled(self, tenant_id: uuid.UUID, capability: str) -> bool:
        """Compatibility convenience returning only the grant boolean."""

        return self.check(tenant_id, capability).entitled


class QuotaService:
    """Consume tenant quota using one conditional database update."""

    @transaction.atomic
    def consume(
        self,
        tenant_id: uuid.UUID,
        resource: str,
        *,
        cost: int = 1,
        at: datetime | None = None,
    ) -> QuotaResult:
        """Reserve ``cost`` units atomically and return the resulting balance.

        BR-ACCESS-002: Missing or expired quota state has limit zero and denies.
        BR-ACCESS-003: The conditional ``UPDATE`` prevents concurrent callers
        from decrementing below zero; no check-then-write race is possible.

        Raises:
            ValueError: If the resource is blank or cost is not positive.
        """

        if not resource or not resource.strip():
            raise ValueError("resource is required")
        if isinstance(cost, bool) or not isinstance(cost, int) or cost <= 0:
            raise ValueError("cost must be a positive integer")

        effective_at = at or timezone.now()
        active_quota = Quota.objects.filter(
            tenant_id=tenant_id,
            resource=resource,
        ).filter(Q(reset_at__isnull=True) | Q(reset_at__gt=effective_at))

        updated = active_quota.filter(
            limit__gte=cost,
            remaining__gte=cost,
        ).update(remaining=F("remaining") - cost, updated_at=effective_at)

        if updated != 1:
            state = active_quota.values("limit", "remaining").first()
            if state is None:
                return QuotaResult(allowed=False, limit=0, remaining=0)
            return QuotaResult(
                allowed=False,
                limit=int(state["limit"]),
                remaining=int(state["remaining"]),
            )

        state = active_quota.values("limit", "remaining").get()
        return QuotaResult(
            allowed=True,
            limit=int(state["limit"]),
            remaining=int(state["remaining"]),
        )

    def check_and_decrement(
        self,
        tenant_id: uuid.UUID,
        resource: str,
        *,
        amount: int = 1,
    ) -> QuotaResult:
        """Compatibility alias for callers using decrement terminology."""

        return self.consume(tenant_id, resource, cost=amount)


TenantEntitlement = Entitlement
TenantQuota = Quota

__all__ = [
    "Entitlement",
    "EntitlementResult",
    "EntitlementService",
    "Quota",
    "QuotaResult",
    "QuotaService",
    "TenantEntitlement",
    "TenantQuota",
]
