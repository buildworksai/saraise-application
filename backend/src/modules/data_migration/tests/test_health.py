"""
Health Check Tests for DataMigration module.

Tests the health check endpoint functionality.
"""
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from src.core.user_models import UserProfile
from src.core.licensing.models import Organization
from ..models import MigrationJob

User = get_user_model()


@pytest.fixture
def client():
    """Create test client."""
    return Client()


@pytest.fixture
def tenant_user(db):
    """Create a test user with tenant."""
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


@pytest.mark.django_db
class TestDataMigrationHealthCheck:
    """Test DataMigration health check endpoint."""

    def test_health_check_returns_200(self, client):
        """Test that health check returns 200 OK."""
        response = client.get("/api/v1/data-migration/health/")
        assert response.status_code == 200

    def test_health_check_returns_json(self, client):
        """Test that health check returns JSON response."""
        response = client.get("/api/v1/data-migration/health/")
        assert response["Content-Type"] == "application/json"
        data = response.json()
        assert "status" in data
        assert "module" in data
        assert "checks" in data

    def test_health_check_includes_module_name(self, client):
        """Test that health check includes module name."""
        response = client.get("/api/v1/data-migration/health/")
        data = response.json()
        assert data["module"] == "data-migration"

    def test_health_check_database_status(self, client):
        """Test that health check reports database status."""
        response = client.get("/api/v1/data-migration/health/")
        data = response.json()
        assert "database" in data["checks"]
        assert data["checks"]["database"] == "ok"

    def test_health_check_cache_status(self, client):
        """Test that health check reports cache status."""
        response = client.get("/api/v1/data-migration/health/")
        data = response.json()
        assert "cache" in data["checks"]
        # Cache status can be "ok" or "degraded" depending on Redis availability
        assert data["checks"]["cache"] in ["ok", "degraded", "not responding correctly"]

    def test_health_check_module_models_status(self, client, tenant_user):
        """Test that health check reports module models status."""
        # Create test data
        MigrationJob.objects.create(
            tenant_id=str(tenant_user.profile.tenant_id),
            name="Test Migration",
            source_type="csv",
            source_config={},
            created_by=str(tenant_user.id),
        )

        response = client.get("/api/v1/data-migration/health/")
        data = response.json()
        assert "module_model" in data["checks"]
        assert data["checks"]["module_model"]["status"] == "ok"
        assert "total_count" in data["checks"]["module_model"]

    def test_health_check_database_error(self, client):
        """Test health check when database has errors."""
        from unittest.mock import patch
        with patch("django.db.connection.cursor") as mock_cursor:
            mock_cursor.side_effect = Exception("Database error")
            response = client.get("/api/v1/data-migration/health/")
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "error" in data["checks"]["database"].lower()

    def test_health_check_cache_error(self, client):
        """Test health check when cache has errors."""
        from unittest.mock import patch
        with patch("django.core.cache.cache.set") as mock_set:
            mock_set.side_effect = Exception("Cache error")
            response = client.get("/api/v1/data-migration/health/")
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "error" in data["checks"]["cache"].lower()

    def test_health_check_model_error(self, client):
        """Test health check when model query has errors."""
        from unittest.mock import patch
        with patch("src.modules.data_migration.models.MigrationJob.objects.count") as mock_count:
            mock_count.side_effect = Exception("Model error")
            response = client.get("/api/v1/data-migration/health/")
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "error" in data["checks"]["module_model"].lower()
