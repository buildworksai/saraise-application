"""Runtime routes for the backup/disaster-recovery v2 domain."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    BackupExecutionViewSet,
    DRExerciseViewSet,
    DRRunbookViewSet,
    DRStepExecutionViewSet,
    ObjectiveReportViewSet,
    ReadinessViewSet,
    RecoveryPointViewSet,
    RestoreRunViewSet,
    RunbookStepViewSet,
)

app_name = "backup_disaster_recovery"

router = DefaultRouter()
router.register("backup-executions", BackupExecutionViewSet, basename="backup-execution")
router.register("recovery-points", RecoveryPointViewSet, basename="recovery-point")
router.register("restore-runs", RestoreRunViewSet, basename="restore-run")
router.register("runbooks", DRRunbookViewSet, basename="runbook")
router.register("runbook-steps", RunbookStepViewSet, basename="runbook-step")
router.register("exercises", DRExerciseViewSet, basename="exercise")
router.register("step-executions", DRStepExecutionViewSet, basename="step-execution")
router.register("reports/objectives", ObjectiveReportViewSet, basename="objective-report")
router.register("readiness", ReadinessViewSet, basename="readiness")

urlpatterns = [path("", include(router.urls))]
