"""
URL routing for Budget Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import BudgetLineViewSet, BudgetViewSet
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"budgets", BudgetViewSet, basename="budget")
router.register(r"budget-lines", BudgetLineViewSet, basename="budget-line")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
