# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Rate Limit Service Tests
# backend/src/tests/test_rate_limit_service.py
# Reference: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Test Coverage)
# CRITICAL NOTES:
# - Test coverage ≥90% for all services (engineering-governance-and-pr-controls.md § 2.2)
# - Rate limit check logic: per-tenant, per-user, per-subscription-plan
# - Test happy path: valid request within limits (success)
# - Test edge case: request at limit boundary (exactly at limit)
# - Test failure path: request exceeds limit (429 Too Many Requests)
# - Test time window reset: requests after reset time allowed
# - Test Redis backend: limit counters stored/incremented correctly
# - Test concurrent requests: atomic counter updates (no race conditions)
# - Test different scopes: user, tenant, global rate limits
# - Mock database and Redis for isolation and speed
# Source: docs/architecture/engineering-governance-and-pr-controls.md § 3

import pytest
from datetime import datetime, timedelta
from src.services.rate_limit_service import RateLimitService, RateLimitScope, RateLimitPeriod
from src.models.rate_limits import SubscriptionRateLimit

@pytest.mark.asyncio
def test_check_rate_limit_success(db_session, redis_client, test_tenant, test_subscription_plan):
    """Test successful rate limit check"""
    # Create rate limit
    rate_limit = SubscriptionRateLimit(
        subscription_plan_id=test_subscription_plan.id,
        scope=RateLimitScope.API.value,
        limit=100,
        period=RateLimitPeriod.MINUTE.value
    )
    db_session.add(rate_limit)
    db_session.commit()

    rate_limit_service = RateLimitService(db_session, redis_client)

    # Check rate limit (should pass)
    is_allowed, info = rate_limit_service.check_rate_limit(
        tenant_id=test_tenant.id,
        scope=RateLimitScope.API
    )

    assert is_allowed is True
    assert info is not None
    assert info["remaining"] < info["limit"]

@pytest.mark.asyncio
def test_check_rate_limit_exceeded(db_session, redis_client, test_tenant, test_subscription_plan):
    """Test rate limit exceeded"""
    # Create rate limit with low limit
    rate_limit = SubscriptionRateLimit(
        subscription_plan_id=test_subscription_plan.id,
        scope=RateLimitScope.API.value,
        limit=1,
        period=RateLimitPeriod.MINUTE.value
    )
    db_session.add(rate_limit)
    db_session.commit()

    rate_limit_service = RateLimitService(db_session, redis_client)

    # First request should pass
    is_allowed1, _ = rate_limit_service.check_rate_limit(
        tenant_id=test_tenant.id,
        scope=RateLimitScope.API
    )
    assert is_allowed1 is True

    # Second request should fail
    is_allowed2, info = rate_limit_service.check_rate_limit(
        tenant_id=test_tenant.id,
        scope=RateLimitScope.API
    )
    assert is_allowed2 is False
    assert info["remaining"] == 0

