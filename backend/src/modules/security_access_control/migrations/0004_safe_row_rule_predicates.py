"""Replace free-form row criteria with a validated predicate AST."""

from __future__ import annotations

import json
import re

from django.db import migrations, models

FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
SUBJECT_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{0,99}$")
ALLOWED_OPS = frozenset({"and", "or", "not", "eq", "in", "is_null", "owner", "tenant"})
MAX_DEPTH = 8
MAX_NODES = 64
MAX_LIST_VALUES = 100


def _field(value: object) -> bool:
    return isinstance(value, str) and "__" not in value and FIELD_PATTERN.fullmatch(value) is not None


def _scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def validate_predicate(node: object, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_NODES or depth > MAX_DEPTH:
        raise ValueError("predicate exceeds complexity limits")
    if not isinstance(node, dict) or not isinstance(node.get("op"), str):
        raise ValueError("each predicate node must be an object with an op")
    op = node["op"]
    if op not in ALLOWED_OPS:
        raise ValueError(f"unsupported predicate operator {op!r}")

    if op in {"and", "or"}:
        if set(node) != {"op", "args"} or not isinstance(node["args"], list) or not node["args"]:
            raise ValueError(f"{op} requires a non-empty args array")
        for child in node["args"]:
            validate_predicate(child, depth=depth + 1, counter=counter)
        return
    if op == "not":
        if set(node) != {"op", "arg"}:
            raise ValueError("not requires exactly one arg")
        validate_predicate(node["arg"], depth=depth + 1, counter=counter)
        return
    if op in {"is_null", "owner", "tenant"}:
        if set(node) != {"op", "field"} or not _field(node["field"]):
            raise ValueError(f"{op} requires one registered-style field name")
        return
    if set(node) != {"op", "field", "value"} or not _field(node["field"]):
        raise ValueError(f"{op} requires field and value")
    value = node["value"]
    if op == "in":
        if (
            not isinstance(value, list)
            or not value
            or len(value) > MAX_LIST_VALUES
            or not all(_scalar(v) for v in value)
        ):
            raise ValueError("in value must be a bounded non-empty scalar array")
        return
    if isinstance(value, dict):
        if (
            set(value) != {"subject"}
            or not isinstance(value["subject"], str)
            or not SUBJECT_PATTERN.fullmatch(value["subject"])
        ):
            raise ValueError("trusted subject operands use {'subject': '<registered.attribute>'}")
    elif not _scalar(value):
        raise ValueError("eq value must be scalar or a trusted subject operand")


def parse_legacy_predicates(apps, schema_editor) -> None:
    del schema_editor
    RowSecurityRule = apps.get_model("security_access_control", "RowSecurityRule")
    failures: list[str] = []
    parsed: list[tuple[object, dict[str, object]]] = []
    for rule in RowSecurityRule.objects.order_by("id").iterator():
        try:
            value = json.loads(rule.legacy_filter_criteria)
            validate_predicate(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            failures.append(str(rule.id))
        else:
            parsed.append((rule, value))
    if failures:
        raise RuntimeError("Unsafe or unparsable RowSecurityRule criteria. Offending IDs: " + ", ".join(failures[:25]))
    for rule, value in parsed:
        rule.filter_criteria = value
        rule.save(update_fields=["filter_criteria"])


def serialize_predicates(apps, schema_editor) -> None:
    del schema_editor
    RowSecurityRule = apps.get_model("security_access_control", "RowSecurityRule")
    for rule in RowSecurityRule.objects.order_by("id").iterator():
        validate_predicate(rule.filter_criteria)
        rule.legacy_filter_criteria = json.dumps(
            rule.filter_criteria,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        rule.save(update_fields=["legacy_filter_criteria"])


class Migration(migrations.Migration):
    dependencies = [("security_access_control", "0003_normalize_permission_sets")]

    operations = [
        migrations.RenameField(
            model_name="rowsecurityrule",
            old_name="filter_criteria",
            new_name="legacy_filter_criteria",
        ),
        migrations.AlterField(
            model_name="rowsecurityrule",
            name="legacy_filter_criteria",
            field=models.TextField(null=True),
        ),
        migrations.AddField(
            model_name="rowsecurityrule",
            name="filter_criteria",
            field=models.JSONField(null=True),
        ),
        migrations.RunPython(parse_legacy_predicates, serialize_predicates),
        migrations.AlterField(
            model_name="rowsecurityrule",
            name="filter_criteria",
            field=models.JSONField(default=dict),
        ),
    ]
