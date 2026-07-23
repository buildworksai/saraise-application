"""Fail-closed DRF orchestration for the Regional module."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, TypeVar

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import RegionalResource
from .permissions import RegionalPolicyPermission
from .serializers import (
    RegionalConfigurationResponseSerializer,
    RegionalConfigurationRollbackSerializer,
    RegionalConfigurationVersionSerializer,
    RegionalConfigurationWriteSerializer,
    RegionalResourceResponseSerializer,
    RegionalResourceWriteSerializer,
)
from .services import RegionalConfigurationService, RegionalService

T = TypeVar("T")


def _call_service(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except DjangoValidationError as exc:
        detail = getattr(exc, "message_dict", None) or {"detail": exc.messages}
        raise ValidationError(detail=detail) from exc
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc)) from exc


def _tenant_id(request: Request) -> uuid.UUID:
    value = get_user_tenant_id(request.user)
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise PermissionDenied("An authenticated tenant context is required.") from exc


def _actor_id(request: Request) -> str:
    value = getattr(request.user, "id", None)
    if value is None:
        raise PermissionDenied("An authenticated actor is required.")
    return str(value)


def _rollout_context(request: Request) -> tuple[str, str]:
    profile = getattr(request.user, "profile", None)
    role = str(getattr(profile, "tenant_role", "") or "")
    cohort = str(request.headers.get("X-SARAISE-Cohort", "all")).strip()
    return role, cohort


def _correlation_id(request: Request) -> uuid.UUID:
    raw = getattr(request, "correlation_id", "") or request.headers.get("X-Correlation-ID", "")
    try:
        correlation = uuid.UUID(str(raw))
    except (AttributeError, TypeError, ValueError):
        correlation = uuid.uuid4()
    request.correlation_id = str(correlation)
    return correlation


def _environment(request: Request) -> str:
    payload_environment = request.data.get("environment") if isinstance(request.data, dict) else None
    return str(payload_environment or request.query_params.get("environment") or settings.SARAISE_MODE)


class RegionalPagination(PageNumberPagination):
    """Apply the tenant's validated page-size policy."""

    page_size_query_param = "page_size"

    def paginate_queryset(
        self,
        queryset: Any,
        request: Request,
        view: Any | None = None,
    ) -> list[Any] | None:
        tenant = _tenant_id(request)
        environment = str(request.query_params.get("environment") or settings.SARAISE_MODE)
        configuration = _call_service(
            lambda: RegionalConfigurationService.get_or_create(tenant, environment)
        )
        self.page_size = int(configuration.document["api"]["default_page_size"])
        self.max_page_size = int(configuration.document["api"]["max_page_size"])
        return super().paginate_queryset(queryset, request, view=view)


class RegionalResourceViewSet(viewsets.ModelViewSet):
    """Tenant-isolated Regional resource API; all writes delegate to services."""

    serializer_class = RegionalResourceResponseSerializer
    permission_classes = (IsAuthenticated, RegionalPolicyPermission)
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    pagination_class = RegionalPagination
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]
    service = RegionalService()

    def _enforce_rollout(self, request: Request) -> None:
        role, cohort = _rollout_context(request)
        _call_service(
            lambda: self.service.ensure_rollout_access(
                _tenant_id(request), settings.SARAISE_MODE, role, cohort
            )
        )

    def get_serializer_class(self) -> type[Any]:
        if self.action in {"create", "update", "partial_update"}:
            return RegionalResourceWriteSerializer
        return RegionalResourceResponseSerializer

    def get_queryset(self) -> Any:
        self._enforce_rollout(self.request)
        tenant = _tenant_id(self.request)
        query = self.request.query_params if self.action == "list" else {}
        return _call_service(
            lambda: self.service.query_resources(tenant, settings.SARAISE_MODE, query)
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        self._enforce_rollout(request)
        serializer = RegionalResourceWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            raise ValidationError({"Idempotency-Key": "This header is required."})
        values = serializer.validated_data
        resource = _call_service(
            lambda: self.service.create_resource(
                tenant_id=_tenant_id(request),
                name=values["name"],
                description=values.get("description"),
                config=values.get("config"),
                created_by=_actor_id(request),
                correlation_id=_correlation_id(request),
                idempotency_key=idempotency_key,
                environment=settings.SARAISE_MODE,
            )
        )
        return Response(
            RegionalResourceResponseSerializer(resource).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args
        self._enforce_rollout(request)
        partial = bool(kwargs.pop("partial", False))
        serializer = RegionalResourceWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        resource = _call_service(
            lambda: self.service.update_resource(
                self.kwargs["pk"],
                _tenant_id(request),
                serializer.validated_data,
                _actor_id(request),
                _correlation_id(request),
                settings.SARAISE_MODE,
            )
        )
        if resource is None:
            raise NotFound("Regional resource was not found.")
        return Response(RegionalResourceResponseSerializer(resource).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        del args, kwargs
        self._enforce_rollout(request)
        deleted = _call_service(
            lambda: self.service.delete_resource(
                self.kwargs["pk"],
                _tenant_id(request),
                _actor_id(request),
                _correlation_id(request),
            )
        )
        if not deleted:
            raise NotFound("Regional resource was not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk: str | None = None) -> Response:
        self._enforce_rollout(request)
        resource = _call_service(
            lambda: self.service.restore_resource(
                pk,
                _tenant_id(request),
                _actor_id(request),
                _correlation_id(request),
            )
        )
        if resource is None:
            raise NotFound("Deleted Regional resource was not found.")
        return Response(RegionalResourceResponseSerializer(resource).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response:
        self._enforce_rollout(request)
        resource = _call_service(
            lambda: self.service.activate_resource(
                pk,
                _tenant_id(request),
                _actor_id(request),
                _correlation_id(request),
                settings.SARAISE_MODE,
            )
        )
        if resource is None:
            raise NotFound("Regional resource was not found.")
        return Response(RegionalResourceResponseSerializer(resource).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        self._enforce_rollout(request)
        resource = _call_service(
            lambda: self.service.deactivate_resource(
                pk,
                _tenant_id(request),
                _actor_id(request),
                _correlation_id(request),
                settings.SARAISE_MODE,
            )
        )
        if resource is None:
            raise NotFound("Regional resource was not found.")
        return Response(RegionalResourceResponseSerializer(resource).data)


class RegionalConfigurationViewSet(viewsets.ViewSet):
    """Configuration-as-code endpoint used by both UI and automation."""

    permission_scope = "configuration"
    permission_classes = (IsAuthenticated, RegionalPolicyPermission)
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    http_method_names = ["get", "put", "patch", "post", "head", "options"]

    def _current(self, request: Request) -> Any:
        return _call_service(
            lambda: RegionalConfigurationService.get_or_create(
                _tenant_id(request),
                _environment(request),
                actor_id=_actor_id(request),
                correlation_id=_correlation_id(request),
            )
        )

    def list(self, request: Request) -> Response:
        return Response(RegionalConfigurationResponseSerializer(self._current(request)).data)

    @action(detail=False, methods=["get", "put", "patch"])
    def current(self, request: Request) -> Response:
        if request.method == "GET":
            return Response(RegionalConfigurationResponseSerializer(self._current(request)).data)
        serializer = RegionalConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        current = _call_service(
            lambda: RegionalConfigurationService.update(
                _tenant_id(request),
                values.get("environment", settings.SARAISE_MODE),
                values["document"],
                _actor_id(request),
                _correlation_id(request),
                partial=request.method == "PATCH",
            )
        )
        return Response(RegionalConfigurationResponseSerializer(current).data)

    @action(detail=False, methods=["post"])
    def preview(self, request: Request) -> Response:
        serializer = RegionalConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        result = _call_service(
            lambda: RegionalConfigurationService.preview(
                _tenant_id(request),
                values.get("environment", settings.SARAISE_MODE),
                values["document"],
            )
        )
        return Response(result)

    @action(detail=False, methods=["get"])
    def history(self, request: Request) -> Response:
        versions = _call_service(
            lambda: RegionalConfigurationService.history(
                _tenant_id(request), _environment(request)
            )
        )
        return Response(RegionalConfigurationVersionSerializer(versions, many=True).data)

    @action(detail=False, methods=["post"])
    def rollback(self, request: Request) -> Response:
        serializer = RegionalConfigurationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        current = _call_service(
            lambda: RegionalConfigurationService.rollback(
                _tenant_id(request),
                values.get("environment", settings.SARAISE_MODE),
                values["version"],
                _actor_id(request),
                _correlation_id(request),
            )
        )
        return Response(RegionalConfigurationResponseSerializer(current).data)

    @action(detail=False, methods=["post"], url_path="import_document")
    def import_document(self, request: Request) -> Response:
        serializer = RegionalConfigurationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        current = _call_service(
            lambda: RegionalConfigurationService.import_document(
                _tenant_id(request),
                values.get("environment", settings.SARAISE_MODE),
                values["document"],
                _actor_id(request),
                _correlation_id(request),
            )
        )
        return Response(RegionalConfigurationResponseSerializer(current).data)

    @action(detail=False, methods=["get"], url_path="export_document")
    def export_document(self, request: Request) -> Response:
        document = _call_service(
            lambda: RegionalConfigurationService.export_document(
                _tenant_id(request), _environment(request)
            )
        )
        return Response(document)
