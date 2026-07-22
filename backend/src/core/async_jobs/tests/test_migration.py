"""SQLite forward/reverse verification for the initial async-jobs migration."""

from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_initial_migration_is_reversible_on_sqlite() -> None:
    executor = MigrationExecutor(connection)
    target = [("async_jobs", "0001_initial")]
    restore_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([("async_jobs", None)])
        assert "async_jobs" not in connection.introspection.table_names()
        assert "async_job_transitions" not in connection.introspection.table_names()
        assert "async_job_outbox_events" not in connection.introspection.table_names()

        executor.loader.build_graph()
        executor.migrate(target)
        tables = connection.introspection.table_names()
        assert "async_jobs" in tables
        assert "async_job_transitions" in tables
        assert "async_job_outbox_events" in tables

        tenant_field = (
            executor.loader.project_state(target).apps.get_model("async_jobs", "AsyncJob")._meta.get_field("tenant_id")
        )
        assert tenant_field.get_internal_type() == "UUIDField"
        assert tenant_field.db_index is True

        executor.loader.build_graph()
        executor.migrate([("async_jobs", None)])
        assert "async_jobs" not in connection.introspection.table_names()
    finally:
        # Unapplying async_jobs also unapplies every dependent module. Restore
        # the complete pre-test graph so later tests inherit no schema damage.
        executor.loader.build_graph()
        executor.migrate(restore_targets)
