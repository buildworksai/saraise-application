import sys
import types
from argparse import ArgumentParser

from rest_framework import viewsets
from rest_framework.decorators import action

from src.core.management.commands.generate_api_docs import Command


class DemoViewSet(viewsets.ViewSet):
    """Demo viewset contract."""

    def list(self, request):
        raise NotImplementedError

    def create(self, request):
        raise NotImplementedError

    def retrieve(self, request, pk=None):
        raise NotImplementedError

    def update(self, request, pk=None):
        raise NotImplementedError

    def partial_update(self, request, pk=None):
        raise NotImplementedError

    def destroy(self, request, pk=None):
        raise NotImplementedError

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        raise NotImplementedError

    @action(detail=False, methods=["get"])
    def summary(self, request):
        raise NotImplementedError


def test_argument_parser_declares_supported_options():
    parser = ArgumentParser()
    Command().add_arguments(parser)

    parsed = parser.parse_args(["--module", "crm", "--output-dir", "/tmp/docs"])
    assert parsed.module == "crm"
    assert parsed.output_dir == "/tmp/docs"
    assert parsed.all_modules is False

    parsed = parser.parse_args(["--all-modules"])
    assert parsed.all_modules is True


def test_handle_requires_module_or_all_modules():
    command = Command()
    messages = []
    command.stdout.write = messages.append

    command.handle(module=None, all_modules=False, output_dir=None)

    assert any("Must specify --module or --all-modules" in message for message in messages)


def test_generate_module_docs_import_error_is_reported_without_raising():
    command = Command()
    messages = []
    command.stdout.write = messages.append

    command.generate_module_docs("does_not_exist")

    assert any("Failed to import does_not_exist" in message for message in messages)


def test_generate_module_docs_reports_empty_viewset_module(monkeypatch, tmp_path):
    module = types.ModuleType("src.modules.empty_module.api")
    monkeypatch.setitem(sys.modules, "src.modules.empty_module.api", module)
    command = Command()
    messages = []
    command.stdout.write = messages.append

    command.generate_module_docs("empty_module", str(tmp_path))

    assert any("No ViewSets found in empty_module" in message for message in messages)
    assert not list(tmp_path.rglob("API.md"))


def test_generate_module_docs_writes_documented_viewset(monkeypatch, tmp_path):
    module = types.ModuleType("src.modules.demo_module.api")
    module.DemoViewSet = DemoViewSet
    monkeypatch.setitem(sys.modules, "src.modules.demo_module.api", module)
    command = Command()
    messages = []
    command.stdout.write = messages.append
    monkeypatch.setattr(command, "_get_current_date", lambda: "2026-08-03")

    command.generate_module_docs("demo_module", str(tmp_path))

    output = tmp_path / "demo-module" / "API.md"
    content = output.read_text()
    assert "# DemoModule - API Documentation" in content
    assert "**Last Updated:** 2026-08-03" in content
    assert "Demo viewset contract." in content
    assert "#### GET /api/v1/demo-module/resources/" in content
    assert "#### POST /api/v1/demo-module/resources/{id}/approve/" in content
    assert "#### GET /api/v1/demo-module/resources/summary/" in content
    assert any("Generated" in message for message in messages)


def test_generate_all_modules_delegates_every_known_foundation_module(monkeypatch):
    command = Command()
    generated = []
    command.stdout.write = lambda _message: None
    monkeypatch.setattr(command, "generate_module_docs", generated.append)

    command.generate_all_modules()

    assert generated[:3] == ["workflow_automation", "api_management", "integration_platform"]
    assert "regional" in generated
    assert len(generated) == len(set(generated))


def test_find_viewsets_and_doc_helpers_cover_standard_and_custom_actions(monkeypatch):
    module = types.SimpleNamespace(DemoViewSet=DemoViewSet, PlainObject=object)
    command = Command()
    monkeypatch.setattr(command, "_get_current_date", lambda: "2026-08-03")

    assert command._find_viewset_classes(module) == [("DemoViewSet", DemoViewSet)]
    content = command._generate_doc_content("demo_module", [("DemoViewSet", DemoViewSet)])

    assert "#### DELETE /api/v1/demo-module/resources/{id}/" in content
    assert "Custom action: approve" in content
    assert "Custom action: summary" in content
    assert command._document_endpoint("GET", "/resource/", "Read") == (
        "#### GET /resource/\n\n"
        "Read\n\n"
        "**Request:** `GET`\n\n"
        "**Response:** `200 OK` (or appropriate status code)\n\n"
        "```json\n"
        "{\n"
        '  "id": "uuid",\n'
        '  "tenant_id": "tenant-uuid",\n'
        '  "name": "Resource Name",\n'
        '  "description": "Resource description",\n'
        '  "is_active": true,\n'
        '  "config": {},\n'
        '  "created_by": "user-uuid",\n'
        '  "created_at": "2026-01-09T00:00:00Z",\n'
        '  "updated_at": "2026-01-09T00:00:00Z"\n'
        "}\n"
        "```\n\n"
    )
