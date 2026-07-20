"""High-coverage tests for the URLconf isolation traceability gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def traceability():
    script = Path(__file__).resolve().parents[5] / "scripts" / "isolation-traceability.py"
    spec = importlib.util.spec_from_file_location("saraise_isolation_traceability", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Pattern:
    def __init__(self, route, callback=None, name=None, url_patterns=None):
        self.pattern = route
        self.callback = callback
        self.name = name
        if url_patterns is not None:
            self.url_patterns = url_patterns


def test_discovers_viewsets_actions_apiviews_and_functions(traceability):
    class DemoViewSet:
        pass

    def list_callback():
        return None

    list_callback.cls = DemoViewSet
    list_callback.actions = {"get": "list", "post": "create"}

    def action_callback():
        return None

    action_callback.cls = DemoViewSet
    action_callback.actions = {"post": "archive"}

    class DemoAPIView:
        http_method_names = ["get", "post", "options"]

        def get(self):
            return None

        def post(self):
            return None

    def api_callback():
        return None

    api_callback.view_class = DemoAPIView

    def function_callback():
        return None

    patterns = [
        Pattern(
            "api/",
            url_patterns=[
                Pattern("resources/", list_callback, "resource-list"),
                Pattern("resources.<format>", list_callback, "resource-list"),
                Pattern("resources/archive/", action_callback, "resource-archive"),
                Pattern("status/", api_callback, "status"),
                Pattern("health/", function_callback, "health"),
            ],
        )
    ]

    endpoints = traceability.discover_from_patterns(patterns)
    by_kind = {endpoint.kind: endpoint for endpoint in endpoints}

    assert {endpoint.kind for endpoint in endpoints} == {
        "viewset",
        "action",
        "apiview",
        "function",
    }
    assert by_kind["viewset"].methods == ("GET", "POST")
    assert len(by_kind["viewset"].routes) == 2
    assert by_kind["action"].id.endswith("DemoViewSet#archive")
    assert by_kind["apiview"].methods == ("GET", "POST")
    assert by_kind["function"].routes == ("api/health/",)


def test_discovers_drf_decorated_function_shape(traceability):
    class WrappedAPIView:
        http_method_names = ["get"]

        def get(self):
            return None

    WrappedAPIView.__qualname__ = "api_view.<locals>.decorator.<locals>.WrappedAPIView"

    def callback():
        return None

    callback.view_class = WrappedAPIView
    endpoints = traceability.discover_from_patterns([Pattern("health/", callback, "health")])

    assert endpoints[0].kind == "function"
    assert endpoints[0].methods == ("GET",)


def test_discovery_skips_non_endpoint_pattern_and_allowed_methods(traceability):
    def callback():
        return None

    callback.allowed_methods = ["post", "get"]
    endpoints = traceability.discover_from_patterns([Pattern("ignored/"), Pattern("function/", callback)])

    assert len(endpoints) == 1
    assert endpoints[0].methods == ("GET", "POST")


def test_model_trace_requires_indexed_uuid_tenant_field(traceability):
    class UUIDField:
        db_index = True
        unique = False

    class CharField:
        db_index = False
        unique = False

    class Meta:
        label = "demo.Record"

        def __init__(self, field):
            self.field = field

        def get_field(self, name):
            if name != "tenant_id":
                raise LookupError(name)
            return self.field

        def get_fields(self):
            return [SimpleNamespace(related_model=None, auto_created=False)]

    good_model = type("Good", (), {"_meta": Meta(UUIDField())})
    bad_model = type("Bad", (), {"_meta": Meta(CharField())})

    good = traceability._trace_model(good_model)
    bad = traceability._trace_model(bad_model)

    assert (good.scope, good.tenant_field_type, good.tenant_indexed) == (
        "tenant",
        "UUIDField",
        True,
    )
    assert (bad.tenant_field_type, bad.tenant_indexed) == ("CharField", False)


def test_model_trace_records_global_models_and_relations(traceability):
    related_meta = SimpleNamespace(label="demo.Parent")
    related = type("Parent", (), {"_meta": related_meta})

    class Meta:
        label = "demo.Global"

        @staticmethod
        def get_field(name):
            raise LookupError(name)

        @staticmethod
        def get_fields():
            return [SimpleNamespace(related_model=related, auto_created=False)]

    model = type("Global", (), {"_meta": Meta()})
    result = traceability._trace_model(model)

    assert result.scope == "global"
    assert result.relations == ("demo.Parent",)


def test_model_trace_accepts_uuid_foreign_key_tenant_relation(traceability):
    UUIDField = type("UUIDField", (), {})
    ForeignKey = type(
        "ForeignKey",
        (),
        {
            "name": "tenant",
            "db_index": True,
            "unique": False,
            "target_field": UUIDField(),
        },
    )

    class Meta:
        label = "demo.RelatedTenant"

        @staticmethod
        def get_field(name):
            return ForeignKey()

        @staticmethod
        def get_fields():
            return []

    model = type("RelatedTenant", (), {"_meta": Meta()})

    traced = traceability._trace_model(model)
    assert traced.scope == "related"
    assert traced.tenant_field_type == "UUIDField"


def test_model_resolution_from_view_serializer_and_source(traceability, monkeypatch):
    class Meta:
        label = "demo.Model"

        @staticmethod
        def get_field(name):
            raise LookupError(name)

        @staticmethod
        def get_fields():
            return []

    model = type("Record", (), {"_meta": Meta()})
    serializer = type("Serializer", (), {"Meta": type("SerializerMeta", (), {"model": model})})
    view = type(
        "View",
        (),
        {"queryset": SimpleNamespace(model=model), "serializer_class": serializer},
    )
    assert traceability._model_from_view(view) == {model}

    module = ModuleType("demo_source_module")
    module.Record = model

    def handler():
        return None

    handler.__module__ = module.__name__
    module.handler = handler
    monkeypatch.setitem(sys.modules, module.__name__, module)
    monkeypatch.setattr(traceability.inspect, "getmodule", lambda unused: module)
    assert traceability._models_from_source(handler, "Record.objects.all()") == {model}
    assert traceability._models_from_source(None, "Record") == {model}
    monkeypatch.setattr(traceability.inspect, "getmodule", lambda unused: None)
    assert traceability._models_from_source(handler, "Record") == set()
    assert traceability._source_for(object()) == ""


@pytest.mark.parametrize(
    ("models", "source", "expected"),
    [
        ([], "tenant_id = value", "tenant"),
        ([], "return public_status", "unknown"),
    ],
)
def test_attach_model_traces_classifies_source_signals(traceability, monkeypatch, models, source, expected):
    view = type("View", (), {})
    endpoint = traceability.EndpointTrace("demo.View", "apiview", ("demo/",), (), ("GET",), "demo.View")
    monkeypatch.setattr(traceability, "_import_fqn", lambda unused: view)
    monkeypatch.setattr(traceability, "_model_from_view", lambda unused: set(models))
    monkeypatch.setattr(traceability, "_source_for", lambda unused: source)
    monkeypatch.setattr(traceability, "_models_from_source", lambda *unused: set())

    assert traceability.attach_model_traces([endpoint])[0].tenancy == expected


def test_import_fqn_resolves_and_fails_safely(traceability):
    assert traceability._import_fqn("json.dumps") is json.dumps
    assert traceability._import_fqn("json.not_present") is None
    assert traceability._import_fqn("definitely_missing.module.value") is None


def test_validation_fails_closed_without_contract(traceability):
    endpoint = traceability.EndpointTrace(
        id="demo.views.SecretView",
        kind="apiview",
        routes=("secret/",),
        names=("secret",),
        methods=("GET",),
        view="demo.views.SecretView",
        tenancy="tenant",
    )

    _, findings = traceability.validate_traceability([endpoint], [], {"contracts": [], "exemptions": []})

    assert [(finding.code, finding.subject) for finding in findings] == [("missing_contract", endpoint.id)]


def test_validation_accepts_real_test_and_attaches_contract(traceability, tmp_path):
    test_path = tmp_path / "test_isolation.py"
    test_path.write_text("def test_cross_tenant_list():\n    assert True\n", encoding="utf-8")
    endpoint = traceability.EndpointTrace(
        id="demo.views.RecordViewSet",
        kind="viewset",
        routes=("records/",),
        names=(),
        methods=("GET",),
        view="demo.views.RecordViewSet",
        tenancy="tenant",
    )
    manifest = {
        "contracts": [
            {
                "selector": endpoint.id,
                "test": test_path.name,
                "isolation_contract": "list isolation",
            }
        ],
        "exemptions": [],
    }

    validated, findings = traceability.validate_traceability([endpoint], [], manifest, repo_root=tmp_path)

    assert findings == []
    assert validated[0].contract == "test_isolation.py"


@pytest.mark.parametrize(
    ("contract", "expected_code"),
    [
        ({"selector": "demo.*", "isolation_contract": "x"}, "invalid_contract"),
        (
            {"selector": "demo.*", "test": "missing.py", "isolation_contract": "x"},
            "missing_test",
        ),
        (
            {"selector": "demo.*", "test": "empty.py", "isolation_contract": "x"},
            "empty_test",
        ),
        ({"selector": "demo.*", "test": "empty.py"}, "invalid_contract"),
    ],
)
def test_validation_rejects_invalid_contracts(traceability, tmp_path, contract, expected_code):
    (tmp_path / "empty.py").write_text("VALUE = 1\n", encoding="utf-8")
    endpoint = traceability.EndpointTrace(
        id="demo.Endpoint",
        kind="function",
        routes=("demo/",),
        names=(),
        methods=("GET",),
        view="demo.Endpoint",
        tenancy="unknown",
    )
    _, findings = traceability.validate_traceability(
        [endpoint],
        [],
        {"contracts": [contract], "exemptions": []},
        repo_root=tmp_path,
    )

    assert expected_code in {finding.code for finding in findings}


def test_validation_checks_model_type_tasks_stale_entries_and_exemptions(traceability, tmp_path):
    test_path = tmp_path / "test_isolation.py"
    test_path.write_text("def test_isolation():\n    pass\n", encoding="utf-8")
    invalid_model = traceability.ModelTrace(
        label="demo.Bad",
        scope="tenant",
        tenant_field_type="CharField",
        tenant_indexed=False,
    )
    endpoint = traceability.EndpointTrace(
        id="demo.Endpoint",
        kind="function",
        routes=("demo/",),
        names=(),
        methods=("GET",),
        view="demo.Endpoint",
        models=(invalid_model,),
        tenancy="tenant",
    )
    exempt = traceability.EndpointTrace(
        id="framework.Health",
        kind="function",
        routes=("health/",),
        names=(),
        methods=("GET",),
        view="framework.Health",
        tenancy="unknown",
    )
    task = traceability.TaskTrace("demo.tasks.export", "tasks.py", 1, "tenant")
    manifest = {
        "contracts": [
            {
                "selector": endpoint.id,
                "test": test_path.name,
                "isolation_contract": "endpoint",
            },
            {
                "selector": "stale.Endpoint",
                "test": test_path.name,
                "isolation_contract": "stale",
            },
        ],
        "exemptions": [{"selector": "framework.*", "reason": "infrastructure"}],
    }

    _, findings = traceability.validate_traceability([endpoint, exempt], [task], manifest, repo_root=tmp_path)
    codes = {finding.code for finding in findings}

    assert codes == {"invalid_tenant_model", "missing_task_contract", "stale_contract"}


def test_model_exemption_is_audited_in_manifest(traceability, tmp_path):
    test_path = tmp_path / "test.py"
    test_path.write_text("def test_it():\n    pass\n", encoding="utf-8")
    model = traceability.ModelTrace("demo.Identity", "tenant", "CharField", True)
    endpoint = traceability.EndpointTrace(
        "demo.Endpoint",
        "function",
        ("x/",),
        (),
        ("GET",),
        "demo.Endpoint",
        (model,),
        "tenant",
    )
    manifest = {
        "contracts": [{"selector": "demo.*", "test": "test.py", "isolation_contract": "identity"}],
        "exemptions": [],
        "model_exemptions": [{"label": model.label, "reason": "external pointer"}],
    }

    _, findings = traceability.validate_traceability([endpoint], [], manifest, repo_root=tmp_path)

    assert findings == []


def test_discovers_worker_tasks_and_tenancy(traceability, tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "tasks.py").write_text(
        "@shared_task\ndef export(*, tenant_id):\n    return tenant_id\n\n"
        "@task\ndef global_job():\n    return None\n\n"
        "@decorator\ndef helper():\n    return None\n",
        encoding="utf-8",
    )

    tasks = traceability.discover_tasks(source)

    assert [(task.id, task.tenancy) for task in tasks] == [
        ("src.tasks.export", "tenant"),
        ("src.tasks.global_job", "unknown"),
    ]


def test_manifest_loading_and_json_report(traceability, tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "contracts": []}), encoding="utf-8")
    assert traceability.load_manifest(path)["version"] == 1

    path.write_text(json.dumps({"version": 2, "contracts": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="version 1"):
        traceability.load_manifest(path)

    report = json.loads(traceability._json_report([], [], []))
    assert report == {"endpoints": [], "findings": [], "tasks": []}

    invalid = tmp_path / "invalid_test.py"
    invalid.write_text("not valid python !!!", encoding="utf-8")
    assert traceability._contains_real_tests(invalid) is False


def test_matching_prefers_the_most_specific_selector(traceability):
    entries = [
        {"selector": "src.modules.*", "value": "broad"},
        {"selector": "src.modules.crm.*", "value": "specific"},
    ]
    assert traceability._matching_entry(entries, "src.modules.crm.api.Lead")["value"] == "specific"


def test_bootstrap_django_uses_runtime_urlconf(traceability, monkeypatch):
    patterns = [object()]
    fake_django = ModuleType("django")
    setup_calls = []
    fake_django.setup = lambda: setup_calls.append(True)
    fake_urls = ModuleType("django.urls")
    fake_urls.get_resolver = lambda root: SimpleNamespace(url_patterns=patterns if root == "demo.urls" else [])
    monkeypatch.setitem(sys.modules, "django", fake_django)
    monkeypatch.setitem(sys.modules, "django.urls", fake_urls)

    assert traceability._bootstrap_django("demo.urls") == patterns
    assert setup_calls == [True]


def test_self_test_and_cli_self_test(traceability, capsys):
    assert traceability.run_self_test() is True
    assert traceability.main(["--self-test"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_cli_reports_json_human_failures_and_discovery_errors(traceability, monkeypatch, tmp_path, capsys):
    endpoint = traceability.EndpointTrace(
        "demo.Endpoint",
        "apiview",
        ("demo/",),
        (),
        ("GET",),
        "demo.Endpoint",
        tenancy="tenant",
    )
    finding = traceability.Finding("missing_contract", endpoint.id, "missing")
    monkeypatch.setattr(traceability, "_bootstrap_django", lambda unused: [object()])
    monkeypatch.setattr(traceability, "discover_from_patterns", lambda unused: [endpoint])
    monkeypatch.setattr(traceability, "attach_model_traces", lambda unused: [endpoint])
    monkeypatch.setattr(traceability, "discover_tasks", lambda: [])
    monkeypatch.setattr(traceability, "load_manifest", lambda unused: {"contracts": []})
    monkeypatch.setattr(
        traceability,
        "validate_traceability",
        lambda *unused: ([endpoint], [finding]),
    )

    assert traceability.main(["--json", "--manifest", str(tmp_path / "x")]) == 1
    assert json.loads(capsys.readouterr().out)["findings"][0]["code"] == "missing_contract"
    assert traceability.main(["--manifest", str(tmp_path / "x")]) == 1
    assert "1 endpoints" in capsys.readouterr().out

    monkeypatch.setattr(
        traceability,
        "_bootstrap_django",
        lambda unused: (_ for _ in ()).throw(RuntimeError("broken urlconf")),
    )
    assert traceability.main([]) == 2
    assert "broken urlconf" in capsys.readouterr().err
