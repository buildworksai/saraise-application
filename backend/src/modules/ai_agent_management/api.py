"""
DRF ViewSets for AI Agent Management module.
Provides REST API endpoints for all models.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from src.core.auth_utils import get_user_tenant_id

from .models import Agent, AgentExecution, AgentSchedulerTask, AgentLifecycleState
from .approval_models import ApprovalRequest, SoDPolicy, SoDViolation, ApprovalStatus
from .quota_models import TenantQuota, QuotaUsage
from .tool_models import Tool, ToolInvocation
from .serializers import (
    AgentSerializer,
    AgentExecutionSerializer,
    AgentSchedulerTaskSerializer,
    ApprovalRequestSerializer,
    SoDPolicySerializer,
    SoDViolationSerializer,
    TenantQuotaSerializer,
    QuotaUsageSerializer,
    ToolSerializer,
    ToolInvocationSerializer,
)
from .services import AgentService


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

    def get_queryset(self):
        """Filter agents by tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if tenant_id:
            return Agent.objects.filter(tenant_id=tenant_id)
        else:
            # Platform users can see all agents (for now, return empty queryset)
            # TODO: Implement platform-level access control
            return Agent.objects.none()

    def perform_create(self, serializer):
        """Set tenant_id and created_by from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise Response(
                {'error': 'Tenant ID required. Platform users cannot create agents.'},
                status=status.HTTP_403_FORBIDDEN
            )
        serializer.save(
            tenant_id=tenant_id,
            created_by=str(self.request.user.id)
        )

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute agent."""
        agent = self.get_object()
        service = AgentService()

        task_definition = request.data.get('task_definition', {})
        metadata = request.data.get('metadata', {})
        schedule = request.data.get('schedule', False)
        priority = request.data.get('priority', 0)

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
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        """Pause agent execution."""
        agent = self.get_object()
        execution_id = request.data.get('execution_id')

        if not execution_id:
            return Response(
                {'error': 'execution_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = AgentService()
            execution = service.pause_execution(execution_id, agent.tenant_id)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        """Resume agent execution."""
        agent = self.get_object()
        execution_id = request.data.get('execution_id')

        if not execution_id:
            return Response(
                {'error': 'execution_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = AgentService()
            execution = service.resume_execution(execution_id, agent.tenant_id)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def terminate(self, request, pk=None):
        """Terminate agent execution."""
        agent = self.get_object()
        execution_id = request.data.get('execution_id')

        if not execution_id:
            return Response(
                {'error': 'execution_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            service = AgentService()
            execution = service.terminate_execution(execution_id, agent.tenant_id)
            serializer = AgentExecutionSerializer(execution)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


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
        queryset = AgentExecution.objects.filter(
            tenant_id=tenant_id
        ).select_related('agent')

        # Optional filtering
        agent_id = self.request.query_params.get('agent_id')
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)

        state = self.request.query_params.get('state')
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
        return AgentSchedulerTask.objects.filter(
            tenant_id=tenant_id
        ).select_related('agent', 'execution')


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

    serializer_class = ApprovalRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter approval requests by tenant_id."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            return ApprovalRequest.objects.none()
        queryset = ApprovalRequest.objects.filter(
            agent_execution__tenant_id=tenant_id
        ).select_related('tool', 'agent_execution', 'tool_invocation')

        # Optional filtering
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def perform_create(self, serializer):
        """Set tenant_id from agent_execution."""
        approval = serializer.save()
        # tenant_id is inherited from agent_execution via TenantBaseModel

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve approval request."""
        approval = self.get_object()

        if approval.status != ApprovalStatus.PENDING:
            return Response(
                {'error': f'Approval request is {approval.status}, cannot approve'},
                status=status.HTTP_400_BAD_REQUEST
            )

        approval.status = ApprovalStatus.APPROVED
        approval.approver_id = request.user.id
        approval.decided_at = timezone.now()
        approval.save()

        serializer = self.get_serializer(approval)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject approval request."""
        approval = self.get_object()

        if approval.status != ApprovalStatus.PENDING:
            return Response(
                {'error': f'Approval request is {approval.status}, cannot reject'},
                status=status.HTTP_400_BAD_REQUEST
            )

        approval.status = ApprovalStatus.REJECTED
        approval.approver_id = request.user.id
        approval.rejection_reason = request.data.get('reason', '')
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
            raise Response(
                {'error': 'Tenant ID required. Platform users cannot create SoD policies.'},
                status=status.HTTP_403_FORBIDDEN
            )
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
        return SoDViolation.objects.filter(
            tenant_id=tenant_id
        ).select_related('policy', 'agent_execution', 'tool_invocation')


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
        quota_type = self.request.query_params.get('quota_type')
        if quota_type:
            queryset = queryset.filter(quota_type=quota_type)

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

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
        return QuotaUsage.objects.filter(
            tenant_id=tenant_id
        ).select_related('quota', 'agent_execution')


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
        owning_module = self.request.query_params.get('owning_module')
        if owning_module:
            queryset = queryset.filter(owning_module=owning_module)

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        return queryset

    def perform_create(self, serializer):
        """Set tenant_id from authenticated user."""
        tenant_id = get_user_tenant_id(self.request.user)
        if not tenant_id:
            raise Response(
                {'error': 'Tenant ID required. Platform users cannot create tools.'},
                status=status.HTTP_403_FORBIDDEN
            )
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
        queryset = ToolInvocation.objects.filter(
            tenant_id=self.request.user.tenant_id
        ).select_related('tool', 'agent_execution')

        # Optional filtering
        tool_id = self.request.query_params.get('tool_id')
        if tool_id:
            queryset = queryset.filter(tool_id=tool_id)

        agent_execution_id = self.request.query_params.get('agent_execution_id')
        if agent_execution_id:
            queryset = queryset.filter(agent_execution_id=agent_execution_id)

        success = self.request.query_params.get('success')
        if success is not None:
            queryset = queryset.filter(success=success.lower() == 'true')

        return queryset

