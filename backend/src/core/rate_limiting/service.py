"""
Rate Limiting Service Implementation.

SPDX-License-Identifier: Apache-2.0
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

from src.modules.tenant_management.models import Tenant

logger = logging.getLogger(__name__)


class RateLimitService:
    """Service for rate limiting based on tenant subscription tiers."""

    CACHE_PREFIX = "rate_limit"
    CACHE_TIMEOUT = 86400  # 24 hours

    @staticmethod
    def check_rate_limit(tenant_id: str, resource_type: str = "api_calls") -> tuple[bool, Optional[int]]:
        """Check if tenant has exceeded rate limit.

        Args:
            tenant_id: Tenant ID.
            resource_type: Type of resource (api_calls, storage, bandwidth, etc.).

        Returns:
            Tuple of (is_allowed, remaining_quota).
            is_allowed: True if request is allowed, False if rate limit exceeded.
            remaining_quota: Remaining quota for the day, or None if unlimited.
        """
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            logger.error(f"Tenant {tenant_id} not found for rate limiting")
            return False, None

        # Get limit based on resource type
        if resource_type == "api_calls":
            limit = tenant.max_api_calls_per_day
        elif resource_type == "storage":
            limit = tenant.max_storage_gb * 1024  # Convert GB to MB for comparison
        else:
            # Default: no limit
            return True, None

        if limit <= 0:
            # Unlimited
            return True, None

        # Get current usage from cache
        cache_key = f"{RateLimitService.CACHE_PREFIX}:{tenant_id}:{resource_type}:{timezone.now().date()}"
        current_usage = cache.get(cache_key, 0)

        if current_usage >= limit:
            return False, 0

        return True, limit - current_usage

    @staticmethod
    def increment_usage(tenant_id: str, resource_type: str = "api_calls", amount: int = 1) -> None:
        """Increment resource usage counter.

        Args:
            tenant_id: Tenant ID.
            resource_type: Type of resource.
            amount: Amount to increment.
        """
        cache_key = f"{RateLimitService.CACHE_PREFIX}:{tenant_id}:{resource_type}:{timezone.now().date()}"
        current_usage = cache.get(cache_key, 0)
        cache.set(cache_key, current_usage + amount, RateLimitService.CACHE_TIMEOUT)

    @staticmethod
    def get_usage(tenant_id: str, resource_type: str = "api_calls") -> int:
        """Get current usage for tenant.

        Args:
            tenant_id: Tenant ID.
            resource_type: Type of resource.

        Returns:
            Current usage count.
        """
        cache_key = f"{RateLimitService.CACHE_PREFIX}:{tenant_id}:{resource_type}:{timezone.now().date()}"
        return cache.get(cache_key, 0)

    @staticmethod
    def get_limit(tenant_id: str, resource_type: str = "api_calls") -> int:
        """Get rate limit for tenant.

        Args:
            tenant_id: Tenant ID.
            resource_type: Type of resource.

        Returns:
            Rate limit (0 for unlimited).
        """
        try:
            tenant = Tenant.objects.get(id=tenant_id)
            if resource_type == "api_calls":
                return tenant.max_api_calls_per_day
            elif resource_type == "storage":
                return tenant.max_storage_gb
            else:
                return 0
        except Tenant.DoesNotExist:
            return 0
