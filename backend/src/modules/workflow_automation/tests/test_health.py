"""
Health Check Tests for WorkflowAutomation module.

Tests the health check endpoint functionality.
"""
import pytest
from django.test import Client
from django.contrib.auth import get_user_model
from src.core.user_models import UserProfile
from src.core.licensing.models import Organization
from src.modules.workflow_automation.models import Workflow, WorkflowInstance, WorkflowTask

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
class TestWorkflowAutomationHealthCheck:
    """Test WorkflowAutomation health check endpoint."""

    def test_health_check_returns_200(self, client):
        """Test that health check returns 200 OK."""
        response = client.get("/api/v1/workflow-automation/health/")
        assert response.status_code == 200

    def test_health_check_returns_json(self, client):
        """Test that health check returns JSON response."""
        response = client.get("/api/v1/workflow-automation/health/")
        assert response["Content-Type"] == "application/json"
        data = response.json()
        assert "status" in data
        assert "module" in data
        assert "checks" in data

    def test_health_check_includes_module_name(self, client):
        """Test that health check includes module name."""
        response = client.get("/api/v1/workflow-automation/health/")
        data = response.json()
        assert data["module"] == "workflow-automation"

    def test_health_check_database_status(self, client):
        """Test that health check reports database status."""
        response = client.get("/api/v1/workflow-automation/health/")
        data = response.json()
        assert "database" in data["checks"]
        assert data["checks"]["database"] == "ok"

    def test_health_check_cache_status(self, client):
        """Test that health check reports cache status."""
        response = client.get("/api/v1/workflow-automation/health/")
        data = response.json()
        assert "cache" in data["checks"]
        # Cache status can be "ok" or "degraded" depending on Redis availability
        assert data["checks"]["cache"] in ["ok", "degraded", "not responding correctly"]

    def test_health_check_module_models_status(self, client, tenant_user):
        """Test that health check reports module models status."""
        # Create test data
        Workflow.objects.create(
            tenant_id=str(tenant_user.profile.tenant_id),
            name="Test Workflow",
            trigger_type="manual",
            created_by=tenant_user,
        )

        response = client.get("/api/v1/workflow-automation/health/")
        data = response.json()
        assert "module_models" in data["checks"]
        assert data["checks"]["module_models"]["status"] == "ok"
        assert "workflows" in data["checks"]["module_models"]
        assert "instances" in data["checks"]["module_models"]
        assert "tasks" in data["checks"]["module_models"]
