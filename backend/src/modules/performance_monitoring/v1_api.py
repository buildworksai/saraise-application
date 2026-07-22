"""Compatibility adapters for the legacy performance-monitoring API v1."""

from __future__ import annotations

from collections.abc import Callable

from rest_framework.pagination import PageNumberPagination
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import exception_handler

from .api import (
    AlertRuleViewSet,
    AlertViewSet,
    ComplianceViewSet,
    ConfigurationViewSet,
    DashboardViewSet,
    EnvironmentViewSet,
    ExtensionViewSet,
    LogViewSet,
    MetricDataPointViewSet,
    MetricDefinitionViewSet,
    MetricViewSet,
    ReportViewSet,
    ServiceViewSet,
    SLAViewSet,
    SLOViewSet,
    TelemetrySourceViewSet,
    TraceViewSet,
)


class V1PageNumberPagination(PageNumberPagination):
    """Retain the bounded DRF collection contract published by API v1."""

    page_size_query_param = "page_size"

    def paginate_queryset(self, queryset, request, view=None):
        from .services import CapabilityUnavailableError, ConfigurationService

        profile = getattr(request.user, "profile", None)
        tenant_id = getattr(profile, "tenant_id", None)
        if tenant_id is None:
            raise CapabilityUnavailableError("Tenant pagination policy is unavailable.")
        policy = ConfigurationService().setting(tenant_id, "pagination")
        self.page_size = int(policy["default_page_size"])
        self.max_page_size = int(policy["max_page_size"])
        return super().paginate_queryset(queryset, request, view)


class V1APIViewMixin:
    """Restore raw JSON, DRF errors, and ``results`` pagination for v1."""

    renderer_classes = (JSONRenderer,)
    pagination_class = V1PageNumberPagination

    def get_exception_handler(self) -> Callable[..., Response | None]:
        return exception_handler


class V1TelemetrySourceViewSet(V1APIViewMixin, TelemetrySourceViewSet):
    pass


class V1EnvironmentViewSet(V1APIViewMixin, EnvironmentViewSet):
    pass


class V1ServiceViewSet(V1APIViewMixin, ServiceViewSet):
    pass


class V1MetricDefinitionViewSet(V1APIViewMixin, MetricDefinitionViewSet):
    pass


class V1MetricViewSet(V1APIViewMixin, MetricViewSet):
    pass


class V1MetricDataPointViewSet(V1APIViewMixin, MetricDataPointViewSet):
    pass


class V1LogViewSet(V1APIViewMixin, LogViewSet):
    pass


class V1TraceViewSet(V1APIViewMixin, TraceViewSet):
    pass


class V1DashboardViewSet(V1APIViewMixin, DashboardViewSet):
    pass


class V1AlertRuleViewSet(V1APIViewMixin, AlertRuleViewSet):
    pass


class V1AlertViewSet(V1APIViewMixin, AlertViewSet):
    pass


class V1SLAViewSet(V1APIViewMixin, SLAViewSet):
    pass


class V1SLOViewSet(V1APIViewMixin, SLOViewSet):
    pass


class V1ComplianceViewSet(V1APIViewMixin, ComplianceViewSet):
    pass


class V1ConfigurationViewSet(V1APIViewMixin, ConfigurationViewSet):
    pass


class V1ReportViewSet(V1APIViewMixin, ReportViewSet):
    pass


class V1ExtensionViewSet(V1APIViewMixin, ExtensionViewSet):
    pass
