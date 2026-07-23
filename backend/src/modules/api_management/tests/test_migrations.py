"""Reversible tenant UUID migration proof."""

import uuid

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_uuid_tenant_migration_is_forward_and_reverse_safe():
    executor = MigrationExecutor(connection)
    executor.migrate([("api_management", "0001_initial")])
    old_apps = executor.loader.project_state([("api_management", "0001_initial")]).apps
    LegacyResource = old_apps.get_model("api_management", "ApiManagementResource")
    tenant_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    LegacyResource.objects.create(
        tenant_id=str(tenant_id),
        id=str(resource_id),
        name="Legacy valid UUID",
        description="",
        is_active=True,
        config={},
        created_by="actor",
    )

    executor = MigrationExecutor(connection)
    executor.migrate([("api_management", "0002_configuration_governance")])
    new_apps = executor.loader.project_state([("api_management", "0002_configuration_governance")]).apps
    Resource = new_apps.get_model("api_management", "ApiManagementResource")
    migrated = Resource.objects.get()
    assert migrated.tenant_id == tenant_id
    assert migrated.id == resource_id

    executor = MigrationExecutor(connection)
    executor.migrate([("api_management", "0001_initial")])
    reversed_apps = executor.loader.project_state([("api_management", "0001_initial")]).apps
    ReversedResource = reversed_apps.get_model("api_management", "ApiManagementResource")
    reversed_resource = ReversedResource.objects.get()
    assert str(reversed_resource.tenant_id) == str(tenant_id)

    executor = MigrationExecutor(connection)
    executor.migrate([("api_management", "0002_configuration_governance")])
    governance_apps = executor.loader.project_state([("api_management", "0002_configuration_governance")]).apps
    Configuration = governance_apps.get_model(
        "api_management",
        "ApiManagementConfiguration",
    )
    ConfigurationVersion = governance_apps.get_model(
        "api_management",
        "ApiManagementConfigurationVersion",
    )
    legacy_document = {
        "environment": "staging",
        "resource_name_min_length": 1,
        "resource_name_max_length": 255,
        "resource_description_default": "",
        "resource_config_default": {},
        "resource_initially_active": True,
        "writable_fields": ["name", "description", "config"],
        "filter_fields": ["is_active"],
        "search_fields": ["name", "description"],
        "ordering_fields": ["name", "created_at", "updated_at"],
        "default_ordering": "-created_at",
        "page_size": 25,
        "max_page_size": 100,
        "deletion_confirmation_message": "Archive this API resource?",
        "activation_enabled": True,
        "deactivation_enabled": True,
        "health_cache_ttl_seconds": 10,
        "table_skeleton_rows": 5,
        "form_description_rows": 4,
        "feature_enabled": True,
        "rollout_percentage": 100,
        "rollout_roles": [],
        "rollout_cohorts": [],
        "allowed_resource_config_keys": [],
    }
    configuration = Configuration.objects.create(
        tenant_id=tenant_id,
        document=legacy_document,
        version=1,
        updated_by="actor",
    )
    ConfigurationVersion.objects.create(
        tenant_id=tenant_id,
        version=1,
        document=legacy_document,
        actor_id="actor",
        correlation_id="migration-test",
        idempotency_key=uuid.uuid4(),
        reason="bootstrap",
    )

    executor = MigrationExecutor(connection)
    executor.migrate([("api_management", "0003_environment_and_resource_versions")])
    environment_apps = executor.loader.project_state(
        [("api_management", "0003_environment_and_resource_versions")]
    ).apps
    MigratedConfiguration = environment_apps.get_model(
        "api_management",
        "ApiManagementConfiguration",
    )
    ResourceVersion = environment_apps.get_model(
        "api_management",
        "ApiManagementResourceVersion",
    )
    migrated_configuration = MigratedConfiguration.objects.get(pk=configuration.pk)
    assert migrated_configuration.environment == "staging"
    assert migrated_configuration.document["validation_limits"]["page_size_maximum"] == 100
    assert migrated_configuration.document["navigation"]["resources_create"]["order"] == 341
    assert ResourceVersion.objects.filter(
        tenant_id=tenant_id,
        resource_id=resource_id,
    ).exists()

    executor = MigrationExecutor(connection)
    executor.migrate([("api_management", "0002_configuration_governance")])
    restored_apps = executor.loader.project_state([("api_management", "0002_configuration_governance")]).apps
    RestoredConfiguration = restored_apps.get_model(
        "api_management",
        "ApiManagementConfiguration",
    )
    restored_document = RestoredConfiguration.objects.get(pk=configuration.pk).document
    assert restored_document == legacy_document
    MigrationExecutor(connection).migrate([("api_management", "0001_initial")])
