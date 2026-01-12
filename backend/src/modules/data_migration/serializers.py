"""
DRF Serializers for DataMigration module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import (
    MigrationJob,
    MigrationLog,
    MigrationMapping,
    MigrationRollback,
    MigrationValidation,
)


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
