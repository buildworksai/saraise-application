"""Governed, tenant-isolated API v2 boundary for backup recovery."""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone
from rest_framework import filters, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from src.core.access import RequiresAccess
from src.core.api import GovernedAPIViewMixin, GovernedPageNumberPagination
from src.core.api.envelope import utc_timestamp
from src.core.views.tenant_scoped import TenantScopedModelViewSet, TenantScopedReadOnlyModelViewSet

from .health import check_module_health
from .models import (
    BackupArchive,
    BackupJob,
    BackupRetentionPolicy,
    BackupSchedule,
    BackupStorageTarget,
    BackupVerification,
)
from .permissions import access_rule
from .serializers import (
    BackupArchiveDetailSerializer,
    BackupArchiveListSerializer,
    BackupJobCancelSerializer,
    BackupJobCreateSerializer,
    BackupJobDetailSerializer,
    BackupJobListSerializer,
    BackupJobRetrySerializer,
    BackupJobUpdateSerializer,
    BackupRequestReceiptSerializer,
    BackupRetentionPolicyCreateSerializer,
    BackupRetentionPolicyDetailSerializer,
    BackupRetentionPolicyListSerializer,
    BackupRetentionPolicyUpdateSerializer,
    BackupScheduleCreateSerializer,
    BackupScheduleDetailSerializer,
    BackupScheduleListSerializer,
    BackupScheduleUpdateSerializer,
    BackupStorageTargetCreateSerializer,
    BackupStorageTargetDetailSerializer,
    BackupStorageTargetListSerializer,
    BackupStorageTargetUpdateSerializer,
    BackupVerificationCancelSerializer,
    BackupVerificationCreateSerializer,
    BackupVerificationDetailSerializer,
    BackupVerificationListSerializer,
    ModuleHealthSerializer,
    RetentionPreviewSerializer,
    ScheduleRunNowSerializer,
    StorageTargetProbeSerializer,
)
from .services import (
    BackupArtifactService,
    BackupRecoveryService,
    BackupScheduleService,
    RetentionPolicyService,
    StorageTargetService,
)


def _actor(request) -> str:
    return str(request.user.pk)


def _receipt_payload(receipt, job: BackupJob) -> dict[str, object]:
    return {
        "job_id": receipt.backup_job_id,
        "async_job_id": job.async_job_id,
        "status": receipt.status.value,
        "idempotency_key": receipt.idempotency_key,
    }


class AccessControlledMixin:
    permission_classes = (RequiresAccess,)
    authentication_classes = (SessionAuthentication,)
    pagination_class = GovernedPageNumberPagination
    access_resource = ""

    def get_permissions(self):
        self.request.tenant_id = self._get_tenant_id()
        action_name = getattr(self, "action", None)
        if action_name is None:
            return ()
        rule = access_rule(self.access_resource, action_name)
        self.required_permission = rule.permission if rule else None
        self.required_entitlement = rule.required_entitlement if rule else None
        self.quota_resource = rule.quota_resource if rule else None
        self.quota_cost = rule.quota_cost if rule else 0
        return super().get_permissions()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        error = response.data.get("error") if isinstance(response.data, dict) else None
        if response.status_code >= 400 and isinstance(error, dict):
            response.data.setdefault(
                "meta",
                {
                    "correlation_id": error.get("correlation_id"),
                    "timestamp": utc_timestamp(),
                },
            )
        return response


class BackupJobViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedModelViewSet):
    queryset = BackupJob.objects.select_related("schedule", "storage_target", "retention_policy")
    access_resource = "jobs"
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("description", "=id")
    ordering_fields = ("requested_at", "completed_at", "size_bytes")
    ordering = ("-requested_at",)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        tenant = self._require_tenant_id()
        values = {
            key: self.request.query_params.get(key)
            for key in (
                "status",
                "backup_type",
                "schedule_id",
                "scope_type",
                "scope_ref",
                "requested_after",
                "requested_before",
            )
        }
        return (
            BackupRecoveryService()
            .list_backup_jobs(tenant, values)
            .select_related("schedule", "storage_target", "retention_policy")
        )

    def get_serializer_class(self):
        return {
            "list": BackupJobListSerializer,
            "retrieve": BackupJobDetailSerializer,
            "create": BackupJobCreateSerializer,
            "partial_update": BackupJobUpdateSerializer,
            "cancel": BackupJobCancelSerializer,
            "retry": BackupJobRetrySerializer,
        }.get(self.action, BackupJobDetailSerializer)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = BackupRecoveryService().request_backup(
            self._require_tenant_id(), _actor(request), **serializer.validated_data
        )
        job = BackupRecoveryService().get_backup_job(self._require_tenant_id(), receipt.backup_job_id)
        return Response(
            BackupRequestReceiptSerializer(_receipt_payload(receipt, job)).data, status=status.HTTP_202_ACCEPTED
        )

    def partial_update(self, request, *args, **kwargs):
        job = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = BackupRecoveryService().update_job_description(
            self._require_tenant_id(), _actor(request), job.id, serializer.validated_data["description"]
        )
        return Response(BackupJobDetailSerializer(job).data)

    def destroy(self, request, *args, **kwargs):
        job = self.get_object()
        BackupRecoveryService().soft_delete_job(self._require_tenant_id(), _actor(request), job.id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        job = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = BackupRecoveryService().cancel_backup(
            self._require_tenant_id(), _actor(request), job.id, serializer.validated_data["transition_key"]
        )
        return Response(BackupJobDetailSerializer(job).data)

    @action(detail=True, methods=("post",))
    def retry(self, request, pk=None):
        job = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = BackupRecoveryService().retry_backup(
            self._require_tenant_id(), _actor(request), job.id, serializer.validated_data["idempotency_key"]
        )
        retried = BackupRecoveryService().get_backup_job(self._require_tenant_id(), receipt.backup_job_id)
        return Response(
            BackupRequestReceiptSerializer(_receipt_payload(receipt, retried)).data,
            status=status.HTTP_202_ACCEPTED,
        )


class BackupScheduleViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedModelViewSet):
    queryset = BackupSchedule.objects.select_related("storage_target", "retention_policy")
    access_resource = "schedules"
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("name", "description", "scope_ref")
    ordering_fields = ("name", "next_run_at", "created_at")
    ordering = ("name",)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        tenant = self._require_tenant_id()
        values = {
            key: self.request.query_params.get(key)
            for key in ("is_active", "frequency", "backup_type", "scope_type", "storage_target_id")
        }
        if values["is_active"] is not None:
            values["is_active"] = values["is_active"].lower() == "true"
        return BackupScheduleService().list(tenant, values).select_related("storage_target", "retention_policy")

    def get_serializer_class(self):
        return {
            "list": BackupScheduleListSerializer,
            "retrieve": BackupScheduleDetailSerializer,
            "create": BackupScheduleCreateSerializer,
            "partial_update": BackupScheduleUpdateSerializer,
            "run_now": ScheduleRunNowSerializer,
        }.get(self.action, BackupScheduleDetailSerializer)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schedule = BackupScheduleService().create(self._require_tenant_id(), _actor(request), serializer.validated_data)
        return Response(BackupScheduleDetailSerializer(schedule).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        schedule = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        schedule = BackupScheduleService().update(
            self._require_tenant_id(), _actor(request), schedule.id, serializer.validated_data
        )
        return Response(BackupScheduleDetailSerializer(schedule).data)

    def destroy(self, request, *args, **kwargs):
        BackupScheduleService().delete(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        schedule = BackupScheduleService().activate(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupScheduleDetailSerializer(schedule).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        schedule = BackupScheduleService().deactivate(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupScheduleDetailSerializer(schedule).data)

    @action(detail=True, methods=("post",), url_path="run-now")
    def run_now(self, request, pk=None):
        schedule = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = BackupScheduleService().run_now(
            self._require_tenant_id(), _actor(request), schedule.id, serializer.validated_data["idempotency_key"]
        )
        payload = {
            "job_id": job.id,
            "async_job_id": job.async_job_id,
            "status": job.status,
            "idempotency_key": job.idempotency_key,
        }
        return Response(BackupRequestReceiptSerializer(payload).data, status=status.HTTP_202_ACCEPTED)


class BackupRetentionPolicyViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedModelViewSet):
    queryset = BackupRetentionPolicy.objects.all()
    access_resource = "retention-policies"
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("name", "description")
    ordering_fields = ("name", "retention_days", "created_at")
    ordering = ("name",)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        value = self.request.query_params.get("is_active")
        return RetentionPolicyService().list(
            self._require_tenant_id(), {"is_active": value.lower() == "true" if value is not None else None}
        )

    def get_serializer_class(self):
        return {
            "list": BackupRetentionPolicyListSerializer,
            "retrieve": BackupRetentionPolicyDetailSerializer,
            "create": BackupRetentionPolicyCreateSerializer,
            "partial_update": BackupRetentionPolicyUpdateSerializer,
            "preview": RetentionPreviewSerializer,
        }.get(self.action, BackupRetentionPolicyDetailSerializer)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = RetentionPolicyService().create(self._require_tenant_id(), _actor(request), serializer.validated_data)
        return Response(BackupRetentionPolicyDetailSerializer(policy).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        policy = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = RetentionPolicyService().update(
            self._require_tenant_id(), _actor(request), policy.id, serializer.validated_data
        )
        return Response(BackupRetentionPolicyDetailSerializer(policy).data)

    def destroy(self, request, *args, **kwargs):
        RetentionPolicyService().delete(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        policy = RetentionPolicyService().activate(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupRetentionPolicyDetailSerializer(policy).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        policy = RetentionPolicyService().deactivate(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupRetentionPolicyDetailSerializer(policy).data)

    @action(detail=True, methods=("get",))
    def preview(self, request, pk=None):
        captured_at = request.query_params.get("captured_at")
        parsed = datetime.fromisoformat(captured_at.replace("Z", "+00:00")) if captured_at else timezone.now()
        result = RetentionPolicyService().preview(self._require_tenant_id(), self.get_object().id, captured_at=parsed)
        return Response(RetentionPreviewSerializer(result).data)


class BackupStorageTargetViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedModelViewSet):
    queryset = BackupStorageTarget.objects.all()
    access_resource = "storage-targets"
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")
    ordering = ("name",)
    http_method_names = ("get", "post", "patch", "delete", "head", "options")

    def get_queryset(self):
        values = {key: self.request.query_params.get(key) for key in ("is_active", "is_default", "adapter_key")}
        for key in ("is_active", "is_default"):
            if values[key] is not None:
                values[key] = values[key].lower() == "true"
        return StorageTargetService().list(self._require_tenant_id(), values)

    def get_serializer_class(self):
        return {
            "list": BackupStorageTargetListSerializer,
            "retrieve": BackupStorageTargetDetailSerializer,
            "create": BackupStorageTargetCreateSerializer,
            "partial_update": BackupStorageTargetUpdateSerializer,
            "probe": StorageTargetProbeSerializer,
        }.get(self.action, BackupStorageTargetDetailSerializer)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = StorageTargetService().create(self._require_tenant_id(), _actor(request), serializer.validated_data)
        return Response(BackupStorageTargetDetailSerializer(target).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        target = StorageTargetService().update(
            self._require_tenant_id(), _actor(request), target.id, serializer.validated_data
        )
        return Response(BackupStorageTargetDetailSerializer(target).data)

    def destroy(self, request, *args, **kwargs):
        StorageTargetService().delete(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        target = StorageTargetService().activate(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupStorageTargetDetailSerializer(target).data)

    @action(detail=True, methods=("post",))
    def deactivate(self, request, pk=None):
        target = StorageTargetService().deactivate(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupStorageTargetDetailSerializer(target).data)

    @action(detail=True, methods=("post",), url_path="set-default")
    def set_default(self, request, pk=None):
        target = StorageTargetService().set_default(self._require_tenant_id(), _actor(request), self.get_object().id)
        return Response(BackupStorageTargetDetailSerializer(target).data)

    @action(detail=True, methods=("post",))
    def probe(self, request, pk=None):
        result = StorageTargetService().probe(self._require_tenant_id(), _actor(request), self.get_object().id)
        health = result.unwrap()
        return Response(StorageTargetProbeSerializer(health).data)


class BackupArchiveViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedReadOnlyModelViewSet):
    queryset = BackupArchive.objects.select_related("backup_job")
    access_resource = "archives"
    filter_backends = (filters.SearchFilter, filters.OrderingFilter)
    search_fields = ("=id", "=backup_job__id")
    ordering_fields = ("captured_at", "expires_at", "size_bytes")
    ordering = ("-captured_at",)

    def get_queryset(self):
        values = {
            key: self.request.query_params.get(key)
            for key in ("lifecycle", "integrity_status", "backup_job_id", "expires_before", "captured_after")
        }
        queryset = BackupArtifactService().list(self._require_tenant_id(), values).select_related("backup_job")
        backup_type = self.request.query_params.get("backup_type")
        return queryset.filter(backup_job__backup_type=backup_type) if backup_type else queryset

    def get_serializer_class(self):
        return BackupArchiveListSerializer if self.action == "list" else BackupArchiveDetailSerializer

    @action(detail=True, methods=("post",))
    def verify(self, request, pk=None):
        archive = self.get_object()
        serializer = BackupVerificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = BackupArtifactService().request_verification(
            self._require_tenant_id(), _actor(request), archive.id, serializer.validated_data["idempotency_key"]
        )
        return Response(BackupVerificationDetailSerializer(verification).data, status=status.HTTP_202_ACCEPTED)


class BackupVerificationViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedReadOnlyModelViewSet):
    queryset = BackupVerification.objects.select_related("archive")
    access_resource = "verifications"
    filter_backends = (filters.OrderingFilter,)
    ordering_fields = ("requested_at", "completed_at")
    ordering = ("-requested_at",)

    def get_queryset(self):
        tenant = self._require_tenant_id()
        queryset = super().get_queryset()
        mapping = {
            "status": "status",
            "archive_id": "archive_id",
            "requested_after": "requested_at__gte",
            "requested_before": "requested_at__lte",
        }
        for key, lookup in mapping.items():
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{lookup: value})
        return queryset.filter(tenant_id=tenant)

    def get_serializer_class(self):
        return BackupVerificationListSerializer if self.action == "list" else BackupVerificationDetailSerializer

    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        verification = self.get_object()
        serializer = BackupVerificationCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = BackupArtifactService().cancel_verification(
            self._require_tenant_id(), _actor(request), verification.id, serializer.validated_data["transition_key"]
        )
        return Response(BackupVerificationDetailSerializer(verification).data)


class ModuleHealthViewSet(GovernedAPIViewMixin, AccessControlledMixin, TenantScopedReadOnlyModelViewSet):
    queryset = BackupStorageTarget.objects.all()
    access_resource = "health"
    http_method_names = ("get", "head", "options")

    def list(self, request, *args, **kwargs):
        report = check_module_health(self._require_tenant_id())
        serializer = ModuleHealthSerializer(report)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK if report["ready"] else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
