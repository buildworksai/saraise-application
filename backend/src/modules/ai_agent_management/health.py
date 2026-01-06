"""
Health check endpoint for AI Agent Management module.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import connection
from django.core.cache import cache

from .models import Agent


@api_view(['GET'])
def health_check(request):
    """
    Health check endpoint.

    Checks:
    - Database connectivity
    - Redis connectivity
    - Module-specific health

    Returns:
    - 200 OK if healthy
    - 503 Service Unavailable if unhealthy
    """
    health_status = {
        'status': 'healthy',
        'module': 'ai-agent-management',
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

    # Check Redis connectivity
    try:
        cache.set('health_check', 'ok', timeout=10)
        result = cache.get('health_check')
        if result == 'ok':
            health_status['checks']['redis'] = 'ok'
        else:
            health_status['status'] = 'unhealthy'
            health_status['checks']['redis'] = 'error: cache read failed'
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['redis'] = f'error: {str(e)}'

    # Check agent queue status
    try:
        active_agents_count = Agent.objects.filter(is_active=True).count()
        health_status['checks']['agent_queue'] = {
            'status': 'ok',
            'active_agents': active_agents_count
        }
    except Exception as e:
        health_status['status'] = 'unhealthy'
        health_status['checks']['agent_queue'] = f'error: {str(e)}'

    status_code = 200 if health_status['status'] == 'healthy' else 503
    return Response(health_status, status=status_code)

