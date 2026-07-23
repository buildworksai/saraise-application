"""Service tests for governed AI-provider configuration behavior."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.exceptions import ValidationError

from src.modules.ai_provider_configuration.models import TenantBaseModel
from src.modules.ai_provider_configuration.services import AiProviderConfigurationService


@pytest.mark.django_db
class TestAiProviderConfigurationService:
    def test_create_resource_requires_uuid_tenant_and_idempotency(self) -> None:
        service = AiProviderConfigurationService()
        with pytest.raises(ValidationError):
            service.create_resource(tenant_id="tenant-123", name="Test Resource", created_by=uuid.uuid4())
        with pytest.raises(ValidationError):
            service.create_resource(tenant_id=uuid.uuid4(), name="Test Resource", created_by=uuid.uuid4())

    def test_create_resource(self) -> None:
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        resource = AiProviderConfigurationService().create_resource(
            tenant_id=tenant_id,
            name="Test Resource",
            description="Test description",
            created_by=actor_id,
            idempotency_key="create-resource",
        )
        assert resource.id is not None
        assert resource.name == "Test Resource"
        assert resource.tenant_id == tenant_id
        assert resource.created_by == actor_id

    def test_create_resource_replays_same_idempotency_key(self) -> None:
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        first = service.create_resource(
            tenant_id=tenant_id,
            name="Test Resource",
            created_by=actor_id,
            idempotency_key="same-request",
        )
        second = service.create_resource(
            tenant_id=tenant_id,
            name="Test Resource",
            created_by=actor_id,
            idempotency_key="same-request",
        )
        assert second.id == first.id

    def test_get_resource_wrong_tenant(self) -> None:
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=uuid.uuid4(),
            name="Test Resource",
            created_by=uuid.uuid4(),
            idempotency_key="tenant-a-create",
        )
        assert service.get_resource(resource.id, uuid.uuid4()) is None

    def test_update_resource_validates_allowed_config_keys(self) -> None:
        tenant_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=tenant_id,
            name="Original Name",
            created_by=uuid.uuid4(),
            idempotency_key="update-create",
        )
        updated = service.update_resource(resource.id, tenant_id, name="Updated Name", config={"owner": "ops"})
        assert updated is not None
        assert updated.name == "Updated Name"
        assert updated.config == {"owner": "ops"}
        with pytest.raises(ValidationError):
            service.update_resource(resource.id, tenant_id, config={"unsupported": True})

    def test_delete_and_restore_resource_are_reversible(self) -> None:
        tenant_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=tenant_id,
            name="To Archive",
            created_by=uuid.uuid4(),
            idempotency_key="delete-create",
        )
        assert service.delete_resource(resource.id, tenant_id) is True
        archived = TenantBaseModel.objects.get(id=resource.id)
        assert archived.is_deleted is True
        restored = service.restore_resource(resource.id, tenant_id)
        assert restored.is_deleted is False

    def test_activate_and_deactivate_resource(self) -> None:
        tenant_id = uuid.uuid4()
        service = AiProviderConfigurationService()
        resource = service.create_resource(
            tenant_id=tenant_id,
            name="Toggle Resource",
            created_by=uuid.uuid4(),
            idempotency_key="toggle-create",
        )
        assert service.deactivate_resource(resource.id, tenant_id).is_active is False
        assert service.activate_resource(resource.id, tenant_id).is_active is True
