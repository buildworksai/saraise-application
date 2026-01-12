"""
URL routing for AiProviderConfiguration module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    AIModelDeploymentViewSet,
    AIModelViewSet,
    AIProviderCredentialViewSet,
    AIProviderViewSet,
    AIUsageLogViewSet,
    SecretManagementViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"providers", AIProviderViewSet, basename="ai-provider")
router.register(r"credentials", AIProviderCredentialViewSet, basename="ai-provider-credential")
router.register(r"models", AIModelViewSet, basename="ai-model")
router.register(r"deployments", AIModelDeploymentViewSet, basename="ai-model-deployment")
router.register(r"usage-logs", AIUsageLogViewSet, basename="ai-usage-log")
router.register(r"secrets", SecretManagementViewSet, basename="secret-management")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
