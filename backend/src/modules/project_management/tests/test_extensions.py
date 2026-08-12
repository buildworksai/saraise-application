"""Project extension SPI contract tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.modules.project_management.extensions import (
    ExtensionRegistry,
    ExtensionResult,
    ProjectDetailPanel,
    ProjectExtensionContext,
    registry,
)


def test_extension_result_unavailable_uses_stable_default_code():
    result = ExtensionResult.unavailable()

    assert result.status == "unavailable"
    assert result.data is None
    assert result.code == "PROVIDER_UNAVAILABLE"
    assert ExtensionResult.unavailable("SCHEDULER_DOWN").code == "SCHEDULER_DOWN"


def test_project_extension_context_and_detail_panel_are_immutable_contracts():
    context = ProjectExtensionContext(
        tenant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        project_version=7,
        actor_id=uuid.uuid4(),
        correlation_id="corr-123",
    )
    panel = ProjectDetailPanel(
        key="cost.forecast",
        title="Cost Forecast",
        slot="details",
        module="project_management",
        permission="project.read",
        entitlement="project.costing",
    )

    assert context.project_version == 7
    assert panel.minimum_spi_version == "1.0"
    with pytest.raises(AttributeError):
        context.project_version = 8  # type: ignore[misc]
    with pytest.raises(AttributeError):
        panel.title = "Changed"  # type: ignore[misc]


def test_extension_registry_registers_orders_retrieves_and_clears_providers():
    extensions = ExtensionRegistry()
    late = SimpleNamespace(key="zeta")
    early = SimpleNamespace(key="alpha")

    assert extensions.register(late) is late
    assert extensions.register(early) is early
    assert extensions.get("alpha") is early
    assert extensions.get("missing") is None
    assert extensions.all() == (early, late)

    extensions.clear()
    assert extensions.all() == ()


def test_extension_registry_rejects_blank_and_duplicate_keys():
    extensions = ExtensionRegistry()

    with pytest.raises(ValueError, match="key is required"):
        extensions.register(SimpleNamespace(key=" "))

    extensions.register(SimpleNamespace(key="capacity"))
    with pytest.raises(ValueError, match="Duplicate extension provider key"):
        extensions.register(SimpleNamespace(key="capacity"))


def test_global_registry_can_be_cleared_between_plugin_lifecycles():
    provider = SimpleNamespace(key="temporary")
    registry.clear()

    registry.register(provider)
    assert registry.get("temporary") is provider

    registry.clear()
    assert registry.get("temporary") is None
