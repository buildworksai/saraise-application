from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .api import ConfigurationVersionViewSet, ConfigurationViewSet, MyWorkView, PortfolioDashboardView, ProjectActivityViewSet, ProjectMemberViewSet, ProjectMilestoneViewSet, ProjectViewSet, TaskViewSet, TimeEntryViewSet
from .health import ProjectManagementHealthView

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("tasks", TaskViewSet, basename="task")
router.register("members", ProjectMemberViewSet, basename="project-member")
router.register("time-entries", TimeEntryViewSet, basename="time-entry")
router.register("milestones", ProjectMilestoneViewSet, basename="project-milestone")
router.register("activities", ProjectActivityViewSet, basename="project-activity")
router.register("configuration/versions", ConfigurationVersionViewSet, basename="project-configuration-version")
router.register("configuration", ConfigurationViewSet, basename="project-configuration")

urlpatterns = [path("dashboard/", PortfolioDashboardView.as_view(), name="dashboard"), path("my-work/", MyWorkView.as_view(), name="my-work"), path("health/", ProjectManagementHealthView.as_view(), name="health_check"), path("", include(router.urls))]
