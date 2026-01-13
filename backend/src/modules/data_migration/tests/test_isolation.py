"""
Tenant Isolation Tests for DataMigration module.

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

from src.modules.data_migration.models import MigrationJob, MigrationLog, MigrationMapping, MigrationValidation
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
class TestMigrationJobTenantIsolation:
    """Tenant isolation tests for MigrationJob model."""

    def test_user_cannot_list_other_tenant_jobs(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's migration jobs in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create job for tenant A
        job_a = MigrationJob.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Job",
            source_type="csv",
            created_by=str(tenant_a_user.id),
        )

        # Create job for tenant B
        job_b = MigrationJob.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Job",
            source_type="csv",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/data-migration/jobs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        job_ids = [j["id"] for j in data]

        # User A should see tenant A's job, but NOT tenant B's job
        assert job_a.id in job_ids
        assert job_b.id not in job_ids

    def test_user_cannot_get_other_tenant_job_by_id(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User cannot GET other tenant's job by ID (returns 404)."""
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create job for tenant B
        job_b = MigrationJob.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Job",
            source_type="csv",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        # Try to access tenant B's job
        response = api_client.get(f"/api/v1/data-migration/jobs/{job_b.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestMigrationMappingTenantIsolation:
    """Tenant isolation tests for MigrationMapping model."""

    def test_user_cannot_list_other_tenant_mappings(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's mappings in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create jobs
        job_a = MigrationJob.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Job",
            source_type="csv",
            created_by=str(tenant_a_user.id),
        )

        job_b = MigrationJob.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Job",
            source_type="csv",
            created_by=str(tenant_b_user.id),
        )

        # Create mappings
        mapping_a = MigrationMapping.objects.create(
            tenant_id=tenant_a_id,
            job=job_a,
            source_field="field_a",
            target_field="target_a",
        )

        mapping_b = MigrationMapping.objects.create(
            tenant_id=tenant_b_id,
            job=job_b,
            source_field="field_b",
            target_field="target_b",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/data-migration/mappings/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        mapping_ids = [m["id"] for m in data]

        # User A should see tenant A's mapping, but NOT tenant B's mapping
        assert mapping_a.id in mapping_ids
        assert mapping_b.id not in mapping_ids


@pytest.mark.django_db
class TestMigrationLogTenantIsolation:
    """Tenant isolation tests for MigrationLog model."""

    def test_user_cannot_list_other_tenant_logs(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's logs in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create jobs
        job_a = MigrationJob.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Job",
            source_type="csv",
            created_by=str(tenant_a_user.id),
        )

        job_b = MigrationJob.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Job",
            source_type="csv",
            created_by=str(tenant_b_user.id),
        )

        # Create logs
        log_a = MigrationLog.objects.create(
            tenant_id=tenant_a_id,
            job=job_a,
            level="info",
            message="Tenant A log message",
        )

        log_b = MigrationLog.objects.create(
            tenant_id=tenant_b_id,
            job=job_b,
            level="info",
            message="Tenant B log message",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/data-migration/logs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        log_ids = [l["id"] for l in data]

        # User A should see tenant A's log, but NOT tenant B's log
        assert log_a.id in log_ids
        assert log_b.id not in log_ids


@pytest.mark.django_db
class TestMigrationValidationTenantIsolation:
    """Tenant isolation tests for MigrationValidation model."""

    def test_user_cannot_list_other_tenant_validations(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's validations in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create jobs
        job_a = MigrationJob.objects.create(
            tenant_id=tenant_a_id,
            name="Tenant A Job",
            source_type="csv",
            created_by=str(tenant_a_user.id),
        )

        job_b = MigrationJob.objects.create(
            tenant_id=tenant_b_id,
            name="Tenant B Job",
            source_type="csv",
            created_by=str(tenant_b_user.id),
        )

        # Create validations
        validation_a = MigrationValidation.objects.create(
            tenant_id=tenant_a_id,
            job=job_a,
            field="field_a",
            rule="required",
            status="failed",
        )

        validation_b = MigrationValidation.objects.create(
            tenant_id=tenant_b_id,
            job=job_b,
            field="field_b",
            rule="required",
            status="failed",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/data-migration/validations/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        validation_ids = [v["id"] for v in data]

        # User A should see tenant A's validation, but NOT tenant B's validation
        assert validation_a.id in validation_ids
        assert validation_b.id not in validation_ids
