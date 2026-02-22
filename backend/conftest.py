"""
Root conftest - runs before any tests. Sets SQLite for tests when Postgres unavailable.
"""
import os
import sys

# Must run before Django settings load - set env for SQLite in tests
if "pytest" in sys.argv or "test" in sys.argv:
    os.environ["DJANGO_USE_SQLITE_FOR_TESTS"] = "1"
