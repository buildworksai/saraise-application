from rest_framework import serializers
from .models import (
    Workflow,
    WorkflowStep,
    WorkflowInstance,
    WorkflowTask,
)


class WorkflowStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowStep
        fields = ["id", "workflow", "name", "step_type", "order", "config"]
        read_only_fields = ["id", "workflow"]


class WorkflowSerializer(serializers.ModelSerializer):
    steps = WorkflowStepSerializer(many=True, required=False)

    class Meta:
        model = Workflow
        fields = [
            "id",
            "tenant_id",
            "name",
            "description",
            "status",
            "trigger_type",
            "steps",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        # Get tenant_id from view context (set in perform_create)
        tenant_id = self.context.get("tenant_id")
        if not tenant_id:
            raise serializers.ValidationError("tenant_id is required")
        validated_data["tenant_id"] = tenant_id
        workflow = Workflow.objects.create(**validated_data)
        for step_data in steps_data:
            WorkflowStep.objects.create(workflow=workflow, **step_data)
        return workflow

    def update(self, instance, validated_data):
        steps_data = validated_data.pop("steps", None)

        # Update standard fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Handle steps update (Full replace strategy for simplicity in Phase 8)
        if steps_data is not None:
            instance.steps.all().delete()
            for step_data in steps_data:
                WorkflowStep.objects.create(workflow=instance, **step_data)

        return instance


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="workflow.name", read_only=True)
    current_step_name = serializers.CharField(source="current_step.name", read_only=True)

    class Meta:
        model = WorkflowInstance
        fields = [
            "id",
            "tenant_id",
            "workflow",
            "workflow_name",
            "current_step",
            "current_step_name",
            "state",
            "context_data",
            "started_at",
            "completed_at",
        ]
        read_only_fields = ["id", "tenant_id", "state", "current_step", "started_at", "completed_at"]


class WorkflowTaskSerializer(serializers.ModelSerializer):
    workflow_name = serializers.CharField(source="instance.workflow.name", read_only=True)
    step_name = serializers.CharField(source="step.name", read_only=True)

    class Meta:
        model = WorkflowTask
        fields = [
            "id",
            "tenant_id",
            "instance",
            "workflow_name",
            "step",
            "step_name",
            "assignee",
            "status",
            "due_date",
            "created_at",
            "completed_at",
            "meta_data",
        ]
        read_only_fields = ["id", "tenant_id", "instance", "step", "created_at"]
