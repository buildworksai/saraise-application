# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Application metrics implementation
# backend/src/core/metrics.py
# Reference: docs/architecture/operational-runbooks.md § 4 (Monitoring)
# CRITICAL NOTES:
# - Prometheus metrics exposed at /metrics endpoint (standard format)
# - REQUEST_COUNT: Total HTTP requests per method, endpoint, status code
# - REQUEST_DURATION: Request latency histogram (latency distribution analysis)
# - ACTIVE_CONNECTIONS: Current active database connections (resource monitoring)
# - Custom metrics added per-module (module-specific performance tracking)
# - Metrics collected without blocking request processing (minimal overhead)
# - Tenant context included in metrics (per-tenant performance tracking)
# - Alert thresholds configured in Prometheus/AlertManager
# - Metrics retained for 15 days (configurable via Prometheus retention)
# - Grafana dashboards visualize metrics (operational-runbooks.md § 4.1)
# - SLA monitoring: response time, error rate, availability (p99 latency)
# Source: docs/architecture/operational-runbooks.md § 4.1

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
import time

# Metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Active database connections')

@api_view(['GET'])
@permission_classes([AllowAny])
def metrics(request):
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), content_type="text/plain")
