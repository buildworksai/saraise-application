"""
API tests for Project Management module.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.project_management import api as project_api
from src.modules.project_management.models import (
    ConfigurationState,
    Project,
    ProjectActivity,
    ProjectManagementConfiguration,
    ProjectManagementConfigurationVersion,
    ProjectMember,
    ProjectMilestone,
    Task,
    TimeEntry,
)

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def authenticated_user(db):
    """Create authenticated user with tenant."""
    from unittest.mock import patch

    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_id(authenticated_user):
    return uuid.UUID(authenticated_user.profile.tenant_id)


@pytest.fixture
def authenticated_client(api_client, authenticated_user):
    api_client.force_authenticate(user=authenticated_user)
    return api_client


@pytest.fixture
def project(tenant_id):
    return Project.objects.create(
        tenant_id=tenant_id,
        project_code="PROJ-001",
        project_name="Test Project",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        project_manager_id=uuid.uuid4(),
        budget=Decimal("1000.00"),
    )


@pytest.fixture
def task(tenant_id, project):
    return Task.objects.create(
        tenant_id=tenant_id,
        project=project,
        task_code="TASK-001",
        task_name="Implementation",
        due_date=date(2026, 2, 1),
        assigned_to_id=uuid.uuid4(),
        priority="high",
    )


@pytest.mark.django_db
class TestProjectAPI:
    """Test Project API endpoints."""

    def test_list_projects(self, api_client, authenticated_user):
        """Test listing projects."""
        tenant_id = uuid.UUID(authenticated_user.profile.tenant_id)

        Project.objects.create(
            tenant_id=tenant_id,
            project_code="PROJ-001",
            project_name="Test Project",
        )

        api_client.force_authenticate(user=authenticated_user)
        response = api_client.get("/api/v1/project-management/projects/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

    def test_create_project(self, api_client, authenticated_user):
        """Test creating a project."""
        api_client.force_authenticate(user=authenticated_user)

        data = {
            "project_code": "PROJ-002",
            "project_name": "Another Project",
        }

        response = api_client.post("/api/v1/project-management/projects/", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["project_code"] == "PROJ-002"


@pytest.mark.django_db
def test_project_filters_invalid_inputs_and_lifecycle_delegate(authenticated_client, project, monkeypatch):
    response = authenticated_client.get("/api/v1/project-management/projects/?include_archived=maybe")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = authenticated_client.get("/api/v1/project-management/projects/?start_from=01-01-2026")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = authenticated_client.get("/api/v1/project-management/projects/?ordering=budget")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    seen = {}

    def transition(tenant_id, actor_id, project_id, command, transition_key, reason):
        seen["transition"] = (tenant_id, actor_id, project_id, command, transition_key, reason)
        project.status = "active"
        return project

    def duplicate(tenant_id, actor_id, project_id, project_code, project_name, idempotency_key):
        seen["duplicate"] = (tenant_id, actor_id, project_id, project_code, project_name, idempotency_key)
        return Project.objects.create(tenant_id=tenant_id, project_code=project_code, project_name=project_name)

    monkeypatch.setattr(project_api.ProjectService, "transition_project", transition)
    monkeypatch.setattr(project_api.ProjectService, "duplicate_project", duplicate)
    monkeypatch.setattr(
        project_api.ProjectService,
        "get_project_summary",
        lambda tenant, project_id: {
            "project_id": project.id,
            "task_count": 1,
            "completed_task_count": 0,
            "blocked_task_count": 0,
            "progress_percentage": Decimal("0.00"),
            "milestone_count": 0,
            "achieved_milestone_count": 0,
            "time_hours": Decimal("0.00"),
            "next_due_date": None,
        },
    )

    response = authenticated_client.post(
        f"/api/v1/project-management/projects/{project.id}/activate/",
        {"transition_key": "activate-1", "reason": "ready"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert seen["transition"][3:] == ("activate", "activate-1", "ready")

    response = authenticated_client.get(f"/api/v1/project-management/projects/{project.id}/summary/")
    assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/projects/{project.id}/duplicate/",
        {"project_code": "PROJ-CLONE", "project_name": "Clone", "idempotency_key": "project-duplicate"},
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert seen["duplicate"][3:] == ("PROJ-CLONE", "Clone", seen["duplicate"][5])


@pytest.mark.django_db
def test_task_filters_actions_reorder_restore_and_errors(authenticated_client, project, task, monkeypatch):
    response = authenticated_client.get("/api/v1/project-management/tasks/?overdue=not-bool")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = authenticated_client.get("/api/v1/project-management/tasks/?due_from=2026/01/01")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = authenticated_client.get("/api/v1/project-management/tasks/?ordering=task_name")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    task.due_date = timezone.localdate().replace(year=timezone.localdate().year - 1)
    task.save()
    response = authenticated_client.get("/api/v1/project-management/tasks/?overdue=true&ordering=-updated_at")
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1

    seen = []

    def transition(tenant_id, actor_id, task_id, command, transition_key, reason, target_state=None):
        seen.append((command, transition_key, reason, target_state))
        task.status = target_state or "in_progress"
        return task

    monkeypatch.setattr(project_api.TaskService, "transition_task", transition)
    monkeypatch.setattr(project_api.TaskService, "reorder_task", lambda *args: task)
    monkeypatch.setattr(project_api.TaskService, "restore_task", lambda *args: task)

    for action in ("start", "submit-review", "request-changes", "complete", "block", "unblock", "cancel"):
        response = authenticated_client.post(
            f"/api/v1/project-management/tasks/{task.id}/{action}/",
            {"transition_key": f"{action}-key", "reason": "operator", "target_state": "in_progress"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/tasks/{task.id}/reorder/",
        {"position": 4, "version": task.version, "idempotency_key": "task-reorder"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/tasks/{task.id}/restore/",
        {"version": task.version, "idempotency_key": "task-restore"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert {item[0] for item in seen} == {
        "start",
        "submit_review",
        "request_changes",
        "complete",
        "block",
        "unblock",
        "cancel",
    }


@pytest.mark.django_db
def test_member_time_entry_milestone_and_activity_endpoints(
    authenticated_client, tenant_id, project, task, monkeypatch
):
    member = ProjectMember.objects.create(tenant_id=tenant_id, project=project, employee_id=uuid.uuid4())
    time_entry = TimeEntry.objects.create(
        tenant_id=tenant_id,
        project=project,
        task=task,
        employee_id=member.employee_id,
        entry_date=date(2026, 1, 3),
        hours_worked=Decimal("4.00"),
        description="Build",
        billable=True,
    )
    milestone = ProjectMilestone.objects.create(
        tenant_id=tenant_id,
        project=project,
        milestone_name="Go live",
        target_date=date(2026, 3, 1),
    )
    activity = ProjectActivity.objects.create(
        tenant_id=tenant_id,
        project=project,
        entity_type="project",
        entity_id=project.id,
        action="project.created",
        actor_id=uuid.uuid4(),
        correlation_id="corr-project",
    )

    for url in (
        "/api/v1/project-management/members/?ordering=role",
        "/api/v1/project-management/time-entries/?billable=true&entry_from=2026-01-01&entry_to=2026-12-31",
        "/api/v1/project-management/milestones/?achieved=false&overdue=false&target_from=2026-01-01",
        f"/api/v1/project-management/activities/?project_id={project.id}&entity_type=project&entity_id={project.id}",
    ):
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    response = authenticated_client.get("/api/v1/project-management/activities/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    response = authenticated_client.get("/api/v1/project-management/time-entries/?billable=maybe")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    monkeypatch.setattr(project_api.ProjectMemberService, "update_member", lambda *args: member)
    monkeypatch.setattr(project_api.ProjectMemberService, "restore_member", lambda *args: member)
    monkeypatch.setattr(project_api.TimeEntryService, "update_time_entry", lambda *args: time_entry)
    monkeypatch.setattr(project_api.TimeEntryService, "restore_time_entry", lambda *args: time_entry)
    monkeypatch.setattr(project_api.MilestoneService, "achieve_milestone", lambda *args: milestone)
    monkeypatch.setattr(project_api.MilestoneService, "reopen_milestone", lambda *args: milestone)
    monkeypatch.setattr(project_api.MilestoneService, "cancel_milestone", lambda *args: milestone)
    monkeypatch.setattr(project_api.MilestoneService, "restore_milestone", lambda *args: milestone)

    response = authenticated_client.patch(
        f"/api/v1/project-management/members/{member.id}/",
        {"role": "team_lead", "idempotency_key": "member-update"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/members/{member.id}/restore/",
        {"idempotency_key": "member-restore"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.patch(
        f"/api/v1/project-management/time-entries/{time_entry.id}/",
        {"hours_worked": "5.00", "version": time_entry.version, "idempotency_key": "time-update"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/time-entries/{time_entry.id}/restore/",
        {"version": time_entry.version, "idempotency_key": "time-restore"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/milestones/{milestone.id}/achieve/",
        {"achieved_date": "2026-03-01", "idempotency_key": "mile-achieve"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    for action in ("reopen", "cancel"):
        response = authenticated_client.post(
            f"/api/v1/project-management/milestones/{milestone.id}/{action}/",
            {"idempotency_key": f"mile-{action}"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

    response = authenticated_client.post(
        f"/api/v1/project-management/milestones/{milestone.id}/restore/",
        {"version": milestone.version, "idempotency_key": "mile-restore"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert activity.correlation_id == "corr-project"


@pytest.mark.django_db
def test_configuration_dashboard_my_work_and_exception_mapping(authenticated_client, tenant_id, project, monkeypatch):
    config = ProjectManagementConfiguration.objects.create(tenant_id=tenant_id, environment="development")
    version = ProjectManagementConfigurationVersion.objects.create(
        tenant_id=tenant_id,
        configuration=config,
        version=1,
        state=ConfigurationState.ACTIVE,
        change_summary="initial",
        created_by_id=uuid.uuid4(),
    )

    monkeypatch.setattr(project_api.ConfigurationService, "runtime_environment", lambda: "development")
    monkeypatch.setattr(project_api.ConfigurationService, "get_active", lambda tenant, environment: version)
    monkeypatch.setattr(project_api.ConfigurationService, "create_draft", lambda tenant, actor, **data: version)
    monkeypatch.setattr(
        project_api.ConfigurationService, "simulate", lambda tenant, draft_id: {"draft_id": str(draft_id)}
    )
    monkeypatch.setattr(project_api.ConfigurationService, "publish", lambda *args: version)
    monkeypatch.setattr(project_api.ConfigurationService, "rollback", lambda *args: version)
    monkeypatch.setattr(
        project_api.ConfigurationService, "export_document", lambda *args: {"configuration": "exported"}
    )
    monkeypatch.setattr(project_api.ConfigurationService, "import_document", lambda *args: version)
    monkeypatch.setattr(
        project_api.ProjectService,
        "get_portfolio_summary",
        lambda tenant: {
            "project_count": 1,
            "active_project_count": 0,
            "task_count": 0,
            "overdue_task_count": 0,
            "blocked_task_count": 0,
            "upcoming_milestone_count": 0,
            "budget_by_currency": [],
        },
    )

    for method, url, payload in (
        ("get", "/api/v1/project-management/configuration/", None),
        (
            "post",
            "/api/v1/project-management/configuration/drafts/",
            {"environment": "development", "values": {"default_currency": "USD"}, "change_summary": "draft"},
        ),
        ("post", f"/api/v1/project-management/configuration/drafts/{version.id}/simulate/", {}),
        (
            "post",
            f"/api/v1/project-management/configuration/drafts/{version.id}/publish/",
            {"idempotency_key": "publish"},
        ),
        (
            "post",
            "/api/v1/project-management/configuration/rollback/",
            {"target_version": 1, "idempotency_key": "rollback"},
        ),
        ("get", "/api/v1/project-management/configuration/export/", None),
        ("post", "/api/v1/project-management/configuration/import/", {"document": {"environment": "development"}}),
        ("get", "/api/v1/project-management/configuration/versions/?environment=development&state=active", None),
        ("get", "/api/v1/project-management/dashboard/", None),
    ):
        response = getattr(authenticated_client, method)(url, payload, format="json")
        assert response.status_code in {status.HTTP_200_OK, status.HTTP_201_CREATED}

    response = authenticated_client.get("/api/v1/project-management/my-work/")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    monkeypatch.setattr(
        project_api.ProjectService,
        "restore_project",
        lambda *args: (_ for _ in ()).throw(project_api.StaleVersionError()),
    )
    response = authenticated_client.post(
        f"/api/v1/project-management/projects/{project.id}/restore/",
        {"version": project.version, "idempotency_key": "restore-stale"},
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT

    monkeypatch.setattr(
        project_api.ProjectService,
        "restore_project",
        lambda *args: (_ for _ in ()).throw(project_api.IdempotencyConflictError()),
    )
    response = authenticated_client.post(
        f"/api/v1/project-management/projects/{project.id}/restore/",
        {"version": project.version, "idempotency_key": "restore-conflict"},
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT

    monkeypatch.setattr(
        project_api.ProjectService,
        "restore_project",
        lambda *args: (_ for _ in ()).throw(project_api.ProjectManagementError("missing", "NOT_FOUND")),
    )
    response = authenticated_client.post(
        f"/api/v1/project-management/projects/{project.id}/restore/",
        {"version": project.version, "idempotency_key": "restore-missing"},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
