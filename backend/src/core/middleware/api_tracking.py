"""
SPDX-License-Identifier: Apache-2.0

API Call Tracking Middleware

Tracks API calls for analytics and metrics collection.
This middleware records request counts, response times, and error rates.
"""

import logging
import time

from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class APITrackingMiddleware(MiddlewareMixin):
    """
    Middleware to track API calls for platform metrics.

    Records:
    - Total API calls (per day)
    - Response times
    - Error rates
    - Endpoint usage patterns

    Data is stored in Redis cache and can be aggregated for metrics.
    """

    def process_request(self, request):
        """Record request start time."""
        request._api_start_time = time.time()
        return None

    def process_response(self, request, response):
        """Record API call metrics."""
        if not hasattr(request, "_api_start_time"):
            return response

        # Calculate response time
        response_time_ms = (time.time() - request._api_start_time) * 1000

        # Skip non-API requests
        if not request.path.startswith("/api/"):
            return response

        try:
            # Get current date key
            from django.utils import timezone

            date_key = timezone.now().strftime("%Y-%m-%d")

            # Track metrics in Redis
            cache_key_prefix = f"api_metrics:{date_key}"

            # Increment total calls
            cache_key_total = f"{cache_key_prefix}:total"
            try:
                cache.incr(cache_key_total, 1)
            except ValueError:
                # Key doesn't exist yet, initialize it
                cache.set(cache_key_total, 1, timeout=86400)

            # Track response time (store as list for aggregation)
            cache_key_times = f"{cache_key_prefix}:response_times"
            times = cache.get(cache_key_times, [])
            times.append(response_time_ms)
            # Keep only last 1000 response times per day
            if len(times) > 1000:
                times = times[-1000:]
            cache.set(cache_key_times, times, timeout=86400)  # 24 hours

            # Track errors
            if response.status_code >= 400:
                cache_key_errors = f"{cache_key_prefix}:errors"
                try:
                    cache.incr(cache_key_errors, 1)
                except ValueError:
                    # Key doesn't exist yet, initialize it
                    cache.set(cache_key_errors, 1, timeout=86400)

            # Track endpoint usage
            endpoint = request.path
            cache_key_endpoint = f"{cache_key_prefix}:endpoint:{endpoint}"
            try:
                cache.incr(cache_key_endpoint, 1)
            except ValueError:
                # Key doesn't exist yet, initialize it
                cache.set(cache_key_endpoint, 1, timeout=86400)

            # Set expiration for all keys (24 hours)
            # Note: expire() is only available for Redis cache, not LocMemCache
            # For LocMemCache, timeout is set when calling cache.set()
            # Since we already set timeout in cache.set() calls above, we only need expire() for Redis
            try:
                cache.expire(cache_key_total, 86400)
                cache.expire(cache_key_endpoint, 86400)
            except AttributeError:
                # LocMemCache doesn't support expire(), but timeout is already set in cache.set()
                pass

        except Exception as e:
            # Don't break requests if tracking fails
            logger.warning(f"Failed to track API metrics: {e}")

        return response
