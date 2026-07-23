"""Service proof for validation, audit, idempotency and reversibility."""

import copy
import uuid

import pytest

from src.modules.api_management.models import (
    ApiManagementAuditRecord,
    ApiManagementConfiguration,
    ApiManagementResourceVersion,
    TenantBaseModel,
)
from src.modules.api_management.services import (
    CONFIGURATION_KEYS,
    PLATFORM_HARD_CEILINGS,
    ApiManagementService,
    ConfigurationValidationError,
    IdempotencyConflictError,
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
        assert exported["schema_version"] == 2
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

    def test_environment_configuration_and_import_promotion_are_isolated(self, context):
        service = ApiManagementService()
        production = service.get_configuration(
            context["tenant_id"],
            environment="production",
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        staging = service.get_configuration(
            context["tenant_id"],
            environment="staging",
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        staging_document = copy.deepcopy(staging.document)
        staging_document["resource_name_max_length"] = 88
        service.update_configuration(
            context["tenant_id"],
            staging_document,
            environment="staging",
            **mutation(context),
        )

        production.refresh_from_db()
        assert production.document["resource_name_max_length"] == 255
        exported = service.export_configuration(
            context["tenant_id"],
            environment="production",
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        promoted = service.import_configuration(
            context["tenant_id"],
            exported,
            environment="staging",
            **mutation(context),
        )
        assert promoted.environment == "staging"
        assert promoted.document["environment"] == "staging"
        assert "staging" in promoted.document["environment_registry"]

    def test_configuration_history_is_environment_scoped_and_governed(self, context):
        service = ApiManagementService()
        current = service.get_configuration(
            context["tenant_id"],
            environment="production",
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        document = copy.deepcopy(current.document)
        document["validation_limits"]["configuration_history_page_size"] = 1
        document["validation_limits"]["configuration_history_max_page_size"] = 1
        document["validation_limits"]["configuration_history_max_page"] = 2
        service.update_configuration(context["tenant_id"], document, **mutation(context))

        versions, count, page, page_size = service.configuration_history(
            context["tenant_id"],
            page=1,
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        assert count == 2
        assert (page, page_size) == (1, 1)
        assert [item.version for item in versions] == [2]
        with pytest.raises(ConfigurationValidationError):
            service.configuration_history(
                context["tenant_id"],
                page=3,
                actor_id=context["actor_id"],
                correlation_id=context["correlation_id"],
            )

    def test_resource_version_rollback_is_audited_and_payload_idempotent(self, context):
        service = ApiManagementService()
        resource = service.create_resource(context["tenant_id"], "Version one", **mutation(context))
        service.update_resource(
            resource.id,
            context["tenant_id"],
            updates={"name": "Version two"},
            **mutation(context),
        )
        rollback_key = uuid.uuid4()
        rollback_context = {
            "actor_id": context["actor_id"],
            "correlation_id": "req_resource_rollback",
            "idempotency_key": rollback_key,
        }
        rolled_back = service.rollback_resource(
            resource.id,
            context["tenant_id"],
            1,
            **rollback_context,
        )
        assert rolled_back is not None
        assert rolled_back.name == "Version one"
        assert rolled_back.version == 3
        assert (
            service.rollback_resource(
                resource.id,
                context["tenant_id"],
                1,
                **rollback_context,
            )
            == rolled_back
        )
        evidence = ApiManagementResourceVersion.objects.get(
            tenant_id=context["tenant_id"],
            idempotency_key=rollback_key,
        )
        assert evidence.source_version == 1
        audit = ApiManagementAuditRecord.objects.get(
            tenant_id=context["tenant_id"],
            idempotency_key=rollback_key,
        )
        assert audit.correlation_id == "req_resource_rollback"
        assert audit.before_value["name"] == "Version two"
        assert audit.after_value["name"] == "Version one"
        with pytest.raises(IdempotencyConflictError):
            service.rollback_resource(
                resource.id,
                context["tenant_id"],
                2,
                **rollback_context,
            )

    def test_configuration_schema_covers_every_governed_field(self, context):
        service = ApiManagementService()
        schema = service.configuration_schema(
            context["tenant_id"],
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        nested = {"validation_limits", "navigation"}
        assert CONFIGURATION_KEYS - nested <= set(schema["fields"])
        current = service.get_configuration(
            context["tenant_id"],
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        assert all(f"validation_limits.{field}" in schema["fields"] for field in current.document["validation_limits"])
        assert all(f"navigation.{target}.order" in schema["fields"] for target in current.document["navigation"])
        assert schema["environment"] == "production"
        assert all(metadata["label"] and metadata["help_text"] for metadata in schema["fields"].values())

    def test_evidence_constraints_are_unsavable_and_quota_fails_closed(self, context):
        service = ApiManagementService()
        current = service.get_configuration(
            context["tenant_id"],
            actor_id=context["actor_id"],
            correlation_id=context["correlation_id"],
        )
        invalid = copy.deepcopy(current.document)
        invalid["audit_actions"].remove("rollback")
        with pytest.raises(ConfigurationValidationError):
            service.update_configuration(context["tenant_id"], invalid, **mutation(context))

        ApiManagementConfiguration.objects.filter(pk=current.pk).update(document={"quota_cost": 0})
        assert service.quota_cost_for_access(context["tenant_id"], "production") == PLATFORM_HARD_CEILINGS["quota_cost"]
