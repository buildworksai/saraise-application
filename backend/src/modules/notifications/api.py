"""
DRF ViewSets for Notifications module.
"""

import uuid
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_id, get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import Notification, NotificationPreference
from .serializers import NotificationPreferenceSerializer, NotificationSerializer


class NotificationViewSet(viewsets.ModelViewSet):
    """ViewSet for Notification CRUD operations."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter notifications by tenant_id and user_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)
        if not tenant_id_str or not user_id_str:
            return Notification.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            return Notification.objects.none()

        queryset = Notification.objects.filter(tenant_id=tenant_id, user_id=user_id)
        # Filter by status if provided
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("-created_at")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        """Mark notification as read."""
        notification = self.get_object()
        from django.utils import timezone
        notification.status = "read"
        notification.read_at = timezone.now()
        notification.save()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all notifications as read."""
        queryset = self.get_queryset().filter(status="unread")
        from django.utils import timezone
        queryset.update(status="read", read_at=timezone.now())
        return Response({"count": queryset.count()})


class NotificationPreferenceViewSet(viewsets.ModelViewSet):
    """ViewSet for NotificationPreference CRUD operations."""

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter preferences by tenant_id and user_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)
        if not tenant_id_str or not user_id_str:
            return NotificationPreference.objects.none()

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            return NotificationPreference.objects.none()

        queryset = NotificationPreference.objects.filter(tenant_id=tenant_id, user_id=user_id)
        return queryset.order_by("channel", "notification_type")

    def perform_create(self, serializer):
        """Set tenant_id and user_id from authenticated user."""
        tenant_id_str = get_user_tenant_id(self.request.user)
        user_id_str = get_user_id(self.request.user)
        if not tenant_id_str or not user_id_str:
            raise PermissionDenied("User must belong to a tenant")

        try:
            tenant_id = uuid.UUID(tenant_id_str)
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            raise PermissionDenied("Invalid tenant_id or user_id format")

        serializer.save(tenant_id=tenant_id, user_id=user_id)
