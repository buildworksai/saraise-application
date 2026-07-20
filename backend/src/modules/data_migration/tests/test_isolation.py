"""
Tenant Isolation Tests for DataMigration module.

CRITICAL: These tests verify that tenants cannot access each other's data.
This is the PRIMARY security mechanism for multi-tenant isolation.

Reference: saraise-documentation/rules/compliance-enforcement.md
Rule: ALL tenant-scoped queries MUST filter by tenant_id
"""

import ipaddress
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.core.encryption.service import EncryptionService
from src.modules.data_migration.models import (
    ExternalConnection,
    MigrationJob,
    MigrationLog,
    MigrationMapping,
    MigrationValidation,
)
from src.modules.data_migration.services import (
    MigrationEngine,
    _connect_external_database,
    _validated_external_hostaddr,
)

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


@pytest.fixture
def platform_operator_user(db):
    """Create a platform-scoped operator with no tenant membership."""
    user = User.objects.create_user(
        username="platform_operator",
        email="operator@example.com",
        password="testpass123",
    )
    profile = user.profile
    profile.platform_role = "platform_operator"
    profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def external_connection(tenant_a_user):
    """Create an active named connection owned by tenant A."""
    return ExternalConnection.objects.create(
        tenant_id=get_user_tenant_id(tenant_a_user),
        name="Partner warehouse",
        db_scheme="postgresql",
        host="warehouse.partner.example",
        port=5432,
        database="warehouse",
        username="readonly_user",
        password_encrypted=EncryptionService.encrypt("operator-secret"),
        created_by=str(tenant_a_user.id),
    )


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

    @pytest.mark.parametrize(
        "forbidden_key",
        ["connection_string", "query", "sql_query", "dsn", "hostaddr", "host", "service"],
    )
    def test_caller_connection_and_sql_fields_are_rejected_by_api(
        self,
        forbidden_key,
        api_client,
        tenant_a_user,
        external_connection,
    ):
        api_client.force_authenticate(user=tenant_a_user)
        source_config = {
            "connection_id": str(external_connection.id),
            "table": "customers",
            forbidden_key: "caller-controlled-value",
        }
        response = api_client.post(
            "/api/v1/data-migration/jobs/",
            {
                "name": "Injected source",
                "source_type": "database",
                "source_config": source_config,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error = str(response.data)
        assert forbidden_key in error or "migration required" in error or "Raw SQL" in error

    def test_legacy_stored_connection_string_fails_with_migration_required(self, tenant_a_user):
        tenant_id = get_user_tenant_id(tenant_a_user)
        job = MigrationJob.objects.create(
            tenant_id=tenant_id,
            name="Legacy database job",
            source_type="database",
            source_config={
                "connection_string": "postgresql://legacy.invalid/source",
                "table": "customers",
            },
            created_by=str(tenant_a_user.id),
        )

        with pytest.raises(ValueError, match="migration required"):
            MigrationEngine().execute_migration(job.id, tenant_id, dry_run=True)

    def test_cross_tenant_connection_reference_is_rejected(
        self,
        api_client,
        tenant_b_user,
        external_connection,
    ):
        api_client.force_authenticate(user=tenant_b_user)
        response = api_client.post(
            "/api/v1/data-migration/jobs/",
            {
                "name": "Cross-tenant source",
                "source_type": "database",
                "source_config": {
                    "connection_id": str(external_connection.id),
                    "table": "customers",
                },
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not found for tenant" in str(response.data)

    def test_non_operator_cannot_register_or_edit_connection(
        self,
        api_client,
        tenant_a_user,
        external_connection,
    ):
        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.post(
            "/api/v1/data-migration/connections/",
            {
                "tenant_id": get_user_tenant_id(tenant_a_user),
                "name": "Forbidden registration",
                "db_scheme": "postgresql",
                "host": "warehouse.partner.example",
                "port": 5432,
                "database": "warehouse",
                "username": "readonly_user",
                "password": "must-not-be-stored",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not ExternalConnection.objects.filter(name="Forbidden registration").exists()

        edit_response = api_client.patch(
            f"/api/v1/data-migration/connections/{external_connection.id}/",
            {"name": "Forbidden edit"},
            format="json",
        )
        assert edit_response.status_code == status.HTTP_403_FORBIDDEN
        external_connection.refresh_from_db()
        assert external_connection.name == "Partner warehouse"

    def test_operator_registration_tenant_reference_and_pinned_readonly_connection(
        self,
        api_client,
        tenant_a_user,
        platform_operator_user,
    ):
        tenant_id = get_user_tenant_id(tenant_a_user)
        api_client.force_authenticate(user=platform_operator_user)
        registration = api_client.post(
            "/api/v1/data-migration/connections/",
            {
                "tenant_id": tenant_id,
                "name": "Operator managed warehouse",
                "db_scheme": "postgresql",
                "host": "warehouse.partner.example",
                "port": 5432,
                "database": "warehouse",
                "username": "readonly_user",
                "password": "operator-secret",
            },
            format="json",
        )

        assert registration.status_code == status.HTTP_201_CREATED
        assert "password" not in registration.data
        connection_config = ExternalConnection.objects.get(id=registration.data["id"])
        assert connection_config.password_encrypted != "operator-secret"
        assert EncryptionService.decrypt(connection_config.password_encrypted) == "operator-secret"

        api_client.force_authenticate(user=tenant_a_user)
        listing = api_client.get("/api/v1/data-migration/connections/")
        assert listing.status_code == status.HTTP_200_OK
        listed = listing.data if isinstance(listing.data, list) else listing.data["results"]
        assert listed[0]["id"] == str(connection_config.id)
        assert "host" not in listed[0]
        assert "username" not in listed[0]
        assert "password" not in listed[0]

        job_response = api_client.post(
            "/api/v1/data-migration/jobs/",
            {
                "name": "Named connection job",
                "source_type": "database",
                "source_config": {
                    "connection_id": str(connection_config.id),
                    "table": "customers",
                    "columns": ["id", "name"],
                    "filters": {"account_id": "tenant-value"},
                },
            },
            format="json",
        )
        assert job_response.status_code == status.HTTP_201_CREATED

        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [(1, "Acme")]
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor
        public_ip = ipaddress.ip_address("8.8.8.8")
        with (
            patch(
                "src.modules.data_migration.services._resolved_addresses",
                return_value={public_ip},
            ),
            patch("src.modules.data_migration.services._primary_db_addresses", return_value=set()),
            patch(
                "psycopg2.connect",
                return_value=database_connection,
            ) as connect,
        ):
            records = MigrationEngine()._load_database_data(job_response.data["source_config"], tenant_id)

        connect_kwargs = connect.call_args.kwargs
        assert connect_kwargs["host"] == "warehouse.partner.example"
        assert connect_kwargs["hostaddr"] == "8.8.8.8"
        assert connect_kwargs["password"] == "operator-secret"
        assert connect_kwargs["connect_timeout"] == 10
        assert connect_kwargs["options"] == "-c statement_timeout=30000"
        assert connect_kwargs["service"] == ""
        assert connect_kwargs["sslmode"] == "verify-full"
        database_connection.set_session.assert_called_once_with(readonly=True, autocommit=False)
        database_connection.close.assert_called_once_with()
        assert records == [{"id": 1, "name": "Acme"}]

    @pytest.mark.parametrize(
        "config",
        [
            {
                "table": "customers; DROP TABLE users",
            },
            {
                "table": "customers",
                "columns": ["name, (SELECT password FROM users)"],
            },
            {
                "table": "customers",
                "filters": {"tenant_id OR 1=1": "attacker"},
            },
        ],
    )
    def test_identifier_injection_is_rejected_before_connect(self, config, tenant_a_user, external_connection):
        config["connection_id"] = str(external_connection.id)
        with patch("src.modules.data_migration.services._connect_external_database") as connect:
            with pytest.raises(ValueError, match="Invalid"):
                MigrationEngine()._load_database_data(config, get_user_tenant_id(tenant_a_user))
        connect.assert_not_called()

    def test_uses_only_named_connection_and_parameterized_filters(self, tenant_a_user, external_connection):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = [("id",), ("name",)]
        cursor.fetchall.return_value = [(1, "Acme")]
        database_connection = MagicMock()
        database_connection.cursor.return_value = cursor

        with patch(
            "src.modules.data_migration.services._connect_external_database",
            return_value=database_connection,
        ) as connect:
            records = MigrationEngine()._load_database_data(
                {
                    "connection_id": str(external_connection.id),
                    "table": "customers",
                    "columns": ["id", "name"],
                    "filters": {"account_id": "tenant-supplied-value"},
                },
                get_user_tenant_id(tenant_a_user),
            )

        connect.assert_called_once_with(external_connection)
        cursor.execute.assert_called_once_with(
            "SELECT id, name FROM customers WHERE account_id = %s",
            ["tenant-supplied-value"],
        )
        database_connection.close.assert_called_once_with()
        assert records == [{"id": 1, "name": "Acme"}]

    def test_raw_sql_never_reaches_any_connection(self, tenant_a_user, external_connection):
        with patch("src.modules.data_migration.services._connect_external_database") as connect:
            with pytest.raises(ValueError, match="Raw SQL"):
                MigrationEngine()._load_database_data(
                    {
                        "connection_id": str(external_connection.id),
                        "table": "customers",
                        "query": "SELECT * FROM crm_customer",
                    },
                    get_user_tenant_id(tenant_a_user),
                )
        connect.assert_not_called()

    def test_registered_host_targeting_primary_db_host_is_rejected(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "primary-db.internal"}}
        with pytest.raises(ValueError, match="configured Django database host"):
            _validated_external_hostaddr("primary-db.internal")

    def test_registered_host_targeting_loopback_is_rejected_even_when_allowlisted(
        self,
        settings,
        monkeypatch,
    ):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        monkeypatch.setenv("DATA_MIGRATION_ALLOWED_DB_HOSTS", "127.0.0.1")
        with pytest.raises(ValueError, match="internal or non-routable"):
            _validated_external_hostaddr("127.0.0.1")

    def test_host_resolving_to_primary_database_ip_is_rejected(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "primary-db.internal"}}

        def resolve(host):
            assert host in {"warehouse.partner.example", "primary-db.internal"}
            return {ipaddress.ip_address("8.8.8.8")}

        with patch("src.modules.data_migration.services._resolved_addresses", side_effect=resolve):
            with pytest.raises(ValueError, match="configured Django database address"):
                _validated_external_hostaddr("warehouse.partner.example")

    def test_empty_host_is_rejected(self, settings):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        with pytest.raises(ValueError, match="non-empty canonical"):
            _validated_external_hostaddr("")

    def test_allowlist_blocks_hosts_not_listed(self, settings, monkeypatch):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        monkeypatch.setenv("DATA_MIGRATION_ALLOWED_DB_HOSTS", "warehouse.partner.example")
        with pytest.raises(ValueError, match="allowlist"):
            _validated_external_hostaddr("other.example")

    def test_allowlist_never_exempts_unresolvable_host(self, settings, monkeypatch):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        monkeypatch.setenv("DATA_MIGRATION_ALLOWED_DB_HOSTS", "warehouse.partner.example")
        with patch("src.modules.data_migration.services._resolved_addresses", return_value=set()):
            with pytest.raises(ValueError, match="could not be resolved"):
                _validated_external_hostaddr("warehouse.partner.example")

    def test_guard_runs_before_connect_for_internal_registered_host(self, settings, external_connection):
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": ""}}
        external_connection.host = "127.0.0.1"
        external_connection.save(update_fields=["host"])
        with patch("psycopg2.connect") as connect:
            with pytest.raises(ValueError, match="internal or non-routable"):
                _connect_external_database(external_connection)
        connect.assert_not_called()


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
