"""Governed, tenant-isolated performance-monitoring API."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet

from .models import (
    Alert,
    AlertNotificationOutcome,
    AlertRule,
    Dashboard,
    ErrorBudgetSnapshot,
    LogEntry,
    Metric,
    MonitoredService,
    MonitoringEnvironment,
    MonitoringExtension,
    ServiceLevelObjective,
    SLAComplianceRecord,
    SLADefinition,
    SLAReport,
    Span,
    TelemetrySource,
    Trace,
)
from .serializers import (
    AlertAcknowledgeSerializer,
    AlertResolveSerializer,
    AlertRuleCreateSerializer,
    AlertRuleDetailSerializer,
    AlertRuleListSerializer,
    AlertRuleUpdateSerializer,
    AlertSerializer,
    ComplianceQuerySerializer,
    ComplianceSerializer,
    DashboardSerializer,
    EnvironmentSerializer,
    ErrorBudgetSerializer,
    ExtensionSerializer,
    LogEntrySerializer,
    LogIngestSerializer,
    MetricBatchSerializer,
    MetricDataPointSerializer,
    MetricDefinitionCreateSerializer,
    MetricDefinitionDetailSerializer,
    MetricDefinitionListSerializer,
    MetricQuerySerializer,
    MetricRecordSerializer,
    MetricSummaryQuerySerializer,
    ServiceSerializer,
    SLADefinitionCreateSerializer,
    SLADefinitionSerializer,
    SLADefinitionUpdateSerializer,
    SLAReportCreateSerializer,
    SLAReportSerializer,
    SLOSerializer,
    SpanSerializer,
    TelemetrySourceCreateSerializer,
    TelemetrySourceDetailSerializer,
    TelemetrySourceListSerializer,
    TelemetrySourceUpdateSerializer,
    TraceIngestSerializer,
    TraceSerializer,
)
from .services import (
    AlertingService,
    MetricsCollectionService,
    MonitoringCatalogService,
    MonitoringError,
    SLAMonitoringService,
    TelemetryService,
)


class CsrfSessionAuthentication(SessionAuthentication):
    """Strict session authentication with an explicit 401 challenge."""

    def authenticate_header(self, request: Request) -> str:
        del request
        return "Session"


def _actor_id(request: Request) -> UUID:
    value = getattr(request.user, "id", None)
    if isinstance(value, UUID):
        return value
    return uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}")


class GovernedMonitoringViewSet(GovernedAPIViewMixin, TenantScopedModelViewSet):
    authentication_classes = (CsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    filter_backends = (SearchFilter, OrderingFilter)
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    http_method_names = ("get", "post", "patch", "delete", "head", "options")
    access_map: Mapping[str, str] = {}

    def check_permissions(self, request: Request) -> None:
        tenant_id = self._get_tenant_id()
        if tenant_id is not None:
            request.tenant_id = tenant_id  # type: ignore[attr-defined]
        permission = self.access_map.get(getattr(self, "action", ""))
        self.required_permission = permission or ""
        self.required_entitlement = permission or ""
        self.quota_resource = permission or ""
        self.quota_cost = 1
        super().check_permissions(request)

    def handle_exception(self, exc: Exception) -> Response:
        if isinstance(exc, MonitoringError):
            return Response(
                {"error": {"code": exc.code, "message": exc.public_message, "details": exc.details}},
                status=exc.http_status,
            )
        if isinstance(exc, DjangoValidationError):
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Domain validation failed.",
                        "details": getattr(exc, "message_dict", {}),
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)

    def tenant_id(self) -> UUID:
        return self._require_tenant_id()


READ = "performance_monitoring.telemetry:read"
INGEST = "performance_monitoring.telemetry:ingest"
CONFIGURE = "performance_monitoring.telemetry:configure"
ALERT_READ = "performance_monitoring.alert:read"
ALERT_MANAGE = "performance_monitoring.alert:manage"
ALERT_RESPOND = "performance_monitoring.alert:respond"
SLA_READ = "performance_monitoring.sla:read"
SLA_MANAGE = "performance_monitoring.sla:manage"
REPORT = "performance_monitoring.report:generate"
EXTENSION_READ = "performance_monitoring.extension:read"


class CatalogViewSet(GovernedMonitoringViewSet):
    model: type[Any]
    access_map = {
        "list": READ,
        "retrieve": READ,
        "create": CONFIGURE,
        "partial_update": CONFIGURE,
        "destroy": CONFIGURE,
    }

    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(is_deleted=False)

    def create(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = MonitoringCatalogService().create(
            self.tenant_id(), self.model, serializer.validated_data, created_by=_actor_id(request)
        )
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        instance = MonitoringCatalogService().update(self.tenant_id(), self.model, pk, serializer.validated_data)
        return Response(self.get_serializer(instance).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        MonitoringCatalogService().delete(self.tenant_id(), self.model, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelemetrySourceViewSet(CatalogViewSet):
    queryset = TelemetrySource.objects.all()
    model = TelemetrySource
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at", "last_seen_at", "status")
    ordering = ("name",)

    def get_serializer_class(self):
        if self.action == "list":
            return TelemetrySourceListSerializer
        if self.action == "create":
            return TelemetrySourceCreateSerializer
        if self.action == "partial_update":
            return TelemetrySourceUpdateSerializer
        return TelemetrySourceDetailSerializer


class EnvironmentViewSet(CatalogViewSet):
    queryset = MonitoringEnvironment.objects.all()
    model = MonitoringEnvironment
    serializer_class = EnvironmentSerializer
    search_fields = ("name", "slug", "kind")
    ordering_fields = ("name", "kind", "created_at")


class ServiceViewSet(CatalogViewSet):
    queryset = MonitoredService.objects.select_related("environment", "source")
    model = MonitoredService
    serializer_class = ServiceSerializer
    search_fields = ("name", "slug", "namespace", "owner")
    ordering_fields = ("name", "status", "last_seen_at", "created_at")


class DashboardViewSet(CatalogViewSet):
    queryset = Dashboard.objects.all()
    model = Dashboard
    serializer_class = DashboardSerializer
    search_fields = ("name", "description")
    ordering_fields = ("name", "created_at", "updated_at")


class SLOViewSet(CatalogViewSet):
    queryset = ServiceLevelObjective.objects.select_related("service", "indicator_metric")
    model = ServiceLevelObjective
    serializer_class = SLOSerializer
    access_map = {
        "list": SLA_READ,
        "retrieve": SLA_READ,
        "create": SLA_MANAGE,
        "partial_update": SLA_MANAGE,
        "destroy": SLA_MANAGE,
        "budget": SLA_READ,
    }

    @action(detail=True, methods=("get",), url_path="budget")
    def budget(self, request: Request, pk: str | None = None) -> Response:
        del request
        snapshot = (
            ErrorBudgetSnapshot.objects.for_tenant(self.tenant_id()).filter(slo_id=pk).order_by("-period_end").first()
        )
        if snapshot is None:
            raise MonitoringError("No error-budget evaluation exists for this SLO.")
        return Response(ErrorBudgetSerializer(snapshot).data)


class MetricDefinitionViewSet(GovernedMonitoringViewSet):
    queryset = Metric.objects.all()
    access_map = {"list": READ, "retrieve": READ, "create": CONFIGURE, "destroy": CONFIGURE}
    search_fields = ("metric_name", "display_name", "description", "namespace")
    ordering_fields = ("metric_name", "metric_type", "created_at", "updated_at")
    ordering = ("metric_name",)

    def get_queryset(self) -> QuerySet[Metric]:
        queryset = super().get_queryset().filter(is_deleted=False)
        metric_type = self.request.query_params.get("metric_type")
        active = self.request.query_params.get("is_active")
        if metric_type:
            queryset = queryset.filter(metric_type=metric_type)
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return MetricDefinitionListSerializer
        if self.action == "create":
            return MetricDefinitionCreateSerializer
        return MetricDefinitionDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = MetricDefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        metric = MetricsCollectionService().define_metric(
            self.tenant_id(),
            values.pop("metric_name"),
            values.pop("metric_type"),
            created_by=_actor_id(request),
            **values,
        )
        return Response(MetricDefinitionDetailSerializer(metric).data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        metric = self.get_object()
        metric.is_active = False
        metric.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MetricViewSet(MetricDefinitionViewSet):
    """Canonical API: list definitions, POST ingestion, query and summary."""

    access_map = {"list": READ, "retrieve": READ, "create": INGEST, "batch": INGEST, "query": READ, "summary": READ}

    def get_serializer_class(self):
        if self.action == "create":
            return MetricRecordSerializer
        return super().get_serializer_class()

    def create(self, request: Request) -> Response:
        serializer = MetricRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        point = MetricsCollectionService().record_metric(
            self.tenant_id(), values.pop("metric_name"), values.pop("value"), created_by=_actor_id(request), **values
        )
        return Response(MetricDataPointSerializer(point).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=("post",), url_path="batch")
    def batch(self, request: Request) -> Response:
        serializer = MetricBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = MetricsCollectionService().record_metrics_batch(
            self.tenant_id(),
            serializer.validated_data["data_points"],
            atomic=serializer.validated_data["atomic"],
            created_by=_actor_id(request),
        )
        return Response(
            {"accepted": result.accepted, "rejected": result.rejected, "errors": result.errors},
            status=status.HTTP_201_CREATED if result.rejected == 0 else status.HTTP_207_MULTI_STATUS,
        )

    @action(detail=False, methods=("get",), url_path="query")
    def query(self, request: Request) -> Response:
        serializer = MetricQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        result = MetricsCollectionService().query_metrics(self.tenant_id(), values.pop("metric_name"), **values)
        return Response(
            {
                "metric_name": result.metric_name,
                "aggregation": result.aggregation,
                "interval": result.interval,
                "data": [{"timestamp": item.timestamp, "value": item.value} for item in result.data],
            }
        )

    @action(detail=False, methods=("get",), url_path="summary")
    def summary(self, request: Request) -> Response:
        serializer = MetricSummaryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        names = [name.strip() for name in serializer.validated_data["metric_names"].split(",") if name.strip()]
        summaries = MetricsCollectionService().get_metric_summary(
            self.tenant_id(), names, serializer.validated_data["period"]
        )
        return Response(
            {
                "summaries": [
                    {
                        "metric_name": item.metric_name,
                        "period": item.period,
                        "min": item.minimum,
                        "max": item.maximum,
                        "avg": item.average,
                        "count": item.count,
                        "p50": item.p50,
                        "p95": item.p95,
                        "p99": item.p99,
                    }
                    for item in summaries
                ]
            }
        )


class LogViewSet(GovernedMonitoringViewSet):
    queryset = LogEntry.objects.select_related("source", "service", "environment")
    access_map = {"list": READ, "retrieve": READ, "create": INGEST}
    search_fields = ("message", "correlation_id", "trace_id")
    ordering_fields = ("timestamp", "level", "created_at")
    ordering = ("-timestamp",)
    http_method_names = ("get", "post", "head", "options")

    def get_serializer_class(self):
        return LogIngestSerializer if self.action == "create" else LogEntrySerializer

    def get_queryset(self) -> QuerySet[LogEntry]:
        queryset = super().get_queryset()
        for parameter, field in (
            ("level", "level"),
            ("service_id", "service_id"),
            ("trace_id", "trace_id"),
            ("correlation_id", "correlation_id"),
        ):
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset

    def create(self, request: Request) -> Response:
        serializer = LogIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = TelemetryService().ingest_log(self.tenant_id(), serializer.validated_data)
        return Response(LogEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class TraceViewSet(GovernedMonitoringViewSet):
    queryset = Trace.objects.select_related("source", "service", "environment")
    access_map = {"list": READ, "retrieve": READ, "create": INGEST, "spans": READ}
    search_fields = ("trace_id", "name", "service__name")
    ordering_fields = ("started_at", "duration_ms", "status", "created_at")
    ordering = ("-started_at",)
    http_method_names = ("get", "post", "head", "options")

    def get_serializer_class(self):
        return TraceIngestSerializer if self.action == "create" else TraceSerializer

    def create(self, request: Request) -> Response:
        serializer = TraceIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trace = TelemetryService().ingest_trace(self.tenant_id(), serializer.validated_data)
        return Response(TraceSerializer(trace).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=("get",), url_path="spans")
    def spans(self, request: Request, pk: str | None = None) -> Response:
        del request
        trace = self.get_object()
        queryset = Span.objects.for_tenant(self.tenant_id()).filter(trace=trace).order_by("started_at")
        page = self.paginate_queryset(queryset)
        serializer = SpanSerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)


class AlertRuleViewSet(GovernedMonitoringViewSet):
    queryset = AlertRule.objects.select_related("metric")
    access_map = {
        "list": ALERT_READ,
        "retrieve": ALERT_READ,
        "create": ALERT_MANAGE,
        "partial_update": ALERT_MANAGE,
        "destroy": ALERT_MANAGE,
        "evaluate": ALERT_MANAGE,
    }
    search_fields = ("name", "metric_name", "description")
    ordering_fields = ("name", "severity", "created_at", "last_evaluated_at")
    ordering = ("name",)

    def get_queryset(self) -> QuerySet[AlertRule]:
        queryset = super().get_queryset().filter(is_deleted=False)
        for parameter in ("metric_name", "severity"):
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{parameter: value})
        active = self.request.query_params.get("is_active")
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return AlertRuleListSerializer
        if self.action == "create":
            return AlertRuleCreateSerializer
        if self.action == "partial_update":
            return AlertRuleUpdateSerializer
        return AlertRuleDetailSerializer

    def create(self, request: Request) -> Response:
        serializer = AlertRuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        rule = AlertingService().create_alert_rule(
            self.tenant_id(),
            values.pop("metric_name"),
            values.pop("condition"),
            values.pop("threshold", None),
            values.pop("action"),
            created_by=_actor_id(request),
            **values,
        )
        return Response(AlertRuleDetailSerializer(rule).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        instance = self.get_object()
        serializer = AlertRuleUpdateSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        rule = AlertingService().update_alert_rule(self.tenant_id(), pk, **serializer.validated_data)
        return Response(AlertRuleDetailSerializer(rule).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        AlertingService().delete_alert_rule(self.tenant_id(), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",), url_path="evaluate")
    def evaluate(self, request: Request, pk: str | None = None) -> Response:
        del request
        alert = AlertingService().evaluate_alert_rule(self.tenant_id(), pk)
        return Response({"alert": AlertSerializer(alert).data if alert else None})


class AlertViewSet(GovernedMonitoringViewSet):
    queryset = Alert.objects.select_related("alert_rule", "metric")
    access_map = {
        "list": ALERT_READ,
        "retrieve": ALERT_READ,
        "evaluate": ALERT_MANAGE,
        "acknowledge": ALERT_RESPOND,
        "resolve": ALERT_RESPOND,
    }
    serializer_class = AlertSerializer
    search_fields = ("title", "description", "metric_name")
    ordering_fields = ("triggered_at", "severity", "status", "last_observed_at")
    ordering = ("-triggered_at",)
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self) -> QuerySet[Alert]:
        queryset = super().get_queryset().filter(is_deleted=False)
        for parameter in ("status", "severity", "metric_name"):
            value = self.request.query_params.get(parameter)
            if value:
                queryset = queryset.filter(**{parameter: value})
        return queryset

    @action(detail=False, methods=("post",), url_path="evaluate")
    def evaluate(self, request: Request) -> Response:
        del request
        alerts = AlertingService().evaluate_alerts(self.tenant_id())
        failed = (
            AlertNotificationOutcome.objects.for_tenant(self.tenant_id())
            .filter(alert__in=alerts, state="failed")
            .exists()
        )
        payload = {
            "fired_alerts": AlertSerializer(alerts, many=True).data,
            "delivery_status": "failed" if failed else "submitted",
        }
        return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE if failed else status.HTTP_200_OK)

    @action(detail=True, methods=("post",), url_path="acknowledge")
    def acknowledge(self, request: Request, pk: str | None = None) -> Response:
        serializer = AlertAcknowledgeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = AlertingService().acknowledge_alert(self.tenant_id(), pk, _actor_id(request))
        return Response(AlertSerializer(alert).data)

    @action(detail=True, methods=("post",), url_path="resolve")
    def resolve(self, request: Request, pk: str | None = None) -> Response:
        serializer = AlertResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        alert = AlertingService().resolve_alert(
            self.tenant_id(), pk, resolved_by=_actor_id(request), note=serializer.validated_data.get("note", "")
        )
        return Response(AlertSerializer(alert).data)


class SLAViewSet(GovernedMonitoringViewSet):
    queryset = SLADefinition.objects.select_related("metric", "service", "previous_version")
    access_map = {
        "list": SLA_READ,
        "retrieve": SLA_READ,
        "create": SLA_MANAGE,
        "partial_update": SLA_MANAGE,
        "destroy": SLA_MANAGE,
        "compliance": SLA_READ,
        "reports": REPORT,
    }
    search_fields = ("name", "service_name", "metric_name", "description")
    ordering_fields = ("service_name", "metric_name", "created_at", "effective_from", "version")
    ordering = ("service_name", "metric_name", "-version")

    def get_queryset(self) -> QuerySet[SLADefinition]:
        queryset = super().get_queryset().filter(is_deleted=False)
        service = self.request.query_params.get("service_name")
        if service:
            queryset = queryset.filter(service_name__icontains=service)
        active = self.request.query_params.get("is_active")
        if active in {"true", "false"}:
            queryset = queryset.filter(is_active=active == "true")
        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return SLADefinitionCreateSerializer
        if self.action == "partial_update":
            return SLADefinitionUpdateSerializer
        return SLADefinitionSerializer

    def create(self, request: Request) -> Response:
        serializer = SLADefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        sla = SLAMonitoringService().define_sla(
            self.tenant_id(),
            values.pop("service_name"),
            values.pop("metric_name"),
            values.pop("target"),
            values.pop("window"),
            created_by=_actor_id(request),
            **values,
        )
        return Response(SLADefinitionSerializer(sla).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        serializer = SLADefinitionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        sla = SLAMonitoringService().update_sla(self.tenant_id(), pk, **serializer.validated_data)
        return Response(SLADefinitionSerializer(sla).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        del request
        SLAMonitoringService().delete_sla(self.tenant_id(), pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("get",), url_path="compliance")
    def compliance(self, request: Request, pk: str | None = None) -> Response:
        serializer = ComplianceQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        period = values.pop("period", "current")
        record = SLAMonitoringService().check_sla_compliance(
            self.tenant_id(), pk, period=None if period == "current" else period, **values
        )
        return Response(ComplianceSerializer(record).data)

    @action(detail=False, methods=("post",), url_path="reports")
    def reports(self, request: Request) -> Response:
        serializer = SLAReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = SLAMonitoringService().generate_sla_report(
            self.tenant_id(),
            serializer.validated_data["period"],
            output_format=serializer.validated_data["format"],
            created_by=_actor_id(request),
        )
        return Response(SLAReportSerializer(report).data, status=status.HTTP_201_CREATED)


class ComplianceViewSet(GovernedAPIViewMixin, TenantScopedReadOnlyModelViewSet):
    queryset = SLAComplianceRecord.objects.select_related("sla")
    serializer_class = ComplianceSerializer
    authentication_classes = (CsrfSessionAuthentication,)
    permission_classes = (IsAuthenticated, RequiresAccess)
    pagination_class = GovernedPageNumberPagination
    required_permission = SLA_READ
    required_entitlement = SLA_READ
    quota_resource = SLA_READ

    def check_permissions(self, request: Request) -> None:
        tenant_id = self._get_tenant_id()
        if tenant_id is not None:
            request.tenant_id = tenant_id  # type: ignore[attr-defined]
        super().check_permissions(request)


class ReportViewSet(ComplianceViewSet):
    queryset = SLAReport.objects.all()
    serializer_class = SLAReportSerializer
    required_permission = SLA_READ


class ExtensionViewSet(ComplianceViewSet):
    queryset = MonitoringExtension.objects.filter(is_active=True, is_deleted=False)
    serializer_class = ExtensionSerializer
    required_permission = EXTENSION_READ
