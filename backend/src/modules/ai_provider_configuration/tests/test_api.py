"""API tests for the governed AI-provider configuration resource endpoint."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.modules.ai_provider_configuration.models import TenantBaseModel

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def tenant_user(db):
    from unittest.mock import patch

    from src.core.user_models import UserProfile

    user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
    with patch.object(UserProfile, "clean"):
        profile, _ = UserProfile.objects.get_or_create(
            user=user,
            defaults={"tenant_id": str(uuid.uuid4()), "tenant_role": "tenant_admin"},
        )
        if not profile.tenant_id:
            profile.tenant_id = str(uuid.uuid4())
            profile.tenant_role = "tenant_admin"
            profile.save()
    user = User.objects.get(pk=user.pk)
    user.has_perm = lambda permission: str(permission).startswith("ai_provider_configuration.")  # type: ignore[method-assign]
    return user


@pytest.fixture
def authenticated_client(api_client: APIClient, tenant_user) -> APIClient:
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture(autouse=True)
def override_saraise_mode(settings) -> None:
    settings.SARAISE_MODE = "development"


def response_items(response) -> list[dict[str, object]]:
    return response.data if isinstance(response.data, list) else response.data.get("results", [])


@pytest.mark.django_db
class TestTenantBaseModelViewSet:
    def test_list_resources_requires_authentication(self, api_client: APIClient) -> None:
        response = api_client.get("/api/v1/ai-provider-configuration/resources/")
        assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}

    def test_list_resources(self, authenticated_client: APIClient, tenant_user) -> None:
        tenant_id = get_user_tenant_id(tenant_user)
        TenantBaseModel.objects.create(
            tenant_id=tenant_id,
            name="Test Resource 1",
            description="Test description 1",
            created_by=uuid.uuid4(),
        )
        TenantBaseModel.objects.create(
            tenant_id=tenant_id,
            name="Test Resource 2",
            description="Test description 2",
            created_by=uuid.uuid4(),
        )

        response = authenticated_client.get("/api/v1/ai-provider-configuration/resources/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response_items(response)) == 2

    def test_create_resource(self, authenticated_client: APIClient, tenant_user) -> None:
        tenant_id = str(get_user_tenant_id(tenant_user))
        response = authenticated_client.post(
            "/api/v1/ai-provider-configuration/resources/",
            {"name": "New Resource", "description": "New resource description", "config": {"owner": "ops"}},
            format="json",
            HTTP_IDEMPOTENCY_KEY="resource-create",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Resource"
        assert str(response.data["tenant_id"]) == tenant_id

    def test_create_resource_requires_idempotency_key(self, authenticated_client: APIClient) -> None:
        response = authenticated_client.post(
            "/api/v1/ai-provider-configuration/resources/",
            {"name": "New Resource", "description": "New resource description"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_resource_detail(self, authenticated_client: APIClient, tenant_user) -> None:
        resource = TenantBaseModel.objects.create(
            tenant_id=get_user_tenant_id(tenant_user),
            name="Test Resource",
            description="Test description",
            created_by=uuid.uuid4(),
        )
        response = authenticated_client.get(f"/api/v1/ai-provider-configuration/resources/{resource.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert str(response.data["id"]) == str(resource.id)

    def test_update_resource(self, authenticated_client: APIClient, tenant_user) -> None:
        resource = TenantBaseModel.objects.create(
            tenant_id=get_user_tenant_id(tenant_user),
            name="Original Name",
            description="Original description",
            created_by=uuid.uuid4(),
        )
        response = authenticated_client.put(
            f"/api/v1/ai-provider-configuration/resources/{resource.id}/",
            {"name": "Updated Name", "description": "Updated description", "config": {"owner": "ops"}},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "Updated Name"

    def test_delete_and_restore_resource(self, authenticated_client: APIClient, tenant_user) -> None:
        resource = TenantBaseModel.objects.create(
            tenant_id=get_user_tenant_id(tenant_user),
            name="To Archive",
            description="Will be archived",
            created_by=uuid.uuid4(),
        )
        delete_response = authenticated_client.delete(f"/api/v1/ai-provider-configuration/resources/{resource.id}/")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT
        resource.refresh_from_db()
        assert resource.is_deleted is True
        restore_response = authenticated_client.post(
            f"/api/v1/ai-provider-configuration/resources/{resource.id}/restore/",
            {},
            format="json",
        )
        assert restore_response.status_code == status.HTTP_200_OK
        resource.refresh_from_db()
        assert resource.is_deleted is False
