"""REST resources for tenant AI-provider configuration."""

from __future__ import annotations

from typing import Any
import uuid
from uuid import UUID

from django.db.models import Count, Q, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderConfigurationResource,
    AIProviderCredential,
    AIProviderRuntimeConfiguration,
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
    AIProviderRuntimeConfigurationAuditSerializer,
    AIProviderRuntimeConfigurationImportSerializer,
    AIProviderRuntimeConfigurationRollbackSerializer,
    AIProviderRuntimeConfigurationSerializer,
    AIProviderRuntimeConfigurationVersionSerializer,
    AIProviderRuntimeConfigurationWriteSerializer,
    AIUsageLogSerializer,
    ReEncryptSerializer,
    RotateKeySerializer,
)
from .services import AIProviderConfigurationService, AIProviderRuntimeConfigurationService, _section


class ModulePagination(PageNumberPagination):
    page_size_query_param = "page_size"

    def get_page_size(self, request: object) -> int:
        tenant_id = get_user_tenant_id(getattr(request, "user", None))
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        pagination = _section(policy, "pagination")
        self.page_size = int(pagination["default_page_size"])
        self.max_page_size = int(pagination["max_page_size"])
        return super().get_page_size(request)


class TenantContextMixin:
    """Resolve tenant and actor identity without accepting either from input."""

    request: Any

    def tenant_id(self) -> UUID:
        value = get_user_tenant_id(self.request.user)
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PermissionDenied("Authenticated identity has no valid tenant.") from exc

    def tenant_id_or_none(self) -> UUID | None:
        try:
            return self.tenant_id()
        except PermissionDenied:
            return None

    def actor_id(self) -> str:
        value = getattr(self.request.user, "pk", None)
        if value is None:
            raise PermissionDenied("Authenticated identity has no actor identifier.")
        try:
            actor_id = str(value if isinstance(value, UUID) else UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            actor_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:user:{value}"))
        if not actor_id:
            raise PermissionDenied("Authenticated identity has no valid actor identifier.")
        return actor_id


class AIProviderConfigurationResourceViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ModelViewSet):
    """Tenant-filtered CRUD for the module's original resource contract."""

    serializer_class = AIProviderConfigurationResourceSerializer
    authentication_classes = (RelaxedCsrfSessionAuthentication,)
    pagination_class = ModulePagination
    service_class = AIProviderConfigurationService
    action_permissions = {
        "list": "ai_provider_configuration.resource:read",
        "retrieve": "ai_provider_configuration.resource:read",
        "create": "ai_provider_configuration.resource:create",
        "update": "ai_provider_configuration.resource:update",
        "partial_update": "ai_provider_configuration.resource:update",
        "destroy": "ai_provider_configuration.resource:delete",
        "restore": "ai_provider_configuration.resource:update",
    }

    def get_queryset(self) -> QuerySet[AIProviderConfigurationResource]:
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIProviderConfigurationResource.objects.none()
        return AIProviderConfigurationResource.objects.for_tenant(tenant_id).filter(is_deleted=False).order_by("name")

    def create(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        resource = self.service_class().create_resource(
            tenant_id=self.tenant_id(),
            created_by=self.actor_id(),
            idempotency_key=self.request.headers.get("Idempotency-Key") or self.request.data.get("idempotency_key"),
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

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        resource = self.service_class().restore_resource(self.kwargs["pk"], self.tenant_id())
        return Response(self.get_serializer(resource).data)


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
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIProvider.objects.none()
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        visibility = _section(policy, "catalog_visibility")
        queryset = AIProvider.objects.all().annotate(models_count=Count("models"))
        if bool(visibility["providers_active_only"]):
            queryset = queryset.filter(is_active=True)
        provider_type = self.request.query_params.get("provider_type")
        if provider_type:
            queryset = queryset.filter(provider_type=provider_type)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search[: int(fields["search_provider_max"])])
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
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIProviderCredential.objects.none()
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        queryset = AIProviderCredential.objects.for_tenant(tenant_id).filter(is_deleted=False).select_related(
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
            queryset = queryset.filter(label__icontains=search[: int(fields["search_credential_max"])])
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
            label=data.get("label"),
            idempotency_key=self.request.headers.get("Idempotency-Key") or self.request.data.get("idempotency_key"),
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
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIModel.objects.none()
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        visibility = _section(policy, "catalog_visibility")
        queryset = AIModel.objects.all().select_related("provider").annotate(
            deployments_count=Count(
                "deployments",
                filter=Q(deployments__tenant_id=tenant_id, deployments__is_deleted=False),
            )
        )
        if bool(visibility["models_active_only"]):
            queryset = queryset.filter(is_active=True)
        provider_id = self.request.query_params.get("provider_id") or self.request.query_params.get("provider")
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)
        capability = self.request.query_params.get("capability")
        if capability:
            queryset = queryset.filter(capabilities__contains=[capability])
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(display_name__icontains=search[: int(fields["search_model_max"])])
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
        "activate": "ai_provider_configuration.deployment:update",
        "deactivate": "ai_provider_configuration.deployment:update",
    }

    def get_queryset(self) -> QuerySet[AIModelDeployment]:
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIModelDeployment.objects.none()
        policy = AIProviderRuntimeConfigurationService.runtime_values(tenant_id)
        fields = _section(policy, "field_limits")
        queryset = (
            AIModelDeployment.objects.for_tenant(tenant_id)
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
            queryset = queryset.filter(deployment_name__icontains=search[: int(fields["search_deployment_max"])])
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
            idempotency_key=self.request.headers.get("Idempotency-Key") or self.request.data.get("idempotency_key"),
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

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        deployment = self.service_class().update_deployment(self.tenant_id(), self.kwargs["pk"], status="active")
        return Response(AIModelDeploymentDetailSerializer(deployment).data)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request: object, *args: object, **kwargs: object) -> Response:
        del request, args, kwargs
        deployment = self.service_class().update_deployment(self.tenant_id(), self.kwargs["pk"], status="inactive")
        return Response(AIModelDeploymentDetailSerializer(deployment).data)


class AIUsageLogViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.ReadOnlyModelViewSet):
    """Read immutable usage evidence for the authenticated tenant."""

    serializer_class = AIUsageLogSerializer
    pagination_class = ModulePagination
    action_permissions = {
        "list": "ai_provider_configuration.usage:read",
        "retrieve": "ai_provider_configuration.usage:read",
    }

    def get_queryset(self) -> QuerySet[AIUsageLog]:
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIUsageLog.objects.none()
        queryset = AIUsageLog.objects.for_tenant(tenant_id).select_related(
            "deployment__model__provider"
        )
        deployment_id = self.request.query_params.get("deployment_id") or self.request.query_params.get("deployment")
        if deployment_id:
            queryset = queryset.filter(deployment_id=deployment_id)
        return queryset.order_by("-created_at")


class AIProviderRuntimeConfigurationViewSet(ActionPermissionMixin, TenantContextMixin, viewsets.GenericViewSet):
    """RBAC-gated runtime configuration, history, audit, import/export and rollback."""

    pagination_class = ModulePagination
    service_class = AIProviderRuntimeConfigurationService
    action_permissions = {
        "current": "ai_provider_configuration.configuration:read",
        "update_current": "ai_provider_configuration.configuration:update",
        "preview": "ai_provider_configuration.configuration:preview",
        "versions": "ai_provider_configuration.configuration:read",
        "audit": "ai_provider_configuration.configuration:audit",
        "rollback": "ai_provider_configuration.configuration:rollback",
        "export": "ai_provider_configuration.configuration:export",
        "import_document": "ai_provider_configuration.configuration:import",
    }

    def get_queryset(self) -> QuerySet:
        tenant_id = self.tenant_id_or_none()
        if tenant_id is None:
            return AIProviderRuntimeConfiguration.objects.none()
        return AIProviderRuntimeConfiguration.objects.for_tenant(tenant_id)

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request: object) -> Response:
        del request
        configuration = self.service_class.current(self.tenant_id(), self.actor_id())
        return Response(AIProviderRuntimeConfigurationSerializer(configuration).data)

    @action(detail=False, methods=["put"], url_path="current")
    def update_current(self, request: object) -> Response:
        del request
        serializer = AIProviderRuntimeConfigurationWriteSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        configuration = self.service_class.update(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data["values"],
            serializer.validated_data["environment"],
        )
        return Response(AIProviderRuntimeConfigurationSerializer(configuration).data)

    @action(detail=False, methods=["post"], url_path="preview")
    def preview(self, request: object) -> Response:
        del request
        serializer = AIProviderRuntimeConfigurationWriteSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            self.service_class.preview(
                self.tenant_id(),
                self.actor_id(),
                serializer.validated_data["values"],
                serializer.validated_data["environment"],
            )
        )

    @action(detail=False, methods=["get"], url_path="versions")
    def versions(self, request: object) -> Response:
        del request
        configuration = self.service_class.current(self.tenant_id(), self.actor_id())
        queryset = configuration.versions.order_by("-version")
        return Response(AIProviderRuntimeConfigurationVersionSerializer(queryset, many=True).data)

    @action(detail=False, methods=["get"], url_path="audit")
    def audit(self, request: object) -> Response:
        del request
        configuration = self.service_class.current(self.tenant_id(), self.actor_id())
        queryset = configuration.audit_records.order_by("-created_at")
        return Response(AIProviderRuntimeConfigurationAuditSerializer(queryset, many=True).data)

    @action(detail=False, methods=["post"], url_path="rollback")
    def rollback(self, request: object) -> Response:
        del request
        serializer = AIProviderRuntimeConfigurationRollbackSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        configuration = self.service_class.rollback(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data["version"],
            serializer.validated_data["environment"],
        )
        return Response(AIProviderRuntimeConfigurationSerializer(configuration).data)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request: object) -> Response:
        del request
        return Response(self.service_class.export(self.tenant_id(), self.actor_id()))

    @action(detail=False, methods=["post"], url_path="import")
    def import_document(self, request: object) -> Response:
        del request
        serializer = AIProviderRuntimeConfigurationImportSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        configuration = self.service_class.import_document(
            self.tenant_id(),
            self.actor_id(),
            serializer.validated_data["document"],
        )
        return Response(AIProviderRuntimeConfigurationSerializer(configuration).data)


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
    "AIProviderRuntimeConfigurationViewSet",
    "AIModelDeploymentViewSet",
    "AIModelViewSet",
    "AIProviderCredentialViewSet",
    "AIProviderViewSet",
    "AIUsageLogViewSet",
    "SecretManagementViewSet",
]
