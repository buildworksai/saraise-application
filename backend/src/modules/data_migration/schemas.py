"""Fail-closed discriminated configuration schemas."""

from __future__ import annotations

import re
from collections.abc import Mapping

SOURCE_ALLOWED = {
    "csv": {"delimiter", "encoding", "header_row", "batch_size"}, "excel": {"sheet", "header_row", "batch_size"},
    "json": {"encoding", "json_path", "batch_size"}, "xml": {"encoding", "record_path", "batch_size"},
    "database": {"connection_id", "table", "columns", "filters", "batch_size"},
    "api": {"connection_id", "relative_path", "method", "query_parameters", "results_path", "page_parameter", "page_size_parameter", "page_size", "max_pages", "batch_size"},
}
TRANSFORMS = {"identity", "cast", "default", "lookup", "concat", "split", "regex_replace", "date_parse", "boolean_map"}
RULES = {"required", "type", "range", "length", "regex", "unique", "referential", "allowed_values"}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping): raise ValueError(f"{name} must be an object")
    return dict(value)


def _only(values: dict[str, object], allowed: set[str], name: str) -> None:
    unknown = set(values) - allowed
    if unknown: raise ValueError(f"{name} contains unsupported fields: {', '.join(sorted(unknown))}")


def _batch(values: dict[str, object]) -> None:
    value = values.get("batch_size", 500)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000: raise ValueError("batch_size must be between 1 and 10000")
    values["batch_size"] = value


def validate_source_config(source_type: str, config: object) -> dict[str, object]:
    if source_type not in SOURCE_ALLOWED: raise ValueError(f"Unsupported source type: {source_type}")
    values = _object(config, "source_config"); _only(values, SOURCE_ALLOWED[source_type], "source_config"); _batch(values)
    if source_type in ("database", "api") and not values.get("connection_id"): raise ValueError("connection_id is required")
    if source_type == "database":
        if not IDENTIFIER.fullmatch(str(values.get("table", ""))): raise ValueError("table must be a safe identifier")
        columns = values.get("columns", [])
        if not isinstance(columns, list) or not columns or any(not IDENTIFIER.fullmatch(str(item)) for item in columns): raise ValueError("columns must be safe identifiers")
        if not isinstance(values.get("filters", {}), (dict, list)): raise ValueError("filters must contain equality filters")
    if source_type == "api":
        path = values.get("relative_path", "")
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "://" in path: raise ValueError("relative_path must be a relative absolute-path reference")
        if values.get("method", "GET") != "GET": raise ValueError("Only GET is supported")
        pages = values.get("max_pages", 1)
        if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 1000: raise ValueError("max_pages must be between 1 and 1000")
    return values


def validate_transform_config(transform_type: str, config: object) -> dict[str, object]:
    if transform_type not in TRANSFORMS: raise ValueError(f"Unsupported transform type: {transform_type}")
    values = _object(config, "transform_config")
    required = {"cast": {"to"}, "default": {"value"}, "concat": {"fields"}, "split": {"separator"}, "regex_replace": {"pattern"}, "date_parse": {"format"}, "boolean_map": {"true_values", "false_values"}}.get(transform_type, set())
    if not required <= set(values): raise ValueError(f"{transform_type} requires: {', '.join(sorted(required))}")
    if transform_type == "regex_replace": _validate_regex(values.get("pattern"))
    return values


def _validate_regex(pattern: object) -> None:
    if not isinstance(pattern, str) or len(pattern) > 256: raise ValueError("regex pattern must be at most 256 characters")
    if re.search(r"(\([^)]*[+*][^)]*\))[+*{]", pattern): raise ValueError("nested regex quantifiers are forbidden")
    try: re.compile(pattern)
    except re.error as exc: raise ValueError("invalid regex pattern") from exc


def validate_rule_config(rule_type: str, config: object) -> dict[str, object]:
    if rule_type not in RULES: raise ValueError(f"Unsupported rule type: {rule_type}")
    values = _object(config, "rule_config")
    required = {"type": {"type"}, "regex": {"pattern"}, "allowed_values": {"values"}, "referential": {"entity", "field"}}.get(rule_type, set())
    if not required <= set(values): raise ValueError(f"{rule_type} requires: {', '.join(sorted(required))}")
    if rule_type == "regex": _validate_regex(values.get("pattern"))
    if rule_type in ("range", "length") and values.get("min") is None and values.get("max") is None: raise ValueError(f"{rule_type} requires min or max")
    if rule_type == "allowed_values" and (not isinstance(values.get("values"), list) or len(values["values"]) > 1000): raise ValueError("allowed_values requires a bounded list")
    return values

__all__ = ["validate_rule_config", "validate_source_config", "validate_transform_config"]
