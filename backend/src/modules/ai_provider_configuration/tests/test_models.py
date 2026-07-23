"""Model tests for tenant-scoped AI-provider configuration resources."""

from __future__ import annotations

import uuid

import pytest

from src.modules.ai_provider_configuration.models import TenantBaseModel


@pytest.mark.django_db
class TestTenantBaseModelModel:
    def test_create_resource_uses_uuid_tenant_and_actor(self) -> None:
        tenant_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        resource = TenantBaseModel.objects.create(
            tenant_id=tenant_id,
            name="Test Resource",
            description="Test description",
            created_by=actor_id,
        )
        assert resource.id is not None
        assert resource.name == "Test Resource"
        assert resource.tenant_id == tenant_id
        assert resource.created_by == actor_id
        assert resource.is_active is True

    def test_resource_str_representation(self) -> None:
        resource = TenantBaseModel.objects.create(
            tenant_id=uuid.uuid4(),
            name="Test Resource",
            created_by=uuid.uuid4(),
        )
        assert str(resource) == f"Test Resource ({resource.id})"

    def test_resource_has_tenant_id(self) -> None:
        resource = TenantBaseModel(
            name="Test Resource",
            created_by=uuid.uuid4(),
        )
        with pytest.raises(Exception):
            resource.save()

    def test_resource_config_field(self) -> None:
        config = {"owner": "ops", "metadata": {"purpose": "test"}}
        resource = TenantBaseModel.objects.create(
            tenant_id=uuid.uuid4(),
            name="Test Resource",
            config=config,
            created_by=uuid.uuid4(),
        )
        assert resource.config == config
