"""
DRF ViewSets for DataMigration module.
Provides REST API endpoints for all models.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id
from src.core.authentication import RelaxedCsrfSessionAuthentication

from .models import (
    MigrationJob,
    MigrationLog,
    MigrationMapping,
    MigrationRollback,
    MigrationValidation,
)
from .serializers import (
    MigrationJobSerializer,
    MigrationLogSerializer,
    MigrationMappingSerializer,
    MigrationRollbackSerializer,
    MigrationValidationSerializer,
)
from .services import MigrationEngine


class MigrationJobViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MigrationJob CRUD operations.

    Endpoints:
    - GET /api/v1/data-migration/jobs/ - List all jobs
    - POST /api/v1/data-migration/jobs/ - Create job
    - GET /api/v1/data-migration/jobs/{id}/ - Get job detail
    - PUT /api/v1/data-migration/jobs/{id}/ - Update job
    - DELETE /api/v1/data-migration/jobs/{id}/ - Delete job
    - POST /api/v1/data-migration/jobs/{id}/execute/ - Execute migration
    - POST /api/v1/data-migration/jobs/{id}/dry-run/ - Dry run migration
    """

    serializer_class = MigrationJobSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter jobs by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return MigrationJob.objects.none()

        queryset = MigrationJob.objects.filter(tenant_id=tenant_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by source type
        source_type = self.request.query_params.get("source_type")
        if source_type:
            queryset = queryset.filter(source_type=source_type)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """Execute migration job."""
        job = self.get_object()
        tenant_id = get_user_tenant_id(request.user)

        engine = MigrationEngine()
        result = engine.execute_migration(job.id, tenant_id, dry_run=False)

        serializer = self.get_serializer(job)
        return Response(
            {
                "job": serializer.data,
                "result": {
                    "success": result.success,
                    "records_processed": result.records_processed,
                    "records_failed": result.records_failed,
                    "errors": result.errors[:10],  # Limit to first 10 errors
                },
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def dry_run(self, request, pk=None):
        """Dry run migration (validate without importing)."""
        job = self.get_object()
        tenant_id = get_user_tenant_id(request.user)

        engine = MigrationEngine()
        result = engine.execute_migration(job.id, tenant_id, dry_run=True)

        serializer = self.get_serializer(job)
        return Response(
            {
                "job": serializer.data,
                "result": {
                    "success": result.success,
                    "records_processed": result.records_processed,
                    "records_failed": result.records_failed,
                    "errors": result.errors[:10],
                },
            },
            status=status.HTTP_200_OK,
        )


class MigrationMappingViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MigrationMapping CRUD operations.

    Endpoints:
    - GET /api/v1/data-migration/mappings/ - List all mappings
    - POST /api/v1/data-migration/mappings/ - Create mapping
    - GET /api/v1/data-migration/mappings/{id}/ - Get mapping detail
    - PUT /api/v1/data-migration/mappings/{id}/ - Update mapping
    - DELETE /api/v1/data-migration/mappings/{id}/ - Delete mapping
    """

    serializer_class = MigrationMappingSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter mappings by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return MigrationMapping.objects.none()

        queryset = MigrationMapping.objects.filter(tenant_id=tenant_id)

        # Filter by job
        job_id = self.request.query_params.get("job_id")
        if job_id:
            queryset = queryset.filter(job_id=job_id)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("User must belong to a tenant")
        serializer.save(tenant_id=tenant_id)


class MigrationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for MigrationLog read operations.

    Endpoints:
    - GET /api/v1/data-migration/logs/ - List all logs
    - GET /api/v1/data-migration/logs/{id}/ - Get log detail
    """

    serializer_class = MigrationLogSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter logs by job tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return MigrationLog.objects.none()

        queryset = MigrationLog.objects.filter(tenant_id=tenant_id)

        # Filter by job
        job_id = self.request.query_params.get("job_id")
        if job_id:
            queryset = queryset.filter(job_id=job_id)

        # Filter by level
        level = self.request.query_params.get("level")
        if level:
            queryset = queryset.filter(level=level)

        return queryset.order_by("-timestamp")


class MigrationValidationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for MigrationValidation read operations.

    Endpoints:
    - GET /api/v1/data-migration/validations/ - List all validations
    - GET /api/v1/data-migration/validations/{id}/ - Get validation detail
    """

    serializer_class = MigrationValidationSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        """Filter validations by job tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return MigrationValidation.objects.none()

        queryset = MigrationValidation.objects.filter(tenant_id=tenant_id)

        # Filter by job
        job_id = self.request.query_params.get("job_id")
        if job_id:
            queryset = queryset.filter(job_id=job_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset.order_by("-created_at")
