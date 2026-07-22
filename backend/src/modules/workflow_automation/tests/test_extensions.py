"""Extension SPI registration, version pinning, and built-in behavior tests."""

from __future__ import annotations

import uuid

import pytest

from ..extensions import (
    ContextProjectionAction,
    DuplicateWorkflowExtension,
    WorkflowActionInvocation,
    action_registry,
    condition_registry,
    execute_registered_action,
)


def _invocation(handler_key: str, *, config: dict[str, object], input_data: dict[str, object]) -> WorkflowActionInvocation:
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


def test_missing_action_handler_is_explicitly_unavailable() -> None:
    result = execute_registered_action(_invocation("missing.industry.action.v1", config={}, input_data={}))
    assert result.status == "unavailable"
    assert result.error_code == "CAPABILITY_UNAVAILABLE"
    assert result.http_status == 503


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
