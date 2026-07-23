"""Tenant configuration contract, history, portability, and fail-closed tests."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from rest_framework import status

from src.core.access.permissions import RequiresAccess
from src.modules.ai_agent_management.models import (
    AgentManagementConfiguration,
    AgentManagementConfigurationVersion,
)
from src.modules.ai_agent_management.services import ConfigurationService
from src.modules.ai_agent_management.urls import router


@pytest.mark.django_db
def test_configuration_versions_export_import_and_rollback_are_immutable(tenant_id, actor_id):
    bootstrap_correlation = uuid4()
    current = ConfigurationService.current(tenant_id, actor_id, bootstrap_correlation)
    assert current.version == 1
    bootstrap = AgentManagementConfigurationVersion.objects.get(
        tenant_id=tenant_id,
        environment="production",
        version=1,
    )
    assert bootstrap.changed_by == actor_id
    assert bootstrap.correlation_id == bootstrap_correlation

    changed = ConfigurationService.defaults()
    changed["provider"]["max_tokens"] = 8192
    update_correlation = uuid4()
    updated = ConfigurationService.replace(
        tenant_id,
        actor_id,
        update_correlation,
        changed,
        expected_version=1,
    )
    assert updated.version == 2
    history = AgentManagementConfigurationVersion.objects.get(
        tenant_id=tenant_id,
        environment="production",
        version=2,
    )
    assert history.previous_document["provider"]["max_tokens"] != 8192
    assert history.document["provider"]["max_tokens"] == 8192
    assert history.correlation_id == update_correlation

    exported = ConfigurationService.export_document(tenant_id, actor_id, uuid4())
    assert exported["schema"] == "saraise.ai-agent-management.configuration/v1"
    assert exported["configuration"] == changed

    rolled_back = ConfigurationService.rollback(tenant_id, actor_id, uuid4(), 1)
    assert rolled_back.version == 3
    assert rolled_back.document == ConfigurationService.defaults()

    with pytest.raises(ValidationError):
        history.save()
    with pytest.raises(ValidationError):
        AgentManagementConfigurationVersion.objects.filter(pk=history.pk).update(version=99)
    with pytest.raises(ValidationError):
        AgentManagementConfigurationVersion.objects.filter(pk=history.pk).delete()


@pytest.mark.django_db
def test_configuration_rejects_unsafe_and_cross_tenant_values(tenant_id, other_tenant_id, actor_id):
    current = ConfigurationService.current(tenant_id, actor_id, uuid4())
    foreign = ConfigurationService.current(other_tenant_id, uuid4(), uuid4())
    unsafe = ConfigurationService.defaults()
    unsafe["egress"]["forbidden_ip_addresses"].remove("169.254.169.254")
    with pytest.raises(ValidationError):
        ConfigurationService.replace(
            tenant_id,
            actor_id,
            uuid4(),
            unsafe,
            expected_version=current.version,
        )
    invalid_graph = ConfigurationService.defaults()
    invalid_graph["agent"]["execution_state_transitions"]["completed"] = ["running"]
    with pytest.raises(ValidationError):
        ConfigurationService.validate_document(invalid_graph)
    current.refresh_from_db()
    foreign.refresh_from_db()
    assert current.version == 1
    assert foreign.version == 1
    assert current.id != foreign.id


@pytest.mark.django_db
def test_configuration_api_is_typed_and_tenant_scoped(
    authenticated_tenant_a_client,
    tenant_a,
    monkeypatch,
):
    monkeypatch.setattr(RequiresAccess, "has_permission", lambda self, request, view: True)
    monkeypatch.setattr(RequiresAccess, "has_object_permission", lambda self, request, view, obj: True)
    response = authenticated_tenant_a_client.get(
        "/api/v2/ai-agent-management/configuration/?environment=production"
    )
    assert response.status_code == status.HTTP_200_OK
    current = response.json()["data"]
    document = current["document"]
    document["ui"]["agent_page_size"] = 50
    update = authenticated_tenant_a_client.post(
        "/api/v2/ai-agent-management/configuration/",
        {
            "environment": "production",
            "expected_version": current["version"],
            "document": document,
        },
        format="json",
    )
    assert update.status_code == status.HTTP_200_OK
    assert update.json()["data"]["document"]["ui"]["agent_page_size"] == 50
    assert AgentManagementConfiguration.objects.filter(tenant_id=tenant_a.id).count() == 1


@pytest.mark.django_db
def test_every_registered_tenant_queryset_is_empty_without_tenant_context():
    request = SimpleNamespace(user=AnonymousUser(), query_params={})
    for prefix, viewset_type, _basename in router.registry:
        viewset = viewset_type()
        viewset.request = request
        viewset.action = "list"
        queryset = viewset.get_queryset()
        assert not queryset.exists(), prefix
