"""Contract tests for the paid-module extension SPI."""

from __future__ import annotations

import uuid

import pytest

from src.modules.asset_management.extensions import (
    AssetExtensionRegistry,
    AvailabilityCode,
    CapabilityDescriptor,
    CapabilityUnavailableError,
    DuplicateCapabilityError,
    EntitlementDecision,
    ExtensionCompatibilityError,
    ExtensionPoint,
    ExtensionRegistrationError,
    RegistrationHandle,
    SemanticVersion,
    SpiVersionRange,
    UnknownCapabilityError,
)


class DetailTab:
    def get_detail(self, tenant_id, asset_id):
        return {"tenant_id": str(tenant_id), "asset_id": str(asset_id)}


class Action:
    def execute(self, tenant_id, asset_id, payload, idempotency_key):
        return {"idempotency_key": idempotency_key, "payload": payload}


class SchemaField:
    def validate(self, tenant_id, value):
        return str(value).upper()


class IdentityProvider:
    def resolve(self, tenant_id, identity):
        return uuid.uuid5(tenant_id, identity)


class Resolver:
    def __init__(self, decision=EntitlementDecision.GRANTED, *, raises=False):
        self.decision = decision
        self.raises = raises
        self.calls = []

    def check(self, tenant_id, entitlement):
        self.calls.append((tenant_id, entitlement))
        if self.raises:
            raise ConnectionError("license service unavailable")
        return self.decision


def descriptor(
    capability_id="acme.fleet.inspection",
    *,
    extension_point=ExtensionPoint.ACTION,
    supported_spi_versions=">=1.0.0,<2.0.0",
    entitlement="asset.premium:inspection",
    metadata=None,
):
    return CapabilityDescriptor(
        capability_id=capability_id,
        extension_point=extension_point,
        display_name="Safety inspection",
        description="Runs the Acme safety inspection workflow.",
        extension_version="2.3.1",
        supported_spi_versions=supported_spi_versions,
        required_entitlement=entitlement,
        quota_key="acme.inspections.monthly",
        metadata=metadata or {"icon": "clipboard-check"},
    )


@pytest.mark.parametrize(
    ("extension_point", "implementation"),
    [
        (ExtensionPoint.DETAIL_TAB, DetailTab()),
        (ExtensionPoint.ACTION, Action()),
        (ExtensionPoint.SCHEMA_FIELD, SchemaField()),
        (ExtensionPoint.IDENTITY_PROVIDER, IdentityProvider()),
    ],
)
def test_registers_and_discovers_each_supported_extension_point(extension_point, implementation):
    registry = AssetExtensionRegistry()
    tenant_id = uuid.uuid4()
    capability = descriptor(
        f"acme.fleet.{extension_point.name.lower()}",
        extension_point=extension_point,
    )

    handle = registry.register(capability, implementation)
    result = registry.discover(tenant_id, entitlement_resolver=Resolver())

    assert handle.capability_id == capability.capability_id
    assert result[0].descriptor is capability
    assert result[0].availability.available is True
    assert (
        registry.resolve(
            capability.capability_id,
            tenant_id,
            entitlement_resolver=Resolver(),
        )
        is implementation
    )


def test_rejects_semantically_incompatible_spi_ranges():
    registry = AssetExtensionRegistry(spi_version=SemanticVersion.parse("1.4.0"))

    with pytest.raises(ExtensionCompatibilityError, match="core provides 1.4.0"):
        registry.register(
            descriptor(supported_spi_versions="^2.0.0"),
            Action(),
        )


@pytest.mark.parametrize(
    ("range_source", "accepted", "rejected"),
    [
        ("^1.2.3", "1.9.9", "2.0.0"),
        ("^0.2.3", "0.2.9", "0.3.0"),
        (">=1.0.0,<1.5.0", "1.4.9", "1.5.0"),
        ("==1.0.0", "1.0.0", "1.0.1"),
    ],
)
def test_semantic_version_range_contract(range_source, accepted, rejected):
    version_range = SpiVersionRange(range_source)

    assert version_range.contains(SemanticVersion.parse(accepted))
    assert not version_range.contains(SemanticVersion.parse(rejected))


@pytest.mark.parametrize("invalid", ["1", "1.0", "v1.0.0", "01.0.0", "1.0.0-beta"])
def test_rejects_non_strict_semantic_versions(invalid):
    with pytest.raises(ExtensionRegistrationError, match="Invalid semantic version"):
        SemanticVersion.parse(invalid)


def test_duplicate_capability_id_cannot_replace_an_existing_handler():
    registry = AssetExtensionRegistry()
    original = Action()
    registry.register(descriptor(), original)

    with pytest.raises(DuplicateCapabilityError):
        registry.register(descriptor(), Action())

    assert registry.resolve("acme.fleet.inspection", uuid.uuid4(), entitlement_resolver=Resolver()) is original


def test_registration_requires_the_protocol_for_its_extension_point():
    with pytest.raises(ExtensionRegistrationError, match="AssetActionHandler"):
        AssetExtensionRegistry().register(descriptor(), IdentityProvider())


def test_discovery_is_fail_closed_when_entitlement_cannot_be_checked():
    registry = AssetExtensionRegistry()
    registry.register(descriptor(), Action())

    result = registry.discover(uuid.uuid4())

    assert result[0].availability.code is AvailabilityCode.ENTITLEMENT_CHECK_UNAVAILABLE
    assert result[0].availability.available is False
    with pytest.raises(CapabilityUnavailableError) as error:
        registry.resolve("acme.fleet.inspection", uuid.uuid4())
    assert error.value.availability.code is AvailabilityCode.ENTITLEMENT_CHECK_UNAVAILABLE


def test_discovery_exposes_upgrade_state_for_denied_entitlement():
    registry = AssetExtensionRegistry()
    tenant_id = uuid.uuid4()
    resolver = Resolver(EntitlementDecision.DENIED)
    registry.register(descriptor(), Action())

    result = registry.discover(tenant_id, entitlement_resolver=resolver)

    assert result[0].availability.code is AvailabilityCode.ENTITLEMENT_REQUIRED
    assert result[0].availability.required_entitlement == "asset.premium:inspection"
    assert resolver.calls == [(tenant_id, "asset.premium:inspection")]


@pytest.mark.parametrize(
    "resolver",
    [Resolver(EntitlementDecision.UNAVAILABLE), Resolver(raises=True)],
)
def test_entitlement_provider_failure_never_fabricates_availability(resolver):
    registry = AssetExtensionRegistry()
    registry.register(descriptor(), Action())

    result = registry.discover(uuid.uuid4(), entitlement_resolver=resolver)

    assert result[0].availability.code is AvailabilityCode.ENTITLEMENT_CHECK_UNAVAILABLE
    assert result[0].availability.available is False


def test_tenant_eligibility_runs_before_entitlement_and_is_tenant_specific():
    registry = AssetExtensionRegistry()
    eligible_tenant = uuid.uuid4()
    ineligible_tenant = uuid.uuid4()
    resolver = Resolver()
    registry.register(
        descriptor(),
        Action(),
        tenant_eligibility=lambda tenant_id: tenant_id == eligible_tenant,
    )

    eligible = registry.discover(eligible_tenant, entitlement_resolver=resolver)
    ineligible = registry.discover(ineligible_tenant, entitlement_resolver=resolver)

    assert eligible[0].availability.code is AvailabilityCode.AVAILABLE
    assert ineligible[0].availability.code is AvailabilityCode.TENANT_NOT_ELIGIBLE
    assert resolver.calls == [(eligible_tenant, "asset.premium:inspection")]


def test_tenant_eligibility_failure_is_explicit_and_fail_closed():
    registry = AssetExtensionRegistry()

    def unavailable(_tenant_id):
        raise TimeoutError("catalog unavailable")

    registry.register(descriptor(), Action(), tenant_eligibility=unavailable)

    result = registry.discover(uuid.uuid4(), entitlement_resolver=Resolver())

    assert result[0].availability.code is AvailabilityCode.ELIGIBILITY_CHECK_UNAVAILABLE


def test_capability_without_paid_entitlement_is_explicitly_available():
    registry = AssetExtensionRegistry()
    registry.register(descriptor(entitlement=None), Action())

    result = registry.discover(uuid.uuid4())

    assert result[0].availability.code is AvailabilityCode.AVAILABLE


def test_discovery_filters_by_extension_point_and_is_stably_sorted():
    registry = AssetExtensionRegistry()
    registry.register(
        descriptor(
            "zeta.fleet.tab",
            extension_point=ExtensionPoint.DETAIL_TAB,
            entitlement=None,
        ),
        DetailTab(),
    )
    registry.register(
        descriptor("acme.fleet.action", entitlement=None),
        Action(),
    )

    all_capabilities = registry.discover(uuid.uuid4())
    only_tabs = registry.discover(uuid.uuid4(), extension_points=[ExtensionPoint.DETAIL_TAB])

    assert [item.descriptor.capability_id for item in all_capabilities] == [
        "acme.fleet.action",
        "zeta.fleet.tab",
    ]
    assert [item.descriptor.capability_id for item in only_tabs] == ["zeta.fleet.tab"]


def test_discovery_metadata_is_immutable_and_does_not_expose_implementation():
    registry = AssetExtensionRegistry()
    metadata = {"component_key": "paid-inspection-tab"}
    registry.register(descriptor(metadata=metadata, entitlement=None), Action())
    metadata["component_key"] = "mutated"

    discovered = registry.discover(uuid.uuid4())[0]

    assert discovered.descriptor.metadata["component_key"] == "paid-inspection-tab"
    assert not hasattr(discovered, "implementation")
    with pytest.raises(TypeError):
        discovered.descriptor.metadata["extra"] = "forbidden"


def test_only_registration_owner_can_unregister():
    registry = AssetExtensionRegistry()
    handle = registry.register(descriptor(entitlement=None), Action())
    forged = RegistrationHandle(handle.capability_id, "forged-token")

    with pytest.raises(ExtensionRegistrationError, match="does not own"):
        registry.unregister(forged)
    assert len(registry.discover(uuid.uuid4())) == 1

    registry.unregister(handle)
    assert registry.discover(uuid.uuid4()) == ()
    with pytest.raises(UnknownCapabilityError):
        registry.unregister(handle)


@pytest.mark.parametrize("tenant_id", ["not-a-uuid", "", None, 42])
def test_tenant_context_must_be_a_valid_uuid(tenant_id):
    registry = AssetExtensionRegistry()

    with pytest.raises(ValueError, match="tenant_id must be a valid UUID"):
        registry.discover(tenant_id)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("capability_id", "Not Namespaced", "capability_id"),
        ("required_entitlement", "premium", "required_entitlement"),
        ("quota_key", "NOT VALID", "quota_key"),
    ],
)
def test_descriptor_rejects_unsafe_identifiers(field, value, message):
    kwargs = {
        "capability_id": "acme.fleet.inspection",
        "extension_point": ExtensionPoint.ACTION,
        "display_name": "Inspection",
        "description": "Inspection action.",
        "extension_version": "1.0.0",
        "supported_spi_versions": "^1.0.0",
        "required_entitlement": "asset.premium:inspection",
        "quota_key": "acme.inspection.monthly",
    }
    kwargs[field] = value

    with pytest.raises(ExtensionRegistrationError, match=message):
        CapabilityDescriptor(**kwargs)


def test_unknown_capability_resolution_is_distinct_from_unavailable():
    with pytest.raises(UnknownCapabilityError):
        AssetExtensionRegistry().resolve("acme.missing.capability", uuid.uuid4())
