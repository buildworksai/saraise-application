"""
Platform Management Health Checks
"""

from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from .models import SystemHealth


def check_database_health():
    """Check database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return {'status': 'healthy', 'response_time_ms': None}
    except Exception as e:
        return {'status': 'unhealthy', 'error_message': str(e)}


def check_cache_health():
    """Check cache (Redis) connectivity."""
    try:
        cache.set('health_check', 'ok', 10)
        result = cache.get('health_check')
        if result == 'ok':
            return {'status': 'healthy', 'response_time_ms': None}
        return {'status': 'degraded', 'error_message': 'Cache not responding correctly'}
    except Exception as e:
        return {'status': 'unhealthy', 'error_message': str(e)}


def update_health_metrics():
    """Update system health metrics."""
    # Database health
    db_health = check_database_health()
    SystemHealth.objects.update_or_create(
        service_name='database',
        defaults={
            'status': db_health['status'],
            'error_message': db_health.get('error_message', ''),
            'last_check': timezone.now()
        }
    )

    # Cache health
    cache_health = check_cache_health()
    SystemHealth.objects.update_or_create(
        service_name='cache',
        defaults={
            'status': cache_health['status'],
            'error_message': cache_health.get('error_message', ''),
            'last_check': timezone.now()
        }
    )
