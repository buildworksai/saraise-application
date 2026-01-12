"""AI Audit Trail Service.

Implements comprehensive audit trail: request → agent → tool → outcome.
Task: 403.1 - AI Audit Trail
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .audit_models import AuditEvent, AuditEventType, AuditTrail
from .models import AgentExecution

logger = logging.getLogger(__name__)


class AuditService:
    """Service for managing AI audit trail."""

    def __init__(self) -> None:
        """Initialize audit service."""
        pass

    def create_audit_trail(
        self,
        tenant_id: str,
        request_id: str,
        agent_execution: AgentExecution,
        initiating_principal: str,
    ) -> AuditTrail:
        """Create a new audit trail for a request.

        Args:
            tenant_id: Tenant ID.
            request_id: Request ID (unique identifier).
            agent_execution: Agent execution instance.
            initiating_principal: User/agent who initiated.

        Returns:
            Created AuditTrail instance.
        """
        trail = AuditTrail.objects.create(
            tenant_id=tenant_id,
            request_id=request_id,
            agent_execution=agent_execution,
            initiating_principal=initiating_principal,
            summary={
                "tools_invoked": [],
                "approvals_requested": [],
                "policy_decisions": [],
            },
        )

        logger.info(f"Created audit trail {trail.id} for request {request_id}")

        return trail

    def record_event(
        self,
        tenant_id: str,
        event_type: str,
        initiating_principal: str,
        subject_id: str,
        outcome: str,
        agent_execution: Optional[AgentExecution] = None,
        tool_invocation: Optional[Any] = None,
        approval_request: Optional[Any] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        outcome_details: Optional[Dict[str, Any]] = None,
        policy_decisions: Optional[List[Dict[str, Any]]] = None,
        workflow_transitions: Optional[List[Dict[str, Any]]] = None,
        affected_resources: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Record an audit event.

        Args:
            tenant_id: Tenant ID.
            event_type: Event type.
            initiating_principal: User/agent who initiated.
            subject_id: Subject ID.
            outcome: Event outcome (success, failure, blocked, pending).
            agent_execution: Optional agent execution instance.
            tool_invocation: Optional tool invocation instance.
            approval_request: Optional approval request instance.
            session_id: Optional session ID.
            request_id: Optional request ID.
            outcome_details: Optional outcome details.
            policy_decisions: Optional policy decisions.
            workflow_transitions: Optional workflow transitions.
            affected_resources: Optional affected resources.
            metadata: Optional metadata.

        Returns:
            Created AuditEvent instance.
        """
        event = AuditEvent.objects.create(
            tenant_id=tenant_id,
            event_type=event_type,
            agent_execution=agent_execution,
            tool_invocation=tool_invocation,
            approval_request=approval_request,
            initiating_principal=initiating_principal,
            subject_id=subject_id,
            session_id=session_id,
            request_id=request_id,
            outcome=outcome,
            outcome_details=outcome_details or {},
            policy_decisions=policy_decisions or [],
            workflow_transitions=workflow_transitions or [],
            affected_resources=affected_resources or [],
            metadata=metadata or {},
        )

        # Add to audit trail if request_id provided
        if request_id:
            trail = AuditTrail.objects.filter(tenant_id=tenant_id, request_id=request_id).first()
            if trail:
                trail.events.add(event)

                # Update trail summary
                self._update_trail_summary(trail, event)

        logger.debug(f"Recorded audit event {event.id}: {event_type} ({outcome})")

        return event

    def record_agent_lifecycle_event(
        self,
        tenant_id: str,
        agent_execution: AgentExecution,
        event_type: str,
        outcome: str,
        outcome_details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Record agent lifecycle event.

        Args:
            tenant_id: Tenant ID.
            agent_execution: Agent execution instance.
            event_type: Event type (agent_started, agent_completed, etc.).
            outcome: Event outcome.
            outcome_details: Optional outcome details.

        Returns:
            Created AuditEvent instance.
        """
        return self.record_event(
            tenant_id=tenant_id,
            event_type=event_type,
            initiating_principal=agent_execution.agent.subject_id,
            subject_id=agent_execution.agent.subject_id,
            outcome=outcome,
            agent_execution=agent_execution,
            session_id=agent_execution.session_id,
            outcome_details=outcome_details,
            metadata={
                "agent_id": agent_execution.agent.id,
                "agent_name": agent_execution.agent.name,
                "task_definition": agent_execution.task_definition,
            },
        )

    def record_tool_invocation_event(
        self,
        tenant_id: str,
        tool_invocation: Any,
        agent_execution: AgentExecution,
        outcome: str,
        outcome_details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Record tool invocation event.

        Args:
            tenant_id: Tenant ID.
            tool_invocation: Tool invocation instance.
            agent_execution: Agent execution instance.
            outcome: Event outcome.
            outcome_details: Optional outcome details.

        Returns:
            Created AuditEvent instance.
        """
        return self.record_event(
            tenant_id=tenant_id,
            event_type=AuditEventType.TOOL_INVOKED,
            initiating_principal=agent_execution.agent.subject_id,
            subject_id=agent_execution.agent.subject_id,
            outcome=outcome,
            agent_execution=agent_execution,
            tool_invocation=tool_invocation,
            session_id=agent_execution.session_id,
            outcome_details=outcome_details,
            affected_resources=[
                f"tool:{tool_invocation.tool.name}",
                f"module:{tool_invocation.tool.owning_module}",
            ],
            metadata={
                "tool_name": tool_invocation.tool.name,
                "tool_input": tool_invocation.input_data,
                "tool_output": tool_invocation.output_data if tool_invocation.success else None,
                "duration_ms": tool_invocation.duration_ms,
            },
        )

    def record_approval_event(
        self,
        tenant_id: str,
        approval_request: Any,
        agent_execution: AgentExecution,
        event_type: str,
        outcome: str,
        approver_id: Optional[str] = None,
        outcome_details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Record approval event.

        Args:
            tenant_id: Tenant ID.
            approval_request: Approval request instance.
            agent_execution: Agent execution instance.
            event_type: Event type (approval_requested, approval_granted, etc.).
            outcome: Event outcome.
            approver_id: Optional approver ID.
            outcome_details: Optional outcome details.

        Returns:
            Created AuditEvent instance.
        """
        return self.record_event(
            tenant_id=tenant_id,
            event_type=event_type,
            initiating_principal=approver_id or approval_request.requested_by,
            subject_id=approval_request.requested_for,
            outcome=outcome,
            agent_execution=agent_execution,
            approval_request=approval_request,
            session_id=agent_execution.session_id,
            outcome_details=outcome_details,
            metadata={
                "tool_name": approval_request.tool.name,
                "justification": approval_request.justification,
                "approver_id": approver_id,
            },
        )

    def complete_audit_trail(
        self,
        request_id: str,
        tenant_id: str,
        final_outcome: str,
        summary: Optional[Dict[str, Any]] = None,
    ) -> AuditTrail:
        """Complete an audit trail.

        Args:
            request_id: Request ID.
            tenant_id: Tenant ID.
            final_outcome: Final outcome.
            summary: Optional summary.

        Returns:
            Updated AuditTrail instance.

        Raises:
            ValueError: If trail not found.
        """
        trail = AuditTrail.objects.filter(tenant_id=tenant_id, request_id=request_id).first()

        if not trail:
            raise ValueError(f"Audit trail {request_id} not found")

        trail.completed_timestamp = timezone.now()
        trail.final_outcome = final_outcome

        if summary:
            trail.summary.update(summary)

        trail.save(
            update_fields=[
                "completed_timestamp",
                "final_outcome",
                "summary",
                "updated_at",
            ]
        )

        logger.info(f"Completed audit trail {trail.id} with outcome {final_outcome}")

        return trail

    def get_audit_trail(self, request_id: str, tenant_id: str) -> Optional[AuditTrail]:
        """Get audit trail by request ID.

        Args:
            request_id: Request ID.
            tenant_id: Tenant ID.

        Returns:
            AuditTrail instance or None if not found.
        """
        return AuditTrail.objects.filter(tenant_id=tenant_id, request_id=request_id).prefetch_related("events").first()

    def query_audit_events(
        self,
        tenant_id: str,
        event_type: Optional[str] = None,
        agent_execution_id: Optional[str] = None,
        initiating_principal: Optional[str] = None,
        outcome: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[AuditEvent]:
        """Query audit events.

        Args:
            tenant_id: Tenant ID.
            event_type: Optional event type filter.
            agent_execution_id: Optional agent execution ID filter.
            initiating_principal: Optional principal filter.
            outcome: Optional outcome filter.
            start_time: Optional start time filter.
            end_time: Optional end time filter.
            limit: Maximum number of events to return.

        Returns:
            List of AuditEvent instances.
        """
        query = AuditEvent.objects.filter(tenant_id=tenant_id)

        if event_type:
            query = query.filter(event_type=event_type)

        if agent_execution_id:
            query = query.filter(agent_execution_id=agent_execution_id)

        if initiating_principal:
            query = query.filter(initiating_principal=initiating_principal)

        if outcome:
            query = query.filter(outcome=outcome)

        if start_time:
            query = query.filter(event_timestamp__gte=start_time)

        if end_time:
            query = query.filter(event_timestamp__lte=end_time)

        return list(query.order_by("-event_timestamp")[:limit])

    def _update_trail_summary(self, trail: AuditTrail, event: AuditEvent) -> None:
        """Update audit trail summary with new event.

        Args:
            trail: AuditTrail instance.
            event: AuditEvent instance.
        """
        summary = trail.summary

        # Track tools invoked
        if event.event_type == AuditEventType.TOOL_INVOKED:
            if "tools_invoked" not in summary:
                summary["tools_invoked"] = []
            summary["tools_invoked"].append(
                {
                    "tool_name": event.metadata.get("tool_name"),
                    "timestamp": event.event_timestamp.isoformat(),
                    "outcome": event.outcome,
                }
            )

        # Track approvals
        if event.event_type in [
            AuditEventType.APPROVAL_REQUESTED,
            AuditEventType.APPROVAL_GRANTED,
            AuditEventType.APPROVAL_REJECTED,
        ]:
            if "approvals_requested" not in summary:
                summary["approvals_requested"] = []
            summary["approvals_requested"].append(
                {
                    "event_type": event.event_type,
                    "timestamp": event.event_timestamp.isoformat(),
                    "outcome": event.outcome,
                }
            )

        # Track policy decisions
        if event.policy_decisions:
            if "policy_decisions" not in summary:
                summary["policy_decisions"] = []
            summary["policy_decisions"].extend(event.policy_decisions)

        trail.summary = summary
        trail.save(update_fields=["summary", "updated_at"])


# Global audit service instance
audit_service = AuditService()
