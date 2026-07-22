"""Adapter compatibility, duplication, and transformation safety tests."""

import pytest
from django.core.exceptions import ValidationError

from src.core.api.results import OperationResult

from ..adapter_registry import AdapterUnavailableError, ConnectorAdapterRegistry, DuplicateAdapterError, transformation_registry
from ..adapters import AdapterDescriptor, ConnectorAdapter, RecordBatch

pytest_plugins = ["src.core.testing"]


class Adapter(ConnectorAdapter):
    descriptor = AdapterDescriptor("tests.adapter", "1.0.0", frozenset({"test"}))

    def validate_config(self, config): return OperationResult.succeeded(dict(config), evidence={"valid": True})
    def test_connection(self, config, credential): return OperationResult.succeeded(True, evidence={"probe": True})
    def pull(self, config, credential, cursor, limit): return OperationResult.unavailable(capability="pull")
    def push(self, config, credential, records, idempotency_key): return OperationResult.unavailable(capability="push")
    def health(self): return OperationResult.succeeded({"status": "healthy"}, evidence={"probe": True})


def test_descriptor_fingerprint_is_stable_and_spi_is_fail_closed():
    first = Adapter().descriptor
    second = AdapterDescriptor(first.key, first.implementation_version, first.capabilities)
    assert first.fingerprint == second.fingerprint
    with pytest.raises(ValueError):
        AdapterDescriptor("tests.bad", "1", frozenset({"test"}), spi_version="99")


def test_duplicate_registration_and_orphan_reason():
    registry = ConnectorAdapterRegistry()
    adapter = Adapter()
    registry.register(adapter.descriptor.key, adapter)
    with pytest.raises(DuplicateAdapterError):
        registry.register(adapter.descriptor.key, adapter)
    registry.unregister(adapter.descriptor.key, reason="module_uninstalled")
    with pytest.raises(AdapterUnavailableError) as exc:
        registry.get(adapter.descriptor.key)
    assert exc.value.reason == "module_uninstalled"


def test_record_batch_requires_explicit_zero_source_evidence():
    with pytest.raises(ValueError):
        RecordBatch(())
    assert RecordBatch((), source_exhausted=True).source_count == 0


def test_unknown_or_executable_transformations_are_rejected():
    for specification in (
        {"operation": "python", "options": {"code": "import os"}},
        {"operation": "trim", "code": "value.strip()"},
    ):
        with pytest.raises(ValidationError):
            transformation_registry.validate(specification)
