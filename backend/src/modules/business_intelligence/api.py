"""Governed synchronous DRF API v2 for Business Intelligence."""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api import GovernedAPIViewMixin
from src.core.auth_utils import get_user_tenant_id

from .health import module_health
from .models import Dashboard, DashboardShare, DashboardWidget, QueryDefinition, QueryExecution, Report
from .permissions import BIActionPermission, StrictSessionAuthentication
from .serializers import (
    DashboardCreateSerializer,
    DashboardDetailSerializer,
    DashboardListSerializer,
    DashboardUpdateSerializer,
    DatasetDetailSerializer,
    DatasetListSerializer,
    ExecutionDetailSerializer,
    ExecutionListSerializer,
    ExecutionRequestSerializer,
    ExecutionResultSerializer,
    HealthResponseSerializer,
    QueryCreateSerializer,
    QueryDetailSerializer,
    QueryListSerializer,
    QueryTransitionSerializer,
    QueryUpdateSerializer,
    QueryValidateSerializer,
    ReportCreateSerializer,
    ReportDetailSerializer,
    ReportListSerializer,
    ReportUpdateSerializer,
    ShareCreateSerializer,
    ShareListSerializer,
    ShareUpdateSerializer,
    WidgetCreateSerializer,
    WidgetDetailSerializer,
    WidgetListSerializer,
    WidgetReorderSerializer,
    WidgetUpdateSerializer,
)
from .services import DashboardService, DatasetCatalogService, ExecutionService, QueryService, ReportService


class _BIViewMixin(GovernedAPIViewMixin):
    authentication_classes = (StrictSessionAuthentication,)
    permission_classes = (BIActionPermission,)

    @property
    def tenant_id(self) -> uuid.UUID:
        raw = getattr(self.request, "tenant_id", None) or get_user_tenant_id(self.request.user)
        try:
            return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
        except (ValueError, TypeError, AttributeError) as exc:
            raise NotFound() from exc

    @property
    def actor_id(self) -> str:
        return str(getattr(self.request.user, "pk", getattr(self.request.user, "id", "")))

    @property
    def correlation_id(self) -> str:
        return str(getattr(self.request, "correlation_id", ""))

    def idempotency_key(self) -> str:
        value = self.request.headers.get("Idempotency-Key", "").strip()
        if not value or len(value) > 255:
            raise ValidationError({"Idempotency-Key": "A key between 1 and 255 characters is required."})
        return value

    def update(self, request: object, *args: Any, **kwargs: Any) -> Response:
        raise MethodNotAllowed("PUT")


class DatasetViewSet(_BIViewMixin, viewsets.GenericViewSet):
    permission_map = {"list": "bi.dataset:read", "retrieve": "bi.dataset:read"}
    lookup_field = "pk"

    def list(self, request: object) -> Response:
        locked_value = request.query_params.get("locked", request.query_params.get("include_locked"))
        if locked_value not in {None, "", "true", "false", "1", "0"}:
            raise ValidationError({"locked": "Use true or false."})
        include_locked = locked_value in {"true", "1"}
        values = DatasetCatalogService.list_datasets(self.tenant_id, request.user, include_locked)
        search, module = request.query_params.get("search", "").lower(), request.query_params.get("module")
        values = [
            item
            for item in values
            if (
                not search or search in str(item.get("label", "")).lower() or search in str(item.get("key", "")).lower()
            )
            and (not module or item.get("module") == module)
        ]
        ordering = request.query_params.get("ordering", "label")
        descending, field = ordering.startswith("-"), ordering.lstrip("-")
        if field not in {"label", "key"}:
            raise ValidationError({"ordering": "Use label or key."})
        values.sort(key=lambda item: str(item.get(field, "")).lower(), reverse=descending)
        page = self.paginate_queryset(values)
        serializer = DatasetListSerializer(page, many=True)  # noqa: F405
        return self.get_paginated_response(serializer.data)

    def retrieve(self, request: object, pk: str | None = None) -> Response:
        return Response(
            DatasetDetailSerializer(DatasetCatalogService.get_dataset(self.tenant_id, request.user, str(pk))).data
        )  # noqa: F405


class _DefinitionViewSet(_BIViewMixin, viewsets.GenericViewSet):
    service: Any
    model: Any
    list_serializer: Any
    detail_serializer: Any
    create_serializer: Any
    update_serializer: Any
    search_fields: tuple[str, ...]
    ordering_fields: tuple[str, ...]

    def get_queryset(self):
        queryset = self.model.objects.for_tenant(self.tenant_id).filter(deleted_at__isnull=True)
        search = self.request.query_params.get("search")
        if search:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)
        for field in ("state", "dataset_key", "created_by_id", "report_type"):
            if field in self.request.query_params and any(item.name == field for item in self.model._meta.fields):
                if field == "state" and self.request.query_params[field] not in {"draft", "published", "archived"}:
                    raise ValidationError({field: "Use draft, published, or archived."})
                if field == "report_type" and self.request.query_params[field] not in {
                    "table",
                    "pivot",
                    "chart",
                    "kpi",
                }:
                    raise ValidationError({field: "Use table, pivot, chart, or kpi."})
                queryset = queryset.filter(**{field: self.request.query_params[field]})
        ordering = self.request.query_params.get("ordering", "-updated_at")
        if ordering.lstrip("-") not in self.ordering_fields:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(ordering, "id")

    def list(self, request: object) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(self.list_serializer(page, many=True).data)

    def retrieve(self, request: object, pk: object = None) -> Response:
        obj = self.get_queryset().filter(pk=pk).first()
        if obj is None:
            raise NotFound()
        self.check_object_permissions(request, obj)
        return Response(self.detail_serializer(obj).data)

    def create(self, request: object) -> Response:
        serializer = self.create_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = self.service.create(
            self.tenant_id, self.actor_id, serializer.validated_data, self.correlation_id, self.idempotency_key()
        )
        return Response(self.detail_serializer(obj).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: object, pk: object = None) -> Response:
        serializer = self.update_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        version = serializer.validated_data.pop("version", None)
        if version is None:
            raise ValidationError({"version": "This field is required."})
        obj = self.service.update(
            self.tenant_id,
            pk,
            self.actor_id,
            version,
            serializer.validated_data,
            self.correlation_id,
            self.idempotency_key(),
        )
        return Response(self.detail_serializer(obj).data)

    def destroy(self, request: object, pk: object = None) -> Response:
        try:
            version = int(request.query_params.get("version", request.data.get("version")))
        except (TypeError, ValueError):
            raise ValidationError({"version": "A positive version is required."})
        self.service.soft_delete(
            self.tenant_id, pk, self.actor_id, version, self.correlation_id, self.idempotency_key()
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _transition(self, request: object, pk: object, command: str) -> Response:
        serializer = QueryTransitionSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = getattr(self.service, command)(
            self.tenant_id,
            pk,
            self.actor_id,
            serializer.validated_data["version"],
            self.correlation_id,
            self.idempotency_key(),
            serializer.validated_data.get("reason", ""),
        )
        return Response(self.detail_serializer(obj).data)

    @action(detail=True, methods=("post",))
    def publish(self, request: object, pk: object = None) -> Response:
        return self._transition(request, pk, "publish")

    @action(detail=True, methods=("post",))
    def archive(self, request: object, pk: object = None) -> Response:
        return self._transition(request, pk, "archive")

    @action(detail=True, methods=("post",))
    def restore(self, request: object, pk: object = None) -> Response:
        return self._transition(request, pk, "restore")

    @action(detail=True, methods=("post",))
    def execute(self, request: object, pk: object = None) -> Response:
        serializer = ExecutionRequestSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        result = self.service.enqueue_execution(
            self.tenant_id,
            pk,
            self.actor_id,
            serializer.validated_data["parameters"],
            self.correlation_id,
            self.idempotency_key(),
        )
        if isinstance(result, list):
            data = {
                "execution_ids": [str(item.id) for item in result],
                "job_ids": [str(item.async_job_id) for item in result],
                "status": "queued",
            }
        else:
            data = {"execution_id": str(result.id), "job_id": str(result.async_job_id), "status": result.status}
        return Response(data, status=status.HTTP_202_ACCEPTED)


COMMON_PERMISSIONS = {
    "list": "read",
    "retrieve": "read",
    "create": "create",
    "update": "update",
    "partial_update": "update",
    "destroy": "delete",
    "publish": "update",
    "archive": "update",
    "restore": "update",
    "execute": "execute",
}


class QueryViewSet(_DefinitionViewSet):
    model, service = QueryDefinition, QueryService
    list_serializer, detail_serializer = QueryListSerializer, QueryDetailSerializer  # noqa: F405
    create_serializer, update_serializer = QueryCreateSerializer, QueryUpdateSerializer  # noqa: F405
    search_fields, ordering_fields = ("query_code", "name", "description"), (
        "query_code",
        "name",
        "state",
        "created_at",
        "updated_at",
    )
    permission_map = {key: f"bi.query:{value}" for key, value in COMMON_PERMISSIONS.items()}
    permission_map["validate"] = "bi.query:read"

    @action(detail=True, methods=("post",))
    def validate(self, request: object, pk: object = None) -> Response:
        serializer = QueryValidateSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        QueryService.validate(self.tenant_id, pk, serializer.validated_data["parameters"])
        return Response({"valid": True})


class ReportViewSet(_DefinitionViewSet):
    model, service = Report, ReportService
    list_serializer, detail_serializer = ReportListSerializer, ReportDetailSerializer  # noqa: F405
    create_serializer, update_serializer = ReportCreateSerializer, ReportUpdateSerializer  # noqa: F405
    search_fields, ordering_fields = ("report_code", "report_name", "description"), (
        "report_code",
        "report_name",
        "report_type",
        "state",
        "created_at",
        "updated_at",
    )
    permission_map = {key: f"bi.report:{value}" for key, value in COMMON_PERMISSIONS.items()}

    def get_queryset(self):
        queryset = super().get_queryset()
        dataset_key = self.request.query_params.get("dataset_key")
        return queryset.filter(query_definition__dataset_key=dataset_key) if dataset_key else queryset


class DashboardViewSet(_DefinitionViewSet):
    model, service = Dashboard, DashboardService
    list_serializer, detail_serializer = DashboardListSerializer, DashboardDetailSerializer  # noqa: F405
    create_serializer, update_serializer = DashboardCreateSerializer, DashboardUpdateSerializer  # noqa: F405
    search_fields, ordering_fields = ("dashboard_code", "dashboard_name", "description"), (
        "dashboard_code",
        "dashboard_name",
        "state",
        "created_at",
        "updated_at",
    )
    permission_map = {key: f"bi.dashboard:{value}" for key, value in COMMON_PERMISSIONS.items()}

    def _role_subjects(self) -> list[str]:
        groups = getattr(self.request.user, "groups", None)
        if groups is None:
            return []
        return [str(value) for value in groups.values_list("name", flat=True)]

    def _require_access(self, pk: object, *, owner_only: bool = False) -> None:
        dashboard = Dashboard.objects.for_tenant(self.tenant_id).filter(pk=pk, deleted_at__isnull=True).first()
        if dashboard is None:
            raise NotFound()
        if dashboard.created_by_id == self.actor_id:
            return
        if owner_only:
            raise PermissionDenied("Only the dashboard owner may perform this operation.")
        editable = (
            DashboardShare.objects.for_tenant(self.tenant_id)
            .active()
            .filter(
                dashboard=dashboard,
                access_level="edit",
            )
        )
        role_subjects = self._role_subjects()
        if editable.filter(subject_type="user", subject_id=self.actor_id).exists() or (
            role_subjects and editable.filter(subject_type="role", subject_id__in=role_subjects).exists()
        ):
            return
        raise PermissionDenied("Dashboard edit access is required.")

    def partial_update(self, request: object, pk: object = None) -> Response:
        self._require_access(pk)
        return super().partial_update(request, pk)

    def destroy(self, request: object, pk: object = None) -> Response:
        self._require_access(pk, owner_only=True)
        return super().destroy(request, pk)

    def _transition(self, request: object, pk: object, command: str) -> Response:
        self._require_access(pk, owner_only=True)
        return super()._transition(request, pk, command)

    def execute(self, request: object, pk: object = None) -> Response:
        if not self.get_queryset().filter(pk=pk).exists():
            raise NotFound()
        return super().execute(request, pk)

    def get_queryset(self):
        queryset = super().get_queryset()
        subject = Q(shares__subject_type="user", shares__subject_id=self.actor_id)
        roles = self._role_subjects()
        if roles:
            subject |= Q(shares__subject_type="role", shares__subject_id__in=roles)
        active_share = (
            subject
            & Q(shares__revoked_at__isnull=True)
            & (Q(shares__expires_at__isnull=True) | Q(shares__expires_at__gt=timezone.now()))
        )
        if self.action in {"publish", "archive", "restore", "destroy"}:
            return queryset.filter(created_by_id=self.actor_id)
        if self.action == "partial_update":
            editable_share = active_share & Q(shares__access_level="edit")
            return queryset.filter(Q(created_by_id=self.actor_id) | editable_share).distinct()
        access = self.request.query_params.get("access")
        if access == "owned":
            return queryset.filter(created_by_id=self.actor_id)
        if access == "shared":
            return queryset.filter(active_share).distinct()
        if access not in {None, ""}:
            raise ValidationError({"access": "Use owned or shared."})
        return queryset.filter(Q(created_by_id=self.actor_id) | active_share).distinct()


class ExecutionViewSet(_BIViewMixin, viewsets.GenericViewSet):
    permission_map = {
        "list": "bi.execution:read",
        "retrieve": "bi.execution:read",
        "result": "bi.execution:read",
        "cancel": "bi.execution:cancel",
    }

    def get_queryset(self):
        queryset = QueryExecution.objects.for_tenant(self.tenant_id)
        status_value = self.request.query_params.get("status")
        if status_value and status_value not in {
            "queued",
            "running",
            "succeeded",
            "failed",
            "cancelled",
            "timed_out",
        }:
            raise ValidationError({"status": "Unsupported execution status."})
        for field in ("status", "query_definition_id", "report_id", "dashboard_id"):
            parameter = {"query_definition_id": "query", "report_id": "report", "dashboard_id": "dashboard"}.get(
                field, field
            )
            if self.request.query_params.get(parameter):
                value = self.request.query_params[parameter]
                if field.endswith("_id"):
                    try:
                        value = uuid.UUID(value)
                    except (TypeError, ValueError, AttributeError) as exc:
                        raise ValidationError({parameter: "A valid UUID is required."}) from exc
                queryset = queryset.filter(**{field: value})
        for parameter, lookup in (("created_from", "created_at__gte"), ("created_to", "created_at__lte")):
            raw = self.request.query_params.get(parameter)
            if raw:
                parsed = parse_datetime(raw)
                if parsed is None:
                    raise ValidationError({parameter: "A valid ISO 8601 date-time is required."})
                queryset = queryset.filter(**{lookup: parsed})
        ordering = self.request.query_params.get("ordering", "-created_at")
        if ordering.lstrip("-") not in {"created_at", "completed_at", "status", "duration_ms"}:
            raise ValidationError({"ordering": "Unsupported ordering field."})
        return queryset.order_by(ordering, "id")

    def list(self, request: object) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(ExecutionListSerializer(page, many=True).data)  # noqa: F405

    def retrieve(self, request: object, pk: object = None) -> Response:
        obj = self.get_queryset().filter(pk=pk).first()
        if obj is None:
            raise NotFound()
        return Response(ExecutionDetailSerializer(obj).data)  # noqa: F405

    @action(detail=True, methods=("get",))
    def result(self, request: object, pk: object = None) -> Response:
        execution = ExecutionService.get_result(self.tenant_id, pk)
        page = self.paginate_queryset(execution.result_rows)
        response = self.get_paginated_response(page)
        result_data = dict(ExecutionResultSerializer(execution).data)  # noqa: F405
        result_data["rows"] = page
        response.data = result_data
        return response

    @action(detail=True, methods=("post",))
    def cancel(self, request: object, pk: object = None) -> Response:
        obj = ExecutionService.cancel(self.tenant_id, pk, self.actor_id, self.correlation_id, self.idempotency_key())
        return Response(ExecutionDetailSerializer(obj).data)  # noqa: F405


class _NestedDashboardView(_BIViewMixin, APIView):
    permission_map = {
        "GET": "bi.dashboard:read",
        "POST": "bi.dashboard:update",
        "PATCH": "bi.dashboard:update",
        "DELETE": "bi.dashboard:update",
    }
    owner_only = False

    def get_permissions(self):
        self.permission_action = self.request.method
        return super().get_permissions()

    def initial(self, request: object, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        dashboard_id = kwargs.get("dashboard_id")
        dashboard = (
            Dashboard.objects.for_tenant(self.tenant_id).filter(pk=dashboard_id, deleted_at__isnull=True).first()
        )
        if dashboard is None:
            raise NotFound()
        if dashboard.created_by_id == self.actor_id:
            return
        if self.owner_only:
            raise PermissionDenied("Only the dashboard owner may manage sharing.")
        groups = getattr(self.request.user, "groups", None)
        roles = [str(value) for value in groups.values_list("name", flat=True)] if groups is not None else []
        shares = DashboardShare.objects.for_tenant(self.tenant_id).active().filter(dashboard=dashboard)
        if self.request.method != "GET":
            shares = shares.filter(access_level="edit")
        allowed = shares.filter(subject_type="user", subject_id=self.actor_id).exists()
        if not allowed and roles:
            allowed = shares.filter(subject_type="role", subject_id__in=roles).exists()
        if not allowed:
            raise PermissionDenied("Dashboard access is required.")

    def paginated(self, request: object, rows: object, serializer_class: object) -> Response:
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(serializer_class(page, many=True).data)


class WidgetCollectionView(_NestedDashboardView):
    def get(self, request: object, dashboard_id: object) -> Response:
        dashboard = (
            Dashboard.objects.for_tenant(self.tenant_id).filter(pk=dashboard_id, deleted_at__isnull=True).first()
        )
        if dashboard is None:
            raise NotFound()
        rows = (
            DashboardWidget.objects.for_tenant(self.tenant_id)
            .filter(dashboard=dashboard, deleted_at__isnull=True)
            .order_by("display_order", "id")
        )
        return self.paginated(request, rows, WidgetListSerializer)  # noqa: F405

    def post(self, request: object, dashboard_id: object) -> Response:
        serializer = WidgetCreateSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = DashboardService.add_widget(
            self.tenant_id,
            dashboard_id,
            self.actor_id,
            serializer.validated_data,
            self.correlation_id,
            self.idempotency_key(),
        )
        return Response(WidgetDetailSerializer(obj).data, status=201)  # noqa: F405


class WidgetDetailView(_NestedDashboardView):
    def _get(self, dashboard_id: object, widget_id: object) -> DashboardWidget:
        obj = (
            DashboardWidget.objects.for_tenant(self.tenant_id)
            .filter(pk=widget_id, dashboard_id=dashboard_id, deleted_at__isnull=True)
            .first()
        )
        if obj is None:
            raise NotFound()
        return obj

    def get(self, request: object, dashboard_id: object, widget_id: object) -> Response:
        return Response(WidgetDetailSerializer(self._get(dashboard_id, widget_id)).data)  # noqa: F405

    def patch(self, request: object, dashboard_id: object, widget_id: object) -> Response:
        serializer = WidgetUpdateSerializer(data=request.data, partial=True)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        version = serializer.validated_data.pop("version", None)
        if version is None:
            raise ValidationError({"version": "This field is required."})
        obj = DashboardService.update_widget(
            self.tenant_id,
            dashboard_id,
            widget_id,
            self.actor_id,
            version,
            serializer.validated_data,
            self.correlation_id,
            self.idempotency_key(),
        )
        return Response(WidgetDetailSerializer(obj).data)  # noqa: F405

    def delete(self, request: object, dashboard_id: object, widget_id: object) -> Response:
        DashboardService.remove_widget(
            self.tenant_id, dashboard_id, widget_id, self.actor_id, self.correlation_id, self.idempotency_key()
        )
        return Response(status=204)


class WidgetReorderView(_NestedDashboardView):
    permission_map = {"POST": "bi.dashboard:update"}

    def post(self, request: object, dashboard_id: object) -> Response:
        serializer = WidgetReorderSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = DashboardService.reorder_widgets(
            self.tenant_id,
            dashboard_id,
            self.actor_id,
            serializer.validated_data["version"],
            serializer.validated_data["widgets"],
            self.correlation_id,
            self.idempotency_key(),
        )
        return Response(DashboardDetailSerializer(obj).data)  # noqa: F405


class ShareCollectionView(_NestedDashboardView):
    owner_only = True
    permission_map = {"GET": "bi.dashboard:share", "POST": "bi.dashboard:share"}

    def get(self, request: object, dashboard_id: object) -> Response:
        if not Dashboard.objects.for_tenant(self.tenant_id).filter(pk=dashboard_id, deleted_at__isnull=True).exists():
            raise NotFound()
        rows = (
            DashboardShare.objects.for_tenant(self.tenant_id).filter(dashboard_id=dashboard_id).order_by("-created_at")
        )
        return self.paginated(request, rows, ShareListSerializer)  # noqa: F405

    def post(self, request: object, dashboard_id: object) -> Response:
        serializer = ShareCreateSerializer(data=request.data)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = DashboardService.share(
            self.tenant_id,
            dashboard_id,
            self.actor_id,
            serializer.validated_data,
            self.correlation_id,
            self.idempotency_key(),
        )
        return Response(ShareListSerializer(obj).data, status=201)  # noqa: F405


class ShareDetailView(_NestedDashboardView):
    owner_only = True
    permission_map = {"PATCH": "bi.dashboard:share", "DELETE": "bi.dashboard:share"}

    def patch(self, request: object, dashboard_id: object, share_id: object) -> Response:
        serializer = ShareUpdateSerializer(data=request.data, partial=True)  # noqa: F405
        serializer.is_valid(raise_exception=True)
        obj = DashboardService.update_share(
            self.tenant_id,
            dashboard_id,
            share_id,
            self.actor_id,
            serializer.validated_data,
            self.correlation_id,
            self.idempotency_key(),
        )
        return Response(ShareListSerializer(obj).data)  # noqa: F405

    def delete(self, request: object, dashboard_id: object, share_id: object) -> Response:
        DashboardService.revoke_share(
            self.tenant_id, dashboard_id, share_id, self.actor_id, self.correlation_id, self.idempotency_key()
        )
        return Response(status=204)


class HealthView(GovernedAPIViewMixin, APIView):
    authentication_classes: tuple = ()
    permission_classes = (AllowAny,)

    def get(self, request: object) -> Response:
        result = module_health()
        serializer = HealthResponseSerializer(result)  # noqa: F405
        return Response(serializer.data, status=200 if result["ready"] else 503)


__all__ = [
    "DashboardViewSet",
    "DatasetViewSet",
    "ExecutionViewSet",
    "HealthView",
    "QueryViewSet",
    "ReportViewSet",
    "ShareCollectionView",
    "ShareDetailView",
    "WidgetCollectionView",
    "WidgetDetailView",
    "WidgetReorderView",
]
