"""Tenant configuration isolation, validation, versioning, and rollback proof."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import yaml
from django.core.exceptions import ValidationError

from src.modules.automation_orchestration.api import (
    ConfigurationViewSet,
    DefinitionViewSet,
    EdgeViewSet,
    NodeViewSet,
    RunViewSet,
    ScheduleViewSet,
    TaskRunViewSet,
)
from src.modules.automation_orchestration.models import (
    OrchestrationConfiguration,
    OrchestrationConfigurationAudit,
    OrchestrationConfigurationVersion,
)
from src.modules.automation_orchestration.permissions import SOD_ACTIONS
from src.modules.automation_orchestration.services import (
    DEFAULT_CONFIGURATION,
    ConfigurationService,
    ServiceValidationError,
)
from src.modules.automation_orchestration.urls import router

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "viewset_type",
    (
        ConfigurationViewSet,
        DefinitionViewSet,
        EdgeViewSet,
        NodeViewSet,
        RunViewSet,
        ScheduleViewSet,
        TaskRunViewSet,
    ),
)
def test_every_tenant_viewset_fails_closed_without_tenant_context(viewset_type) -> None:
    assert not viewset_type().get_queryset().exists()


def _write(tenant_id: uuid.UUID, actor_id: uuid.UUID, timeout: int, correlation_id: str):
    document = ConfigurationService.validate_document(DEFAULT_CONFIGURATION)
    document["defaults"]["timeout_seconds"] = timeout
    return ConfigurationService.update(
        tenant_id,
        actor_id,
        correlation_id,
        {"document": document, "enabled": True, "rollout_percentage": 100, "allowed_roles": []},
        environment="development",
    )


def test_configuration_is_tenant_isolated_and_versioned() -> None:
    tenant_a, tenant_b, actor = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first = _write(tenant_a, actor, 30, "config-a-v1")
    _write(tenant_b, actor, 90, "config-b-v1")
    second = _write(tenant_a, actor, 45, "config-a-v2")

    assert first.id == second.id
    assert ConfigurationService.effective_document(tenant_a)["defaults"]["timeout_seconds"] == 45
    assert ConfigurationService.effective_document(tenant_b)["defaults"]["timeout_seconds"] == 90
    assert OrchestrationConfiguration.objects.for_tenant(tenant_a).count() == 1
    assert OrchestrationConfigurationVersion.objects.for_tenant(tenant_a).count() == 2
    assert OrchestrationConfigurationAudit.objects.for_tenant(tenant_a).count() == 2
    assert not OrchestrationConfiguration.objects.for_tenant(tenant_a).filter(tenant_id=tenant_b).exists()


def test_configuration_validation_makes_unsafe_values_unsaveable() -> None:
    unsafe = ConfigurationService.validate_document(DEFAULT_CONFIGURATION)
    unsafe["defaults"]["timeout_seconds"] = unsafe["limits"]["timeout_seconds_max"] + 1
    with pytest.raises(ServiceValidationError, match="outside configured limits"):
        ConfigurationService.validate_document(unsafe)


def test_configuration_rolls_back_to_any_prior_version_and_evidence_is_immutable() -> None:
    tenant, actor = uuid.uuid4(), uuid.uuid4()
    configuration = _write(tenant, actor, 30, "config-v1")
    _write(tenant, actor, 60, "config-v2")
    prior = configuration.versions.get(version=1)

    rolled_back = ConfigurationService.rollback(
        tenant,
        actor,
        "config-rollback",
        version_number=prior.version,
        environment="development",
    )

    assert rolled_back.version == 3
    assert ConfigurationService.effective_document(tenant)["defaults"]["timeout_seconds"] == 30
    latest = rolled_back.versions.get(version=3)
    assert latest.rollback_of_id == prior.id
    with pytest.raises(ValidationError, match="immutable"):
        OrchestrationConfigurationVersion.objects.for_tenant(tenant).update(correlation_id="tampered")
    with pytest.raises(ValidationError, match="immutable"):
        OrchestrationConfigurationAudit.objects.for_tenant(tenant).delete()


def test_manifest_declares_sod_model_and_router_inventories() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert tuple(tuple(pair) for pair in manifest["sod_actions"]) == SOD_ACTIONS
    assert {entry["name"] for entry in manifest["entities"]} == {
        "OrchestrationConfiguration",
        "OrchestrationConfigurationVersion",
        "OrchestrationConfigurationAudit",
        "OrchestrationCommand",
        "OrchestrationDefinition",
        "OrchestrationNode",
        "OrchestrationEdge",
        "OrchestrationSchedule",
        "OrchestrationRun",
        "OrchestrationTaskRun",
        "RetryAttempt",
        "OrchestrationReconciliation",
        "OrchestrationEvent",
    }
    assert {prefix for prefix, _viewset, _basename in router.registry} == {
        "configuration",
        "definitions",
        "nodes",
        "edges",
        "schedules",
        "runs",
        "task-runs",
        "node-types",
    }
