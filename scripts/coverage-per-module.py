#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Enforce honest line and branch coverage for every SARAISE component.

The gate deliberately derives its inventory from the source tree.  A newly added
module is therefore covered by the gate without somebody remembering to update a
second, easily stale list.  Coverage is calculated from covered/total counters;
percentages are never averaged, because averaging percentages gives tiny files
the same weight as large files and can conceal missing coverage.

Both reports are required and must contain real branch-coverage evidence.  A
missing, empty, malformed, or line-only report is a gate failure, never a skip.
"""

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

THRESHOLD = 90.0
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKEND_REPORT = Path("backend/coverage.xml")
DEFAULT_FRONTEND_REPORT = Path("frontend/coverage/coverage-summary.json")


class CoverageReportError(ValueError):
    """Raised when a report cannot provide trustworthy coverage evidence."""


@dataclass
class CoverageMetrics:
    """Exact coverage counters for one component."""

    covered_lines: int = 0
    total_lines: int = 0
    covered_branches: int = 0
    total_branches: int = 0

    def add(self, other: "CoverageMetrics") -> None:
        """Add file-level counters without averaging percentages."""

        self.covered_lines += other.covered_lines
        self.total_lines += other.total_lines
        self.covered_branches += other.covered_branches
        self.total_branches += other.total_branches

    @property
    def line_percent(self) -> float:
        """Return line coverage, treating no executable lines as no evidence."""

        if not self.total_lines:
            return 0.0
        return self.covered_lines * 100.0 / self.total_lines

    @property
    def branch_percent(self) -> float:
        """Return branch coverage (100% when a component has no branches)."""

        if not self.total_branches:
            return 100.0
        return self.covered_branches * 100.0 / self.total_branches


@dataclass(frozen=True)
class CoverageResult:
    """One component's evaluated line and branch coverage."""

    component: str
    line_percent: float
    branch_percent: float
    has_line_evidence: bool

    def passes(self, threshold: float) -> bool:
        """Return whether every independently enforced metric passes."""

        return self.has_line_evidence and self.line_percent >= threshold and self.branch_percent >= threshold


def _discover_directories(parent: Path, excluded_names: set[str]) -> list[Path]:
    if not parent.is_dir():
        raise CoverageReportError(f"source directory not found: {parent}")
    return sorted(
        (
            path
            for path in parent.iterdir()
            if path.is_dir() and path.name not in excluded_names and not path.name.startswith(".")
        ),
        key=lambda path: path.name,
    )


def discover_backend_modules(repo_root: Path = REPO_ROOT) -> list[str]:
    """Discover every first-party module under ``backend/src/modules``."""

    root = Path(repo_root).resolve()
    modules = _discover_directories(root / "backend/src/modules", {"__pycache__", "__tests__"})
    return [path.relative_to(root).as_posix() for path in modules]


def discover_frontend_modules(repo_root: Path = REPO_ROOT) -> list[str]:
    """Discover every frontend module rather than maintaining a parallel list."""

    root = Path(repo_root).resolve()
    modules = _discover_directories(root / "frontend/src/modules", {"__pycache__", "__tests__"})
    return [path.relative_to(root).as_posix() for path in modules]


def discover_backend_components(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return modules plus the shared backend runtime components."""

    root = Path(repo_root).resolve()
    shared_components = ["backend/src/core", "backend/saraise_backend"]
    missing = [name for name in shared_components if not (root / name).is_dir()]
    if missing:
        raise CoverageReportError("source directory not found: " + ", ".join(sorted(missing)))
    return [*discover_backend_modules(root), *shared_components]


# Import-time inventories preserve the original script's useful public surface,
# while remaining derived from the checked-out source tree rather than hardcoded.
BACKEND_MODULES = tuple(discover_backend_modules())
BACKEND_COMPONENTS = tuple(discover_backend_components())
FRONTEND_MODULES = tuple(discover_frontend_modules())


def _normalise_report_path(filename: str) -> str:
    normalised = filename.replace("\\", "/")
    return PurePosixPath(normalised).as_posix()


def _component_for_file(filename: str, components: Sequence[str]) -> str | None:
    """Map absolute or common coverage-relative filenames to a component."""

    normalised = _normalise_report_path(filename)
    padded_filename = f"/{normalised.lstrip('/')}"
    for component in components:
        candidates = {component}
        if component.startswith("backend/"):
            candidates.add(component.removeprefix("backend/"))
        elif component.startswith("frontend/"):
            candidates.add(component.removeprefix("frontend/"))
        for candidate in candidates:
            padded_candidate = f"/{candidate.strip('/')}"
            if padded_filename == padded_candidate or padded_filename.startswith(f"{padded_candidate}/"):
                return component
            if f"{padded_candidate}/" in padded_filename:
                return component
    return None


def _is_non_product_file(filename: str) -> bool:
    """Exclude tests and generated migrations from product coverage counters."""

    path = PurePosixPath(_normalise_report_path(filename))
    parts = set(path.parts)
    name = path.name
    return (
        "tests" in parts
        or "__tests__" in parts
        or "migrations" in parts
        or name == "conftest.py"
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    )


def _parse_nonnegative_int(value: object, context: str) -> int:
    if isinstance(value, bool):
        raise CoverageReportError(f"{context} must be a non-negative integer")
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise CoverageReportError(f"{context} must be a non-negative integer") from error
    if parsed < 0 or str(value).strip() not in {str(parsed), f"{parsed}.0"}:
        raise CoverageReportError(f"{context} must be a non-negative integer")
    return parsed


def _validate_counter_pair(covered: int, total: int, context: str) -> None:
    if covered > total:
        raise CoverageReportError(f"{context} has covered count {covered} greater than total {total}")


_CONDITION_COVERAGE = re.compile(r"^\s*[^()]*(?:\((\d+)\s*/\s*(\d+)\))\s*$")


def _parse_condition_coverage(value: str | None, context: str) -> tuple[int, int]:
    if value is None:
        raise CoverageReportError(f"{context} is missing condition-coverage")
    match = _CONDITION_COVERAGE.match(value)
    if not match:
        raise CoverageReportError(f"{context} has malformed condition-coverage")
    covered, total = (int(number) for number in match.groups())
    _validate_counter_pair(covered, total, context)
    if total == 0:
        raise CoverageReportError(f"{context} has an empty branch counter")
    return covered, total


def _load_xml(coverage_file: Path):  # type: ignore[no-untyped-def]
    try:
        from defusedxml.ElementTree import parse
    except ImportError:  # pragma: no cover - dependency-free CLI fallback
        from xml.etree.ElementTree import parse

    try:
        return parse(coverage_file)
    except (OSError, ValueError, SyntaxError) as error:
        raise CoverageReportError(f"malformed backend coverage report {coverage_file}: {error}") from error
    except Exception as error:
        # DefusedXML raises its own safe-parser exception classes.
        raise CoverageReportError(f"malformed backend coverage report {coverage_file}: {error}") from error


def _validate_backend_branch_metadata(root, coverage_file: Path) -> None:  # type: ignore[no-untyped-def]
    branches_valid = _parse_nonnegative_int(root.get("branches-valid"), "backend branches-valid")
    branches_covered = _parse_nonnegative_int(root.get("branches-covered"), "backend branches-covered")
    _validate_counter_pair(branches_covered, branches_valid, "backend branch coverage")
    try:
        branch_rate = float(root.get("branch-rate"))
    except (TypeError, ValueError) as error:
        raise CoverageReportError("backend branch-rate is missing or malformed") from error
    if not math.isfinite(branch_rate) or not 0.0 <= branch_rate <= 1.0:
        raise CoverageReportError("backend branch-rate must be between zero and one")
    if branches_valid == 0:
        raise CoverageReportError(
            f"backend report {coverage_file} has no branch evidence; rerun pytest " "with --cov-branch"
        )


def parse_coverage_xml(coverage_file: Path, components: Sequence[str] | None = None) -> dict[str, CoverageMetrics]:
    """Parse exact per-component counters from a branch-enabled Cobertura XML."""

    report = Path(coverage_file)
    if not report.is_file():
        raise CoverageReportError(f"backend coverage report not found: {report}")
    if report.stat().st_size == 0:
        raise CoverageReportError(f"backend coverage report is empty: {report}")

    expected = tuple(components or BACKEND_COMPONENTS)
    tree = _load_xml(report)
    root = tree.getroot()
    if root.tag != "coverage":
        raise CoverageReportError(f"backend coverage report has unexpected root element: {root.tag}")
    _validate_backend_branch_metadata(root, report)

    metrics = {component: CoverageMetrics() for component in expected}
    classes = root.findall(".//class")
    if not classes:
        raise CoverageReportError(f"backend coverage report contains no file-level evidence: {report}")

    relevant_files = 0
    for class_element in classes:
        filename = class_element.get("filename")
        if not filename:
            raise CoverageReportError("backend coverage class is missing filename")
        component = _component_for_file(filename, expected)
        if component is None or _is_non_product_file(filename):
            continue
        relevant_files += 1
        file_metrics = CoverageMetrics()
        for line in class_element.findall("./lines/line"):
            hits = _parse_nonnegative_int(line.get("hits"), f"backend line hit count in {filename}")
            file_metrics.total_lines += 1
            if hits > 0:
                file_metrics.covered_lines += 1
            if line.get("branch", "false").lower() == "true":
                covered, total = _parse_condition_coverage(
                    line.get("condition-coverage"),
                    f"backend branch counter in {filename}",
                )
                file_metrics.covered_branches += covered
                file_metrics.total_branches += total
        metrics[component].add(file_metrics)

    if relevant_files == 0:
        raise CoverageReportError(f"backend coverage report contains no expected source files: {report}")
    return metrics


def _parse_json_metric(coverage_data: Mapping[str, object], metric_name: str, filename: str) -> tuple[int, int]:
    value = coverage_data.get(metric_name)
    if not isinstance(value, Mapping):
        raise CoverageReportError(f"{filename} is missing {metric_name} coverage")
    covered = _parse_nonnegative_int(value.get("covered"), f"{filename} {metric_name}.covered")
    total = _parse_nonnegative_int(value.get("total"), f"{filename} {metric_name}.total")
    _validate_counter_pair(covered, total, f"{filename} {metric_name} coverage")
    return covered, total


def _validate_frontend_branch_metadata(data: Mapping[str, object], report: Path) -> None:
    total = data.get("total")
    if not isinstance(total, Mapping):
        raise CoverageReportError(f"frontend report has no total coverage object: {report}")
    covered, branch_total = _parse_json_metric(total, "branches", "total")
    _validate_counter_pair(covered, branch_total, "frontend total branch coverage")
    if branch_total == 0:
        raise CoverageReportError(f"frontend report {report} has no branch evidence; enable branch coverage")


def parse_coverage_json(coverage_file: Path, components: Sequence[str] | None = None) -> dict[str, CoverageMetrics]:
    """Parse exact per-component counters from Jest coverage-summary JSON."""

    report = Path(coverage_file)
    if not report.is_file():
        raise CoverageReportError(f"frontend coverage report not found: {report}")
    if report.stat().st_size == 0:
        raise CoverageReportError(f"frontend coverage report is empty: {report}")
    try:
        raw_data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CoverageReportError(f"malformed frontend coverage report {report}: {error}") from error
    if not isinstance(raw_data, Mapping):
        raise CoverageReportError(f"frontend coverage report must contain a JSON object: {report}")
    _validate_frontend_branch_metadata(raw_data, report)

    expected = tuple(components or FRONTEND_MODULES)
    metrics = {component: CoverageMetrics() for component in expected}
    relevant_files = 0
    for filename, value in raw_data.items():
        if filename == "total":
            continue
        if not isinstance(filename, str) or not isinstance(value, Mapping):
            raise CoverageReportError(f"frontend report contains a malformed file entry: {filename!r}")
        component = _component_for_file(filename, expected)
        if component is None or _is_non_product_file(filename):
            continue
        relevant_files += 1
        covered_lines, total_lines = _parse_json_metric(value, "lines", filename)
        covered_branches, total_branches = _parse_json_metric(value, "branches", filename)
        metrics[component].add(
            CoverageMetrics(
                covered_lines=covered_lines,
                total_lines=total_lines,
                covered_branches=covered_branches,
                total_branches=total_branches,
            )
        )

    if relevant_files == 0:
        raise CoverageReportError(f"frontend coverage report contains no expected source files: {report}")
    return metrics


def evaluate_components(components: Iterable[str], metrics: Mapping[str, CoverageMetrics]) -> list[CoverageResult]:
    """Evaluate every discovered component, including absent report entries."""

    results = []
    for component in components:
        component_metrics = metrics.get(component, CoverageMetrics())
        results.append(
            CoverageResult(
                component=component,
                line_percent=component_metrics.line_percent,
                branch_percent=component_metrics.branch_percent,
                has_line_evidence=component_metrics.total_lines > 0,
            )
        )
    return results


def check_backend_coverage(
    repo_root: Path = REPO_ROOT,
    coverage_file: Path | None = None,
) -> list[CoverageResult]:
    """Load and evaluate coverage for all backend components."""

    root = Path(repo_root).resolve()
    components = discover_backend_components(root)
    report = Path(coverage_file) if coverage_file else root / DEFAULT_BACKEND_REPORT
    return evaluate_components(components, parse_coverage_xml(report, components))


def check_frontend_coverage(
    repo_root: Path = REPO_ROOT,
    coverage_file: Path | None = None,
) -> list[CoverageResult]:
    """Load and evaluate coverage for all dynamically discovered frontend modules."""

    root = Path(repo_root).resolve()
    components = discover_frontend_modules(root)
    report = Path(coverage_file) if coverage_file else root / DEFAULT_FRONTEND_REPORT
    return evaluate_components(components, parse_coverage_json(report, components))


def _print_results(results: Sequence[CoverageResult], threshold: float) -> int:
    failures = [result for result in results if not result.passes(threshold)]
    passing = [result for result in results if result.passes(threshold)]

    if passing:
        print(f"\nPassing components ({len(passing)}):")
        for result in sorted(passing, key=lambda item: item.component):
            print(
                f"  PASS {result.component}: lines {result.line_percent:.1f}%, "
                f"branches {result.branch_percent:.1f}%"
            )
    if failures:
        print(f"\nFailing components ({len(failures)}):")
        for result in sorted(failures, key=lambda item: item.component):
            reason = (
                "missing file evidence"
                if not result.has_line_evidence
                else (f"lines {result.line_percent:.1f}%, " f"branches {result.branch_percent:.1f}%")
            )
            print(f"  FAIL {result.component}: {reason}")
    return len(failures)


def main(
    repo_root: Path = REPO_ROOT,
    backend_report: Path | None = None,
    frontend_report: Path | None = None,
    threshold: float = THRESHOLD,
) -> int:
    """Run the complete gate and return a process-compatible status code."""

    if not math.isfinite(threshold) or not 0.0 <= threshold <= 100.0:
        print("ERROR: threshold must be between zero and 100", file=sys.stderr)
        return 2

    print(f"Checking per-component line and branch coverage (threshold: {threshold}%)")
    try:
        backend = check_backend_coverage(repo_root, backend_report)
        frontend = check_frontend_coverage(repo_root, frontend_report)
    except CoverageReportError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    results = [*backend, *frontend]
    failure_count = _print_results(results, threshold)
    if failure_count:
        print(f"\nFAILED: {failure_count} component(s) are below the coverage gate")
        return 1
    print(f"\nPASSED: all {len(results)} components meet the coverage gate")
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (defaults to the script's parent repository)",
    )
    parser.add_argument(
        "--backend-report",
        type=Path,
        help="override the backend coverage.xml path",
    )
    parser.add_argument(
        "--frontend-report",
        type=Path,
        help="override the frontend coverage-summary.json path",
    )
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args()
    raise SystemExit(
        main(
            repo_root=arguments.repo_root,
            backend_report=arguments.backend_report,
            frontend_report=arguments.frontend_report,
            threshold=arguments.threshold,
        )
    )
