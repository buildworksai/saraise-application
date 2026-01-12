"""
DRF ViewSets for AiProviderConfiguration module.
Provides REST API endpoints for all models.
"""

import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

logger = logging.getLogger(__name__)

from .models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderCredential,
    AIUsageLog,
)
from .serializers import (
    AIModelDeploymentSerializer,
    AIModelSerializer,
    AIProviderCredentialSerializer,
    AIProviderSerializer,
    AIUsageLogSerializer,
)


class AIProviderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AIProvider read operations (platform-level).

    Endpoints:
    - GET /api/v1/ai-provider-configuration/providers/ - List all providers
    - GET /api/v1/ai-provider-configuration/providers/{id}/ - Get provider detail
    """

    serializer_class = AIProviderSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """List all active providers (platform-level, no tenant filtering)."""
        queryset = AIProvider.objects.filter(is_active=True)

        # Filter by type
        provider_type = self.request.query_params.get("provider_type")
        if provider_type:
            queryset = queryset.filter(provider_type=provider_type)

        return queryset.order_by("name")


class AIProviderCredentialViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AIProviderCredential CRUD operations.

    Endpoints:
    - GET /api/v1/ai-provider-configuration/credentials/ - List all credentials
    - POST /api/v1/ai-provider-configuration/credentials/ - Create credential
    - GET /api/v1/ai-provider-configuration/credentials/{id}/ - Get credential detail
    - PUT /api/v1/ai-provider-configuration/credentials/{id}/ - Update credential
    - DELETE /api/v1/ai-provider-configuration/credentials/{id}/ - Delete credential
    """

    serializer_class = AIProviderCredentialSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter credentials by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return AIProviderCredential.objects.none()

        queryset = AIProviderCredential.objects.filter(tenant_id=tenant_id)

        # Filter by provider
        provider_id = self.request.query_params.get("provider_id")
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)


class AIModelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AIModel read operations (platform-level).

    Endpoints:
    - GET /api/v1/ai-provider-configuration/models/ - List all models
    - GET /api/v1/ai-provider-configuration/models/{id}/ - Get model detail
    """

    serializer_class = AIModelSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """List all active models (platform-level, no tenant filtering)."""
        queryset = AIModel.objects.filter(is_active=True)

        # Filter by provider
        provider_id = self.request.query_params.get("provider_id")
        if provider_id:
            queryset = queryset.filter(provider_id=provider_id)

        return queryset.order_by("display_name")


class AIModelDeploymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for AIModelDeployment CRUD operations.

    Endpoints:
    - GET /api/v1/ai-provider-configuration/deployments/ - List all deployments
    - POST /api/v1/ai-provider-configuration/deployments/ - Create deployment
    - GET /api/v1/ai-provider-configuration/deployments/{id}/ - Get deployment detail
    - PUT /api/v1/ai-provider-configuration/deployments/{id}/ - Update deployment
    - DELETE /api/v1/ai-provider-configuration/deployments/{id}/ - Delete deployment
    """

    serializer_class = AIModelDeploymentSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter deployments by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return AIModelDeployment.objects.none()

        queryset = AIModelDeployment.objects.filter(tenant_id=tenant_id)

        # Filter by model
        model_id = self.request.query_params.get("model_id")
        if model_id:
            queryset = queryset.filter(model_id=model_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))


class AIUsageLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AIUsageLog read operations.

    Endpoints:
    - GET /api/v1/ai-provider-configuration/usage-logs/ - List all usage logs
    - GET /api/v1/ai-provider-configuration/usage-logs/{id}/ - Get usage log detail
    """

    serializer_class = AIUsageLogSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter usage logs by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return AIUsageLog.objects.none()

        queryset = AIUsageLog.objects.filter(tenant_id=tenant_id)

        # Filter by deployment
        deployment_id = self.request.query_params.get("deployment_id")
        if deployment_id:
            queryset = queryset.filter(deployment_id=deployment_id)

        return queryset.order_by("-timestamp")


class SecretManagementViewSet(viewsets.ViewSet):
    """
    ViewSet for secret management operations (key rotation, re-encryption).

    Endpoints:
    - POST /api/v1/ai-provider-configuration/secrets/rotate-key/ - Generate new encryption key
    - POST /api/v1/ai-provider-configuration/secrets/re-encrypt/ - Re-encrypt all secrets
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    @action(detail=False, methods=["post"])
    def rotate_key(self, request):
        """Generate a new encryption key.

        Returns:
            New base64-encoded encryption key.
        """
        from src.core.encryption import EncryptionService

        new_key = EncryptionService.rotate_key()
        return Response(
            {
                "new_key": new_key,
                "message": "New encryption key generated. Save it securely and use it to re-encrypt existing secrets.",
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"])
    def re_encrypt(self, request):
        """Re-encrypt all credentials with a new key.

        Request body:
            - old_key: Old encryption key (base64-encoded)
            - new_key: New encryption key (base64-encoded)

        Returns:
            Number of re-encrypted secrets.
        """
        from src.core.encryption import EncryptionService
        from src.core.auth_utils import get_user_tenant_id

        tenant_id = get_user_tenant_id(request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")

        old_key = request.data.get("old_key")
        new_key = request.data.get("new_key")

        if not old_key or not new_key:
            return Response(
                {"error": "old_key and new_key are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get all credentials for this tenant
        credentials = AIProviderCredential.objects.filter(tenant_id=tenant_id)
        re_encrypted_count = 0

        for credential in credentials:
            try:
                # Re-encrypt with new key
                new_encrypted = EncryptionService.re_encrypt(
                    credential.api_key_encrypted, old_key, new_key
                )
                credential.api_key_encrypted = new_encrypted
                credential.save()
                re_encrypted_count += 1
            except Exception as e:
                logger.error(f"Failed to re-encrypt credential {credential.id}: {e}")
                # Continue with other credentials

        return Response(
            {
                "success": True,
                "re_encrypted_count": re_encrypted_count,
                "message": f"Re-encrypted {re_encrypted_count} secrets successfully",
            },
            status=status.HTTP_200_OK,
        )
