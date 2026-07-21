"""Validation and safe compilation for the row-security predicate DSL.

The compiler only creates Django ``Q`` objects from a closed JSON grammar. It
never accepts ORM lookup suffixes, SQL fragments, callables, or interpolation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Q

MAX_PREDICATE_NODES = 64
MAX_PREDICATE_DEPTH = 8
MAX_IN_VALUES = 100
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_LEAF = frozenset({"eq", "in", "is_null", "owner", "tenant"})
_COMPOUND = frozenset({"and", "or", "not"})


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _field(value: object, *, allowed_fields: frozenset[str] | None) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or "__" in value:
        raise ValidationError("Predicate field must be a registered simple identifier.")
    if allowed_fields is not None and value not in allowed_fields:
        raise ValidationError(f"Predicate field '{value}' is not registered for this resource.")
    return value


def _literal(value: object, *, subject_attributes: Mapping[str, object]) -> object:
    if isinstance(value, Mapping):
        if set(value) != {"subject"}:
            raise ValidationError("Predicate operands may only reference a trusted subject attribute.")
        attribute = value.get("subject")
        if not isinstance(attribute, str) or not _IDENTIFIER.fullmatch(attribute):
            raise ValidationError("Subject attribute is invalid.")
        if attribute not in subject_attributes:
            raise ValidationError(f"Subject attribute '{attribute}' is unavailable.")
        return subject_attributes[attribute]
    if value is None or isinstance(value, (str, int, float, bool, UUID)):
        return value
    raise ValidationError("Predicate literal type is not supported.")


def validate_predicate(
    predicate: object,
    *,
    allowed_fields: Sequence[str] | None = None,
    max_nodes: int = MAX_PREDICATE_NODES,
    max_depth: int = MAX_PREDICATE_DEPTH,
) -> dict[str, object]:
    """Validate and return the same predicate after enforcing the closed schema."""

    fields = frozenset(allowed_fields) if allowed_fields is not None else None
    count = 0

    def walk(node: object, depth: int) -> None:
        nonlocal count
        count += 1
        if count > max_nodes or depth > max_depth:
            raise ValidationError("Predicate exceeds the safe complexity limit.")
        if not isinstance(node, Mapping):
            raise ValidationError("Every predicate node must be an object.")
        operation = node.get("op")
        if operation not in _LEAF | _COMPOUND:
            raise ValidationError("Predicate operator is not supported.")
        if operation in {"and", "or"}:
            if set(node) != {"op", "args"} or not _sequence(node.get("args")) or not node["args"]:
                raise ValidationError(f"'{operation}' requires a non-empty args array.")
            for child in node["args"]:
                walk(child, depth + 1)
            return
        if operation == "not":
            if set(node) != {"op", "arg"}:
                raise ValidationError("'not' requires exactly one arg.")
            walk(node["arg"], depth + 1)
            return
        field = _field(node.get("field"), allowed_fields=fields)
        del field
        expected = {"op", "field"}
        if operation in {"eq", "in"}:
            expected.add("value")
        if set(node) != expected:
            raise ValidationError(f"'{operation}' predicate has unexpected or missing keys.")
        if operation == "in":
            values = node.get("value")
            if not _sequence(values) or not values or len(values) > MAX_IN_VALUES:
                raise ValidationError("'in' requires 1 to 100 literal values.")
            for value in values:
                _literal(value, subject_attributes={}) if not isinstance(value, Mapping) else None
        elif operation == "eq" and not isinstance(node.get("value"), Mapping):
            _literal(node.get("value"), subject_attributes={})

    walk(predicate, 1)
    return dict(predicate)  # type: ignore[arg-type]


def compile_predicate(
    predicate: object,
    *,
    allowed_fields: Sequence[str],
    subject_attributes: Mapping[str, object],
    tenant_id: UUID,
) -> Q:
    """Compile a validated predicate into a Django ``Q`` expression."""

    validate_predicate(predicate, allowed_fields=allowed_fields)
    fields = frozenset(allowed_fields)

    def compile_node(node: Mapping[str, object]) -> Q:
        operation = str(node["op"])
        if operation == "and":
            result = Q()
            for child in node["args"]:  # type: ignore[union-attr]
                result &= compile_node(child)
            return result
        if operation == "or":
            result = Q(pk__in=[])
            for child in node["args"]:  # type: ignore[union-attr]
                result |= compile_node(child)
            return result
        if operation == "not":
            return ~compile_node(node["arg"])  # type: ignore[arg-type]
        field = _field(node["field"], allowed_fields=fields)
        if operation == "tenant":
            return Q(**{field: tenant_id})
        if operation == "owner":
            if "id" not in subject_attributes:
                return Q(pk__in=[])
            return Q(**{field: subject_attributes["id"]})
        if operation == "is_null":
            return Q(**{f"{field}__isnull": True})
        if operation == "eq":
            return Q(**{field: _literal(node["value"], subject_attributes=subject_attributes)})
        values = [
            _literal(item, subject_attributes=subject_attributes) for item in node["value"]  # type: ignore[union-attr]
        ]
        return Q(**{f"{field}__in": values})

    return compile_node(predicate)  # type: ignore[arg-type]


def predicate_matches(
    predicate: object,
    *,
    record: Mapping[str, object],
    allowed_fields: Sequence[str],
    subject_attributes: Mapping[str, object],
    tenant_id: UUID,
) -> bool:
    """Evaluate the same DSL against a bounded attribute mapping for previews."""

    validate_predicate(predicate, allowed_fields=allowed_fields)

    def evaluate(node: Mapping[str, object]) -> bool:
        operation = str(node["op"])
        if operation == "and":
            return all(evaluate(item) for item in node["args"])  # type: ignore[union-attr]
        if operation == "or":
            return any(evaluate(item) for item in node["args"])  # type: ignore[union-attr]
        if operation == "not":
            return not evaluate(node["arg"])  # type: ignore[arg-type]
        field = str(node["field"])
        actual = record.get(field)
        if operation == "tenant":
            return str(actual) == str(tenant_id)
        if operation == "owner":
            return "id" in subject_attributes and str(actual) == str(subject_attributes["id"])
        if operation == "is_null":
            return actual is None
        if operation == "eq":
            return actual == _literal(node["value"], subject_attributes=subject_attributes)
        return actual in [
            _literal(item, subject_attributes=subject_attributes) for item in node["value"]  # type: ignore[union-attr]
        ]

    return evaluate(predicate)  # type: ignore[arg-type]


__all__ = ["compile_predicate", "predicate_matches", "validate_predicate"]
