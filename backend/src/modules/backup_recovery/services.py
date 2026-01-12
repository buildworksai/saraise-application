"""
Backup & Recovery (Extended) Services.

High-level service layer for backup business logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import BackupArchive, BackupJob, BackupJobStatus, BackupRetentionPolicy, BackupSchedule

logger = logging.getLogger(__name__)


class BackupRecoveryService:
    """Service for managing backup operations."""

    def create_backup_job(
        self,
        tenant_id: str,
        backup_type: str,
        description: str = "",
        created_by: str = "",
    ) -> BackupJob:
        """Create a new backup job.

        Args:
            tenant_id: Tenant ID.
            backup_type: Type of backup (full, incremental, differential).
            description: Backup description.
            created_by: User ID who created the backup.

        Returns:
            Created BackupJob instance.

        Raises:
            ValueError: If validation fails.
        """
        with transaction.atomic():
            backup_job = BackupJob.objects.create(
                tenant_id=tenant_id,
                backup_type=backup_type,
                status=BackupJobStatus.PENDING,
                description=description,
                created_by=created_by,
            )

            logger.info(f"Created backup job {backup_job.id} for tenant {tenant_id}")
            return backup_job

    def start_backup_job(self, job_id: str, tenant_id: str) -> Optional[BackupJob]:
        """Start a backup job.

        Args:
            job_id: Backup job ID.
            tenant_id: Tenant ID.

        Returns:
            Updated BackupJob instance or None if not found.
        """
        job = self.get_backup_job(job_id, tenant_id)
        if not job:
            return None

        if job.status != BackupJobStatus.PENDING:
            raise ValueError(f"Cannot start job in status: {job.status}")

        with transaction.atomic():
            job.status = BackupJobStatus.RUNNING
            job.start_time = timezone.now()
            job.save()

            logger.info(f"Started backup job {job_id}")
            return job

    def complete_backup_job(
        self,
        job_id: str,
        tenant_id: str,
        backup_size_bytes: Optional[int] = None,
        storage_location: str = "",
    ) -> Optional[BackupJob]:
        """Complete a backup job.

        Args:
            job_id: Backup job ID.
            tenant_id: Tenant ID.
            backup_size_bytes: Size of backup in bytes.
            storage_location: Location where backup is stored.

        Returns:
            Updated BackupJob instance or None if not found.
        """
        job = self.get_backup_job(job_id, tenant_id)
        if not job:
            return None

        with transaction.atomic():
            job.status = BackupJobStatus.COMPLETED
            job.end_time = timezone.now()
            if backup_size_bytes is not None:
                job.backup_size_bytes = backup_size_bytes
            if storage_location:
                job.storage_location = storage_location
            job.save()

            logger.info(f"Completed backup job {job_id}")
            return job

    def fail_backup_job(
        self, job_id: str, tenant_id: str, error_message: str = ""
    ) -> Optional[BackupJob]:
        """Mark a backup job as failed.

        Args:
            job_id: Backup job ID.
            tenant_id: Tenant ID.
            error_message: Error message.

        Returns:
            Updated BackupJob instance or None if not found.
        """
        job = self.get_backup_job(job_id, tenant_id)
        if not job:
            return None

        with transaction.atomic():
            job.status = BackupJobStatus.FAILED
            job.end_time = timezone.now()
            if error_message:
                job.error_message = error_message
            job.save()

            logger.warning(f"Failed backup job {job_id}: {error_message}")
            return job

    def get_backup_job(self, job_id: str, tenant_id: str) -> Optional[BackupJob]:
        """Get backup job by ID.

        Args:
            job_id: Backup job ID.
            tenant_id: Tenant ID.

        Returns:
            BackupJob instance or None if not found.
        """
        return BackupJob.objects.filter(id=job_id, tenant_id=tenant_id).first()

    def list_backup_jobs(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        backup_type: Optional[str] = None,
    ) -> list[BackupJob]:
        """List all backup jobs for tenant.

        Args:
            tenant_id: Tenant ID.
            status: Optional filter by status.
            backup_type: Optional filter by backup type.

        Returns:
            List of BackupJob instances.
        """
        queryset = BackupJob.objects.filter(tenant_id=tenant_id)
        if status:
            queryset = queryset.filter(status=status)
        if backup_type:
            queryset = queryset.filter(backup_type=backup_type)
        return list(queryset.order_by("-created_at"))

    def create_backup_schedule(
        self,
        tenant_id: str,
        frequency: str,
        retention_days: int,
        backup_type: str = "full",
        schedule_time: Optional[str] = None,
        description: str = "",
        created_by: str = "",
    ) -> BackupSchedule:
        """Create a new backup schedule.

        Args:
            tenant_id: Tenant ID.
            frequency: How often to run (hourly, daily, weekly, monthly).
            retention_days: Number of days to retain backups.
            backup_type: Type of backup to create.
            schedule_time: Time of day to run (for daily/weekly/monthly).
            description: Schedule description.
            created_by: User ID who created the schedule.

        Returns:
            Created BackupSchedule instance.
        """
        with transaction.atomic():
            schedule = BackupSchedule.objects.create(
                tenant_id=tenant_id,
                frequency=frequency,
                retention_days=retention_days,
                backup_type=backup_type,
                schedule_time=schedule_time,
                description=description,
                created_by=created_by,
            )

            logger.info(f"Created backup schedule {schedule.id} for tenant {tenant_id}")
            return schedule

    def get_backup_schedule(
        self, schedule_id: str, tenant_id: str
    ) -> Optional[BackupSchedule]:
        """Get backup schedule by ID.

        Args:
            schedule_id: Schedule ID.
            tenant_id: Tenant ID.

        Returns:
            BackupSchedule instance or None if not found.
        """
        return BackupSchedule.objects.filter(id=schedule_id, tenant_id=tenant_id).first()

    def list_backup_schedules(
        self, tenant_id: str, is_active: Optional[bool] = None
    ) -> list[BackupSchedule]:
        """List all backup schedules for tenant.

        Args:
            tenant_id: Tenant ID.
            is_active: Optional filter by active status.

        Returns:
            List of BackupSchedule instances.
        """
        queryset = BackupSchedule.objects.filter(tenant_id=tenant_id)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)
        return list(queryset.order_by("-created_at"))

    def create_retention_policy(
        self,
        tenant_id: str,
        policy_name: str,
        retention_days: int,
        archive_after_days: int,
        description: str = "",
        created_by: str = "",
    ) -> BackupRetentionPolicy:
        """Create a new retention policy.

        Args:
            tenant_id: Tenant ID.
            policy_name: Policy name.
            retention_days: Days to retain backups.
            archive_after_days: Days after which to archive.
            description: Policy description.
            created_by: User ID who created the policy.

        Returns:
            Created BackupRetentionPolicy instance.
        """
        if archive_after_days >= retention_days:
            raise ValueError("Archive after days must be less than retention days")

        with transaction.atomic():
            policy = BackupRetentionPolicy.objects.create(
                tenant_id=tenant_id,
                policy_name=policy_name,
                retention_days=retention_days,
                archive_after_days=archive_after_days,
                description=description,
                created_by=created_by,
            )

            logger.info(f"Created retention policy {policy.id} for tenant {tenant_id}")
            return policy

    def archive_backup_job(
        self,
        job_id: str,
        tenant_id: str,
        archive_location: str,
        archive_size_bytes: Optional[int] = None,
        created_by: str = "",
    ) -> Optional[BackupArchive]:
        """Archive a backup job.

        Args:
            job_id: Backup job ID to archive.
            tenant_id: Tenant ID.
            archive_location: Location where archived backup is stored.
            archive_size_bytes: Size of archived backup.
            created_by: User ID who created the archive.

        Returns:
            Created BackupArchive instance or None if job not found.
        """
        job = self.get_backup_job(job_id, tenant_id)
        if not job:
            return None

        with transaction.atomic():
            archive = BackupArchive.objects.create(
                tenant_id=tenant_id,
                backup_job=job,
                archive_location=archive_location,
                archive_size_bytes=archive_size_bytes,
                created_by=created_by,
            )

            logger.info(f"Archived backup job {job_id} to {archive_location}")
            return archive

    def list_backup_archives(
        self, tenant_id: str, job_id: Optional[str] = None
    ) -> list[BackupArchive]:
        """List all backup archives for tenant.

        Args:
            tenant_id: Tenant ID.
            job_id: Optional filter by backup job ID.

        Returns:
            List of BackupArchive instances.
        """
        queryset = BackupArchive.objects.filter(tenant_id=tenant_id)
        if job_id:
            queryset = queryset.filter(backup_job_id=job_id)
        return list(queryset.order_by("-archived_at"))
