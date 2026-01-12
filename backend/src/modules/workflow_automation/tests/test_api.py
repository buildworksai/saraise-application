from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from src.core.user_models import UserProfile
from src.modules.tenant_management.models import Tenant
from src.core.licensing.models import Organization, License, LicenseStatus
from ..models import Workflow, WorkflowStep, WorkflowInstance, WorkflowTask

User = get_user_model()


class WorkflowAPITestCase(APITestCase):
    def setUp(self):
        # Create Organization
        self.org = Organization.objects.create(name="Test Org", domain="example.com")

        # Create active License to bypass LicenseValidationMiddleware
        # We need to satisfy the License model requirements
        License.objects.create(
            organization=self.org,
            status=LicenseStatus.ACTIVE,
            license_key="test-key",
            max_users=-1,
            industry_modules=[],
            core_tier="pro",
        )

        # Create Tenant with same ID
        self.tenant = Tenant.objects.create(id=self.org.id, name="Test Tenant", slug="test-tenant")

        # Create User
        self.user = User.objects.create_user(username="testuser", password="password", email="test@example.com")

        # Update Profile with tenant_id
        profile = self.user.profile
        profile.tenant_id = self.org.id
        profile.save()

        # Force reload user to ensure profile relationship is available
        self.user.refresh_from_db()

        self.client.force_authenticate(user=self.user)
        self.url = reverse("workflow-list")

    def test_create_workflow(self):
        data = {
            "name": "Test Workflow",
            "description": "A test workflow",
            "trigger_type": "manual",
            "steps": [
                {"name": "Step 1", "step_type": "action", "order": 1},
                {"name": "Step 2", "step_type": "approval", "order": 2},
            ],
        }
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Workflow.objects.count(), 1)
        self.assertEqual(WorkflowStep.objects.count(), 2)

    def test_start_workflow_instance(self):
        # Create published workflow
        workflow = Workflow.objects.create(
            name="Published Workflow", tenant_id=self.tenant.id, status="published", created_by=self.user
        )
        WorkflowStep.objects.create(workflow=workflow, name="Step 1", order=1, step_type="action")

        url = reverse("workflow-start", args=[workflow.id])
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkflowInstance.objects.count(), 1)
        instance = WorkflowInstance.objects.first()
        self.assertEqual(instance.state, "completed")

    def test_approval_workflow(self):
        # Workflow with Approval Query
        workflow = Workflow.objects.create(
            name="Approval Workflow", tenant_id=self.tenant.id, status="published", created_by=self.user
        )
        # Step 1: Approval (ASSIGNED TO CURRENT USER)
        WorkflowStep.objects.create(
            workflow=workflow,
            name="Approval Step",
            order=1,
            step_type="approval",
            config={"assignee_id": str(self.user.id)},
        )

        # Start Instance
        start_url = reverse("workflow-start", args=[workflow.id])
        self.client.post(start_url, {}, format="json")

        instance = WorkflowInstance.objects.first()
        self.assertEqual(instance.state, "running")

        # Check Task Created
        task = WorkflowTask.objects.filter(instance=instance).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.status, "pending")

        # Complete Task
        complete_url = reverse("workflow-task-complete", args=[task.id])
        response = self.client.post(complete_url, {"meta_data": {"comment": "Approved"}}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check Instance Completed
        instance.refresh_from_db()
        self.assertEqual(instance.state, "completed")
