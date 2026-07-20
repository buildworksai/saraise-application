"""Self-tests for the fail-closed per-component coverage gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
COVERAGE_SCRIPT = REPOSITORY_ROOT / "scripts" / "coverage-per-module.py"


def _load_coverage_gate() -> ModuleType:
    """Load the executable coverage script as an importable test subject."""

    spec = importlib.util.spec_from_file_location("saraise_coverage_gate", COVERAGE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load coverage gate at {COVERAGE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


coverage_gate = _load_coverage_gate()


def _make_source_tree(root: Path) -> None:
    """Create the smallest repository layout understood by the gate."""

    for directory in (
        "backend/src/modules/example",
        "backend/src/core",
        "backend/saraise_backend",
        "frontend/src/modules/example",
    ):
        (root / directory).mkdir(parents=True)


def _write_backend_report(path: Path, *, example_percent: int = 100) -> None:
    """Write valid branch-enabled Cobertura evidence for every backend component."""

    example_hits = [1] * (example_percent // 10) + [0] * (10 - example_percent // 10)
    example_lines = "".join(
        f'<line number="{number}" hits="{hits}"/>' for number, hits in enumerate(example_hits, start=1)
    )
    example_branches = example_percent // 10
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0" ?>
<coverage branch-rate="0.9" branches-covered="12" branches-valid="14">
  <packages><package name="src">
    <classes>
      <class filename="src/modules/example/services.py"><lines>
        {example_lines}
        <line number="20" hits="1" branch="true"
              condition-coverage="{example_percent}% ({example_branches}/10)"/>
      </lines></class>
      <class filename="src/core/services.py"><lines>
        <line number="1" hits="1" branch="true" condition-coverage="100% (2/2)"/>
      </lines></class>
      <class filename="saraise_backend/settings.py"><lines>
        <line number="1" hits="1" branch="true" condition-coverage="100% (2/2)"/>
      </lines></class>
    </classes>
  </package></packages>
</coverage>
""",
        encoding="utf-8",
    )


def _summary(covered: int, total: int) -> dict[str, Any]:
    percent = 100.0 if total == 0 else covered * 100.0 / total
    return {"covered": covered, "total": total, "skipped": 0, "pct": percent}


def _write_frontend_report(path: Path) -> None:
    """Write valid line and branch counters for the example frontend module."""

    file_coverage = {
        "lines": _summary(10, 10),
        "branches": _summary(4, 4),
        "statements": _summary(10, 10),
        "functions": _summary(2, 2),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "total": file_coverage,
                "frontend/src/modules/example/page.tsx": file_coverage,
            }
        ),
        encoding="utf-8",
    )


def test_discovers_every_backend_module_and_shared_component() -> None:
    """The inventory follows the source tree and includes non-module runtime code."""

    modules = coverage_gate.discover_backend_modules(REPOSITORY_ROOT)
    components = coverage_gate.discover_backend_components(REPOSITORY_ROOT)

    expected_modules = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in (REPOSITORY_ROOT / "backend/src/modules").iterdir()
        if path.is_dir() and path.name not in {"__pycache__", "__tests__"} and not path.name.startswith(".")
    }
    assert len(modules) >= 41
    assert set(modules) == expected_modules
    assert "backend/src/core" in components
    assert "backend/saraise_backend" in components


def test_gate_fails_when_a_report_is_missing(tmp_path: Path) -> None:
    """No report means no evidence, even when the other report is valid."""

    _make_source_tree(tmp_path)
    frontend_report = tmp_path / "frontend/coverage/coverage-summary.json"
    _write_frontend_report(frontend_report)

    result = coverage_gate.main(
        repo_root=tmp_path,
        backend_report=tmp_path / "backend/missing-coverage.xml",
        frontend_report=frontend_report,
    )

    assert result != 0


def test_gate_fails_when_one_component_is_below_threshold(tmp_path: Path) -> None:
    """A weak module cannot be concealed by stronger shared components."""

    _make_source_tree(tmp_path)
    backend_report = tmp_path / "backend/coverage.xml"
    frontend_report = tmp_path / "frontend/coverage/coverage-summary.json"
    _write_backend_report(backend_report, example_percent=80)
    _write_frontend_report(frontend_report)

    result = coverage_gate.main(
        repo_root=tmp_path,
        backend_report=backend_report,
        frontend_report=frontend_report,
        threshold=90.0,
    )

    assert result != 0


@pytest.mark.parametrize("contents", ["", "not XML", "<coverage>"])
def test_backend_parser_rejects_empty_or_malformed_reports(tmp_path: Path, contents: str) -> None:
    """Broken backend artifacts are explicit coverage failures."""

    report = tmp_path / "coverage.xml"
    report.write_text(contents, encoding="utf-8")

    with pytest.raises(coverage_gate.CoverageReportError):
        coverage_gate.parse_coverage_xml(report, ["backend/src/core"])


@pytest.mark.parametrize("contents", ["", "not JSON", "{}", "[]"])
def test_frontend_parser_rejects_empty_or_malformed_reports(tmp_path: Path, contents: str) -> None:
    """Broken frontend artifacts are explicit coverage failures."""

    report = tmp_path / "coverage-summary.json"
    report.write_text(contents, encoding="utf-8")

    with pytest.raises(coverage_gate.CoverageReportError):
        coverage_gate.parse_coverage_json(report, ["frontend/src/modules/example"])


def test_backend_parser_rejects_line_only_coverage(tmp_path: Path) -> None:
    """A line-only Cobertura artifact is not branch-coverage evidence."""

    report = tmp_path / "coverage.xml"
    report.write_text(
        '<coverage branch-rate="0" branches-covered="0" branches-valid="0"/>',
        encoding="utf-8",
    )

    with pytest.raises(coverage_gate.CoverageReportError, match="branch evidence"):
        coverage_gate.parse_coverage_xml(report, ["backend/src/core"])
