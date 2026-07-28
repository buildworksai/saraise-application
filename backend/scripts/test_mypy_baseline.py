#!/usr/bin/env python3
"""Mutation test proving the MyPy ratchet covers its configured scope."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
BASELINE_PATH = BACKEND_DIR / "mypy-baseline.txt"


def baseline_files() -> tuple[str, ...]:
    """Return every source file represented in the reviewed baseline."""
    files = {
        line.split(":", 1)[0]
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    return tuple(sorted(path for path in files if path.startswith("src/") and path.endswith(".py")))


def main() -> int:
    represented_files = baseline_files()
    if not represented_files:
        print("Mutation test failed: no backend/src files are represented in the MyPy baseline.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="saraise-mypy-ratchet-") as temporary_directory:
        test_backend = Path(temporary_directory) / "backend"
        shutil.copytree(
            BACKEND_DIR,
            test_backend,
            ignore=shutil.ignore_patterns(
                ".mypy_cache",
                ".pytest_cache",
                ".venv",
                "__pycache__",
                "coverage*",
                "schema.*",
                "venv",
            ),
        )

        for index, relative_path in enumerate(represented_files):
            source_file = test_backend / relative_path
            with source_file.open("a", encoding="utf-8") as file_handle:
                file_handle.write(f"\n__mypy_ratchet_probe_{index}: str = {index}\n")

        scope_probe = test_backend / "src" / "__mypy_scope_probe.py"
        scope_probe.write_text("__mypy_scope_probe: str = 1\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "scripts/mypy_baseline.py", "check"],
            cwd=test_backend,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            print(output, end="", file=sys.stderr)
            print("Mutation test failed: the ratchet accepted injected errors.", file=sys.stderr)
            return 1

        missing = [path for path in represented_files if path not in output]
        if str(scope_probe.relative_to(test_backend)) not in output:
            missing.append(str(scope_probe.relative_to(test_backend)))
        if missing:
            print(output, end="", file=sys.stderr)
            print("Mutation test did not detect probes in:\n" + "\n".join(missing), file=sys.stderr)
            return 1

        print(f"MyPy ratchet mutation test passed for {len(represented_files)} baseline source files plus scope probe.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
