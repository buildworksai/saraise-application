"""URL routing for the Business Intelligence v2 module."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    DashboardViewSet,
    DatasetViewSet,
    ExecutionViewSet,
    HealthView,
    QueryViewSet,
    ReportViewSet,
    ShareCollectionView,
    ShareDetailView,
    WidgetCollectionView,
    WidgetDetailView,
    WidgetReorderView,
)

app_name = "business_intelligence"
router = DefaultRouter()
router.register("datasets", DatasetViewSet, basename="dataset")
router.register("queries", QueryViewSet, basename="query")
router.register("reports", ReportViewSet, basename="report")
router.register("dashboards", DashboardViewSet, basename="dashboard")
router.register("executions", ExecutionViewSet, basename="execution")

urlpatterns = [
    path("dashboards/<uuid:dashboard_id>/widgets/", WidgetCollectionView.as_view(), name="dashboard-widgets"),
    path(
        "dashboards/<uuid:dashboard_id>/widgets/reorder/", WidgetReorderView.as_view(), name="dashboard-widgets-reorder"
    ),
    path(
        "dashboards/<uuid:dashboard_id>/widgets/<uuid:widget_id>/",
        WidgetDetailView.as_view(),
        name="dashboard-widget-detail",
    ),
    path("dashboards/<uuid:dashboard_id>/shares/", ShareCollectionView.as_view(), name="dashboard-shares"),
    path(
        "dashboards/<uuid:dashboard_id>/shares/<uuid:share_id>/",
        ShareDetailView.as_view(),
        name="dashboard-share-detail",
    ),
    path("health/", HealthView.as_view(), name="health"),
    path("", include(router.urls)),
]
