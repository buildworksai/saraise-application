"""Cross-tenant API and configuration isolation proof."""

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.core.user_models import UserProfile
from src.modules.api_management.models import TenantBaseModel
from src.modules.api_management.services import ApiManagementService

User = get_user_model()


def make_user(username):
    tenant_id = str(uuid.uuid4())
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password="testpass123")
    with patch.object(UserProfile, "clean"):
        profile = UserProfile.objects.get(user=user)
        profile.tenant_id = tenant_id
        profile.tenant_role = "tenant_admin"
        profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_a_user(db):
    return make_user("user_a")


@pytest.fixture
def tenant_b_user(db):
    return make_user("user_b")


def create_resource(user, name):
    return ApiManagementService().create_resource(
        get_user_tenant_id(user),
        name,
        actor_id=str(user.id),
        correlation_id="req_isolation",
        idempotency_key=uuid.uuid4(),
    )


def headers():
    return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}


@pytest.mark.django_db
class TestApiManagementTenantIsolation:
    def test_user_cannot_list_other_tenant_resources(self, tenant_a_user, tenant_b_user):
        own = create_resource(tenant_a_user, "Tenant A Resource")
        foreign = create_resource(tenant_b_user, "Tenant B Resource")
        client = APIClient()
        client.force_authenticate(user=tenant_a_user)
        response = client.get("/api/v1/api-management/resources/")
        ids = [item["id"] for item in response.data["results"]]
        assert str(own.id) in ids
        assert str(foreign.id) not in ids

    def test_user_cannot_get_other_tenant_resource_by_id(self, tenant_a_user, tenant_b_user):
        foreign = create_resource(tenant_b_user, "Tenant B Resource")
        client = APIClient()
        client.force_authenticate(user=tenant_a_user)
        assert client.get(f"/api/v1/api-management/resources/{foreign.id}/").status_code == 404

    def test_user_cannot_update_other_tenant_resource(self, tenant_a_user, tenant_b_user):
        foreign = create_resource(tenant_b_user, "Tenant B Resource")
        client = APIClient()
        client.force_authenticate(user=tenant_a_user)
        response = client.patch(
            f"/api/v1/api-management/resources/{foreign.id}/",
            {"name": "Hacked"},
            format="json",
            **headers(),
        )
        assert response.status_code == 404
        foreign.refresh_from_db()
        assert foreign.name == "Tenant B Resource"

    def test_user_cannot_delete_other_tenant_resource(self, tenant_a_user, tenant_b_user):
        foreign = create_resource(tenant_b_user, "Tenant B Resource")
        client = APIClient()
        client.force_authenticate(user=tenant_a_user)
        response = client.delete(f"/api/v1/api-management/resources/{foreign.id}/", **headers())
        assert response.status_code == 404
        assert TenantBaseModel.objects.filter(pk=foreign.id, deleted_at__isnull=True).exists()

    def test_create_rejects_spoofed_tenant_identifier(self, tenant_a_user, tenant_b_user):
        client = APIClient()
        client.force_authenticate(user=tenant_a_user)
        response = client.post(
            "/api/v1/api-management/resources/",
            {"name": "Spoofed", "tenant_id": get_user_tenant_id(tenant_b_user)},
            format="json",
            **headers(),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not TenantBaseModel.objects.filter(name="Spoofed").exists()

    def test_configuration_read_is_tenant_isolated(self, tenant_a_user, tenant_b_user):
        service = ApiManagementService()
        config_b = service.get_configuration(
            get_user_tenant_id(tenant_b_user), actor_id=str(tenant_b_user.id), correlation_id="req_b"
        )
        changed = dict(config_b.document)
        changed["resource_name_max_length"] = 77
        service.update_configuration(
            get_user_tenant_id(tenant_b_user),
            changed,
            actor_id=str(tenant_b_user.id),
            correlation_id="req_b",
            idempotency_key=uuid.uuid4(),
        )
        client = APIClient()
        client.force_authenticate(user=tenant_a_user)
        response = client.get("/api/v1/api-management/configuration/")
        assert response.status_code == 200
        assert response.data["document"]["resource_name_max_length"] == 255
