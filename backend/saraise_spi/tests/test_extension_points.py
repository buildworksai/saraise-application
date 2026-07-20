"""Contract tests for paid-module extension points."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, Mapping
from uuid import UUID, uuid4

import pytest

from saraise_spi import (
    CAPABILITY_EXTENSION_POINT,
    ENGINE_EXTENSION_POINT,
    EXTENSION_POINT_IDS,
    PROVIDER_EXTENSION_POINT,
    SPI_VERSION,
    EntitlementDecision,
    EntitlementDeniedError,
    EntitlementServiceUnavailableError,
    ExecutionContext,
    ExtensionActivationError,
    ExtensionLifecycleError,
    ExtensionMetadata,
    ExtensionPoint,
    ExtensionRegistry,
    ExtensionState,
    ExtensionValidationError,
    RegistrationError,
    UnknownExtensionError,
    is_spi_compatible,
)


class Resolver:
    """In-memory test resolver whose decisions can be revoked."""

    def __init__(self, grants: Mapping[str, bool] | None = None) -> None:
        self.grants: Dict[str, bool] = dict(grants or {})
        self.calls: list[tuple[UUID, str]] = []

    def check(self, *, tenant_id: UUID, entitlement_id: str) -> EntitlementDecision:
        self.calls.append((tenant_id, entitlement_id))
        granted = self.grants.get(entitlement_id, False)
        return EntitlementDecision(
            granted=granted,
            source="test-license",
            reason=None if granted else "Not present in the tenant license",
        )


class Capability:
    def __init__(self, metadata: ExtensionMetadata) -> None:
        self.metadata = metadata
        self.validations = 0
        self.activations: list[UUID] = []
        self.invocations: list[tuple[UUID, object]] = []

    def validate(self) -> None:
        self.validations += 1

    def activate(self, context: ExecutionContext) -> None:
        self.activations.append(context.tenant_id)

    def invoke(self, context: ExecutionContext, request: object) -> object:
        self.invocations.append((context.tenant_id, request))
        return {"tenant_id": str(context.tenant_id), "request": request}


class Provider(Capability):
    def provide(self, context: ExecutionContext, request: object) -> object:
        return {"provider": self.metadata.extension_id, "request": request}


class Engine(Capability):
    def execute(self, context: ExecutionContext, request: object) -> object:
        return {"engine": self.metadata.extension_id, "request": request}


def metadata(
    point: ExtensionPoint = ExtensionPoint.CAPABILITY,
    *,
    extension_id: str = "com.buildworks.manufacturing.mrp",
    entitlements: frozenset[str] = frozenset({"industry.manufacturing.mrp"}),
) -> ExtensionMetadata:
    return ExtensionMetadata(
        extension_id=extension_id,
        extension_point=point,
        module_id="industry.manufacturing",
        module_version="2.4.1",
        display_name="Manufacturing resource planning",
        description="Production planning and material requirements.",
        required_entitlements=entitlements,
    )


def context(resolver: Resolver, tenant_id: UUID | None = None) -> ExecutionContext:
    return ExecutionContext(
        tenant_id=tenant_id or uuid4(),
        correlation_id="request-01J00000000000000000000000",
        principal_id="user@example.test",
        entitlement_resolver=resolver,
        attributes={"deployment_mode": "self-hosted-isolated"},
    )


def activated_capability() -> tuple[ExtensionRegistry, Capability, Resolver, ExecutionContext]:
    resolver = Resolver({"industry.manufacturing.mrp": True})
    execution_context = context(resolver)
    extension = Capability(metadata())
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    registry.activate(extension.metadata.extension_id, execution_context)
    return registry, extension, resolver, execution_context


def test_public_versioned_extension_point_ids_are_stable() -> None:
    assert SPI_VERSION == "1.0.0"
    assert PROVIDER_EXTENSION_POINT == "saraise.spi.provider.v1"
    assert ENGINE_EXTENSION_POINT == "saraise.spi.engine.v1"
    assert CAPABILITY_EXTENSION_POINT == "saraise.spi.capability.v1"
    assert EXTENSION_POINT_IDS == {
        PROVIDER_EXTENSION_POINT,
        ENGINE_EXTENSION_POINT,
        CAPABILITY_EXTENSION_POINT,
    }


@pytest.mark.parametrize(
    ("requested", "host", "compatible"),
    [
        ("1.0.0", "1.0.0", True),
        ("1.0.0", "1.5.0", True),
        ("1.1.0", "1.0.9", False),
        ("2.0.0", "1.9.9", False),
        ("not-semver", "1.0.0", False),
        ("1.0.0", "bad-host", False),
    ],
)
def test_spi_semantic_version_compatibility(requested: str, host: str, compatible: bool) -> None:
    assert is_spi_compatible(requested, host) is compatible


def test_execution_context_requires_real_uuid_resolver_and_correlation_id() -> None:
    resolver = Resolver()
    with pytest.raises(TypeError, match="UUID"):
        ExecutionContext("tenant", "correlation", resolver)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="correlation_id"):
        ExecutionContext(uuid4(), " ", resolver)
    with pytest.raises(TypeError, match="check"):
        ExecutionContext(uuid4(), "correlation", object())  # type: ignore[arg-type]


def test_execution_context_copies_attributes_to_an_immutable_mapping() -> None:
    mutable_attributes = {"mode": "isolated"}
    execution_context = context(Resolver(), attributes := uuid4())
    assert execution_context.tenant_id == attributes
    isolated_context = ExecutionContext(uuid4(), "correlation", Resolver(), attributes=mutable_attributes)
    mutable_attributes["mode"] = "connected"
    assert isolated_context.attributes["mode"] == "isolated"
    with pytest.raises(TypeError):
        isolated_context.attributes["mode"] = "saas"  # type: ignore[index]


def test_denied_decisions_require_reason_and_all_decisions_require_source() -> None:
    with pytest.raises(ValueError, match="source"):
        EntitlementDecision(granted=True, source=" ")
    with pytest.raises(ValueError, match="reason"):
        EntitlementDecision(granted=False, source="offline-license")


def test_register_validate_activate_lifecycle_is_explicit_and_tenant_specific() -> None:
    resolver = Resolver({"industry.manufacturing.mrp": True})
    first_tenant = context(resolver)
    second_tenant = context(resolver)
    extension = Capability(metadata())
    registry = ExtensionRegistry()

    registered = registry.register(extension)
    assert registered.state is ExtensionState.REGISTERED
    assert registered.active_tenants == ()
    with pytest.raises(ExtensionLifecycleError, match="validated"):
        registry.activate(extension.metadata.extension_id, first_tenant)

    validated = registry.validate(extension.metadata.extension_id)
    assert validated.state is ExtensionState.VALIDATED
    assert extension.validations == 1
    assert registry.validate(extension.metadata.extension_id) == validated
    assert extension.validations == 1

    first_activation = registry.activate(extension.metadata.extension_id, first_tenant)
    assert first_activation.state is ExtensionState.ACTIVE
    assert first_activation.active_tenants == (first_tenant.tenant_id,)
    registry.activate(extension.metadata.extension_id, first_tenant)
    registry.activate(extension.metadata.extension_id, second_tenant)
    assert extension.activations == [first_tenant.tenant_id, second_tenant.tenant_id]
    assert set(registry.snapshot(extension.metadata.extension_id).active_tenants) == {
        first_tenant.tenant_id,
        second_tenant.tenant_id,
    }


def test_registry_rejects_missing_metadata_duplicates_and_unknown_ids() -> None:
    registry = ExtensionRegistry()
    extension = Capability(metadata())
    with pytest.raises(RegistrationError, match="ExtensionMetadata"):
        registry.register(object())  # type: ignore[arg-type]
    empty_id = Capability(metadata(extension_id=""))
    with pytest.raises(RegistrationError, match="extension_id"):
        registry.register(empty_id)
    registry.register(extension)
    with pytest.raises(RegistrationError, match="already registered"):
        registry.register(extension)
    with pytest.raises(UnknownExtensionError, match="not registered"):
        registry.snapshot("com.example.missing")


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"extension_id": "Not Namespaced"}, "extension_id"),
        ({"module_id": "manufacturing"}, "module_id"),
        ({"display_name": " "}, "display_name"),
        ({"module_version": "version-one"}, "module_version"),
        ({"spi_version": "2.0.0"}, "not compatible"),
        ({"required_entitlements": frozenset({"INVALID ENTITLEMENT"})}, "Entitlement"),
    ],
)
def test_validation_rejects_invalid_metadata(changed: Mapping[str, object], message: str) -> None:
    extension = Capability(replace(metadata(), **changed))  # type: ignore[arg-type]
    registry = ExtensionRegistry()
    registry.register(extension)
    with pytest.raises(ExtensionValidationError, match=message):
        registry.validate(extension.metadata.extension_id)
    assert registry.snapshot(extension.metadata.extension_id).state is ExtensionState.REGISTERED


def test_validation_rejects_unsupported_extension_point_even_if_runtime_object_is_mutated() -> None:
    extension_metadata = metadata()
    object.__setattr__(extension_metadata, "extension_point", "saraise.spi.unknown.v1")
    extension = Capability(extension_metadata)
    registry = ExtensionRegistry()
    registry.register(extension)
    with pytest.raises(ExtensionValidationError, match="supported ExtensionPoint"):
        registry.validate(extension.metadata.extension_id)


@pytest.mark.parametrize("missing_method", ["validate", "activate", "invoke"])
def test_validation_rejects_missing_protocol_methods(missing_method: str) -> None:
    extension = Capability(metadata())
    setattr(extension, missing_method, None)
    registry = ExtensionRegistry()
    registry.register(extension)
    with pytest.raises(ExtensionValidationError, match=missing_method):
        registry.validate(extension.metadata.extension_id)


def test_validation_rejects_incompatible_method_signature() -> None:
    extension = Capability(metadata())
    setattr(extension, "invoke", lambda: None)
    registry = ExtensionRegistry()
    registry.register(extension)
    with pytest.raises(ExtensionValidationError, match="signature"):
        registry.validate(extension.metadata.extension_id)


def test_validation_hook_failure_and_fabricated_boolean_success_are_rejected() -> None:
    failing = Capability(metadata(extension_id="com.example.validation.failure"))

    def fail_validation() -> None:
        raise RuntimeError("missing configuration")

    failing.validate = fail_validation  # type: ignore[method-assign]
    registry = ExtensionRegistry()
    registry.register(failing)
    with pytest.raises(ExtensionValidationError, match="rejected") as error:
        registry.validate(failing.metadata.extension_id)
    assert isinstance(error.value.__cause__, RuntimeError)

    dishonest = Capability(metadata(extension_id="com.example.validation.boolean"))
    setattr(dishonest, "validate", lambda: True)
    registry.register(dishonest)
    with pytest.raises(ExtensionValidationError, match="returning None"):
        registry.validate(dishonest.metadata.extension_id)


def test_paid_extension_is_discoverable_but_denied_without_entitlement() -> None:
    resolver = Resolver({"industry.manufacturing.mrp": False})
    execution_context = context(resolver)
    extension = Capability(metadata())
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)

    discovered = registry.registrations()
    assert [item.metadata.extension_id for item in discovered] == [extension.metadata.extension_id]
    assert discovered[0].metadata.required_entitlements == {"industry.manufacturing.mrp"}
    with pytest.raises(EntitlementDeniedError) as error:
        registry.activate(extension.metadata.extension_id, execution_context)
    assert error.value.extension_id == extension.metadata.extension_id
    assert error.value.tenant_id == execution_context.tenant_id
    assert error.value.missing_entitlements == ("industry.manufacturing.mrp",)
    assert error.value.reasons["industry.manufacturing.mrp"] == "Not present in the tenant license"
    assert registry.snapshot(extension.metadata.extension_id).state is ExtensionState.VALIDATED
    assert extension.activations == []


def test_all_required_entitlements_must_be_granted() -> None:
    resolver = Resolver({"industry.manufacturing.mrp": True, "industry.manufacturing.scheduling": False})
    execution_context = context(resolver)
    extension = Capability(
        metadata(entitlements=frozenset({"industry.manufacturing.mrp", "industry.manufacturing.scheduling"}))
    )
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    with pytest.raises(EntitlementDeniedError) as error:
        registry.activate(extension.metadata.extension_id, execution_context)
    assert error.value.missing_entitlements == ("industry.manufacturing.scheduling",)
    assert [entitlement for _, entitlement in resolver.calls] == [
        "industry.manufacturing.mrp",
        "industry.manufacturing.scheduling",
    ]


def test_free_extension_activates_without_fabricating_an_entitlement_check() -> None:
    resolver = Resolver()
    execution_context = context(resolver)
    extension = Capability(metadata(entitlements=frozenset()))
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    registry.activate(extension.metadata.extension_id, execution_context)
    assert extension.activations == [execution_context.tenant_id]
    assert resolver.calls == []


def test_entitlement_resolver_failure_and_invalid_response_are_explicit_unavailability() -> None:
    class UnavailableResolver(Resolver):
        def check(self, *, tenant_id: UUID, entitlement_id: str) -> EntitlementDecision:
            raise TimeoutError("offline verifier is unavailable")

    extension = Capability(metadata())
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    with pytest.raises(EntitlementServiceUnavailableError) as error:
        registry.activate(extension.metadata.extension_id, context(UnavailableResolver()))
    assert isinstance(error.value.__cause__, TimeoutError)

    class InvalidResolver(Resolver):
        def check(self, *, tenant_id: UUID, entitlement_id: str) -> EntitlementDecision:
            return True  # type: ignore[return-value]

    with pytest.raises(EntitlementServiceUnavailableError, match="invalid decision"):
        registry.activate(extension.metadata.extension_id, context(InvalidResolver()))


def test_activation_failure_does_not_change_lifecycle_state() -> None:
    resolver = Resolver({"industry.manufacturing.mrp": True})
    extension = Capability(metadata())

    def fail_activation(execution_context: ExecutionContext) -> None:
        raise RuntimeError("engine bootstrap failed")

    setattr(extension, "activate", fail_activation)
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    with pytest.raises(ExtensionActivationError, match="failed activation") as error:
        registry.activate(extension.metadata.extension_id, context(resolver))
    assert isinstance(error.value.__cause__, RuntimeError)
    assert registry.snapshot(extension.metadata.extension_id).state is ExtensionState.VALIDATED


def test_activation_hook_cannot_return_a_fabricated_success_flag() -> None:
    resolver = Resolver({"industry.manufacturing.mrp": True})
    extension = Capability(metadata())
    setattr(extension, "activate", lambda execution_context: True)
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    with pytest.raises(ExtensionActivationError, match="returning None"):
        registry.activate(extension.metadata.extension_id, context(resolver))


def test_capability_invocation_is_real_and_entitlement_is_rechecked_for_revocation() -> None:
    registry, extension, resolver, execution_context = activated_capability()
    request = {"work_order": "WO-1007"}
    assert registry.invoke(extension.metadata.extension_id, execution_context, request) == {
        "tenant_id": str(execution_context.tenant_id),
        "request": request,
    }
    assert extension.invocations == [(execution_context.tenant_id, request)]

    resolver.grants["industry.manufacturing.mrp"] = False
    with pytest.raises(EntitlementDeniedError):
        registry.invoke(extension.metadata.extension_id, execution_context, request)
    assert extension.invocations == [(execution_context.tenant_id, request)]


def test_extension_must_be_active_for_the_calling_tenant() -> None:
    registry, extension, resolver, _ = activated_capability()
    other_tenant_context = context(resolver)
    with pytest.raises(ExtensionLifecycleError, match="not active"):
        registry.invoke(extension.metadata.extension_id, other_tenant_context, {})


@pytest.mark.parametrize(
    ("point", "extension_factory", "operation", "expected_key"),
    [
        (ExtensionPoint.PROVIDER, Provider, "provide", "provider"),
        (ExtensionPoint.ENGINE, Engine, "execute", "engine"),
    ],
)
def test_provider_and_engine_protocols_dispatch_to_real_implementations(
    point: ExtensionPoint,
    extension_factory: type[Capability],
    operation: str,
    expected_key: str,
) -> None:
    resolver = Resolver({"industry.manufacturing.mrp": True})
    execution_context = context(resolver)
    extension = extension_factory(metadata(point))
    registry = ExtensionRegistry()
    registry.register(extension)
    registry.validate(extension.metadata.extension_id)
    registry.activate(extension.metadata.extension_id, execution_context)
    result = getattr(registry, operation)(extension.metadata.extension_id, execution_context, {"input": 7})
    assert result == {expected_key: extension.metadata.extension_id, "request": {"input": 7}}


def test_wrong_operation_for_extension_point_is_rejected() -> None:
    registry, extension, _, execution_context = activated_capability()
    with pytest.raises(ExtensionLifecycleError, match=PROVIDER_EXTENSION_POINT):
        registry.provide(extension.metadata.extension_id, execution_context, {})


def test_registrations_are_sorted_and_snapshots_do_not_expose_mutable_state() -> None:
    registry = ExtensionRegistry()
    second = Capability(metadata(extension_id="com.example.zulu"))
    first = Capability(metadata(extension_id="com.example.alpha"))
    registry.register(second)
    registry.register(first)
    snapshots = registry.registrations()
    assert [snapshot.metadata.extension_id for snapshot in snapshots] == [
        "com.example.alpha",
        "com.example.zulu",
    ]
    assert isinstance(snapshots[0].active_tenants, tuple)
