"""
Tenant Isolation Tests for WorkflowAutomation module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from ..models import Workflow, WorkflowInstance, WorkflowTask, WorkflowStatus
from src.core.auth_utils import get_user_tenant_id

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
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
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
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
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


@pytest.mark.django_db
class TestWorkflowTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for Workflow model.
    These tests verify that tenants cannot access each other's workflows.
    """

    def test_user_cannot_list_other_tenant_workflows(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's workflows in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflow for tenant A
        workflow_a = Workflow.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Workflow",
            description="Workflow for tenant A",
            status=WorkflowStatus.DRAFT,
            created_by=tenant_a_user,
        )

        # Create workflow for tenant B
        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            description="Workflow for tenant B",
            status=WorkflowStatus.DRAFT,
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/workflow-automation/workflows/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        workflow_ids = [str(w["id"]) for w in data]

        # User A should see tenant A's workflow, but NOT tenant B's workflow
        assert str(workflow_a.id) in workflow_ids
        assert str(workflow_b.id) not in workflow_ids

    def test_user_cannot_get_other_tenant_workflow_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's workflow by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflow for tenant B
        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            description="Workflow for tenant B",
            status=WorkflowStatus.DRAFT,
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's workflow
        response = api_client.get(f"/api/v1/workflow-automation/workflows/{workflow_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_workflow(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's workflow (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflow for tenant B
        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            description="Workflow for tenant B",
            status=WorkflowStatus.DRAFT,
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's workflow
        data = {"name": "Hacked Name"}
        response = api_client.put(
            f"/api/v1/workflow-automation/workflows/{workflow_b.id}/",
            data,
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify workflow was not modified
        workflow_b.refresh_from_db()
        assert workflow_b.name == "Tenant B Workflow"

    def test_user_cannot_delete_other_tenant_workflow(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's workflow (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflow for tenant B
        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            description="Workflow for tenant B",
            status=WorkflowStatus.DRAFT,
            created_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's workflow
        response = api_client.delete(f"/api/v1/workflow-automation/workflows/{workflow_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify workflow still exists
        assert Workflow.objects.filter(id=workflow_b.id).exists()


@pytest.mark.django_db
class TestWorkflowInstanceTenantIsolation:
    """Tenant isolation tests for WorkflowInstance model."""

    def test_user_cannot_list_other_tenant_instances(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's workflow instances in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflows
        workflow_a = Workflow.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=tenant_a_user,
        )

        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=tenant_b_user,
        )

        # Create instances
        instance_a = WorkflowInstance.objects.create(
            tenant_id=tenant_a_id,
            workflow=workflow_a,
            started_by=tenant_a_user,
        )

        instance_b = WorkflowInstance.objects.create(
            tenant_id=tenant_b_id,
            workflow=workflow_b,
            started_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/workflow-automation/instances/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        instance_ids = [str(i["id"]) for i in data]

        # User A should see tenant A's instance, but NOT tenant B's instance
        assert str(instance_a.id) in instance_ids
        assert str(instance_b.id) not in instance_ids

    def test_user_cannot_get_other_tenant_instance_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's workflow instance by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflow and instance for tenant B
        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=tenant_b_user,
        )

        instance_b = WorkflowInstance.objects.create(
            tenant_id=tenant_b_id,
            workflow=workflow_b,
            started_by=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's instance
        response = api_client.get(f"/api/v1/workflow-automation/instances/{instance_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestWorkflowTaskTenantIsolation:
    """Tenant isolation tests for WorkflowTask model."""

    def test_user_cannot_list_other_tenant_tasks(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's workflow tasks in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflows
        workflow_a = Workflow.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=tenant_a_user,
        )

        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=tenant_b_user,
        )

        # Create instances
        instance_a = WorkflowInstance.objects.create(
            tenant_id=tenant_a_id,
            workflow=workflow_a,
            started_by=tenant_a_user,
        )

        instance_b = WorkflowInstance.objects.create(
            tenant_id=tenant_b_id,
            workflow=workflow_b,
            started_by=tenant_b_user,
        )

        # Create steps
        from ..models import WorkflowStep, WorkflowStepType

        step_a = WorkflowStep.objects.create(
            workflow=workflow_a,
            name="Step A",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        step_b = WorkflowStep.objects.create(
            workflow=workflow_b,
            name="Step B",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        # Create tasks
        task_a = WorkflowTask.objects.create(
            tenant_id=tenant_a_id,
            instance=instance_a,
            step=step_a,
            assignee=tenant_a_user,
        )

        task_b = WorkflowTask.objects.create(
            tenant_id=tenant_b_id,
            instance=instance_b,
            step=step_b,
            assignee=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/workflow-automation/tasks/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        task_ids = [str(t["id"]) for t in data]

        # User A should see tenant A's task, but NOT tenant B's task
        assert str(task_a.id) in task_ids
        assert str(task_b.id) not in task_ids

    def test_user_cannot_get_other_tenant_task_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's workflow task by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create workflow, instance, step, and task for tenant B
        workflow_b = Workflow.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=tenant_b_user,
        )

        instance_b = WorkflowInstance.objects.create(
            tenant_id=tenant_b_id,
            workflow=workflow_b,
            started_by=tenant_b_user,
        )

        from ..models import WorkflowStep, WorkflowStepType

        step_b = WorkflowStep.objects.create(
            workflow=workflow_b,
            name="Step B",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        task_b = WorkflowTask.objects.create(
            tenant_id=tenant_b_id,
            instance=instance_b,
            step=step_b,
            assignee=tenant_b_user,
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's task
        response = api_client.get(f"/api/v1/workflow-automation/tasks/{task_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
