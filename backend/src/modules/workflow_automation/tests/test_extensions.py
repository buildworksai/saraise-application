"""Extension SPI registration, version pinning, and built-in behavior tests."""

from __future__ import annotations

import uuid

import pytest
from django.test import override_settings

from src.core.api.results import OperationResult

from ..extensions import (
    ActionDescriptor,
    AssigneeProviderDescriptor,
    AssigneeSearchInvocation,
    ConditionDescriptor,
    ContextProjectionAction,
    DuplicateWorkflowExtension,
    EntityReferenceSubjectResolver,
    LookupDescriptor,
    SubjectResolutionInvocation,
    SubjectResolverDescriptor,
    VersionedRegistry,
    WorkflowActionInvocation,
    WorkflowExtensionContractError,
    WorkflowExtensionNotFound,
    WorkflowExtensionReplacementForbidden,
    action_registry,
    assignee_registry,
    condition_registry,
    execute_registered_action,
    subject_registry,
)


def _invocation(
    handler_key: str, *, config: dict[str, object], input_data: dict[str, object]
) -> WorkflowActionInvocation:
    handler = action_registry.get(handler_key) if handler_key in action_registry.keys() else None
    descriptor_version = handler.descriptor.contract_version if handler else "1.0"
    descriptor_fingerprint = handler.descriptor.contract_fingerprint if handler else "missing"
    return WorkflowActionInvocation(
        tenant_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        instance_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        actor_id="actor",
        correlation_id=str(uuid.uuid4()),
        idempotency_key=f"operation:{uuid.uuid4()}",
        handler_key=handler_key,
        descriptor_version=descriptor_version,
        descriptor_fingerprint=descriptor_fingerprint,
        config=config,
        input=input_data,
        cancellation_probe=lambda: False,
    )


def test_builtin_catalog_has_complete_oss_actions_and_conditions() -> None:
    assert {
        "core.in_app_notification.v1",
        "core.email_notification.v1",
        "core.context_projection.v1",
        "core.terminal_completion.v1",
    }.issubset(action_registry.keys())
    assert {"core.equals.v1", "core.truthy.v1"}.issubset(condition_registry.keys())


def test_duplicate_registration_is_rejected_without_explicit_replacement() -> None:
    with pytest.raises(DuplicateWorkflowExtension):
        action_registry.register(ContextProjectionAction())


def test_registry_catalog_marks_non_core_capability_availability_by_access_context() -> None:
    registry: VersionedRegistry[ContextProjectionAction, ActionDescriptor] = VersionedRegistry("test action")
    descriptor = ActionDescriptor(
        key="industry.shipping.allocate.v1",
        display_name="Allocate shipment",
        description="Reserve carrier capacity.",
        category="Shipping",
        owning_module="shipping",
        required_permission="workflow:start",
        required_entitlement="module.shipping",
        quota_resource="workflow",
        quota_cost=1,
        configuration_schema={"type": "object"},
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        idempotency_supported=True,
        outbound_network_required=False,
        icon_key="truck",
    )

    ShippingAction = type("ShippingAction", (ContextProjectionAction,), {"descriptor": descriptor})

    registry.register(ShippingAction())

    assert registry.catalog()[0].availability == "locked"
    assert registry.catalog({"modules": [], "entitlements": []})[0].availability == "setup_required"
    assert (
        registry.catalog({"modules": ["shipping"], "entitlements": [], "unavailable_modules": ["shipping"]})[
            0
        ].availability
        == "unavailable"
    )
    assert registry.catalog({"modules": ["shipping"], "entitlements": []})[0].availability == "locked"
    assert (
        registry.catalog({"modules": ["shipping"], "entitlements": ["module.shipping"]})[0].availability == "available"
    )
    assert registry.unregister("industry.shipping.allocate.v1") is not None
    assert registry.unregister("industry.shipping.allocate.v1") is None


@override_settings(DEBUG=False)
def test_registry_replacement_is_forbidden_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARAISE_MODE", "production")
    registry: VersionedRegistry[ContextProjectionAction, ActionDescriptor] = VersionedRegistry("test action")
    registry.register(ContextProjectionAction())

    with pytest.raises(WorkflowExtensionReplacementForbidden):
        registry.register(ContextProjectionAction(), replace=True)


def test_missing_action_handler_is_explicitly_unavailable() -> None:
    result = execute_registered_action(_invocation("missing.industry.action.v1", config={}, input_data={}))
    assert result.status == "unavailable"
    assert result.error_code == "CAPABILITY_UNAVAILABLE"
    assert result.http_status == 503


def test_descriptor_version_mismatch_never_executes_handler() -> None:
    invocation = _invocation("core.context_projection.v1", config={"input_mapping": {}}, input_data={})
    result = execute_registered_action(
        WorkflowActionInvocation(
            tenant_id=invocation.tenant_id,
            workflow_id=invocation.workflow_id,
            instance_id=invocation.instance_id,
            step_id=invocation.step_id,
            actor_id=invocation.actor_id,
            correlation_id=invocation.correlation_id,
            idempotency_key=invocation.idempotency_key,
            handler_key=invocation.handler_key,
            descriptor_version="old:contract:1",
            descriptor_fingerprint=invocation.descriptor_fingerprint,
            config=invocation.config,
            input=invocation.input,
            cancellation_probe=lambda: False,
        )
    )
    assert result.status == "unavailable"
    assert result.error_code == "CAPABILITY_UNAVAILABLE"


def test_contract_fingerprint_mismatch_never_executes_handler() -> None:
    invocation = _invocation(
        "core.context_projection.v1",
        config={"input_mapping": {"order_number": "order.number"}},
        input_data={"order": {"number": "SO-100"}},
    )
    invocation = WorkflowActionInvocation(
        tenant_id=invocation.tenant_id,
        workflow_id=invocation.workflow_id,
        instance_id=invocation.instance_id,
        step_id=invocation.step_id,
        actor_id=invocation.actor_id,
        correlation_id=invocation.correlation_id,
        idempotency_key=invocation.idempotency_key,
        handler_key=invocation.handler_key,
        descriptor_version=invocation.descriptor_version,
        descriptor_fingerprint="changed-contract",
        config=invocation.config,
        input=invocation.input,
        cancellation_probe=lambda: False,
    )
    result = execute_registered_action(invocation)
    assert result.status == "unavailable"
    assert result.value is None


def test_context_projection_returns_real_output_and_evidence() -> None:
    result = execute_registered_action(
        _invocation(
            "core.context_projection.v1",
            config={"input_mapping": {"order_number": "order.number"}},
            input_data={"order": {"number": "SO-100"}},
        )
    )
    assert result.status == "succeeded"
    assert result.value == {"order_number": "SO-100"}
    assert result.evidence["projected_fields"] == 1


def test_context_projection_missing_path_returns_structured_failure() -> None:
    result = execute_registered_action(
        _invocation(
            "core.context_projection.v1",
            config={"input_mapping": {"order_number": "order.number"}},
            input_data={"order": {}},
        )
    )

    assert result.status == "failed"
    assert result.error_code == "CONTEXT_PATH_MISSING"
    assert result.detail == {"path": "order.number"}


def test_terminal_completion_and_email_actions_return_governed_results() -> None:
    terminal = execute_registered_action(_invocation("core.terminal_completion.v1", config={}, input_data={}))
    assert terminal.status == "succeeded"
    assert terminal.value == {"completed": True}
    assert terminal.evidence["terminal_marker"]

    email = execute_registered_action(
        _invocation(
            "core.email_notification.v1",
            config={"template_key": "approval"},
            input_data={"recipient_email": "ops@example.com", "template_context": {"order": "SO-100"}},
        )
    )
    assert email.status == "unavailable"
    assert email.error_code == "CAPABILITY_UNAVAILABLE"


def test_extension_descriptors_validate_contract_shape_and_immutable_schemas() -> None:
    with pytest.raises(WorkflowExtensionContractError, match="quota_cost cannot be negative"):
        ActionDescriptor(
            key="industry.bad.v1",
            display_name="Bad",
            description="Invalid quota",
            category="Test",
            owning_module="industry",
            required_permission="workflow:start",
            required_entitlement="industry.bad",
            quota_resource="workflow",
            quota_cost=-1,
            configuration_schema={"type": "object"},
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            idempotency_supported=True,
            outbound_network_required=False,
            icon_key="box",
        )

    descriptor = condition_registry.get("core.truthy.v1").descriptor
    with pytest.raises(TypeError):
        descriptor.condition_schema["type"] = "array"
    with pytest.raises(TypeError):
        descriptor.condition_schema.pop("type")
    with pytest.raises(TypeError):
        descriptor.condition_schema.update({"type": "array"})


def test_condition_and_subject_registries_fail_closed_for_missing_keys() -> None:
    with pytest.raises(WorkflowExtensionContractError):
        AssigneeSearchInvocation(uuid.uuid4(), 0)
    with pytest.raises(WorkflowExtensionNotFound, match="No condition handler"):
        condition_registry.get("missing.condition.v1")
    with pytest.raises(WorkflowExtensionNotFound, match="No subject resolver"):
        subject_registry.get("missing.subject.v1")
    with pytest.raises(WorkflowExtensionNotFound, match="No assignee provider"):
        assignee_registry.get("missing.assignee.v1")


def test_builtin_conditions_evaluate_configured_context_paths() -> None:
    equals = condition_registry.get("core.equals.v1")
    equals.validate({"handler": "core.equals.v1", "left_path": "order.status", "right_value": "approved"})
    assert equals.evaluate({"left": "approved", "right": "approved"}) is True
    assert equals.evaluate({"left": "rejected", "right": "approved"}) is False

    truthy = condition_registry.get("core.truthy.v1")
    truthy.validate({"handler": "core.truthy.v1", "value_path": "flags.ready"})
    assert truthy.evaluate({"value": True}) is True
    assert truthy.evaluate({"value": False}) is False

    with pytest.raises(WorkflowExtensionContractError):
        truthy.evaluate({"value": 1})


def test_descriptor_and_invocation_validation_fail_closed_for_bad_contracts() -> None:
    with pytest.raises(WorkflowExtensionContractError, match="canonical"):
        LookupDescriptor(" recipient_id", "core.users.v1", "Recipient")
    with pytest.raises(WorkflowExtensionContractError, match="Unsupported workflow condition SPI"):
        ConditionDescriptor(
            key="industry.condition.v1",
            display_name="Condition",
            description="Condition",
            owning_module="industry",
            required_entitlement="module.industry",
            condition_schema={"type": "object"},
            context_schema={"type": "object"},
            spi_version="999",
        )
    with pytest.raises(WorkflowExtensionContractError, match="entity_types"):
        SubjectResolverDescriptor(
            key="industry.subject.v1",
            display_name="Subject",
            owning_module="industry",
            entity_types=(),
            required_entitlement="module.industry",
        )
    with pytest.raises(WorkflowExtensionContractError, match="assignment_kind"):
        AssigneeProviderDescriptor(
            key="industry.assignee.v1",
            display_name="Assignee",
            owning_module="industry",
            assignment_kind="team",
            required_permission="workflow:read",
            required_entitlement="module.industry",
            result_schema={"type": "object"},
        )
    with pytest.raises(WorkflowExtensionContractError, match="tenant_id must be a UUID"):
        WorkflowActionInvocation(
            tenant_id="not-a-uuid",
            workflow_id=uuid.uuid4(),
            instance_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            actor_id=None,
            correlation_id=str(uuid.uuid4()),
            idempotency_key="idem",
            handler_key="core.context_projection.v1",
            descriptor_version="1",
            descriptor_fingerprint="fingerprint",
            config={},
            input={},
            cancellation_probe=lambda: False,
        )
    with pytest.raises(WorkflowExtensionContractError, match="cancellation_probe must be callable"):
        WorkflowActionInvocation(
            tenant_id=uuid.uuid4(),
            workflow_id=uuid.uuid4(),
            instance_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            actor_id=None,
            correlation_id=str(uuid.uuid4()),
            idempotency_key="idem",
            handler_key="core.context_projection.v1",
            descriptor_version="1",
            descriptor_fingerprint="fingerprint",
            config={},
            input={},
            cancellation_probe=None,
        )


def test_execute_registered_action_normalizes_handler_contract_failures() -> None:
    class BrokenResultAction:
        descriptor = ActionDescriptor(
            key=f"tests.bad-result.{uuid.uuid4().hex}.v1",
            display_name="Bad result",
            description="Returns the wrong type.",
            category="Tests",
            owning_module="workflow_automation",
            required_permission="workflow:start",
            required_entitlement="module.workflow_automation",
            quota_resource="workflow",
            quota_cost=0,
            configuration_schema={"type": "object"},
            input_schema={"type": "object"},
            output_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
            idempotency_supported=True,
            outbound_network_required=False,
            icon_key="test",
        )

        @property
        def key(self) -> str:
            return self.descriptor.key

        @property
        def schema_version(self) -> str:
            return self.descriptor.schema_version

        def validate_config(self, config: dict[str, object]) -> None:
            del config

        def health(self):  # type: ignore[no-untyped-def]
            raise AssertionError("execute_registered_action should not health-check handlers")

        def execute(self, invocation: WorkflowActionInvocation):  # type: ignore[no-untyped-def]
            del invocation
            return {"ok": True}

    class BadOutputAction:
        descriptor = ActionDescriptor(
            key=f"tests.bad-output.{uuid.uuid4().hex}.v1",
            display_name="Bad output",
            description="Returns schema-invalid output.",
            category="Tests",
            owning_module="workflow_automation",
            required_permission="workflow:start",
            required_entitlement="module.workflow_automation",
            quota_resource="workflow",
            quota_cost=0,
            configuration_schema={"type": "object"},
            input_schema={"type": "object"},
            output_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
            idempotency_supported=True,
            outbound_network_required=False,
            icon_key="test",
        )

        @property
        def key(self) -> str:
            return self.descriptor.key

        @property
        def schema_version(self) -> str:
            return self.descriptor.schema_version

        def validate_config(self, config: dict[str, object]) -> None:
            del config

        def health(self):  # type: ignore[no-untyped-def]
            raise AssertionError("execute_registered_action should not health-check handlers")

        def execute(self, invocation: WorkflowActionInvocation) -> OperationResult[dict[str, object]]:
            del invocation
            return OperationResult.succeeded({"ok": "yes"}, evidence={"handler": self.key})

    expectations = (
        (BrokenResultAction(), "ACTION_RESULT_INVALID"),
        (BadOutputAction(), "ACTION_OUTPUT_INVALID"),
    )
    for handler, expected_code in expectations:
        action_registry.register(handler)
        try:
            result = execute_registered_action(_invocation(handler.key, config={}, input_data={}))
            assert result.status == "failed"
            assert result.error_code == expected_code
        finally:
            action_registry.unregister(handler.key)


def test_builtin_subject_resolver_preserves_identity_without_fabricating_resolution() -> None:
    entity_id = uuid.uuid4()
    result = EntityReferenceSubjectResolver().resolve(
        SubjectResolutionInvocation(uuid.uuid4(), "sales_order", entity_id)
    )

    assert result.status == "succeeded"
    assert result.value == {
        "entity_type": "sales_order",
        "entity_id": str(entity_id),
        "display_name": f"sales_order {entity_id}",
        "resolved": False,
    }
    assert result.evidence == {"identity_preserved": True, "resolver": "core.entity_reference.v1"}
