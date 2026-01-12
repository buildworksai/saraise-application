"""
Tenant Isolation Tests for Backup & Recovery (Extended) module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from ..models import BackupArchive, BackupJob, BackupRetentionPolicy, BackupSchedule
from src.core.auth_utils import get_user_tenant_id

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_a_user(db):
    """Create user for tenant A."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_a",
        email="usera@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_b_user(db):
    """Create user for tenant B."""
    from unittest.mock import patch
    from src.core.user_models import UserProfile

    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(
        username="user_b",
        email="userb@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": tenant_id, "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = tenant_id
            profile.tenant_role = "tenant_admin"
            profile.save()
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestBackupJobTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for BackupJob model.
    These tests verify that tenants cannot access each other's backup jobs.
    """

    def test_user_cannot_list_other_tenant_backup_jobs(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's backup jobs in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create backup job for tenant A
        job_a = BackupJob.objects.create(
            tenant_id=tenant_a_id,
            backup_type="full",
            created_by=str(tenant_a_user.id),
        )

        # Create backup job for tenant B
        job_b = BackupJob.objects.create(
            tenant_id=tenant_b_id,
            backup_type="incremental",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/backup-recovery/jobs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        job_ids = [j["id"] for j in data]

        # User A should see tenant A's job, but NOT tenant B's job
        assert job_a.id in job_ids
        assert job_b.id not in job_ids

    def test_user_cannot_get_other_tenant_backup_job_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's backup job by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create backup job for tenant B
        job_b = BackupJob.objects.create(
            tenant_id=tenant_b_id,
            backup_type="full",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's backup job
        response = api_client.get(f"/api/v1/backup-recovery/jobs/{job_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_user_cannot_update_other_tenant_backup_job(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot UPDATE other tenant's backup job (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create backup job for tenant B
        job_b = BackupJob.objects.create(
            tenant_id=tenant_b_id,
            backup_type="full",
            description="Original description",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to update tenant B's backup job
        data = {"description": "Hacked description"}
        response = api_client.patch(
            f"/api/v1/backup-recovery/jobs/{job_b.id}/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify backup job was not modified
        job_b.refresh_from_db()
        assert job_b.description == "Original description"

    def test_user_cannot_delete_other_tenant_backup_job(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot DELETE other tenant's backup job (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create backup job for tenant B
        job_b = BackupJob.objects.create(
            tenant_id=tenant_b_id,
            backup_type="full",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to delete tenant B's backup job
        response = api_client.delete(f"/api/v1/backup-recovery/jobs/{job_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        # Verify backup job still exists
        assert BackupJob.objects.filter(id=job_b.id).exists()


@pytest.mark.django_db
class TestBackupScheduleTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for BackupSchedule model.
    These tests verify that tenants cannot access each other's schedules.
    """

    def test_user_cannot_list_other_tenant_schedules(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's schedules in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create schedule for tenant A
        schedule_a = BackupSchedule.objects.create(
            tenant_id=tenant_a_id,
            frequency="daily",
            retention_days=30,
            created_by=str(tenant_a_user.id),
        )

        # Create schedule for tenant B
        schedule_b = BackupSchedule.objects.create(
            tenant_id=tenant_b_id,
            frequency="weekly",
            retention_days=60,
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/backup-recovery/schedules/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        schedule_ids = [s["id"] for s in data]

        # User A should see tenant A's schedule, but NOT tenant B's schedule
        assert schedule_a.id in schedule_ids
        assert schedule_b.id not in schedule_ids

    def test_user_cannot_get_other_tenant_schedule_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's schedule by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create schedule for tenant B
        schedule_b = BackupSchedule.objects.create(
            tenant_id=tenant_b_id,
            frequency="daily",
            retention_days=30,
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's schedule
        response = api_client.get(f"/api/v1/backup-recovery/schedules/{schedule_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestBackupRetentionPolicyTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for BackupRetentionPolicy model.
    These tests verify that tenants cannot access each other's policies.
    """

    def test_user_cannot_list_other_tenant_policies(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's policies in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create policy for tenant A
        policy_a = BackupRetentionPolicy.objects.create(
            tenant_id=tenant_a_id,
            policy_name="Policy A",
            retention_days=30,
            archive_after_days=15,
            created_by=str(tenant_a_user.id),
        )

        # Create policy for tenant B
        policy_b = BackupRetentionPolicy.objects.create(
            tenant_id=tenant_b_id,
            policy_name="Policy B",
            retention_days=60,
            archive_after_days=30,
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/backup-recovery/retention-policies/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        policy_ids = [p["id"] for p in data]

        # User A should see tenant A's policy, but NOT tenant B's policy
        assert policy_a.id in policy_ids
        assert policy_b.id not in policy_ids


@pytest.mark.django_db
class TestBackupArchiveTenantIsolation:
    """
    CRITICAL: Tenant isolation tests for BackupArchive model.
    These tests verify that tenants cannot access each other's archives.
    """

    def test_user_cannot_list_other_tenant_archives(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's archives in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create backup job and archive for tenant A
        job_a = BackupJob.objects.create(
            tenant_id=tenant_a_id,
            backup_type="full",
            created_by=str(tenant_a_user.id),
        )
        archive_a = BackupArchive.objects.create(
            tenant_id=tenant_a_id,
            backup_job=job_a,
            archive_location="s3://bucket/archive-a",
            created_by=str(tenant_a_user.id),
        )

        # Create backup job and archive for tenant B
        job_b = BackupJob.objects.create(
            tenant_id=tenant_b_id,
            backup_type="full",
            created_by=str(tenant_b_user.id),
        )
        archive_b = BackupArchive.objects.create(
            tenant_id=tenant_b_id,
            backup_job=job_b,
            archive_location="s3://bucket/archive-b",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/backup-recovery/archives/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        archive_ids = [a["id"] for a in data]

        # User A should see tenant A's archive, but NOT tenant B's archive
        assert archive_a.id in archive_ids
        assert archive_b.id not in archive_ids

    def test_user_cannot_get_other_tenant_archive_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's archive by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create backup job and archive for tenant B
        job_b = BackupJob.objects.create(
            tenant_id=tenant_b_id,
            backup_type="full",
            created_by=str(tenant_b_user.id),
        )
        archive_b = BackupArchive.objects.create(
            tenant_id=tenant_b_id,
            backup_job=job_b,
            archive_location="s3://bucket/archive-b",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's archive
        response = api_client.get(f"/api/v1/backup-recovery/archives/{archive_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
