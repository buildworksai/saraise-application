"""
Root conftest - runs before any tests. Sets SQLite for tests when Postgres unavailable.
"""

import os
import sys

import pytest

pytest_plugins = ["src.core.testing"]

# Must run before Django settings load - set env for SQLite in tests
if "pytest" in sys.argv or "test" in sys.argv:
    os.environ["DJANGO_USE_SQLITE_FOR_TESTS"] = "1"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip DB migration graph tests only when pytest-django has disabled migrations."""

    if not config.getoption("nomigrations", default=False):
        return

    skip_disabled_migrations = pytest.mark.skip(
        reason="Migration graph/database DDL tests require migrations; pytest is running with --nomigrations."
    )
    for item in items:
        path = str(item.path)
        if "/test_migration" in path and item.get_closest_marker("django_db") is not None:
            item.add_marker(skip_disabled_migrations)
