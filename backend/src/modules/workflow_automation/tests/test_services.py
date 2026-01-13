"""
Service Unit Tests for WorkflowAutomation module.

Tests business logic in services layer.
"""
import uuid
import pytest
from django.contrib.auth import get_user_model

from src.modules.workflow_automation.models import (
    Workflow,
    WorkflowStep,
    WorkflowInstance,
    WorkflowTask,
    WorkflowStatus,
    WorkflowTriggerType,
    WorkflowStepType,
    WorkflowInstanceState,
    WorkflowTaskStatus,
)
from src.modules.workflow_automation.services import WorkflowEngine

User = get_user_model()


@pytest.mark.django_db
class TestWorkflowEngine:
    """Test WorkflowEngine business logic."""

    def test_start_workflow(self, db):
        """Test starting a workflow instance."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            trigger_type=WorkflowTriggerType.MANUAL,
            created_by=user,
        )

        # Create a step
        WorkflowStep.objects.create(
            workflow=workflow,
            name="First Step",
            step_type=WorkflowStepType.ACTION,
            order=1,
        )

        engine = WorkflowEngine()
        instance = engine.start_workflow(workflow.id, tenant_id, user, {"key": "value"})

        assert instance.id is not None
        assert instance.tenant_id == tenant_id
        assert instance.workflow == workflow
        assert instance.state == WorkflowInstanceState.COMPLETED  # Action step completes immediately
        # Context data includes original data plus action results
        assert "key" in instance.context_data
        assert instance.context_data["key"] == "value"
        # Action results are added to context
        assert any(k.startswith("action_result_") for k in instance.context_data.keys())

    def test_start_workflow_not_published(self, db):
        """Test that starting a non-published workflow raises error."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Draft Workflow",
            status=WorkflowStatus.DRAFT,
            created_by=user,
        )

        engine = WorkflowEngine()
        with pytest.raises(ValueError, match="Cannot start a workflow that is not published"):
            engine.start_workflow(workflow.id, tenant_id, user)

    def test_start_workflow_empty(self, db):
        """Test starting a workflow with no steps completes immediately."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Empty Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        engine = WorkflowEngine()
        instance = engine.start_workflow(workflow.id, tenant_id, user)

        assert instance.state == WorkflowInstanceState.COMPLETED
        assert instance.completed_at is not None

    def test_transition_task_complete(self, db):
        """Test completing a workflow task."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        step1 = WorkflowStep.objects.create(
            workflow=workflow,
            name="Step 1",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        step2 = WorkflowStep.objects.create(
            workflow=workflow,
            name="Step 2",
            step_type=WorkflowStepType.ACTION,
            order=2,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            current_step=step1,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )

        task = WorkflowTask.objects.create(
            tenant_id=tenant_id,
            instance=instance,
            step=step1,
            assignee=user,
            status=WorkflowTaskStatus.PENDING,
        )

        engine = WorkflowEngine()
        updated_task = engine.transition_task(task.id, tenant_id, "complete", {"comment": "Approved"})

        assert updated_task.status == WorkflowTaskStatus.COMPLETED
        assert updated_task.completed_at is not None
        assert updated_task.meta_data == {"comment": "Approved"}

    def test_transition_task_reject(self, db):
        """Test rejecting a workflow task."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        step = WorkflowStep.objects.create(
            workflow=workflow,
            name="Approval Step",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            current_step=step,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )

        task = WorkflowTask.objects.create(
            tenant_id=tenant_id,
            instance=instance,
            step=step,
            assignee=user,
            status=WorkflowTaskStatus.PENDING,
        )

        engine = WorkflowEngine()
        updated_task = engine.transition_task(task.id, tenant_id, "reject", {"comment": "Rejected"})

        assert updated_task.status == WorkflowTaskStatus.REJECTED
        assert updated_task.completed_at is not None
        assert updated_task.meta_data == {"comment": "Rejected"}

        # Instance should be failed
        instance.refresh_from_db()
        assert instance.state == WorkflowInstanceState.FAILED

    def test_transition_task_invalid_action(self, db):
        """Test that invalid action raises error."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        step = WorkflowStep.objects.create(
            workflow=workflow,
            name="Approval Step",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            current_step=step,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )

        task = WorkflowTask.objects.create(
            tenant_id=tenant_id,
            instance=instance,
            step=step,
            assignee=user,
            status=WorkflowTaskStatus.PENDING,
        )

        engine = WorkflowEngine()
        with pytest.raises(ValueError, match="Invalid action"):
            engine.transition_task(task.id, tenant_id, "invalid_action")

    def test_transition_task_not_pending(self, db):
        """Test that transitioning a non-pending task raises error."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        step = WorkflowStep.objects.create(
            workflow=workflow,
            name="Approval Step",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            current_step=step,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )

        task = WorkflowTask.objects.create(
            tenant_id=tenant_id,
            instance=instance,
            step=step,
            assignee=user,
            status=WorkflowTaskStatus.COMPLETED,
        )

        engine = WorkflowEngine()
        with pytest.raises(ValueError, match="Task is not pending"):
            engine.transition_task(task.id, tenant_id, "complete")
