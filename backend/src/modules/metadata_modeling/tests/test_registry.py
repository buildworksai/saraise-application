"""Extension registry safety contracts."""

from __future__ import annotations

import math

import pytest

from src.modules.metadata_modeling.registry import (
    DuplicateExtensionError,
    ExtensionRegistrationError,
    MetadataExtensionRegistry,
)


def _schema(field_type: str = "text", *, key: str = "title", order: int = 0) -> dict[str, object]:
    return {
        "fields": [
            {
                "name": "Title",
                "key": key,
                "field_type": field_type,
                "order": order,
            }
        ]
    }


def test_registry_lists_contracts_and_complete_field_extensions_in_stable_order() -> None:
    registry = MetadataExtensionRegistry()

    first = registry.register_entity_contract("billing", "1.0.0", "invoice", lambda: _schema())
    second = registry.register_entity_contract("billing", "1.1.0", "receipt", lambda: _schema("currency"))
    registry.register_field_validator("currency", lambda value: value)
    registry.register_field_renderer("currency", lambda value: {"component": "money", "value": value})

    assert registry.get_entity_contract("billing", "invoice", "1.0.0") is first
    assert registry.list_entity_contracts() == (first, second)
    assert registry.list_entity_contracts("billing") == (first, second)
    assert registry.list_entity_contracts("missing") == ()
    assert registry.list_field_types()[0].type_key == "currency"
    assert registry.system_check_errors() == []


def test_registry_rejects_ambiguous_registration_and_surfaces_startup_errors() -> None:
    registry = MetadataExtensionRegistry()
    registry.register_entity_contract("billing", "1", "invoice", lambda: _schema())
    registry.register_field_validator("currency", lambda value: value)

    with pytest.raises(DuplicateExtensionError):
        registry.register_entity_contract("billing", "1", "invoice", lambda: _schema())
    with pytest.raises(ExtensionRegistrationError):
        registry.register_field_renderer("text", lambda value: value)
    with pytest.raises(ExtensionRegistrationError):
        registry.register_entity_contract("Billing", "v1", "invoice", lambda: _schema())
    with pytest.raises(ExtensionRegistrationError):
        registry.register_field_validator("bad", object())  # type: ignore[arg-type]

    messages = [error.msg for error in registry.system_check_errors()]
    assert any("duplicate entity contract registration" in message for message in messages)
    assert any("built-in field type 'text' cannot be overridden" in message for message in messages)
    assert any("owner_module must be a lowercase slug" in message for message in messages)
    assert any("validator must be callable" in message for message in messages)
    assert any("Extension field type 'currency' has no renderer" in message for message in messages)


@pytest.mark.parametrize(
    "schema_factory, expected",
    [
        (lambda: [], "schema_factory must return a mapping"),
        (lambda: {"fields": "title"}, "schema.fields must be a list"),
        (lambda: {"fields": [None]}, "schema.fields[0] must be an object"),
        (lambda: {"fields": [{"name": "", "key": "title", "field_type": "text", "order": 0}]}, "name"),
        (lambda: _schema("unknown"), "is not registered"),
        (lambda: {"fields": [{"name": "Title", "key": "title", "field_type": "text", "order": True}]}, "order"),
        (
            lambda: {
                "fields": [_schema()["fields"][0], {"name": "Other", "key": "title", "field_type": "text", "order": 1}]
            },
            "duplicate field key",
        ),
        (
            lambda: {
                "fields": [_schema()["fields"][0], {"name": "Other", "key": "other", "field_type": "text", "order": 0}]
            },
            "duplicate field order",
        ),
        (
            lambda: {"fields": [{"name": "Title", "key": "title", "field_type": "text", "order": 0}], "bad": math.nan},
            "JSON-serializable",
        ),
    ],
)
def test_registry_system_checks_malformed_contract_schemas(schema_factory, expected: str) -> None:
    registry = MetadataExtensionRegistry()
    registry.register_entity_contract("billing", "1", f"invoice_{abs(hash(expected))}", schema_factory)

    errors = registry.system_check_errors()

    assert len(errors) == 1
    assert expected in errors[0].msg
