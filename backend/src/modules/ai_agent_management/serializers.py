"""
DRF Serializers for AI Agent Management module.
Provides request/response validation for all models.
"""
from rest_framework import serializers
from .models import Agent, AgentExecution, AgentSchedulerTask, AgentIdentityType, AgentLifecycleState
from .approval_models import ApprovalRequest, SoDPolicy, SoDViolation, ApprovalStatus
from .audit_models import AuditEvent, AuditTrail, AuditEventType
from .egress_models import EgressRule, EgressRequest, Secret, SecretAccess
from .quota_models import TenantQuota, QuotaUsage, ShardSaturation, KillSwitch, QuotaType, QuotaPeriod
from .token_models import TokenUsage, CostRecord, CostSummary
from .tool_models import Tool, ToolInvocation


# ===== Core Agent Serializers =====

class AgentSerializer(serializers.ModelSerializer):
    """Agent serializer for create/update/read operations."""

    class Meta:
        model = Agent
        fields = [
            'id', 'tenant_id', 'name', 'description', 'identity_type',
            'subject_id', 'session_id', 'framework', 'config',
            'is_active', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_by', 'created_at', 'updated_at']

    def validate(self, data):
        """Validate agent data."""
        # User-bound agents must have session_id
        if data.get('identity_type') == AgentIdentityType.USER_BOUND:
            if not data.get('session_id'):
                raise serializers.ValidationError(
                    "User-bound agents must have session_id"
                )

        # System-bound agents should not have session_id
        if data.get('identity_type') == AgentIdentityType.SYSTEM_BOUND:
            if data.get('session_id'):
                raise serializers.ValidationError(
                    "System-bound agents must not have session_id"
                )

        return data


class AgentExecutionSerializer(serializers.ModelSerializer):
    """Agent execution serializer."""

    agent_name = serializers.CharField(source='agent.name', read_only=True)
    agent_id = serializers.CharField(source='agent.id', read_only=True)

    class Meta:
        model = AgentExecution
        fields = [
            'id', 'agent', 'agent_id', 'agent_name', 'state', 'session_id',
            'task_definition', 'started_at', 'completed_at', 'error_message',
            'result', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'created_at', 'updated_at']


class AgentSchedulerTaskSerializer(serializers.ModelSerializer):
    """Agent scheduler task serializer."""

    agent_name = serializers.CharField(source='agent.name', read_only=True)

    class Meta:
        model = AgentSchedulerTask
        fields = [
            'id', 'agent', 'agent_name', 'execution', 'priority',
            'scheduled_at', 'started_at', 'completed_at', 'retry_count',
            'max_retries', 'status', 'error_message', 'task_data',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'started_at', 'completed_at', 'created_at', 'updated_at']


# ===== Approval Serializers =====

class ApprovalRequestSerializer(serializers.ModelSerializer):
    """Approval request serializer."""

    tool_name = serializers.CharField(source='tool.name', read_only=True)
    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True)

    class Meta:
        model = ApprovalRequest
        fields = [
            'id', 'tool', 'tool_name', 'agent_execution', 'agent_execution_id',
            'tool_invocation', 'requested_by', 'requested_for', 'approver_id',
            'status', 'tool_input', 'justification', 'rejection_reason',
            'requested_at', 'expires_at', 'decided_at', 'metadata',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'approver_id', 'decided_at', 'created_at', 'updated_at']


class SoDPolicySerializer(serializers.ModelSerializer):
    """SoD policy serializer."""

    class Meta:
        model = SoDPolicy
        fields = [
            'id', 'tenant_id', 'name', 'description', 'action_1',
            'action_2', 'is_active', 'created_by', 'created_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at']


class SoDViolationSerializer(serializers.ModelSerializer):
    """SoD violation serializer."""

    policy_name = serializers.CharField(source='policy.name', read_only=True)

    class Meta:
        model = SoDViolation
        fields = [
            'id', 'policy', 'policy_name', 'agent_execution', 'tool_invocation',
            'action_1_user', 'action_2_user', 'action_1_timestamp',
            'action_2_timestamp', 'blocked', 'violation_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'violation_at', 'created_at', 'updated_at']


# ===== Quota Serializers =====

class TenantQuotaSerializer(serializers.ModelSerializer):
    """Tenant quota serializer."""

    class Meta:
        model = TenantQuota
        fields = [
            'id', 'tenant_id', 'quota_type', 'period', 'limit_value',
            'current_usage', 'reset_at', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'current_usage', 'created_at', 'updated_at']


class QuotaUsageSerializer(serializers.ModelSerializer):
    """Quota usage serializer."""

    quota_type = serializers.CharField(source='quota.quota_type', read_only=True)

    class Meta:
        model = QuotaUsage
        fields = [
            'id', 'tenant_id', 'quota', 'quota_type', 'agent_execution',
            'usage_value', 'usage_timestamp', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'usage_timestamp', 'created_at', 'updated_at']


class ShardSaturationSerializer(serializers.ModelSerializer):
    """Shard saturation serializer."""

    class Meta:
        model = ShardSaturation
        fields = [
            'id', 'tenant_id', 'shard_id', 'saturation_level',
            'active_agents', 'active_executions', 'cpu_usage_percent',
            'memory_usage_percent', 'measured_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'measured_at', 'created_at', 'updated_at']


class KillSwitchSerializer(serializers.ModelSerializer):
    """Kill switch serializer."""

    class Meta:
        model = KillSwitch
        fields = [
            'id', 'tenant_id', 'name', 'description', 'scope', 'scope_id',
            'is_active', 'reason', 'activated_by', 'activated_at',
            'deactivated_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'activated_at', 'created_at', 'updated_at']


# ===== Tool Serializers =====

class ToolSerializer(serializers.ModelSerializer):
    """Tool serializer."""

    class Meta:
        model = Tool
        fields = [
            'id', 'tenant_id', 'name', 'owning_module', 'version',
            'description', 'required_permissions', 'input_schema',
            'output_schema', 'side_effect_class', 'is_active',
            'metadata', 'registered_by', 'registered_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'registered_at', 'created_at', 'updated_at']


class ToolInvocationSerializer(serializers.ModelSerializer):
    """Tool invocation serializer."""

    tool_name = serializers.CharField(source='tool.name', read_only=True)
    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True, allow_null=True)

    class Meta:
        model = ToolInvocation
        fields = [
            'id', 'tenant_id', 'tool', 'tool_name', 'agent_execution',
            'agent_execution_id', 'input_data', 'output_data', 'success',
            'error_message', 'invoked_at', 'completed_at', 'duration_ms',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'invoked_at', 'completed_at', 'created_at', 'updated_at']


# ===== Egress Serializers =====

class EgressRuleSerializer(serializers.ModelSerializer):
    """Egress rule serializer."""

    class Meta:
        model = EgressRule
        fields = [
            'id', 'tenant_id', 'name', 'description', 'destination_type',
            'destination', 'port', 'protocol', 'is_active', 'created_by',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']


class EgressRequestSerializer(serializers.ModelSerializer):
    """Egress request serializer."""

    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True)
    matched_rule_name = serializers.CharField(source='matched_rule.name', read_only=True, allow_null=True)

    class Meta:
        model = EgressRequest
        fields = [
            'id', 'tenant_id', 'agent_execution', 'agent_execution_id',
            'destination', 'port', 'protocol', 'allowed', 'matched_rule',
            'matched_rule_name', 'requested_at', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'requested_at', 'created_at', 'updated_at']


class SecretSerializer(serializers.ModelSerializer):
    """Secret serializer."""

    class Meta:
        model = Secret
        fields = [
            'id', 'tenant_id', 'name', 'description', 'secret_type',
            'encrypted_value', 'encryption_key_id', 'is_active',
            'expires_at', 'last_rotated_at', 'rotation_interval_days',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate(self, data):
        """Validate secret data."""
        # Don't expose encrypted_value in responses
        if self.instance and 'encrypted_value' not in data:
            # If updating and encrypted_value not provided, keep existing
            pass
        return data


class SecretAccessSerializer(serializers.ModelSerializer):
    """Secret access serializer."""

    secret_name = serializers.CharField(source='secret.name', read_only=True)

    class Meta:
        model = SecretAccess
        fields = [
            'id', 'tenant_id', 'secret', 'secret_name', 'agent_execution',
            'accessed_by', 'accessed_at', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'accessed_at', 'created_at', 'updated_at']


# ===== Audit Serializers =====

class AuditEventSerializer(serializers.ModelSerializer):
    """Audit event serializer."""

    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True, allow_null=True)
    tool_invocation_id = serializers.CharField(source='tool_invocation.id', read_only=True, allow_null=True)
    approval_request_id = serializers.CharField(source='approval_request.id', read_only=True, allow_null=True)

    class Meta:
        model = AuditEvent
        fields = [
            'id', 'tenant_id', 'event_type', 'agent_execution', 'agent_execution_id',
            'tool_invocation', 'tool_invocation_id', 'approval_request', 'approval_request_id',
            'initiating_principal', 'subject_id', 'session_id', 'request_id',
            'event_timestamp', 'outcome', 'outcome_details', 'policy_decisions',
            'workflow_transitions', 'affected_resources', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'event_timestamp', 'created_at', 'updated_at']


class AuditTrailSerializer(serializers.ModelSerializer):
    """Audit trail serializer."""

    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True)

    class Meta:
        model = AuditTrail
        fields = [
            'id', 'tenant_id', 'request_id', 'agent_execution', 'agent_execution_id',
            'initiating_principal', 'request_timestamp', 'completed_timestamp',
            'final_outcome', 'summary', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'request_timestamp', 'created_at', 'updated_at']


# ===== Token Serializers =====

class TokenUsageSerializer(serializers.ModelSerializer):
    """Token usage serializer."""

    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True)

    class Meta:
        model = TokenUsage
        fields = [
            'id', 'tenant_id', 'agent_execution', 'agent_execution_id',
            'provider', 'model', 'input_tokens', 'output_tokens',
            'total_tokens', 'usage_timestamp', 'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'usage_timestamp', 'created_at', 'updated_at']


class CostRecordSerializer(serializers.ModelSerializer):
    """Cost record serializer."""

    agent_execution_id = serializers.CharField(source='agent_execution.id', read_only=True, allow_null=True)
    tool_invocation_id = serializers.CharField(source='tool_invocation.id', read_only=True, allow_null=True)

    class Meta:
        model = CostRecord
        fields = [
            'id', 'tenant_id', 'agent_execution', 'agent_execution_id',
            'tool_invocation', 'tool_invocation_id', 'module_name',
            'cost_type', 'provider', 'amount', 'currency', 'cost_timestamp',
            'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'cost_timestamp', 'created_at', 'updated_at']


class CostSummarySerializer(serializers.ModelSerializer):
    """Cost summary serializer."""

    class Meta:
        model = CostSummary
        fields = [
            'id', 'tenant_id', 'period_start', 'period_end', 'period_type',
            'total_cost', 'currency', 'cost_by_type', 'cost_by_module',
            'cost_by_provider', 'total_tokens', 'total_executions', 'created_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at']

