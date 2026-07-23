"""Governed API integration tests."""

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from src.core.auth_utils import get_user_tenant_id
from src.modules.api_management.api import ApiManagementResourceViewSet
from src.modules.api_management.models import TenantBaseModel
from src.modules.api_management.services import ApiManagementService

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tenant_user(db):
    from src.core.licensing.models import Organization
    from src.core.user_models import UserProfile

    organization = Organization.objects.create(name="Test Organization")
    user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = str(organization.id)
    profile.tenant_role = "tenant_admin"
    profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    api_client.force_authenticate(user=tenant_user)
    return api_client


def headers():
    return {"HTTP_IDEMPOTENCY_KEY": str(uuid.uuid4())}


@pytest.mark.django_db
class TestApiManagementResourceViewSet:
    def test_list_resources_requires_authentication(self, api_client):
        assert api_client.get("/api/v1/api-management/resources/").status_code in {401, 403}

    def test_resource_crud_and_transitions_delegate_to_services(self, authenticated_client, tenant_user):
        create = authenticated_client.post(
            "/api/v1/api-management/resources/",
            {"name": "New Resource"},
            format="json",
            **headers(),
        )
        assert create.status_code == status.HTTP_201_CREATED
        assert "tenant_id" not in create.data
        resource_id = create.data["id"]

        update = authenticated_client.patch(
            f"/api/v1/api-management/resources/{resource_id}/",
            {"description": "Updated"},
            format="json",
            **headers(),
        )
        assert update.status_code == status.HTTP_200_OK
        assert update.data["description"] == "Updated"

        deactivate = authenticated_client.post(
            f"/api/v1/api-management/resources/{resource_id}/deactivate/", **headers()
        )
        assert deactivate.status_code == 200
        assert deactivate.data["is_active"] is False
        activate = authenticated_client.post(f"/api/v1/api-management/resources/{resource_id}/activate/", **headers())
        assert activate.status_code == 200
        assert activate.data["is_active"] is True

        delete = authenticated_client.delete(f"/api/v1/api-management/resources/{resource_id}/", **headers())
        assert delete.status_code == status.HTTP_204_NO_CONTENT
        archived = TenantBaseModel.objects.get(pk=resource_id)
        assert archived.deleted_at is not None

        restore = authenticated_client.post(f"/api/v1/api-management/resources/{resource_id}/restore/", **headers())
        assert restore.status_code == 200
        assert restore.data["id"] == resource_id

    def test_list_is_bounded_filtered_and_ordered(self, authenticated_client, tenant_user):
        service = ApiManagementService()
        tenant = get_user_tenant_id(tenant_user)
        for name in ("Zulu", "Alpha"):
            service.create_resource(
                tenant,
                name,
                actor_id=str(tenant_user.id),
                correlation_id="req_list",
                idempotency_key=uuid.uuid4(),
            )
        response = authenticated_client.get("/api/v1/api-management/resources/?ordering=name&page_size=1")
        assert response.status_code == 200
        assert response.data["count"] == 2
        assert response.data["results"][0]["name"] == "Alpha"

    def test_configuration_endpoints_round_trip(self, authenticated_client):
        current = authenticated_client.get("/api/v1/api-management/configuration/")
        assert current.status_code == 200
        document = dict(current.data["document"])
        document["resource_name_max_length"] = 100
        preview = authenticated_client.post(
            "/api/v1/api-management/configuration/preview/", {"document": document}, format="json"
        )
        assert preview.status_code == 200
        assert preview.data["valid"] is True
        update = authenticated_client.put(
            "/api/v1/api-management/configuration/",
            {"document": document, "idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        assert update.status_code == 200
        assert update.data["version"] == 2
        history = authenticated_client.get("/api/v1/api-management/configuration/history/")
        assert [item["version"] for item in history.data["results"]] == [2, 1]
        export = authenticated_client.get("/api/v1/api-management/configuration/export/")
        assert export.data["document"]["resource_name_max_length"] == 100

    def test_get_queryset_without_tenant_returns_none(self, db):
        request = APIRequestFactory().get("/api/v1/api-management/resources/")
        request.user = AnonymousUser()
        request.tenant_id = None
        view = ApiManagementResourceViewSet()
        view.request = request
        assert list(view.get_queryset()) == []

    def test_resource_rollback_endpoint_creates_compensating_version(
        self,
        authenticated_client,
    ):
        created = authenticated_client.post(
            "/api/v1/api-management/resources/",
            {"name": "Version one"},
            format="json",
            **headers(),
        )
        resource_id = created.data["id"]
        updated = authenticated_client.patch(
            f"/api/v1/api-management/resources/{resource_id}/",
            {"name": "Version two"},
            format="json",
            **headers(),
        )
        assert updated.data["version"] == 2
        versions = authenticated_client.get(f"/api/v1/api-management/resources/{resource_id}/versions/")
        assert versions.status_code == 200
        assert [item["version"] for item in versions.data["results"]] == [2, 1]
        rolled_back = authenticated_client.post(
            f"/api/v1/api-management/resources/{resource_id}/rollback/",
            {"version": 1},
            format="json",
            **headers(),
        )
        assert rolled_back.status_code == 200
        assert rolled_back.data["name"] == "Version one"
        assert rolled_back.data["version"] == 3

    def test_configuration_history_explicit_pagination_is_bounded(
        self,
        authenticated_client,
    ):
        current = authenticated_client.get("/api/v1/api-management/configuration/?environment=staging")
        document = current.data["document"]
        document["resource_name_max_length"] = 99
        authenticated_client.put(
            "/api/v1/api-management/configuration/?environment=staging",
            {"document": document, "idempotency_key": str(uuid.uuid4())},
            format="json",
        )
        response = authenticated_client.get(
            "/api/v1/api-management/configuration/history/" "?environment=staging&page=1&page_size=1"
        )
        assert response.status_code == 200
        assert response.data["count"] == 2
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["environment"] == "staging"
        assert response.data["next"] == 2

    def test_configuration_schema_returns_selected_environment_and_guidance(
        self,
        authenticated_client,
    ):
        response = authenticated_client.get("/api/v1/api-management/configuration/schema/?environment=development")
        assert response.status_code == 200
        assert response.data["environment"] == "development"
        assert response.data["fields"]["health_cache_ttl_seconds"]["help_text"]
        assert response.data["fields"]["validation_limits.page_size_maximum"]["max_value"]

    def test_resource_operations_ignore_client_selected_policy_environment(
        self,
        authenticated_client,
        tenant_user,
    ):
        service = ApiManagementService()
        tenant = get_user_tenant_id(tenant_user)
        development = service.get_configuration(
            tenant,
            environment="development",
            actor_id=str(tenant_user.id),
            correlation_id="trusted-runtime-policy",
        )
        document = development.document
        document["validation_limits"]["resource_name_maximum_ceiling"] = 400
        document["resource_name_max_length"] = 400
        service.update_configuration(
            tenant,
            document,
            environment="development",
            actor_id=str(tenant_user.id),
            correlation_id="trusted-runtime-policy",
            idempotency_key=uuid.uuid4(),
        )
        response = authenticated_client.post(
            "/api/v1/api-management/resources/?environment=development",
            {"name": "x" * 300},
            format="json",
            **headers(),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_unregistered_environment_read_does_not_create_state(
        self,
        authenticated_client,
    ):
        response = authenticated_client.get("/api/v1/api-management/configuration/?environment=rogue")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
