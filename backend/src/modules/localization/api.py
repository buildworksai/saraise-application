"""
DRF ViewSets for Localization module.
Provides REST API endpoints for all models.
"""

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import CurrencyConfig, Language, LocaleConfig, LocalizationResource, RegionalSettings, Translation
from .serializers import (
    CurrencyConfigSerializer,
    LanguageSerializer,
    LocaleConfigSerializer,
    LocalizationResourceSerializer,
    RegionalSettingsSerializer,
    TranslationSerializer,
)
from .services import LocalizationService, TranslationService


class LocalizationResourceViewSet(viewsets.ModelViewSet):
    """Tenant-isolated CRUD endpoint for localization resources."""

    serializer_class = LocalizationResourceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_permissions(self) -> list[BasePermission]:
        """Allow an empty anonymous list only in explicit development mode."""
        if self.action == "list" and settings.SARAISE_MODE == "development":
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        """Limit every query to the authenticated user's tenant."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return LocalizationResource.objects.none()
        return LocalizationResource.objects.filter(tenant_id=tenant_id)

    def create(self, request, *args, **kwargs):
        """Validate transport input and delegate creation to the service."""
        tenant_id = get_user_tenant_id(request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = LocalizationService().create_resource(
            tenant_id=tenant_id,
            created_by=str(request.user.id),
            **serializer.validated_data,
        )
        response_serializer = self.get_serializer(resource)
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    def update(self, request, *args, **kwargs):
        """Validate transport input and delegate updates to the service."""
        partial = kwargs.pop("partial", False)
        resource = self.get_object()
        serializer = self.get_serializer(resource, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated = LocalizationService().update_resource(
            resource.id,
            get_user_tenant_id(request.user),
            **serializer.validated_data,
        )
        if updated is None:
            raise PermissionDenied("Resource is outside the tenant boundary")
        return Response(self.get_serializer(updated).data)

    def destroy(self, request, *args, **kwargs):
        """Delegate tenant-scoped deletion to the service."""
        resource = self.get_object()
        deleted = LocalizationService().delete_resource(
            resource.id,
            get_user_tenant_id(request.user),
        )
        if not deleted:
            raise PermissionDenied("Resource is outside the tenant boundary")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate the selected tenant-owned resource."""
        resource = self.get_object()
        LocalizationService().activate_resource(
            resource.id,
            get_user_tenant_id(request.user),
        )
        return Response({"status": "activated"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate the selected tenant-owned resource."""
        resource = self.get_object()
        LocalizationService().deactivate_resource(
            resource.id,
            get_user_tenant_id(request.user),
        )
        return Response({"status": "deactivated"}, status=status.HTTP_200_OK)


class LanguageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Language read operations (platform-level).

    CRITICAL: This ViewSet provides read-only access to platform-level language data.
    Languages are shared across all tenants and managed by platform administrators.

    Access Control:
    - READ: All authenticated users (tenants can view available languages)
    - WRITE: Not available via this endpoint (platform owners use admin interface)
    - DELETE: Not available via this endpoint (platform owners use admin interface)

    Rationale for ReadOnlyModelViewSet:
    - Prevents tenants from creating/modifying platform-level reference data
    - Ensures language consistency across the platform
    - Platform owners manage languages via Django admin or platform admin interface
    - If write access is needed in the future, it MUST be restricted to platform_owner role

    Endpoints:
    - GET /api/v1/localization/languages/ - List all languages
    - GET /api/v1/localization/languages/{id}/ - Get language detail
    """

    serializer_class = LanguageSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """
        List all active languages (platform-level, no tenant filtering).

        CRITICAL: No tenant filtering because Language is platform-level.
        All tenants see the same language list.
        """
        queryset = Language.objects.filter(is_active=True)

        # Filter by code
        code = self.request.query_params.get("code")
        if code:
            queryset = queryset.filter(code=code)

        return queryset.order_by("name")

    # NOTE: If this ViewSet is ever changed to ModelViewSet to allow writes,
    # the following access control MUST be added:
    #
    # def perform_create(self, serializer):
    #     """Restrict create to platform owners only."""
    #     from src.core.auth_utils import get_user_platform_role
    #     if get_user_platform_role(self.request.user) != "platform_owner":
    #         raise PermissionDenied("Only platform owners can create languages")
    #     serializer.save()
    #
    # def perform_update(self, serializer):
    #     """Restrict update to platform owners only."""
    #     from src.core.auth_utils import get_user_platform_role
    #     if get_user_platform_role(self.request.user) != "platform_owner":
    #         raise PermissionDenied("Only platform owners can update languages")
    #     super().perform_update(serializer)
    #
    # def perform_destroy(self, instance):
    #     """Restrict delete to platform owners only."""
    #     from src.core.auth_utils import get_user_platform_role
    #     if get_user_platform_role(self.request.user) != "platform_owner":
    #         raise PermissionDenied("Only platform owners can delete languages")
    #     # Soft delete via is_active flag instead of hard delete
    #     instance.is_active = False
    #     instance.save()


class TranslationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Translation CRUD operations.

    Endpoints:
    - GET /api/v1/localization/translations/ - List all translations
    - POST /api/v1/localization/translations/ - Create translation
    - GET /api/v1/localization/translations/{id}/ - Get translation detail
    - PUT /api/v1/localization/translations/{id}/ - Update translation
    - DELETE /api/v1/localization/translations/{id}/ - Delete translation
    """

    serializer_class = TranslationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter translations by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Translation.objects.none()

        queryset = Translation.objects.filter(tenant_id=tenant_id)

        # Filter by language
        language_id = self.request.query_params.get("language_id")
        if language_id:
            queryset = queryset.filter(language_id=language_id)

        # Filter by context
        context = self.request.query_params.get("context")
        if context is not None:
            queryset = queryset.filter(context=context)

        return queryset.order_by("key")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)

    def perform_update(self, serializer):
        """Invalidate cache on update."""
        super().perform_update(serializer)
        # Invalidate cache for this translation
        service = TranslationService()
        service.invalidate_cache(
            serializer.instance.tenant_id,
            serializer.instance.language.code,
        )


class LocaleConfigViewSet(viewsets.ModelViewSet):
    """
    ViewSet for LocaleConfig CRUD operations.

    Endpoints:
    - GET /api/v1/localization/locale-configs/ - List all locale configs
    - POST /api/v1/localization/locale-configs/ - Create locale config
    - GET /api/v1/localization/locale-configs/{id}/ - Get locale config detail
    - PUT /api/v1/localization/locale-configs/{id}/ - Update locale config
    - DELETE /api/v1/localization/locale-configs/{id}/ - Delete locale config
    """

    serializer_class = LocaleConfigSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter locale configs by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return LocaleConfig.objects.none()
        return LocaleConfig.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)


class CurrencyConfigViewSet(viewsets.ModelViewSet):
    """
    ViewSet for CurrencyConfig CRUD operations.

    Endpoints:
    - GET /api/v1/localization/currency-configs/ - List all currency configs
    - POST /api/v1/localization/currency-configs/ - Create currency config
    - GET /api/v1/localization/currency-configs/{id}/ - Get currency config detail
    - PUT /api/v1/localization/currency-configs/{id}/ - Update currency config
    - DELETE /api/v1/localization/currency-configs/{id}/ - Delete currency config
    """

    serializer_class = CurrencyConfigSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter currency configs by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return CurrencyConfig.objects.none()
        return CurrencyConfig.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)


class RegionalSettingsViewSet(viewsets.ModelViewSet):
    """
    ViewSet for RegionalSettings CRUD operations.

    Endpoints:
    - GET /api/v1/localization/regional-settings/ - List all regional settings
    - POST /api/v1/localization/regional-settings/ - Create regional settings
    - GET /api/v1/localization/regional-settings/{id}/ - Get regional settings detail
    - PUT /api/v1/localization/regional-settings/{id}/ - Update regional settings
    - DELETE /api/v1/localization/regional-settings/{id}/ - Delete regional settings
    """

    serializer_class = RegionalSettingsSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter regional settings by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return RegionalSettings.objects.none()
        return RegionalSettings.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)
