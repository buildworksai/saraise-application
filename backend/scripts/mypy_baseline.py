#!/usr/bin/env python3
"""Enforce an exact, ratcheting baseline for existing MyPy findings."""

from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASELINE_PATH = BACKEND_DIR / "mypy-baseline.txt"
CONFIG_PATH = BACKEND_DIR / "mypy-precommit.ini"
REQUIRED_VERSIONS = {
    "mypy": "2.3.0",
    "django-stubs": "6.0.7",
    "djangorestframework-stubs": "3.17.0",
}


def error_lines(output: str) -> list[str]:
    """Return stable MyPy error fingerprints, excluding notes and summaries."""
    return sorted(line for line in output.splitlines() if ": error: " in line)


def verify_toolchain() -> None:
    """Refuse to compare results produced by an unreviewed analyzer toolchain."""
    mismatches = []
    for package, expected in REQUIRED_VERSIONS.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = "not installed"
        if actual != expected:
            mismatches.append(f"{package}: expected {expected}, found {actual}")

    if mismatches:
        raise SystemExit("MyPy baseline toolchain mismatch:\n" + "\n".join(mismatches))


def read_baseline() -> list[str]:
    """Load the reviewed findings without treating comments as findings."""
    return [
        line for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")
    ]


def run_mypy() -> subprocess.CompletedProcess[str]:
    """Run MyPy deterministically from the backend directory."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(CONFIG_PATH),
            "--no-incremental",
            "--show-error-codes",
            "--no-error-summary",
            "src",
        ],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


def check() -> int:
    """Allow removal of debt, but reject every new or changed finding."""
    verify_toolchain()
    baseline = read_baseline()
    result = run_mypy()
    combined_output = result.stdout + result.stderr
    current = error_lines(combined_output)

    if result.returncode not in (0, 1):
        print(combined_output, end="", file=sys.stderr)
        print(f"MyPy failed to execute (exit {result.returncode}).", file=sys.stderr)
        return result.returncode

    new_findings = list((Counter(current) - Counter(baseline)).elements())
    if new_findings:
        print("New or changed MyPy findings:", file=sys.stderr)
        print("\n".join(sorted(new_findings)), file=sys.stderr)
        print(
            f"MyPy ratchet failed: {len(baseline)} baseline findings, "
            f"{len(current)} current findings, {len(new_findings)} new or changed.",
            file=sys.stderr,
        )
        return 1

    print(
        f"MyPy ratchet passed: {len(baseline)} baseline findings, "
        f"{len(current)} current findings, 0 new or changed."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.parse_args()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
