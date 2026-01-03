# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Complete Health Check Implementation
# backend/src/api/routes/health.py
# Reference: docs/architecture/operational-runbooks.md § 4.1 (Health Monitoring)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.db import connection
from django.conf import settings
from datetime import datetime
import redis


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Basic health check.
    
    CRITICAL: Health checks execute without authentication context.
    Used by load balancers and monitoring systems.
    See docs/architecture/operational-runbooks.md § 4.1.
    """
    return Response({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": getattr(settings, 'APP_VERSION', 'unknown'),
        "environment": getattr(settings, 'APP_ENV', 'unknown')
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def detailed_health_check(request):
    """Detailed health check with dependencies."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": getattr(settings, 'APP_VERSION', 'unknown'),
        "environment": getattr(settings, 'APP_ENV', 'unknown'),
        "checks": {}
    }

    # Database check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status["checks"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    # Redis check
    try:
        redis_url = getattr(settings, 'REDIS_URL', None)
        if redis_url:
            r = redis.from_url(redis_url)
            r.ping()
            health_status["checks"]["redis"] = {"status": "healthy"}
        else:
            health_status["checks"]["redis"] = {"status": "not_configured"}
    except Exception as e:
        health_status["checks"]["redis"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "unhealthy"

    return Response(health_status)


@api_view(['GET'])
@permission_classes([AllowAny])
def readiness_check(request):
    """Kubernetes readiness check."""
    try:
        # Check if database is ready
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Check if Redis is ready
        redis_url = getattr(settings, 'REDIS_URL', None)
        if redis_url:
            r = redis.from_url(redis_url)
            r.ping()

        return Response({"status": "ready"})
    except Exception as e:
        return Response(
            {"status": "not ready", "error": str(e)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def liveness_check(request):
    """Kubernetes liveness check."""
    return Response({"status": "alive"})
