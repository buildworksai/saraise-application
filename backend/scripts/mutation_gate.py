#!/usr/bin/env python3
"""Run mutmut against changed backend source files and enforce the mutation score."""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

THRESHOLD = 90.0
APPLICABLE_STATUSES = ("killed", "survived", "timeout", "suspicious")
ALL_STATUSES = (*APPLICABLE_STATUSES, "untested", "skipped")
EXCLUDED_DIRECTORIES = {"generated", "migrations", "test", "tests"}
EXCLUDED_FILENAMES = ("settings*.py", "test_*.py", "*_test.py", "*_tests.py")


def _source_files(arguments: list[str], package_root: Path) -> list[Path]:
    source_root = (package_root / "src").resolve()
    selected: set[Path] = set()

    for argument in arguments:
        candidate = Path(argument)
        if candidate.parts[:1] == ("backend",):
            candidate = Path(*candidate.parts[1:])
        if not candidate.is_absolute():
            candidate = package_root / candidate
        candidate = candidate.resolve()

        try:
            relative = candidate.relative_to(source_root)
        except ValueError:
            continue
        if not candidate.is_file() or candidate.suffix != ".py":
            continue
        if EXCLUDED_DIRECTORIES.intersection(relative.parts):
            continue
        if any(fnmatch.fnmatch(candidate.name, pattern) for pattern in EXCLUDED_FILENAMES):
            continue
        selected.add(candidate.relative_to(package_root))

    return sorted(selected)


def _result_counts(package_root: Path) -> dict[str, int]:
    report = subprocess.run(
        ["mutmut", "junitxml", "--suspicious-policy", "error", "--untested-policy", "skipped"],
        cwd=package_root,
        check=True,
        capture_output=True,
        env=_mutation_environment(),
        text=True,
    )
    root = ET.fromstring(report.stdout)
    testcases = root.findall(".//testcase")
    counts = {status: 0 for status in ALL_STATUSES}

    for testcase in testcases:
        outcome = next((child for child in testcase if child.tag in {"error", "failure", "skipped"}), None)
        if outcome is None:
            counts["killed"] += 1
            continue
        message = outcome.attrib.get("message")
        if message == "bad_survived":
            counts["survived"] += 1
        elif message == "bad_timeout":
            counts["timeout"] += 1
        elif message == "ok_suspicious":
            counts["suspicious"] += 1
        elif message == "untested":
            counts["untested"] += 1
        else:
            raise RuntimeError(f"Unexpected mutmut JUnit outcome: {message!r}")

    skipped = subprocess.run(
        ["mutmut", "result-ids", "skipped"],
        cwd=package_root,
        check=True,
        capture_output=True,
        env=_mutation_environment(),
        text=True,
    )
    counts["skipped"] = len(skipped.stdout.split())
    counts["killed"] -= counts["skipped"]
    if counts["killed"] < 0:
        raise RuntimeError("mutmut reported more skipped mutants than successful JUnit cases")
    return counts


def _mutation_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{environment.get('PATH', '')}"
    return environment


def run_gate(arguments: list[str], package_root: Path) -> int:
    files = _source_files(arguments, package_root)
    if not files:
        print("Mutation gate: no applicable changed Python source files; skipping.")
        return 0

    cache = package_root / ".mutmut-cache"
    cache.unlink(missing_ok=True)

    mutation_paths = ",".join(path.as_posix() for path in files)
    print(f"Mutation gate: mutating {mutation_paths}", flush=True)
    run = subprocess.run(
        [
            "mutmut",
            "run",
            "--paths-to-mutate",
            mutation_paths,
            "--simple-output",
            "--no-progress",
        ],
        cwd=package_root,
        check=False,
        env=_mutation_environment(),
    )
    if run.returncode & 1:
        print(f"Mutation gate: mutmut failed fatally with exit code {run.returncode}.", file=sys.stderr)
        return 1

    counts = _result_counts(package_root)
    total_applicable = sum(counts[status] for status in APPLICABLE_STATUSES)
    score = 100.0 if total_applicable == 0 else counts["killed"] / total_applicable * 100.0

    print("Mutation gate results:")
    for status in ALL_STATUSES:
        print(f"  {status}: {counts[status]}")
    print(f"  total applicable: {total_applicable}")
    print(f"  score: {score:.2f}% (required: {THRESHOLD:.1f}%)")

    if score < THRESHOLD:
        print("Mutation gate: FAILED", file=sys.stderr)
        return 1
    print("Mutation gate: PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Changed source files, relative to the repository or backend")
    args = parser.parse_args()
    return run_gate(args.files, Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    raise SystemExit(main())
