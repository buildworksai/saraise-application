"""Fail-closed connector, event, and deterministic transformation registries."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ImproperlyConfigured, ValidationError

from .adapters import ConnectorAdapter
from .configuration import DEFAULT_CONFIGURATION

_TRANSFORM_POLICY = DEFAULT_CONFIGURATION["transformations"]
assert isinstance(_TRANSFORM_POLICY, Mapping)


class DuplicateAdapterError(ImproperlyConfigured):
    pass


class AdapterUnavailableError(LookupError):
    def __init__(self, key: str, reason: str = "adapter_not_registered") -> None:
        self.key = key
        self.reason = reason
        super().__init__(f"Connector adapter {key!r} is unavailable ({reason})")


class ConnectorAdapterRegistry:
    """Thread-safe adapter ownership keyed by ``Connector.adapter_key``."""

    def __init__(self) -> None:
        self._adapters: dict[str, ConnectorAdapter] = {}
        self._orphan_reasons: dict[str, str] = {}
        self._lock = threading.RLock()

    def register(self, adapter_key: str, adapter: ConnectorAdapter) -> ConnectorAdapter:
        if not isinstance(adapter, ConnectorAdapter):
            raise TypeError("adapter must implement ConnectorAdapter")
        key = adapter_key.strip() if isinstance(adapter_key, str) else ""
        if not key or key != adapter.descriptor.key:
            raise ValueError("Registration key must match adapter.descriptor.key")
        with self._lock:
            if key in self._adapters:
                raise DuplicateAdapterError(f"Connector adapter {key!r} is already registered")
            self._adapters[key] = adapter
            self._orphan_reasons.pop(key, None)
        return adapter

    def unregister(self, adapter_key: str, *, reason: str = "module_uninstalled") -> ConnectorAdapter | None:
        with self._lock:
            removed = self._adapters.pop(adapter_key, None)
            if removed is not None:
                self._orphan_reasons[adapter_key] = reason
            return removed

    def get(self, adapter_key: str) -> ConnectorAdapter:
        with self._lock:
            adapter = self._adapters.get(adapter_key)
            reason = self._orphan_reasons.get(adapter_key, "adapter_not_registered")
        if adapter is None:
            raise AdapterUnavailableError(adapter_key, reason)
        return adapter

    def is_registered(self, adapter_key: str) -> bool:
        with self._lock:
            return adapter_key in self._adapters

    def availability_reason(self, adapter_key: str) -> str:
        with self._lock:
            if adapter_key in self._adapters:
                return "available"
            return self._orphan_reasons.get(adapter_key, "adapter_not_registered")

    def catalog(self) -> tuple[object, ...]:
        with self._lock:
            return tuple(self._adapters[key].descriptor for key in sorted(self._adapters))

    def clear(self) -> None:
        """Reset registrations for isolated test application registries."""
        with self._lock:
            self._adapters.clear()
            self._orphan_reasons.clear()


Transform = Callable[[object, Mapping[str, object]], object]


def _trim(value: object, options: Mapping[str, object]) -> object:
    del options
    return value.strip() if isinstance(value, str) else value


def _string_case(value: object, options: Mapping[str, object]) -> object:
    if value is None:
        return None
    mode = options.get("case")
    if mode not in set(_TRANSFORM_POLICY["string_case_modes"]):
        raise ValidationError({"transform": "string_case requires lower, upper, title, or casefold."})
    text = str(value)
    return getattr(text, str(mode))()


def _number(value: object, options: Mapping[str, object]) -> object:
    if value is None or value == "":
        return None
    kind = options.get("type", _TRANSFORM_POLICY["default_number_mode"])
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError({"transform": "Value cannot be converted to a number."}) from exc
    if kind == "integer":
        return int(number)
    if kind == "float":
        return float(number)
    if kind == "decimal":
        return str(number)
    raise ValidationError({"transform": "number type must be integer, float, or decimal."})


def _date_format(value: object, options: Mapping[str, object]) -> object:
    if value is None or value == "":
        return None
    output = options.get("output_format")
    if not isinstance(output, str) or not output:
        raise ValidationError({"transform": "date_format requires output_format."})
    try:
        parsed = value if isinstance(value, datetime) else datetime.strptime(str(value), str(options.get("input_format") or _TRANSFORM_POLICY["default_input_date_format"]))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"transform": "Value does not match input_format."}) from exc
    return parsed.strftime(output)


def _default(value: object, options: Mapping[str, object]) -> object:
    return options.get("value") if value is None or value == "" else value


def _enum_map(value: object, options: Mapping[str, object]) -> object:
    mapping = options.get("mapping")
    if not isinstance(mapping, Mapping):
        raise ValidationError({"transform": "enum_map requires a mapping object."})
    key = str(value)
    if key in mapping:
        return mapping[key]
    if options.get("allow_unmapped", _TRANSFORM_POLICY["allow_unmapped_enum"]) is True:
        return value
    raise ValidationError({"transform": f"No enum mapping exists for {key!r}."})


def _identity(value: object, options: Mapping[str, object]) -> object:
    del options
    return value


class TransformationRegistry:
    """Bounded transformation DSL with no evaluation or attribute access."""

    def __init__(self) -> None:
        self._operations: dict[str, Transform] = {}
        self._lock = threading.RLock()

    def register(self, name: str, operation: Transform) -> None:
        if not name or not callable(operation):
            raise ValueError("A transformation name and callable are required")
        with self._lock:
            if name in self._operations:
                raise ImproperlyConfigured(f"Transformation {name!r} is already registered")
            self._operations[name] = operation

    @staticmethod
    def _steps(specification: object) -> list[Mapping[str, object]]:
        if specification in ({}, None):
            return []
        raw: object
        if isinstance(specification, Mapping) and "operations" in specification:
            raw = specification["operations"]
        elif isinstance(specification, Mapping):
            raw = [specification]
        elif isinstance(specification, Sequence) and not isinstance(specification, (str, bytes)):
            raw = specification
        else:
            raise ValidationError({"transform": "Transformation must be an object or operation array."})
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValidationError({"transform": "operations must be an array."})
        maximum = int(_TRANSFORM_POLICY["max_chain_length"])
        if len(raw) > maximum:
            raise ValidationError({"transform": f"At most {maximum} transformations may be chained."})
        steps: list[Mapping[str, object]] = []
        for step in raw:
            if not isinstance(step, Mapping):
                raise ValidationError({"transform": "Each transformation must be an object."})
            unknown = set(step) - {"operation", "options"}
            if unknown:
                raise ValidationError({"transform": f"Unknown transformation keys: {', '.join(sorted(unknown))}."})
            steps.append(step)
        return steps

    def validate(self, specification: object) -> None:
        for step in self._steps(specification):
            name = step.get("operation")
            if not isinstance(name, str) or name not in self._operations:
                raise ValidationError({"transform": f"Unknown transformation {name!r}."})
            options = step.get("options", {})
            if not isinstance(options, Mapping):
                raise ValidationError({"transform": "Transformation options must be an object."})
            # Run option validation without depending on a real sample where possible.
            if name == "string_case" and options.get("case") not in set(_TRANSFORM_POLICY["string_case_modes"]):
                raise ValidationError({"transform": "string_case requires a supported case."})
            if name == "date_format" and not isinstance(options.get("output_format"), str):
                raise ValidationError({"transform": "date_format requires output_format."})
            if name == "number" and options.get("type", _TRANSFORM_POLICY["default_number_mode"]) not in set(_TRANSFORM_POLICY["number_modes"]):
                raise ValidationError({"transform": "number type is unsupported."})
            if name == "enum_map" and not isinstance(options.get("mapping"), Mapping):
                raise ValidationError({"transform": "enum_map requires a mapping object."})

    def apply(self, value: object, specification: object) -> object:
        self.validate(specification)
        transformed = value
        for step in self._steps(specification):
            operation = self._operations[str(step["operation"])]
            transformed = operation(transformed, step.get("options", {}))  # type: ignore[arg-type]
        return transformed

    @property
    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._operations))


connector_adapter_registry = ConnectorAdapterRegistry()
transformation_registry = TransformationRegistry()
_AVAILABLE_OPERATIONS = dict((
    ("rename", _identity),
    ("string_case", _string_case),
    ("trim", _trim),
    ("number", _number),
    ("date_format", _date_format),
    ("default", _default),
    ("enum_map", _enum_map),
))
for _name in _TRANSFORM_POLICY["operations"]:
    transformation_registry.register(str(_name), _AVAILABLE_OPERATIONS[str(_name)])


__all__ = [
    "AdapterUnavailableError", "ConnectorAdapterRegistry", "DuplicateAdapterError",
    "TransformationRegistry", "connector_adapter_registry", "transformation_registry",
]
