"""Service proof for validation, audit, idempotency and reversibility."""

import uuid

import pytest

from src.modules.api_management.models import ApiManagementAuditRecord, TenantBaseModel
from src.modules.api_management.services import (
    ApiManagementService,
    ConfigurationValidationError,
)


@pytest.fixture
def context():
    return {
        "tenant_id": uuid.uuid4(),
        "actor_id": "user-123",
        "correlation_id": "req_service_test",
    }


def mutation(context):
    return {
        "actor_id": context["actor_id"],
        "correlation_id": context["correlation_id"],
        "idempotency_key": uuid.uuid4(),
    }


@pytest.mark.django_db
class TestApiManagementService:
    def test_create_is_idempotent_and_audited(self, context):
        service = ApiManagementService()
        key = uuid.uuid4()
        first = service.create_resource(
            context["tenant_id"],
            "Test Resource",
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
            idempotency_key=key,
        )
        replay = service.create_resource(
            context["tenant_id"],
            "Test Resource",
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
            idempotency_key=key,
        )
        assert replay.id == first.id
        assert TenantBaseModel.objects.filter(tenant_id=context["tenant_id"]).count() == 1
        assert ApiManagementAuditRecord.objects.filter(target_id=first.id, action="create").count() == 1

    def test_get_resource_is_tenant_isolated(self, context):
        service = ApiManagementService()
        created = service.create_resource(context["tenant_id"], "Test", **mutation(context))
        assert service.get_resource(created.id, context["tenant_id"]) == created
        assert service.get_resource(created.id, uuid.uuid4()) is None

    def test_query_uses_configured_search_and_ordering(self, context):
        service = ApiManagementService()
        service.create_resource(context["tenant_id"], "Zulu", **mutation(context))
        service.create_resource(context["tenant_id"], "Alpha", **mutation(context))
        result = list(
            service.query_resources(
                context["tenant_id"],
                {"search": "l", "ordering": "name"},
                actor_id=context["actor_id"],
                correlation_id=context["correlation_id"],
            )
        )
        assert [item.name for item in result] == ["Alpha", "Zulu"]

    def test_update_rejects_system_fields(self, context):
        service = ApiManagementService()
        resource = service.create_resource(context["tenant_id"], "Original", **mutation(context))
        with pytest.raises(ValueError):
            service.update_resource(
                resource.id,
                context["tenant_id"],
                updates={"is_active": False},
                **mutation(context),
            )

    def test_update_success_and_missing_resource_paths(self, context):
        service = ApiManagementService()
        resource = service.create_resource(context["tenant_id"], "Original", **mutation(context))
        updated = service.update_resource(
            resource.id,
            context["tenant_id"],
            updates={"name": "Updated", "description": "Updated description"},
            **mutation(context),
        )
        assert updated is not None
        assert updated.name == "Updated"
        assert (
            service.update_resource(
                uuid.uuid4(), context["tenant_id"], updates={"name": "Missing"}, **mutation(context)
            )
            is None
        )
        assert service.delete_resource(uuid.uuid4(), context["tenant_id"], **mutation(context)) is False

    def test_activate_and_deactivate_follow_configuration(self, context):
        service = ApiManagementService()
        resource = service.create_resource(context["tenant_id"], "Transitions", **mutation(context))
        deactivated = service.deactivate_resource(resource.id, context["tenant_id"], **mutation(context))
        assert deactivated is not None and deactivated.is_active is False
        activated = service.activate_resource(resource.id, context["tenant_id"], **mutation(context))
        assert activated is not None and activated.is_active is True
        configuration = service.get_configuration(
            context["tenant_id"], actor_id=context["actor_id"], correlation_id=context["correlation_id"]
        )
        document = dict(configuration.document)
        document["activation_enabled"] = False
        service.update_configuration(context["tenant_id"], document, **mutation(context))
        service.deactivate_resource(resource.id, context["tenant_id"], **mutation(context))
        with pytest.raises(PermissionError):
            service.activate_resource(resource.id, context["tenant_id"], **mutation(context))

    def test_archive_and_restore_are_reversible(self, context):
        service = ApiManagementService()
        resource = service.create_resource(context["tenant_id"], "To archive", **mutation(context))
        assert service.delete_resource(resource.id, context["tenant_id"], **mutation(context)) is True
        assert service.get_resource(resource.id, context["tenant_id"]) is None
        restored = service.restore_resource(resource.id, context["tenant_id"], **mutation(context))
        assert restored is not None
        assert restored.deleted_at is None

    def test_configuration_version_preview_rollback_and_export(self, context):
        service = ApiManagementService()
        current = service.get_configuration(
            context["tenant_id"],
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        changed = dict(current.document)
        changed["resource_name_max_length"] = 100
        preview = service.preview_configuration(context["tenant_id"], changed)
        assert preview["valid"] is True
        assert preview["changes"] == [{"field": "resource_name_max_length", "before": 255, "after": 100}]
        updated = service.update_configuration(context["tenant_id"], changed, **mutation(context))
        assert updated.version == 2
        rolled_back = service.rollback_configuration(context["tenant_id"], 1, **mutation(context))
        assert rolled_back.version == 3
        assert rolled_back.document["resource_name_max_length"] == 255
        exported = service.export_configuration(
            context["tenant_id"],
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        assert exported["module"] == "api_management"
        imported_document = dict(rolled_back.document)
        imported_document["resource_name_min_length"] = 2
        imported = service.import_configuration(
            context["tenant_id"], {"module": "api_management", "document": imported_document}, **mutation(context)
        )
        assert imported.version == 4
        assert imported.document["resource_name_min_length"] == 2

    def test_configuration_invalid_dependencies_are_unsavable(self, context):
        service = ApiManagementService()
        document = service.default_configuration()
        document["page_size"] = document["max_page_size"] + 1
        with pytest.raises(ConfigurationValidationError):
            service.update_configuration(context["tenant_id"], document, **mutation(context))

    def test_feature_flag_and_targeted_rollout_gate_resource_operations(self, context):
        service = ApiManagementService()
        resource = service.create_resource(context["tenant_id"], "Governed", **mutation(context))
        current = service.get_configuration(
            context["tenant_id"],
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        disabled = dict(current.document)
        disabled.update(
            feature_enabled=False,
            rollout_percentage=0,
            rollout_roles=[],
            rollout_cohorts=[],
            activation_enabled=False,
            deactivation_enabled=False,
        )
        service.update_configuration(context["tenant_id"], disabled, **mutation(context))
        with pytest.raises(PermissionError):
            service.query_resources(
                context["tenant_id"],
                {},
                actor_id=context["actor_id"],
                correlation_id=context["correlation_id"],
            )
        with pytest.raises(PermissionError):
            service.delete_resource(resource.id, context["tenant_id"], **mutation(context))

        targeted = dict(disabled)
        targeted.update(
            feature_enabled=True,
            rollout_roles=["beta_operator"],
            activation_enabled=True,
            deactivation_enabled=True,
        )
        service.update_configuration(context["tenant_id"], targeted, **mutation(context))
        with pytest.raises(PermissionError):
            service.query_resources(
                context["tenant_id"],
                {},
                actor_id=context["actor_id"],
                correlation_id=context["correlation_id"],
            )
        visible = service.query_resources(
            context["tenant_id"],
            {},
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
            audience_roles=["beta_operator"],
        )
        assert list(visible) == [resource]
