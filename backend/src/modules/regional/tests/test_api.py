"""Regional API integration tests."""

import copy
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.auth_utils import get_user_tenant_id
from src.core.licensing.models import Organization
from src.core.user_models import UserProfile
from src.modules.regional.models import RegionalAuditRecord, RegionalResource
from src.modules.regional.services import DEFAULT_CONFIGURATION_DOCUMENT

User = get_user_model()
PREFIX = "/api/v1/regional"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def tenant_user(db):
    org = Organization.objects.create(name="Test Organization")
    user = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    profile = UserProfile.objects.get(user=user)
    profile.tenant_id = str(org.id)
    profile.tenant_role = "tenant_admin"
    profile.save()
    return User.objects.get(pk=user.pk)


@pytest.fixture
def authenticated_client(api_client, tenant_user):
    api_client.force_authenticate(user=tenant_user)
    return api_client


@pytest.fixture(autouse=True)
def override_saraise_mode(settings):
    settings.SARAISE_MODE = "development"


def create_payload(name="New Resource"):
    return {
        "name": name,
        "description": "New resource description",
        "config": {"country_code": "IN", "jurisdiction_type": "country"},
    }


@pytest.mark.django_db
class TestRegionalResourceViewSet:
    def test_all_environments_require_authentication(self, api_client, settings):
        for mode in ("development", "self-hosted", "saas"):
            settings.SARAISE_MODE = mode
            response = api_client.get(f"{PREFIX}/resources/")
            assert response.status_code in {
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            }

    def test_list_is_paginated_ordered_and_omits_internal_ids(
        self, authenticated_client, tenant_user
    ):
        tenant_id = get_user_tenant_id(tenant_user)
        for name in ("Bravo", "Alpha"):
            RegionalResource.objects.create(
                tenant_id=tenant_id,
                name=name,
                description="Description",
                is_active=True,
                created_by=str(tenant_user.id),
            )
        response = authenticated_client.get(f"{PREFIX}/resources/?ordering=name")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 2
        assert [item["name"] for item in response.data["results"]] == ["Alpha", "Bravo"]
        assert "tenant_id" not in response.data["results"][0]
        assert "created_by" not in response.data["results"][0]

    def test_create_requires_idempotency_and_returns_original_on_replay(
        self, authenticated_client
    ):
        missing = authenticated_client.post(
            f"{PREFIX}/resources/", create_payload(), format="json"
        )
        assert missing.status_code == status.HTTP_400_BAD_REQUEST

        key = str(uuid.uuid4())
        first = authenticated_client.post(
            f"{PREFIX}/resources/",
            create_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        replay = authenticated_client.post(
            f"{PREFIX}/resources/",
            create_payload(),
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert first.status_code == status.HTTP_201_CREATED
        assert replay.status_code == status.HTTP_201_CREATED
        assert replay.data["id"] == first.data["id"]

    def test_detail_update_lifecycle_and_soft_delete(
        self, authenticated_client, tenant_user
    ):
        resource = RegionalResource.objects.create(
            tenant_id=get_user_tenant_id(tenant_user),
            name="Original",
            description="Description",
            is_active=True,
            created_by=str(tenant_user.id),
        )
        detail = authenticated_client.get(f"{PREFIX}/resources/{resource.id}/")
        assert detail.status_code == status.HTTP_200_OK

        update = authenticated_client.patch(
            f"{PREFIX}/resources/{resource.id}/",
            {"name": "Updated"},
            format="json",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert update.status_code == status.HTTP_200_OK
        assert update.data["name"] == "Updated"

        deactivate = authenticated_client.post(
            f"{PREFIX}/resources/{resource.id}/deactivate/",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert deactivate.status_code == status.HTTP_200_OK
        assert deactivate.data["is_active"] is False
        activate = authenticated_client.post(
            f"{PREFIX}/resources/{resource.id}/activate/",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert activate.status_code == status.HTTP_200_OK
        assert activate.data["is_active"] is True

        deleted = authenticated_client.delete(
            f"{PREFIX}/resources/{resource.id}/",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        resource.refresh_from_db()
        assert resource.deleted_at is not None
        assert authenticated_client.get(
            f"{PREFIX}/resources/{resource.id}/"
        ).status_code == status.HTTP_404_NOT_FOUND
        assert RegionalAuditRecord.objects.filter(
            entity_id=resource.id, operation="resource.delete"
        ).exists()


@pytest.mark.django_db
class TestRegionalConfigurationViewSet:
    def test_current_preview_update_history_export_import_and_rollback(
        self, authenticated_client
    ):
        current = authenticated_client.get(f"{PREFIX}/configuration/current/")
        assert current.status_code == status.HTTP_200_OK
        assert current.data["version"] == 1

        proposed = copy.deepcopy(DEFAULT_CONFIGURATION_DOCUMENT)
        proposed["resource"]["name_max_length"] = 120
        preview = authenticated_client.post(
            f"{PREFIX}/configuration/preview/",
            {"environment": "development", "document": proposed},
            format="json",
        )
        assert preview.status_code == status.HTTP_200_OK
        assert preview.data["valid"] is True

        updated = authenticated_client.put(
            f"{PREFIX}/configuration/current/",
            {"environment": "development", "document": proposed},
            format="json",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert updated.status_code == status.HTTP_200_OK
        assert updated.data["version"] == 2

        history = authenticated_client.get(
            f"{PREFIX}/configuration/history/?environment=development"
        )
        assert history.status_code == status.HTTP_200_OK
        assert [item["version"] for item in history.data] == [2, 1]

        exported = authenticated_client.get(
            f"{PREFIX}/configuration/export_document/?environment=development"
        )
        assert exported.status_code == status.HTTP_200_OK
        assert exported.data["document"] == proposed

        imported_document = copy.deepcopy(proposed)
        imported_document["resource"]["name_max_length"] = 100
        imported = authenticated_client.post(
            f"{PREFIX}/configuration/import_document/",
            {"environment": "development", "document": imported_document},
            format="json",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert imported.status_code == status.HTTP_200_OK
        assert imported.data["version"] == 3

        rollback = authenticated_client.post(
            f"{PREFIX}/configuration/rollback/",
            {"environment": "development", "version": 1},
            format="json",
            HTTP_X_CORRELATION_ID=str(uuid.uuid4()),
        )
        assert rollback.status_code == status.HTTP_200_OK
        assert rollback.data["version"] == 4

    def test_non_admin_is_denied_configuration_write(
        self, authenticated_client, tenant_user
    ):
        profile = tenant_user.profile
        profile.tenant_role = "tenant_user"
        profile.save()
        response = authenticated_client.put(
            f"{PREFIX}/configuration/current/",
            {"environment": "development", "document": DEFAULT_CONFIGURATION_DOCUMENT},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
