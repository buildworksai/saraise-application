"""AI Quota Enforcement Service.

Implements tenant-level quotas, shard-level saturation controls, and kill switches.
Task: 402.2 - AI Quota Enforcement
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta

from django.utils import timezone
from django.db import transaction

from .models import AgentExecution
from .quota_models import (
    TenantQuota,
    QuotaUsage,
    ShardSaturation,
    KillSwitch,
    QuotaType,
    QuotaPeriod,
)

logger = logging.getLogger(__name__)


class QuotaService:
    """Service for managing AI quotas and saturation controls."""

    def __init__(self) -> None:
        """Initialize quota service."""
        self._saturation_threshold = 0.8  # 80% saturation threshold

    def check_quota(
        self,
        tenant_id: str,
        quota_type: str,
        requested_amount: int,
        period: Optional[str] = None,
    ) -> Tuple[bool, Optional[TenantQuota], str]:
        """Check if quota allows requested amount.

        Args:
            tenant_id: Tenant ID.
            quota_type: Type of quota.
            requested_amount: Amount requested.
            period: Optional period (defaults to daily).

        Returns:
            Tuple of (allowed, quota, message).
        """
        # Default to daily period
        if not period:
            period = QuotaPeriod.DAILY

        # Get quota
        quota = TenantQuota.objects.filter(
            tenant_id=tenant_id,
            quota_type=quota_type,
            period=period,
            is_active=True,
        ).first()

        if not quota:
            # No quota defined - allow by default
            logger.debug(
                f"No quota defined for {quota_type} ({period}) - allowing"
            )
            return True, None, "No quota defined"

        # Check if quota has reset
        if timezone.now() >= quota.reset_at:
            self._reset_quota(quota)

        # Check if quota allows requested amount
        if quota.current_usage + requested_amount > quota.limit_value:
            logger.warning(
                f"Quota exceeded: {quota_type} ({period}) - "
                f"{quota.current_usage + requested_amount}/{quota.limit_value}"
            )
            return (
                False,
                quota,
                f"Quota exceeded: {quota.current_usage + requested_amount}/{quota.limit_value}",
            )

        return True, quota, "Quota available"

    def consume_quota(
        self,
        tenant_id: str,
        quota_type: str,
        amount: int,
        agent_execution: Optional[AgentExecution] = None,
        period: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TenantQuota:
        """Consume quota amount.

        Args:
            tenant_id: Tenant ID.
            quota_type: Type of quota.
            amount: Amount to consume.
            agent_execution: Optional agent execution instance.
            period: Optional period (defaults to daily).

        Returns:
            Updated TenantQuota instance.

        Raises:
            ValueError: If quota not found or insufficient.
        """
        # Default to daily period
        if not period:
            period = QuotaPeriod.DAILY

        # Check quota
        allowed, quota, message = self.check_quota(
            tenant_id, quota_type, amount, period
        )

        if not allowed:
            raise ValueError(f"Quota check failed: {message}")

        # If no quota exists, create default unlimited quota
        if not quota:
            quota = self._create_default_quota(
                tenant_id, quota_type, period
            )

        # Consume quota
        with transaction.atomic():
            quota.current_usage += amount
            quota.save(update_fields=["current_usage", "updated_at"])

            # Record usage
            QuotaUsage.objects.create(
                tenant_id=tenant_id,
                quota=quota,
                agent_execution=agent_execution,
                usage_value=amount,
                metadata=metadata or {},
            )

        logger.info(
            f"Consumed {amount} {quota_type} quota for tenant {tenant_id} "
            f"({quota.current_usage}/{quota.limit_value})"
        )

        return quota

    def check_kill_switch(
        self,
        tenant_id: str,
        shard_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[KillSwitch]]:
        """Check if kill switch is active.

        Args:
            tenant_id: Tenant ID.
            shard_id: Optional shard ID.
            agent_id: Optional agent ID.

        Returns:
            Tuple of (blocked, kill_switch).
        """
        # Check global kill switches
        global_switches = KillSwitch.objects.filter(
            scope="global", is_active=True
        )

        if global_switches.exists():
            switch = global_switches.first()
            logger.warning(f"Global kill switch active: {switch.name}")
            return True, switch

        # Check tenant kill switches
        tenant_switches = KillSwitch.objects.filter(
            tenant_id=tenant_id, scope="tenant", is_active=True
        )

        if tenant_switches.exists():
            switch = tenant_switches.first()
            logger.warning(
                f"Tenant kill switch active for {tenant_id}: {switch.name}"
            )
            return True, switch

        # Check shard kill switches
        if shard_id:
            shard_switches = KillSwitch.objects.filter(
                scope="shard",
                scope_id=shard_id,
                is_active=True,
            )

            if shard_switches.exists():
                switch = shard_switches.first()
                logger.warning(
                    f"Shard kill switch active for {shard_id}: {switch.name}"
                )
                return True, switch

        # Check agent kill switches
        if agent_id:
            agent_switches = KillSwitch.objects.filter(
                scope="agent",
                scope_id=agent_id,
                is_active=True,
            )

            if agent_switches.exists():
                switch = agent_switches.first()
                logger.warning(
                    f"Agent kill switch active for {agent_id}: {switch.name}"
                )
                return True, switch

        return False, None

    def activate_kill_switch(
        self,
        name: str,
        scope: str,
        tenant_id: str,
        scope_id: Optional[str] = None,
        reason: str = "",
        activated_by: str = "",
    ) -> KillSwitch:
        """Activate a kill switch.

        Args:
            name: Kill switch name.
            scope: Kill switch scope (global, tenant, shard, agent).
            tenant_id: Tenant ID (for tenant-scoped switches).
            scope_id: Scope identifier (for shard/agent scopes).
            reason: Reason for activation.
            activated_by: User who activated.

        Returns:
            Created KillSwitch instance.
        """
        # For global scope, tenant_id can be None
        if scope != "global":
            if not tenant_id:
                raise ValueError(f"tenant_id required for scope {scope}")

        kill_switch = KillSwitch.objects.create(
            tenant_id=tenant_id if scope != "global" else None,
            name=name,
            scope=scope,
            scope_id=scope_id,
            is_active=True,
            reason=reason,
            activated_by=activated_by,
        )

        logger.warning(
            f"Kill switch activated: {name} (scope={scope}, "
            f"scope_id={scope_id})"
        )

        return kill_switch

    def deactivate_kill_switch(
        self, kill_switch_id: str, tenant_id: Optional[str] = None
    ) -> KillSwitch:
        """Deactivate a kill switch.

        Args:
            kill_switch_id: Kill switch ID.
            tenant_id: Optional tenant ID (for tenant-scoped switches).

        Returns:
            Updated KillSwitch instance.

        Raises:
            ValueError: If kill switch not found.
        """
        query = KillSwitch.objects.filter(id=kill_switch_id)

        if tenant_id:
            query = query.filter(tenant_id=tenant_id)

        kill_switch = query.first()

        if not kill_switch:
            raise ValueError(f"Kill switch {kill_switch_id} not found")

        kill_switch.is_active = False
        kill_switch.deactivated_at = timezone.now()
        kill_switch.save(
            update_fields=["is_active", "deactivated_at", "updated_at"]
        )

        logger.info(f"Kill switch deactivated: {kill_switch.name}")

        return kill_switch

    def check_shard_saturation(
        self, shard_id: str, tenant_id: str
    ) -> Tuple[bool, Optional[ShardSaturation]]:
        """Check shard saturation level.

        Args:
            shard_id: Shard ID.
            tenant_id: Tenant ID.

        Returns:
            Tuple of (saturated, saturation_record).
        """
        # Get latest saturation measurement
        saturation = ShardSaturation.objects.filter(
            tenant_id=tenant_id, shard_id=shard_id
        ).order_by("-measured_at").first()

        if not saturation:
            return False, None

        # Check if saturation exceeds threshold
        if saturation.saturation_level >= self._saturation_threshold:
            logger.warning(
                f"Shard {shard_id} saturated: {saturation.saturation_level:.2%}"
            )
            return True, saturation

        return False, saturation

    def record_saturation(
        self,
        shard_id: str,
        tenant_id: str,
        saturation_level: float,
        active_agents: int = 0,
        active_executions: int = 0,
        cpu_usage_percent: Optional[float] = None,
        memory_usage_percent: Optional[float] = None,
    ) -> ShardSaturation:
        """Record shard saturation measurement.

        Args:
            shard_id: Shard ID.
            tenant_id: Tenant ID.
            saturation_level: Saturation level (0.0 to 1.0).
            active_agents: Number of active agents.
            active_executions: Number of active executions.
            cpu_usage_percent: Optional CPU usage percentage.
            memory_usage_percent: Optional memory usage percentage.

        Returns:
            Created ShardSaturation instance.
        """
        saturation = ShardSaturation.objects.create(
            tenant_id=tenant_id,
            shard_id=shard_id,
            saturation_level=saturation_level,
            active_agents=active_agents,
            active_executions=active_executions,
            cpu_usage_percent=cpu_usage_percent,
            memory_usage_percent=memory_usage_percent,
        )

        logger.debug(
            f"Recorded saturation for shard {shard_id}: {saturation_level:.2%}"
        )

        return saturation

    def create_quota(
        self,
        tenant_id: str,
        quota_type: str,
        period: str,
        limit_value: int,
    ) -> TenantQuota:
        """Create a quota definition.

        Args:
            tenant_id: Tenant ID.
            quota_type: Type of quota.
            period: Quota period.
            limit_value: Quota limit value.

        Returns:
            Created TenantQuota instance.
        """
        # Calculate reset time
        reset_at = self._calculate_reset_time(period)

        quota = TenantQuota.objects.create(
            tenant_id=tenant_id,
            quota_type=quota_type,
            period=period,
            limit_value=limit_value,
            current_usage=0,
            reset_at=reset_at,
        )

        logger.info(
            f"Created quota {quota_type} ({period}) for tenant {tenant_id}: "
            f"{limit_value}"
        )

        return quota

    def _reset_quota(self, quota: TenantQuota) -> None:
        """Reset quota usage.

        Args:
            quota: Quota instance to reset.
        """
        quota.current_usage = 0
        quota.reset_at = self._calculate_reset_time(quota.period)
        quota.save(update_fields=["current_usage", "reset_at", "updated_at"])

        logger.info(
            f"Reset quota {quota.quota_type} ({quota.period}) for tenant "
            f"{quota.tenant_id}"
        )

    def _calculate_reset_time(self, period: str) -> datetime:
        """Calculate quota reset time.

        Args:
            period: Quota period.

        Returns:
            Reset datetime.
        """
        now = timezone.now()

        if period == QuotaPeriod.HOURLY:
            return now.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=1
            )
        elif period == QuotaPeriod.DAILY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
        elif period == QuotaPeriod.WEEKLY:
            days_until_monday = (7 - now.weekday()) % 7
            if days_until_monday == 0:
                days_until_monday = 7
            return now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=days_until_monday)
        elif period == QuotaPeriod.MONTHLY:
            next_month = now.replace(day=1) + timedelta(days=32)
            return next_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Default to daily
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=1
        )

    def _create_default_quota(
        self, tenant_id: str, quota_type: str, period: str
    ) -> TenantQuota:
        """Create default unlimited quota.

        Args:
            tenant_id: Tenant ID.
            quota_type: Type of quota.
            period: Quota period.

        Returns:
            Created TenantQuota instance.
        """
        # Default to very high limit (effectively unlimited)
        default_limit = 10**12  # 1 trillion

        return self.create_quota(tenant_id, quota_type, period, default_limit)


# Global quota service instance
quota_service = QuotaService()

