"""
Service Unit Tests for Backup & Recovery (Extended) module.

Tests business logic in services layer.
"""
import pytest
from django.utils import timezone

from src.modules.backup_recovery.models import BackupArchive, BackupJob, BackupJobStatus, BackupRetentionPolicy, BackupSchedule
from src.modules.backup_recovery.services import BackupRecoveryService


@pytest.mark.django_db
class TestBackupRecoveryService:
    """Test BackupRecoveryService business logic."""

    def test_create_backup_job(self, db):
        """Test creating a backup job via service."""
        service = BackupRecoveryService()
        job = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            description="Test backup",
            created_by="user-123",
        )
        assert job.id is not None
        assert job.backup_type == "full"
        assert job.status == BackupJobStatus.PENDING
        assert job.tenant_id == "tenant-123"

    def test_start_backup_job(self, db):
        """Test starting a backup job."""
        service = BackupRecoveryService()
        job = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        
        started_job = service.start_backup_job(job.id, "tenant-123")
        assert started_job is not None
        assert started_job.status == BackupJobStatus.RUNNING
        assert started_job.start_time is not None

    def test_complete_backup_job(self, db):
        """Test completing a backup job."""
        service = BackupRecoveryService()
        job = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        service.start_backup_job(job.id, "tenant-123")
        
        completed_job = service.complete_backup_job(
            job.id,
            "tenant-123",
            backup_size_bytes=1024000,
            storage_location="s3://bucket/backup-123",
        )
        assert completed_job is not None
        assert completed_job.status == BackupJobStatus.COMPLETED
        assert completed_job.end_time is not None
        assert completed_job.backup_size_bytes == 1024000
        assert completed_job.storage_location == "s3://bucket/backup-123"

    def test_fail_backup_job(self, db):
        """Test failing a backup job."""
        service = BackupRecoveryService()
        job = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        service.start_backup_job(job.id, "tenant-123")
        
        failed_job = service.fail_backup_job(
            job.id,
            "tenant-123",
            error_message="Backup failed due to network error",
        )
        assert failed_job is not None
        assert failed_job.status == BackupJobStatus.FAILED
        assert failed_job.end_time is not None
        assert "network error" in failed_job.error_message.lower()

    def test_get_backup_job(self, db):
        """Test getting a backup job by ID."""
        service = BackupRecoveryService()
        created = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        
        retrieved = service.get_backup_job(created.id, "tenant-123")
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_backup_job_wrong_tenant(self, db):
        """Test that getting backup job from wrong tenant returns None."""
        service = BackupRecoveryService()
        created = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        
        retrieved = service.get_backup_job(created.id, "tenant-456")
        assert retrieved is None

    def test_list_backup_jobs(self, db):
        """Test listing backup jobs for tenant."""
        service = BackupRecoveryService()
        service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="incremental",
            created_by="user-123",
        )
        service.create_backup_job(
            tenant_id="tenant-456",
            backup_type="full",
            created_by="user-456",
        )
        
        jobs = service.list_backup_jobs("tenant-123")
        assert len(jobs) == 2
        assert all(j.tenant_id == "tenant-123" for j in jobs)

    def test_create_backup_schedule(self, db):
        """Test creating a backup schedule."""
        service = BackupRecoveryService()
        schedule = service.create_backup_schedule(
            tenant_id="tenant-123",
            frequency="daily",
            retention_days=30,
            backup_type="full",
            description="Daily full backup",
            created_by="user-123",
        )
        assert schedule.id is not None
        assert schedule.frequency == "daily"
        assert schedule.retention_days == 30
        assert schedule.backup_type == "full"

    def test_create_retention_policy(self, db):
        """Test creating a retention policy."""
        service = BackupRecoveryService()
        policy = service.create_retention_policy(
            tenant_id="tenant-123",
            policy_name="Standard Policy",
            retention_days=30,
            archive_after_days=15,
            description="Standard retention policy",
            created_by="user-123",
        )
        assert policy.id is not None
        assert policy.policy_name == "Standard Policy"
        assert policy.retention_days == 30
        assert policy.archive_after_days == 15

    def test_create_retention_policy_invalid_archive_days(self, db):
        """Test that creating retention policy with invalid archive_after_days raises error."""
        service = BackupRecoveryService()
        with pytest.raises(ValueError, match="Archive after days must be less than retention days"):
            service.create_retention_policy(
                tenant_id="tenant-123",
                policy_name="Invalid Policy",
                retention_days=30,
                archive_after_days=30,  # Same as retention_days, should fail
                created_by="user-123",
            )

    def test_archive_backup_job(self, db):
        """Test archiving a backup job."""
        service = BackupRecoveryService()
        job = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        service.complete_backup_job(
            job.id,
            "tenant-123",
            backup_size_bytes=1024000,
            storage_location="s3://bucket/backup-123",
        )
        
        archive = service.archive_backup_job(
            job.id,
            "tenant-123",
            archive_location="s3://bucket/archive-123",
            archive_size_bytes=1024000,
            created_by="user-123",
        )
        assert archive is not None
        assert archive.backup_job == job
        assert archive.archive_location == "s3://bucket/archive-123"

    def test_list_backup_archives(self, db):
        """Test listing backup archives for tenant."""
        service = BackupRecoveryService()
        job1 = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="full",
            created_by="user-123",
        )
        job2 = service.create_backup_job(
            tenant_id="tenant-123",
            backup_type="incremental",
            created_by="user-123",
        )
        service.complete_backup_job(job1.id, "tenant-123", storage_location="s3://bucket/job1")
        service.complete_backup_job(job2.id, "tenant-123", storage_location="s3://bucket/job2")
        
        service.archive_backup_job(
            job1.id,
            "tenant-123",
            archive_location="s3://bucket/archive-1",
            created_by="user-123",
        )
        service.archive_backup_job(
            job2.id,
            "tenant-123",
            archive_location="s3://bucket/archive-2",
            created_by="user-123",
        )
        
        archives = service.list_backup_archives("tenant-123")
        assert len(archives) == 2
        assert all(a.tenant_id == "tenant-123" for a in archives)
