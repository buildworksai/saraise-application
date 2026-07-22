"""Declarative extension contracts for the metadata kernel.

The registry is intentionally process-local: extensions register immutable code
contracts at application startup while tenant-owned definitions and records stay
behind the metadata services.  Registration never grants data access.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from typing import TypeAlias

from django.core import checks

JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]
SchemaFactory: TypeAlias = Callable[[], Mapping[str, JSONValue]]
FieldValidator: TypeAlias = Callable[..., object]
FieldRenderer: TypeAlias = Callable[..., object]

BUILT_IN_FIELD_TYPES = frozenset({"text", "number", "date", "boolean", "select", "reference", "json"})

_SLUG = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,2}(?:-[a-z0-9][a-z0-9.-]*)?$")


class ExtensionRegistrationError(ValueError):
    """Raised when an extension attempts an unsafe or ambiguous registration."""


class DuplicateExtensionError(ExtensionRegistrationError):
    """Raised when a stable registry key has already been claimed."""


@dataclass(frozen=True, slots=True)
class EntityContract:
    """Immutable registration for one version of an extension-owned entity."""

    owner_module: str
    contract_version: str
    code: str
    schema_factory: SchemaFactory


@dataclass(frozen=True, slots=True)
class FieldTypeExtension:
    """Validator and renderer pair for one non-core field type."""

    type_key: str
    validator: FieldValidator
    renderer: FieldRenderer


class MetadataExtensionRegistry:
    """Thread-safe registry with deterministic startup validation.

    Contracts contain declarations only.  They do not contain tenant identifiers,
    model instances, permissions, or persistence callbacks.  Consumers must use the
    tenant-first service API to materialize a registered contract.
    """

    def __init__(self) -> None:
        self._contracts: dict[tuple[str, str, str], EntityContract] = {}
        self._field_validators: dict[str, FieldValidator] = {}
        self._field_renderers: dict[str, FieldRenderer] = {}
        self._registration_errors: list[str] = []
        self._lock = RLock()

    def register_entity_contract(
        self,
        owner_module: str,
        contract_version: str,
        code: str,
        schema_factory: SchemaFactory,
    ) -> EntityContract:
        """Register an immutable entity contract under its complete version key."""

        try:
            self._validate_stable_key("owner_module", owner_module)
            self._validate_stable_key("code", code)
            if not isinstance(contract_version, str) or not _VERSION.fullmatch(contract_version):
                raise ExtensionRegistrationError("contract_version must be a numeric version such as '1' or '1.2.0'")
            self._validate_callable("schema_factory", schema_factory, positional_arguments=0)
        except ExtensionRegistrationError as exc:
            self._remember_registration_error(str(exc))
            raise

        key = (owner_module, code, contract_version)
        contract = EntityContract(owner_module, contract_version, code, schema_factory)
        with self._lock:
            if key in self._contracts:
                message = "duplicate entity contract registration for " f"{owner_module}.{code}@{contract_version}"
                self._registration_errors.append(message)
                raise DuplicateExtensionError(message)
            self._contracts[key] = contract
        return contract

    def get_entity_contract(self, owner_module: str, code: str, contract_version: str) -> EntityContract | None:
        """Return the exact contract version, never a guessed latest version."""

        with self._lock:
            return self._contracts.get((owner_module, code, contract_version))

    def list_entity_contracts(self, owner_module: str | None = None) -> tuple[EntityContract, ...]:
        """Return a stable, immutable snapshot of registered contracts."""

        with self._lock:
            contracts = tuple(self._contracts.values())
        if owner_module is not None:
            contracts = tuple(item for item in contracts if item.owner_module == owner_module)
        return tuple(
            sorted(
                contracts,
                key=lambda item: (item.owner_module, item.code, item.contract_version),
            )
        )

    def register_field_validator(self, type_key: str, validator: FieldValidator) -> None:
        """Register validation for an extension field type."""

        self._register_field_callback(
            registry=self._field_validators,
            callback_kind="validator",
            type_key=type_key,
            callback=validator,
        )

    def register_field_renderer(self, type_key: str, renderer: FieldRenderer) -> None:
        """Register a declarative form-descriptor renderer for a field type."""

        self._register_field_callback(
            registry=self._field_renderers,
            callback_kind="renderer",
            type_key=type_key,
            callback=renderer,
        )

    def get_field_validator(self, type_key: str) -> FieldValidator | None:
        with self._lock:
            return self._field_validators.get(type_key)

    def get_field_renderer(self, type_key: str) -> FieldRenderer | None:
        with self._lock:
            return self._field_renderers.get(type_key)

    def list_field_types(self) -> tuple[FieldTypeExtension, ...]:
        """List only complete field extensions; half-registered types are unusable."""

        with self._lock:
            complete = self._field_validators.keys() & self._field_renderers.keys()
            return tuple(
                FieldTypeExtension(
                    type_key=type_key,
                    validator=self._field_validators[type_key],
                    renderer=self._field_renderers[type_key],
                )
                for type_key in sorted(complete)
            )

    def system_check_errors(self) -> list[checks.CheckMessage]:
        """Validate every registration without mutating registry state."""

        with self._lock:
            contracts = tuple(self._contracts.values())
            validators = dict(self._field_validators)
            renderers = dict(self._field_renderers)
            registration_errors = tuple(self._registration_errors)

        errors: list[checks.CheckMessage] = [
            checks.Error(
                message,
                hint="Use a unique stable key and register each extension exactly once.",
                id="metadata_modeling.E001",
            )
            for message in registration_errors
        ]

        for type_key in sorted(validators.keys() ^ renderers.keys()):
            missing = "renderer" if type_key in validators else "validator"
            errors.append(
                checks.Error(
                    f"Extension field type '{type_key}' has no {missing}.",
                    hint="Register validator and renderer together before startup checks run.",
                    id="metadata_modeling.E003",
                )
            )

        known_field_types = BUILT_IN_FIELD_TYPES | validators.keys() & renderers.keys()
        for contract in contracts:
            label = f"{contract.owner_module}.{contract.code}@{contract.contract_version}"
            try:
                schema = contract.schema_factory()
                self._validate_schema(schema, known_field_types)
            except Exception as exc:  # A broken extension must become a startup error.
                errors.append(
                    checks.Error(
                        f"Entity contract '{label}' is malformed: {exc}",
                        hint=(
                            "Return a JSON-serializable schema with uniquely keyed, ordered "
                            "fields and registered field types."
                        ),
                        obj=contract.schema_factory,
                        id="metadata_modeling.E002",
                    )
                )
        return errors

    def _register_field_callback(
        self,
        *,
        registry: dict[str, Callable[..., object]],
        callback_kind: str,
        type_key: str,
        callback: Callable[..., object],
    ) -> None:
        try:
            self._validate_stable_key("type_key", type_key)
            if type_key in BUILT_IN_FIELD_TYPES:
                raise ExtensionRegistrationError(f"built-in field type '{type_key}' cannot be overridden")
            self._validate_callable(callback_kind, callback, positional_arguments=1)
        except ExtensionRegistrationError as exc:
            self._remember_registration_error(str(exc))
            raise

        with self._lock:
            if type_key in registry:
                message = f"duplicate field {callback_kind} registration for '{type_key}'"
                self._registration_errors.append(message)
                raise DuplicateExtensionError(message)
            registry[type_key] = callback

    def _remember_registration_error(self, message: str) -> None:
        with self._lock:
            self._registration_errors.append(message)

    @staticmethod
    def _validate_stable_key(name: str, value: object) -> str:
        if not isinstance(value, str) or len(value) > 100 or not _SLUG.fullmatch(value):
            raise ExtensionRegistrationError(f"{name} must be a lowercase slug of at most 100 characters")
        return value

    @staticmethod
    def _validate_callable(name: str, callback: object, *, positional_arguments: int) -> None:
        if not callable(callback):
            raise ExtensionRegistrationError(f"{name} must be callable")
        try:
            inspect.signature(callback).bind(*([None] * positional_arguments))
        except (TypeError, ValueError) as exc:
            raise ExtensionRegistrationError(
                f"{name} must accept {positional_arguments} positional argument(s)"
            ) from exc

    @classmethod
    def _validate_schema(
        cls,
        schema: object,
        known_field_types: set[str] | frozenset[str],
    ) -> None:
        if not isinstance(schema, Mapping):
            raise ExtensionRegistrationError("schema_factory must return a mapping")
        try:
            json.dumps(schema, allow_nan=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ExtensionRegistrationError(
                "schema must contain finite, JSON-serializable declarative values only"
            ) from exc

        fields = schema.get("fields")
        if not isinstance(fields, list):
            raise ExtensionRegistrationError("schema.fields must be a list")

        keys: set[str] = set()
        orders: set[int] = set()
        for position, field in enumerate(fields):
            if not isinstance(field, Mapping):
                raise ExtensionRegistrationError(f"schema.fields[{position}] must be an object")
            field_key = cls._validate_stable_key(f"schema.fields[{position}].key", field.get("key"))
            field_name = field.get("name")
            field_type = field.get("field_type")
            order = field.get("order")
            if not isinstance(field_name, str) or not field_name.strip() or len(field_name) > 160:
                raise ExtensionRegistrationError(f"schema.fields[{position}].name must be a non-empty string")
            if field_type not in known_field_types:
                raise ExtensionRegistrationError(
                    f"schema.fields[{position}].field_type '{field_type}' is not registered"
                )
            if isinstance(order, bool) or not isinstance(order, int) or order < 0:
                raise ExtensionRegistrationError(f"schema.fields[{position}].order must be a non-negative integer")
            if field_key in keys:
                raise ExtensionRegistrationError(f"duplicate field key '{field_key}'")
            if order in orders:
                raise ExtensionRegistrationError(f"duplicate field order '{order}'")
            keys.add(field_key)
            orders.add(order)


extension_registry = MetadataExtensionRegistry()


def register_entity_contract(
    owner_module: str,
    contract_version: str,
    code: str,
    schema_factory: SchemaFactory,
) -> EntityContract:
    """Register an entity contract in the process-wide extension registry."""

    return extension_registry.register_entity_contract(owner_module, contract_version, code, schema_factory)


def get_entity_contract(owner_module: str, code: str, contract_version: str) -> EntityContract | None:
    return extension_registry.get_entity_contract(owner_module, code, contract_version)


def list_entity_contracts(owner_module: str | None = None) -> tuple[EntityContract, ...]:
    return extension_registry.list_entity_contracts(owner_module)


def register_field_validator(type_key: str, validator: FieldValidator) -> None:
    extension_registry.register_field_validator(type_key, validator)


def register_field_renderer(type_key: str, renderer: FieldRenderer) -> None:
    extension_registry.register_field_renderer(type_key, renderer)


def get_field_validator(type_key: str) -> FieldValidator | None:
    return extension_registry.get_field_validator(type_key)


def get_field_renderer(type_key: str) -> FieldRenderer | None:
    return extension_registry.get_field_renderer(type_key)


@checks.register(checks.Tags.models)
def check_metadata_extension_registry(app_configs: object = None, **kwargs: object) -> list[checks.CheckMessage]:
    """Expose extension defects through Django's deployment/system check gate."""

    del app_configs, kwargs
    return extension_registry.system_check_errors()


__all__ = [
    "BUILT_IN_FIELD_TYPES",
    "DuplicateExtensionError",
    "EntityContract",
    "ExtensionRegistrationError",
    "FieldTypeExtension",
    "MetadataExtensionRegistry",
    "check_metadata_extension_registry",
    "extension_registry",
    "get_entity_contract",
    "get_field_renderer",
    "get_field_validator",
    "list_entity_contracts",
    "register_entity_contract",
    "register_field_renderer",
    "register_field_validator",
]
