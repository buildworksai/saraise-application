"""
Regional Health Checks

Rule: SARAISE-17007 (Health checks required for all modules)
"""
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .models import RegionalResource


@require_http_methods(["GET"])
def health_check(request):
    """
    Health check endpoint for Regional module.

    Returns:
    - 200 OK if healthy
    - 503 Service Unavailable if unhealthy
    """
    health_status = {
        'status': 'healthy',
        'module': 'regional',
        'checks': {}
    }

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health_status['checks']['database'] = 'ok'
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['database'] = f'error: {str(e)}'

    # Check cache (Redis) connectivity
    try:
        cache.set("health_check_regional", "ok", 10)
        result = cache.get("health_check_regional")
        if result == "ok":
            health_status['checks']['cache'] = 'ok'
        else:
            health_status['status'] = 'degraded'
            health_status['checks']['cache'] = 'not responding correctly'
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['cache'] = f'error: {str(e)}'

    # Check module-specific model accessibility
    try:
        # Verify we can query the primary model
        count = RegionalResource.objects.count()
        health_status['checks']['module_model'] = {'status': 'ok', 'total_count': count}
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['module_model'] = f'error: {str(e)}'

    status_code = 200 if health_status['status'] == 'healthy' else 503
    return JsonResponse(health_status, status=status_code)
