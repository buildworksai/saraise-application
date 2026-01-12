from django.utils import timezone
from django.db import transaction
from .models import (
    Workflow,
    WorkflowInstance,
    WorkflowStep,
    WorkflowTask,
    WorkflowInstanceState,
    WorkflowTaskStatus,
    WorkflowStatus,
)


class WorkflowEngine:
    """
    Core engine for managing workflow state transitions.
    """

    def start_workflow(self, workflow_id, tenant_id, user, context_data=None):
        """
        Starts a new instance of a published workflow.
        """
        workflow = Workflow.objects.get(id=workflow_id, tenant_id=tenant_id)

        if workflow.status != WorkflowStatus.PUBLISHED:
            raise ValueError("Cannot start a workflow that is not published.")

        instance = WorkflowInstance.objects.create(
            workflow=workflow,
            tenant_id=tenant_id,
            state=WorkflowInstanceState.RUNNING,
            context_data=context_data or {},
            started_by=user,
        )

        # Execute first step
        first_step = workflow.steps.order_by("order").first()
        if first_step:
            self._execute_step(instance, first_step)
        else:
            # Empty workflow, complete immediately
            instance.state = WorkflowInstanceState.COMPLETED
            instance.completed_at = timezone.now()
            instance.save()

        return instance

    def transition_task(self, task_id, tenant_id, action, meta_data=None):
        """
        Handles a task completion/rejection.
        """
        task = WorkflowTask.objects.get(id=task_id, tenant_id=tenant_id)

        if task.status != WorkflowTaskStatus.PENDING:
            raise ValueError("Task is not pending.")

        if action == "complete":
            task.status = WorkflowTaskStatus.COMPLETED
        elif action == "reject":
            task.status = WorkflowTaskStatus.REJECTED
        else:
            raise ValueError(f"Invalid action: {action}")

        task.completed_at = timezone.now()
        if meta_data:
            task.meta_data.update(meta_data)
        task.save()

        # After task completion, decide what to do next
        # For Phase 8 simple sequential workflows:
        if action == "complete":
            self._move_to_next_step(task.instance, task.step)
        elif action == "reject":
            # Fail the workflow or handle rejection logic
            task.instance.state = WorkflowInstanceState.FAILED
            task.instance.completed_at = timezone.now()
            task.instance.save()

        return task

    def _execute_step(self, instance, step):
        """
        Executes the logic for entering a step.
        """
        instance.current_step = step
        instance.save()

        if step.step_type == "action":
            # Execute action
            from .action_executor import ActionExecutor

            action_type = step.config.get("action_type", "update_database")
            action_result = ActionExecutor.execute_action(
                action_type=action_type,
                action_config=step.config,
                workflow_context=instance.context_data,
                tenant_id=instance.tenant_id,
            )

            # Store action result in context
            instance.context_data[f"action_result_{step.id}"] = action_result
            instance.save()

            # Move to next step
            self._move_to_next_step(instance, step)

        elif step.step_type == "approval":
            # Create a Task
            assignee_id = step.config.get("assignee_id")  # Simplified: direct user assignment
            WorkflowTask.objects.create(
                tenant_id=instance.tenant_id, instance=instance, step=step, assignee_id=assignee_id
            )
            # Instance waits in RUNNING state until task is completed

        elif step.step_type == "notification":
            # Send notification
            from src.core.notifications import NotificationService

            title = step.config.get("title", "Workflow Notification")
            message = step.config.get("message", f"Workflow step: {step.name}")
            user_id = step.config.get("user_id") or instance.context_data.get("user_id", "")

            if user_id:
                NotificationService.create_notification(
                    tenant_id=instance.tenant_id,
                    user_id=user_id,
                    title=title,
                    message=message,
                    notification_type="workflow",
                    action_url=step.config.get("action_url"),
                    metadata={"workflow_id": str(instance.workflow.id), "step_id": str(step.id)},
                )

            # Then move next
            self._move_to_next_step(instance, step)

    def _move_to_next_step(self, instance, current_step):
        """
        Finds the next step and executes it, or completes the workflow.
        """
        next_step = (
            WorkflowStep.objects.filter(workflow=instance.workflow, order__gt=current_step.order)
            .order_by("order")
            .first()
        )

        if next_step:
            self._execute_step(instance, next_step)
        else:
            # End of workflow
            instance.state = WorkflowInstanceState.COMPLETED
            instance.current_step = None
            instance.completed_at = timezone.now()
            instance.save()
