from __future__ import annotations

import time
import uuid

import pytest

from src.core.resilience.circuit_breaker import CircuitOpenError
from src.modules.compliance_management.extension_contracts import (
    CollectedEvidence,
    ComplianceExtensionRegistry,
    EvidenceCollectionRequest,
    EvidenceCollectionResult,
    ExtensionAdapterFailure,
    ExtensionCircuitOpen,
    ExtensionDescriptor,
    ExtensionEntitlementDenied,
    ExtensionKind,
    ExtensionRegistrationCollision,
    ExtensionUnavailable,
)


def request() -> EvidenceCollectionRequest:
    return EvidenceCollectionRequest(
        tenant_id=uuid.uuid4(),
        correlation_id=str(uuid.uuid4()),
        actor_id=str(uuid.uuid4()),
        idempotency_key=str(uuid.uuid4()),
        parameters={"requirement_code": "ISO-A.1"},
    )


class Collector:
    descriptor = ExtensionDescriptor(
        identifier="vendor.compliance.collector",
        kind=ExtensionKind.EVIDENCE_COLLECTOR,
        version="1.2.0",
        required_entitlement="vendor.compliance.collector",
    )

    def collect(self, context, collection_request):
        assert context.tenant_id == collection_request.tenant_id
        return EvidenceCollectionResult(
            extension_id=self.descriptor.identifier,
            extension_version=self.descriptor.version,
            input_digest="a" * 64,
            evidence=(
                CollectedEvidence(
                    stable_key="evidence-1",
                    evidence_type="report",
                    reference_kind="text_reference",
                    reference="Provider assertion 1",
                ),
            ),
        )


def test_registration_and_real_collection_result():
    registry = ComplianceExtensionRegistry(
        entitlement_checker=lambda tenant, entitlement: True,
        http_client_factory=lambda descriptor: None,
    )
    registry.register(Collector())

    result = registry.collect_evidence(Collector.descriptor.identifier, request())

    assert result.evidence[0].stable_key == "evidence-1"
    assert registry.identifiers() == (Collector.descriptor.identifier,)


def test_registration_collision_is_rejected():
    registry = ComplianceExtensionRegistry()
    registry.register(Collector())
    with pytest.raises(ExtensionRegistrationCollision):
        registry.register(Collector())


def test_missing_extension_is_explicitly_unavailable():
    registry = ComplianceExtensionRegistry()
    with pytest.raises(ExtensionUnavailable):
        registry.collect_evidence("vendor.missing.collector", request())


def test_entitlement_denial_prevents_adapter_execution():
    called = False

    class TrackingCollector(Collector):
        def collect(self, context, collection_request):
            nonlocal called
            called = True
            return super().collect(context, collection_request)

    registry = ComplianceExtensionRegistry(entitlement_checker=lambda tenant, entitlement: False)
    registry.register(TrackingCollector())
    with pytest.raises(ExtensionEntitlementDenied):
        registry.collect_evidence(Collector.descriptor.identifier, request())
    assert called is False


def test_adapter_failure_is_sanitized_and_never_fabricates_success():
    class FailedCollector(Collector):
        def collect(self, context, collection_request):
            raise RuntimeError("provider secret response")

    registry = ComplianceExtensionRegistry(entitlement_checker=lambda tenant, entitlement: True)
    registry.register(FailedCollector())
    with pytest.raises(ExtensionAdapterFailure) as captured:
        registry.collect_evidence(Collector.descriptor.identifier, request())
    assert "provider secret response" not in str(captured.value)


def test_circuit_open_failure_remains_distinct():
    class OpenCircuitCollector(Collector):
        def collect(self, context, collection_request):
            raise CircuitOpenError("vendor-api", time.monotonic() + 10)

    registry = ComplianceExtensionRegistry(entitlement_checker=lambda tenant, entitlement: True)
    registry.register(OpenCircuitCollector())
    with pytest.raises(ExtensionCircuitOpen):
        registry.collect_evidence(Collector.descriptor.identifier, request())


def test_successful_collection_cannot_be_empty():
    with pytest.raises(ValueError):
        EvidenceCollectionResult(
            extension_id="vendor.compliance.collector",
            extension_version="1.0.0",
            input_digest="b" * 64,
            evidence=(),
        )
