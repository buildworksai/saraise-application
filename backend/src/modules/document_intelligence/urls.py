"""API v2 routes for document intelligence; no legacy resource surface."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ClassifierModelVersionViewSet,
    ClassifierTrainingJobViewSet,
    DocumentClassificationScoreViewSet,
    DocumentClassificationViewSet,
    DocumentExtractionPageViewSet,
    DocumentExtractionViewSet,
    ExtractionTemplateViewSet,
    ExtractionTemplateZoneViewSet,
    ModuleHealthAPIView,
)

app_name = "document_intelligence"

router = DefaultRouter()
router.register("extractions", DocumentExtractionViewSet, basename="extraction")
router.register("extraction-pages", DocumentExtractionPageViewSet, basename="extraction-page")
router.register("classifications", DocumentClassificationViewSet, basename="classification")
router.register("classification-scores", DocumentClassificationScoreViewSet, basename="classification-score")
router.register("templates", ExtractionTemplateViewSet, basename="template")
router.register("template-zones", ExtractionTemplateZoneViewSet, basename="template-zone")
router.register("training-jobs", ClassifierTrainingJobViewSet, basename="training-job")
router.register("model-versions", ClassifierModelVersionViewSet, basename="model-version")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", ModuleHealthAPIView.as_view(), name="health"),
]
