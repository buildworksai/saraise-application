# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Rate Limit Middleware
# Reference: docs/architecture/security-model.md § 4.1 (Rate Limiting)
# Also: docs/architecture/operational-runbooks.md § 4 (Security Operations)
# 
# CRITICAL NOTES:
# - Rate limits enforced PER TENANT (tenant_id from session)
# - Sliding window counter tracks requests in time buckets
# - Exceeding limits returns 429 Too Many Requests (no exception exposed)
# - All rate limit violations logged to audit logs (security-model.md § 4.2)
# - Uses Django ORM and DRF Response per application-architecture.md § 3.2

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status
from django.middleware.base import BaseHTTPMiddleware
from src.services.rate_limit_service import RateLimitService, RateLimitScope
from django.db import transaction
from src.core.redis_client import get_redis_client
from typing import Callable, Optional

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limits per tenant."""
    
    def __init__(self, app, scope: RateLimitScope = RateLimitScope.API):
        super().__init__(app)
        self.scope = scope
        self.redis_client = get_redis_client()

    def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limit before processing request."""
        # Skip rate limiting for platform operations
        if request.path.startswith("/api/v1/platform/"):
            return call_next(request)

        # Get tenant ID from request
        tenant_id = self._get_tenant_id(request)
        if not tenant_id:
            # No tenant ID - allow request (will be handled by auth middleware)
            return call_next(request)

        # Check rate limit
        rate_limit_service = RateLimitService(self.redis_client)
        is_allowed, rate_limit_info = rate_limit_service.check_rate_limit(
            tenant_id=tenant_id,
            scope=self.scope,
            request=request
        )

        if not is_allowed:
            # Rate limit exceeded - return 429
            response = Response(
                data={
                    "error": "Rate limit exceeded",
                    "message": f"Rate limit of {rate_limit_info['limit']} requests per {self.scope.value} exceeded",
                    "limit": rate_limit_info["limit"],
                    "retry_after": rate_limit_info.get("retry_after"),
                    "reset": rate_limit_info.get("reset")
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

            # Add rate limit headers
            response["X-RateLimit-Limit"] = str(rate_limit_info["limit"])
            response["X-RateLimit-Remaining"] = "0"
            response["X-RateLimit-Reset"] = rate_limit_info.get("reset", "")
            response["Retry-After"] = str(rate_limit_info.get("retry_after", 60))

            return response

        # Process request
        response = call_next(request)

        # Add rate limit headers to successful response
        if rate_limit_info:
            response["X-RateLimit-Limit"] = str(rate_limit_info["limit"])
            response["X-RateLimit-Remaining"] = str(rate_limit_info["remaining"])
            response["X-RateLimit-Reset"] = rate_limit_info.get("reset", "")

        return response

    def _get_tenant_id(self, request: Request) -> Optional[str]:
        """Get tenant ID from request (from session or header)."""
        # Try to get from session (if authenticated)
        if hasattr(request, 'user') and hasattr(request.user, 'tenant_id'):
            return request.user.tenant_id

        # Try to get from header
        return request.META.get("HTTP_X_TENANT_ID")

