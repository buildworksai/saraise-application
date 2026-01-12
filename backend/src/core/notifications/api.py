"""
Notifications API ViewSets.

SPDX-License-Identifier: Apache-2.0
"""

import logging
import uuid

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id, get_user_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer
from .services import NotificationService

logger = logging.getLogger(__name__)


def _convert_user_id_to_uuid(user_id_str: str) -> uuid.UUID:
    """
    Convert Django user ID (integer as string) to UUID.
    
    Uses uuid5 with a fixed namespace to generate deterministic UUIDs
    from user IDs. This allows Notification.user_id (UUIDField) to work
    with Django's integer-based user IDs.
    """
    if not user_id_str:
        raise ValueError("user_id_str cannot be empty")
    
    # Use a fixed namespace UUID for user ID conversion
    # This ensures the same user ID always maps to the same UUID
    NAMESPACE_USER_ID = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
    
    try:
        # Try to parse as UUID first (in case it's already a UUID string)
        return uuid.UUID(user_id_str)
    except ValueError:
        # If not a UUID, generate one from the user ID using uuid5
        return uuid.uuid5(NAMESPACE_USER_ID, user_id_str)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Notification read operations."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter notifications by tenant_id and user_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)
        if not tenant_id or not user_id_str:
            return Notification.objects.none()

        # Convert user_id to UUID (Notification.user_id is UUIDField)
        try:
            user_id_uuid = _convert_user_id_to_uuid(user_id_str)
            tenant_id_uuid = uuid.UUID(tenant_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid user_id or tenant_id format: {e}")
            return Notification.objects.none()

        queryset = Notification.objects.filter(tenant_id=tenant_id_uuid, user_id=user_id_uuid)

        # Filter by read status
        unread_only = self.request.query_params.get("unread_only", "false").lower() == "true"
        if unread_only:
            queryset = queryset.filter(read=False)

        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark notification as read."""
        tenant_id = get_user_tenant_id(request.user)
        user_id_str = get_user_id(request.user)
        
        if not tenant_id or not user_id_str:
            return Response({"error": "User must belong to a tenant"}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            user_id_uuid = _convert_user_id_to_uuid(user_id_str)
            tenant_id_uuid = uuid.UUID(tenant_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid user_id or tenant_id format: {e}")
            return Response({"error": "Invalid user or tenant ID format"}, status=status.HTTP_400_BAD_REQUEST)

        success = NotificationService.mark_as_read(pk, str(tenant_id_uuid), str(user_id_uuid))
        if success:
            return Response({"success": True}, status=status.HTTP_200_OK)
        return Response({"error": "Notification not found"}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all notifications as read for the user."""
        tenant_id = get_user_tenant_id(request.user)
        user_id_str = get_user_id(request.user)
        
        if not tenant_id or not user_id_str:
            return Response({"error": "User must belong to a tenant"}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            user_id_uuid = _convert_user_id_to_uuid(user_id_str)
            tenant_id_uuid = uuid.UUID(tenant_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid user_id or tenant_id format: {e}")
            return Response({"error": "Invalid user or tenant ID format"}, status=status.HTTP_400_BAD_REQUEST)

        count = NotificationService.mark_all_read(str(tenant_id_uuid), str(user_id_uuid))
        return Response({"count": count}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Get unread notification count."""
        tenant_id = get_user_tenant_id(request.user)
        user_id_str = get_user_id(request.user)
        
        if not tenant_id or not user_id_str:
            return Response({"count": 0}, status=status.HTTP_200_OK)
        
        try:
            user_id_uuid = _convert_user_id_to_uuid(user_id_str)
            tenant_id_uuid = uuid.UUID(tenant_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid user_id or tenant_id format: {e}")
            return Response({"count": 0}, status=status.HTTP_200_OK)

        notifications = NotificationService.get_user_notifications(str(tenant_id_uuid), str(user_id_uuid), unread_only=True)
        return Response({"count": len(notifications)}, status=status.HTTP_200_OK)


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for NotificationPreference CRUD operations."""

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter preferences by tenant_id and user_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)
        if not tenant_id or not user_id_str:
            return NotificationPreference.objects.none()

        try:
            user_id_uuid = _convert_user_id_to_uuid(user_id_str)
            tenant_id_uuid = uuid.UUID(tenant_id)
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid user_id or tenant_id format: {e}")
            return NotificationPreference.objects.none()

        return NotificationPreference.objects.filter(tenant_id=tenant_id_uuid, user_id=user_id_uuid)

    def perform_create(self, serializer):
        """Set tenant_id and user_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)
        
        if not tenant_id or not user_id_str:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "User must belong to a tenant"})
        
        try:
            user_id_uuid = _convert_user_id_to_uuid(user_id_str)
            tenant_id_uuid = uuid.UUID(tenant_id)
        except (ValueError, TypeError) as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": f"Invalid user or tenant ID format: {e}"})

        serializer.save(tenant_id=tenant_id_uuid, user_id=user_id_uuid)
