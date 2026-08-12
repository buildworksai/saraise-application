"""API tests for the governed AI-provider configuration resource endpoint."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from src.core.access.decision import AccessDecision, AccessReasonCode
from src.core.auth_utils import get_user_tenant_id
from src.core.encryption import EncryptionService
from src.modules.ai_provider_configuration.api import ModulePagination, TenantContextMixin
from src.modules.ai_provider_configuration.models import (
    AIModel,
    AIModelDeployment,
    AIProvider,
    AIUsageLog,
    CredentialStatus,
    ProviderType,
    TenantBaseModel,
)
from src.modules.ai_provider_configuration.services import DEFAULT_RUNTIME_CONFIGURATION, AIUsageService

User = get_user_model()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def allow_declared_ai_provider_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provision the explicit policy projection used by these API tests."""

    def allow(self, tenant_id, identity, required_permission, **kwargs):
        del self, identity, kwargs
        assert str(required_permission).startswith("ai_provider_configuration.")
        return AccessDecision(
            allowed=True,
            reason_code=AccessReasonCode.ALLOW,
            reason="ai provider test projection",
            tenant_id=uuid.UUID(str(tenant_id)),
            remaining_quota=100,
        )

    monkeypatch.setattr("src.core.access.decision.AccessDecisionPipeline.decide", allow)


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


def configure_test_encryption(settings) -> str:
    key = Fernet.generate_key().decode("ascii")
    settings.SARAISE_ENCRYPTION_KEYS = {"primary": key}
    settings.SARAISE_ACTIVE_ENCRYPTION_KEY_ID = "primary"
    settings.SARAISE_ENCRYPTION_KEY = None
    EncryptionService._fernet = None
    EncryptionService._cached_keys = None
    return key


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


@pytest.mark.django_db
def test_catalog_credentials_deployments_usage_runtime_and_secret_actions(authenticated_client, tenant_user, settings):
    active_key = configure_test_encryption(settings)
    tenant_id = get_user_tenant_id(tenant_user)
    provider = AIProvider.objects.create(
        name="OpenAI Test",
        provider_type=ProviderType.OPENAI,
        base_url="https://api.openai.test",
    )
    inactive_provider = AIProvider.objects.create(
        name="Inactive Provider",
        provider_type=ProviderType.CUSTOM,
        base_url="https://inactive.example.test",
        is_active=False,
    )
    model = AIModel.objects.create(
        provider=provider,
        model_id="gpt-test",
        display_name="GPT Test",
        capabilities=["chat", "embeddings"],
        max_tokens=4096,
    )
    AIModel.objects.create(
        provider=inactive_provider,
        model_id="disabled-model",
        display_name="Disabled Model",
        capabilities=["chat"],
        is_active=False,
    )

    providers = authenticated_client.get(
        "/api/v1/ai-provider-configuration/providers/",
        {"provider_type": ProviderType.OPENAI, "search": "OpenAI Test"},
    )
    assert providers.status_code == status.HTTP_200_OK
    assert [item["name"] for item in response_items(providers)] == ["OpenAI Test"]

    models = authenticated_client.get(
        "/api/v1/ai-provider-configuration/models/",
        {"provider": str(provider.id), "capability": "chat", "search": "GPT"},
    )
    assert models.status_code == status.HTTP_200_OK
    assert [item["model_id"] for item in response_items(models)] == ["gpt-test"]

    credential_response = authenticated_client.post(
        "/api/v1/ai-provider-configuration/credentials/",
        {"provider": str(provider.id), "label": "Primary", "api_key": "sk-test-12345678"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-credential-create",
    )
    assert credential_response.status_code == status.HTTP_201_CREATED, credential_response.data
    credential_id = credential_response.data["id"]
    assert credential_response.data["has_secret"] is True
    assert credential_response.data["secret_hint"] == "5678"

    credential = AIProvider.objects.get(pk=provider.id).credentials.get(pk=credential_id)
    credential.status = CredentialStatus.VALID
    credential.save(update_fields=("status", "updated_at"))

    credential_list = authenticated_client.get(
        "/api/v1/ai-provider-configuration/credentials/",
        {"provider_id": str(provider.id), "status": CredentialStatus.VALID, "search": "Prim"},
    )
    assert credential_list.status_code == status.HTTP_200_OK
    assert [item["id"] for item in response_items(credential_list)] == [credential_id]

    deployment_response = authenticated_client.post(
        "/api/v1/ai-provider-configuration/deployments/",
        {
            "model": str(model.id),
            "credential": str(credential_id),
            "deployment_name": "Primary Chat",
            "config": {"max_tokens": 500, "temperature": 0.2},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="api-deployment-create",
    )
    assert deployment_response.status_code == status.HTTP_201_CREATED, deployment_response.data
    deployment_id = deployment_response.data["id"]

    patch_response = authenticated_client.patch(
        f"/api/v1/ai-provider-configuration/deployments/{deployment_id}/",
        {"deployment_name": "Primary Chat Updated", "config": {"top_p": 0.8}},
        format="json",
    )
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_response.data["config"]["max_tokens"] == 1000
    assert patch_response.data["config"]["top_p"] == 0.8

    deactivate = authenticated_client.post(f"/api/v1/ai-provider-configuration/deployments/{deployment_id}/deactivate/")
    activate = authenticated_client.post(f"/api/v1/ai-provider-configuration/deployments/{deployment_id}/activate/")
    assert deactivate.status_code == status.HTTP_200_OK
    assert activate.status_code == status.HTTP_200_OK
    assert activate.data["status"] == "active"

    AIUsageService().record_usage(
        tenant_id,
        deployment_id=deployment_id,
        prompt_tokens=7,
        completion_tokens=11,
        cost=Decimal("0.012345"),
        provider_request_id="req-api-usage",
    )
    usage = authenticated_client.get(
        "/api/v1/ai-provider-configuration/usage-logs/",
        {"deployment_id": deployment_id},
    )
    assert usage.status_code == status.HTTP_200_OK
    assert response_items(usage)[0]["tokens_used"] == 18

    proposed = dict(DEFAULT_RUNTIME_CONFIGURATION)
    proposed["pagination"] = {"default_page_size": 10, "max_page_size": 50}
    preview = authenticated_client.post(
        "/api/v1/ai-provider-configuration/runtime-configuration/preview/",
        {"environment": "default", "values": proposed},
        format="json",
    )
    assert preview.status_code == status.HTTP_200_OK
    assert preview.data["changes"]["pagination"]["after"]["default_page_size"] == 10
    update = authenticated_client.put(
        "/api/v1/ai-provider-configuration/runtime-configuration/current/",
        {"environment": "default", "values": proposed},
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    versions = authenticated_client.get("/api/v1/ai-provider-configuration/runtime-configuration/versions/")
    audit = authenticated_client.get("/api/v1/ai-provider-configuration/runtime-configuration/audit/")
    exported = authenticated_client.get("/api/v1/ai-provider-configuration/runtime-configuration/export/")
    assert versions.status_code == status.HTTP_200_OK
    assert audit.status_code == status.HTTP_200_OK
    assert exported.data["version"] == 2

    rollback = authenticated_client.post(
        "/api/v1/ai-provider-configuration/runtime-configuration/rollback/",
        {"environment": "default", "version": 1},
        format="json",
    )
    imported = authenticated_client.post(
        "/api/v1/ai-provider-configuration/runtime-configuration/import/",
        {"document": exported.data},
        format="json",
    )
    assert rollback.status_code == status.HTTP_200_OK
    assert imported.status_code == status.HTTP_200_OK
    assert imported.data["version"] == 4

    rotate_key = authenticated_client.post("/api/v1/ai-provider-configuration/secrets/rotate-key/", {}, format="json")
    assert rotate_key.status_code == status.HTTP_200_OK
    assert rotate_key.data["new_key"]
    re_encrypt = authenticated_client.post(
        "/api/v1/ai-provider-configuration/secrets/re-encrypt/",
        {"old_key": active_key, "new_key": rotate_key.data["new_key"]},
        format="json",
    )
    assert re_encrypt.status_code == status.HTTP_200_OK
    assert re_encrypt.data["re_encrypted_count"] == 1

    delete_deployment = authenticated_client.delete(f"/api/v1/ai-provider-configuration/deployments/{deployment_id}/")
    delete_credential = authenticated_client.delete(f"/api/v1/ai-provider-configuration/credentials/{credential_id}/")
    assert delete_deployment.status_code == status.HTTP_204_NO_CONTENT
    assert delete_credential.status_code == status.HTTP_204_NO_CONTENT
    assert AIModelDeployment.objects.for_tenant(tenant_id).get(pk=deployment_id).is_deleted is True
    assert AIUsageLog.objects.for_tenant(tenant_id).count() == 1


def test_tenant_context_and_pagination_fail_closed_for_invalid_identity(monkeypatch):
    mixin = TenantContextMixin()
    mixin.request = type("Request", (), {"user": type("User", (), {"pk": None})()})()

    with pytest.raises(Exception, match="valid tenant"):
        mixin.tenant_id()
    assert mixin.tenant_id_or_none() is None
    with pytest.raises(Exception, match="actor identifier"):
        mixin.actor_id()

    mixin.request.user.pk = "not-a-uuid"
    mixin.request.user.tenant_id = uuid.uuid4()
    assert uuid.UUID(mixin.actor_id())

    monkeypatch.setattr(
        "src.modules.ai_provider_configuration.api.AIProviderRuntimeConfigurationService.runtime_values",
        lambda tenant_id: {"pagination": {"default_page_size": 7, "max_page_size": 11}},
    )
    pagination = ModulePagination()
    request = type("Request", (), {"user": mixin.request.user, "query_params": {}})()
    assert pagination.get_page_size(request) == 7
    assert pagination.max_page_size == 11


@pytest.mark.django_db
def test_credential_and_deployment_updates_validate_empty_and_map_relation_fields(
    authenticated_client, tenant_user, settings
):
    configure_test_encryption(settings)
    tenant_id = get_user_tenant_id(tenant_user)
    first_provider = AIProvider.objects.create(
        name="Primary Provider",
        provider_type=ProviderType.OPENAI,
        base_url="https://primary.example.test",
    )
    second_provider = AIProvider.objects.create(
        name="Secondary Provider",
        provider_type=ProviderType.CUSTOM,
        base_url="https://secondary.example.test",
    )
    second_model = AIModel.objects.create(
        provider=second_provider,
        model_id="secondary-model",
        display_name="Secondary Model",
        capabilities=["chat"],
    )

    credential_response = authenticated_client.post(
        "/api/v1/ai-provider-configuration/credentials/",
        {"provider": str(first_provider.id), "label": "Primary", "api_key": "sk-primary-12345678"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="branch-credential-create",
    )
    assert credential_response.status_code == status.HTTP_201_CREATED, credential_response.data
    credential_id = credential_response.data["id"]

    empty_credential_update = authenticated_client.patch(
        f"/api/v1/ai-provider-configuration/credentials/{credential_id}/",
        {},
        format="json",
    )
    assert empty_credential_update.status_code == status.HTTP_400_BAD_REQUEST

    credential_update = authenticated_client.put(
        f"/api/v1/ai-provider-configuration/credentials/{credential_id}/",
        {"provider": str(second_provider.id), "label": "Secondary", "api_key": "sk-secondary-12345678"},
        format="json",
    )
    assert credential_update.status_code == status.HTTP_200_OK, credential_update.data
    assert credential_update.data["provider"] == second_provider.id
    assert credential_update.data["secret_hint"] == "5678"
    credential = second_provider.credentials.get(pk=credential_id)
    credential.status = CredentialStatus.VALID
    credential.save(update_fields=("status", "updated_at"))

    deployment_response = authenticated_client.post(
        "/api/v1/ai-provider-configuration/deployments/",
        {
            "model": str(second_model.id),
            "credential": str(credential_id),
            "deployment_name": "Branch Deployment",
            "config": {"temperature": 0.1},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="branch-deployment-create",
    )
    assert deployment_response.status_code == status.HTTP_201_CREATED, deployment_response.data
    deployment_id = deployment_response.data["id"]

    empty_deployment_update = authenticated_client.patch(
        f"/api/v1/ai-provider-configuration/deployments/{deployment_id}/",
        {},
        format="json",
    )
    assert empty_deployment_update.status_code == status.HTTP_400_BAD_REQUEST

    deployment_update = authenticated_client.put(
        f"/api/v1/ai-provider-configuration/deployments/{deployment_id}/",
        {
            "model": str(second_model.id),
            "credential": credential_id,
            "deployment_name": "Branch Deployment Updated",
            "config": {"top_p": 0.9},
        },
        format="json",
    )
    assert deployment_update.status_code == status.HTTP_200_OK, deployment_update.data
    assert deployment_update.data["model"] == second_model.id
    assert deployment_update.data["deployment_name"] == "Branch Deployment Updated"
    assert AIModelDeployment.objects.for_tenant(tenant_id).get(pk=deployment_id).model_id == second_model.id
