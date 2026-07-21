"""Governed, tenant-bound process-mining API v2 controllers."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db.models import Q, QuerySet
from django.http import FileResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api.profile import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id

from .health import get_module_health
from .models import BottleneckAnalysis, ConformanceCheck, EventExportJob, ProcessDiscoveryJob, ProcessModel, ProcessModelVersion
from .permissions import ActionAccessMixin
from .serializers import (
    BottleneckAnalysisDetailSerializer, BottleneckAnalysisListSerializer, BottleneckCreateSerializer,
    BottleneckFindingSerializer, CaseFitnessSerializer, ConformanceCreateSerializer, ConformanceDetailSerializer,
    ConformanceListSerializer, DeviationListSerializer, DiscoveryCreateSerializer, DiscoveryDetailSerializer,
    DiscoveryListSerializer, EventBatchIngestSerializer, EventExportCreateSerializer, EventExportDetailSerializer,
    EventExportListSerializer, IngestResultSerializer, ModuleHealthSerializer, ProcessEventDetailSerializer,
    ProcessEventListSerializer, ProcessModelCreateSerializer, ProcessModelDetailSerializer, ProcessModelListSerializer,
    ProcessModelUpdateSerializer, ProcessModelVersionDetailSerializer, ProcessModelVersionListSerializer,
    ProcessVariantSerializer, SetReferenceSerializer, TransitionActionSerializer,
)
from .services import BottleneckService, ConformanceService, EventLogService, ExportService, ProcessDiscoveryService, ProcessModelService


class TenantGovernedViewSet(GovernedAPIViewMixin, ActionAccessMixin, viewsets.GenericViewSet):
    """Bind the profile tenant before access evaluation and every service call."""

    def tenant_id(self) -> UUID:
        value = get_user_tenant_id(self.request.user)
        try:
            tenant = UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc
        self.request.tenant_id = tenant
        return tenant

    def actor_id(self) -> UUID:
        value = getattr(self.request.user, "id", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no valid actor.")
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return uuid5(NAMESPACE_URL, f"saraise:user:{value}")

    def paginated(self, queryset: Any, serializer: type, **context: object) -> Response:
        page = self.paginate_queryset(queryset)
        if page is None:
            raise RuntimeError("Governed pagination is required.")
        return self.get_paginated_response(serializer(page, many=True, context=context).data)


def _ordering(params: Any, allowed: set[str], default: str) -> str:
    value = str(params.get("ordering") or default)
    if value.lstrip("-") not in allowed:
        raise ValidationError({"ordering": "Unsupported ordering field."})
    return value


def _filter_fields(queryset: QuerySet[Any], params: Any, fields: tuple[str, ...]) -> QuerySet[Any]:
    for field in fields:
        if params.get(field) not in (None, ""):
            queryset = queryset.filter(**{field: params[field]})
    return queryset


class ProcessOverviewViewSet(mixins.ListModelMixin, TenantGovernedViewSet):
    action_permissions = {"list": "process_mining.event:read", "retrieve": "process_mining.event:read"}

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        rows = ProcessModelService().get_process_overview(self.tenant_id(), self.request.query_params)
        page = self.paginate_queryset(rows)
        if page is None:
            raise RuntimeError("Governed pagination is required.")
        return self.get_paginated_response(page)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        rows = ProcessModelService().get_process_overview(self.tenant_id(), {"process_name": self.kwargs["pk"]})
        if not rows:
            raise NotFound()
        return Response(rows[0])


class ProcessEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, TenantGovernedViewSet):
    service_class = EventLogService
    action_permissions = {"list": "process_mining.event:read", "retrieve": "process_mining.event:read", "create": "process_mining.event:ingest"}
    action_quotas = {"create": "process_mining.events_ingested"}

    def get_queryset(self) -> Any:
        if self.action == "list":
            return self.service_class().query_events(self.tenant_id(), self.request.query_params)
        return self.service_class().query_events(self.tenant_id(), {"process_name": self.request.query_params.get("process_name"), "start": self.request.query_params.get("start"), "end": self.request.query_params.get("end")})

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ProcessEventListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return Response(ProcessEventDetailSerializer(self.service_class().get_event(self.tenant_id(), self.kwargs["pk"])).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = EventBatchIngestSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = self.service_class().ingest_events(self.tenant_id(), self.actor_id(), data["source_module"], data["process_name"], data["events"])
        return Response(IngestResultSerializer(result).data, status=status.HTTP_201_CREATED)


class TransitionActionsMixin:
    """Expose the common cancel/retry actions without leaking other routes."""

    @action(detail=True, methods=["post"])
    def cancel(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists():
            raise NotFound()
        return self._transition("cancel")

    @action(detail=True, methods=["post"])
    def retry(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists():
            raise NotFound()
        return self._transition("retry")


class EventExportViewSet(TransitionActionsMixin, TenantGovernedViewSet):
    service_class = ExportService
    action_permissions = {"list": "process_mining.export:read", "retrieve": "process_mining.export:read", "create": "process_mining.export:create", "download": "process_mining.export:download", "cancel": "process_mining.export:cancel", "retry": "process_mining.export:create", "destroy": "process_mining.export:delete"}
    action_quotas = {"create": "process_mining.export_bytes", "retry": "process_mining.export_bytes"}

    def get_queryset(self) -> QuerySet[EventExportJob]:
        queryset = EventExportJob.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        queryset = _filter_fields(queryset, self.request.query_params, ("process_name", "format", "status"))
        if self.request.query_params.get("created_after"):
            queryset = queryset.filter(created_at__gte=self.request.query_params["created_after"])
        if self.request.query_params.get("created_before"):
            queryset = queryset.filter(created_at__lte=self.request.query_params["created_before"])
        return queryset.order_by(_ordering(self.request.query_params, {"created_at", "completed_at"}, "-created_at"), "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), EventExportListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(EventExportDetailSerializer(value).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = EventExportCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        value = self.service_class().request_export(self.tenant_id(), self.actor_id(), data["process_name"], data["format"], data.get("event_filter", {}), data["idempotency_key"])
        return Response(EventExportDetailSerializer(value).data, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        self.service_class().delete_export(self.tenant_id(), self.kwargs["pk"], self.actor_id())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def download(self, request: object, pk: str | None = None) -> FileResponse:
        del request, pk
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        record, stream = self.service_class().open_download(self.tenant_id(), self.kwargs["pk"])
        return FileResponse(stream, content_type=record.content_type, as_attachment=True, filename=f"{record.process_name}.{record.format}")

    def _transition(self, command: str) -> Response:
        serializer = TransitionActionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if command == "cancel": value = self.service_class().cancel_export(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data.get("reason", ""))
        else:
            if not data.get("idempotency_key"): raise ValidationError({"idempotency_key": "This field is required for retry."})
            value = self.service_class().retry_export(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data["idempotency_key"])
        return Response(EventExportDetailSerializer(value).data, status=status.HTTP_202_ACCEPTED if command == "retry" else 200)


class DiscoveryViewSet(TransitionActionsMixin, TenantGovernedViewSet):
    service_class = ProcessDiscoveryService
    action_permissions = {"list": "process_mining.discovery:read", "retrieve": "process_mining.discovery:read", "create": "process_mining.discovery:create", "model": "process_mining.discovery:read", "cancel": "process_mining.discovery:cancel", "retry": "process_mining.discovery:retry", "destroy": "process_mining.discovery:delete"}
    action_quotas = {"create": "process_mining.analysis_compute", "retry": "process_mining.analysis_compute"}

    def get_queryset(self) -> QuerySet[ProcessDiscoveryJob]:
        queryset = ProcessDiscoveryJob.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        queryset = _filter_fields(queryset, self.request.query_params, ("process_name", "algorithm", "status"))
        return queryset.order_by(_ordering(self.request.query_params, {"created_at", "completed_at"}, "-created_at"), "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), DiscoveryListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(DiscoveryDetailSerializer(value).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = DiscoveryCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        value = self.service_class().request_discovery(self.tenant_id(), self.actor_id(), data["process_name"], data["algorithm"], data.get("parameters", {}), data["idempotency_key"])
        return Response(DiscoveryDetailSerializer(value).data, status=status.HTTP_202_ACCEPTED)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        self.service_class().delete_discovery(self.tenant_id(), self.kwargs["pk"], self.actor_id()); return Response(status=204)

    @action(detail=True, methods=["get"])
    def model(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return Response(ProcessModelVersionDetailSerializer(self.service_class().get_discovered_model(self.tenant_id(), self.kwargs["pk"])).data)

    def _transition(self, command: str) -> Response:
        serializer = TransitionActionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        if command == "cancel": value = self.service_class().cancel_discovery(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data.get("reason", ""))
        else:
            if not data.get("idempotency_key"): raise ValidationError({"idempotency_key": "This field is required for retry."})
            value = self.service_class().retry_discovery(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data["idempotency_key"])
        return Response(DiscoveryDetailSerializer(value).data, status=202 if command == "retry" else 200)


class ProcessModelViewSet(TenantGovernedViewSet):
    service_class = ProcessModelService
    action_permissions = {"list": "process_mining.model:read", "retrieve": "process_mining.model:read", "create": "process_mining.model:create", "partial_update": "process_mining.model:update", "destroy": "process_mining.model:delete", "versions": "process_mining.model:read", "set_reference": "process_mining.model:set_reference"}

    def get_queryset(self) -> QuerySet[ProcessModel]:
        queryset = ProcessModel.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        queryset = _filter_fields(queryset, self.request.query_params, ("process_name", "source_kind"))
        if self.request.query_params.get("has_reference") is not None:
            expected = str(self.request.query_params["has_reference"]).lower() in {"1", "true"}; queryset = queryset.filter(reference_version_number__isnull=not expected)
        search = self.request.query_params.get("search")
        if search: queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return queryset.order_by("name", "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ProcessModelListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(ProcessModelDetailSerializer(value).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ProcessModelCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        value = self.service_class().create_imported_model(self.tenant_id(), self.actor_id(), data["name"], data["process_name"], data.get("description", ""), data["model_data"])
        return Response(ProcessModelDetailSerializer(value).data, status=201)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        current = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if current is None: raise NotFound()
        payload = {"name": current.name, "description": current.description, **dict(self.request.data)}
        serializer = ProcessModelUpdateSerializer(data=payload); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        return Response(ProcessModelDetailSerializer(self.service_class().update_model_metadata(self.tenant_id(), current.id, self.actor_id(), data["name"], data.get("description", ""))).data)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        self.service_class().soft_delete_model(self.tenant_id(), self.kwargs["pk"], self.actor_id()); return Response(status=204)

    @action(detail=True, methods=["get"])
    def versions(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        model = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if model is None: raise NotFound()
        return self.paginated(ProcessModelVersion.objects.for_tenant(self.tenant_id()).filter(process_model=model).order_by("-version"), ProcessModelVersionListSerializer)

    @action(detail=True, methods=["post"], url_path="set-reference")
    def set_reference(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        serializer = SetReferenceSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        value = self.service_class().set_reference_version(self.tenant_id(), self.kwargs["pk"], data["version_id"], self.actor_id(), data["transition_key"])
        return Response(ProcessModelVersionDetailSerializer(value).data)


class ProcessModelVersionViewSet(mixins.RetrieveModelMixin, TenantGovernedViewSet):
    action_permissions = {"retrieve": "process_mining.model:read"}
    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = ProcessModelVersion.objects.for_tenant(self.tenant_id()).filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(ProcessModelVersionDetailSerializer(value).data)


class ConformanceViewSet(TransitionActionsMixin, TenantGovernedViewSet):
    service_class = ConformanceService
    action_permissions = {"list": "process_mining.conformance:read", "retrieve": "process_mining.conformance:read", "create": "process_mining.conformance:create", "deviations": "process_mining.conformance:read", "fitness": "process_mining.conformance:read", "cancel": "process_mining.conformance:cancel", "retry": "process_mining.conformance:retry", "destroy": "process_mining.conformance:delete"}
    action_quotas = {"create": "process_mining.analysis_compute", "retry": "process_mining.analysis_compute"}

    def get_queryset(self) -> QuerySet[ConformanceCheck]:
        queryset = ConformanceCheck.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        queryset = _filter_fields(queryset, self.request.query_params, ("process_model_version", "status"))
        if self.request.query_params.get("fitness_min"): queryset = queryset.filter(fitness__gte=self.request.query_params["fitness_min"])
        if self.request.query_params.get("fitness_max"): queryset = queryset.filter(fitness__lte=self.request.query_params["fitness_max"])
        return queryset.order_by(_ordering(self.request.query_params, {"created_at", "completed_at", "fitness"}, "-created_at"), "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), ConformanceListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(ConformanceDetailSerializer(value).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = ConformanceCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        value = self.service_class().request_check(self.tenant_id(), self.actor_id(), data["process_model_version_id"], data.get("event_filter", {}), data["idempotency_key"])
        return Response(ConformanceDetailSerializer(value).data, status=202)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        self.service_class().delete_check(self.tenant_id(), self.kwargs["pk"], self.actor_id()); return Response(status=204)

    @action(detail=True, methods=["get"])
    def deviations(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self.paginated(self.service_class().list_deviations(self.tenant_id(), self.kwargs["pk"], self.request.query_params), DeviationListSerializer)

    @action(detail=True, methods=["get"])
    def fitness(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        check, cases = self.service_class().get_fitness(self.tenant_id(), self.kwargs["pk"])
        return Response({"check": ConformanceDetailSerializer(check).data, "cases": CaseFitnessSerializer(cases, many=True).data})

    def _transition(self, command: str) -> Response:
        serializer = TransitionActionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        if command == "cancel": value = self.service_class().cancel_check(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data.get("reason", ""))
        else:
            if not data.get("idempotency_key"): raise ValidationError({"idempotency_key": "This field is required for retry."})
            value = self.service_class().retry_check(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data["idempotency_key"])
        return Response(ConformanceDetailSerializer(value).data, status=202 if command == "retry" else 200)


class BottleneckViewSet(TransitionActionsMixin, TenantGovernedViewSet):
    service_class = BottleneckService
    action_permissions = {"list": "process_mining.bottleneck:read", "retrieve": "process_mining.bottleneck:read", "create": "process_mining.bottleneck:create", "findings": "process_mining.bottleneck:read", "variants": "process_mining.bottleneck:read", "cancel": "process_mining.bottleneck:cancel", "retry": "process_mining.bottleneck:retry", "destroy": "process_mining.bottleneck:delete"}
    action_quotas = {"create": "process_mining.analysis_compute", "retry": "process_mining.analysis_compute"}

    def get_queryset(self) -> QuerySet[BottleneckAnalysis]:
        queryset = BottleneckAnalysis.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)
        queryset = _filter_fields(queryset, self.request.query_params, ("process_name", "status"))
        return queryset.order_by(_ordering(self.request.query_params, {"created_at", "completed_at", "time_range_start"}, "-created_at"), "id")

    def list(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self.paginated(self.get_queryset(), BottleneckAnalysisListSerializer)

    def retrieve(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        value = self.get_queryset().filter(pk=self.kwargs["pk"]).first()
        if value is None: raise NotFound()
        return Response(BottleneckAnalysisDetailSerializer(value).data)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = BottleneckCreateSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        value = self.service_class().request_analysis(self.tenant_id(), self.actor_id(), data["process_name"], (data["time_range_start"], data["time_range_end"]), data["idempotency_key"])
        return Response(BottleneckAnalysisDetailSerializer(value).data, status=202)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        if not self.get_queryset().filter(pk=self.kwargs["pk"]).exists(): raise NotFound()
        self.service_class().delete_analysis(self.tenant_id(), self.kwargs["pk"], self.actor_id()); return Response(status=204)

    @action(detail=True, methods=["get"])
    def findings(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self.paginated(self.service_class().get_findings(self.tenant_id(), self.kwargs["pk"], self.request.query_params), BottleneckFindingSerializer)

    @action(detail=True, methods=["get"])
    def variants(self, request: object, pk: str | None = None) -> Response:
        del request, pk
        return self.paginated(self.service_class().get_variants(self.tenant_id(), self.kwargs["pk"], self.request.query_params), ProcessVariantSerializer)

    def _transition(self, command: str) -> Response:
        serializer = TransitionActionSerializer(data=self.request.data); serializer.is_valid(raise_exception=True); data = serializer.validated_data
        if command == "cancel": value = self.service_class().cancel_analysis(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data.get("reason", ""))
        else:
            if not data.get("idempotency_key"): raise ValidationError({"idempotency_key": "This field is required for retry."})
            value = self.service_class().retry_analysis(self.tenant_id(), self.kwargs["pk"], self.actor_id(), data["transition_key"], data["idempotency_key"])
        return Response(BottleneckAnalysisDetailSerializer(value).data, status=202 if command == "retry" else 200)


class ModuleHealthAPIView(GovernedAPIViewMixin, ActionAccessMixin, APIView):
    action = "health"
    action_permissions = {"health": "process_mining.health:read"}

    def get(self, request: object) -> Response:
        del request
        report = get_module_health()
        return Response(ModuleHealthSerializer(report.payload).data, status=report.status_code)


__all__ = ["BottleneckViewSet", "ConformanceViewSet", "DiscoveryViewSet", "EventExportViewSet", "ModuleHealthAPIView", "ProcessEventViewSet", "ProcessModelVersionViewSet", "ProcessModelViewSet", "ProcessOverviewViewSet"]
