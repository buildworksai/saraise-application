"""Cross-tenant isolation proof for resources and configuration."""

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.core.user_models import UserProfile
from src.modules.regional.models import RegionalConfiguration, RegionalResource

User = get_user_model()
PREFIX = "/api/v1/regional"


def make_tenant_user(username):
    tenant_id = uuid.uuid4()
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )
    with patch.object(UserProfile, "clean"):
        profile = UserProfile.objects.get(user=user)
        profile.tenant_id = str(tenant_id)
        profile.tenant_role = "tenant_admin"
        profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def tenant_a_user(db):
    return make_tenant_user("user_a")


@pytest.fixture
def tenant_b_user(db):
    return make_tenant_user("user_b")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    settings.SARAISE_MODE = "development"


@pytest.mark.django_db
class TestRegionalTenantIsolation:
    def test_list_detail_update_delete_are_tenant_isolated(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        tenant_a = get_user_tenant_id(tenant_a_user)
        tenant_b = get_user_tenant_id(tenant_b_user)
        resource_a = RegionalResource.objects.create(
            tenant_id=tenant_a,
            name="Tenant A",
            is_active=True,
            created_by=str(tenant_a_user.id),
        )
        resource_b = RegionalResource.objects.create(
            tenant_id=tenant_b,
            name="Tenant B",
            is_active=True,
            created_by=str(tenant_b_user.id),
        )
        api_client.force_authenticate(user=tenant_a_user)

        listed = api_client.get(f"{PREFIX}/resources/")
        assert listed.status_code == status.HTTP_200_OK
        ids = {item["id"] for item in listed.data["results"]}
        assert str(resource_a.id) in ids
        assert str(resource_b.id) not in ids
        assert api_client.get(
            f"{PREFIX}/resources/{resource_b.id}/"
        ).status_code == status.HTTP_404_NOT_FOUND
        assert api_client.patch(
            f"{PREFIX}/resources/{resource_b.id}/",
            {"name": "Hacked"},
            format="json",
        ).status_code == status.HTTP_404_NOT_FOUND
        assert api_client.delete(
            f"{PREFIX}/resources/{resource_b.id}/"
        ).status_code == status.HTTP_404_NOT_FOUND
        resource_b.refresh_from_db()
        assert resource_b.name == "Tenant B"
        assert resource_b.deleted_at is None

    def test_create_cannot_bind_foreign_tenant(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        foreign_tenant = get_user_tenant_id(tenant_b_user)
        api_client.force_authenticate(user=tenant_a_user)
        response = api_client.post(
            f"{PREFIX}/resources/",
            {
                "tenant_id": foreign_tenant,
                "name": "Injected",
                "config": {"country_code": "IN"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not RegionalResource.objects.filter(
            tenant_id=foreign_tenant, name="Injected"
        ).exists()

    def test_configuration_history_and_rollback_are_tenant_isolated(
        self, api_client, tenant_a_user, tenant_b_user
    ):
        api_client.force_authenticate(user=tenant_b_user)
        assert api_client.get(
            f"{PREFIX}/configuration/current/"
        ).status_code == status.HTTP_200_OK
        tenant_b = get_user_tenant_id(tenant_b_user)
        assert RegionalConfiguration.objects.filter(tenant_id=tenant_b).exists()

        api_client.force_authenticate(user=tenant_a_user)
        history = api_client.get(
            f"{PREFIX}/configuration/history/?environment=development"
        )
        assert history.status_code == status.HTTP_200_OK
        assert all(item["environment"] == "development" for item in history.data)
        rollback = api_client.post(
            f"{PREFIX}/configuration/rollback/",
            {"environment": "development", "version": 99},
            format="json",
        )
        assert rollback.status_code == status.HTTP_400_BAD_REQUEST
