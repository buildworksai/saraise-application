"""
URL routing for PerformanceMonitoring module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import PerformanceMonitoringResourceViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r'resources', PerformanceMonitoringResourceViewSet, basename='resource')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('health/', health_check, name='health_check'),
]
