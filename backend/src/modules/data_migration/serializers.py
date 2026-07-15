"""
DRF Serializers for DataMigration module.
Provides request/response validation for all models.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from src.core.auth_utils import get_user_tenant_id

from .models import (
    ExternalConnection,
    MigrationJob,
    MigrationLog,
    MigrationMapping,
    MigrationRollback,
    MigrationValidation,
)
from .services import _validate_database_source_config


def validate_database_source_config(config, tenant_id=None):
    """Enforce the named-connection contract and optional tenant ownership."""
    try:
        _validate_database_source_config(config)
    except ValueError as exc:
        raise serializers.ValidationError(str(exc)) from exc
    if tenant_id:
        try:
            exists = ExternalConnection.objects.filter(
                id=config["connection_id"],
                tenant_id=tenant_id,
                is_active=True,
            ).exists()
        except (DjangoValidationError, ValueError, TypeError):
            exists = False
        if not exists:
            raise serializers.ValidationError("Active external connection not found for tenant")
    return config


class ExternalConnectionReferenceSerializer(serializers.ModelSerializer):
    """Credential-free connection reference visible to tenant users."""

    class Meta:
        model = ExternalConnection
        fields = ["id", "name", "db_scheme", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class ExternalConnectionManagementSerializer(serializers.ModelSerializer):
    """Operator-only registration input; password is encrypted by the service."""

    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = ExternalConnection
        fields = [
            "id",
            "tenant_id",
            "name",
            "db_scheme",
            "host",
            "port",
            "database",
            "username",
            "password",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        """Require a password on registration and enforce canonical host/port values."""
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Password is required"})
        if self.instance is not None and "tenant_id" in attrs and attrs["tenant_id"] != self.instance.tenant_id:
            raise serializers.ValidationError({"tenant_id": "Tenant ownership cannot be changed"})
        password = attrs.get("password")
        if password is not None and not password:
            raise serializers.ValidationError({"password": "Password cannot be empty"})
        return attrs

    def validate_host(self, value):
        """Reject connection-list and Unix-socket syntax at registration time."""
        if value != value.strip() or value.startswith("/") or "," in value or "\x00" in value:
            raise serializers.ValidationError("Unix-socket and multi-host values are forbidden")
        return value

    def validate_port(self, value):
        """Restrict ports to the valid TCP range."""
        if value < 1 or value > 65535:
            raise serializers.ValidationError("Port must be between 1 and 65535")
        return value


class MigrationJobSerializer(serializers.ModelSerializer):
    """Serializer for MigrationJob model."""

    mappings_count = serializers.IntegerField(source="mappings.count", read_only=True)
    logs_count = serializers.IntegerField(source="logs.count", read_only=True)
    validations_count = serializers.IntegerField(source="validations.count", read_only=True)
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = MigrationJob
        fields = [
            "id",
            "tenant_id",
            "name",
            "source_type",
            "source_config",
            "status",
            "started_at",
            "completed_at",
            "records_processed",
            "records_failed",
            "records_total",
            "error_message",
            "mappings_count",
            "logs_count",
            "validations_count",
            "progress_percentage",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "status",
            "started_at",
            "completed_at",
            "records_processed",
            "records_failed",
            "records_total",
            "error_message",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_progress_percentage(self, obj):
        """Calculate progress percentage."""
        if obj.records_total == 0:
            return 0
        return int((obj.records_processed / obj.records_total) * 100)

    def validate_name(self, value):
        """Validate name field."""
        if not value or not value.strip():
            raise serializers.ValidationError("Name cannot be empty")
        return value.strip()

    def validate(self, attrs):
        """Validate database sources before caller-controlled config is stored."""
        source_type = attrs.get("source_type", getattr(self.instance, "source_type", None))
        source_config = attrs.get("source_config", getattr(self.instance, "source_config", None))
        if source_type == "database":
            request = self.context.get("request")
            tenant_id = get_user_tenant_id(request.user) if request else None
            attrs["source_config"] = validate_database_source_config(source_config, tenant_id)
        return attrs


class MigrationMappingSerializer(serializers.ModelSerializer):
    """Serializer for MigrationMapping model."""

    job_name = serializers.CharField(source="job.name", read_only=True)

    class Meta:
        model = MigrationMapping
        fields = [
            "id",
            "tenant_id",
            "job",
            "job_name",
            "source_field",
            "target_field",
            "transform",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]

    def validate_job(self, value):
        """Validate job belongs to same tenant."""
        if value and hasattr(self, "initial_data"):
            tenant_id = self.initial_data.get("tenant_id")
            if tenant_id and value.tenant_id != tenant_id:
                raise serializers.ValidationError("Job must belong to the same tenant")
        return value


class MigrationLogSerializer(serializers.ModelSerializer):
    """Serializer for MigrationLog model."""

    job_name = serializers.CharField(source="job.name", read_only=True)

    class Meta:
        model = MigrationLog
        fields = [
            "id",
            "tenant_id",
            "job",
            "job_name",
            "level",
            "message",
            "timestamp",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "timestamp", "created_at", "updated_at"]


class MigrationValidationSerializer(serializers.ModelSerializer):
    """Serializer for MigrationValidation model."""

    job_name = serializers.CharField(source="job.name", read_only=True)

    class Meta:
        model = MigrationValidation
        fields = [
            "id",
            "tenant_id",
            "job",
            "job_name",
            "field",
            "rule",
            "status",
            "message",
            "record_index",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class MigrationRollbackSerializer(serializers.ModelSerializer):
    """Serializer for MigrationRollback model."""

    job_name = serializers.CharField(source="job.name", read_only=True)

    class Meta:
        model = MigrationRollback
        fields = [
            "id",
            "tenant_id",
            "job",
            "job_name",
            "checkpoint_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
