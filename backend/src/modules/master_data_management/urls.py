"""API v2 routing for Master Data Management."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import jobs as _jobs  # noqa: F401 - importing performs explicit handler registration

from .api import (
    AsyncJobViewSet,
    DashboardViewSet,
    DataQualityIssueViewSet,
    DataQualityRuleViewSet,
    MasterDataEntityViewSet,
    MasterDataConfigurationViewSet,
    MasterEntityTypeViewSet,
    MatchCandidateViewSet,
    MatchingOperationsViewSet,
    MatchingRuleViewSet,
    MergeViewSet,
    QualityScanViewSet,
)
from .health import live, ready

app_name = "master_data_management"

router = DefaultRouter()
router.register("entity-types", MasterEntityTypeViewSet, basename="entity-type")
router.register("entities", MasterDataEntityViewSet, basename="entity")
router.register("quality-rules", DataQualityRuleViewSet, basename="quality-rule")
router.register("quality-issues", DataQualityIssueViewSet, basename="quality-issue")
router.register("quality-scans", QualityScanViewSet, basename="quality-scan")
router.register("matching-rules", MatchingRuleViewSet, basename="matching-rule")
router.register("matching", MatchingOperationsViewSet, basename="matching")
router.register("match-candidates", MatchCandidateViewSet, basename="match-candidate")
router.register("merges", MergeViewSet, basename="merge")
router.register("dashboard", DashboardViewSet, basename="dashboard")
router.register("jobs", AsyncJobViewSet, basename="job")
router.register("configurations", MasterDataConfigurationViewSet, basename="configuration")

urlpatterns = [
    path("", include(router.urls)),
    path("health/live/", live, name="health-live"),
    path("health/ready/", ready, name="health-ready"),
]
