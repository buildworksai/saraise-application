"""Integration DTO and provider-registry contracts for sales management."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.modules.sales_management import integrations


class _Provider:
    def __init__(self, descriptor: integrations.ProviderDescriptor) -> None:
        self.descriptor = descriptor

    def get_opportunity(
        self,
        tenant_id: uuid.UUID,
        opportunity_id: uuid.UUID,
        correlation_id: uuid.UUID,
    ) -> integrations.GatewayResult[integrations.OpportunitySnapshot]:
        return integrations.GatewayResult.success(
            integrations.OpportunitySnapshot(opportunity_id, None, "usd", None, (), str(correlation_id))
        )

    def check_availability(
        self,
        request: integrations.InventoryAvailabilityRequest,
    ) -> integrations.GatewayResult[integrations.InventoryAvailability]:
        line = integrations.InventoryLineAvailability(
            request.lines[0][0],
            request.lines[0][1],
            request.lines[0][1],
            True,
        )
        return integrations.GatewayResult.success(integrations.InventoryAvailability(True, (line,), "stock-1"))

    def create_invoice(
        self,
        request: integrations.InvoiceRequest,
    ) -> integrations.GatewayResult[integrations.InvoiceResult]:
        return integrations.GatewayResult.success(
            integrations.InvoiceResult(uuid.uuid4(), request.idempotency_key, datetime.now(timezone.utc))
        )

    def calculate_tax(
        self,
        request: integrations.TaxCalculationRequest,
    ) -> integrations.GatewayResult[integrations.TaxCalculation]:
        line = integrations.TaxLineResult(request.lines[0].line_id, Decimal("1.00"), Decimal("0.10"), "US-CA")
        return integrations.GatewayResult.success(
            integrations.TaxCalculation(Decimal("1.00"), (line,), "tax-1", "2026.08")
        )

    def create_shipment(
        self,
        request: integrations.ShipmentRequest,
    ) -> integrations.GatewayResult[integrations.ShipmentResult]:
        return integrations.GatewayResult.success(
            integrations.ShipmentResult(str(request.delivery_note_id), "TRACK-1", "Carrier", datetime.now(timezone.utc))
        )

    def render(
        self,
        request: integrations.DocumentRenderRequest,
    ) -> integrations.GatewayResult[integrations.RenderedDocument]:
        return integrations.GatewayResult.success(
            integrations.RenderedDocument(uuid.uuid4(), "application/pdf", b"pdf", "a" * 64, datetime.now(timezone.utc))
        )

    def dispatch(
        self,
        request: integrations.DocumentDispatchRequest,
    ) -> integrations.GatewayResult[integrations.DocumentDispatchResult]:
        return integrations.GatewayResult.success(
            integrations.DocumentDispatchResult("dispatch-1", datetime.now(timezone.utc), request.idempotency_key)
        )


def _descriptor(
    provider_id: str,
    *capabilities: integrations.Capability,
    priority: int = 100,
    configured: bool = True,
    entitlement: str | None = None,
) -> integrations.ProviderDescriptor:
    return integrations.ProviderDescriptor(
        provider_id=provider_id,
        provider_version="1.0.0",
        capabilities=capabilities or (integrations.Capability.INVENTORY_AVAILABILITY,),
        priority=priority,
        configured=configured,
        required_entitlement=entitlement,
    )


def test_gateway_result_requires_exactly_one_outcome_and_non_empty_success() -> None:
    failure = integrations.GatewayResult.unavailable(
        dependency="inventory",
        code=integrations.FailureCode.DEPENDENCY_TIMEOUT,
        message="timed out",
        retryable=True,
    )

    assert failure.succeeded is False
    assert failure.failure is not None
    assert failure.failure.retryable is True
    with pytest.raises(ValueError, match="exactly one"):
        integrations.GatewayResult()
    with pytest.raises(ValueError, match="exactly one"):
        integrations.GatewayResult(value="ok", failure=failure.failure)
    with pytest.raises(ValueError, match="require evidence"):
        integrations.GatewayResult.success(None)


def test_provider_descriptor_rejects_ambiguous_or_incompatible_registration_metadata() -> None:
    capability = integrations.Capability.INVENTORY_AVAILABILITY

    with pytest.raises(ValueError, match="non-empty and unique"):
        integrations.ProviderDescriptor("provider", "1.0.0", ())
    with pytest.raises(ValueError, match="non-empty and unique"):
        integrations.ProviderDescriptor("provider", "1.0.0", (capability, capability))
    with pytest.raises(ValueError, match="major version"):
        integrations.ProviderDescriptor("provider", "1.0.0", (capability,), contract_version="2.0.0")
    with pytest.raises(TypeError, match="priority"):
        integrations.ProviderDescriptor("provider", "1.0.0", (capability,), priority=True)
    with pytest.raises(ValueError, match="required_entitlement"):
        integrations.ProviderDescriptor("provider", "1.0.0", (capability,), required_entitlement=" ")


def test_opportunity_snapshot_freezes_metadata_and_rejects_non_json_values() -> None:
    snapshot = integrations.OpportunitySnapshot(
        uuid.uuid4(),
        uuid.uuid4(),
        "usd",
        date(2026, 8, 3),
        ({"sku": "A", "nested": {"qty": 2}, "tags": ["quoted", "priority"]},),
        " v1 ",
    )

    assert snapshot.currency == "USD"
    assert snapshot.source_version == "v1"
    assert snapshot.line_items[0]["tags"] == ("quoted", "priority")
    with pytest.raises(TypeError, match="JSON-compatible"):
        integrations.OpportunitySnapshot(uuid.uuid4(), None, "usd", None, ({"bad": object()},), "v1")


def test_amount_and_evidence_dtos_enforce_invariants() -> None:
    item_id = uuid.uuid4()

    with pytest.raises(ValueError, match="at least one line"):
        integrations.InventoryAvailabilityRequest(uuid.uuid4(), uuid.uuid4(), None, (), uuid.uuid4())
    with pytest.raises(ValueError, match="quantity must be positive"):
        integrations.InventoryAvailabilityRequest(
            uuid.uuid4(), uuid.uuid4(), None, ((item_id, Decimal("0")),), uuid.uuid4()
        )
    with pytest.raises(ValueError, match="acceptance must match"):
        integrations.InventoryAvailability(
            True,
            (integrations.InventoryLineAvailability(item_id, Decimal("1"), Decimal("0"), False),),
            "evidence",
        )
    with pytest.raises(ValueError, match="tax total"):
        integrations.TaxCalculation(
            Decimal("2.00"),
            (integrations.TaxLineResult(uuid.uuid4(), Decimal("1.00"), Decimal("0.10"), "US-CA"),),
            "tax-ref",
            "v1",
        )
    with pytest.raises(ValueError, match="checksum_sha256"):
        integrations.RenderedDocument(uuid.uuid4(), "application/pdf", b"pdf", "not-hex", datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="content cannot be empty"):
        integrations.RenderedDocument(uuid.uuid4(), "application/pdf", b"", "a" * 64, datetime.now(timezone.utc))


def test_registry_selects_highest_priority_available_provider_and_handles_collisions() -> None:
    registry = integrations.SalesIntegrationRegistry()
    low = _Provider(_descriptor("low", priority=10))
    high = _Provider(_descriptor("high", priority=200))

    registry.register(low)
    registry.register(high)

    assert registry.resolve(uuid.uuid4(), integrations.Capability.INVENTORY_AVAILABILITY) is high
    with pytest.raises(integrations.RegistrationCollision):
        registry.register(_Provider(_descriptor("high")))
    assert registry.unregister("high") == (high,)
    assert registry.resolve(uuid.uuid4(), integrations.Capability.INVENTORY_AVAILABILITY) is low
    assert registry.unregister("missing") == ()


def test_registry_reports_not_installed_not_configured_and_not_entitled_states() -> None:
    tenant_id = uuid.uuid4()
    empty = integrations.SalesIntegrationRegistry()

    not_installed = empty.capability_state(tenant_id, integrations.Capability.SHIPPING)

    assert not_installed.status is integrations.CapabilityStatus.NOT_INSTALLED
    with pytest.raises(integrations.IntegrationUnavailable) as missing:
        empty.resolve(tenant_id, integrations.Capability.SHIPPING)
    assert missing.value.state.reason_code == integrations.FailureCode.NOT_INSTALLED.value

    registry = integrations.SalesIntegrationRegistry(entitlement_checker=lambda tenant, entitlement: False)
    registry.register(_Provider(_descriptor("disabled", configured=False)))
    registry.register(_Provider(_descriptor("paid", entitlement="sales.inventory")))

    disabled = registry.capability_state(tenant_id, integrations.Capability.INVENTORY_AVAILABILITY)

    assert disabled.status is integrations.CapabilityStatus.NOT_CONFIGURED
    assert registry.unregister("disabled")
    denied = registry.capability_state(tenant_id, integrations.Capability.INVENTORY_AVAILABILITY)
    assert denied.status is integrations.CapabilityStatus.NOT_ENTITLED


def test_registry_treats_missing_or_failed_entitlement_authority_as_temporarily_unavailable() -> None:
    tenant_id = uuid.uuid4()
    missing_checker = integrations.SalesIntegrationRegistry()
    missing_checker.register(_Provider(_descriptor("paid", entitlement="sales.inventory")))

    missing_state = missing_checker.capability_state(tenant_id, integrations.Capability.INVENTORY_AVAILABILITY)

    assert missing_state.status is integrations.CapabilityStatus.TEMPORARILY_UNAVAILABLE
    assert missing_state.reason_code == integrations.FailureCode.ENTITLEMENT_AUTHORITY_UNAVAILABLE.value

    failing_checker = integrations.SalesIntegrationRegistry(
        entitlement_checker=lambda tenant, entitlement: (_ for _ in ()).throw(RuntimeError("down"))
    )
    failing_checker.register(_Provider(_descriptor("paid", entitlement="sales.inventory")))

    failed_state = failing_checker.capability_state(tenant_id, integrations.Capability.INVENTORY_AVAILABILITY)

    assert failed_state.status is integrations.CapabilityStatus.TEMPORARILY_UNAVAILABLE
    assert failed_state.reason_code == integrations.FailureCode.ENTITLEMENT_AUTHORITY_UNAVAILABLE.value


def test_registry_uses_availability_resolver_and_rejects_wrong_capability_response() -> None:
    tenant_id = uuid.uuid4()
    provider = _Provider(_descriptor("inventory"))
    unavailable_state = integrations.CapabilityState(
        integrations.Capability.INVENTORY_AVAILABILITY,
        integrations.CapabilityStatus.TEMPORARILY_UNAVAILABLE,
        integrations.FailureCode.DEPENDENCY_UNAVAILABLE.value,
        "inventory",
        "1.0.0",
    )
    registry = integrations.SalesIntegrationRegistry(
        availability_resolver=lambda tenant, descriptor, capability: unavailable_state
    )
    registry.register(provider)

    state = registry.capability_state(tenant_id, integrations.Capability.INVENTORY_AVAILABILITY)

    assert state.reason_code == integrations.FailureCode.DEPENDENCY_UNAVAILABLE.value

    wrong = integrations.CapabilityState(
        integrations.Capability.SHIPPING,
        integrations.CapabilityStatus.AVAILABLE,
        "AVAILABLE",
        "inventory",
        "1.0.0",
    )
    broken = integrations.SalesIntegrationRegistry(availability_resolver=lambda tenant, descriptor, capability: wrong)
    broken.register(provider)
    with pytest.raises(ValueError, match="wrong capability"):
        broken.capability_state(tenant_id, integrations.Capability.INVENTORY_AVAILABILITY)


def test_registry_rejects_invalid_provider_and_global_registry_type() -> None:
    registry = integrations.SalesIntegrationRegistry()

    with pytest.raises(TypeError, match="ProviderDescriptor"):
        registry.register(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tenant_id must be UUID"):
        registry.capability_state("tenant", integrations.Capability.INVENTORY_AVAILABILITY)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="provider_id"):
        registry.unregister(" ")
    with pytest.raises(TypeError, match="SalesIntegrationRegistry"):
        integrations.set_integration_registry(object())  # type: ignore[arg-type]


def test_global_registry_helpers_replace_alias_consistently() -> None:
    original = integrations.get_integration_registry()
    registry = integrations.SalesIntegrationRegistry()
    try:
        integrations.set_integration_registry(registry)

        assert integrations.get_integration_registry() is registry
        assert integrations.integrations is registry
    finally:
        integrations.set_integration_registry(original)
