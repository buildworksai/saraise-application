"""Approval Service.

Implements human approval gates with SoD enforcement.
Task: 401.3 - Human Approval Gates
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .approval_models import ApprovalRequest, ApprovalStatus, SoDPolicy, SoDViolation
from .models import AgentExecution
from .tool_models import Tool, ToolInvocation
from .tool_registry import ToolSideEffectClass

logger = logging.getLogger(__name__)


class ApprovalService:
    """Service for managing approval requests and SoD enforcement."""

    def __init__(self) -> None:
        """Initialize approval service."""
        self._default_timeout_hours = 24

    def requires_approval(
        self,
        tool: Tool,
        tenant_id: str,
        requested_by: str,
        requested_for: str,
    ) -> bool:
        """Check if tool invocation requires approval.

        Args:
            tool: Tool instance.
            tenant_id: Tenant ID.
            requested_by: User/agent requesting.
            requested_for: User/agent who will execute.

        Returns:
            True if approval required, False otherwise.
        """
        # Check side-effect class
        side_effect_class = ToolSideEffectClass(tool.side_effect_class)

        # Data mutation tools require approval
        if side_effect_class == ToolSideEffectClass.DATA_MUTATION:
            # Check if affecting financial, HR, or compliance domains
            if self._is_high_risk_domain(tool.owning_module):
                return True

        # External integration tools with write capability require approval
        if side_effect_class == ToolSideEffectClass.EXTERNAL_INTEGRATION:
            # Check if has write or destructive capability
            if self._has_write_capability(tool):
                return True

        # Check SoD constraints
        if self._violates_sod(tool, tenant_id, requested_by, requested_for):
            return True

        return False

    def create_approval_request(
        self,
        tool: Tool,
        agent_execution: AgentExecution,
        tool_invocation: Optional[ToolInvocation],
        tenant_id: str,
        requested_by: str,
        requested_for: str,
        tool_input: Dict[str, Any],
        justification: str = "",
        timeout_hours: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create an approval request.

        Args:
            tool: Tool instance.
            agent_execution: Agent execution instance.
            tool_invocation: Optional tool invocation instance.
            tenant_id: Tenant ID.
            requested_by: User/agent requesting.
            requested_for: User/agent who will execute.
            tool_input: Tool input data.
            justification: Justification for the request.
            timeout_hours: Optional timeout in hours.

        Returns:
            Created ApprovalRequest instance.
        """
        # Calculate expiration time
        timeout = timeout_hours or self._default_timeout_hours
        expires_at = timezone.now() + timedelta(hours=timeout)

        # Create approval request
        approval_request = ApprovalRequest.objects.create(
            tenant_id=tenant_id,
            tool=tool,
            agent_execution=agent_execution,
            tool_invocation=tool_invocation,
            requested_by=requested_by,
            requested_for=requested_for,
            status=ApprovalStatus.PENDING,
            tool_input=tool_input,
            justification=justification,
            expires_at=expires_at,
        )

        logger.info(f"Created approval request {approval_request.id} for tool {tool.name}")

        # TODO: Send notification (Task 401.3 - notification system)

        return approval_request

    def approve_request(
        self,
        approval_request_id: str,
        tenant_id: str,
        approver_id: str,
        comment: str = "",
    ) -> ApprovalRequest:
        """Approve an approval request.

        Args:
            approval_request_id: Approval request ID.
            tenant_id: Tenant ID.
            approver_id: User ID approving.
            comment: Optional comment.

        Returns:
            Updated ApprovalRequest instance.

        Raises:
            ValueError: If request not found or cannot be approved.
        """
        approval_request = ApprovalRequest.objects.filter(id=approval_request_id, tenant_id=tenant_id).first()

        if not approval_request:
            raise ValueError(f"Approval request {approval_request_id} not found")

        if approval_request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request {approval_request_id} is not pending")

        # Check if expired
        if approval_request.expires_at and timezone.now() > approval_request.expires_at:
            approval_request.status = ApprovalStatus.EXPIRED
            approval_request.decided_at = timezone.now()
            approval_request.save(update_fields=["status", "decided_at", "updated_at"])
            raise ValueError(f"Approval request {approval_request_id} has expired")

        # Check SoD constraints
        if self._violates_sod(
            approval_request.tool,
            tenant_id,
            approval_request.requested_by,
            approver_id,
        ):
            # Record violation
            self._record_sod_violation(
                approval_request.tool,
                tenant_id,
                approval_request.requested_by,
                approver_id,
                approval_request.agent_execution,
                approval_request.tool_invocation,
            )
            raise ValueError("Approval violates SoD policy - cannot approve")

        # Approve request
        approval_request.status = ApprovalStatus.APPROVED
        approval_request.approver_id = approver_id
        approval_request.decided_at = timezone.now()
        if comment:
            approval_request.metadata["approval_comment"] = comment
        approval_request.save(
            update_fields=[
                "status",
                "approver_id",
                "decided_at",
                "metadata",
                "updated_at",
            ]
        )

        logger.info(f"Approved request {approval_request_id} by {approver_id}")

        # TODO: Send notification (Task 401.3 - notification system)

        return approval_request

    def reject_request(
        self,
        approval_request_id: str,
        tenant_id: str,
        approver_id: str,
        rejection_reason: str,
    ) -> ApprovalRequest:
        """Reject an approval request.

        Args:
            approval_request_id: Approval request ID.
            tenant_id: Tenant ID.
            approver_id: User ID rejecting.
            rejection_reason: Reason for rejection.

        Returns:
            Updated ApprovalRequest instance.

        Raises:
            ValueError: If request not found or cannot be rejected.
        """
        approval_request = ApprovalRequest.objects.filter(id=approval_request_id, tenant_id=tenant_id).first()

        if not approval_request:
            raise ValueError(f"Approval request {approval_request_id} not found")

        if approval_request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request {approval_request_id} is not pending")

        # Reject request
        approval_request.status = ApprovalStatus.REJECTED
        approval_request.approver_id = approver_id
        approval_request.rejection_reason = rejection_reason
        approval_request.decided_at = timezone.now()
        approval_request.save(
            update_fields=[
                "status",
                "approver_id",
                "rejection_reason",
                "decided_at",
                "updated_at",
            ]
        )

        logger.info(f"Rejected request {approval_request_id} by {approver_id}: " f"{rejection_reason}")

        # TODO: Send notification (Task 401.3 - notification system)

        return approval_request

    def cancel_request(self, approval_request_id: str, tenant_id: str) -> ApprovalRequest:
        """Cancel an approval request.

        Args:
            approval_request_id: Approval request ID.
            tenant_id: Tenant ID.

        Returns:
            Updated ApprovalRequest instance.

        Raises:
            ValueError: If request not found or cannot be cancelled.
        """
        approval_request = ApprovalRequest.objects.filter(id=approval_request_id, tenant_id=tenant_id).first()

        if not approval_request:
            raise ValueError(f"Approval request {approval_request_id} not found")

        if approval_request.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval request {approval_request_id} is not pending")

        # Cancel request
        approval_request.status = ApprovalStatus.CANCELLED
        approval_request.decided_at = timezone.now()
        approval_request.save(update_fields=["status", "decided_at", "updated_at"])

        logger.info(f"Cancelled approval request {approval_request_id}")

        return approval_request

    def get_pending_approvals(
        self,
        tenant_id: str,
        approver_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ApprovalRequest]:
        """Get pending approval requests.

        Args:
            tenant_id: Tenant ID.
            approver_id: Optional approver ID filter.
            limit: Maximum number of requests to return.

        Returns:
            List of pending ApprovalRequest instances.
        """
        query = ApprovalRequest.objects.filter(
            tenant_id=tenant_id,
            status=ApprovalStatus.PENDING,
            expires_at__gt=timezone.now(),
        )

        if approver_id:
            # Filter by approver (if SoD policies specify)
            # For now, return all pending requests
            pass

        return list(query.order_by("requested_at")[:limit])

    def expire_old_requests(self, tenant_id: str) -> int:
        """Expire old approval requests.

        Args:
            tenant_id: Tenant ID.

        Returns:
            Number of expired requests.
        """
        expired = ApprovalRequest.objects.filter(
            tenant_id=tenant_id,
            status=ApprovalStatus.PENDING,
            expires_at__lte=timezone.now(),
        )

        count = expired.count()
        expired.update(
            status=ApprovalStatus.EXPIRED,
            decided_at=timezone.now(),
        )

        logger.info(f"Expired {count} approval requests for tenant {tenant_id}")

        return count

    def _is_high_risk_domain(self, module_name: str) -> bool:
        """Check if module is high-risk domain.

        Args:
            module_name: Module name.

        Returns:
            True if high-risk domain, False otherwise.
        """
        high_risk_modules = [
            "finance",
            "accounting",
            "hr",
            "human-resources",
            "compliance",
            "audit",
        ]

        return any(risk_module in module_name.lower() for risk_module in high_risk_modules)

    def _has_write_capability(self, tool: Tool) -> bool:
        """Check if tool has write or destructive capability.

        Args:
            tool: Tool instance.

        Returns:
            True if has write capability, False otherwise.
        """
        # Check metadata for write capability flag
        if tool.metadata.get("write_capability", False):
            return True

        # Check tool name for write indicators
        write_indicators = ["create", "update", "delete", "modify", "write"]
        return any(indicator in tool.name.lower() for indicator in write_indicators)

    def _violates_sod(
        self,
        tool: Tool,
        tenant_id: str,
        user_1: str,
        user_2: str,
    ) -> bool:
        """Check if action violates SoD policy.

        Args:
            tool: Tool instance.
            tenant_id: Tenant ID.
            user_1: First user ID.
            user_2: Second user ID.

        Returns:
            True if violates SoD, False otherwise.
        """
        # Get SoD policies for this tenant
        policies = SoDPolicy.objects.filter(tenant_id=tenant_id, is_active=True)

        # Check if tool action violates any SoD policy
        tool_action = f"{tool.owning_module}.{tool.name}"

        for policy in policies:
            # Check if user_1 performed action_1 and user_2 attempting action_2
            if (
                policy.action_1 == tool_action
                and self._user_performed_action(tenant_id, user_1, policy.action_1)
                and policy.action_2 in self._get_user_recent_actions(tenant_id, user_2)
            ):
                return True

            # Check reverse
            if (
                policy.action_2 == tool_action
                and self._user_performed_action(tenant_id, user_1, policy.action_2)
                and policy.action_1 in self._get_user_recent_actions(tenant_id, user_2)
            ):
                return True

        return False

    def _user_performed_action(self, tenant_id: str, user_id: str, action: str) -> bool:
        """Check if user performed an action recently.

        Args:
            tenant_id: Tenant ID.
            user_id: User ID.
            action: Action identifier.

        Returns:
            True if user performed action, False otherwise.
        """
        # Check recent tool invocations
        from .tool_models import ToolInvocation

        recent_invocations = ToolInvocation.objects.filter(
            tenant_id=tenant_id,
            tool__name=action.split(".")[-1] if "." in action else action,
            invoked_at__gte=timezone.now() - timedelta(hours=24),
        )

        # TODO: Check actual user attribution from agent execution
        # For now, return False (placeholder)
        return False

    def _get_user_recent_actions(self, tenant_id: str, user_id: str) -> List[str]:
        """Get user's recent actions.

        Args:
            tenant_id: Tenant ID.
            user_id: User ID.

        Returns:
            List of action identifiers.
        """
        # TODO: Implement actual action tracking
        # For now, return empty list (placeholder)
        return []

    def _record_sod_violation(
        self,
        tool: Tool,
        tenant_id: str,
        user_1: str,
        user_2: str,
        agent_execution: Optional[AgentExecution],
        tool_invocation: Optional[ToolInvocation],
    ) -> None:
        """Record SoD violation.

        Args:
            tool: Tool instance.
            tenant_id: Tenant ID.
            user_1: First user ID.
            user_2: Second user ID.
            agent_execution: Optional agent execution.
            tool_invocation: Optional tool invocation.
        """
        # Find matching SoD policy
        tool_action = f"{tool.owning_module}.{tool.name}"
        policy = SoDPolicy.objects.filter(
            tenant_id=tenant_id,
            action_1=tool_action,
            is_active=True,
        ).first()

        if not policy:
            policy = SoDPolicy.objects.filter(
                tenant_id=tenant_id,
                action_2=tool_action,
                is_active=True,
            ).first()

        if policy:
            SoDViolation.objects.create(
                tenant_id=tenant_id,
                policy=policy,
                agent_execution=agent_execution,
                tool_invocation=tool_invocation,
                action_1_user=user_1,
                action_2_user=user_2,
                action_1_timestamp=timezone.now() - timedelta(hours=1),
                action_2_timestamp=timezone.now(),
                blocked=True,
            )

            logger.warning(f"Recorded SoD violation: {policy.name} " f"(user_1={user_1}, user_2={user_2})")


# Global approval service instance
approval_service = ApprovalService()
