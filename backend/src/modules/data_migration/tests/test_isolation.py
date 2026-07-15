"""
Tenant Isolation Tests for DataMigration module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.data_migration.models import MigrationJob, MigrationLog, MigrationMapping, MigrationValidation
from src.modules.data_migration.services import MigrationEngine, _assert_external_dsn_allowed

User = get_user_model()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    """Force development mode for tests to bypass licensing."""
    settings.SARAISE_MODE = "development"
    settings.MIDDLEWARE = [
        middleware
        for middleware in settings.MIDDLEWARE
        if middleware != "src.core.auth.mode_auth_middleware.ModeAuthMiddleware"
    ]


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

    def test_user_cannot_execute_other_tenant_job(self, api_client, tenant_a_user, tenant_b_user):
        """Execution lookup is tenant-scoped and cannot reach another tenant's source."""
        job_b = MigrationJob.objects.create(
            tenant_id=get_user_tenant_id(tenant_b_user),
            name="Tenant B database job",
            source_type="database",
            source_config={
                "connection_string": "postgresql://external/source",
                "table": "customers",
            },
            created_by=str(tenant_b_user.id),
        )
        api_client.force_authenticate(user=tenant_a_user)

        with patch.object(MigrationEngine, "execute_migration") as execute:
            response = api_client.post(f"/api/v1/data-migration/jobs/{job_b.id}/execute/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        execute.assert_not_called()


class TestExternalDatabaseSourceSecurity:
    """Database migration sources never execute caller SQL on the application DB."""

    def test_raw_query_payload_is_rejected_by_api(self, api_client, tenant_a_user):
        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.post(
            "/api/v1/data-migration/jobs/",
            {
                "name": "Injected source",
                "source_type": "database",
                "source_config": {
                    "connection_string": "postgresql://external/source",
                    "table": "customers",
                    "query": "SELECT * FROM crm_customer",
                },
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Raw SQL queries are not supported" in str(response.data)

    @pytest.mark.parametrize(
        "config",
        [
            {
                "connection_string": "postgresql://external/source",
                "table": "customers; DROP TABLE users",
            },
            {
                "connection_string": "postgresql://external/source",
                "table": "customers",
                "columns": ["name, (SELECT password FROM users)"],
            },
            {
                "connection_string": "postgresql://external/source",
                "table": "customers",
                "filters": {"tenant_id OR 1=1": "attacker"},
            },
        ],
    )
    def test_identifier_injection_is_rejected_before_connect(self, config):
        with patch("src.modules.data_migration.services._connect_external_database") as connect:
            with pytest.raises(ValueError, match="Invalid"):
                MigrationEngine()._load_database_data(config, str(uuid.uuid4()))
        connect.assert_not_called()

    def test_uses_only_external_connection_and_parameterized_filters(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [(1, "Acme")]
        external_connection = MagicMock()
        external_connection.cursor.return_value = cursor

        with patch(
            "src.modules.data_migration.services._connect_external_database",
            return_value=external_connection,
        ) as connect:
            records = MigrationEngine()._load_database_data(
                {
                    "connection_string": "postgresql://external/source",
                    "table": "customers",
                    "columns": ["id", "name"],
                    "filters": {"account_id": "tenant-supplied-value"},
                },
                str(uuid.uuid4()),
            )

        connect.assert_called_once_with("postgresql://external/source")
        cursor.execute.assert_called_once_with(
            "SELECT id, name FROM customers WHERE account_id = %s",
            ["tenant-supplied-value"],
        )
        external_connection.close.assert_called_once_with()
        assert records == [{"id": 1, "name": "Acme"}]

    def test_raw_sql_never_reaches_any_connection(self):
        with patch("src.modules.data_migration.services._connect_external_database") as connect:
            with pytest.raises(ValueError, match="Raw SQL"):
                MigrationEngine()._load_database_data(
                    {
                        "connection_string": "postgresql://external/source",
                        "table": "customers",
                        "query": "SELECT * FROM crm_customer",
                    },
                    str(uuid.uuid4()),
                )
        connect.assert_not_called()

    def test_dsn_targeting_primary_db_host_is_rejected(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "primary-db.internal"}}
        with pytest.raises(ValueError, match="primary database host"):
            _assert_external_dsn_allowed("postgresql://user:pw@primary-db.internal:5432/saraise")

    def test_dsn_targeting_loopback_is_rejected(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        with pytest.raises(ValueError, match="loopback or internal"):
            _assert_external_dsn_allowed("postgresql://user:pw@127.0.0.1:5432/source")

    def test_dsn_without_host_is_rejected(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        with pytest.raises(ValueError, match="must specify a host"):
            _assert_external_dsn_allowed("postgresql:///source")

    def test_allowlist_blocks_hosts_not_listed(self, settings, monkeypatch):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        monkeypatch.setenv("DATA_MIGRATION_ALLOWED_DB_HOSTS", "warehouse.partner.example")
        with pytest.raises(ValueError, match="allowlist"):
            _assert_external_dsn_allowed("postgresql://user:pw@other.example:5432/source")

    def test_allowlist_permits_listed_unresolvable_host(self, settings, monkeypatch):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        monkeypatch.setenv("DATA_MIGRATION_ALLOWED_DB_HOSTS", "warehouse.partner.example")
        # An explicitly allowlisted host is permitted even if DNS cannot resolve it here.
        _assert_external_dsn_allowed("postgresql://user:pw@warehouse.partner.example:5432/source")

    def test_guard_runs_before_connect_for_internal_dsn(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        with pytest.raises(ValueError, match="loopback or internal"):
            MigrationEngine()._load_database_data(
                {
                    "connection_string": "postgresql://user:pw@127.0.0.1:5432/source",
                    "table": "customers",
                    "columns": ["id"],
                },
                str(uuid.uuid4()),
            )


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
        log_ids = [log["id"] for log in data]

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
