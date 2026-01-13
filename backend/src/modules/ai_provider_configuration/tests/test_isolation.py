"""
Tenant Isolation Tests for AiProviderConfiguration module.

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

from src.modules.ai_provider_configuration.models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIProviderCredential,
    AIUsageLog,
)
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
class TestAIProviderCredentialTenantIsolation:
    """Tenant isolation tests for AIProviderCredential model."""

    def test_user_cannot_list_other_tenant_credentials(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's credentials in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create provider
        provider = AIProvider.objects.create(
            name="Test Provider",
            provider_type="openai",
        )

        # Create credentials
        credential_a = AIProviderCredential.objects.create(
            tenant_id=tenant_a_id,
            provider=provider,
            api_key_encrypted="encrypted_key_a",
        )

        credential_b = AIProviderCredential.objects.create(
            tenant_id=tenant_b_id,
            provider=provider,
            api_key_encrypted="encrypted_key_b",
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-provider-configuration/credentials/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        credential_ids = [c["id"] for c in data]

        # User A should see tenant A's credential, but NOT tenant B's credential
        assert credential_a.id in credential_ids
        assert credential_b.id not in credential_ids


@pytest.mark.django_db
class TestAIModelDeploymentTenantIsolation:
    """Tenant isolation tests for AIModelDeployment model."""

    def test_user_cannot_list_other_tenant_deployments(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's deployments in list."""
        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create provider and model
        provider = AIProvider.objects.create(
            name="Test Provider",
            provider_type="openai",
        )
        model = AIModel.objects.create(
            provider=provider,
            model_id="gpt-4",
            display_name="GPT-4",
        )

        # Create deployments
        deployment_a = AIModelDeployment.objects.create(
            tenant_id=tenant_a_id,
            model=model,
            status="active",
            created_by=str(tenant_a_user.id),
        )

        deployment_b = AIModelDeployment.objects.create(
            tenant_id=tenant_b_id,
            model=model,
            status="active",
            created_by=str(tenant_b_user.id),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-provider-configuration/deployments/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        deployment_ids = [d["id"] for d in data]

        # User A should see tenant A's deployment, but NOT tenant B's deployment
        assert deployment_a.id in deployment_ids
        assert deployment_b.id not in deployment_ids


@pytest.mark.django_db
class TestAIUsageLogTenantIsolation:
    """Tenant isolation tests for AIUsageLog model."""

    def test_user_cannot_list_other_tenant_usage_logs(self, api_client, tenant_a_user, tenant_b_user):
        """Test: User sees only their tenant's usage logs in list."""
        from decimal import Decimal

        tenant_a_id = get_user_tenant_id(tenant_a_user)
        tenant_b_id = get_user_tenant_id(tenant_b_user)

        # Create provider, model, and deployments
        provider = AIProvider.objects.create(
            name="Test Provider",
            provider_type="openai",
        )
        model = AIModel.objects.create(
            provider=provider,
            model_id="gpt-4",
            display_name="GPT-4",
        )
        deployment_a = AIModelDeployment.objects.create(
            tenant_id=tenant_a_id,
            model=model,
            created_by=str(tenant_a_user.id),
        )
        deployment_b = AIModelDeployment.objects.create(
            tenant_id=tenant_b_id,
            model=model,
            created_by=str(tenant_b_user.id),
        )

        # Create usage logs
        usage_a = AIUsageLog.objects.create(
            tenant_id=tenant_a_id,
            deployment=deployment_a,
            tokens_used=1000,
            cost=Decimal("0.01"),
        )

        usage_b = AIUsageLog.objects.create(
            tenant_id=tenant_b_id,
            deployment=deployment_b,
            tokens_used=2000,
            cost=Decimal("0.02"),
        )

        # Login as tenant A
        api_client.force_authenticate(user=tenant_a_user)

        response = api_client.get("/api/v1/ai-provider-configuration/usage-logs/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data if isinstance(response.data, list) else response.data.get("results", [])
        usage_ids = [u["id"] for u in data]

        # User A should see tenant A's usage, but NOT tenant B's usage
        assert usage_a.id in usage_ids
        assert usage_b.id not in usage_ids
