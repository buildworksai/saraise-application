"""Canonical API v2 routes for backup recovery."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    BackupArchiveViewSet,
    BackupJobViewSet,
    BackupRetentionPolicyViewSet,
    BackupScheduleViewSet,
    BackupStorageTargetViewSet,
    BackupVerificationViewSet,
    ModuleHealthViewSet,
)

app_name = "backup_recovery"

router = DefaultRouter()
router.register("jobs", BackupJobViewSet, basename="job")
router.register("schedules", BackupScheduleViewSet, basename="schedule")
router.register("retention-policies", BackupRetentionPolicyViewSet, basename="retention-policy")
router.register("storage-targets", BackupStorageTargetViewSet, basename="storage-target")
router.register("archives", BackupArchiveViewSet, basename="archive")
router.register("verifications", BackupVerificationViewSet, basename="verification")
router.register("health", ModuleHealthViewSet, basename="health")

urlpatterns = [path("", include(router.urls))]
