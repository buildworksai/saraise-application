"""Deterministically backfill v2 ownership, identity, and legacy evidence."""

from django.db import migrations


MARKER_COMMAND = "legacy_import"


def _workflow_key(workflow) -> str:
    return f"workflow-{str(workflow.id).replace('-', '')[:16]}"


def _step_key(step) -> str:
    return f"step-{step.order}-{str(step.id).replace('-', '')[:12]}"


def _marker(instance, state: str, occurred_at, reason: str) -> dict:
    return {
        "transition_key": f"migration:0003:{instance.id}:{reason}",
        "command": MARKER_COMMAND,
        "from_state": state,
        "to_state": state,
        "occurred_at": occurred_at.isoformat(),
        "metadata": {"source": "workflow_automation.0003", "reason": reason},
    }


def backfill_v2_data(apps, schema_editor) -> None:
    del schema_editor
    Workflow = apps.get_model("workflow_automation", "Workflow")
    WorkflowStep = apps.get_model("workflow_automation", "WorkflowStep")
    WorkflowInstance = apps.get_model("workflow_automation", "WorkflowInstance")
    WorkflowTask = apps.get_model("workflow_automation", "WorkflowTask")

    for workflow in Workflow.objects.all().iterator(chunk_size=1000):
        updates = {}
        if workflow.key is None:
            updates["key"] = _workflow_key(workflow)
        if workflow.version is None:
            updates["version"] = 1
        history = list(workflow.transition_history or [])
        if workflow.status == "published" and workflow.published_at is None:
            updates["published_at"] = workflow.updated_at
            history.append(_marker(workflow, workflow.status, workflow.updated_at, "published_timestamp_copied"))
        if workflow.status == "archived" and workflow.archived_at is None:
            updates["archived_at"] = workflow.updated_at
            history.append(_marker(workflow, workflow.status, workflow.updated_at, "archived_timestamp_copied"))
        if history != workflow.transition_history:
            updates["transition_history"] = history
        if updates:
            Workflow.objects.filter(pk=workflow.pk).update(**updates)

    workflow_values = {
        row["id"]: row
        for row in Workflow.objects.values("id", "tenant_id", "created_at", "updated_at", "version")
    }
    for step in WorkflowStep.objects.all().iterator(chunk_size=1000):
        owner = workflow_values[step.workflow_id]
        updates = {}
        if step.tenant_id is None:
            updates["tenant_id"] = owner["tenant_id"]
        if step.key is None:
            updates["key"] = _step_key(step)
        if step.created_at is None:
            updates["created_at"] = owner["created_at"]
        if step.updated_at is None:
            updates["updated_at"] = owner["updated_at"]
        if updates:
            WorkflowStep.objects.filter(pk=step.pk).update(**updates)

    for instance in WorkflowInstance.objects.all().iterator(chunk_size=1000):
        owner = workflow_values[instance.workflow_id]
        updates = {}
        if instance.workflow_version is None:
            updates["workflow_version"] = owner["version"] or 1
        if instance.idempotency_key is None:
            updates["idempotency_key"] = f"legacy:{instance.id}"
        if instance.correlation_id is None:
            updates["correlation_id"] = f"legacy-{str(instance.id).replace('-', '')}"
        if instance.created_at is None:
            updates["created_at"] = instance.started_at
        if instance.updated_at is None:
            updates["updated_at"] = instance.completed_at or instance.started_at
        history = list(instance.transition_history or [])
        if instance.state in {"completed", "failed", "cancelled"} and instance.completed_at is None:
            updates["completed_at"] = instance.started_at
            history.append(_marker(instance, instance.state, instance.started_at, "terminal_timestamp_copied"))
        if instance.state == "failed" and not instance.failure_code:
            updates["failure_code"] = "LEGACY_FAILURE_UNSPECIFIED"
            if not history:
                history.append(_marker(instance, instance.state, instance.started_at, "failure_code_classified"))
        if history != instance.transition_history:
            updates["transition_history"] = history
        if updates:
            WorkflowInstance.objects.filter(pk=instance.pk).update(**updates)

    instance_values = {
        row["id"]: row
        for row in WorkflowInstance.objects.values(
            "id", "tenant_id", "workflow_id", "correlation_id", "created_at", "updated_at"
        )
    }
    for task in WorkflowTask.objects.all().iterator(chunk_size=1000):
        owner = instance_values[task.instance_id]
        updates = {}
        if task.assignee_id is not None and task.assignee_role_id is None:
            updates["assignment_kind"] = "user"
            updates["assignment_key"] = f"user:{task.assignee_id}"
        elif task.assignee_id is None and task.assignee_role_id is not None:
            updates["assignment_kind"] = "role"
            updates["assignment_key"] = f"role:{task.assignee_role_id}"
        if task.correlation_id is None:
            updates["correlation_id"] = owner["correlation_id"]
        if task.updated_at is None:
            updates["updated_at"] = task.completed_at or task.created_at
        history = list(task.transition_history or [])
        if task.status in {"completed", "rejected", "cancelled", "expired"} and task.completed_at is None:
            updates["completed_at"] = task.created_at
            history.append(_marker(task, task.status, task.created_at, "terminal_timestamp_copied"))
        if history != task.transition_history:
            updates["transition_history"] = history
        if updates:
            WorkflowTask.objects.filter(pk=task.pk).update(**updates)


def reverse_v2_backfill(apps, schema_editor) -> None:
    del schema_editor
    Workflow = apps.get_model("workflow_automation", "Workflow")
    WorkflowStep = apps.get_model("workflow_automation", "WorkflowStep")
    WorkflowInstance = apps.get_model("workflow_automation", "WorkflowInstance")
    WorkflowTask = apps.get_model("workflow_automation", "WorkflowTask")

    for task in WorkflowTask.objects.all().iterator(chunk_size=1000):
        updates = {"assignment_kind": None, "assignment_key": None, "correlation_id": None, "updated_at": None}
        markers = [item for item in (task.transition_history or []) if item.get("command") == MARKER_COMMAND]
        if any(item.get("metadata", {}).get("reason") == "terminal_timestamp_copied" for item in markers):
            updates["completed_at"] = None
        updates["transition_history"] = [
            item for item in (task.transition_history or []) if item.get("command") != MARKER_COMMAND
        ]
        WorkflowTask.objects.filter(pk=task.pk).update(**updates)

    for instance in WorkflowInstance.objects.all().iterator(chunk_size=1000):
        updates = {
            "workflow_version": None,
            "idempotency_key": None,
            "correlation_id": None,
            "created_at": None,
            "updated_at": None,
        }
        markers = [item for item in (instance.transition_history or []) if item.get("command") == MARKER_COMMAND]
        reasons = {item.get("metadata", {}).get("reason") for item in markers}
        if "terminal_timestamp_copied" in reasons:
            updates["completed_at"] = None
        if "failure_code_classified" in reasons or (
            instance.failure_code == "LEGACY_FAILURE_UNSPECIFIED" and markers
        ):
            updates["failure_code"] = ""
        updates["transition_history"] = [
            item for item in (instance.transition_history or []) if item.get("command") != MARKER_COMMAND
        ]
        WorkflowInstance.objects.filter(pk=instance.pk).update(**updates)

    for step in WorkflowStep.objects.all().iterator(chunk_size=1000):
        updates = {"tenant_id": None, "created_at": None, "updated_at": None}
        if step.key == _step_key(step):
            updates["key"] = None
        WorkflowStep.objects.filter(pk=step.pk).update(**updates)

    for workflow in Workflow.objects.all().iterator(chunk_size=1000):
        updates = {}
        if workflow.key == _workflow_key(workflow):
            updates["key"] = None
        if workflow.version == 1:
            updates["version"] = None
        markers = [item for item in (workflow.transition_history or []) if item.get("command") == MARKER_COMMAND]
        reasons = {item.get("metadata", {}).get("reason") for item in markers}
        if "published_timestamp_copied" in reasons:
            updates["published_at"] = None
        if "archived_timestamp_copied" in reasons:
            updates["archived_at"] = None
        updates["transition_history"] = [
            item for item in (workflow.transition_history or []) if item.get("command") != MARKER_COMMAND
        ]
        if updates:
            Workflow.objects.filter(pk=workflow.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("workflow_automation", "0002_add_v2_nullable_fields")]

    operations = [migrations.RunPython(backfill_v2_data, reverse_v2_backfill)]
