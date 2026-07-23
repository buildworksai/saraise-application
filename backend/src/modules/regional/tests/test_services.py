"""Business-service proof for Regional configuration and resources."""

import copy
import uuid

import pytest
from django.core.exceptions import ValidationError

from src.modules.regional.models import (
    RegionalAuditRecord,
    RegionalConfigurationVersion,
    RegionalResource,
)
from src.modules.regional.services import (
    DEFAULT_CONFIGURATION_DOCUMENT,
    RegionalConfigurationService,
    RegionalService,
)


@pytest.fixture
def tenant_id():
    return uuid.uuid4()


@pytest.fixture
def service():
    return RegionalService()


def create_resource(service, tenant_id, *, key=None, name="Test Resource"):
    return service.create_resource(
        tenant_id=tenant_id,
        name=name,
        description=None,
        config={"country_code": "in"},
        created_by="user-123",
        correlation_id=uuid.uuid4(),
        idempotency_key=key or str(uuid.uuid4()),
        environment="development",
    )


@pytest.mark.django_db
class TestRegionalService:
    def test_create_applies_configuration_and_is_idempotent(self, service, tenant_id):
        key = str(uuid.uuid4())
        first = create_resource(service, tenant_id, key=key)
        replay = create_resource(service, tenant_id, key=key)
        assert replay.id == first.id
        assert first.config == {"country_code": "IN"}
        assert first.is_active is True
        assert RegionalResource.objects.filter(tenant_id=tenant_id).count() == 1
        assert RegionalAuditRecord.objects.filter(
            tenant_id=tenant_id, operation="resource.create"
        ).count() == 1

    def test_idempotency_key_cannot_be_reused_for_different_request(self, service, tenant_id):
        key = str(uuid.uuid4())
        create_resource(service, tenant_id, key=key)
        with pytest.raises(ValidationError):
            create_resource(service, tenant_id, key=key, name="Different")

    def test_server_validation_rejects_unknown_and_unsafe_values(self, service, tenant_id):
        with pytest.raises(ValidationError):
            service.create_resource(
                tenant_id,
                "",
                None,
                {"secret": "not-allowed"},
                "user-123",
                uuid.uuid4(),
                str(uuid.uuid4()),
                "development",
            )

    def test_get_list_update_soft_delete_restore_and_lifecycle(self, service, tenant_id):
        resource = create_resource(service, tenant_id)
        other_tenant = uuid.uuid4()
        assert service.get_resource(resource.id, other_tenant) is None
        assert list(service.query_resources(tenant_id, "development", {})) == [resource]

        updated = service.update_resource(
            resource.id,
            tenant_id,
            {"name": "Updated", "description": "Updated description"},
            "user-123",
            uuid.uuid4(),
            "development",
        )
        assert updated is not None and updated.name == "Updated"

        deactivated = service.deactivate_resource(
            resource.id, tenant_id, "user-123", uuid.uuid4(), "development"
        )
        assert deactivated is not None and deactivated.is_active is False
        activated = service.activate_resource(
            resource.id, tenant_id, "user-123", uuid.uuid4(), "development"
        )
        assert activated is not None and activated.is_active is True

        assert service.delete_resource(resource.id, tenant_id, "user-123", uuid.uuid4())
        assert service.get_resource(resource.id, tenant_id) is None
        assert RegionalResource.objects.filter(pk=resource.id, deleted_at__isnull=False).exists()
        restored = service.restore_resource(resource.id, tenant_id, "user-123", uuid.uuid4())
        assert restored is not None and restored.deleted_at is None

    def test_query_policy_rejects_unknown_filters(self, service, tenant_id):
        create_resource(service, tenant_id)
        with pytest.raises(ValidationError):
            service.query_resources(tenant_id, "development", {"tenant_id": str(uuid.uuid4())})


@pytest.mark.django_db
class TestRegionalConfigurationService:
    def test_update_preview_history_export_import_and_rollback(self, tenant_id):
        current = RegionalConfigurationService.get_or_create(tenant_id, "development")
        assert current.version == 1
        proposed = copy.deepcopy(DEFAULT_CONFIGURATION_DOCUMENT)
        proposed["resource"]["name_max_length"] = 120
        preview = RegionalConfigurationService.preview(tenant_id, "development", proposed)
        assert preview["valid"] is True
        assert preview["changes"][0]["path"] == "resource.name_max_length"

        updated = RegionalConfigurationService.update(
            tenant_id, "development", proposed, "actor", uuid.uuid4()
        )
        assert updated.version == 2
        assert list(
            RegionalConfigurationService.history(tenant_id, "development").values_list(
                "version", flat=True
            )
        ) == [2, 1]
        exported = RegionalConfigurationService.export_document(tenant_id, "development")
        assert exported["document"] == proposed

        imported = copy.deepcopy(proposed)
        imported["resource"]["name_max_length"] = 100
        current = RegionalConfigurationService.import_document(
            tenant_id, "development", imported, "actor", uuid.uuid4()
        )
        assert current.version == 3
        rolled_back = RegionalConfigurationService.rollback(
            tenant_id, "development", 1, "actor", uuid.uuid4()
        )
        assert rolled_back.version == 4
        assert rolled_back.document == DEFAULT_CONFIGURATION_DOCUMENT
        assert RegionalConfigurationVersion.objects.filter(tenant_id=tenant_id).count() == 4

    def test_validation_and_tenant_isolation_fail_closed(self, tenant_id):
        invalid = copy.deepcopy(DEFAULT_CONFIGURATION_DOCUMENT)
        invalid["api"]["default_page_size"] = 501
        with pytest.raises(ValidationError):
            RegionalConfigurationService.update(
                tenant_id, "development", invalid, "actor", uuid.uuid4()
            )
        other = uuid.uuid4()
        RegionalConfigurationService.get_or_create(other, "development")
        assert not RegionalConfigurationService.history(
            tenant_id, "development"
        ).filter(tenant_id=other).exists()
