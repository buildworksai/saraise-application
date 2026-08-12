from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from django.core.exceptions import ImproperlyConfigured, ValidationError

from src.core.api.results import OperationResult

from ..adapter_registry import (
    AdapterUnavailableError,
    ConnectorAdapterRegistry,
    DuplicateAdapterError,
    TransformationRegistry,
    transformation_registry,
)
from ..adapters import AdapterDescriptor, ConnectorAdapter, PushEvidence, RecordBatch


class RegistryAdapter(ConnectorAdapter):
    def __init__(self, key: str = "registry-adapter") -> None:
        self.descriptor = AdapterDescriptor(key, "1.0.0", frozenset({"test", "pull", "push"}))

    def validate_config(self, config):
        return OperationResult.succeeded(dict(config))

    def test_connection(self, config, credential):
        return OperationResult.succeeded({"connected": True})

    def pull(self, config, credential, cursor, limit):
        return OperationResult.succeeded(RecordBatch((), source_exhausted=True, source_count=0))

    def push(self, config, credential, records, idempotency_key):
        return OperationResult.succeeded(PushEvidence(len(records), 0, idempotency_key))

    def health(self):
        return OperationResult.succeeded({"status": "healthy"})


def test_connector_registry_tracks_uninstall_reason_and_rejects_bad_registration() -> None:
    registry = ConnectorAdapterRegistry()
    adapter = RegistryAdapter()

    assert registry.register(adapter.descriptor.key, adapter) is adapter
    assert registry.is_registered(adapter.descriptor.key)
    assert registry.availability_reason(adapter.descriptor.key) == "available"
    assert registry.catalog() == (adapter.descriptor,)

    with pytest.raises(DuplicateAdapterError):
        registry.register(adapter.descriptor.key, adapter)
    with pytest.raises(ValueError):
        registry.register("mismatch", adapter)
    with pytest.raises(TypeError):
        registry.register("bad", object())  # type: ignore[arg-type]

    removed = registry.unregister(adapter.descriptor.key, reason="module_disabled")
    assert removed is adapter
    with pytest.raises(AdapterUnavailableError) as exc:
        registry.get(adapter.descriptor.key)
    assert exc.value.reason == "module_disabled"
    registry.clear()
    assert registry.catalog() == ()


def test_transformation_registry_validates_bounded_dsl_and_applies_supported_operations() -> None:
    assert transformation_registry.apply(" alpha ", {"operation": "trim", "options": {}}) == "alpha"
    assert transformation_registry.apply("alpha", {"operation": "string_case", "options": {"case": "title"}}) == "Alpha"
    assert transformation_registry.apply("42.5", {"operation": "number", "options": {"type": "float"}}) == 42.5
    assert transformation_registry.apply("42", {"operation": "number", "options": {"type": "integer"}}) == 42
    assert transformation_registry.apply("42.50", {"operation": "number", "options": {"type": "decimal"}}) == "42.50"
    assert (
        transformation_registry.apply(
            "2026-08-03",
            {"operation": "date_format", "options": {"input_format": "%Y-%m-%d", "output_format": "%d/%m/%Y"}},
        )
        == "03/08/2026"
    )
    assert (
        transformation_registry.apply(
            datetime(2026, 8, 3),
            {"operation": "date_format", "options": {"output_format": "%Y%m%d"}},
        )
        == "20260803"
    )
    assert transformation_registry.apply("", {"operation": "default", "options": {"value": "fallback"}}) == "fallback"
    assert (
        transformation_registry.apply(
            "A",
            {"operation": "enum_map", "options": {"mapping": {"A": "approved"}}},
        )
        == "approved"
    )
    assert (
        transformation_registry.apply(
            "B",
            {"operation": "enum_map", "options": {"mapping": {}, "allow_unmapped": True}},
        )
        == "B"
    )


@pytest.mark.parametrize(
    "specification",
    [
        "not-a-transform",
        {"operation": "unknown", "options": {}},
        {"operation": "string_case", "options": {"case": "unsupported"}},
        {"operation": "number", "options": {"type": "complex"}},
        {"operation": "date_format", "options": {}},
        {"operation": "enum_map", "options": {}},
        {"operation": "trim", "options": [], "extra": True},
        [{"operation": "trim", "options": {}}] * 21,
    ],
)
def test_transformation_registry_rejects_unsafe_or_invalid_specs(specification: object) -> None:
    with pytest.raises(ValidationError):
        transformation_registry.validate(specification)


def test_custom_transformation_registry_registration_guards() -> None:
    registry = TransformationRegistry()
    with pytest.raises(ValueError):
        registry.register("", lambda value, options: value)
    with pytest.raises(ValueError):
        registry.register("bad", object())  # type: ignore[arg-type]

    registry.register("identity", lambda value, options: (value, dict(options)))
    with pytest.raises(ImproperlyConfigured):
        registry.register("identity", lambda value, options: value)
    assert registry.apply(uuid.UUID(int=1), {"operation": "identity", "options": {"seen": True}}) == (
        uuid.UUID(int=1),
        {"seen": True},
    )
