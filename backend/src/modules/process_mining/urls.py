"""
URL routing for ProcessMining module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import ProcessMiningResourceViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r'resources', ProcessMiningResourceViewSet, basename='resource')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('health/', health_check, name='health_check'),
]
