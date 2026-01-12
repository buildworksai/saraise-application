"""
URL routing for AI Agent Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AgentExecutionViewSet,
    AgentSchedulerTaskViewSet,
    AgentViewSet,
    ApprovalRequestViewSet,
    QuotaUsageViewSet,
    SoDPolicyViewSet,
    SoDViolationViewSet,
    TenantQuotaViewSet,
    ToolInvocationViewSet,
    ToolViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agent")
router.register(r"executions", AgentExecutionViewSet, basename="execution")
router.register(r"scheduler-tasks", AgentSchedulerTaskViewSet, basename="scheduler-task")
router.register(r"approvals", ApprovalRequestViewSet, basename="approval")
router.register(r"sod-policies", SoDPolicyViewSet, basename="sod-policy")
router.register(r"sod-violations", SoDViolationViewSet, basename="sod-violation")
router.register(r"quotas", TenantQuotaViewSet, basename="quota")
router.register(r"quota-usage", QuotaUsageViewSet, basename="quota-usage")
router.register(r"tools", ToolViewSet, basename="tool")
router.register(r"tool-invocations", ToolInvocationViewSet, basename="tool-invocation")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
