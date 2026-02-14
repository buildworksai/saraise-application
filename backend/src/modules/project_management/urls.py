"""
URL routing for Project Management module.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .api import (
    ProjectMemberViewSet,
    ProjectMilestoneViewSet,
    ProjectViewSet,
    TaskViewSet,
    TimeEntryViewSet,
)
from .health import health_check

# Create router and register ViewSets
router = DefaultRouter()
router.register(r"projects", ProjectViewSet, basename="project")
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"members", ProjectMemberViewSet, basename="project-member")
router.register(r"time-entries", TimeEntryViewSet, basename="time-entry")
router.register(r"milestones", ProjectMilestoneViewSet, basename="project-milestone")

# URL patterns
urlpatterns = [
    path("", include(router.urls)),
    path("health/", health_check, name="health_check"),
]
