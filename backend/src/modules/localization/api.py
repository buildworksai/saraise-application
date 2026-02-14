"""
DRF ViewSets for Localization module.
Provides REST API endpoints for all models.
"""

from rest_framework import viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    CurrencyConfig,
    Language,
    LocaleConfig,
    RegionalSettings,
    Translation,
)
from .serializers import (
    CurrencyConfigSerializer,
    LanguageSerializer,
    LocaleConfigSerializer,
    RegionalSettingsSerializer,
    TranslationSerializer,
)
from .services import TranslationService


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
