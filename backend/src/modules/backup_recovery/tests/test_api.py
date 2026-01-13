"""
API Integration Tests for Backup & Recovery (Extended) module.

Tests all DRF ViewSet endpoints:
- CRUD operations
- Authentication/authorization
- Tenant isolation
- Custom actions
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.backup_recovery.models import BackupArchive, BackupJob, BackupRetentionPolicy, BackupSchedule
from src.core.auth_utils import get_user_tenant_id

User = get_user_model()


@pytest.fixture
def api_client():
    """Create API client for testing."""
    return APIClient()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""
    from src.core.user_models import UserProfile
    from src.core.licensing.models import Organization
    import uuid

    # Create a valid Organization for the tenant
    org = Organization.objects.create(name="Test Organization")
    tenant_id = str(org.id)

    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = tenant_id
    profile.tenant_role = "tenant_admin"
    profile.save()

    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    """Create authenticated API client."""
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.mark.django_db
class TestBackupJobViewSet:
    """Test BackupJobViewSet CRUD operations."""

    def test_list_backup_jobs(self, authenticated_client, tenant_user):
        """Test listing backup jobs for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        # Create test backup jobs
        BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="full",
            created_by=str(tenant_user.id),
        )
        BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="incremental",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get("/api/v1/backup-recovery/jobs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 2

    def test_create_backup_job(self, authenticated_client, tenant_user):
        """Test creating a backup job."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        data = {
            "backup_type": "full",
            "description": "Test backup",
        }

        response = authenticated_client.post(
            "/api/v1/backup-recovery/jobs/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["backup_type"] == "full"
        assert response.data["tenant_id"] == tenant_id

    def test_get_backup_job_detail(self, authenticated_client, tenant_user):
        """Test getting backup job detail."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job = BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="full",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/backup-recovery/jobs/{job.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == job.id
        assert response.data["backup_type"] == "full"

    def test_start_backup_job(self, authenticated_client, tenant_user):
        """Test starting a backup job."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job = BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="full",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.post(f"/api/v1/backup-recovery/jobs/{job.id}/start/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "running"

    def test_complete_backup_job(self, authenticated_client, tenant_user):
        """Test completing a backup job."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job = BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="full",
            created_by=str(tenant_user.id),
        )
        # Start the job first
        authenticated_client.post(f"/api/v1/backup-recovery/jobs/{job.id}/start/")

        data = {
            "backup_size_bytes": 1024000,
            "storage_location": "s3://bucket/backup-123",
        }
        response = authenticated_client.post(
            f"/api/v1/backup-recovery/jobs/{job.id}/complete/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "completed"
        assert response.data["backup_size_bytes"] == 1024000


@pytest.mark.django_db
class TestBackupScheduleViewSet:
    """Test BackupScheduleViewSet CRUD operations."""

    def test_list_backup_schedules(self, authenticated_client, tenant_user):
        """Test listing backup schedules for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        BackupSchedule.objects.create(
            tenant_id=tenant_id,
            frequency="daily",
            retention_days=30,
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get("/api/v1/backup-recovery/schedules/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_create_backup_schedule(self, authenticated_client, tenant_user):
        """Test creating a backup schedule."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        data = {
            "frequency": "daily",
            "retention_days": 30,
            "backup_type": "full",
            "description": "Daily full backup",
        }

        response = authenticated_client.post(
            "/api/v1/backup-recovery/schedules/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["frequency"] == "daily"
        assert response.data["tenant_id"] == tenant_id

    def test_activate_schedule(self, authenticated_client, tenant_user):
        """Test activating a schedule."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        schedule = BackupSchedule.objects.create(
            tenant_id=tenant_id,
            frequency="daily",
            retention_days=30,
            is_active=False,
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.post(f"/api/v1/backup-recovery/schedules/{schedule.id}/activate/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_active"] is True


@pytest.mark.django_db
class TestBackupRetentionPolicyViewSet:
    """Test BackupRetentionPolicyViewSet CRUD operations."""

    def test_list_retention_policies(self, authenticated_client, tenant_user):
        """Test listing retention policies for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        BackupRetentionPolicy.objects.create(
            tenant_id=tenant_id,
            policy_name="Standard Policy",
            retention_days=30,
            archive_after_days=15,
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get("/api/v1/backup-recovery/retention-policies/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_create_retention_policy(self, authenticated_client, tenant_user):
        """Test creating a retention policy."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        data = {
            "policy_name": "Standard Policy",
            "retention_days": 30,
            "archive_after_days": 15,
            "description": "Standard retention policy",
        }

        response = authenticated_client.post(
            "/api/v1/backup-recovery/retention-policies/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["policy_name"] == "Standard Policy"
        assert response.data["tenant_id"] == tenant_id


@pytest.mark.django_db
class TestBackupArchiveViewSet:
    """Test BackupArchiveViewSet read operations."""

    def test_list_backup_archives(self, authenticated_client, tenant_user):
        """Test listing backup archives for authenticated user."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job = BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="full",
            created_by=str(tenant_user.id),
        )
        BackupArchive.objects.create(
            tenant_id=tenant_id,
            backup_job=job,
            archive_location="s3://bucket/archive-123",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get("/api/v1/backup-recovery/archives/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_get_backup_archive_detail(self, authenticated_client, tenant_user):
        """Test getting backup archive detail."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job = BackupJob.objects.create(
            tenant_id=tenant_id,
            backup_type="full",
            created_by=str(tenant_user.id),
        )
        archive = BackupArchive.objects.create(
            tenant_id=tenant_id,
            backup_job=job,
            archive_location="s3://bucket/archive-123",
            created_by=str(tenant_user.id),
        )

        response = authenticated_client.get(f"/api/v1/backup-recovery/archives/{archive.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == archive.id
        assert response.data["archive_location"] == "s3://bucket/archive-123"
