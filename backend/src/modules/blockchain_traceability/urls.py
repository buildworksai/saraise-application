"""API v2 routes for the blockchain traceability domain."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    AuthenticityCredentialViewSet,
    BlockchainTraceabilityHealthView,
    ComplianceEvidenceViewSet,
    LedgerAnchorViewSet,
    LedgerNetworkViewSet,
    TraceabilityAssetViewSet,
    TraceabilityEventViewSet,
    VerificationAttemptViewSet,
)

app_name = "blockchain_traceability"

router = DefaultRouter()
router.register("networks", LedgerNetworkViewSet, basename="network")
router.register("assets", TraceabilityAssetViewSet, basename="asset")
router.register("events", TraceabilityEventViewSet, basename="event")
router.register("anchors", LedgerAnchorViewSet, basename="anchor")
router.register("credentials", AuthenticityCredentialViewSet, basename="credential")
router.register("compliance-evidence", ComplianceEvidenceViewSet, basename="compliance-evidence")
router.register("verification-attempts", VerificationAttemptViewSet, basename="verification-attempt")

urlpatterns = [
    path("health/", BlockchainTraceabilityHealthView.as_view(), name="health"),
    path("", include(router.urls)),
]
