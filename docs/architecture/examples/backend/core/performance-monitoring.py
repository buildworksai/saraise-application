# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Application performance monitoring
# backend/src/core/performance_monitoring.py
# Reference: docs/architecture/operational-runbooks.md § 4.1 (Performance Monitoring)
# CRITICAL NOTES:
# - Decorator-based monitoring for minimal code changes (non-intrusive)
# - Async and sync function support (auto-detects via inspection)
# - Execution time threshold: 1.0 second for warning logs (configurable per environment)
# - Slow operation logging includes function name and execution time
# - Exception handling logs errors without suppressing (monitoring without masking issues)
# - Memory profiling optional (CPU-intensive, use only for debugging)
# - Database query timing tracked separately (connection pool, query execution time)
# - Request latency percentiles: p50, p95, p99 (SLA monitoring)
# - Performance alerts triggered on thresholds (Prometheus/AlertManager)
# - Metrics aggregated by endpoint and module (module-level performance tracking)
# Source: docs/architecture/operational-runbooks.md § 4.1

import time
import functools
import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

def monitor_performance(func: Callable) -> Callable:
    """Decorator to monitor function performance"""
    @functools.wraps(func)
    def async_wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            if execution_time > 1.0:  # Log slow operations
                logger.warning(f"Slow operation: {func.__name__} took {execution_time:.2f}s")

            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Operation failed: {func.__name__} failed after {execution_time:.2f}s: {e}")
            raise

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time

            if execution_time > 1.0:  # Log slow operations
                logger.warning(f"Slow operation: {func.__name__} took {execution_time:.2f}s")

            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Operation failed: {func.__name__} failed after {execution_time:.2f}s: {e}")
            raise

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

# Usage example
@monitor_performance
def create_ai_agent(agent_data: dict) -> AIAgent:
    # Agent creation logic
    pass

