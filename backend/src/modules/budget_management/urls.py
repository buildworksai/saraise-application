"""Authoritative v2 route surface for budget management."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ApprovalViewSet,
    AvailabilityAPIView,
    BudgetLineViewSet,
    BudgetViewSet,
    HealthAPIView,
    VarianceAlertViewSet,
)

app_name = "budget_management"

router = DefaultRouter()
router.register("budgets", BudgetViewSet, basename="budget")
router.register("budget-lines", BudgetLineViewSet, basename="budget-line")
router.register("approvals", ApprovalViewSet, basename="approval")
router.register("variance-alerts", VarianceAlertViewSet, basename="variance-alert")

urlpatterns = [
    path("", include(router.urls)),
    path("availability/", AvailabilityAPIView.as_view(), name="availability"),
    path("health/", HealthAPIView.as_view(), name="health"),
]
