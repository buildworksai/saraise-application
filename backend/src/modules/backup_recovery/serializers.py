"""
DRF Serializers for Backup & Recovery (Extended) module.
Provides request/response validation for all models.
"""

from rest_framework import serializers

from .models import BackupArchive, BackupJob, BackupRetentionPolicy, BackupSchedule


class BackupJobSerializer(serializers.ModelSerializer):
    """Serializer for BackupJob model."""

    class Meta:
        model = BackupJob
        fields = [
            "id",
            "tenant_id",
            "backup_type",
            "status",
            "start_time",
            "end_time",
            "backup_size_bytes",
            "storage_location",
            "description",
            "error_message",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "created_by",
            "created_at",
            "updated_at",
            "start_time",
            "end_time",
        ]

    def validate_backup_type(self, value):
        """Validate backup type."""
        if value not in ["full", "incremental", "differential"]:
            raise serializers.ValidationError("Invalid backup type")
        return value


class BackupJobCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating BackupJob."""

    class Meta:
        model = BackupJob
        fields = [
            "backup_type",
            "description",
        ]

    def validate_backup_type(self, value):
        """Validate backup type."""
        if value not in ["full", "incremental", "differential"]:
            raise serializers.ValidationError("Invalid backup type")
        return value


class BackupScheduleSerializer(serializers.ModelSerializer):
    """Serializer for BackupSchedule model."""

    class Meta:
        model = BackupSchedule
        fields = [
            "id",
            "tenant_id",
            "frequency",
            "schedule_time",
            "retention_days",
            "is_active",
            "backup_type",
            "description",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_by", "created_at", "updated_at"]

    def validate_frequency(self, value):
        """Validate frequency."""
        if value not in ["hourly", "daily", "weekly", "monthly"]:
            raise serializers.ValidationError("Invalid frequency")
        return value

    def validate_retention_days(self, value):
        """Validate retention days."""
        if value < 1:
            raise serializers.ValidationError("Retention days must be at least 1")
        if value > 3650:  # 10 years max
            raise serializers.ValidationError("Retention days cannot exceed 3650")
        return value


class BackupScheduleCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating BackupSchedule."""

    class Meta:
        model = BackupSchedule
        fields = [
            "frequency",
            "schedule_time",
            "retention_days",
            "backup_type",
            "description",
        ]

    def validate_frequency(self, value):
        """Validate frequency."""
        if value not in ["hourly", "daily", "weekly", "monthly"]:
            raise serializers.ValidationError("Invalid frequency")
        return value


class BackupRetentionPolicySerializer(serializers.ModelSerializer):
    """Serializer for BackupRetentionPolicy model."""

    class Meta:
        model = BackupRetentionPolicy
        fields = [
            "id",
            "tenant_id",
            "policy_name",
            "retention_days",
            "archive_after_days",
            "is_active",
            "description",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_by", "created_at", "updated_at"]

    def validate_retention_days(self, value):
        """Validate retention days."""
        if value < 1:
            raise serializers.ValidationError("Retention days must be at least 1")
        return value

    def validate_archive_after_days(self, value):
        """Validate archive after days."""
        if value < 0:
            raise serializers.ValidationError("Archive after days cannot be negative")
        return value

    def validate(self, data):
        """Validate that archive_after_days is less than retention_days."""
        retention_days = data.get("retention_days")
        archive_after_days = data.get("archive_after_days")
        if retention_days and archive_after_days and archive_after_days >= retention_days:
            raise serializers.ValidationError(
                "Archive after days must be less than retention days"
            )
        return data


class BackupRetentionPolicyCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating BackupRetentionPolicy."""

    class Meta:
        model = BackupRetentionPolicy
        fields = [
            "policy_name",
            "retention_days",
            "archive_after_days",
            "description",
        ]


class BackupArchiveSerializer(serializers.ModelSerializer):
    """Serializer for BackupArchive model."""

    backup_job = BackupJobSerializer(read_only=True)
    backup_job_id = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = BackupArchive
        fields = [
            "id",
            "tenant_id",
            "backup_job",
            "backup_job_id",
            "archive_location",
            "archived_at",
            "archive_size_bytes",
            "description",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "created_by",
            "created_at",
            "updated_at",
            "archived_at",
        ]
