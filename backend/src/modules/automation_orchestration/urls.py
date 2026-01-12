"""
URL routing for AutomationOrchestration module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import AutomationOrchestrationResourceViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r'resources', AutomationOrchestrationResourceViewSet, basename='resource')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('health/', health_check, name='health_check'),
]
