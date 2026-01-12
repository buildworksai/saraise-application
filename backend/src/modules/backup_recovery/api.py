"""
DRF ViewSets for Backup & Recovery (Extended) module.
Provides REST API endpoints for all models.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import BackupArchive, BackupJob, BackupRetentionPolicy, BackupSchedule
from .serializers import (
    BackupArchiveSerializer,
    BackupJobCreateSerializer,
    BackupJobSerializer,
    BackupRetentionPolicyCreateSerializer,
    BackupRetentionPolicySerializer,
    BackupScheduleCreateSerializer,
    BackupScheduleSerializer,
)
from .services import BackupRecoveryService


class BackupJobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for BackupJob CRUD operations.

    Endpoints:
    - GET /api/v1/backup-recovery/jobs/ - List all backup jobs
    - POST /api/v1/backup-recovery/jobs/ - Create backup job
    - GET /api/v1/backup-recovery/jobs/{id}/ - Get backup job detail
    - PATCH /api/v1/backup-recovery/jobs/{id}/ - Update backup job
    - DELETE /api/v1/backup-recovery/jobs/{id}/ - Delete backup job
    """

    serializer_class = BackupJobSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter backup jobs by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return BackupJob.objects.none()
        return BackupJob.objects.filter(tenant_id=tenant_id)

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "create":
            return BackupJobCreateSerializer
        return BackupJobSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id)
        )

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a backup job."""
        job = self.get_object()
        service = BackupRecoveryService()
        updated_job = service.start_backup_job(job.id, get_user_tenant_id(request.user))
        if not updated_job:
            return Response(
                {"error": "Backup job not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(BackupJobSerializer(updated_job).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Complete a backup job."""
        job = self.get_object()
        service = BackupRecoveryService()
        backup_size_bytes = request.data.get("backup_size_bytes")
        storage_location = request.data.get("storage_location", "")
        updated_job = service.complete_backup_job(
            job.id,
            get_user_tenant_id(request.user),
            backup_size_bytes=backup_size_bytes,
            storage_location=storage_location,
        )
        if not updated_job:
            return Response(
                {"error": "Backup job not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(BackupJobSerializer(updated_job).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def fail(self, request, pk=None):
        """Mark a backup job as failed."""
        job = self.get_object()
        service = BackupRecoveryService()
        error_message = request.data.get("error_message", "")
        updated_job = service.fail_backup_job(
            job.id,
            get_user_tenant_id(request.user),
            error_message=error_message,
        )
        if not updated_job:
            return Response(
                {"error": "Backup job not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        return Response(BackupJobSerializer(updated_job).data, status=status.HTTP_200_OK)


class BackupScheduleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for BackupSchedule CRUD operations.

    Endpoints:
    - GET /api/v1/backup-recovery/schedules/ - List all schedules
    - POST /api/v1/backup-recovery/schedules/ - Create schedule
    - GET /api/v1/backup-recovery/schedules/{id}/ - Get schedule detail
    - PATCH /api/v1/backup-recovery/schedules/{id}/ - Update schedule
    - DELETE /api/v1/backup-recovery/schedules/{id}/ - Delete schedule
    """

    serializer_class = BackupScheduleSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter schedules by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return BackupSchedule.objects.none()
        return BackupSchedule.objects.filter(tenant_id=tenant_id)

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "create":
            return BackupScheduleCreateSerializer
        return BackupScheduleSerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id)
        )

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a schedule."""
        schedule = self.get_object()
        schedule.is_active = True
        schedule.save()
        return Response(BackupScheduleSerializer(schedule).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a schedule."""
        schedule = self.get_object()
        schedule.is_active = False
        schedule.save()
        return Response(BackupScheduleSerializer(schedule).data, status=status.HTTP_200_OK)


class BackupRetentionPolicyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for BackupRetentionPolicy CRUD operations.

    Endpoints:
    - GET /api/v1/backup-recovery/retention-policies/ - List all policies
    - POST /api/v1/backup-recovery/retention-policies/ - Create policy
    - GET /api/v1/backup-recovery/retention-policies/{id}/ - Get policy detail
    - PATCH /api/v1/backup-recovery/retention-policies/{id}/ - Update policy
    - DELETE /api/v1/backup-recovery/retention-policies/{id}/ - Delete policy
    """

    serializer_class = BackupRetentionPolicySerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter policies by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return BackupRetentionPolicy.objects.none()
        return BackupRetentionPolicy.objects.filter(tenant_id=tenant_id)

    def get_serializer_class(self):
        """Return appropriate serializer class."""
        if self.action == "create":
            return BackupRetentionPolicyCreateSerializer
        return BackupRetentionPolicySerializer

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id)
        )


class BackupArchiveViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for BackupArchive read operations.

    Endpoints:
    - GET /api/v1/backup-recovery/archives/ - List all archives
    - GET /api/v1/backup-recovery/archives/{id}/ - Get archive detail
    """

    serializer_class = BackupArchiveSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter archives by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return BackupArchive.objects.none()
        return BackupArchive.objects.filter(tenant_id=tenant_id).select_related("backup_job")
