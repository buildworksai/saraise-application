# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Redis Connection with Retry and Error Handling
# backend/src/services/redis_service.py
# Reference: docs/architecture/operational-runbooks.md § 2.1 (Infrastructure)

import redis
import asyncio
from src.core.urls import get_redis_url
from typing import Optional

class RedisService:
    """Redis integration with resilient retry logic.
    
    CRITICAL: Platform-level infrastructure service (no tenant isolation).
    Used for session storage and caching. See docs/architecture/
    authentication-and-session-management-spec.md § 3.1.
    """
    
    def __init__(self):
        redis_url = get_redis_url()
        self.client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )

    def get_with_retry(self, key: str, max_retries: int = 3) -> Optional[str]:
        """Get value with retry logic"""
        for attempt in range(max_retries):
            try:
                return self.client.get(key)
            except redis.RedisError as e:
                if attempt == max_retries - 1:
                    raise e
                asyncio.sleep(2 ** attempt)  # Exponential backoff
        return None

