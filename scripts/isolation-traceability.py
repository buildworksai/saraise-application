#!/usr/bin/env python3
"""Inventory routed Django endpoints and enforce tenant-isolation traceability.

The URLconf is the authority: this gate recursively walks resolved URL patterns,
including DRF ViewSets and custom actions, APIViews, DRF function views, and
plain Django functions.  Tenant-touching or unresolved endpoints must match an
``isolation_contract`` whose test exists and contains real pytest tests.

Exit codes are fail-closed: 0 means every required contract is present; 1 means
coverage, model typing, or manifest integrity is incomplete; 2 means discovery
could not run.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import inspect
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
DEFAULT_MANIFEST = Path(__file__).with_name("isolation-contracts.json")

STANDARD_VIEWSET_ACTIONS = {
    "list",
    "retrieve",
    "create",
    "update",
    "partial_update",
    "destroy",
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


@dataclass(frozen=True)
class ModelTrace:
    """Tenant classification for a model used by an endpoint."""

    label: str
    scope: str
    tenant_field_type: str | None = None
    tenant_indexed: bool | None = None
    relations: tuple[str, ...] = ()


@dataclass(frozen=True)
class EndpointTrace:
    """Stable routed-endpoint inventory record."""

    id: str
    kind: str
    routes: tuple[str, ...]
    names: tuple[str, ...]
    methods: tuple[str, ...]
    view: str
    models: tuple[ModelTrace, ...] = ()
    tenancy: str = "unknown"
    contract: str | None = None


@dataclass(frozen=True)
class TaskTrace:
    """Static inventory record for a tenant-aware worker task."""

    id: str
    path: str
    line: int
    tenancy: str


@dataclass(frozen=True)
class Finding:
    """A deterministic gate failure."""

    code: str
    subject: str
    detail: str


def _fqn(value: Any) -> str:
    module = getattr(value, "__module__", "") or "unknown"
    qualname = getattr(value, "__qualname__", None) or getattr(value, "__name__", "unknown")
    return f"{module}.{qualname}"


def _route_text(prefix: str, pattern: Any) -> str:
    route = f"{prefix}{pattern}"
    route = re.sub(r"\(\?P<format>[^)]+\)", "<format>", route)
    return route.replace("^", "").replace("$", "")


def _callback_class(callback: Any) -> type[Any] | None:
    candidate = getattr(callback, "cls", None) or getattr(callback, "view_class", None)
    return candidate if inspect.isclass(candidate) else None


def _is_decorated_function_view(view_class: type[Any]) -> bool:
    return "WrappedAPIView" in getattr(view_class, "__qualname__", "")


def _view_methods(callback: Any, view_class: type[Any] | None) -> tuple[str, ...]:
    actions = getattr(callback, "actions", None)
    if isinstance(actions, Mapping):
        return tuple(sorted(str(method).upper() for method in actions if method.lower() in HTTP_METHODS))
    if view_class is not None:
        methods = []
        for method in getattr(view_class, "http_method_names", ()):
            if method in HTTP_METHODS and callable(getattr(view_class, method, None)):
                methods.append(method.upper())
        return tuple(sorted(methods))
    allowed = getattr(callback, "allowed_methods", ())
    return tuple(sorted(str(method).upper() for method in allowed))


def _endpoint_parts(callback: Any) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Return ``(id, kind, view, methods)`` records for one URL callback."""
    view_class = _callback_class(callback)
    actions = getattr(callback, "actions", None)
    if view_class is not None and isinstance(actions, Mapping):
        view = _fqn(view_class)
        standard_methods = tuple(
            sorted(method.upper() for method, action_name in actions.items() if action_name in STANDARD_VIEWSET_ACTIONS)
        )
        parts = []
        if standard_methods:
            parts.append((view, "viewset", view, standard_methods))
        for action_name in sorted(set(actions.values()) - STANDARD_VIEWSET_ACTIONS):
            methods = tuple(sorted(method.upper() for method, mapped in actions.items() if mapped == action_name))
            parts.append((f"{view}#{action_name}", "action", view, methods))
        return parts

    if view_class is not None:
        kind = "function" if _is_decorated_function_view(view_class) else "apiview"
        view = _fqn(view_class) if kind == "apiview" else _fqn(callback)
        return [(view, kind, view, _view_methods(callback, view_class))]

    view = _fqn(callback)
    return [(view, "function", view, _view_methods(callback, None))]


def discover_from_patterns(patterns: Iterable[Any], prefix: str = "") -> list[EndpointTrace]:
    """Recursively discover endpoint shapes from URLPattern-like objects."""
    discovered: dict[str, EndpointTrace] = {}
    for pattern in patterns:
        nested = getattr(pattern, "url_patterns", None)
        if nested is not None:
            nested_prefix = _route_text(prefix, getattr(pattern, "pattern", ""))
            for endpoint in discover_from_patterns(nested, nested_prefix):
                _merge_endpoint(discovered, endpoint)
            continue

        callback = getattr(pattern, "callback", None)
        if callback is None:
            continue
        route = _route_text(prefix, getattr(pattern, "pattern", ""))
        name = str(getattr(pattern, "name", "") or "")
        for endpoint_id, kind, view, methods in _endpoint_parts(callback):
            endpoint = EndpointTrace(
                id=endpoint_id,
                kind=kind,
                routes=(route,),
                names=(name,) if name else (),
                methods=methods,
                view=view,
            )
            _merge_endpoint(discovered, endpoint)
    return sorted(discovered.values(), key=lambda endpoint: endpoint.id)


def _merge_endpoint(target: dict[str, EndpointTrace], incoming: EndpointTrace) -> None:
    current = target.get(incoming.id)
    if current is None:
        target[incoming.id] = incoming
        return
    target[incoming.id] = replace(
        current,
        routes=tuple(sorted(set(current.routes + incoming.routes))),
        names=tuple(sorted(set(current.names + incoming.names))),
        methods=tuple(sorted(set(current.methods + incoming.methods))),
    )


def _bootstrap_django(root_urlconf: str) -> Sequence[Any]:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "saraise_backend.settings")
    os.environ.setdefault("DJANGO_USE_SQLITE_FOR_TESTS", "1")
    import django
    from django.urls import get_resolver

    django.setup()
    return get_resolver(root_urlconf).url_patterns


def _model_from_view(view_class: type[Any]) -> set[type[Any]]:
    models: set[type[Any]] = set()
    queryset = getattr(view_class, "queryset", None)
    model = getattr(queryset, "model", None)
    if inspect.isclass(model):
        models.add(model)
    serializer = getattr(view_class, "serializer_class", None)
    serializer_model = getattr(getattr(serializer, "Meta", None), "model", None)
    if inspect.isclass(serializer_model):
        models.add(serializer_model)
    return models


def _source_for(value: Any) -> str:
    try:
        return inspect.getsource(value)
    except (OSError, TypeError):
        return ""


def _models_from_source(value: Any, source: str) -> set[type[Any]]:
    module = inspect.getmodule(value)
    if not isinstance(module, ModuleType):
        return set()
    referenced = set()
    for name, candidate in vars(module).items():
        if inspect.isclass(candidate) and hasattr(candidate, "_meta"):
            if re.search(rf"\b{re.escape(name)}\b", source):
                referenced.add(candidate)
    return referenced


def _trace_model(model: type[Any]) -> ModelTrace:
    meta = model._meta
    label = getattr(meta, "label", _fqn(model))
    relations = []
    for field in meta.get_fields():
        related = getattr(field, "related_model", None)
        if related is not None and not getattr(field, "auto_created", False):
            relations.append(getattr(related._meta, "label", _fqn(related)))
    try:
        tenant_field = meta.get_field("tenant_id")
    except Exception:
        return ModelTrace(label=label, scope="global", relations=tuple(sorted(set(relations))))

    field_type = tenant_field.__class__.__name__
    target_field = getattr(tenant_field, "target_field", None)
    if getattr(tenant_field, "name", "tenant_id") != "tenant_id":
        return ModelTrace(
            label=label,
            scope="related",
            tenant_field_type=(target_field.__class__.__name__ if target_field is not None else field_type),
            tenant_indexed=bool(getattr(tenant_field, "db_index", False)),
            relations=tuple(sorted(set(relations))),
        )
    if field_type == "ForeignKey" and target_field is not None:
        field_type = target_field.__class__.__name__
    indexed = bool(getattr(tenant_field, "db_index", False) or getattr(tenant_field, "unique", False))
    return ModelTrace(
        label=label,
        scope="tenant",
        tenant_field_type=field_type,
        tenant_indexed=indexed,
        relations=tuple(sorted(set(relations))),
    )


def attach_model_traces(endpoints: Iterable[EndpointTrace]) -> list[EndpointTrace]:
    """Map endpoints to direct models and classify tenancy conservatively."""
    traced = []
    for endpoint in endpoints:
        value = _import_fqn(endpoint.view.split("#", 1)[0])
        view_class = value if inspect.isclass(value) else _callback_class(value)
        source_target = view_class or value
        models = _model_from_view(view_class) if view_class is not None else set()
        source = _source_for(source_target)
        models.update(_models_from_source(source_target, source))
        model_traces = tuple(sorted((_trace_model(model) for model in models), key=lambda item: item.label))
        if any(model.scope == "tenant" for model in model_traces):
            tenancy = "tenant"
        elif model_traces:
            tenancy = "global"
        elif "tenant_id" in source or "get_user_tenant_id" in source:
            tenancy = "tenant"
        else:
            tenancy = "unknown"
        traced.append(replace(endpoint, models=model_traces, tenancy=tenancy))
    return traced


def _import_fqn(fqn: str) -> Any:
    parts = fqn.split(".")
    for index in range(len(parts), 0, -1):
        module_name = ".".join(parts[:index])
        try:
            module = __import__(module_name, fromlist=["*"])
        except (ImportError, AttributeError):
            continue
        value = module
        try:
            for part in parts[index:]:
                value = getattr(value, part)
        except AttributeError:
            return None
        return value
    return None


def discover_tasks(source_root: Path = BACKEND_ROOT / "src") -> list[TaskTrace]:
    """Inventory decorated worker tasks without importing queue infrastructure."""
    tasks = []
    for path in sorted(source_root.rglob("*.py")):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        try:
            relative_module = path.relative_to(BACKEND_ROOT)
        except ValueError:
            relative_module = path.relative_to(source_root.parent)
        module = ".".join(relative_module.with_suffix("").parts)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decorators = {ast.unparse(decorator) for decorator in node.decorator_list}
            if not any(
                re.search(r"(^|\.)(shared_task|task|tenant_context_worker)(\(|$)", decorator)
                for decorator in decorators
            ):
                continue
            source = ast.get_source_segment(path.read_text(encoding="utf-8"), node) or ""
            tenancy = "tenant" if "tenant_id" in source or "tenant_context_worker" in source else "unknown"
            try:
                display_path = path.relative_to(REPO_ROOT)
            except ValueError:
                display_path = path.relative_to(source_root.parent)
            tasks.append(
                TaskTrace(
                    id=f"{module}.{node.name}",
                    path=str(display_path),
                    line=node.lineno,
                    tenancy=tenancy,
                )
            )
    return tasks


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("contracts"), list):
        raise ValueError("isolation manifest must have version 1 and a contracts list")
    return data


def _matching_entry(entries: Iterable[Mapping[str, Any]], endpoint_id: str) -> Mapping[str, Any] | None:
    matches = [entry for entry in entries if fnmatch.fnmatchcase(endpoint_id, str(entry.get("selector", "")))]
    if len(matches) > 1:
        matches.sort(key=lambda item: len(str(item.get("selector", ""))), reverse=True)
    return matches[0] if matches else None


def _contract_path(entry: Mapping[str, Any], endpoint_id: str, repo_root: Path) -> Path | None:
    raw_path = entry.get("test") or entry.get("test_template")
    if not isinstance(raw_path, str):
        return None
    parts = endpoint_id.split(".")
    module = parts[2] if len(parts) > 2 and parts[:2] == ["src", "modules"] else ""
    return repo_root / raw_path.format(module=module)


def _contains_real_tests(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        for node in ast.walk(tree)
    )


def validate_traceability(
    endpoints: Iterable[EndpointTrace],
    tasks: Iterable[TaskTrace],
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> tuple[list[EndpointTrace], list[Finding]]:
    """Attach contracts and return every fail-closed finding."""
    findings = []
    validated = []
    contracts = manifest.get("contracts", [])
    exemptions = manifest.get("exemptions", [])
    model_exemptions = {str(entry.get("label")) for entry in manifest.get("model_exemptions", [])}
    matched_selectors = set()

    for endpoint in endpoints:
        entry = _matching_entry(contracts, endpoint.id)
        exemption = _matching_entry(exemptions, endpoint.id)
        requires_contract = endpoint.tenancy in {"tenant", "unknown"} and exemption is None
        if requires_contract and entry is None:
            findings.append(
                Finding(
                    "missing_contract",
                    endpoint.id,
                    f"{endpoint.tenancy} endpoint has no isolation_contract",
                )
            )
            validated.append(endpoint)
            continue
        if entry is None:
            validated.append(endpoint)
            continue

        selector = str(entry.get("selector"))
        matched_selectors.add(selector)
        contract_path = _contract_path(entry, endpoint.id, repo_root)
        if not entry.get("isolation_contract"):
            findings.append(
                Finding(
                    "invalid_contract",
                    endpoint.id,
                    "contract has no isolation_contract marker",
                )
            )
        elif contract_path is None:
            findings.append(Finding("invalid_contract", endpoint.id, "contract has no test path"))
        elif not contract_path.is_file():
            findings.append(Finding("missing_test", endpoint.id, str(contract_path)))
        elif not _contains_real_tests(contract_path):
            findings.append(Finding("empty_test", endpoint.id, f"no pytest tests in {contract_path}"))
        contract_label = str(contract_path.relative_to(repo_root)) if contract_path else None
        validated.append(replace(endpoint, contract=contract_label))

        for model in endpoint.models:
            if (
                model.scope == "tenant"
                and model.label not in model_exemptions
                and (model.tenant_field_type != "UUIDField" or model.tenant_indexed is not True)
            ):
                findings.append(
                    Finding(
                        "invalid_tenant_model",
                        model.label,
                        f"tenant_id is {model.tenant_field_type}, indexed={model.tenant_indexed}",
                    )
                )

    for task in tasks:
        if task.tenancy in {"tenant", "unknown"} and _matching_entry(contracts, task.id) is None:
            findings.append(
                Finding(
                    "missing_task_contract",
                    task.id,
                    f"{task.tenancy} worker task is uncovered",
                )
            )

    for entry in contracts:
        selector = str(entry.get("selector", ""))
        if "*" not in selector and selector not in matched_selectors:
            findings.append(
                Finding(
                    "stale_contract",
                    selector,
                    "manifest entry matches no routed endpoint",
                )
            )

    return validated, sorted(findings, key=lambda item: (item.code, item.subject, item.detail))


def run_self_test() -> bool:
    """Exercise APIView/function discovery and missing-coverage failure in memory."""

    class Pattern:
        def __init__(self, route: str, callback: Any, name: str) -> None:
            self.pattern = route
            self.callback = callback
            self.name = name

    class DemoAPIView:
        http_method_names = ["get"]

        def get(self):
            return None

    def api_callback():
        return None

    api_callback.view_class = DemoAPIView  # type: ignore[attr-defined]

    def function_callback():
        return None

    endpoints = discover_from_patterns(
        [
            Pattern("api/", api_callback, "api"),
            Pattern("function/", function_callback, "function"),
        ]
    )
    kinds = {endpoint.kind for endpoint in endpoints}
    uncovered = [replace(endpoints[0], tenancy="tenant")]
    _, findings = validate_traceability(uncovered, [], {"contracts": [], "exemptions": []})
    return kinds == {"apiview", "function"} and any(finding.code == "missing_contract" for finding in findings)


def _json_report(
    endpoints: Iterable[EndpointTrace],
    tasks: Iterable[TaskTrace],
    findings: Iterable[Finding],
) -> str:
    return json.dumps(
        {
            "endpoints": [asdict(endpoint) for endpoint in endpoints],
            "tasks": [asdict(task) for task in tasks],
            "findings": [asdict(finding) for finding in findings],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-urlconf", default="saraise_backend.urls")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        passed = run_self_test()
        print("isolation traceability self-test: PASS" if passed else "isolation traceability self-test: FAIL")
        return 0 if passed else 1

    try:
        patterns = _bootstrap_django(args.root_urlconf)
        endpoints = attach_model_traces(discover_from_patterns(patterns))
        tasks = discover_tasks()
        manifest = load_manifest(args.manifest)
        endpoints, findings = validate_traceability(endpoints, tasks, manifest)
    except Exception as exc:
        print(f"isolation traceability discovery failed: {exc}", file=sys.stderr)
        return 2

    if args.as_json:
        print(_json_report(endpoints, tasks, findings))
    else:
        viewsets = sum(endpoint.kind == "viewset" for endpoint in endpoints)
        actions = sum(endpoint.kind == "action" for endpoint in endpoints)
        api_views = sum(endpoint.kind == "apiview" for endpoint in endpoints)
        functions = sum(endpoint.kind == "function" for endpoint in endpoints)
        print(
            "Isolation traceability: "
            f"{len(endpoints)} endpoints "
            f"({viewsets} ViewSets, {actions} actions, {api_views} APIViews, {functions} functions), "
            f"{len(tasks)} tasks"
        )
        for finding in findings:
            print(f"ERROR {finding.code}: {finding.subject}: {finding.detail}")
        print("PASS: all tenant-touching endpoints have isolation contracts" if not findings else "FAIL")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
