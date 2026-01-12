"""
DRF ViewSets for IntegrationPlatform module.
Provides REST API endpoints for all models.
"""

import secrets

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    Connector,
    DataMapping,
    Integration,
    IntegrationCredential,
    Webhook,
    WebhookDelivery,
)
from .serializers import (
    ConnectorSerializer,
    DataMappingSerializer,
    IntegrationCredentialSerializer,
    IntegrationSerializer,
    WebhookDeliverySerializer,
    WebhookSerializer,
)
from .services import WebhookService


class IntegrationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Integration CRUD operations.

    Endpoints:
    - GET /api/v1/integration-platform/integrations/ - List all integrations
    - POST /api/v1/integration-platform/integrations/ - Create integration
    - GET /api/v1/integration-platform/integrations/{id}/ - Get integration detail
    - PUT /api/v1/integration-platform/integrations/{id}/ - Update integration
    - PATCH /api/v1/integration-platform/integrations/{id}/ - Partial update integration
    - DELETE /api/v1/integration-platform/integrations/{id}/ - Delete integration
    - POST /api/v1/integration-platform/integrations/{id}/test/ - Test integration
    - POST /api/v1/integration-platform/integrations/{id}/sync/ - Sync integration
    """

    serializer_class = IntegrationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter integrations by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Integration.objects.none()

        queryset = Integration.objects.filter(tenant_id=tenant_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by type
        integration_type = self.request.query_params.get("integration_type")
        if integration_type:
            queryset = queryset.filter(integration_type=integration_type)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Test integration connection."""
        from .services import IntegrationService

        integration = self.get_object()
        result = IntegrationService.test_connection(integration)

        if result.get("success"):
            # Update integration status
            integration.status = "active"
            integration.save(update_fields=["status"])
            return Response(result, status=status.HTTP_200_OK)
        else:
            integration.status = "error"
            integration.save(update_fields=["status"])
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        """Sync integration data."""
        from .services import IntegrationService

        integration = self.get_object()
        direction = request.data.get("direction", "pull")
        data_mapping_id = request.data.get("data_mapping_id")

        result = IntegrationService.sync_integration(integration, direction, data_mapping_id)

        if result.get("success"):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class IntegrationCredentialViewSet(viewsets.ModelViewSet):
    """
    ViewSet for IntegrationCredential CRUD operations.

    Endpoints:
    - GET /api/v1/integration-platform/integration-credentials/ - List all credentials
    - POST /api/v1/integration-platform/integration-credentials/ - Create credential
    - GET /api/v1/integration-platform/integration-credentials/{id}/ - Get credential detail
    - PUT /api/v1/integration-platform/integration-credentials/{id}/ - Update credential
    - DELETE /api/v1/integration-platform/integration-credentials/{id}/ - Delete credential
    """

    serializer_class = IntegrationCredentialSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter credentials by integration tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return IntegrationCredential.objects.none()

        queryset = IntegrationCredential.objects.filter(integration__tenant_id=tenant_id)

        # Filter by integration
        integration_id = self.request.query_params.get("integration_id")
        if integration_id:
            queryset = queryset.filter(integration_id=integration_id)

        return queryset.order_by("-created_at")


class WebhookViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Webhook CRUD operations.

    Endpoints:
    - GET /api/v1/integration-platform/webhooks/ - List all webhooks
    - POST /api/v1/integration-platform/webhooks/ - Create webhook
    - GET /api/v1/integration-platform/webhooks/{id}/ - Get webhook detail
    - PUT /api/v1/integration-platform/webhooks/{id}/ - Update webhook
    - DELETE /api/v1/integration-platform/webhooks/{id}/ - Delete webhook
    """

    serializer_class = WebhookSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter webhooks by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Webhook.objects.none()

        queryset = Webhook.objects.filter(tenant_id=tenant_id)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id, created_by, and generate secret."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")

        # Generate secret for webhook
        webhook_secret = secrets.token_urlsafe(32)
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id),
            secret=webhook_secret,
        )


class WebhookReceiveView(APIView):
    """
    Public endpoint for receiving incoming webhooks.

    Endpoints:
    - POST /api/v1/integration-platform/webhooks/receive/{webhook_id}/ - Receive webhook
    """

    permission_classes = [AllowAny]  # Public endpoint for external systems

    def post(self, request, webhook_id):
        """Receive incoming webhook."""
        try:
            webhook = Webhook.objects.get(id=webhook_id, is_active=True)
        except Webhook.DoesNotExist:
            return Response({"error": "Webhook not found"}, status=status.HTTP_404_NOT_FOUND)

        # Verify signature if provided
        signature = request.headers.get("X-Webhook-Signature")
        if signature:
            service = WebhookService()
            if not service.verify_signature(webhook.secret, request.data, signature):
                return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        # Process webhook
        from .services import WebhookProcessor

        event_type = request.headers.get("X-Webhook-Event")
        payload = request.data if hasattr(request, "data") else {}

        result = WebhookProcessor.process_webhook(webhook, payload, event_type)

        # Log webhook delivery
        from .models import WebhookDelivery

        WebhookDelivery.objects.create(
            webhook=webhook,
            event=event_type or "unknown",
            payload=payload,
            status="delivered" if result.get("success") else "failed",
            response_code=200 if result.get("success") else 400,
            response_body=str(result),
            delivered_at=timezone.now(),
        )

        if result.get("success"):
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)


class WebhookDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for WebhookDelivery read operations.

    Endpoints:
    - GET /api/v1/integration-platform/webhook-deliveries/ - List all deliveries
    - GET /api/v1/integration-platform/webhook-deliveries/{id}/ - Get delivery detail
    """

    serializer_class = WebhookDeliverySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter deliveries by webhook tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return WebhookDelivery.objects.none()

        queryset = WebhookDelivery.objects.filter(webhook__tenant_id=tenant_id)

        # Filter by webhook
        webhook_id = self.request.query_params.get("webhook_id")
        if webhook_id:
            queryset = queryset.filter(webhook_id=webhook_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")


class ConnectorViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Connector read operations (platform-level).

    Endpoints:
    - GET /api/v1/integration-platform/connectors/ - List all connectors
    - GET /api/v1/integration-platform/connectors/{id}/ - Get connector detail
    - GET /api/v1/integration-platform/connectors/{id}/schema/ - Get connector schema
    """

    serializer_class = ConnectorSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """List all active connectors (platform-level, no tenant filtering)."""
        queryset = Connector.objects.filter(is_active=True)

        # Filter by type
        connector_type = self.request.query_params.get("connector_type")
        if connector_type:
            queryset = queryset.filter(connector_type=connector_type)

        return queryset.order_by("name")

    @action(detail=True, methods=["get"], url_path="schema")
    def get_connector_schema(self, request, pk=None):
        """Get connector schema."""
        connector = self.get_object()
        return Response(connector.schema, status=status.HTTP_200_OK)


class DataMappingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for DataMapping CRUD operations.

    Endpoints:
    - GET /api/v1/integration-platform/data-mappings/ - List all mappings
    - POST /api/v1/integration-platform/data-mappings/ - Create mapping
    - GET /api/v1/integration-platform/data-mappings/{id}/ - Get mapping detail
    - PUT /api/v1/integration-platform/data-mappings/{id}/ - Update mapping
    - DELETE /api/v1/integration-platform/data-mappings/{id}/ - Delete mapping
    """

    serializer_class = DataMappingSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter mappings by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return DataMapping.objects.none()

        queryset = DataMapping.objects.filter(tenant_id=tenant_id)

        # Filter by integration
        integration_id = self.request.query_params.get("integration_id")
        if integration_id:
            queryset = queryset.filter(integration_id=integration_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)
