from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from django.db.models import Q

from src.modules.security_access_control.extensions import (
    ExtensionCollisionError,
    ExtensionContractError,
    FieldAccess,
    FieldPolicyPort,
    PermissionCatalogPort,
    PermissionDescriptor,
    PermissionRisk,
    PredicateSchemaDescriptor,
    ResourceFieldDescriptor,
    ResourceFieldType,
    ResourceSecurityDescriptor,
    RowAccessExplanation,
    RowPolicyPort,
    SecurityEnforcementPort,
    SecurityExtensionDescriptor,
    SecurityExtensionRegistry,
    extension_registry,
    get_predicate_schema,
    get_resource_descriptor,
    register_security_extension,
    unregister_security_extension,
)


def descriptor(*, owner: str = "healthcare", version: str = "1.0.0") -> SecurityExtensionDescriptor:
    return SecurityExtensionDescriptor(
        owner_manifest=owner,
        owner_version=version,
        permission_namespace="healthcare",
        permissions=(
            PermissionDescriptor(
                module="healthcare",
                resource="claims",
                action="read",
                name="Read claims",
                risk_level=PermissionRisk.HIGH,
            ),
        ),
        resources=(
            ResourceSecurityDescriptor(
                module="healthcare",
                resource="claims",
                fields=(
                    ResourceFieldDescriptor("id", ResourceFieldType.UUID, allowed_predicates=("eq", "in")),
                    ResourceFieldDescriptor("owner_id", ResourceFieldType.UUID),
                ),
                trusted_subject_attributes=("user_id", "organization_id"),
            ),
        ),
    )


def test_descriptor_contract_is_versioned_canonical_and_immutable() -> None:
    extension = descriptor()
    permission = extension.permissions[0]

    assert permission.code == "healthcare.claims:read"
    assert extension.resources[0].key == "healthcare.claims"
    assert extension.schema_version == "1.0"
    assert len(extension.fingerprint) == 64
    assert extension.fingerprint == descriptor().fingerprint
    with pytest.raises((AttributeError, TypeError)):
        permission.action = "delete"  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [
        PermissionDescriptor(module="wrong", resource="claims", action="read", name="Read"),
    ],
)
def test_permission_namespace_ownership_is_enforced(value: PermissionDescriptor) -> None:
    with pytest.raises(ExtensionContractError, match="owned namespace"):
        replace(descriptor(), permissions=(value,))


def test_resource_metadata_rejects_unsafe_or_duplicate_fields() -> None:
    with pytest.raises(ExtensionContractError, match="unsafe operator"):
        ResourceFieldDescriptor("amount", ResourceFieldType.DECIMAL, allowed_predicates=("raw_sql",))

    repeated = ResourceFieldDescriptor("amount", ResourceFieldType.DECIMAL, allowed_predicates=("eq",))
    with pytest.raises(ExtensionContractError, match="unique"):
        ResourceSecurityDescriptor(module="healthcare", resource="claims", fields=(repeated, repeated))


def test_predicate_schema_is_bounded_and_cannot_expand_operator_vocabulary() -> None:
    with pytest.raises(ExtensionContractError, match="unsupported nodes"):
        PredicateSchemaDescriptor(allowed_nodes=("eq", "regex"))
    with pytest.raises(ExtensionContractError, match="between 1 and 16"):
        PredicateSchemaDescriptor(max_depth=17)
    with pytest.raises(ExtensionContractError, match="incompatible"):
        PredicateSchemaDescriptor(schema_version="2.0")


def test_registry_registration_retry_upgrade_discovery_and_uninstall() -> None:
    registry = SecurityExtensionRegistry()
    first = descriptor()
    assert registry.register(first) is first
    assert registry.register(descriptor()) is first
    assert registry.get_permission("healthcare.claims:read").risk_level == PermissionRisk.HIGH
    assert registry.get_resource("healthcare", "claims").fields[0].name == "id"
    assert registry.get_predicate_schema("healthcare", "claims").schema_version == "1.0"

    newer = replace(first, owner_version="1.1.0")
    assert registry.register(newer) is newer
    with pytest.raises(ExtensionCollisionError, match="newer"):
        registry.register(first)
    with pytest.raises(ExtensionCollisionError, match="version changed"):
        registry.unregister("healthcare", expected_version="1.0.0")

    assert registry.unregister("healthcare", expected_version="1.1.0") is newer
    assert registry.unregister("healthcare") is None
    with pytest.raises(LookupError):
        registry.get_resource("healthcare", "claims")
    with pytest.raises(LookupError, match="predicate schema"):
        registry.get_predicate_schema("healthcare", "claims")


def test_registry_rejects_namespace_and_resource_takeover_without_partial_write() -> None:
    registry = SecurityExtensionRegistry()
    original = descriptor()
    registry.register(original)
    takeover = replace(original, owner_manifest="healthcare-competitor", owner_version="2.0.0")

    with pytest.raises(ExtensionCollisionError, match="namespace"):
        registry.register(takeover)
    assert registry.list_extensions() == (original,)


def test_contract_protocols_are_structural_and_do_not_require_model_imports() -> None:
    class Adapter:
        def register_extension(
            self,
            tenant_id: UUID,
            extension: SecurityExtensionDescriptor,
            *,
            actor_id: UUID,
            correlation_id: str,
        ) -> tuple[str, ...]:
            del tenant_id, actor_id, correlation_id
            return tuple(item.code for item in extension.permissions)

        def resolve_field_access(self, *_args: object, **_kwargs: object):
            return {"id": FieldAccess("visible", "read_only")}

        def compile_queryset_filter(self, *_args: object, **_kwargs: object):
            return Q(pk__isnull=False)

        def explain_row_access(self, *_args: object, **_kwargs: object):
            return RowAccessExplanation(True, (uuid4(),), ("ROW_POLICY_MATCHED",))

        def secure_queryset(self, *_args: object, **_kwargs: object):
            return _args[-1]

        def project_fields(self, *_args: object, **_kwargs: object):
            return _args[-1]

    adapter = Adapter()
    assert isinstance(adapter, PermissionCatalogPort)
    assert isinstance(adapter, FieldPolicyPort)
    assert isinstance(adapter, RowPolicyPort)
    assert isinstance(adapter, SecurityEnforcementPort)
    assert adapter.register_extension(uuid4(), descriptor(), actor_id=uuid4(), correlation_id="req") == (
        "healthcare.claims:read",
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"module": "Healthcare"}, "invalid format"),
        ({"name": " "}, "1 to 255"),
        ({"name": "x" * 256}, "1 to 255"),
        ({"description": "x" * 2_001}, "at most 2000"),
        ({"risk_level": "severe"}, "unsupported"),
    ],
)
def test_permission_descriptor_rejects_noncanonical_values(changes: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "module": "healthcare",
        "resource": "claims",
        "action": "read",
        "name": "Read claims",
    }
    values.update(changes)
    with pytest.raises(ExtensionContractError, match=message):
        PermissionDescriptor(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"data_type": "binary"}, "unsupported"),
        ({"nullable": "yes"}, "must be boolean"),
        ({"allowed_predicates": ()}, "non-empty and unique"),
        ({"allowed_predicates": ("eq", "eq")}, "non-empty and unique"),
        ({"allowed_predicates": ("is_null",)}, "at least one usable"),
    ],
)
def test_field_descriptor_rejects_ambiguous_metadata(changes: dict[str, object], message: str) -> None:
    values: dict[str, object] = {"name": "amount", "data_type": ResourceFieldType.DECIMAL}
    values.update(changes)
    with pytest.raises(ExtensionContractError, match=message):
        ResourceFieldDescriptor(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"descriptor_version": "one"}, "descriptor_version"),
        ({"predicate_schema_version": "2.0"}, "incompatible"),
        ({"fields": ()}, "typed fields"),
        ({"fields": ("id",)}, "typed fields"),
        ({"trusted_subject_attributes": ("user_id", "user_id")}, "must be unique"),
        ({"trusted_subject_attributes": ("User-ID",)}, "invalid format"),
    ],
)
def test_resource_descriptor_rejects_incompatible_metadata(changes: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "module": "healthcare",
        "resource": "claims",
        "fields": (ResourceFieldDescriptor("id", ResourceFieldType.UUID, allowed_predicates=("eq",)),),
    }
    values.update(changes)
    with pytest.raises(ExtensionContractError, match=message):
        ResourceSecurityDescriptor(**values)  # type: ignore[arg-type]


def test_extension_descriptor_rejects_incompatible_or_duplicate_payloads() -> None:
    base = descriptor()
    with pytest.raises(ExtensionContractError, match="semantic versioning"):
        replace(base, owner_version="1.0")
    with pytest.raises(ExtensionContractError, match="schema_version"):
        replace(base, schema_version="2.0")
    with pytest.raises(ExtensionContractError, match="PermissionDescriptor"):
        replace(base, permissions=("permission",))  # type: ignore[arg-type]
    with pytest.raises(ExtensionContractError, match="must be unique"):
        replace(base, permissions=(base.permissions[0], base.permissions[0]))
    with pytest.raises(ExtensionContractError, match="ResourceSecurityDescriptor"):
        replace(base, resources=("resource",))  # type: ignore[arg-type]
    with pytest.raises(ExtensionContractError, match="owned namespace"):
        other_resource = replace(base.resources[0], module="finance")
        replace(base, resources=(other_resource,))
    with pytest.raises(ExtensionContractError, match="resource keys must be unique"):
        replace(base, resources=(base.resources[0], base.resources[0]))
    with pytest.raises(ExtensionContractError, match="schema versions must match"):
        replace(base, predicate_schema=PredicateSchemaDescriptor(schema_version="1.1"))


def test_registry_defence_in_depth_lookup_clear_and_public_helpers() -> None:
    registry = SecurityExtensionRegistry()
    with pytest.raises(ExtensionContractError, match="must be"):
        registry.register("invalid")  # type: ignore[arg-type]
    with pytest.raises(LookupError, match="permission descriptor"):
        registry.get_permission("healthcare.claims:read")

    owned = descriptor()
    registry.register(owned)
    registry.clear()
    assert registry.list_extensions() == ()

    extension_registry.clear()
    try:
        assert register_security_extension(owned) is owned
        assert get_resource_descriptor("healthcare", "claims").key == "healthcare.claims"
        assert get_predicate_schema("healthcare", "claims").max_depth == 8
        assert unregister_security_extension("healthcare", expected_version="1.0.0") is owned
    finally:
        extension_registry.clear()


def test_registry_detects_permission_and_resource_index_corruption() -> None:
    registry = SecurityExtensionRegistry()
    contribution = descriptor()
    registry._permissions[contribution.permissions[0].code] = ("other-owner", contribution.permissions[0])
    with pytest.raises(ExtensionCollisionError, match="permission"):
        registry.register(contribution)

    registry = SecurityExtensionRegistry()
    registry._resources[contribution.resources[0].key] = ("other-owner", contribution.resources[0])
    with pytest.raises(ExtensionCollisionError, match="resource"):
        registry.register(contribution)
