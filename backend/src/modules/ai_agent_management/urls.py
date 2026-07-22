"""Normative API v2 routes (also mounted under the compatibility v1 path)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AgentExecutionViewSet, AgentViewSet, ApprovalRequestViewSet, AsyncJobViewSet,
    AuditEventViewSet, AuditTrailViewSet, CostRecordViewSet, CostSummaryViewSet,
    EgressRequestViewSet, EgressRuleViewSet, KillSwitchViewSet, QuotaUsageViewSet,
    QuotaViewSet, ScheduleViewSet, SecretAccessViewSet, SecretViewSet,
    ShardSaturationViewSet, SoDPolicyViewSet, SoDViolationViewSet,
    TokenUsageViewSet, ToolInvocationViewSet, ToolViewSet,
)
from .health import ModuleHealthView

router = DefaultRouter()
router.register("agents", AgentViewSet, basename="agent")
router.register("executions", AgentExecutionViewSet, basename="execution")
router.register("schedules", ScheduleViewSet, basename="schedule")
router.register("approvals", ApprovalRequestViewSet, basename="approval")
router.register("sod-policies", SoDPolicyViewSet, basename="sod-policy")
router.register("sod-violations", SoDViolationViewSet, basename="sod-violation")
router.register("tools", ToolViewSet, basename="tool")
router.register("tool-invocations", ToolInvocationViewSet, basename="tool-invocation")
router.register("egress-rules", EgressRuleViewSet, basename="egress-rule")
router.register("egress-requests", EgressRequestViewSet, basename="egress-request")
router.register("secrets", SecretViewSet, basename="secret")
router.register("secret-accesses", SecretAccessViewSet, basename="secret-access")
router.register("quotas", QuotaViewSet, basename="quota")
router.register("quota-usage", QuotaUsageViewSet, basename="quota-usage")
router.register("saturation", ShardSaturationViewSet, basename="saturation")
router.register("kill-switches", KillSwitchViewSet, basename="kill-switch")
router.register("token-usage", TokenUsageViewSet, basename="token-usage")
router.register("cost-records", CostRecordViewSet, basename="cost-record")
router.register("cost-summaries", CostSummaryViewSet, basename="cost-summary")
router.register("audit-events", AuditEventViewSet, basename="audit-event")
router.register("audit-trails", AuditTrailViewSet, basename="audit-trail")
router.register("jobs", AsyncJobViewSet, basename="job")

urlpatterns = [path("", include(router.urls)), path("health/", ModuleHealthView.as_view(), name="health")]
