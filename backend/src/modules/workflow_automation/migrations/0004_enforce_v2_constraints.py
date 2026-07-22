"""Validate legacy ownership, then enforce the complete v2 contract."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def validate_v2_data(apps, schema_editor) -> None:
    del schema_editor
    Workflow = apps.get_model("workflow_automation", "Workflow")
    WorkflowStep = apps.get_model("workflow_automation", "WorkflowStep")
    WorkflowInstance = apps.get_model("workflow_automation", "WorkflowInstance")
    WorkflowTask = apps.get_model("workflow_automation", "WorkflowTask")

    for workflow in Workflow.objects.all().iterator(chunk_size=1000):
        if not workflow.key or workflow.key != workflow.key.strip() or not workflow.name.strip():
            raise ValueError(f"Workflow {workflow.pk} has an invalid key or blank name")
        if workflow.version is None or workflow.version < 1:
            raise ValueError(f"Workflow {workflow.pk} has no valid version")

    workflow_owners = {
        row["id"]: (row["tenant_id"], row["version"]) for row in Workflow.objects.values("id", "tenant_id", "version")
    }
    step_owners = {}
    for step in WorkflowStep.objects.all().iterator(chunk_size=1000):
        workflow_owner = workflow_owners.get(step.workflow_id)
        if workflow_owner is None or step.tenant_id != workflow_owner[0]:
            raise ValueError(f"WorkflowStep {step.pk} has a cross-tenant workflow relationship")
        if not step.key or step.key != step.key.strip() or not step.name.strip():
            raise ValueError(f"WorkflowStep {step.pk} has an invalid key or blank name")
        step_owners[step.id] = (step.tenant_id, step.workflow_id)

    instance_owners = {}
    for instance in WorkflowInstance.objects.all().iterator(chunk_size=1000):
        workflow_owner = workflow_owners.get(instance.workflow_id)
        if workflow_owner is None or instance.tenant_id != workflow_owner[0]:
            raise ValueError(f"WorkflowInstance {instance.pk} has a cross-tenant workflow relationship")
        if instance.workflow_version != workflow_owner[1]:
            raise ValueError(f"WorkflowInstance {instance.pk} does not pin its referenced workflow version")
        if not instance.idempotency_key or not instance.correlation_id:
            raise ValueError(f"WorkflowInstance {instance.pk} lacks durable identity")
        if instance.current_step_id is not None:
            step_owner = step_owners.get(instance.current_step_id)
            if step_owner != (instance.tenant_id, instance.workflow_id):
                raise ValueError(f"WorkflowInstance {instance.pk} has a cross-tenant/current-workflow step")
        instance_owners[instance.id] = (instance.tenant_id, instance.workflow_id)

    for task in WorkflowTask.objects.all().iterator(chunk_size=1000):
        instance_owner = instance_owners.get(task.instance_id)
        step_owner = step_owners.get(task.step_id)
        if instance_owner is None or instance_owner[0] != task.tenant_id:
            raise ValueError(f"WorkflowTask {task.pk} has a cross-tenant instance relationship")
        if step_owner != (task.tenant_id, instance_owner[1]):
            raise ValueError(f"WorkflowTask {task.pk} has a cross-tenant or cross-workflow step")
        valid_user = (
            task.assignment_kind == "user"
            and task.assignee_id is not None
            and task.assignee_role_id is None
            and task.assignment_key == f"user:{task.assignee_id}"
        )
        valid_role = (
            task.assignment_kind == "role"
            and task.assignee_id is None
            and task.assignee_role_id is not None
            and task.assignment_key == f"role:{task.assignee_role_id}"
        )
        if not valid_user and not valid_role:
            raise ValueError(f"WorkflowTask {task.pk} has an invalid legacy assignment")
        if not task.correlation_id:
            raise ValueError(f"WorkflowTask {task.pk} lacks correlation evidence")


def prepare_reverse_legacy_shape(apps, schema_editor) -> None:
    """Restore the legacy non-null started_at shape before reversing it."""
    del schema_editor
    WorkflowInstance = apps.get_model("workflow_automation", "WorkflowInstance")
    WorkflowInstance.objects.filter(started_at__isnull=True).update(started_at=models.F("created_at"))


class Migration(migrations.Migration):
    dependencies = [("workflow_automation", "0003_backfill_v2_data")]

    operations = [
        migrations.RunPython(validate_v2_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workflow",
            name="key",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="workflow",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_workflows",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="workflowstep",
            name="tenant_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AlterField(
            model_name="workflowstep",
            name="key",
            field=models.CharField(max_length=64),
        ),
        migrations.AlterField(
            model_name="workflowstep",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="workflowstep",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="workflow_version",
            field=models.PositiveIntegerField(),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="idempotency_key",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="correlation_id",
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="started_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="started_workflow_instances",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="workflowinstance",
            name="state",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("waiting", "Waiting"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="workflowtask",
            name="assignment_kind",
            field=models.CharField(choices=[("user", "User"), ("role", "Role")], max_length=20),
        ),
        migrations.AlterField(
            model_name="workflowtask",
            name="assignment_key",
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name="workflowtask",
            name="correlation_id",
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AlterField(
            model_name="workflowtask",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="workflowtask",
            name="instance",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="tasks",
                to="workflow_automation.workflowinstance",
            ),
        ),
        migrations.AlterField(
            model_name="workflowtask",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("completed", "Completed"),
                    ("rejected", "Rejected"),
                    ("cancelled", "Cancelled"),
                    ("expired", "Expired"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RemoveIndex(model_name="workflow", name="workflow_de_tenant__61a1e6_idx"),
        migrations.RemoveIndex(model_name="workflowinstance", name="workflow_in_tenant__4c4ab9_idx"),
        migrations.RemoveIndex(model_name="workflowtask", name="workflow_ta_tenant__2eb062_idx"),
        migrations.AlterUniqueTogether(name="workflowstep", unique_together=set()),
        migrations.AddConstraint(
            model_name="workflow",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "key", "version"), name="wf_def_tenant_key_ver_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflow",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="published", deleted_at__isnull=True),
                fields=("tenant_id", "key"),
                name="wf_def_published_key_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflow",
            constraint=models.CheckConstraint(condition=models.Q(version__gte=1), name="wf_def_version_gte_1"),
        ),
        migrations.AddConstraint(
            model_name="workflow",
            constraint=models.CheckConstraint(
                condition=~models.Q(status="published") | models.Q(published_at__isnull=False),
                name="wf_def_published_at_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflow",
            constraint=models.CheckConstraint(
                condition=~models.Q(status="archived") | models.Q(archived_at__isnull=False),
                name="wf_def_archived_at_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflow",
            constraint=models.CheckConstraint(
                condition=models.Q(deleted_at__isnull=True) | models.Q(status="draft"),
                name="wf_def_deleted_draft_only",
            ),
        ),
        migrations.AddIndex(
            model_name="workflow",
            index=models.Index(fields=["tenant_id", "status", "-updated_at"], name="wf_def_tenant_status_upd_idx"),
        ),
        migrations.AddIndex(
            model_name="workflow",
            index=models.Index(fields=["tenant_id", "workflow_type", "status"], name="wf_def_tenant_type_status_idx"),
        ),
        migrations.AddIndex(
            model_name="workflow",
            index=models.Index(fields=["tenant_id", "trigger_type", "status"], name="wf_def_tenant_trigger_idx"),
        ),
        migrations.AddIndex(
            model_name="workflow",
            index=models.Index(fields=["tenant_id", "key", "-version"], name="wf_def_tenant_key_ver_idx"),
        ),
        migrations.AddIndex(
            model_name="workflow",
            index=models.Index(fields=["tenant_id", "deleted_at"], name="wf_def_tenant_deleted_idx"),
        ),
        migrations.AddConstraint(
            model_name="workflowstep",
            constraint=models.UniqueConstraint(fields=("tenant_id", "workflow", "key"), name="wf_step_tenant_key_uniq"),
        ),
        migrations.AddConstraint(
            model_name="workflowstep",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "workflow", "order"), name="wf_step_tenant_order_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowstep",
            constraint=models.CheckConstraint(condition=models.Q(order__gte=1), name="wf_step_order_gte_1"),
        ),
        migrations.AddConstraint(
            model_name="workflowstep",
            constraint=models.CheckConstraint(
                condition=models.Q(timeout_seconds__isnull=True) | models.Q(timeout_seconds__gt=0),
                name="wf_step_timeout_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowstep",
            constraint=models.CheckConstraint(
                condition=models.Q(timeout_seconds__isnull=False) | models.Q(timeout_action__isnull=True),
                name="wf_step_timeout_action_ck",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowstep",
            index=models.Index(fields=["tenant_id", "workflow", "order"], name="wf_step_tenant_order_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowstep",
            index=models.Index(fields=["tenant_id", "workflow", "step_type"], name="wf_step_tenant_type_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowstep",
            index=models.Index(fields=["tenant_id", "is_terminal"], name="wf_step_tenant_terminal_idx"),
        ),
        migrations.AddConstraint(
            model_name="workflowinstance",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "idempotency_key"), name="wf_inst_tenant_idem_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowinstance",
            constraint=models.CheckConstraint(
                condition=models.Q(priority__gte=1, priority__lte=9), name="wf_inst_priority_1_9"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowinstance",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(state__in=("completed", "failed", "cancelled"), completed_at__isnull=False)
                    | models.Q(state__in=("pending", "running", "waiting"), completed_at__isnull=True)
                ),
                name="wf_inst_terminal_completed_at",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowinstance",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(state="failed", failure_code__gt="")
                    | (~models.Q(state="failed") & models.Q(failure_code=""))
                ),
                name="wf_inst_failure_code_state",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowinstance",
            index=models.Index(fields=["tenant_id", "state", "-created_at"], name="wf_inst_state_created_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowinstance",
            index=models.Index(fields=["tenant_id", "workflow", "-created_at"], name="wf_inst_workflow_created_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowinstance",
            index=models.Index(fields=["tenant_id", "entity_type", "entity_id"], name="wf_inst_tenant_entity_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowinstance",
            index=models.Index(fields=["tenant_id", "started_by", "-created_at"], name="wf_inst_actor_created_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowinstance",
            index=models.Index(fields=["tenant_id", "correlation_id"], name="wf_inst_tenant_corr_idx"),
        ),
        migrations.AddConstraint(
            model_name="workflowtask",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "instance", "step", "assignment_key"), name="wf_task_assignment_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowtask",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(assignment_kind="user", assignee__isnull=False, assignee_role_id__isnull=True)
                    | models.Q(assignment_kind="role", assignee__isnull=True, assignee_role_id__isnull=False)
                ),
                name="wf_task_assignment_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowtask",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(status="pending", completed_at__isnull=True)
                    | models.Q(status__in=("completed", "rejected", "cancelled", "expired"), completed_at__isnull=False)
                ),
                name="wf_task_terminal_completed_at",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowtask",
            index=models.Index(
                fields=["tenant_id", "status", "assignee", "due_date"], name="wf_task_tenant_user_due_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="workflowtask",
            index=models.Index(
                fields=["tenant_id", "status", "assignee_role_id", "due_date"], name="wf_task_tenant_role_due_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="workflowtask",
            index=models.Index(fields=["tenant_id", "instance", "created_at"], name="wf_task_tenant_instance_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowtask",
            index=models.Index(
                condition=models.Q(status="pending"),
                fields=["tenant_id", "due_date"],
                name="wf_task_pending_due_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowstepexecution",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "operation_key"), name="wf_step_exec_operation_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowstepexecution",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "instance", "step", "attempt"), name="wf_step_exec_attempt_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowstepexecution",
            constraint=models.CheckConstraint(condition=models.Q(attempt__gte=1), name="wf_step_exec_attempt_gte_1"),
        ),
        migrations.AddConstraint(
            model_name="workflowstepexecution",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(state__in=("succeeded", "failed", "cancelled"), completed_at__isnull=False)
                    | models.Q(state__in=("pending", "running"), completed_at__isnull=True)
                ),
                name="wf_step_exec_terminal_time",
            ),
        ),
        migrations.AddConstraint(
            model_name="workflowstepexecution",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(state="failed", failure_code__gt="")
                    | (~models.Q(state="failed") & models.Q(failure_code=""))
                ),
                name="wf_step_exec_failure_state",
            ),
        ),
        migrations.AddIndex(
            model_name="workflowstepexecution",
            index=models.Index(fields=["tenant_id", "instance", "created_at"], name="wf_step_exec_instance_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowstepexecution",
            index=models.Index(fields=["tenant_id", "state", "created_at"], name="wf_step_exec_state_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowstepexecution",
            index=models.Index(fields=["tenant_id", "handler_key", "created_at"], name="wf_step_exec_handler_idx"),
        ),
        migrations.AddIndex(
            model_name="workflowstepexecution",
            index=models.Index(fields=["tenant_id", "correlation_id"], name="wf_step_exec_corr_idx"),
        ),
        migrations.RunPython(migrations.RunPython.noop, prepare_reverse_legacy_shape),
    ]
