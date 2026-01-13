import uuid

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from src.core.auth_utils import get_user_tenant_id, get_user_id
from src.core.authentication import RelaxedCsrfSessionAuthentication
from .models import Workflow, WorkflowInstance, WorkflowTask
from .serializers import WorkflowSerializer, WorkflowInstanceSerializer, WorkflowTaskSerializer
from .services import WorkflowEngine


class WorkflowViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return Workflow.objects.none()
        # Convert string tenant_id to UUID for filtering
        # Workflow.tenant_id is UUIDField, but get_user_tenant_id returns string (CharField)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Workflow.objects.none()
        return Workflow.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "User must belong to a tenant"})
        # Convert string tenant_id to UUID
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"error": "Invalid tenant_id format"})
        # Pass tenant_id to serializer context so create() can use it
        serializer.context["tenant_id"] = tenant_id
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        workflow = self.get_object()
        workflow.status = "published"
        workflow.save()
        return Response({"status": "published"})

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """
        Manually start a workflow instance.
        """
        workflow = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "User must belong to a tenant"}, status=status.HTTP_403_FORBIDDEN)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant_id format"}, status=status.HTTP_400_BAD_REQUEST)
        context_data = request.data.get("context", {})

        engine = WorkflowEngine()
        try:
            instance = engine.start_workflow(workflow.id, tenant_id, request.user, context_data)
            serializer = WorkflowInstanceSerializer(instance)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class WorkflowInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkflowInstanceSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]

    def get_queryset(self):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return WorkflowInstance.objects.none()
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return WorkflowInstance.objects.none()
        return WorkflowInstance.objects.filter(tenant_id=tenant_id)


class WorkflowTaskViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowTaskSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [RelaxedCsrfSessionAuthentication]
    # Restrict to tasks assigned to user OR created by user's tenant admins (simplified for now)

    def get_queryset(self):
        tenant_id_str = get_user_tenant_id(self.request.user)
        if not tenant_id_str:
            return WorkflowTask.objects.none()
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return WorkflowTask.objects.none()
        queryset = WorkflowTask.objects.filter(tenant_id=tenant_id)

        # Filter by assignee for non-admin users
        if not self.request.user.is_staff:
            assignee_id = get_user_id(self.request.user)
            queryset = queryset.filter(assignee_id=assignee_id)

        return queryset

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        task = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "User must belong to a tenant"}, status=status.HTTP_403_FORBIDDEN)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant_id format"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify assignee
        if task.assignee and task.assignee != request.user:
            return Response({"error": "Not assigned to you"}, status=status.HTTP_403_FORBIDDEN)

        engine = WorkflowEngine()
        try:
            updated_task = engine.transition_task(task.id, tenant_id, "complete", request.data.get("meta_data"))
            return Response(WorkflowTaskSerializer(updated_task).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        task = self.get_object()
        tenant_id_str = get_user_tenant_id(request.user)
        if not tenant_id_str:
            return Response({"error": "User must belong to a tenant"}, status=status.HTTP_403_FORBIDDEN)
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except (ValueError, TypeError):
            return Response({"error": "Invalid tenant_id format"}, status=status.HTTP_400_BAD_REQUEST)

        # Verify assignee
        if task.assignee and task.assignee != request.user:
            return Response({"error": "Not assigned to you"}, status=status.HTTP_403_FORBIDDEN)

        engine = WorkflowEngine()
        try:
            updated_task = engine.transition_task(task.id, tenant_id, "reject", request.data.get("meta_data"))
            return Response(WorkflowTaskSerializer(updated_task).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
