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

    MigrationExecutor(connection).migrate([("api_management", "0002_configuration_governance")])
