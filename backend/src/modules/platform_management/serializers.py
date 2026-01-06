"""
Platform Management Serializers
DRF serializers for API validation and transformation
"""

from rest_framework import serializers
from .models import (
    PlatformSetting,
    FeatureFlag,
    SystemHealth,
    PlatformAuditEvent,
    PlatformMetrics,
)


class PlatformSettingSerializer(serializers.ModelSerializer):
    """Serializer for platform settings."""

    class Meta:
        model = PlatformSetting
        fields = [
            'id', 'tenant_id', 'key', 'value', 'category',
            'description', 'is_secret', 'data_type',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate_key(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Key must be at least 2 characters")
        return value.lower().replace(' ', '_')

    def to_representation(self, instance):
        """Mask secret values in output."""
        data = super().to_representation(instance)
        if instance.is_secret:
            data['value'] = '********'
        return data


class PlatformSettingCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating platform settings."""

    class Meta:
        model = PlatformSetting
        fields = ['key', 'value', 'category', 'description', 'is_secret', 'data_type']

    def validate_key(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Key must be at least 2 characters")
        return value.lower().replace(' ', '_')


class FeatureFlagSerializer(serializers.ModelSerializer):
    """Serializer for feature flags."""

    class Meta:
        model = FeatureFlag
        fields = [
            'id', 'tenant_id', 'name', 'enabled',
            'description', 'rollout_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'tenant_id', 'created_at', 'updated_at']

    def validate_name(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters")
        return value.lower().replace(' ', '_')

    def validate_rollout_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Rollout percentage must be 0-100")
        return value


class FeatureFlagCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating feature flags."""

    class Meta:
        model = FeatureFlag
        fields = ['name', 'enabled', 'description', 'rollout_percentage']

    def validate_name(self, value):
        if not value or len(value) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters")
        return value.lower().replace(' ', '_')

    def validate_rollout_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Rollout percentage must be 0-100")
        return value


class SystemHealthSerializer(serializers.ModelSerializer):
    """Serializer for system health status."""

    class Meta:
        model = SystemHealth
        fields = [
            'id', 'service_name', 'status', 'last_check',
            'response_time_ms', 'details', 'error_message'
        ]
        read_only_fields = ['id', 'last_check']


class PlatformAuditEventSerializer(serializers.ModelSerializer):
    """Serializer for audit events (read-only)."""

    class Meta:
        model = PlatformAuditEvent
        fields = [
            'id', 'tenant_id', 'action', 'actor_type', 'actor_id',
            'resource_type', 'resource_id', 'timestamp',
            'details', 'ip_address'
        ]
        read_only_fields = fields  # All fields are read-only


class PlatformMetricsSerializer(serializers.ModelSerializer):
    """Serializer for platform metrics records."""

    class Meta:
        model = PlatformMetrics
        fields = [
            'id', 'metric_type', 'time_range', 'metrics_data',
            'recorded_at', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]
        read_only_fields = [
            'id', 'recorded_at', 'created_at', 'updated_at', 'created_by', 'updated_by'
        ]


class PlatformMetricsRequestSerializer(serializers.Serializer):
    """Serializer for platform metrics requests."""

    metric_type = serializers.ChoiceField(choices=PlatformMetrics.MetricType.choices)
    time_range = serializers.CharField(max_length=20, required=False, default="30d")
