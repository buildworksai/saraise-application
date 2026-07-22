"""Routes for the governed compliance-management API v2."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ActivityViewSet, AssessmentViewSet, ConfigurationViewSet, DashboardViewSet,
    EvidenceLinkViewSet, EvidenceViewSet, FrameworkViewSet, GapViewSet,
    JobViewSet, MappingViewSet, PolicyViewSet, RequirementViewSet,
)

router = DefaultRouter()
router.register("frameworks", FrameworkViewSet, basename="compliance-framework")
router.register("requirements", RequirementViewSet, basename="compliance-requirement")
router.register("policies", PolicyViewSet, basename="compliance-policy")
router.register("mappings", MappingViewSet, basename="compliance-mapping")
router.register("gaps", GapViewSet, basename="compliance-gap")
router.register("assessments", AssessmentViewSet, basename="compliance-assessment")
router.register("evidence", EvidenceViewSet, basename="compliance-evidence")
router.register("evidence-links", EvidenceLinkViewSet, basename="compliance-evidence-link")
router.register("configuration", ConfigurationViewSet, basename="compliance-configuration")
router.register("activity", ActivityViewSet, basename="compliance-activity")
router.register("dashboard", DashboardViewSet, basename="compliance-dashboard")
router.register("jobs", JobViewSet, basename="compliance-job")

urlpatterns = [path("", include(router.urls))]
