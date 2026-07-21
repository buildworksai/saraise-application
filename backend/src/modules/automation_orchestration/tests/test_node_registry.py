"""Public paid-module node SPI contract tests."""

from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError

import pytest
from django.test import override_settings

from ..node_registry import (
    DuplicateNodeRegistration,
    NodeDescriptor,
    NodeExecutionContext,
    NodeExecutionResult,
    NodeReplacementForbidden,
    NodeResultStatus,
    execute_registered_node,
    list_node_catalog,
    register_node,
    unregister_node,
)


def _descriptor(key: str, *, source_module: str = "test_extension", capability: str = "test.execute"):
    schema = {"type": "object", "additionalProperties": True}
    return NodeDescriptor(
        key=key,
        display_name="Test node",
        category="Tests",
        description="Typed test extension",
        configuration_schema={"type": "object", "additionalProperties": False},
        input_schema=schema,
        output_schema=schema,
        icon_key="test",
        capability=capability,
        source_module=source_module,
    )


def _context(descriptor: NodeDescriptor) -> NodeExecutionContext:
    return NodeExecutionContext(
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        task_run_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        input={"value": 1},
        validated_config={},
        cancellation_probe=lambda: False,
        operation_token=str(uuid.uuid4()),
        delivery_token=str(uuid.uuid4()),
        handler_key=descriptor.key,
        descriptor_version=descriptor.contract_version,
        request_fingerprint="a" * 64,
    )


def test_descriptor_is_immutable_and_registration_rejects_duplicates() -> None:
    descriptor = _descriptor(f"test.{uuid.uuid4()}")
    register_node(descriptor, lambda context: NodeExecutionResult.success(dict(context.input)))
    try:
        with pytest.raises(FrozenInstanceError):
            descriptor.key = "changed"  # type: ignore[misc]
        with pytest.raises(DuplicateNodeRegistration):
            register_node(descriptor, lambda context: NodeExecutionResult.success())
    finally:
        unregister_node(descriptor.key)


def test_executor_output_is_schema_validated_and_invalid_contract_fails_explicitly() -> None:
    descriptor = _descriptor(f"test.{uuid.uuid4()}")
    register_node(descriptor, lambda context: {"fabricated": True})  # type: ignore[arg-type]
    try:
        result = execute_registered_node(_context(descriptor))
        assert result.status == NodeResultStatus.FAILED
        assert result.error_code == "INVALID_EXECUTOR_RESULT"
    finally:
        unregister_node(descriptor.key)


def test_executor_exception_and_cancellation_are_explicit_failures() -> None:
    descriptor = _descriptor(f"test.{uuid.uuid4()}")

    def explode(context: NodeExecutionContext) -> NodeExecutionResult:
        del context
        raise RuntimeError("private detail")

    register_node(descriptor, explode)
    try:
        failed = execute_registered_node(_context(descriptor))
        assert failed.error_code == "NODE_EXECUTOR_EXCEPTION"
        assert "private detail" not in failed.error_message

        context = _context(descriptor)
        cancelled_context = NodeExecutionContext(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            task_run_id=context.task_run_id,
            attempt_id=context.attempt_id,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            input=context.input,
            validated_config=context.validated_config,
            cancellation_probe=lambda: True,
            operation_token=context.operation_token,
            delivery_token=context.delivery_token,
            handler_key=context.handler_key,
            descriptor_version=context.descriptor_version,
            request_fingerprint=context.request_fingerprint,
        )
        assert execute_registered_node(cancelled_context).error_code == "EXECUTION_CANCELLED"
        assert cancelled_context.idempotency_token == context.operation_token
    finally:
        unregister_node(descriptor.key)


@override_settings(DEBUG=False)
def test_production_replacement_is_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARAISE_MODE", "saas")
    descriptor = _descriptor(f"test.{uuid.uuid4()}")
    register_node(descriptor, lambda context: NodeExecutionResult.success(dict(context.input)))
    try:
        with pytest.raises(NodeReplacementForbidden):
            register_node(
                descriptor,
                lambda context: NodeExecutionResult.success(dict(context.input)),
                replace=True,
            )
    finally:
        unregister_node(descriptor.key)


def test_missing_or_version_mismatched_handler_is_unavailable() -> None:
    descriptor = _descriptor(f"test.{uuid.uuid4()}")
    missing = execute_registered_node(_context(descriptor))
    assert missing.status == NodeResultStatus.UNAVAILABLE
    assert missing.error_code == "NODE_HANDLER_MISSING"

    register_node(descriptor, lambda context: NodeExecutionResult.success(dict(context.input)))
    try:
        context = _context(descriptor)
        mismatched = NodeExecutionContext(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            task_run_id=context.task_run_id,
            attempt_id=context.attempt_id,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            input=context.input,
            validated_config=context.validated_config,
            cancellation_probe=context.cancellation_probe,
            operation_token=context.operation_token,
            delivery_token=context.delivery_token,
            handler_key=context.handler_key,
            descriptor_version="1.0:old:1",
            request_fingerprint=context.request_fingerprint,
        )
        assert execute_registered_node(mismatched).error_code == "NODE_VERSION_MISMATCH"
    finally:
        unregister_node(descriptor.key)


def test_catalog_discovery_does_not_grant_execution_access() -> None:
    descriptor = _descriptor(f"paid.{uuid.uuid4()}", source_module="paid_industry")
    register_node(descriptor, lambda context: NodeExecutionResult.success(dict(context.input)))
    try:
        setup = {item.key: item for item in list_node_catalog({"modules": (), "capabilities": ()})}
        assert setup[descriptor.key].availability == "setup_required"
        locked = {item.key: item for item in list_node_catalog({"modules": ("paid_industry",), "capabilities": ()})}
        assert locked[descriptor.key].availability == "locked"
        available = {
            item.key: item
            for item in list_node_catalog({"modules": ("paid_industry",), "capabilities": ("test.execute",)})
        }
        assert available[descriptor.key].availability == "available"
    finally:
        unregister_node(descriptor.key)
