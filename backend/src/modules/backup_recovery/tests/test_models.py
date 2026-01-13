"""
Model Unit Tests for Backup & Recovery (Extended) module.

Tests model creation, validation, and relationships.
"""
import pytest
from django.utils import timezone

from src.modules.backup_recovery.models import BackupArchive, BackupJob, BackupJobStatus, BackupRetentionPolicy, BackupSchedule


@pytest.mark.django_db
class TestBackupJobModel:
    """Test BackupJob model."""

    def test_create_backup_job(self, db):
        """Test creating a backup job."""
        job = BackupJob.objects.create(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        assert job.id is not None
        assert job.backup_type == "full"
        assert job.status == BackupJobStatus.PENDING
        assert job.tenant_id == "tenant-123"

    def test_backup_job_str_representation(self, db):
        """Test backup job string representation."""
        job = BackupJob.objects.create(
            tenant_id="tenant-123",
            backup_type="incremental",
            status=BackupJobStatus.RUNNING,
            created_by="user-123",
        )
        assert "incremental" in str(job)
        assert "running" in str(job).lower()

    def test_backup_job_has_tenant_id(self, db):
        """Test that backup job requires tenant_id."""
        job = BackupJob(
            backup_type="full",
            created_by="user-123",
        )
        # Should raise error if tenant_id is missing
        with pytest.raises(Exception):
            job.save()


@pytest.mark.django_db
class TestBackupScheduleModel:
    """Test BackupSchedule model."""

    def test_create_backup_schedule(self, db):
        """Test creating a backup schedule."""
        schedule = BackupSchedule.objects.create(
            tenant_id="tenant-123",
            frequency="daily",
            retention_days=30,
            created_by="user-123",
        )
        assert schedule.id is not None
        assert schedule.frequency == "daily"
        assert schedule.retention_days == 30
        assert schedule.is_active is True
        assert schedule.tenant_id == "tenant-123"

    def test_backup_schedule_str_representation(self, db):
        """Test backup schedule string representation."""
        schedule = BackupSchedule.objects.create(
            tenant_id="tenant-123",
            frequency="weekly",
            retention_days=60,
            created_by="user-123",
        )
        assert "weekly" in str(schedule).lower()


@pytest.mark.django_db
class TestBackupRetentionPolicyModel:
    """Test BackupRetentionPolicy model."""

    def test_create_retention_policy(self, db):
        """Test creating a retention policy."""
        policy = BackupRetentionPolicy.objects.create(
            tenant_id="tenant-123",
            policy_name="Standard Policy",
            retention_days=30,
            archive_after_days=15,
            created_by="user-123",
        )
        assert policy.id is not None
        assert policy.policy_name == "Standard Policy"
        assert policy.retention_days == 30
        assert policy.archive_after_days == 15
        assert policy.is_active is True
        assert policy.tenant_id == "tenant-123"

    def test_retention_policy_str_representation(self, db):
        """Test retention policy string representation."""
        policy = BackupRetentionPolicy.objects.create(
            tenant_id="tenant-123",
            policy_name="Test Policy",
            retention_days=30,
            archive_after_days=15,
            created_by="user-123",
        )
        assert "Test Policy" in str(policy)


@pytest.mark.django_db
class TestBackupArchiveModel:
    """Test BackupArchive model."""

    def test_create_backup_archive(self, db):
        """Test creating a backup archive."""
        job = BackupJob.objects.create(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        archive = BackupArchive.objects.create(
            tenant_id="tenant-123",
            backup_job=job,
            archive_location="s3://bucket/archive-123",
            archive_size_bytes=1024000,
            created_by="user-123",
        )
        assert archive.id is not None
        assert archive.backup_job == job
        assert archive.archive_location == "s3://bucket/archive-123"
        assert archive.archive_size_bytes == 1024000
        assert archive.tenant_id == "tenant-123"

    def test_backup_archive_str_representation(self, db):
        """Test backup archive string representation."""
        job = BackupJob.objects.create(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        archive = BackupArchive.objects.create(
            tenant_id="tenant-123",
            backup_job=job,
            archive_location="s3://bucket/archive-123",
            created_by="user-123",
        )
        assert job.id in str(archive)
