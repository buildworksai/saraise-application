from __future__ import annotations

from pathlib import Path

from scripts.mutation_gate import _derived_test_targets, _runner_for_files


def test_core_package_sources_use_package_local_tests() -> None:
    targets = _derived_test_targets(Path("src/core/async_jobs/models.py"), Path.cwd())

    assert targets == (Path("src/core/async_jobs/tests"),)


def test_runner_includes_default_tests_when_file_has_specific_targets() -> None:
    runner = _runner_for_files(
        [
            Path("src/core/management/commands/seed_default_users.py"),
            Path("src/modules/business_intelligence/services.py"),
        ],
        Path.cwd(),
    )

    assert " -q src/core/tests " in runner
    assert "src/modules/business_intelligence/tests" in runner
    assert "src/core/tests/test_seed_default_users.py" in runner
    assert "src/core/tests/test_seed_default_users_collector.py" in runner
