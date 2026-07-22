"""Thin governed HTTP adapters for API-management services."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from django.db import IntegrityError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.api.envelope import correlation_id_for_request
from src.core.auth_utils import get_user_tenant_id, get_user_tenant_role

from .health import module_health
from .models import ApiManagementResource
from .permissions import (
    CONFIG_EXPORT,
    CONFIG_IMPORT,
    CONFIG_READ,
    CONFIG_ROLLBACK,
    CONFIG_UPDATE,
    HEALTH_READ,
    RESOURCE_ACTIVATE,
    RESOURCE_CREATE,
    RESOURCE_DEACTIVATE,
    RESOURCE_DELETE,
    RESOURCE_READ,
    RESOURCE_RESTORE,
    RESOURCE_UPDATE,
    ActionAccessMixin,
)
from .serializers import (
    ApiManagementConfigurationSerializer,
    ApiManagementConfigurationVersionSerializer,
    ApiManagementResourceInputSerializer,
    ApiManagementResourceSerializer,
    ConfigurationDocumentSerializer,
    ConfigurationRollbackSerializer,
)
from .services import (
    ApiManagementService,
    ConfigurationValidationError,
    IdempotencyConflictError,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The operation conflicts with current state."
    default_code = "conflict"


def _actor(request: Request) -> str:
    value = getattr(request.user, "id", getattr(request.user, "pk", None))
    if value is None:
        raise PermissionDenied("Authenticated actor identity is required.")
    return str(value)


def _tenant(request: Request) -> uuid.UUID:
    value = getattr(request, "tenant_id", None) or get_user_tenant_id(request.user)
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("Authenticated tenant context is required.") from exc


def _idempotency_key(request: Request, body_value: object | None = None) -> uuid.UUID:
    raw = body_value or request.headers.get("Idempotency-Key")
    try:
        return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"idempotency_key": "A valid UUID idempotency key is required."}) from exc


def _audience(request: Request) -> tuple[tuple[str, ...], tuple[str, ...]]:
    role = get_user_tenant_role(request.user)
    roles = (role,) if isinstance(role, str) and role else ()
    groups = getattr(request.user, "groups", None)
    cohorts = tuple(groups.values_list("name", flat=True)) if hasattr(groups, "values_list") else ()
    return roles, cohorts


def _service(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except ConfigurationValidationError as exc:
        raise ValidationError(exc.errors) from exc
    except IdempotencyConflictError as exc:
        raise Conflict(str(exc)) from exc
    except IntegrityError as exc:
        raise Conflict("The operation conflicts with persisted state.") from exc
    except PermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    except LookupError as exc:
        raise NotFound(str(exc)) from exc
    except ValueError as exc:
        raise ValidationError({"non_field_errors": [str(exc)]}) from exc


class TenantConfiguredPagination(PageNumberPagination):
    """Bound pagination using the current tenant's validated limits."""

    page_size_query_param = "page_size"
    page_size = None
    max_page_size = None

    def paginate_queryset(self, queryset: Any, request: Request, view: Any = None) -> list[Any] | None:
        document = getattr(view, "configuration_document", None)
        if not isinstance(document, dict):
            raise PermissionDenied("Tenant pagination configuration is unavailable.")
        self.page_size = int(document["page_size"])
        self.max_page_size = int(document["max_page_size"])
        return super().paginate_queryset(queryset, request, view)


class ApiManagementResourceViewSet(ActionAccessMixin, viewsets.ViewSet):
    """Tenant-isolated resource controller delegating all logic to services."""

    action_permissions = {
        "list": RESOURCE_READ,
        "retrieve": RESOURCE_READ,
        "create": RESOURCE_CREATE,
        "update": RESOURCE_UPDATE,
        "partial_update": RESOURCE_UPDATE,
        "destroy": RESOURCE_DELETE,
        "activate": RESOURCE_ACTIVATE,
        "deactivate": RESOURCE_DEACTIVATE,
        "restore": RESOURCE_RESTORE,
    }
    pagination_class = TenantConfiguredPagination
    service = ApiManagementService()

    def get_queryset(self):
        tenant = _tenant(self.request)
        actor = _actor(self.request)
        correlation = correlation_id_for_request(self.request)
        configuration = self.service.get_configuration(tenant, actor_id=actor, correlation_id=correlation)
        self.configuration_document = configuration.document
        roles, cohorts = _audience(self.request)
        return _service(
            lambda: self.service.query_resources(
                tenant,
                self.request.query_params,
                actor_id=actor,
                correlation_id=correlation,
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )

    def get_object(self) -> ApiManagementResource:
        tenant = _tenant(self.request)
        actor = _actor(self.request)
        correlation = correlation_id_for_request(self.request)
        roles, cohorts = _audience(self.request)
        queryset = _service(
            lambda: self.service.query_resources(
                tenant,
                {},
                actor_id=actor,
                correlation_id=correlation,
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )
        resource = queryset.filter(pk=self.kwargs.get("pk")).first()
        if resource is None:
            raise NotFound("Resource was not found.")
        self.check_object_permissions(self.request, resource)
        return resource

    def list(self, request: Request) -> Response:
        queryset = self.get_queryset()
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ApiManagementResourceSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(ApiManagementResourceSerializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        serializer = ApiManagementResourceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        roles, cohorts = _audience(request)
        resource = _service(
            lambda: self.service.create_resource(
                _tenant(request),
                values["name"],
                values.get("description"),
                values.get("config"),
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request),
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )
        return Response(ApiManagementResourceSerializer(resource).data, status=status.HTTP_201_CREATED)

    def _update(self, request: Request, *, partial: bool) -> Response:
        resource = self.get_object()
        serializer = ApiManagementResourceInputSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        roles, cohorts = _audience(request)
        updated = _service(
            lambda: self.service.update_resource(
                resource.id,
                _tenant(request),
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request),
                updates=serializer.validated_data,
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )
        if updated is None:
            raise NotFound("Resource was not found.")
        return Response(ApiManagementResourceSerializer(updated).data)

    def update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        return self._update(request, partial=False)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        del pk
        return self._update(request, partial=True)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        resource = self.get_object()
        roles, cohorts = _audience(request)
        deleted = _service(
            lambda: self.service.delete_resource(
                resource.id,
                _tenant(request),
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request),
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )
        if not deleted:
            raise NotFound("Resource was not found.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    def _transition(self, request: Request, operation: Callable[..., Any]) -> Response:
        resource = self.get_object()
        roles, cohorts = _audience(request)
        result = _service(
            lambda: operation(
                resource.id,
                _tenant(request),
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request),
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )
        if result is None:
            raise NotFound("Resource was not found.")
        return Response(ApiManagementResourceSerializer(result).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: str | None = None) -> Response:
        del pk
        return self._transition(request, self.service.activate_resource)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, pk: str | None = None) -> Response:
        del pk
        return self._transition(request, self.service.deactivate_resource)

    @action(detail=True, methods=["post"])
    def restore(self, request: Request, pk: str | None = None) -> Response:
        del pk
        # Archived resources are intentionally absent from get_object().
        roles, cohorts = _audience(request)
        result = _service(
            lambda: self.service.restore_resource(
                self.kwargs.get("pk"),
                _tenant(request),
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request),
                audience_roles=roles,
                audience_cohorts=cohorts,
            )
        )
        if result is None:
            raise NotFound("Archived resource was not found.")
        return Response(ApiManagementResourceSerializer(result).data)


class GovernedConfigurationView(ActionAccessMixin, APIView):
    """APIView variant using HTTP methods as deny-default action names."""

    def get_permissions(self) -> list[object]:
        self.action = self.request.method.lower()
        return super().get_permissions()

    @property
    def service(self) -> ApiManagementService:
        return ApiManagementService()


class ConfigurationView(GovernedConfigurationView):
    action_permissions = {"get": CONFIG_READ, "put": CONFIG_UPDATE}

    def get(self, request: Request) -> Response:
        configuration = _service(
            lambda: self.service.get_configuration(
                _tenant(request), actor_id=_actor(request), correlation_id=correlation_id_for_request(request)
            )
        )
        return Response(ApiManagementConfigurationSerializer(configuration).data)

    def put(self, request: Request) -> Response:
        serializer = ConfigurationDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration = _service(
            lambda: self.service.update_configuration(
                _tenant(request),
                serializer.validated_data["document"],
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request, serializer.validated_data.get("idempotency_key")),
            )
        )
        return Response(ApiManagementConfigurationSerializer(configuration).data)


class ConfigurationPreviewView(GovernedConfigurationView):
    action_permissions = {"post": CONFIG_UPDATE}

    def post(self, request: Request) -> Response:
        serializer = ConfigurationDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = _service(
            lambda: self.service.preview_configuration(_tenant(request), serializer.validated_data["document"])
        )
        return Response(result)


class ConfigurationHistoryView(GovernedConfigurationView):
    action_permissions = {"get": CONFIG_READ}

    def get(self, request: Request) -> Response:
        versions = _service(lambda: self.service.configuration_history(_tenant(request)))
        return Response(ApiManagementConfigurationVersionSerializer(versions, many=True).data)


class ConfigurationRollbackView(GovernedConfigurationView):
    action_permissions = {"post": CONFIG_ROLLBACK}

    def post(self, request: Request) -> Response:
        serializer = ConfigurationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration = _service(
            lambda: self.service.rollback_configuration(
                _tenant(request),
                serializer.validated_data["version"],
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request, serializer.validated_data.get("idempotency_key")),
            )
        )
        return Response(ApiManagementConfigurationSerializer(configuration).data)


class ConfigurationImportView(GovernedConfigurationView):
    action_permissions = {"post": CONFIG_IMPORT}

    def post(self, request: Request) -> Response:
        serializer = ConfigurationDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration = _service(
            lambda: self.service.import_configuration(
                _tenant(request),
                serializer.validated_data["document"],
                actor_id=_actor(request),
                correlation_id=correlation_id_for_request(request),
                idempotency_key=_idempotency_key(request, serializer.validated_data.get("idempotency_key")),
            )
        )
        return Response(ApiManagementConfigurationSerializer(configuration).data)


class ConfigurationExportView(GovernedConfigurationView):
    action_permissions = {"get": CONFIG_EXPORT}

    def get(self, request: Request) -> Response:
        result = _service(
            lambda: self.service.export_configuration(
                _tenant(request), actor_id=_actor(request), correlation_id=correlation_id_for_request(request)
            )
        )
        return Response(result)


class HealthView(GovernedConfigurationView):
    action_permissions = {"get": HEALTH_READ}

    def get(self, request: Request) -> Response:
        configuration = _service(
            lambda: self.service.get_configuration(
                _tenant(request), actor_id=_actor(request), correlation_id=correlation_id_for_request(request)
            )
        )
        payload, http_status = module_health(
            tenant_id=_tenant(request),
            cache_ttl_seconds=configuration.document["health_cache_ttl_seconds"],
        )
        return Response(payload, status=http_status)


__all__ = [
    "ApiManagementResourceViewSet",
    "ConfigurationExportView",
    "ConfigurationHistoryView",
    "ConfigurationImportView",
    "ConfigurationPreviewView",
    "ConfigurationRollbackView",
    "ConfigurationView",
    "HealthView",
]
