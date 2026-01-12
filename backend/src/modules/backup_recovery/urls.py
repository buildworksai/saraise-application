"""
URL routing for Backup & Recovery (Extended) module.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import (
    BackupArchiveViewSet,
    BackupJobViewSet,
    BackupRetentionPolicyViewSet,
    BackupScheduleViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r'jobs', BackupJobViewSet, basename='backup-job')
router.register(r'schedules', BackupScheduleViewSet, basename='backup-schedule')
router.register(r'retention-policies', BackupRetentionPolicyViewSet, basename='retention-policy')
router.register(r'archives', BackupArchiveViewSet, basename='backup-archive')

# URL patterns
urlpatterns = [
    path('', include(router.urls)),
    path('health/', health_check, name='health_check'),
]
