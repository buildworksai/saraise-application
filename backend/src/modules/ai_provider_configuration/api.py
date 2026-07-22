"""REST resources for tenant AI-provider configuration."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Count, Q, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderConfigurationResource,
    AIProviderCredential,
    AIUsageLog,
)
from .permissions import ActionPermissionMixin
from .serializers import (
    AIModelDeploymentCreateSerializer,
    AIModelDeploymentDetailSerializer,
    AIModelDeploymentListSerializer,
    AIModelDeploymentUpdateSerializer,
    AIModelDetailSerializer,
    AIModelListSerializer,
    AIProviderCredentialCreateSerializer,
    AIProviderCredentialDetailSerializer,
    AIProviderCredentialListSerializer,
    AIProviderCredentialUpdateSerializer,
    AIProviderConfigurationResourceSerializer,
    AIProviderDetailSerializer,
    AIProviderListSerializer,
    AIUsageLogSerializer,
    ReEncryptSerializer,
    RotateKeySerializer,
)
from .services import AIProviderConfigurationService


class ModulePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class TenantContextMixin:
    """Resolve tenant and actor identity without accepting either from input."""

    request: Any

    def tenant_id(self) -> UUID:
        value = get_user_tenant_id(self.request.user)
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc

    def actor_id(self) -> str:
        value = getattr(self.request.user, "pk", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no actor identifier.")
        actor_id = str(value)
        if not actor_id or len(actor_id) > 36:
            raise PermissionDenied("Authenticated identity has no valid actor identifier.")
        return actor_id


class AIProviderConfigurationResourceViewSet(viewsets.ModelViewSet):
    """Tenant-filtered CRUD for the module's original resource contract."""

    serializer_class = AIProviderConfigurationResourceSerializer
    permission_classes = (IsAuthenticated,)
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    service_class = AIProviderConfigurationService

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "list" and settings.SARAISE_MODE == "development":
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self) -> QuerySet[AIProviderConfigurationResource]:
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return AIProviderConfigurationResource.objects.none()
        return AIProviderConfigurationResource.objects.filter(tenant_id=tenant_id).order_by("name")

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant.")
        resource = self.service_class().create_resource(
            tenant_id=str(tenant_id),
            created_by=str(self.request.user.pk),
            **serializer.validated_data,
        )
        return Response(self.get_serializer(resource).data, status=status.HTTP_201_CREATED)

    def _update(self, *, partial: bool) -> Response:
        resource = self.get_object()
        serializer = self.get_serializer(resource, data=self.request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated = self.service_class().update_resource(
            str(resource.pk),
            resource.tenant_id,
            **serializer.validated_data,
        )
        if updated is None:
            raise PermissionDenied("Resource is no longer available.")
        return Response(self.get_serializer(updated).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self._update(partial=False)

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self._update(partial=True)

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        resource = self.get_object()
        if not self.service_class().delete_resource(str(resource.pk), resource.tenant_id):
            raise PermissionDenied("Resource is no longer available.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class AIProviderViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ReadOnlyModelViewSet):
    """Read the platform provider catalog."""

    pagination_class = ModulePagination
    action_permissions = {
        "list": "ai_provider_configuration.provider:read",
        "retrieve": "ai_provider_configuration.provider:read",
    }

    def get_queryset(self) -> QuerySet[AIProvider]:
        # Resolve a tenant even for global reference rows, preventing catalog
        # access by authenticated platform identities without tenant context.
        self.tenant_id()
        queryset = AIProvider.objects.filter(is_active=True).annotate(models_count=Count("models"))
        provider_type = self.request.query_params.get("provider_type")
        if provider_type:
            queryset = queryset.filter(provider_type=provider_type)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search[:255])
        return queryset.order_by("name")

    def get_serializer_class(self) -> type:
        return AIProviderListSerializer if self.action == "list" else AIProviderDetailSerializer


class AIProviderCredentialViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ModelViewSet):
    """Manage encrypted tenant credentials without exposing secret material."""

    pagination_class = ModulePagination
    service_class = AIProviderConfigurationService
    http_method_names = ("get", "post", "put", "patch", "delete", "head", "options")
    action_permissions = {
        "list": "ai_provider_configuration.credential:read",
        "retrieve": "ai_provider_configuration.credential:read",
        "create": "ai_provider_configuration.credential:create",
        "update": "ai_provider_configuration.credential:update",
        "partial_update": "ai_provider_configuration.credential:update",
        "destroy": "ai_provider_configuration.credential:delete",
    }

    def get_queryset(self) -> QuerySet[AIProviderCredential]:
        queryset = AIProviderCredential.objects.for_tenant(self.tenant_id()).filter(is_deleted=False).select_related(
            "provider"
        )
        provider_id = self.request.query_params.get("provider_id") or self.request.query_params.get("provider")
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(label__icontains=search[:120])
        return queryset.order_by("-created_at")

    def get_serializer_class(self) -> type:
        return {
            "list": AIProviderCredentialListSerializer,
            "create": AIProviderCredentialCreateSerializer,
            "update": AIProviderCredentialUpdateSerializer,
            "partial_update": AIProviderCredentialUpdateSerializer,
        }.get(self.action, AIProviderCredentialDetailSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = AIProviderCredentialCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        credential = self.service_class().create_credential(
            self.tenant_id(),
            provider_id=data["provider"],
            api_key=data["api_key"],
            label=data.get("label", "Default"),
        )
        return Response(AIProviderCredentialDetailSerializer(credential).data, status=status.HTTP_201_CREATED)

    def _update(self) -> Response:
        self.get_object()
        serializer = AIProviderCredentialUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        credential = self.service_class().update_credential(
            self.tenant_id(),
            self.kwargs["pk"],
            provider_id=data.get("provider"),
            api_key=data.get("api_key"),
            label=data.get("label"),
        )
        return Response(AIProviderCredentialDetailSerializer(credential).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self._update()

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self._update()

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class().delete_credential(self.tenant_id(), self.kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AIModelViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ReadOnlyModelViewSet):
    """Read the active platform model catalog."""

    pagination_class = ModulePagination
    action_permissions = {
        "list": "ai_provider_configuration.model:read",
        "retrieve": "ai_provider_configuration.model:read",
    }

    def get_queryset(self) -> QuerySet[AIModel]:
        tenant_id = self.tenant_id()
        queryset = AIModel.objects.filter(is_active=True).select_related("provider").annotate(
            deployments_count=Count(
                "deployments",
                filter=Q(deployments__tenant_id=tenant_id, deployments__is_deleted=False),
            )
        )
        provider_id = self.request.query_params.get("provider_id") or self.request.query_params.get("provider")
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        capability = self.request.query_params.get("capability")
        if capability:
            queryset = queryset.filter(capabilities__contains=[capability])
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(display_name__icontains=search[:255])
        return queryset.order_by("display_name")

    def get_serializer_class(self) -> type:
        return AIModelListSerializer if self.action == "list" else AIModelDetailSerializer


class AIModelDeploymentViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ModelViewSet):
    """Manage tenant deployment configurations through the service layer."""

    pagination_class = ModulePagination
    service_class = AIProviderConfigurationService
    http_method_names = ("get", "post", "put", "patch", "delete", "head", "options")
    action_permissions = {
        "list": "ai_provider_configuration.deployment:read",
        "retrieve": "ai_provider_configuration.deployment:read",
        "create": "ai_provider_configuration.deployment:create",
        "update": "ai_provider_configuration.deployment:update",
        "partial_update": "ai_provider_configuration.deployment:update",
        "destroy": "ai_provider_configuration.deployment:delete",
    }

    def get_queryset(self) -> QuerySet[AIModelDeployment]:
        queryset = (
            AIModelDeployment.objects.for_tenant(self.tenant_id())
            .filter(is_deleted=False)
            .select_related("model__provider", "credential")
        )
        model_id = self.request.query_params.get("model_id") or self.request.query_params.get("model")
        if model_id:
            queryset = queryset.filter(model_id=model_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(deployment_name__icontains=search[:255])
        return queryset.order_by("-created_at")

    def get_serializer_class(self) -> type:
        return {
            "list": AIModelDeploymentListSerializer,
            "create": AIModelDeploymentCreateSerializer,
            "update": AIModelDeploymentUpdateSerializer,
            "partial_update": AIModelDeploymentUpdateSerializer,
        }.get(self.action, AIModelDeploymentDetailSerializer)

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = AIModelDeploymentCreateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        deployment = self.service_class().create_deployment(
            self.tenant_id(),
            self.actor_id(),
            model_id=data["model"],
            credential_id=data.get("credential"),
            deployment_name=data["deployment_name"],
            config=data.get("config", {}),
            status=data.get("status", "active"),
        )
        return Response(AIModelDeploymentDetailSerializer(deployment).data, status=status.HTTP_201_CREATED)

    def _update(self) -> Response:
        self.get_object()
        serializer = AIModelDeploymentUpdateSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        changes: dict[str, object] = {}
        for source, target in (("model", "model_id"), ("credential", "credential_id")):
            if source in data:
                changes[target] = data.pop(source)
        changes.update(data)
        deployment = self.service_class().update_deployment(
            self.tenant_id(), self.kwargs["pk"], **changes
        )
        return Response(AIModelDeploymentDetailSerializer(deployment).data)

    def update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self._update()

    def partial_update(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        return self._update()

    def destroy(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        self.get_object()
        self.service_class().delete_deployment(self.tenant_id(), self.kwargs["pk"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AIUsageLogViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ReadOnlyModelViewSet):
    """Read immutable usage evidence for the authenticated tenant."""

    serializer_class = AIUsageLogSerializer
    pagination_class = ModulePagination
    action_permissions = {
        "list": "ai_provider_configuration.usage:read",
        "retrieve": "ai_provider_configuration.usage:read",
    }

    def get_queryset(self) -> QuerySet[AIUsageLog]:
        queryset = AIUsageLog.objects.for_tenant(self.tenant_id()).select_related(
            "deployment__model__provider"
        )
        deployment_id = self.request.query_params.get("deployment_id") or self.request.query_params.get("deployment")
        if deployment_id:
            queryset = queryset.filter(deployment_id=deployment_id)
        return queryset.order_by("-created_at")


class SecretManagementViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.GenericViewSet):
    """Operator-led key generation and transactional credential rotation."""

    service_class = AIProviderConfigurationService
    action_permissions = {
        "rotate_key": "ai_provider_configuration.secret:rotate",
        "re_encrypt": "ai_provider_configuration.secret:rotate",
    }

    def get_queryset(self) -> QuerySet[AIProviderCredential]:
        return AIProviderCredential.objects.for_tenant(self.tenant_id()).filter(is_deleted=False)

    @action(detail=False, methods=["post"], url_path="rotate-key")
    def rotate_key(self, request: object) -> Response:
        del request
        self.get_queryset()  # Require tenant context before generating secret material.
        serializer = RotateKeySerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {
                "new_key": self.service_class().generate_rotation_key(),
                "message": "Store the new key, configure it as primary, then re-encrypt tenant credentials.",
            }
        )

    @action(detail=False, methods=["post"], url_path="re-encrypt")
    def re_encrypt(self, request: object) -> Response:
        del request
        self.get_queryset()
        serializer = ReEncryptSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        result = self.service_class().re_encrypt_credentials(
            self.tenant_id(),
            old_key=serializer.validated_data["old_key"],
            new_key=serializer.validated_data["new_key"],
        )
        return Response(
            {
                "success": True,
                "re_encrypted_count": result.rotated_count,
                "message": f"Re-encrypted {result.rotated_count} tenant credential(s) atomically.",
            }
        )


__all__ = [
    "AIProviderConfigurationResourceViewSet",
    "AIModelDeploymentViewSet",
    "AIModelViewSet",
    "AIProviderCredentialViewSet",
    "AIProviderViewSet",
    "AIUsageLogViewSet",
    "SecretManagementViewSet",
]
