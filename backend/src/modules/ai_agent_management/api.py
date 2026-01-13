"""
DRF ViewSets for AI Agent Management module.
Provides REST API endpoints for all models.
"""

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from src.core.auth_utils import get_user_tenant_id

from .approval_models import ApprovalRequest, ApprovalStatus, SoDPolicy, SoDViolation
from .models import Agent, AgentExecution, AgentSchedulerTask
from .quota_models import QuotaUsage, TenantQuota
from .serializers import (
    AgentExecutionSerializer,
    AgentSchedulerTaskSerializer,
    AgentSerializer,
    ApprovalRequestSerializer,
    QuotaUsageSerializer,
    SoDPolicySerializer,
    SoDViolationSerializer,
    TenantQuotaSerializer,
    ToolInvocationSerializer,
    ToolSerializer,
)
from .services import AgentService
from .tool_models import Tool, ToolInvocation


class AgentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Agent CRUD operations.

    Endpoints:
    - GET /api/v1/ai-agents/agents/ - List all agents
    - POST /api/v1/ai-agents/agents/ - Create agent
    - GET /api/v1/ai-agents/agents/{id}/ - Get agent detail
    - PUT /api/v1/ai-agents/agents/{id}/ - Update agent
    - PATCH /api/v1/ai-agents/agents/{id}/ - Partial update agent
    - DELETE /api/v1/ai-agents/agents/{id}/ - Delete agent
    - POST /api/v1/ai-agents/agents/{id}/execute/ - Execute agent
    - POST /api/v1/ai-agents/agents/{id}/pause/ - Pause agent
    - POST /api/v1/ai-agents/agents/{id}/resume/ - Resume agent
    - POST /api/v1/ai-agents/agents/{id}/terminate/ - Terminate agent
    """

    serializer_class = AgentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        Override to allow unauthenticated list requests.

        CRITICAL: For list action, allow unauthenticated access to return empty list
        instead of 403 to prevent retry loops and improve perceived performance.
        """
        # Check if this is a list action
        # self.action is set by DRF router in dispatch() before get_permissions() is called
        action = getattr(self, "action", None)

        # Fallback: determine action from request path if action not set
        # This is needed because self.action might not be set in all cases
        if action is None and hasattr(self, "request") and self.request:
            if self.request.method == "GET":
                path = self.request.path
                # Simple check: if path ends with /agents/ or /agents, it's likely a list action
                # (detail views would have an ID in the path)
                if path.endswith("/agents/") or path.endswith("/agents"):
                    # Additional check: make sure it's not a detail view
                    # Detail views have pattern like /agents/{uuid}/ or /agents/{uuid}
                    import re

                    # If path doesn't match detail pattern, it's a list action
                    if not re.search(r"/agents/[a-f0-9-]{36}", path):
                        action = "list"

        # For list action, allow unauthenticated access
        if action == "list":
            return [AllowAny()]

        # For all other actions, require authentication
        return [IsAuthenticated()]

    def get_queryset(self):
        """Filter agents by tenant_id from authenticated user."""
        # For unauthenticated users (list action only), return empty queryset
        if not self.request.user or not self.request.user.is_authenticated:
            return Agent.objects.none()

        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            # This should never happen for authenticated tenant users,
            # but handle gracefully to prevent data leakage
            return Agent.objects.none()
        return Agent.objects.filter(tenant_id=tenant_id).order_by("-created_at")

    def check_object_permissions(self, request, obj):
        """Override to skip object permission check for list action."""
        # For list action, we don't have an object, so skip this check
        if self.action == "list":
            return
        super().check_object_permissions(request, obj)

    def list(self, request, *args, **kwargs):
        """
        Override list to always return 200 OK, even if queryset is empty or user not authenticated.

        CRITICAL: Per architectural guidelines, DRF ViewSets should return 200 OK
        with empty list instead of errors when queryset is empty. This ensures
        consistent API behavior and prevents frontend retry loops.
        """
        # If authentication failed (caught in initial()), return empty list
        if hasattr(request, "_auth_exception"):
            return Response([])

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("Tenant ID required. Platform users cannot create agents.")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        """Execute agent."""
        agent = self.get_object()
        service = AgentService()

        task_definition = request.data.get("task_definition", {})
        metadata = request.data.get("metadata", {})
        schedule = request.data.get("schedule", False)
        priority = request.data.get("priority", 0)

        try:
            execution = service.create_execution(
                agent_id=agent.id,
                tenant_id=agent.tenant_id,
                task_definition=task_definition,
                metadata=metadata,
                schedule=schedule,
                priority=priority,
            )
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """Pause agent execution."""
        agent = self.get_object()
        execution_id = request.data.get("execution_id")

        if not execution_id:
            return Response({"error": "execution_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            service = AgentService()
            execution = service.pause_execution(execution_id, agent.tenant_id)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """Resume agent execution."""
        agent = self.get_object()
        execution_id = request.data.get("execution_id")

        if not execution_id:
            return Response({"error": "execution_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            service = AgentService()
            execution = service.resume_execution(execution_id, agent.tenant_id)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def terminate(self, request, pk=None):
        """Terminate agent execution."""
        agent = self.get_object()
        execution_id = request.data.get("execution_id")

        if not execution_id:
            return Response({"error": "execution_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            service = AgentService()
            execution = service.terminate_execution(execution_id, agent.tenant_id)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AgentExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AgentExecution (read-only).

    Endpoints:
    - GET /api/v1/ai-agents/executions/ - List executions
    - GET /api/v1/ai-agents/executions/{id}/ - Get execution detail
    """

    serializer_class = AgentExecutionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter executions by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return AgentExecution.objects.none()
        queryset = AgentExecution.objects.filter(tenant_id=tenant_id).select_related("agent")

        # Optional filtering
        agent_id = self.request.query_params.get("agent_id")
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)

        state = self.request.query_params.get("state")
        if state:
            queryset = queryset.filter(state=state)

        return queryset


class AgentSchedulerTaskViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AgentSchedulerTask (read-only).

    Endpoints:
    - GET /api/v1/ai-agents/scheduler-tasks/ - List scheduler tasks
    - GET /api/v1/ai-agents/scheduler-tasks/{id}/ - Get scheduler task detail
    """

    serializer_class = AgentSchedulerTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter scheduler tasks by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return AgentSchedulerTask.objects.none()
        return AgentSchedulerTask.objects.filter(tenant_id=tenant_id).select_related("agent", "execution")


class ApprovalRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ApprovalRequest.

    Endpoints:
    - GET /api/v1/ai-agents/approvals/ - List approval requests
    - GET /api/v1/ai-agents/approvals/{id}/ - Get approval detail
    - POST /api/v1/ai-agents/approvals/ - Create approval request
    - POST /api/v1/ai-agents/approvals/{id}/approve/ - Approve request
    - POST /api/v1/ai-agents/approvals/{id}/reject/ - Reject request
    """

    # CRITICAL: Don't override authentication_classes - use default from settings
    # This ensures consistent authentication behavior across all ViewSets
    # The default RelaxedCsrfSessionAuthentication from settings handles session auth correctly
    serializer_class = ApprovalRequestSerializer
    permission_classes = [IsAuthenticated]

    def check_object_permissions(self, request, obj):
        """Override to skip object permission check for list action."""
        # For list action, we don't have an object, so skip this check
        if self.action == "list":
            return
        super().check_object_permissions(request, obj)

    def get_queryset(self):
        """Filter approval requests by tenant_id.

        CRITICAL: ApprovalRequest inherits from TenantBaseModel, so it has tenant_id directly.
        Filter directly on tenant_id instead of through agent_execution__tenant_id to avoid
        unnecessary JOINs and improve query performance.
        """
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return ApprovalRequest.objects.none()

        # CRITICAL: Filter directly on tenant_id (from TenantBaseModel) instead of
        # agent_execution__tenant_id to avoid unnecessary JOIN and improve performance
        queryset = ApprovalRequest.objects.filter(tenant_id=tenant_id).select_related(
            "tool", "agent_execution", "tool_invocation"
        )

        # Optional filtering
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Add ordering for consistent results and better performance
        queryset = queryset.order_by("-requested_at")

        return queryset

    def initial(self, request, *args, **kwargs):
        """
        Override initial to catch authentication errors for list action.

        CRITICAL: DRF's initial() raises 403 if authentication fails.
        For list action, we catch this and allow list() to return empty list instead.
        """
        # Set action early
        self.action = kwargs.get("action", self.action)
        try:
            # Call parent to handle authentication and permissions
            super().initial(request, *args, **kwargs)
        except (NotAuthenticated, PermissionDenied) as e:
            # Store the exception so list() can handle it gracefully
            # Only store for list action - other actions should raise normally
            if self.action == "list":
                request._auth_exception = e
            else:
                # For non-list actions, re-raise the exception
                raise

    def list(self, request, *args, **kwargs):
        """
        Override list to always return 200 OK, even if queryset is empty or user not authenticated.

        CRITICAL: Per architectural guidelines (see PlatformSettingViewSet pattern),
        DRF ViewSets should return 200 OK with empty list instead of 403 Forbidden
        when queryset is empty. This prevents unnecessary retries and improves UX.

        PERFORMANCE: Limit queryset to 100 items max to prevent large payloads.

        AUTHENTICATION FIX: If authentication failed in initial(), return empty list
        instead of 403 to prevent retry loops and improve perceived performance.
        """
        # If authentication failed in initial(), return empty list
        if hasattr(request, "_auth_exception"):
            return Response([])

        queryset = self.filter_queryset(self.get_queryset())

        # PERFORMANCE: Limit results to prevent large payloads
        # Use [:100] slice instead of pagination for better performance on small datasets
        queryset = queryset[:100]

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Set tenant_id from agent_execution."""
        _approval = serializer.save()  # noqa: F841
        # tenant_id is inherited from agent_execution via TenantBaseModel

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approve approval request."""
        approval = self.get_object()

        if approval.status != ApprovalStatus.PENDING:
            return Response(
                {"error": f"Approval request is {approval.status}, cannot approve"}, status=status.HTTP_400_BAD_REQUEST
            )

        approval.status = ApprovalStatus.APPROVED
        approval.approver_id = request.user.id
        approval.decided_at = timezone.now()
        approval.save()

        serializer = self.get_serializer(approval)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Reject approval request."""
        approval = self.get_object()

        if approval.status != ApprovalStatus.PENDING:
            return Response(
                {"error": f"Approval request is {approval.status}, cannot reject"}, status=status.HTTP_400_BAD_REQUEST
            )

        approval.status = ApprovalStatus.REJECTED
        approval.approver_id = request.user.id
        approval.rejection_reason = request.data.get("reason", "")
        approval.decided_at = timezone.now()
        approval.save()

        serializer = self.get_serializer(approval)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SoDPolicyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SoDPolicy.

    Endpoints:
    - GET /api/v1/ai-agents/sod-policies/ - List SoD policies
    - POST /api/v1/ai-agents/sod-policies/ - Create SoD policy
    - GET /api/v1/ai-agents/sod-policies/{id}/ - Get SoD policy detail
    - PUT /api/v1/ai-agents/sod-policies/{id}/ - Update SoD policy
    - DELETE /api/v1/ai-agents/sod-policies/{id}/ - Delete SoD policy
    """

    serializer_class = SoDPolicySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter SoD policies by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return SoDPolicy.objects.none()
        return SoDPolicy.objects.filter(tenant_id=tenant_id)

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("Tenant ID required. Platform users cannot create SoD policies.")
        serializer.save(tenant_id=tenant_id, created_by=str(self.request.user.id))


class SoDViolationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for SoDViolation (read-only).

    Endpoints:
    - GET /api/v1/ai-agents/sod-violations/ - List SoD violations
    - GET /api/v1/ai-agents/sod-violations/{id}/ - Get SoD violation detail
    """

    serializer_class = SoDViolationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter SoD violations by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return SoDViolation.objects.none()
        return SoDViolation.objects.filter(tenant_id=tenant_id).select_related(
            "policy", "agent_execution", "tool_invocation"
        )


class TenantQuotaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for TenantQuota (read-only).

    Endpoints:
    - GET /api/v1/ai-agents/quotas/ - List quotas
    - GET /api/v1/ai-agents/quotas/{id}/ - Get quota detail
    """

    serializer_class = TenantQuotaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter quotas by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return TenantQuota.objects.none()
        queryset = TenantQuota.objects.filter(tenant_id=tenant_id)

        # Optional filtering
        quota_type = self.request.query_params.get("quota_type")
        if quota_type:
            queryset = queryset.filter(quota_type=quota_type)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset


class QuotaUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for QuotaUsage (read-only).

    Endpoints:
    - GET /api/v1/ai-agents/quota-usage/ - List quota usage records
    - GET /api/v1/ai-agents/quota-usage/{id}/ - Get quota usage detail
    """

    serializer_class = QuotaUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter quota usage by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return QuotaUsage.objects.none()
        return QuotaUsage.objects.filter(tenant_id=tenant_id).select_related("quota", "agent_execution")


class ToolViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Tool.

    Endpoints:
    - GET /api/v1/ai-agents/tools/ - List tools
    - POST /api/v1/ai-agents/tools/ - Create tool
    - GET /api/v1/ai-agents/tools/{id}/ - Get tool detail
    - PUT /api/v1/ai-agents/tools/{id}/ - Update tool
    - DELETE /api/v1/ai-agents/tools/{id}/ - Delete tool
    """

    serializer_class = ToolSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter tools by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return Tool.objects.none()
        queryset = Tool.objects.filter(tenant_id=tenant_id)

        # Optional filtering
        owning_module = self.request.query_params.get("owning_module")
        if owning_module:
            queryset = queryset.filter(owning_module=owning_module)

        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise PermissionDenied("Tenant ID required. Platform users cannot create tools.")
        serializer.save(tenant_id=tenant_id, registered_by=str(self.request.user.id))


class ToolInvocationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for ToolInvocation (read-only).

    Endpoints:
    - GET /api/v1/ai-agents/tool-invocations/ - List tool invocations
    - GET /api/v1/ai-agents/tool-invocations/{id}/ - Get tool invocation detail
    """

    serializer_class = ToolInvocationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter tool invocations by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return ToolInvocation.objects.none()
        queryset = ToolInvocation.objects.filter(tenant_id=tenant_id).select_related("tool", "agent_execution")

        # Optional filtering
        tool_id = self.request.query_params.get("tool_id")
        if tool_id:
            queryset = queryset.filter(tool_id=tool_id)

        agent_execution_id = self.request.query_params.get("agent_execution_id")
        if agent_execution_id:
            queryset = queryset.filter(agent_execution_id=agent_execution_id)

        success = self.request.query_params.get("success")
        if success is not None:
            queryset = queryset.filter(success=success.lower() == "true")

        return queryset
