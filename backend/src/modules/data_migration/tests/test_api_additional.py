"""
Additional API Tests for DataMigration module.

Tests for MigrationMapping, MigrationLog, and MigrationValidation ViewSets.
"""
import pytest
import json
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.modules.data_migration.models import MigrationJob, MigrationMapping, MigrationLog, MigrationValidation
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


@pytest.fixture
def migration_job(tenant_user):
    """Create a test migration job."""
    tenant_id = get_user_tenant_id(tenant_user)
    return MigrationJob.objects.create(
        tenant_id=tenant_id,
        name="Test Job",
        source_type="json",
        source_config={"data": json.dumps([{"name": "Test"}])},
        created_by=str(tenant_user.id),
    )


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"


@pytest.mark.django_db
class TestMigrationMappingViewSet:
    """Test MigrationMappingViewSet CRUD operations."""

    def test_list_mappings(self, authenticated_client, tenant_user, migration_job):
        """Test listing migration mappings."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        MigrationMapping.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            source_field="old_name",
            target_field="new_name",
            transform={},
        )

        response = authenticated_client.get("/api/v1/data-migration/mappings/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_create_mapping(self, authenticated_client, tenant_user, migration_job):
        """Test creating a migration mapping."""
        data = {
            "job": migration_job.id,
            "source_field": "old_field",
            "target_field": "new_field",
            "transform": {"type": "string"},
        }

        response = authenticated_client.post(
            "/api/v1/data-migration/mappings/",
            data,
            format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["source_field"] == "old_field"

    def test_filter_mappings_by_job(self, authenticated_client, tenant_user, migration_job):
        """Test filtering mappings by job."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job2 = MigrationJob.objects.create(
            tenant_id=tenant_id,
            name="Job 2",
            source_type="csv",
            source_config={},
            created_by=str(tenant_user.id),
        )

        MigrationMapping.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            source_field="field1",
            target_field="target1",
            transform={},
        )
        MigrationMapping.objects.create(
            tenant_id=tenant_id,
            job=job2,
            source_field="field2",
            target_field="target2",
            transform={},
        )

        response = authenticated_client.get(f"/api/v1/data-migration/mappings/?job_id={migration_job.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1
        assert data[0]["job"] == migration_job.id


@pytest.mark.django_db
class TestMigrationLogViewSet:
    """Test MigrationLogViewSet read operations."""

    def test_list_logs(self, authenticated_client, tenant_user, migration_job):
        """Test listing migration logs."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        MigrationLog.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            level="info",
            message="Test log message",
        )

        response = authenticated_client.get("/api/v1/data-migration/logs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_filter_logs_by_job(self, authenticated_client, tenant_user, migration_job):
        """Test filtering logs by job."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job2 = MigrationJob.objects.create(
            tenant_id=tenant_id,
            name="Job 2",
            source_type="csv",
            source_config={},
            created_by=str(tenant_user.id),
        )

        MigrationLog.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            level="info",
            message="Log 1",
        )
        MigrationLog.objects.create(
            tenant_id=tenant_id,
            job=job2,
            level="error",
            message="Log 2",
        )

        response = authenticated_client.get(f"/api/v1/data-migration/logs/?job_id={migration_job.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_filter_logs_by_level(self, authenticated_client, tenant_user, migration_job):
        """Test filtering logs by level."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        MigrationLog.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            level="info",
            message="Info log",
        )
        MigrationLog.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            level="error",
            message="Error log",
        )

        response = authenticated_client.get("/api/v1/data-migration/logs/?level=error")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1
        assert data[0]["level"] == "error"


@pytest.mark.django_db
class TestMigrationValidationViewSet:
    """Test MigrationValidationViewSet read operations."""

    def test_list_validations(self, authenticated_client, tenant_user, migration_job):
        """Test listing migration validations."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        MigrationValidation.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            field="name",
            rule="required",
            status="failed",
            message="Field is required",
            record_index=0,
        )

        response = authenticated_client.get("/api/v1/data-migration/validations/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_filter_validations_by_job(self, authenticated_client, tenant_user, migration_job):
        """Test filtering validations by job."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        job2 = MigrationJob.objects.create(
            tenant_id=tenant_id,
            name="Job 2",
            source_type="csv",
            source_config={},
            created_by=str(tenant_user.id),
        )

        MigrationValidation.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            field="field1",
            rule="required",
            status="failed",
            message="Error 1",
            record_index=0,
        )
        MigrationValidation.objects.create(
            tenant_id=tenant_id,
            job=job2,
            field="field2",
            rule="type_check",
            status="failed",
            message="Error 2",
            record_index=0,
        )

        response = authenticated_client.get(f"/api/v1/data-migration/validations/?job_id={migration_job.id}")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1

    def test_filter_validations_by_status(self, authenticated_client, tenant_user, migration_job):
        """Test filtering validations by status."""
        tenant_id = get_user_tenant_id(tenant_user)
        
        MigrationValidation.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            field="field1",
            rule="required",
            status="failed",
            message="Failed validation",
            record_index=0,
        )
        MigrationValidation.objects.create(
            tenant_id=tenant_id,
            job=migration_job,
            field="field2",
            rule="type_check",
            status="passed",
            message="Passed validation",
            record_index=1,
        )

        response = authenticated_client.get("/api/v1/data-migration/validations/?status=failed")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        assert len(data) == 1
        assert data[0]["status"] == "failed"
