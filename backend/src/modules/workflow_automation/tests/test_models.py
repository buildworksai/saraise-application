"""
Model Unit Tests for WorkflowAutomation module.

Tests model creation, validation, and relationships.
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

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

User = get_user_model()


@pytest.mark.django_db
class TestWorkflowModel:
    """Test Workflow model."""

    def test_create_workflow(self, db):
        """Test creating a workflow."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            description="Test description",
            status=WorkflowStatus.DRAFT,
            trigger_type=WorkflowTriggerType.MANUAL,
            created_by=user,
        )
        assert workflow.id is not None
        assert workflow.name == "Test Workflow"
        assert workflow.tenant_id == tenant_id
        assert workflow.status == WorkflowStatus.DRAFT

    def test_workflow_str_representation(self, db):
        """Test workflow string representation."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.DRAFT,
            created_by=user,
        )
        assert str(workflow) == f"Test Workflow ({WorkflowStatus.DRAFT})"

    def test_workflow_has_tenant_id(self, db):
        """Test that workflow requires tenant_id."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")

        workflow = Workflow(
            name="Test Workflow",
            status=WorkflowStatus.DRAFT,
            created_by=user,
        )
        # Should raise error if tenant_id is missing
        with pytest.raises(Exception):
            workflow.save()


@pytest.mark.django_db
class TestWorkflowStepModel:
    """Test WorkflowStep model."""

    def test_create_workflow_step(self, db):
        """Test creating a workflow step."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.DRAFT,
            created_by=user,
        )

        step = WorkflowStep.objects.create(
            workflow=workflow,
            name="Test Step",
            step_type=WorkflowStepType.ACTION,
            order=1,
            config={"key": "value"},
        )
        assert step.id is not None
        assert step.name == "Test Step"
        assert step.step_type == WorkflowStepType.ACTION
        assert step.order == 1
        assert step.config == {"key": "value"}

    def test_workflow_step_str_representation(self, db):
        """Test workflow step string representation."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.DRAFT,
            created_by=user,
        )

        step = WorkflowStep.objects.create(
            workflow=workflow,
            name="Test Step",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )
        assert str(step) == f"1. Test Step ({WorkflowStepType.APPROVAL})"


@pytest.mark.django_db
class TestWorkflowInstanceModel:
    """Test WorkflowInstance model."""

    def test_create_workflow_instance(self, db):
        """Test creating a workflow instance."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            state=WorkflowInstanceState.RUNNING,
            context_data={"key": "value"},
            started_by=user,
        )
        assert instance.id is not None
        assert instance.tenant_id == tenant_id
        assert instance.workflow == workflow
        assert instance.state == WorkflowInstanceState.RUNNING
        assert instance.context_data == {"key": "value"}

    def test_workflow_instance_str_representation(self, db):
        """Test workflow instance string representation."""
        user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass")
        tenant_id = uuid.uuid4()

        workflow = Workflow.objects.create(
            tenant_id=tenant_id,
            name="Test Workflow",
            status=WorkflowStatus.PUBLISHED,
            created_by=user,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )
        assert str(instance) == f"Instance of Test Workflow - {WorkflowInstanceState.RUNNING}"


@pytest.mark.django_db
class TestWorkflowTaskModel:
    """Test WorkflowTask model."""

    def test_create_workflow_task(self, db):
        """Test creating a workflow task."""
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
            name="Test Step",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )

        task = WorkflowTask.objects.create(
            tenant_id=tenant_id,
            instance=instance,
            step=step,
            assignee=user,
            status=WorkflowTaskStatus.PENDING,
            meta_data={"comment": "Test"},
        )
        assert task.id is not None
        assert task.tenant_id == tenant_id
        assert task.instance == instance
        assert task.step == step
        assert task.assignee == user
        assert task.status == WorkflowTaskStatus.PENDING
        assert task.meta_data == {"comment": "Test"}

    def test_workflow_task_str_representation(self, db):
        """Test workflow task string representation."""
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
            name="Test Step",
            step_type=WorkflowStepType.APPROVAL,
            order=1,
        )

        instance = WorkflowInstance.objects.create(
            tenant_id=tenant_id,
            workflow=workflow,
            state=WorkflowInstanceState.RUNNING,
            started_by=user,
        )

        task = WorkflowTask.objects.create(
            tenant_id=tenant_id,
            instance=instance,
            step=step,
        )
        assert str(task) == f"Task for {instance}: Test Step"
