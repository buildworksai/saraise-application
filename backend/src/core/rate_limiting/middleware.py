"""
Rate Limiting Middleware.

SPDX-License-Identifier: Apache-2.0
"""

import logging

from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from src.core.auth_utils import get_user_tenant_id
from src.core.rate_limiting.service import RateLimitService

logger = logging.getLogger(__name__)


class RateLimitMiddleware(MiddlewareMixin):
    """Middleware to enforce rate limits on API requests."""

    def process_request(self, request):
        """Check rate limit before processing request."""
        # Skip rate limiting for non-API endpoints
        if not request.path.startswith("/api/"):
            return None

        # Skip rate limiting for health checks and metrics
        if request.path in ["/api/health/", "/api/metrics/"]:
            return None

        tenant_id = get_user_tenant_id(request.user) if hasattr(request, "user") and request.user.is_authenticated else None

        if not tenant_id:
            # No tenant ID - allow request (will be handled by auth middleware)
            return None

        # Check rate limit
        is_allowed, remaining = RateLimitService.check_rate_limit(tenant_id, "api_calls")

        if not is_allowed:
            logger.warning(f"Rate limit exceeded for tenant {tenant_id}")
            return JsonResponse(
                {
                    "error": "Rate limit exceeded",
                    "message": "You have exceeded your daily API call limit. Please upgrade your plan or try again tomorrow.",
                },
                status=429,
            )

        # Increment usage counter
        RateLimitService.increment_usage(tenant_id, "api_calls")

        # Add rate limit headers
        if remaining is not None:
            request.META["X-RateLimit-Remaining"] = str(remaining)
            limit = RateLimitService.get_limit(tenant_id, "api_calls")
            request.META["X-RateLimit-Limit"] = str(limit)

        return None
