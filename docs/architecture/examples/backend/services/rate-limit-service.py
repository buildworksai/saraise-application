# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Rate Limit Service
# backend/src/modules/ratelimit/services/rate_limit_service.py
# Reference: docs/architecture/application-architecture.md § 2.1
# CRITICAL: SARAISE uses Django ORM exclusively

from django.db import transaction
from django.db.models import Q
from src.models.rate_limits import (
    SubscriptionRateLimit, RateLimitUsage, RateLimitViolation,
    RateLimitScope, RateLimitPeriod
)
from src.models.subscriptions import Subscription
from src.models.tenants import Tenant
from datetime import datetime, timedelta
from typing import Optional, Tuple
import redis

class RateLimitService:
    """Rate limiting service (tenant-scoped).
    
    CRITICAL: Rate limits are tenant-scoped with explicit filtering.
    Uses Redis for fast in-memory counting; database for persistent records.
    See docs/architecture/application-architecture.md § 2.1.
    """
    
    def __init__(self, redis_client: redis.Redis, tenant_id: str):
        # ✅ CORRECT: Django ORM - no database session needed
        # Use Model.objects directly for all operations
        self.redis = redis_client
        self.tenant_id = tenant_id

    def _get_period_timedelta(self, period: RateLimitPeriod) -> timedelta:
        """Get timedelta for rate limit period"""
        period_map = {
            RateLimitPeriod.SECOND: timedelta(seconds=1),
            RateLimitPeriod.MINUTE: timedelta(minutes=1),
            RateLimitPeriod.HOUR: timedelta(hours=1),
            RateLimitPeriod.DAY: timedelta(days=1),
            RateLimitPeriod.MONTH: timedelta(days=30),
        }
        return period_map.get(period, timedelta(minutes=1))

    def _get_redis_key(self, tenant_id: str, scope: RateLimitScope, period_start: datetime) -> str:
        """Get Redis key for rate limit tracking"""
        period_str = period_start.strftime("%Y%m%d%H%M%S")
        return f"rate_limit:{tenant_id}:{scope.value}:{period_str}"

    def get_rate_limit(
        self,
        tenant_id: str,
        scope: RateLimitScope
    ) -> Optional[SubscriptionRateLimit]:
        """Get rate limit for tenant's subscription

        NOTE: tenant_id is used for platform-level subscription lookup.
        Subscriptions table is in platform schema and requires tenant_id filtering.
        """
        # Get tenant's active subscription (platform-level query)
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        subscription = Subscription.objects.filter(
            tenant_id=tenant_id,
            status="active"
        ).order_by('-created_at').first()

        if not subscription:
            # Return default rate limit or None
            return None

        # Get rate limit for subscription plan and scope
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        rate_limit = SubscriptionRateLimit.objects.filter(
            subscription_plan_id=subscription.plan_id,
            scope=scope.value
        ).first()

        return rate_limit

    def check_rate_limit(
        self,
        tenant_id: str,
        scope: RateLimitScope,
        request: Optional[Request] = None
    ) -> Tuple[bool, Optional[dict]]:
        """Check if request is within rate limit"""
        # Get rate limit configuration
        rate_limit = self.get_rate_limit(tenant_id, scope)

        if not rate_limit:
            # No rate limit configured - allow request
            return True, None

        # Calculate current period
        period_delta = self._get_period_timedelta(RateLimitPeriod(rate_limit.period))
        now = datetime.utcnow()
        period_start = now.replace(
            second=0, microsecond=0
        ) if rate_limit.period == RateLimitPeriod.MINUTE else now.replace(
            minute=0, second=0, microsecond=0
        ) if rate_limit.period == RateLimitPeriod.HOUR else now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) if rate_limit.period == RateLimitPeriod.DAY else now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        # Get or create usage record
        redis_key = self._get_redis_key(tenant_id, scope, period_start)
        current_count = self.redis.incr(redis_key)

        # Set expiration
        if current_count == 1:
            self.redis.expire(redis_key, int(period_delta.total_seconds()))

        # Check if limit exceeded
        if current_count > rate_limit.limit:
            # Log violation
            self.log_violation(
                tenant_id=tenant_id,
                scope=scope,
                limit=rate_limit.limit,
                current_count=current_count,
                request=request
            )

            # Update usage record
            self.update_usage(
                tenant_id=tenant_id,
                scope=scope,
                period_start=period_start,
                period_end=period_start + period_delta,
                request_count=current_count,
                limit=rate_limit.limit,
                is_violation=True
            )

            return False, {
                "limit": rate_limit.limit,
                "remaining": 0,
                "reset": (period_start + period_delta).isoformat(),
                "retry_after": int((period_start + period_delta - now).total_seconds())
            }

        # Update usage record
        self.update_usage(
            tenant_id=tenant_id,
            scope=scope,
            period_start=period_start,
            period_end=period_start + period_delta,
            request_count=current_count,
            limit=rate_limit.limit,
            is_violation=False
        )

        return True, {
            "limit": rate_limit.limit,
            "remaining": max(0, rate_limit.limit - current_count),
            "reset": (period_start + period_delta).isoformat()
        }

    def update_usage(
        self,
        tenant_id: str,
        scope: RateLimitScope,
        period_start: datetime,
        period_end: datetime,
        request_count: int,
        limit: int,
        is_violation: bool = False
    ):
        """Update rate limit usage record"""
        # ✅ CORRECT: Django ORM - use Model.objects.get_or_create() or filter().first()
        usage, created = RateLimitUsage.objects.get_or_create(
            tenant_id=tenant_id,
            scope=scope.value,
            period_start=period_start,
            defaults={
                'period_end': period_end,
                'request_count': request_count,
                'limit': limit
            }
        )

        if not created:
            usage.request_count = request_count
            usage.updated_at = datetime.utcnow()

        if is_violation:
            usage.violations += 1
            usage.last_violation_at = datetime.utcnow()

        usage.save()

    def log_violation(
        self,
        tenant_id: str,
        scope: RateLimitScope,
        limit: int,
        current_count: int,
        request: Optional[Request] = None
    ):
        """Log rate limit violation"""
        # ✅ CORRECT: Django ORM - use Model.objects.create() for creating records
        violation = RateLimitViolation.objects.create(
            tenant_id=tenant_id,
            scope=scope.value,
            limit=limit,
            current_count=current_count,
            endpoint=request.url.path if request else None,
            request_method=request.method if request else None,
            ip_address=request.client.host if request else None,
            user_agent=request.headers.get("user-agent") if request else None
        )

    def get_usage_stats(
        self,
        tenant_id: str,
        scope: Optional[RateLimitScope] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> dict:
        """Get rate limit usage statistics

        NOTE: RateLimitUsage is platform-level tracking (in platform schema).
        tenant_id filtering is appropriate here for usage statistics queries.
        """
        # ✅ CORRECT: Django ORM - use Model.objects.filter() using Django ORM QuerySet
        queryset = RateLimitUsage.objects.filter(tenant_id=tenant_id)

        if scope:
            queryset = queryset.filter(scope=scope.value)
        if start_date:
            queryset = queryset.filter(period_start__gte=start_date)
        if end_date:
            queryset = queryset.filter(period_end__lte=end_date)

        usage_records = queryset.all()

        total_requests = sum(record.request_count for record in usage_records)
        total_violations = sum(record.violations for record in usage_records)

        return {
            "total_requests": total_requests,
            "total_violations": total_violations,
            "violation_rate": total_violations / total_requests if total_requests > 0 else 0,
            "periods": len(usage_records)
        }

